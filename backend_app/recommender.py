from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .discovery import discover, warm as warm_search
from .i18n import (AVOID_LABELS_EN, LOW_TAG_LABELS_EN, NEED_LABELS_EN, RELIEF_LABELS_EN,
                   STATE_LABELS_EN, TAG_LABELS_EN, ui)
from .narrate import narrate_quietly
from .map_provider import (AmapClient, MapProviderError, TRUSTWORTHY_COORDINATES, WalkingRoute,
                            map_links, navigation_url)
from .opening_hours import open_state
from .presence import geofence_radius_m, has_geofence
from .schemas import Geofence, Location, NeedState, RecommendRequest, Recommendation


logger = logging.getLogger("current.recommender")

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


EN_PATH = Path(__file__).parent / "data" / "places.en.json"


@lru_cache(maxsize=1)
def english_places() -> dict[str, dict]:
    """26 个人工地点的英文版（scripts/translate_places.py 生成，人可以再过一遍）。

    现场翻会多一次模型往返，而这些文案是产品的门面，值得先译好放在这儿，
    而不是每次请求重新掷一次骰子。译不到的字段就留中文——缺一句比错一句好。
    """
    if not EN_PATH.exists():
        return {}
    with EN_PATH.open(encoding="utf-8") as handle:
        return json.load(handle).get("places", {})


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


# 没力气的人走不了太远。估算距离和高德实测距离都按这一条过滤，
# 常量只此一份——两边各写一个数字，迟早会改岔。
ENERGY_DISTANCE_LIMIT_KM = 8


# 用户明说的「不想要」比他没说出口的偏好重，但还不到一票否决——
# 说「不想见人」的人，不该被拿掉全北京所有有人的地方。
AVOID_WEIGHT = 0.25

# 现场搜出来的地点要让人工核对过的一个身位。差距要小到「附近真的更合适」时
# 它仍然能赢，又要大到同分时不会把人写的那份内容挤掉。
CURATION_PREFERENCE = 0.06

# 「避开某个需求」到底该避开哪个维度，必须一条条写出来，不能拿 NEEDS 的 target 反推。
# 反推过一版：need「想手上有事做」的 target 是 {创作刺激, 可久待}，于是用户说「什么都不做」
# 会连「能坐很久」一起扣分——而那恰恰是一个累坏的人最需要的。
# 只列「不想要」讲得通的那几个，其余的说了也不扣分。
AVOID_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "people": ("co", "c"),   # 不想见人 → 避开生活气重、人挤人
    "loud": ("l", "c"),      # 不想吵 → 避开热闹、人挤人
    "sound": ("l",),
    "hands": ("cr",),        # 什么都不做 → 避开需要动手动脑的
    "new": ("e",),           # 不想看新东西
    "walk": ("w",),          # 不想一直走
    "green": ("g",),
}


def _avoid_penalty(place: dict, state: NeedState) -> float:
    """把「我不想要什么」真的算进分数里。

    模型一直在从原话里抽这个字段（「不想见人」→ avoid_tags 里有 people），
    但在这之前没有任何地方读它——用户说了等于没说，这正是「推荐和我说的对不上」的来源。
    """
    tags = place.get("tags", {})
    worst = 0.0
    for key in state.avoid_tags:
        for dimension in AVOID_DIMENSIONS.get(key, ()):
            if dimension not in tags:
                continue
            # 0.5 是中性。只惩罚明显就是用户想避开的那一面的地方，
            # 中性和更弱的一律不扣——否则等于给所有地点齐刷刷减一个数，白扣。
            worst = max(worst, max(0.0, tags[dimension] - 0.5) * 2)
    return -AVOID_WEIGHT * worst


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
    if state.energy <= 1 and place.get("distanceKm", 0) > ENERGY_DISTANCE_LIMIT_KM:
        return False
    # 估算出来的「大概率关着门」不能当硬约束——估算会错，用户会被无声地少给选项。
    # 只有核对过的营业时间才允许直接把地点拿掉。
    status, _, source = open_state(place, now)
    if source == "verified" and status == "closed":
        return False
    # 路程上限是用户自己说的（「太远了，就近」），必须真的生效。
    # 这里用的是原型估算——估算会错，但把用户明说的条件当没听见更错。
    # 接上高德之后 recommend_with_live_context 会再用实测时间过一遍。
    if state.max_travel_minutes is not None and _estimate_reach_minutes(place) > state.max_travel_minutes:
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


