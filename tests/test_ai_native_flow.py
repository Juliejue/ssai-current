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
