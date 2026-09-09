from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .map_provider import AmapClient, MapProviderError, WalkingRoute, navigation_url
from .opening_hours import open_state
from .presence import geofence_radius_m, has_geofence
from .schemas import Geofence, NeedState, RecommendRequest, Recommendation


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


def _hard_filter(place: dict, state: NeedState, rejected: set[str], now: datetime | None = None) -> bool:
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
    # 估算出来的「大概率关着门」不能当硬约束——估算会错，用户会被无声地少给选项。
    # 只有核对过的营业时间才允许直接把地点拿掉。
    status, _, source = open_state(place, now)
    if source == "verified" and status == "closed":
        return False
    return True


# time-to-relief (FR-06): how long until this person is actually held, not how
# far the place is. An urgent state buys nearby options, never a better far one.
RELIEF_TIERS: tuple[tuple[int, str, str], ...] = (
    (10, "now", "现在就能到"),
    (25, "near", "二十分钟上下"),
    (10 ** 6, "later", "路上要花点时间 · 可以改天再去"),
)


def _estimate_reach_minutes(place: dict) -> int:
    """Prototype estimate, clearly separated from an AMap-measured walking time."""
    distance_km = float(place.get("distanceKm") or 0)
    return max(5, round(distance_km * 4) + 6)


def _relief_tier(minutes: int) -> tuple[str, str]:
    for threshold, tier, label in RELIEF_TIERS:
        if minutes <= threshold:
            return tier, label
    return "later", "路上要花点时间 · 可以改天再去"


def _is_hurried(state: NeedState) -> bool:
    if state.max_travel_minutes is not None and state.max_travel_minutes <= 15:
        return True
    return state.energy <= 1 or state.mood_id in {"tight", "noisy"}


RELIEF_BONUS = {"now": 0.12, "near": 0.04, "later": -0.10}

# 关着门的地方排到后面，但不隐藏——用户有权知道它存在、也有权自己判断估算对不对。
OPEN_PENALTY = {"likely_closed": -0.45, "closed": -0.60, "unknown": -0.05}

# How a tag reads when the state wants a LOW value of it.
# What a state asks for when the user has not named a need themselves.
MOOD_NEED_HINTS: dict[str, str] = {
    "low": "一个不用打起精神的地方",
    "quiet": "一个声音跟你无关的地方",
    "noisy": "一个能把注意力放出去的地方",
    "spark": "一个能撞见新东西的地方",
    "tired": "一个能坐下来不被催的地方",
    "empty": "一个有点人气、但不用应付的地方",
    "tight": "一个能松开肩膀的地方",
    "near": "一个周围有人、但不用说话的地方",
    "fresh": "一个你没去过的地方",
    "okay": "一个适合随便走走的地方",
}

LOW_TAG_LABELS: dict[str, str] = {
    "q": "有点声音",
    "g": "没什么绿",
    "c": "人不多",
    "s": "更适合结伴",
    "co": "没什么生活气",
    "e": "熟悉、不刺激",
    "r": "不特别放松",
    "cr": "不用动脑",
    "l": "不吵",
    "st": "待不久",
    "cp": "消费压力低",
    "w": "走不了太远",
}


def _reason_chain(place: dict, state: NeedState, catalog: dict) -> list[str]:
    """状态 → 需求 → 命中属性. Every line points at a stored field (FR-20)."""
    from .interpretation import NEED_LABELS, STATE_LABELS

    chain = [f"你说：{STATE_LABELS.get(state.mood_id, '说不太清楚')}"]
    needs = [NEED_LABELS[key] for key in state.need_keys if key in NEED_LABELS][:2]
    if needs:
        chain.append("所以要找：" + "、".join(needs))
    elif state.social_mode == "alone":
        chain.append("所以要找：一个人待着不奇怪的地方")
    elif state.budget_level == "free":
        chain.append("所以要找：不用消费也能待的地方")
    else:
        chain.append("所以要找：" + MOOD_NEED_HINTS.get(state.mood_id, "能让你慢下来的地方"))

    target, _ = _target_for(state, catalog)
    tags = place.get("tags", {})
    hits = sorted(
        (key for key, wanted in target.items() if key in tags and abs(wanted - tags[key]) <= 0.25),
        key=lambda key: -abs(target[key] - 0.5),
    )
    labels = [
        catalog["TAGS"][key] if target[key] >= 0.5 else LOW_TAG_LABELS.get(key, "不" + catalog["TAGS"][key])
        for key in hits
        if key in catalog["TAGS"]
    ][:3]
    chain.append("这里命中：" + "、".join(labels) if labels else "这里只是大致接近，我不太确定")
    return chain