def _reason_chain(place: dict, state: NeedState, catalog: dict, lang: str = "zh") -> list[str]:
    """两行：你说了什么 → 这里是什么。每一行都指向真实存下来的字段（FR-20）。

    原来是三行：「你说：X」「所以要找：Y」「这里命中：Z」。中间那行是模板生成的套话
    （need_keys 空的时候尤其明显，只会说「一个人待着不奇怪的地方」），
    读起来像填充物，反而把「我说的」和「你给的」之间那根线冲淡了。
    现在把用户明说的「想要」和「不想要」并到第一行，让这根线自己看得见。
    """
    from .interpretation import AVOID_LABELS, NEED_LABELS, STATE_LABELS

    english = lang == "en"
    need_table = NEED_LABELS_EN if english else NEED_LABELS
    avoid_table = AVOID_LABELS_EN if english else AVOID_LABELS
    state_table = STATE_LABELS_EN if english else STATE_LABELS
    joiner = ", " if english else "、"

    # 一行最多三样，不然它自己就变成了同事说的那种「可以不要的小字」。
    # 「不想要」是用户自己说出口的，比任何推断都硬，所以它占掉那三样里的一个。
    avoided = [avoid_table[key] for key in state.avoid_tags if key in avoid_table][:1]
    wanted = [need_table[key] for key in state.need_keys if key in need_table]
    said = [state_table.get(state.mood_id, "hard to name" if english else "说不太清楚")] + wanted[: 2 - len(avoided)] + avoided
    # 中文用全角冒号，英文用半角——排版上这是两回事，混用会一眼看出不对。
    lead = f'{ui("chain_said", "en")}: ' if english else "你说："
    chain = [lead + joiner.join(said)]

    target, _ = _target_for(state, catalog)
    tags = place.get("tags", {})
    hits = sorted(
        (key for key, wanted in target.items() if key in tags and abs(wanted - tags[key]) <= 0.25),
        key=lambda key: -abs(target[key] - 0.5),
    )
    if english:
        labels = [
            TAG_LABELS_EN[key] if target[key] >= 0.5 else LOW_TAG_LABELS_EN.get(key, key)
            for key in hits
            if key in TAG_LABELS_EN
        ][:3]
        chain.append(f'{ui("chain_here", "en")}: ' + joiner.join(labels) if labels else ui("chain_unsure", "en") or "")
        return chain
    labels = [
        catalog["TAGS"][key] if target[key] >= 0.5 else LOW_TAG_LABELS.get(key, "不" + catalog["TAGS"][key])
        for key in hits
        if key in catalog["TAGS"]
    ][:3]
    chain.append("这里：" + "、".join(labels) if labels else "这里只是大致接近，我不太确定")
    return chain


TRADEOFF_EN = {
    "人会比较多": "it gets crowded",
    "声音偏大": "it's on the loud side",
    "消费压力偏高": "not cheap",
    "要花点钱": "costs a bit",
    "不太适合久待": "not a place to linger",
    "不用花钱": "free",
    "人不多": "not crowded",
    "不吵": "quiet",
    "一个人去不奇怪": "going alone is normal here",
}


