from backend_app.interpretation import interpret_with_rules
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

