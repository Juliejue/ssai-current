"""The PRD's visible promises, asserted where they can regress silently."""

import re
from urllib.parse import quote

import pytest

from fastapi.testclient import TestClient

from backend_app.interpretation import interpret_with_rules, _decorate
from backend_app.main import app
from backend_app.recommender import recommend
from backend_app.schemas import NeedState, RecommendRequest


client = TestClient(app)


def _read(text: str):
    return _decorate(interpret_with_rules(text), text)


def test_restatement_quotes_the_user_and_never_uses_clinical_labels():
    read = _read("今天脑子很乱，不想见人，也不想花很多钱")
    assert read.state_label == "脑子停不下来"
    assert "很乱" in read.evidence[0]
    assert 1 <= len(read.evidence) <= 3
    banned = ("焦虑症", "抑郁", "高敏感", "你太", "你应该", "病")
    blob = read.acknowledgement + "".join(read.evidence)
    assert not any(word in blob for word in banned)


def test_at_most_one_follow_up_and_only_when_it_changes_the_shortlist():
    detailed = _read("今天脑子很乱，不想见人，也不想花很多钱")
    assert detailed.clarify_field is None
    assert detailed.state.needs_clarification is False

    vague = _read("难受")
    assert vague.clarify_field == "social_mode"
    assert vague.state.clarifying_question is not None
    assert 2 <= len(vague.clarify_options) <= 3


def test_urgent_language_is_never_asked_a_follow_up_question():
    read = _read("我不想活了")
    assert read.state.risk_level.value == "urgent"
    assert read.clarify_field is None
    assert read.state.clarifying_question is None


def test_correction_chips_are_body_words_and_exclude_the_current_guess():
    read = _read("今天脑子很乱")
    assert len(read.corrections.state) == 6
    assert all(chip.key != read.state.mood_id for chip in read.corrections.state)


def test_all_four_links_can_be_corrected_not_only_the_state():
    """FR-03：状态 / 需求 / 约束 / 地点。地点那一环是动作，不需要选项。"""
    read = _read("今天脑子很乱，不想见人，也不想花很多钱")
    assert read.corrections.state, "状态可改"
    assert read.corrections.need, "需求可改"
    assert read.corrections.constraint, "条件可改"
    assert all(len(getattr(read.corrections, link)) <= 6 for link in ("state", "need", "constraint"))


def test_corrections_do_not_offer_what_the_user_already_said():
    read = _read("今天脑子很乱，不想见人，也不想花很多钱")
    assert read.state.social_mode == "alone"
    assert "social_mode:alone" not in [c.key for c in read.corrections.constraint]
    assert "hide" not in [c.key for c in read.corrections.need]


def test_constraint_corrections_only_name_real_need_state_fields():
    read = _read("难受")
    allowed = set(NeedState.model_fields)
    for chip in read.corrections.constraint:
        field, _, raw = chip.key.partition(":")
        assert field in allowed, f"{field} 不是 NeedState 上的字段"
        assert raw


def test_first_result_is_the_primary_and_the_rest_are_alternates():
    results = recommend(RecommendRequest(state=NeedState(mood_id="noisy", need_keys=["hide"]), limit=3))
    assert len(results) == 3
    assert [item.role for item in results] == ["primary", "alternate", "alternate"]


def test_reason_chain_is_what_you_said_then_what_this_place_is():
    """两行，不是三行。

    中间那行「所以要找：…」是模板套话——need_keys 为空时只会说
    「一个人待着不奇怪的地方」——读起来像填充物，删掉。
    """
    results = recommend(RecommendRequest(state=NeedState(mood_id="tight", need_keys=["slow"]), limit=1))
    chain = results[0].reason_chain
    assert len(chain) == 2
    assert chain[0].startswith("你说：")
    assert chain[1].startswith("这里：") or "不太确定" in chain[1]
    assert not any(line.startswith("所以要找：") for line in chain)


def test_what_the_user_ruled_out_is_shown_back_to_them():
    """用户明说的「不想要」必须出现在理由链里，而且一行最多三样。"""
    results = recommend(
        RecommendRequest(
            state=NeedState(mood_id="tired", need_keys=["hide", "sit"], avoid_tags=["people"]),
            limit=1,
        )
    )
    said = results[0].reason_chain[0]
    assert "不想见人" in said
    assert said.removeprefix("你说：").count("、") <= 2