def _tradeoffs(place: dict, lang: str = "zh") -> list[str]:
    """代价照实写. Derived from the reviewed place record, never invented."""
    tags = place.get("tags", {})
    costs: list[str] = []
    if place.get("crowd") == "high":
        costs.append("人会比较多")
    if tags.get("l", 0) >= 0.7:
        costs.append("声音偏大")
    if not place.get("free"):
        costs.append("消费压力偏高" if tags.get("cp", 0) >= 0.6 else "要花点钱")
    # 路程不写进代价：「到达」那一行已经把它说清楚了，重复一遍会让代价栏
    # 看起来只有这一条，反而显得这地方没有别的代价。
    if tags.get("st", 1) <= 0.35:
        costs.append("不太适合久待")
    if costs:
        picked = costs[:3]
        return [TRADEOFF_EN.get(c, c) for c in picked] if lang == "en" else picked

    # 真的没有代价也是一条信息，但要说清楚「凭什么没有」，
    # 否则「暂时没看到」读起来像系统没算出来。
    upsides = []
    if place.get("free"):
        upsides.append("不用花钱")
    if place.get("crowd") == "low":
        upsides.append("人不多")
    if tags.get("l", 1) < 0.4:
        upsides.append("不吵")
    if tags.get("s", 0) >= 0.7:
        upsides.append("一个人去不奇怪")
    if lang == "en":
        english = [TRADEOFF_EN.get(u, u) for u in upsides[:3]]
        return [ui("tradeoff_lead", "en") + ", ".join(english)] if english else [ui("no_tradeoff", "en") or ""]
    return ["没什么要你付出的：" + "、".join(upsides[:3])] if upsides else ["没看出明显的代价"]


def _rank(
    request: RecommendRequest,
    now: datetime | None = None,
    discovered: list[dict] | None = None,
) -> list[tuple[float, dict, dict[str, float]]]:
    catalog = load_catalog()
    rejected = set(request.rejected_place_ids)
    hurried = _is_hurried(request.state)
    ranked: list[tuple[float, dict, dict[str, float]]] = []

    # 人工核对过的和现场搜出来的走同一套打分——差别在数据可信度，不在算法。
    for place in list(catalog["PLACES"]) + list(discovered or []):
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
        if place.get("source") == "discovered":
            # 同分时让人工核对过的先出场：它有真人写的理由、核对过的身份、
            # 和能进汇总的到访。现场结果是用来补空缺的，不是用来顶替的。
            score -= CURATION_PREFERENCE
            breakdown = {**breakdown, "discovered": 1.0}
        avoid_penalty = _avoid_penalty(place, request.state)
        if avoid_penalty:
            score += avoid_penalty
            breakdown = {**breakdown, "avoid_penalty": round(avoid_penalty, 4)}
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
    lang: str = "zh",
) -> Recommendation:
    reasons = place.get("matchReason", {})
    name = place["placeName"]
    action = place["action"]
    category = place.get("category")
    see, cost = place.get("see"), place.get("cost")
    transport, duration = place.get("transport"), place.get("suggestedDuration")
    # 现场搜出来的地点由模型当场按语言写，已经是对的语言了；
    # 这里只覆盖人工那 26 个。
    if lang == "en" and place.get("source") == "discovered":
        # 名字保留中文——评委要照着招牌找过去，翻成英文反而找不到。
        category = place.get("category_en") or category
    if lang == "en" and place.get("source") != "discovered":
        english = english_places().get(place["placeId"]) or {}
        if english:
            reasons = english.get("matchReason") or reasons
            name = english.get("placeName") or name
            action = english.get("action") or action
            category = english.get("category") or category
            see, cost = english.get("see") or see, english.get("cost") or cost
            transport = english.get("transport") or transport
            duration = english.get("suggestedDuration") or duration
    reason = reasons.get(state.mood_id) or reasons.get("_") or (
        "It's close to what you just described." if lang == "en" else "它和你刚才说的需要比较接近。")
    distance_km = round(route.distance_meters / 1000, 2) if route else place.get("distanceKm")
    walking_minutes = max(1, round(route.duration_seconds / 60)) if route else None
    reach_minutes = walking_minutes or _estimate_reach_minutes(place)
    tier, relief_label = _relief_tier(reach_minutes)
    if lang == "en":
        relief_label = RELIEF_LABELS_EN.get(tier, relief_label)
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
        place_name=name,
        action=action,
        reason=reason,
        score=round(max(0.0, min(1.0, score)), 4),
        distance_km=distance_km,
        walking_minutes=walking_minutes,
        travel_mode=route.mode if route else "walk",
        distance_source=(
            "amap" if route
            # 现场搜到的地点，距离是高德周边搜索一起返回的，是真的直线距离。
            else "amap_straight_line" if place.get("source") == "discovered" and distance_km is not None
            else "prototype_estimate"
        ),
        map_verified=(place.get("amap") or {}).get("verification_status") == "verified",
        source=place.get("source") or "curated",
        photos=[url for url in (place.get("photos") or []) if isinstance(url, str)][:3],
        category=category,
        area=place.get("area"),
        latitude=float(amap["latitude"]) if amap.get("latitude") is not None else None,
        longitude=float(amap["longitude"]) if amap.get("longitude") is not None else None,
        navigation_url=navigation_url(place),
        transport=transport,
        suggested_duration=duration,
        cost=cost,
        see=see,
        tradeoffs=_tradeoffs(place, lang),
        score_breakdown=breakdown,
        role=role,  # type: ignore[arg-type]
        reach_minutes=reach_minutes,
        time_to_relief=tier,  # type: ignore[arg-type]
        relief_label=relief_label,
        reason_chain=_reason_chain(place, state, load_catalog(), lang),
        # Current has no verified visit feedback yet, so nothing may be
        # presented as an average (FR-10b). The prototype numbers stay out.
        sample_size=0,
        low_support=True,
        open_state=status,  # type: ignore[arg-type]
        open_label=open_label,
        hours_source=hours_source,  # type: ignore[arg-type]
        geofence=fence,
        map_links=map_links(place),
    )


