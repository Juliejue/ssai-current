"""坐标系转换（US-06）。

高德和腾讯用 GCJ-02（火星坐标），Apple 和 Google 用 WGS-84。
中国境内两者相差 500 米以上——跨端跳转不转换，用户会被送到隔壁街区。

浏览器那侧做的是 WGS-84 → GCJ-02（围栏判定），这里做的是反向：
我们存的是高德给的 GCJ-02，要跳 Apple/Google 就得转回 WGS-84。
"""

from __future__ import annotations

import math


A = 6378245.0                    # 克拉索夫斯基椭球长半轴
EE = 0.00669342162296594323      # 偏心率平方


def out_of_china(latitude: float, longitude: float) -> bool:
    return not (72.004 < longitude < 137.8347 and 0.8293 < latitude < 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    ret += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    ret += (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    ret += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    ret += (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    return ret


def _offset(latitude: float, longitude: float) -> tuple[float, float]:
    d_lat = _transform_lat(longitude - 105.0, latitude - 35.0)
    d_lon = _transform_lon(longitude - 105.0, latitude - 35.0)
    rad_lat = latitude / 180.0 * math.pi
    magic = 1 - EE * math.sin(rad_lat) ** 2
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return d_lat, d_lon


def wgs_to_gcj(latitude: float, longitude: float) -> tuple[float, float]:
    if out_of_china(latitude, longitude):
        return latitude, longitude
    d_lat, d_lon = _offset(latitude, longitude)
    return latitude + d_lat, longitude + d_lon


def gcj_to_wgs(latitude: float, longitude: float) -> tuple[float, float]:
    """反向没有闭式解。迭代逼近，几次就收敛到厘米级，远超导航需要的精度。"""
    if out_of_china(latitude, longitude):
        return latitude, longitude
    guess_lat, guess_lon = latitude, longitude
    for _ in range(6):
        forward_lat, forward_lon = wgs_to_gcj(guess_lat, guess_lon)
        guess_lat += latitude - forward_lat
        guess_lon += longitude - forward_lon
    return guess_lat, guess_lon
