from __future__ import annotations

import json
import math
import uuid
from functools import lru_cache
from pathlib import Path

from .schemas import NeedState, RecommendRequest, Recommendation


DATA_PATH = Path(__file__).parent / "data" / "places.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with DATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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


def recommend(request: RecommendRequest) -> list[Recommendation]:
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
    output: list[Recommendation] = []
    for score, place, breakdown in ranked[: request.limit]:
        reasons = place.get("matchReason", {})
        reason = reasons.get(request.state.mood_id) or reasons.get("_") or "它和你刚才说的需要比较接近。"
        output.append(
            Recommendation(
                recommendation_id=f"rec_{uuid.uuid4().hex}",
                place_id=place["placeId"],
                place_name=place["placeName"],
                action=place["action"],
                reason=reason,
                score=round(max(0.0, min(1.0, score)), 4),
                distance_km=place.get("distanceKm"),
                transport=place.get("transport"),
                suggested_duration=place.get("suggestedDuration"),
                cost=place.get("cost"),
                see=place.get("see"),
                tradeoffs=_tradeoffs(place),
                score_breakdown=breakdown,
            )
        )
    return output

