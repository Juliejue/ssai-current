from __future__ import annotations

import asyncio
import json
import uuid
from functools import lru_cache
from pathlib import Path

from .map_provider import AmapClient, MapProviderError, WalkingRoute, navigation_url
from .schemas import NeedState, RecommendRequest, Recommendation


DATA_PATH = Path(__file__).parent / "data" / "places.json"
OVERRIDES_PATH = Path(__file__).parent / "data" / "place_overrides.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with DATA_PATH.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if OVERRIDES_PATH.exists():
        with OVERRIDES_PATH.open(encoding="utf-8") as handle:
            overrides = json.load(handle).get("places", {})
        for place in catalog["PLACES"]:
            if place["placeId"] in overrides:
                place.update(overrides[place["placeId"]])
    return catalog


def _target_for(state: NeedState, catalog: dict) -> tuple[dict[str, float], dict[str, int]]:
    target = dict(catalog["MOOD_TARGET"].get(state.mood_id, catalog["MOOD_TARGET"]["low"]))
    boosts: dict[str, int] = {}
    for key in state.need_keys:
        need = catalog["NEEDS"].get(key)
        if not need:
            continue
        for dimension, value in need["target"].items():
            target[dimension] = value
            boosts[dimension] = boosts.get(dimension, 0) + 1
    return target, boosts


def _match_score(place: dict, state: NeedState, catalog: dict) -> float:
    target, boosts = _target_for(state, catalog)
    total = 0.0
    weight_total = 0.0
    for key, wanted in target.items():
        if key not in place["tags"]:
            continue
        weight = (abs(wanted - 0.5) + 0.5) * (1 + boosts.get(key, 0) * 1.8)
        total += (1 - abs(wanted - place["tags"][key])) * weight
        weight_total += weight
    return total / weight_total if weight_total else 0.0


def _hard_filter(place: dict, state: NeedState, rejected: set[str]) -> bool:
    if place["placeId"] in rejected:
        return False
    if state.environment == "indoor" and not place.get("indoor"):
        return False
    if state.environment == "outdoor" and place.get("indoor"):
        return False
    if state.budget_level == "free" and not place.get("free"):
        return False
    if state.social_mode == "alone" and place.get("crowd") == "high":
        return False
    if state.energy <= 1 and place.get("distanceKm", 0) > 8:
        return False
    return True


def _tradeoffs(place: dict) -> list[str]:
    factors = set(place.get("factors", []))
    labels = {
        "toocrowd": "可能会挤",
        "toonoisy": "声音可能偏大",
        "toopricey": "消费压力偏高",
        "needsocial": "可能需要和人周旋",
        "faraway": "路上可能消耗力气",
        "unsafe": "晚间需要额外注意安全",
    }
    return [label for key, label in labels.items() if key in factors][:3]


