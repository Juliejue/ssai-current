"""营业状态（FR-07）。

我们没有任何一家店的一手营业时间。所以这里存的**不是**每个地点的事实，
而是「这一类场所通常几点开门」——类目层面的常识，标注为估算。

§9.1 明写「不能编造营业状态」：所以估算永远只降权、只提示，绝不冒充确定。
只有人工核对过、写进 place_overrides.json 且 verification_status=verified 的
营业时间，才会作为硬约束把地点直接过滤掉——和地图身份走同一套审核纪律。
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo


# 26 个地点都在北京，所以判断「现在开着吗」用北京时间，而不是用户设备所在时区。
BEIJING = ZoneInfo("Asia/Shanghai")

OpenState = Literal["always_open", "open", "likely_closed", "closed", "unknown"]

ALWAYS_OPEN = "always_open"

# 类目 → (开, 关)。关门时间小于开门时间表示跨过午夜。
CATEGORY_HOURS: dict[str, tuple[str, str] | None] = {
    "唱片店": ("12:00", "20:00"),
    "书店": ("10:00", "22:00"),
    "咖啡": ("09:00", "21:00"),
    "精酿": ("17:00", "02:00"),
    "酒吧": ("17:00", "02:00"),
    "livehouse": ("20:00", "03:00"),
    "club": ("21:00", "04:00"),
    "影院": ("09:00", "23:00"),
    "吃": ("11:00", "22:00"),
    "公园": ("06:00", "21:00"),
    "园区": ("08:00", "22:00"),
    # 开放街道与河岸没有门，也就没有营业时间。
    "河岸": None,
    "水边": None,
    "胡同": None,
    "市集": ("10:00", "20:00"),
    "买手店": ("11:00", "21:00"),
}


def _parse(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _category_keys(place: dict) -> list[str]:
    return [part.strip() for part in str(place.get("category", "")).split("·")]


def _category_window(place: dict) -> tuple[tuple[str, str] | None, bool]:
    """返回 (营业窗口, 是否命中类目)。窗口为 None 表示这一类没有门。"""
    for key in _category_keys(place):
        if key in CATEGORY_HOURS:
            return CATEGORY_HOURS[key], True
    return None, False


def resolve_hours(place: dict) -> dict:
    """人工核对过的营业时间优先；否则退回类目估算；都没有就是 unknown。"""
    verified = place.get("hours") or {}
    if verified.get("verification_status") == "verified":
        return {
            "open": verified.get("open"),
            "close": verified.get("close"),
            "closed_days": verified.get("closed_days") or [],
            "source": "verified",
        }
    window, matched = _category_window(place)
    if not matched:
        return {"open": None, "close": None, "closed_days": [], "source": "unknown"}
    if window is None:
        return {"open": None, "close": None, "closed_days": [], "source": "always_open"}
    return {"open": window[0], "close": window[1], "closed_days": [], "source": "category_estimate"}


def _within(now: datetime, opens: time, closes: time) -> bool:
    current = now.time()
    if opens <= closes:
        return opens <= current < closes
    # 跨午夜：22:00–02:00 这种
    return current >= opens or current < closes


def open_state(place: dict, now: datetime | None = None) -> tuple[OpenState, str, str]:
    """返回 (状态, 给用户看的一句话, 数据来源)。"""
    now = now or datetime.now(BEIJING)
    hours = resolve_hours(place)
    source = hours["source"]

    if source == "always_open":
        return ALWAYS_OPEN, "没有门，什么时候都能去", source
    if source == "unknown":
        return "unknown", "营业时间不确定，去之前最好查一下", source

    if now.weekday() in (hours["closed_days"] or []):
        return "closed", "今天闭馆", source

    opens, closes = _parse(hours["open"]), _parse(hours["close"])
    inside = _within(now, opens, closes)

    if source == "verified":
        return ("open", f"现在开着 · {hours['close']} 关门", source) if inside else ("closed", f"现在没开 · {hours['open']} 才开门", source)

    # 估算：说清楚这是「一般来说」，不冒充确定
    if inside:
        return "open", f"这一类一般开到 {hours['close']}（未经核对）", source
    return "likely_closed", f"这个点大概率关着门（这一类一般 {hours['open']}–{hours['close']}，未经核对）", source
