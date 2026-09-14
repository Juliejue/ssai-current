import asyncio

import httpx
import pytest

from backend_app.map_provider import AmapClient, MapProviderError, navigation_url, parse_location


def test_search_places_returns_reviewable_candidates_without_promoting_them():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/place/text"
        assert request.url.params["key"] == "server-secret"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "infocode": "10000",
                "pois": [
                    {
                        "id": "B000TEST",
                        "name": "测试书店",
                        "location": "116.40,39.90",
                        "address": "一条需要人工核对的地址",
                        "adname": "东城区",
                        "type": "购物服务;专卖店;书店",
                        "typecode": "060101",
                        "business": {"rating": "4.7"},
                    }
                ],
            },
        )

    client = AmapClient(api_key="server-secret", transport=httpx.MockTransport(handler))
    candidates = asyncio.run(client.search_places("测试书店"))
    assert candidates[0]["provider_place_id"] == "B000TEST"
    assert candidates[0]["longitude"] == 116.4
    assert "verification_status" not in candidates[0]


def test_walking_route_parses_distance_and_duration():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/direction/walking"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "infocode": "10000",
                "route": {"paths": [{"distance": "1234", "cost": {"duration": "900"}}]},
            },
        )

    client = AmapClient(api_key="server-secret", transport=httpx.MockTransport(handler))
    route = asyncio.run(
        client.walking_route(
            origin_longitude=116.3,
            origin_latitude=39.9,
            destination_longitude=116.4,
            destination_latitude=39.91,
        )
    )
    assert route.distance_meters == 1234
    assert route.duration_seconds == 900


def test_provider_error_and_coordinate_validation():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "0", "infocode": "10001", "info": "INVALID_USER_KEY"})

    client = AmapClient(api_key="bad", transport=httpx.MockTransport(handler))
    with pytest.raises(MapProviderError, match="INVALID_USER_KEY"):
        asyncio.run(client.search_places("书店"))
    with pytest.raises(MapProviderError):
        parse_location("999,39")


def test_navigation_requires_human_verified_identity():
    place = {
        "placeName": "测试书店",
        "amap": {"longitude": 116.4, "latitude": 39.9, "verification_status": "unverified"},
    }
    assert navigation_url(place) is None
    place["amap"]["verification_status"] = "verified"
    assert navigation_url(place).startswith("https://uri.amap.com/navigation?")
