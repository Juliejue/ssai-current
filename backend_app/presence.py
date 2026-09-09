"""在场证明 L1（FR-08）。

L1 要「默认无感」（§14），所以核验只有两个信号：进没进围栏、待了多久。
两个都在浏览器里算完，只有结论上传——**用户的经纬度一次都不会离开设备**。

因此浏览器报上来的 presence_level 是不可信的：它可以随手写成最高等级。
服务端的职责就是这一条——降级。一个地点连人工核对过的坐标都没有，
它就没有围栏，任何「我用围栏证明我到了」的声明都会被降回自述。
这是 FR-08 里 L3 反作弊最小、也最该先有的一环。
"""

from __future__ import annotations

from typing import Literal


PresenceLevel = Literal["geofence_dwell", "dwell_only", "self_reported"]

# 停留多久才算「到过」。PRD 给的是 5–10 分钟，取下限，少劝退一点。
MIN_DWELL_MINUTES = 5

# 围栏半径。公园、河岸、胡同这种大范围空间，用店铺的半径会一直判定为「没到」。
LARGE_AREA_CATEGORIES = ("公园", "河岸", "水边", "胡同", "园区")
SMALL_RADIUS_M = 150
LARGE_RADIUS_M = 400


def geofence_radius_m(place: dict) -> int:
    categories = [part.strip() for part in str(place.get("category", "")).split("·")]
    return LARGE_RADIUS_M if any(c in LARGE_AREA_CATEGORIES for c in categories) else SMALL_RADIUS_M


def has_geofence(place: dict) -> bool:
    """只有人工核对过坐标的地点才有围栏——和导航、路线同一道门。"""
    amap = place.get("amap") or {}
    if amap.get("verification_status") != "verified":
        return False
    try:
        float(amap["longitude"])
        float(amap["latitude"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def verify(claimed: str, dwell_minutes: int, place: dict | None) -> tuple[PresenceLevel, str]:
    """把浏览器的声明降到证据支持得住的等级。只降不升。"""
    dwell_ok = dwell_minutes >= MIN_DWELL_MINUTES

    if claimed == "geofence_dwell" and place is not None and has_geofence(place) and dwell_ok:
        return "geofence_dwell", f"围栏内停留 {dwell_minutes} 分钟"
    if dwell_ok:
        reason = (
            "这个地点还没有人工核对过的坐标，没法用围栏核验"
            if claimed == "geofence_dwell"
            else f"自己确认到达，停留 {dwell_minutes} 分钟"
        )
        return "dwell_only", reason
    return "self_reported", f"停留不到 {MIN_DWELL_MINUTES} 分钟，只算自述"
