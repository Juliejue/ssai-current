import asyncio

from backend_app import recommender
from backend_app.map_provider import WalkingRoute
from backend_app.recommender import load_catalog, recommend
from backend_app.schemas import Location, NeedState, RecommendRequest


def test_catalog_contains_all_prototype_places():
    assert len(load_catalog()["PLACES"]) == 26


def test_free_request_only_returns_free_places():
    request = RecommendRequest(state=NeedState(mood_id="low", need_keys=["free"], budget_level="free"))
    results = recommend(request)
    catalog = {place["placeId"]: place for place in load_catalog()["PLACES"]}
    assert results
    assert all(catalog[item.place_id]["free"] for item in results)


def test_rejected_place_is_not_returned():
    baseline = recommend(RecommendRequest(state=NeedState(mood_id="quiet")))
    rejected = baseline[0].place_id
    after = recommend(RecommendRequest(state=NeedState(mood_id="quiet"), rejected_place_ids=[rejected]))
    assert rejected not in {item.place_id for item in after}


def test_live_route_replaces_estimate_and_respects_max_travel(monkeypatch):
    place = dict(load_catalog()["PLACES"][0])
    place["amap"] = {
        "provider_place_id": "B000TEST",
        "longitude": 116.4,
        "latitude": 39.9,
        "verified_name": place["placeName"],
        "verification_status": "verified",
    }
    monkeypatch.setattr(recommender, "_rank", lambda _: [(0.8, place, {"travel_fit": 0.5})])

    class FakeMapClient:
        configured = True

        async def walking_route(self, **_):
            return WalkingRoute(distance_meters=1600, duration_seconds=1200)

    request = RecommendRequest(
        state=NeedState(mood_id="quiet", max_travel_minutes=25),
        location=Location(latitude=39.8, longitude=116.3),
    )
    results = asyncio.run(recommender.recommend_with_live_context(request, map_client=FakeMapClient()))
    assert results[0].distance_source == "amap"
    assert results[0].walking_minutes == 20
    assert results[0].map_verified is True

    request.state.max_travel_minutes = 10
    assert asyncio.run(recommender.recommend_with_live_context(request, map_client=FakeMapClient())) == []