def recommend(request: RecommendRequest, now: datetime | None = None) -> list[Recommendation]:
    output: list[Recommendation] = []
    for index, (score, place, breakdown) in enumerate(_rank(request, now)[: request.limit]):
        role = "primary" if index == 0 else "alternate"
        output.append(_to_recommendation(score, place, breakdown, request.state, role=role, now=now, lang=request.lang))
    return output


def _spread(ranked: list[tuple], limit: int) -> list[tuple]:
    """同一类最多出现两个。

    「一个主推荐 + 两个备选」的意义是给出不同的出路；三个都是咖啡馆，
    等于把选择权收回去了。先按分数挑，类别满了的先跳过，
    最后不够数再把跳过的按分数补回来——宁可重复，也不能少给。
    """
    picked: list[tuple] = []
    skipped: list[tuple] = []
    seen: dict[str, int] = {}
    for item in ranked:
        category = str(item[1].get("category") or "")
        if seen.get(category, 0) >= 2:
            skipped.append(item)
            continue
        seen[category] = seen.get(category, 0) + 1
        picked.append(item)
        if len(picked) >= limit:
            return picked
    return (picked + skipped)[:limit]


async def warm_discovery(location: Location | None) -> None:
    """在 /interpret 那几秒里先把周边搜好，填进缓存。失败了当没发生过。"""
    if location is None:
        return
    client = AmapClient()
    if not client.configured:
        return
    try:
        await warm_search(client, location)
    except Exception:  # noqa: BLE001 - 预热是纯赚，不能反过来弄坏任何东西
        logger.debug("discovery warm-up failed", exc_info=True)


