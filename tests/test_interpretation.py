import asyncio

import pytest

from backend_app import interpretation
from backend_app.interpretation import interpret, interpret_with_rules
from backend_app.schemas import NeedState
from backend_app.schemas import RiskLevel


def test_low_energy_private_need_is_extracted():
    result = interpret_with_rules("我今天很累，不想见人，也不想花钱，只想出去走走")
    assert result.state.energy == 1
    assert result.state.social_mode == "alone"
    assert result.state.budget_level == "free"
    assert {"hide", "free", "walk"}.issubset(result.state.need_keys)


def test_urgent_language_is_routed_before_recommendation():
    result = interpret_with_rules("我不想活了")
    assert result.state.risk_level == RiskLevel.urgent


@pytest.mark.parametrize(
    ("text", "mood_id"),
    [
        ("今天特别开心，想找个热闹的地方继续玩", "bright"),
        ("刚拿到 offer，兴奋得坐不住，想庆祝一下", "bright"),
        ("我很生气，想出去走走吹吹风", "heated"),
        ("刚开完会有点紧绷，想看夕阳吹风", "tight"),
        ("我有点委屈，想找个安静没人看见我的地方", "low"),
        ("我不难过，也不累，就是想随便走走", "okay"),
    ],
)
def test_distinct_states_do_not_collapse_to_tired(text, mood_id):
    assert interpret_with_rules(text).state.mood_id == mood_id


def test_positive_excitement_is_not_mistaken_for_racing_thoughts():
    state = interpret_with_rules("拿到 offer 以后特别兴奋，坐不住，想庆祝").state
    assert state.mood_id == "bright"
    assert state.energy == 3


def test_not_wanting_to_be_alone_is_not_parsed_as_wanting_solitude():
    state = interpret_with_rules("吵完架脑子停不下来，但我不想一个人待着，也不想说话").state
    # “但”后面强调的是此刻不想独处；主状态可以落在 near，前半句不能
    # 反过来把后半句解析成 alone / hide。
    assert state.mood_id == "near"
    assert state.social_mode == "low_contact"
    assert "people" in state.need_keys
    assert "hide" not in state.need_keys


def test_positive_mood_can_still_rule_out_noise():
    state = interpret_with_rules("我很开心，但不想去太吵的地方").state
    assert state.mood_id == "bright"
    assert "loud" in state.avoid_tags


def test_sunset_breeze_and_open_view_are_treated_as_outdoor_requirements():
    for text in ("刚开完会有点紧绷，想看夕阳吹风", "想找个视野开阔、能看远一点的地方"):
        state = interpret_with_rules(text).state
        assert state.environment == "outdoor"
        assert "breathe" in state.need_keys


def test_explicit_need_outweighs_negated_substrings():
    state = interpret_with_rules("我不难过，也不累，只想去一个能走走的地方").state
    assert state.mood_id == "okay"
    assert "walk" in state.need_keys


def test_negated_actions_do_not_turn_into_positive_energy_or_social_needs():
    state = interpret_with_rules("我不想动，也不想跳舞，更不想聊天").state
    assert state.energy == 1
    assert "loud" not in state.need_keys
    assert "people" not in state.need_keys
    assert state.social_mode != "with_people"
    assert state.place_types == []


def test_model_cannot_default_an_ambiguous_work_context_to_tired(monkeypatch):
    async def fake_call(*_args, **_kwargs):
        return NeedState(mood_id="tired", confidence=0.92), ["「刚开完会」——所以我猜你累了"]

    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setattr(interpretation, "_call_model_with_backoff", fake_call)

    result = asyncio.run(interpret("刚开完会，现在不知道去哪儿"))
    assert result.state.mood_id == "okay"
    assert result.state.confidence <= 0.4
    assert all("累" not in line for line in result.evidence)
