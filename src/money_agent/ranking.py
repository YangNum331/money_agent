from __future__ import annotations


def expected_profit(
    expected_revenue: float,
    success_probability: float,
    api_cost: float,
    platform_cost: float,
    risk_cost: float,
) -> float:
    return round(
        expected_revenue * success_probability - api_cost - platform_cost - risk_cost,
        2,
    )


def opportunity_score(
    *,
    expected_profit_usd: float,
    automation_score: float,
    success_probability: float,
    difficulty_score: float,
    competition_risk: float,
    platform_risk: float,
    expected_hours: float,
) -> float:
    profit_score = min(max(expected_profit_usd, 0.0) / 100.0, 1.0) * 100.0
    time_score = max(0.0, 100.0 - min(expected_hours, 20.0) * 5.0)
    score = (
        0.28 * profit_score
        + 0.22 * automation_score
        + 0.20 * (success_probability * 100.0)
        + 0.10 * (100.0 - difficulty_score)
        + 0.08 * (100.0 - competition_risk)
        + 0.07 * (100.0 - platform_risk)
        + 0.05 * time_score
    )
    return round(min(max(score, 0.0), 100.0), 2)