async def recommend_with_live_context(
    request: RecommendRequest,
    *,
    map_client: AmapClient | None = None,
    now: datetime | None = None,
) -> list[Recommendation]:
    client = map_client or AmapClient()
    # 现场从地图上搜候选。搜不到就退回人工那 26 个——少给选项，但绝不编。
    discovered = await discover(client, request.location, request.state) if request.location else []
    ranked = _rank(request, now, discovered=discovered)
    if not request.location or not client.configured:
        return [
            _to_recommendation(score, place, breakdown, request.state, role="primary" if index == 0 else "alternate", now=now, lang=request.lang)
            for index, (score, place, breakdown) in enumerate(ranked[: request.limit])
        ]

    # Route only a bounded shortlist. A reviewed provider ID/coordinate is mandatory;
    # search results are never silently promoted to production data.
    shortlist = ranked[: request.limit + 2]
    semaphore = asyncio.Semaphore(4)

    # 公交要城市编码。现场搜索的结果里本来就带着，捡一个用就行。
    citycode = next((str(place.get("citycode")) for place in discovered if place.get("citycode")), None)

    async def route_for(place: dict) -> WalkingRoute | None:
        amap = place.get("amap") or {}
        # 人工核对过的，和高德自己的 POI 记录，两种坐标都可以拿来算路线。
        if amap.get("verification_status") not in TRUSTWORTHY_COORDINATES:
            return None
        # 先按直线距离决定「该怎么过去」。只问步行会给出「步行 160 分钟」，
        # 那不是算错了，是问错了问题——没人会照着走。
        mode = AmapClient.mode_for(place.get("distanceKm"))
        try:
            async with semaphore:
                return await client.route(
                    origin_longitude=request.location.longitude,
                    origin_latitude=request.location.latitude,
                    destination_longitude=float(amap["longitude"]),
                    destination_latitude=float(amap["latitude"]),
                    destination_id=amap.get("provider_place_id"),
                    mode=mode,
                    citycode=citycode,
                )
        except (KeyError, TypeError, ValueError, MapProviderError):
            return None

    # 文案和路线一起发，不排队——多花的是并发，不是用户的时间。
    # 只给现场搜出来的写：人工那 26 个已经有真人写的理由链了，模型不该去改它。
    to_narrate = [place for _, place, _ in shortlist[: request.limit * 2] if place.get("source") == "discovered"]
    routes, written = await asyncio.gather(
        asyncio.gather(*(route_for(place) for _, place, _ in shortlist)),
        narrate_quietly(to_narrate, request.state, lang=request.lang),
    )
    for place in to_narrate:
        line = written.get(place["placeId"])
        if line:
            # 模板那句是保底；模型这句是这个产品的意义所在。
            place["action"] = line["action"]
            place["matchReason"] = {"_": line["why_now"]}
            place["narrated"] = True
    enriched: list[tuple[float, dict, dict[str, float], WalkingRoute | None]] = []
    # 只因为「实测太远」被拿掉的。全军覆没时还得把它们请回来——
    # 给一个远的并说清楚它远，好过给空屏（US-03）。
    too_far: list[tuple[float, dict, dict[str, float], WalkingRoute | None]] = []
    for (score, place, breakdown), route in zip(shortlist, routes, strict=True):
        if route:
            walking_minutes = max(1, round(route.duration_seconds / 60))
            distance_km = route.distance_meters / 1000
            if request.state.max_travel_minutes and walking_minutes > request.state.max_travel_minutes:
                continue
            travel_fit = max(0.0, 1 - walking_minutes / 90)
            score = score - breakdown["travel_fit"] * 0.15 + travel_fit * 0.15
            breakdown = {**breakdown, "travel_fit": round(travel_fit, 4)}

            # places.json 里的 distanceKm 是原型里的固定常数，跟用户从哪儿出发无关。
            # 所以实测一回来，凡是拿估算算出来的结论都必须重算，而不是只调 travel_fit：
            # 否则一个实际要走 108 分钟的地方，会带着估算给的「现在就能到」加分当主推荐。
            if "relief_bonus" in breakdown:
                tier, _ = _relief_tier(walking_minutes)
                score = score - breakdown["relief_bonus"] + RELIEF_BONUS[tier]
                breakdown = {**breakdown, "relief_bonus": RELIEF_BONUS[tier]}

            # _hard_filter 里的同一条上限，用实测距离再过一遍。
            if request.state.energy <= 1 and distance_km > ENERGY_DISTANCE_LIMIT_KM:
                too_far.append((score, place, breakdown, route))
                continue
        enriched.append((score, place, breakdown, route))

    if not enriched:
        enriched = too_far

    enriched.sort(key=lambda item: item[0], reverse=True)
    return [
        _to_recommendation(score, place, breakdown, request.state, route, role="primary" if index == 0 else "alternate", now=now, lang=request.lang)
        for index, (score, place, breakdown, route) in enumerate(_spread(enriched, request.limit))
    ]
