from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from .coords import gcj_to_wgs

import httpx


AMAP_BASE_URL = "https://restapi.amap.com"

# 只对传输层错误重试，不对「高德说你参数错了」重试。
CONNECT_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 0.4


class MapProviderError(RuntimeError):
    """A map provider failure that is safe to expose as an availability issue."""


@dataclass(frozen=True)
class WalkingRoute:
    distance_meters: int
    duration_seconds: int


def parse_location(value: str) -> tuple[float, float]:
    try:
        longitude_text, latitude_text = value.split(",", 1)
        longitude, latitude = float(longitude_text), float(latitude_text)
    except (AttributeError, TypeError, ValueError) as error:
        raise MapProviderError("地图服务返回了无效坐标") from error
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise MapProviderError("地图服务返回了越界坐标")
    return longitude, latitude


class AmapClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("AMAP_WEB_SERVICE_KEY", "")
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _get(self, path: str, params: dict[str, str | int]) -> dict[str, Any]:
        if not self.api_key:
            raise MapProviderError("AMAP_WEB_SERVICE_KEY is not configured")
        request_params = {**params, "key": self.api_key}
        # restapi.amap.com 会间歇性重置连接（实测约一半的首次握手失败，重试就好）。
        # 不重试的话，一半的路线会静默退回原型估算——用户看到「未接地图」，
        # 会以为 Key 没配好，其实只是没重连。传输错误重试，业务错误不重试。
        last_error: Exception | None = None
        payload: dict[str, Any] | None = None
        for attempt in range(CONNECT_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    base_url=AMAP_BASE_URL,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.get(path, params=request_params)
                    response.raise_for_status()
                    payload = response.json()
                break
            except httpx.TransportError as error:
                # TransportError 覆盖连不上、连接超时、读超时、协议错——
                # GET 是幂等的，这几种全都可以安全重试。业务错误走下面那条，不重试。
                last_error = error
                if attempt + 1 < CONNECT_ATTEMPTS:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            except (httpx.HTTPError, ValueError) as error:
                raise MapProviderError("地图服务暂时不可用") from error
        if payload is None:
            raise MapProviderError("地图服务暂时不可用") from last_error
        if str(payload.get("status")) != "1" or str(payload.get("infocode")) != "10000":
            raise MapProviderError(str(payload.get("info") or "地图服务请求失败"))
        return payload

    async def search_places(
        self,
        keywords: str,
        *,
        region: str = "北京市",
        page_size: int = 5,
    ) -> list[dict[str, Any]]:
        payload = await self._get(
            "/v5/place/text",
            {
                "keywords": keywords,
                "region": region,
                "city_limit": "true",
                "show_fields": "business,navi",
                "page_size": max(1, min(page_size, 10)),
            },
        )
        candidates: list[dict[str, Any]] = []
        for poi in payload.get("pois") or []:
            try:
                longitude, latitude = parse_location(poi.get("location", ""))
            except MapProviderError:
                continue
            business = poi.get("business") if isinstance(poi.get("business"), dict) else {}
            candidates.append(
                {
                    "provider_place_id": str(poi.get("id") or ""),
                    "name": str(poi.get("name") or ""),
                    "longitude": longitude,
                    "latitude": latitude,
                    "address": str(poi.get("address") or ""),
                    "district": str(poi.get("adname") or ""),
                    "type": str(poi.get("type") or ""),
                    "typecode": str(poi.get("typecode") or ""),
                    "rating": business.get("rating"),
                    "business_area": business.get("business_area"),
                    "open_time_today": business.get("opentime_today"),
                }
            )
        return candidates

    async def search_around(
        self,
        *,
        longitude: float,
        latitude: float,
        types: str = "",
        keywords: str = "",
        radius: int = 5000,
        page_size: int = 25,
    ) -> list[dict[str, Any]]:
        """周边搜索：候选地点从地图来，而不是从我们写死的清单来。

        `show_fields` 里的 photos 是 #2「把实景放上来」的全部来源——
        高德给每个 POI 返回若干张真实照片，页面直接用。
        """
        payload = await self._get(
            "/v5/place/around",
            {
                "location": f"{longitude},{latitude}",
                **({"types": types} if types else {}),
                **({"keywords": keywords} if keywords else {}),
                "radius": max(500, min(radius, 50000)),
                "show_fields": "business,photos,navi",
                "page_size": max(1, min(page_size, 25)),
                "sortrule": "distance",
            },
        )
        results: list[dict[str, Any]] = []
        for poi in payload.get("pois") or []:
            try:
                poi_longitude, poi_latitude = parse_location(poi.get("location", ""))
            except MapProviderError:
                continue
            results.append({**poi, "longitude": poi_longitude, "latitude": poi_latitude})
        return results

    async def walking_route(
        self,
        *,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
        destination_id: str | None = None,
    ) -> WalkingRoute:
        params: dict[str, str | int] = {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{destination_longitude},{destination_latitude}",
            "show_fields": "cost",
        }
        if destination_id:
            params["destination_id"] = destination_id
        payload = await self._get("/v5/direction/walking", params)
        paths = (payload.get("route") or {}).get("paths") or []
        if not paths:
            raise MapProviderError("没有可用的步行路线")
        path = paths[0]
        try:
            return WalkingRoute(
                distance_meters=int(float(path["distance"])),
                duration_seconds=int(float(path["cost"]["duration"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise MapProviderError("地图服务返回了无效路线") from error


# 坐标可信 ≠ 身份是我们认定的。
# "verified"        我们把一个名字人工核对到了某个 POI 上
# "provider_exact"  这条记录整个就是高德的 POI，名字和坐标本来就是一对
# 导航要的是前一种保证（不会把人送到同名的另一家），两者都满足。
# 围栏在场证明要的是后一种以外的东西（防作弊、进汇总），只认 "verified"。
TRUSTWORTHY_COORDINATES = ("verified", "provider_exact")


STATIC_MAP_URL = "https://restapi.amap.com/v3/staticmap"


async def static_map_png(longitude: float, latitude: float, width: int, height: int) -> bytes:
    """一张以这个地点为中心的地图图片。

    必须走服务端：静态地图接口把 key 放在 URL 里，直接让浏览器去请求
    等于把 key 贴在页面上。这里只接受地点坐标——地点坐标是公开信息，
    用户自己的坐标一次都不上传（守则 6）。
    """
    key = os.getenv("AMAP_WEB_SERVICE_KEY") or ""
    if not key:
        raise MapProviderError("没有配置高德 Key")
    params = {
        "key": key,
        "location": f"{longitude:.6f},{latitude:.6f}",
        "zoom": 15,
        "size": f"{width}*{height}",
        "scale": 2,
        "markers": f"mid,0xC4703C,:{longitude:.6f},{latitude:.6f}",
    }
    last: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(STATIC_MAP_URL, params=params)
            if response.status_code != 200 or "image" not in (response.headers.get("content-type") or ""):
                raise MapProviderError("静态地图返回的不是图片")
            return response.content
        except httpx.HTTPError as error:  # 跨境抖动，重试（见交接文档 §3①）
            last = error
            await asyncio.sleep(0.4 * attempt)
    raise MapProviderError(str(last or "静态地图请求失败"))


def navigation_url(place: dict[str, Any]) -> str | None:
    amap = place.get("amap") or {}
    if amap.get("verification_status") not in TRUSTWORTHY_COORDINATES:
        return None
    try:
        longitude = float(amap["longitude"])
        latitude = float(amap["latitude"])
    except (KeyError, TypeError, ValueError):
        return None
    query = urlencode(
        {
            "to": f"{longitude},{latitude},{amap.get('verified_name') or place['placeName']}",
            "mode": "walk",
            "policy": 1,
            "src": "current",
            "coordinate": "gaode",
            "callnative": 1,
        }
    )
    return f"https://uri.amap.com/navigation?{query}"


def map_links(place: dict[str, Any]) -> dict[str, str]:
    """US-06：给用户选地图，而不是替他决定用哪家。

    我们存的坐标来自高德，是 GCJ-02。Apple 和 Google 用 WGS-84，
    不转换会偏 500 米以上——跳过去就是隔壁街区。
    和导航、围栏同一道门：没有人工核对过的坐标就一条链接都不给。
    """
    amap = place.get("amap") or {}
    if amap.get("verification_status") not in TRUSTWORTHY_COORDINATES:
        return {}
    try:
        gcj_longitude = float(amap["longitude"])
        gcj_latitude = float(amap["latitude"])
    except (KeyError, TypeError, ValueError):
        return {}

    name = amap.get("verified_name") or place["placeName"]
    wgs_latitude, wgs_longitude = (round(v, 6) for v in gcj_to_wgs(gcj_latitude, gcj_longitude))

    amap_query = urlencode(
        {
            "to": f"{gcj_longitude},{gcj_latitude},{name}",
            "mode": "walk",
            "policy": 1,
            "src": "current",
            "coordinate": "gaode",
            "callnative": 1,
        }
    )
    apple_query = urlencode({"daddr": f"{wgs_latitude},{wgs_longitude}", "q": name, "dirflg": "w"})
    google_query = urlencode(
        {
            "api": 1,
            "destination": f"{wgs_latitude},{wgs_longitude}",
            "travelmode": "walking",
        }
    )
    return {
        "amap": f"https://uri.amap.com/navigation?{amap_query}",
        "apple": f"https://maps.apple.com/?{apple_query}",
        "google": f"https://www.google.com/maps/dir/?{google_query}",
    }