def _rank(request: RecommendRequest) -> list[tuple[float, dict, dict[str, float]]]:
    catalog = load_catalog()
    rejected = set(request.rejected_place_ids)
    ranked: list[tuple[float, dict, dict[str, float]]] = []

    for place in catalog["PLACES"]:
        if not _hard_filter(place, request.state, rejected):
            continue
        need_match = _match_score(place, request.state, catalog)
        energy_fit = 1.0
        if request.state.energy <= 1:
            energy_fit = max(0.0, 1 - place.get("tags", {}).get("l", 0.5) * 0.7 - place.get("tags", {}).get("c", 0.5) * 0.3)
        social_fit = 1.0
        if request.state.social_mode == "alone":
            social_fit = place.get("tags", {}).get("s", 0.5)
        elif request.state.social_mode == "with_people":
            social_fit = place.get("tags", {}).get("co", 0.5)
        travel_fit = max(0.0, 1 - float(place.get("distanceKm", 0)) / 20)
        budget_fit = 1.0 if request.state.budget_level == "unknown" else 1 - place.get("tags", {}).get("cp", 0.5)

        breakdown = {
            "need_match": round(need_match, 4),
            "energy_fit": round(energy_fit, 4),
            "travel_fit": round(travel_fit, 4),
            "social_fit": round(social_fit, 4),
            "budget_fit": round(budget_fit, 4),
        }
        score = need_match * 0.45 + energy_fit * 0.20 + travel_fit * 0.15 + social_fit * 0.10 + budget_fit * 0.10
        ranked.append((score, place, breakdown))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _to_recommendation(
    score: float,
    place: dict,
    breakdown: dict[str, float],
    state: NeedState,
    route: WalkingRoute | None = None,
) -> Recommendation:
    reasons = place.get("matchReason", {})
    reason = reasons.get(state.mood_id) or reasons.get("_") or "它和你刚才说的需要比较接近。"
    distance_km = round(route.distance_meters / 1000, 2) if route else place.get("distanceKm")
    walking_minutes = max(1, round(route.duration_seconds / 60)) if route else None
    return Recommendation(
        recommendation_id=f"rec_{uuid.uuid4().hex}",
        place_id=place["placeId"],
        place_name=place["placeName"],
        action=place["action"],
        reason=reason,
        score=round(max(0.0, min(1.0, score)), 4),
        distance_km=distance_km,
        walking_minutes=walking_minutes,
        distance_source="amap" if route else "prototype_estimate",
        map_verified=(place.get("amap") or {}).get("verification_status") == "verified",
        navigation_url=navigation_url(place),
        transport=place.get("transport"),
        suggested_duration=place.get("suggestedDuration"),
        cost=place.get("cost"),
        see=place.get("see"),
        tradeoffs=_tradeoffs(place),
        score_breakdown=breakdown,
    )


def recommend(request: RecommendRequest) -> list[Recommendation]:
    output: list[Recommendation] = []
    for score, place, breakdown in _rank(request)[: request.limit]:
        output.append(_to_recommendation(score, place, breakdown, request.state))
    return output


async def recommend_with_live_context(
    request: RecommendRequest,
    *,
    map_client: AmapClient | None = None,
) -> list[Recommendation]:
    ranked = _rank(request)
    client = map_client or AmapClient()
    if not request.location or not client.configured:
        return [
            _to_recommendation(score, place, breakdown, request.state)
            for score, place, breakdown in ranked[: request.limit]
        ]

    # Route only a bounded shortlist. A reviewed provider ID/coordinate is mandatory;
    # search results are never silently promoted to production data.
    shortlist = ranked[: max(request.limit * 3, 9)]
    semaphore = asyncio.Semaphore(4)

    async def route_for(place: dict) -> WalkingRoute | None:
        amap = place.get("amap") or {}
        if amap.get("verification_status") != "verified":
            return None
        try:
            async with semaphore:
                return await client.walking_route(
                    origin_longitude=request.location.longitude,
                    origin_latitude=request.location.latitude,
                    destination_longitude=float(amap["longitude"]),
                    destination_latitude=float(amap["latitude"]),
                    destination_id=amap.get("provider_place_id"),
                )
        except (KeyError, TypeError, ValueError, MapProviderError):
            return None

    routes = await asyncio.gather(*(route_for(place) for _, place, _ in shortlist))
    enriched: list[tuple[float, dict, dict[str, float], WalkingRoute | None]] = []
    for (score, place, breakdown), route in zip(shortlist, routes, strict=True):
        if route:
            walking_minutes = max(1, round(route.duration_seconds / 60))
            if request.state.max_travel_minutes and walking_minutes > request.state.max_travel_minutes:
                continue
            travel_fit = max(0.0, 1 - walking_minutes / 90)
            score = score - breakdown["travel_fit"] * 0.15 + travel_fit * 0.15
            breakdown = {**breakdown, "travel_fit": round(travel_fit, 4)}
        enriched.append((score, place, breakdown, route))

    enriched.sort(key=lambda item: item[0], reverse=True)
    return [
        _to_recommendation(score, place, breakdown, request.state, route)
        for score, place, breakdown, route in enriched[: request.limit]
    ]