def test_hurried_state_prefers_somewhere_reachable_now():
    hurried = recommend(RecommendRequest(state=NeedState(mood_id="tight", energy=1), limit=3))
    assert hurried[0].time_to_relief in {"now", "near"}
    assert hurried[0].relief_label
    assert all(item.reach_minutes and item.reach_minutes > 0 for item in hurried)


def test_trade_offs_come_from_the_place_record_not_from_feedback_options():
    for item in recommend(RecommendRequest(state=NeedState(mood_id="low"), limit=5)):
        assert item.tradeoffs


def test_travel_time_is_stated_once_and_never_repeated_as_a_cost():
    """「到达」那一行已经写了路程，代价栏再写一遍是同一个信息说两遍。"""
    for item in recommend(RecommendRequest(state=NeedState(mood_id="low"), limit=8)):
        for cost in item.tradeoffs:
            assert "路上" not in cost and "分钟" not in cost, f"代价里重复了路程：{cost}"


def test_each_piece_of_evidence_quotes_a_different_thing_the_user_said():
    read = _read("今天脑子很乱，不想见人，也不想花很多钱")
    quoted = re.findall(r"「([^」]+)」", "".join(read.evidence))
    assert len(quoted) == len(set(quoted)), f"同一句话被引用了两次：{quoted}"
    assert len(read.evidence) == 3


def test_no_place_may_present_an_average_before_it_has_samples():
    for item in recommend(RecommendRequest(state=NeedState(mood_id="low"), limit=5)):
        assert item.sample_size == 0
        assert item.low_support is True


def test_api_returns_one_primary_plus_two_alternates():
    response = client.post(
        "/api/v1/recommendations",
        json={"state": {"mood_id": "empty", "need_keys": ["sit"]}, "limit": 3},
    )
    body = response.json()
    assert response.status_code == 200
    roles = [item["role"] for item in body["recommendations"]]
    assert roles.count("primary") == 1
    assert roles[0] == "primary"
    assert "no_good_match" in body


def test_interpret_endpoint_exposes_the_restatement_the_first_screen_needs():
    body = client.post("/api/v1/interpret", json={"text": "很累，不想说话"}).json()
    assert body["state_label"]
    assert body["acknowledgement"]
    assert body["evidence"]
    assert body["corrections"]["state"]


# --- FR-07 营业状态 ---------------------------------------------------------

from datetime import datetime

from backend_app.opening_hours import BEIJING, open_state, resolve_hours


def _place(place_id: str) -> dict:
    from backend_app.recommender import load_catalog

    return next(p for p in load_catalog()["PLACES"] if p["placeId"] == place_id)


def test_open_spaces_have_no_opening_hours_to_get_wrong():
    for place_id in ("liangmahe", "shichahai", "yangmeizhu"):
        status, label, source = open_state(_place(place_id), datetime(2026, 9, 9, 3, tzinfo=BEIJING))
        assert status == "always_open"
        assert source == "always_open"
        assert "没有门" in label


def test_late_night_stops_recommending_places_with_doors():
    from backend_app.recommender import recommend

    results = recommend(
        RecommendRequest(state=NeedState(mood_id="low"), limit=3),
        now=datetime(2026, 9, 9, 3, tzinfo=BEIJING),
    )
    assert results
    assert all(item.open_state == "always_open" for item in results)


def test_a_bar_is_open_at_midnight_and_shut_at_noon():
    bar = _place("zhaodai")
    assert open_state(bar, datetime(2026, 9, 9, 23, tzinfo=BEIJING))[0] == "open"
    assert open_state(bar, datetime(2026, 9, 9, 12, tzinfo=BEIJING))[0] == "likely_closed"


def test_estimated_hours_never_hard_filter_and_always_say_they_are_estimates():
    from backend_app.recommender import _hard_filter

    shop = {"placeId": "x", "category": "唱片店 · 室内", "distanceKm": 2}
    midnight = datetime(2026, 9, 9, 3, tzinfo=BEIJING)
    status, label, source = open_state(shop, midnight)
    assert status == "likely_closed"
    assert source == "category_estimate"
    assert "未经核对" in label
    # 估算只降权，不把地点悄悄拿掉
    assert _hard_filter(shop, NeedState(mood_id="low"), set(), midnight) is True