def _tradeoffs(place: dict, reach_minutes: int) -> list[str]:
    """代价照实写. Derived from the reviewed place record, never invented."""
    tags = place.get("tags", {})
    costs: list[str] = []
    if place.get("crowd") == "high":
        costs.append("人会比较多")
    if tags.get("l", 0) >= 0.7:
        costs.append("声音偏大")
    if not place.get("free"):
        costs.append("消费压力偏高" if tags.get("cp", 0) >= 0.6 else "要花点钱")
    if reach_minutes >= 25:
        costs.append(f"路上大约 {reach_minutes} 分钟")
    if tags.get("st", 1) <= 0.35:
        costs.append("不太适合久待")
    return costs[:3] or ["暂时没看到明显的代价"]


def _rank(request: RecommendRequest, now: datetime | None = None) -> list[tuple[float, dict, dict[str, float]]]:
    catalog = load_catalog()
    rejected = set(request.rejected_place_ids)
    hurried = _is_hurried(request.state)
    ranked: list[tuple[float, dict, dict[str, float]]] = []

    for place in catalog["PLACES"]:
        if not _hard_filter(place, request.state, rejected, now):
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
        if hurried:
            tier, _ = _relief_tier(_estimate_reach_minutes(place))
            score += RELIEF_BONUS[tier]
            breakdown = {**breakdown, "relief_bonus": RELIEF_BONUS[tier]}
        status, _, _ = open_state(place, now)
        if status in OPEN_PENALTY:
            score += OPEN_PENALTY[status]
            breakdown = {**breakdown, "open_penalty": OPEN_PENALTY[status]}
        ranked.append((score, place, breakdown))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _to_recommendation(
    score: float,
    place: dict,
    breakdown: dict[str, float],
    state: NeedState,
    route: WalkingRoute | None = None,
    *,
    role: str = "alternate",
    now: datetime | None = None,
) -> Recommendation:
    reasons = place.get("matchReason", {})
    reason = reasons.get(state.mood_id) or reasons.get("_") or "它和你刚才说的需要比较接近。"
    distance_km = round(route.distance_meters / 1000, 2) if route else place.get("distanceKm")
    walking_minutes = max(1, round(route.duration_seconds / 60)) if route else None
    reach_minutes = walking_minutes or _estimate_reach_minutes(place)
    tier, relief_label = _relief_tier(reach_minutes)
    status, open_label, hours_source = open_state(place, now)
    amap = place.get("amap") or {}
    fence = (
        Geofence(
            latitude=float(amap["latitude"]),
            longitude=float(amap["longitude"]),
            radius_m=geofence_radius_m(place),
        )
        if has_geofence(place)
        else None
    )
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
        tradeoffs=_tradeoffs(place, reach_minutes),
        score_breakdown=breakdown,
        role=role,  # type: ignore[arg-type]
        reach_minutes=reach_minutes,
        time_to_relief=tier,  # type: ignore[arg-type]
        relief_label=relief_label,
        reason_chain=_reason_chain(place, state, load_catalog()),
        # Current has no verified visit feedback yet, so nothing may be
        # presented as an average (FR-10b). The prototype numbers stay out.
        sample_size=0,
        low_support=True,
        open_state=status,  # type: ignore[arg-type]
        open_label=open_label,
        hours_source=hours_source,  # type: ignore[arg-type]
        geofence=fence,
    )


def recommend(request: RecommendRequest, now: datetime | None = None) -> list[Recommendation]:
    output: list[Recommendation] = []
    for index, (score, place, breakdown) in enumerate(_rank(request, now)[: request.limit]):
        role = "primary" if index == 0 else "alternate"
        output.append(_to_recommendation(score, place, breakdown, request.state, role=role, now=now))
    return output


async def recommend_with_live_context(
    request: RecommendRequest,
    *,
    map_client: AmapClient | None = None,
    now: datetime | None = None,
) -> list[Recommendation]:
    ranked = _rank(request, now)
    client = map_client or AmapClient()
    if not request.location or not client.configured:
        return [
            _to_recommendation(score, place, breakdown, request.state, role="primary" if index == 0 else "alternate", now=now)
            for index, (score, place, breakdown) in enumerate(ranked[: request.limit])
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
        _to_recommendation(score, place, breakdown, request.state, route, role="primary" if index == 0 else "alternate", now=now)
        for index, (score, place, breakdown, route) in enumerate(enriched[: request.limit])
    ]
