from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


AMAP_BASE_URL = "https://restapi.amap.com"


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
        timeout_seconds: float = 4.0,
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
        try:
            async with httpx.AsyncClient(
                base_url=AMAP_BASE_URL,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=request_params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MapProviderError("地图服务暂时不可用") from error
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


def navigation_url(place: dict[str, Any]) -> str | None:
    amap = place.get("amap") or {}
    if amap.get("verification_status") != "verified":
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