def test_provider_hours_are_used_but_still_never_hard_filter():
    """高德的营业时间比我猜的准，但也会过期——过期的数据不该悄悄拿掉选项。"""
    from backend_app.recommender import _hard_filter

    shop = {"placeId": "x", "category": "唱片店 · 室内", "distanceKm": 2,
            "hours": {"spans": [["12:00", "20:00"]], "verification_status": "provider"}}
    midnight = datetime(2026, 9, 9, 3, tzinfo=BEIJING)
    status, label, source = open_state(shop, midnight)
    assert status == "likely_closed"
    assert source == "provider"
    assert "高德" in label
    assert _hard_filter(shop, NeedState(mood_id="low"), set(), midnight) is True


def test_verified_closed_hours_are_a_real_hard_constraint():
    from backend_app.recommender import _hard_filter

    shop = dict(_place("fruityshop"))
    shop["hours"] = {"open": "12:00", "close": "20:00", "verification_status": "verified"}
    midnight = datetime(2026, 9, 9, 3, tzinfo=BEIJING)
    assert open_state(shop, midnight)[0] == "closed"
    assert resolve_hours(shop)["source"] == "verified"
    assert _hard_filter(shop, NeedState(mood_id="low"), set(), midnight) is False


def test_when_everything_is_shut_the_response_says_so():
    body = client.post(
        "/api/v1/recommendations",
        json={"state": {"mood_id": "spark", "environment": "indoor"}, "limit": 3},
    ).json()
    shut = [item for item in body["recommendations"] if item["open_state"] in {"likely_closed", "closed"}]
    if len(shut) == len(body["recommendations"]) and body["recommendations"]:
        assert body["no_good_match"] is True
        assert "打烊" in body["fallback_note"]


# --- FR-09 哪一环对/错 ------------------------------------------------------


def test_outcome_accepts_and_defaults_the_mismatch_stage():
    from backend_app.schemas import OutcomeRequest

    payload = OutcomeRequest(
        session_id="ses_12345678",
        recommendation_id="rec_12345678",
        place_id="beihai",
        change_score=-1,
    )
    assert payload.mismatch_stage == "none"
    payload = OutcomeRequest(
        session_id="ses_12345678",
        recommendation_id="rec_12345678",
        place_id="beihai",
        change_score=-1,
        mismatch_stage="constraint",
    )
    assert payload.mismatch_stage == "constraint"


def test_mismatch_stage_is_rejected_when_it_is_not_one_of_the_four_steps():
    response = client.post(
        "/api/v1/outcomes",
        json={
            "session_id": "ses_12345678",
            "recommendation_id": "rec_12345678",
            "place_id": "beihai",
            "change_score": 1,
            "mismatch_stage": "vibes",
        },
    )
    assert response.status_code == 422


def test_mismatch_stage_survives_the_event_property_allowlist():
    from backend_app.schemas import ProductEvent
    from backend_app.storage import safe_event_properties

    event = ProductEvent(
        name="outcome_saved",
        session_id="ses_12345678",
        properties={"mismatch_stage": "need", "change_score": 2, "note": "不该出现的原文"},
    )
    safe = safe_event_properties(event)
    assert safe["mismatch_stage"] == "need"
    assert "note" not in safe


# --- FR-08 在场证明 ---------------------------------------------------------

from backend_app.presence import (
    MIN_DWELL_MINUTES,
    geofence_radius_m,
    has_geofence,
    verify as verify_presence,
)

VERIFIED_AMAP = {
    "provider_place_id": "B000TEST",
    "longitude": 116.389,
    "latitude": 39.925,
    "verification_status": "verified",
}


def _unverified_place() -> dict:
    """随便找一个还没人工核对过的地点。

    直接写死某个 placeId 会在 Julie 确认到它的那天突然变红——
    这些测试要的是「未核对的地点长什么样」，不是某一家店。
    """
    from backend_app.presence import has_geofence
    from backend_app.recommender import load_catalog

    for place in load_catalog()["PLACES"]:
        if not has_geofence(place):
            return place
    pytest.skip("26 个地点已经全部核对完了，这条断言没有对象可测")


