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
    monkeypatch.setattr(recommender, "_rank", lambda _request, _now=None, discovered=None: [(0.8, place, {"travel_fit": 0.5})])

    class FakeMapClient:
        configured = True

        async def search_around(self, **_):
            # 这些用例考的是「实测路线怎么改变排序」，不是现场搜索。
            # 返回空 = 候选集只有人工那 26 个，正是这些断言假设的前提。
            return []

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


def _verified(place_id: str) -> dict:
    """原型地点 + 一份人工核对过的高德身份，这样它才会被真的去算路线。"""
    place = dict(next(p for p in load_catalog()["PLACES"] if p["placeId"] == place_id))
    place["amap"] = {
        "provider_place_id": f"B000{place_id[:6].upper()}",
        "longitude": 116.4,
        "latitude": 39.9,
        "verified_name": place["placeName"],
        "verification_status": "verified",
    }
    return place


def test_measured_walk_cancels_the_estimated_relief_bonus(monkeypatch):
    """108 分钟的路不能带着估算给的「现在就能到」加分当主推荐。

    places.json 里的 distanceKm 是固定常数，跟用户从哪儿出发无关。线上真实复现过：
    估算说电影资料馆离国贸 1.0 公里（→「现在就能到」+0.12），高德实测 8.1 公里 / 108 分钟。
    """
    far = _verified("ziliaoguan")
    near = _verified("liangmahe")
    # 估算阶段：远的那个分数更高，正是因为它拿了「现在就能到」的加分。
    monkeypatch.setattr(
        recommender,
        "_rank",
        lambda _request, _now=None, discovered=None: [
            (0.80, far, {"travel_fit": 0.95, "relief_bonus": 0.12}),
            (0.74, near, {"travel_fit": 0.85, "relief_bonus": 0.12}),
        ],
    )

    routes = {far["placeId"]: WalkingRoute(distance_meters=8100, duration_seconds=6480),
              near["placeId"]: WalkingRoute(distance_meters=2990, duration_seconds=2400)}

    class FakeMapClient:
        configured = True

        async def search_around(self, **_):
            # 这些用例考的是「实测路线怎么改变排序」，不是现场搜索。
            # 返回空 = 候选集只有人工那 26 个，正是这些断言假设的前提。
            return []
        order = [far["placeId"], near["placeId"]]

        def __init__(self):
            self.calls = 0

        async def walking_route(self, **_):
            route = routes[self.order[self.calls]]
            self.calls += 1
            return route

    # energy=2：远的那个不被距离上限拿掉，但必须掉到主推荐之外。
    request = RecommendRequest(
        state=NeedState(mood_id="tight", energy=2),
        location=Location(latitude=39.9388, longitude=116.4527),
    )
    results = asyncio.run(recommender.recommend_with_live_context(request, map_client=FakeMapClient()))
    assert results[0].place_id == near["placeId"]
    assert results[0].walking_minutes == 40
    far_result = next(item for item in results if item.place_id == far["placeId"])
    assert far_result.walking_minutes == 108
    assert far_result.time_to_relief == "later"
    assert far_result.score_breakdown["relief_bonus"] == recommender.RELIEF_BONUS["later"]


def test_measured_distance_applies_the_same_limit_as_the_estimate(monkeypatch):
    """没力气的人走不了 8 公里——估算说 1 公里也一样。"""
    far = _verified("ziliaoguan")
    near = _verified("liangmahe")
    monkeypatch.setattr(
        recommender,
        "_rank",
        lambda _request, _now=None, discovered=None: [
            (0.80, far, {"travel_fit": 0.95, "relief_bonus": 0.12}),
            (0.74, near, {"travel_fit": 0.85, "relief_bonus": 0.12}),
        ],
    )
    routes = [WalkingRoute(distance_meters=8100, duration_seconds=6480),
              WalkingRoute(distance_meters=2990, duration_seconds=2400)]

    class FakeMapClient:
        configured = True

        async def search_around(self, **_):
            # 这些用例考的是「实测路线怎么改变排序」，不是现场搜索。
            # 返回空 = 候选集只有人工那 26 个，正是这些断言假设的前提。
            return []

        def __init__(self):
            self.calls = 0

        async def walking_route(self, **_):
            route = routes[self.calls]
            self.calls += 1
            return route

    request = RecommendRequest(
        state=NeedState(mood_id="tight", energy=1),
        location=Location(latitude=39.9388, longitude=116.4527),
    )
    results = asyncio.run(recommender.recommend_with_live_context(request, map_client=FakeMapClient()))
    assert far["placeId"] not in {item.place_id for item in results}
    assert results[0].place_id == near["placeId"]


def test_never_returns_empty_when_only_distance_disqualified_everything(monkeypatch):
    """全被距离筛掉时，宁可给远的并说清楚，也不能给空屏（US-03）。"""
    far = _verified("ziliaoguan")
    monkeypatch.setattr(
        recommender,
        "_rank",
        lambda _request, _now=None, discovered=None: [(0.80, far, {"travel_fit": 0.95, "relief_bonus": 0.12})],
    )

    class FakeMapClient:
        configured = True

        async def search_around(self, **_):
            # 这些用例考的是「实测路线怎么改变排序」，不是现场搜索。
            # 返回空 = 候选集只有人工那 26 个，正是这些断言假设的前提。
            return []

        async def walking_route(self, **_):
            return WalkingRoute(distance_meters=9000, duration_seconds=7200)

    request = RecommendRequest(
        state=NeedState(mood_id="tight", energy=1),
        location=Location(latitude=39.9388, longitude=116.4527),
    )
    results = asyncio.run(recommender.recommend_with_live_context(request, map_client=FakeMapClient()))
    assert len(results) == 1
    assert results[0].time_to_relief == "later"


def test_a_straight_line_distance_from_the_map_is_not_called_a_prototype_estimate(monkeypatch):
    """现场搜到的地点带着高德给的直线距离，不能标成「原型估算」。

    三种来源必须分得开：实测步行路线 / 高德直线距离 / 原型里写死的常数。
    把第二种说成第三种，是在自己抹黑自己的数据——而这个产品的立身之本
    就是「数据从哪来，说清楚」。
    """
    found = dict(_verified("liangmahe"))
    found["source"] = "discovered"
    found["distanceKm"] = 0.53
    # 不要把这个局部变量叫 discovered——会遮住 lambda 自己的同名参数。
    monkeypatch.setattr(
        recommender, "_rank",
        lambda _request, _now=None, discovered=None: [(0.8, found, {"travel_fit": 0.9})],
    )

    class NoRouteClient:
        configured = True

        async def search_around(self, **_):
            return []

        async def walking_route(self, **_):
            raise recommender.MapProviderError("跨境失败")

    request = RecommendRequest(
        state=NeedState(mood_id="tired"),
        location=Location(latitude=39.9432, longitude=116.4022),
    )
    results = asyncio.run(recommender.recommend_with_live_context(request, map_client=NoRouteClient()))
    assert results[0].distance_source == "amap_straight_line"
    assert results[0].distance_km == 0.53
