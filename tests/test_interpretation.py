import re

from backend_app.interpretation import _decorate, interpret_with_rules
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


def test_english_rule_fallback_keeps_the_whole_response_in_english():
    text = "I'm exhausted and don't want to see anyone. I need fresh air and a breeze."
    result = _decorate(interpret_with_rules(text), text, lang="en")

    assert result.state.mood_id == "tired"
    assert result.state.social_mode == "alone"
    assert result.state.environment == "outdoor"
    assert {"hide", "breathe"}.issubset(result.state.need_keys)
    assert "tired but wired" in result.acknowledgement
    assert all(not re.search(r"[\u3400-\u9fff]", line) for line in result.evidence)
    assert any("「exhausted」" in line for line in result.evidence)


def test_natural_english_evidence_is_not_rejected_by_the_chinese_length_limit():
    text = "Long day at work. I am wiped out."
    evidence = ["「Long day at work」 — so I’ll keep this low effort and close by"]
    result = _decorate(
        interpret_with_rules(text),
        text,
        model_evidence=evidence,
        lang="en",
    )

    assert result.evidence == evidence


def test_english_outdoor_negation_is_not_misread_as_an_outdoor_request():
    result = interpret_with_rules("I want somewhere quiet, but not outside")
    assert result.state.environment == "indoor"