def test_a_geofence_exists_only_where_a_human_confirmed_the_coordinates():
    """围栏必须和人工核对一一对应：核对过的才有，没核对的一个都不能有。"""
    from backend_app.recommender import load_catalog

    for place in load_catalog()["PLACES"]:
        reviewed = (place.get("amap") or {}).get("verification_status") == "verified"
        assert has_geofence(place) is reviewed, f"{place['placeId']} 的围栏和核对状态对不上"


def test_large_open_spaces_get_a_bigger_radius_than_shops():
    assert geofence_radius_m(_place("beihai")) > geofence_radius_m(_place("douzai"))
    assert geofence_radius_m(_place("liangmahe")) == geofence_radius_m(_place("tiantan"))


def test_the_server_downgrades_a_geofence_claim_it_cannot_back_up():
    # 地点没有核对过的坐标 → 没有围栏 → 声明降为「按停留时长算数」
    level, reason = verify_presence("geofence_dwell", 45, _unverified_place())
    assert level == "dwell_only"
    assert "坐标" in reason


def test_short_visits_are_never_more_than_self_reported():
    verified = dict(_unverified_place(), amap=VERIFIED_AMAP)
    level, _ = verify_presence("geofence_dwell", MIN_DWELL_MINUTES - 1, verified)
    assert level == "self_reported"


def test_a_verified_place_plus_enough_dwell_is_the_only_way_to_get_verified():
    verified = dict(_unverified_place(), amap=VERIFIED_AMAP)
    level, reason = verify_presence("geofence_dwell", MIN_DWELL_MINUTES, verified)
    assert level == "geofence_dwell"
    assert str(MIN_DWELL_MINUTES) in reason


def test_presence_level_is_never_upgraded_beyond_what_the_client_claimed():
    verified = dict(_unverified_place(), amap=VERIFIED_AMAP)
    assert verify_presence("self_reported", 60, verified)[0] == "dwell_only"


def test_the_outcomes_endpoint_returns_the_level_it_actually_accepted():
    body = client.post(
        "/api/v1/outcomes",
        json={
            "session_id": "ses_12345678",
            "recommendation_id": "rec_12345678",
            "place_id": _unverified_place()["placeId"],
            "change_score": 2,
            "presence_level": "geofence_dwell",
            "dwell_minutes": 45,
        },
    ).json()
    assert body["presence_level"] == "dwell_only", "客户端说了不算"
    assert body["presence_reason"]


def test_a_geofence_is_published_only_alongside_a_navigation_url():
    """围栏和导航同一道门：都要人工核对过的坐标。"""
    from backend_app.recommender import _to_recommendation

    unreviewed = _unverified_place()
    rec = _to_recommendation(0.8, dict(unreviewed, amap=VERIFIED_AMAP), {}, NeedState(mood_id="low"))
    assert rec.geofence is not None
    assert rec.navigation_url is not None

    plain = _to_recommendation(0.8, unreviewed, {}, NeedState(mood_id="low"))
    assert plain.geofence is None
    assert plain.navigation_url is None


def test_the_client_never_sends_coordinates_anywhere():
    """在场证明的输入是坐标，输出只有结论。任何请求体里都不该出现经纬度。"""
    import pathlib

    client_js = (pathlib.Path(__file__).parents[1] / "current-client.js").read_text(encoding="utf-8")
    sends = re.findall(r"JSON\.stringify\(\{(.*?)\}\)", client_js, re.S)
    assert sends
    for body in sends:
        for field in ("latitude", "longitude", "coords"):
            assert field not in body or "location: activeLocation" in body, (
                f"请求体里出现了 {field}：{body[:120]}"
            )


# --- US-06 地图三选 ---------------------------------------------------------

from backend_app.coords import gcj_to_wgs, wgs_to_gcj
from backend_app.map_provider import map_links


def test_gcj_and_wgs_round_trip_without_drifting():
    for latitude, longitude in ((39.925, 116.389), (31.2304, 121.4737), (23.1291, 113.2644)):
        back = wgs_to_gcj(*gcj_to_wgs(latitude, longitude))
        assert abs(back[0] - latitude) < 1e-7
        assert abs(back[1] - longitude) < 1e-7


