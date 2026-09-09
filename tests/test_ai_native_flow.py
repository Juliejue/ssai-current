"""The PRD's visible promises, asserted where they can regress silently."""

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
    assert len(read.correction_chips) == 6
    assert all(chip.key != read.state.mood_id for chip in read.correction_chips)


def test_first_result_is_the_primary_and_the_rest_are_alternates():
    results = recommend(RecommendRequest(state=NeedState(mood_id="noisy", need_keys=["hide"]), limit=3))
    assert len(results) == 3
    assert [item.role for item in results] == ["primary", "alternate", "alternate"]


def test_reason_chain_is_state_then_need_then_matched_attribute():
    results = recommend(RecommendRequest(state=NeedState(mood_id="tight", need_keys=["slow"]), limit=1))
    chain = results[0].reason_chain
    assert len(chain) == 3
    assert chain[0].startswith("你说：")
    assert chain[1].startswith("所以要找：")
    assert chain[2].startswith("这里命中：") or "不太确定" in chain[2]


def test_hurried_state_prefers_somewhere_reachable_now():
    hurried = recommend(RecommendRequest(state=NeedState(mood_id="tight", energy=1), limit=3))
    assert hurried[0].time_to_relief in {"now", "near"}
    assert hurried[0].relief_label
    assert all(item.reach_minutes and item.reach_minutes > 0 for item in hurried)


def test_trade_offs_come_from_the_place_record_not_from_feedback_options():
    for item in recommend(RecommendRequest(state=NeedState(mood_id="low"), limit=5)):
        assert item.tradeoffs
        if item.reach_minutes < 25:
            assert not any("路上大约" in cost for cost in item.tradeoffs)


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
    assert "correction_chips" in body


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

    shop = _place("fruityshop")
    midnight = datetime(2026, 9, 9, 3, tzinfo=BEIJING)
    status, label, source = open_state(shop, midnight)
    assert status == "likely_closed"
    assert source == "category_estimate"
    assert "未经核对" in label
    # 估算只降权，不把地点悄悄拿掉
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