def test_the_two_coordinate_systems_really_are_hundreds_of_metres_apart():
    """如果这个测试变成 0，说明转换被谁绕过去了——跳转会偏到隔壁街区。"""
    import math

    latitude, longitude = 39.925, 116.389
    wgs_lat, wgs_lon = gcj_to_wgs(latitude, longitude)
    metres = math.hypot(
        (latitude - wgs_lat) * 111_320,
        (longitude - wgs_lon) * 111_320 * math.cos(math.radians(latitude)),
    )
    assert 300 < metres < 900, f"境内偏移应当是几百米，实测 {metres:.0f} m"


def test_outside_china_nothing_is_shifted():
    assert gcj_to_wgs(40.7128, -74.0060) == (40.7128, -74.0060)


def test_three_maps_are_offered_and_each_gets_its_own_coordinate_system():
    place = dict(_place("beihai"), amap=VERIFIED_AMAP)
    links = map_links(place)
    assert set(links) == {"amap", "apple", "google"}

    gcj = f"{VERIFIED_AMAP['longitude']},{VERIFIED_AMAP['latitude']}"
    assert quote(gcj, safe="") in links["amap"].replace("%2C", quote(",", safe=""))
    # Apple / Google 必须拿到转换后的 WGS-84，不能是原始的 GCJ-02
    assert str(VERIFIED_AMAP["latitude"]) not in links["apple"]
    assert str(VERIFIED_AMAP["latitude"]) not in links["google"]
    wgs_lat, wgs_lon = (round(v, 6) for v in gcj_to_wgs(VERIFIED_AMAP["latitude"], VERIFIED_AMAP["longitude"]))
    assert quote(f"{wgs_lat},{wgs_lon}", safe="") in links["apple"].replace("%2C", quote(",", safe=""))
    assert quote(f"{wgs_lat},{wgs_lon}", safe="") in links["google"].replace("%2C", quote(",", safe=""))


def test_map_links_need_the_same_human_review_as_navigation():
    from backend_app.recommender import _to_recommendation

    unreviewed = _unverified_place()
    assert map_links(unreviewed) == {}
    assert _to_recommendation(0.8, unreviewed, {}, NeedState(mood_id="low")).map_links == {}
    verified = _to_recommendation(0.8, dict(unreviewed, amap=VERIFIED_AMAP), {}, NeedState(mood_id="low"))
    assert set(verified.map_links) == {"amap", "apple", "google"}


# --- FR-12 记忆可删除 -------------------------------------------------------


def test_deleting_a_record_is_accepted_and_scoped_to_one_session():
    body = client.post(
        "/api/v1/outcomes/delete",
        json={"session_id": "ses_12345678", "recommendation_id": "rec_12345678"},
    )
    assert body.status_code == 202
    assert body.json()["accepted"] is True


def test_delete_rejects_ids_that_could_not_be_ours():
    for payload in (
        {"session_id": "short", "recommendation_id": "rec_12345678"},
        {"session_id": "ses_12345678"},
        {"recommendation_id": "rec_12345678"},
    ):
        assert client.post("/api/v1/outcomes/delete", json=payload).status_code == 422


def test_delete_never_logs_what_was_deleted(caplog):
    with caplog.at_level("INFO", logger="current"):
        client.post(
            "/api/v1/outcomes/delete",
            json={"session_id": "ses_12345678", "recommendation_id": "rec_12345678"},
        )
    logged = " ".join(r.message for r in caplog.records)
    assert "outcome_deleted" in logged
    assert "note" not in logged and "change_score" not in logged


# --- 「太远了」这条纠错必须真的生效，且不能把人推进空屏 ---


def test_saying_it_is_too_far_actually_narrows_the_shortlist():
    wide = recommend(RecommendRequest(state=NeedState(mood_id="noisy"), limit=3))
    near = recommend(RecommendRequest(state=NeedState(mood_id="noisy", max_travel_minutes=15), limit=3))
    assert any(item.reach_minutes > 15 for item in wide), "没有上限时本来就该出现远的"
    assert all(item.reach_minutes <= 15 for item in near), "说了太远还给远的，等于没听见"


def test_an_impossible_cap_falls_back_to_the_nearest_and_says_they_exceed_it():
    body = client.post(
        "/api/v1/recommendations",
        json={"state": {"mood_id": "noisy", "max_travel_minutes": 5}, "limit": 3},
    ).json()
    assert body["recommendations"], "纠错之后不能给空屏"
    assert body["no_good_match"] is True
    assert "都超了" in body["fallback_note"]
