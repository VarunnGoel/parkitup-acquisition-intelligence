from __future__ import annotations

import pandas as pd
import pytest

from python.model_validation.sensitivity import (
    rank_stability,
    recalculate_weighted_scores,
    revenue_sensitivity_grid,
    validate_weights,
)


THRESHOLDS = {
    "attractiveness_high": 65.0,
    "attractiveness_develop": 45.0,
    "feasibility_mid": 60.0,
}


def test_weight_validation_accepts_percentages_and_rejects_invalid_totals() -> None:
    weights = validate_weights(
        {"DEMAND": 30, "REVENUE": 25, "COMPETITION": 15, "STRATEGIC_FIT": 15, "FEASIBILITY": 15}
    )
    assert sum(weights.values()) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        validate_weights(
            {"DEMAND": 30, "REVENUE": 25, "COMPETITION": 15, "STRATEGIC_FIT": 15, "FEASIBILITY": 10}
        )


def test_reweighting_changes_scores_and_recalculates_rank() -> None:
    frame = pd.DataFrame(
        {
            "parking_id": [1, 2, 3],
            "demand_score": [95.0, 50.0, 35.0],
            "revenue_score": [30.0, 95.0, 40.0],
            "competition_score": [50.0, 50.0, 90.0],
            "strategic_fit_score": [50.0, 50.0, 90.0],
            "feasibility_score": [60.0, 60.0, 90.0],
        }
    )
    demand = recalculate_weighted_scores(
        frame,
        {"DEMAND": 0.60, "REVENUE": 0.10, "COMPETITION": 0.10, "STRATEGIC_FIT": 0.10, "FEASIBILITY": 0.10},
        THRESHOLDS,
    )
    revenue = recalculate_weighted_scores(
        frame,
        {"DEMAND": 0.10, "REVENUE": 0.60, "COMPETITION": 0.10, "STRATEGIC_FIT": 0.10, "FEASIBILITY": 0.10},
        THRESHOLDS,
    )
    assert int(demand.iloc[0]["parking_id"]) == 1
    assert int(revenue.iloc[0]["parking_id"]) == 2
    assert set(demand["rank_overall"]) == {1, 2, 3}


def test_rank_stability_calculates_top10_and_top20_frequency() -> None:
    rows = []
    for scenario, ranks in {"BASE_CASE": [1, 11], "ALT_A": [2, 9], "ALT_B": [12, 8]}.items():
        for parking_id, rank in zip([1, 2], ranks):
            rows.append(
                {
                    "parking_id": parking_id,
                    "lot_name": f"Lot {parking_id}",
                    "locality_name": "Test",
                    "scenario_code": scenario,
                    "rank_overall": rank,
                    "acquisition_score": 80 - rank,
                    "segment_code": "ACQUIRE_NOW" if rank <= 10 else "PURSUE",
                }
            )
    result = rank_stability(pd.DataFrame(rows)).set_index("parking_id")
    assert result.loc[1, "top_10_frequency_pct"] == pytest.approx(66.67)
    assert result.loc[2, "top_10_frequency_pct"] == pytest.approx(66.67)
    assert result.loc[1, "top_20_frequency_pct"] == 100.0


def test_revenue_sensitivity_increases_with_occupancy_and_commission() -> None:
    frame = pd.DataFrame(
        {
            "parking_id": [1],
            "lot_name": ["Lot 1"],
            "locality_name": ["Test"],
            "avg_occupancy_rate": [0.50],
            "avg_daily_platform_bookings": [20.0],
            "cancellation_rate": [0.10],
            "avg_park_duration_hours": [2.0],
            "hourly_rate_inr": [50.0],
            "expected_commission_pct": [15.0],
        }
    )
    lot, _ = revenue_sensitivity_grid(
        frame,
        occupancy_levels=[0.40, 0.80],
        price_multipliers=[1.0],
        commission_rates=[10.0, 20.0],
    )
    pivot = lot.pivot(index="occupancy_rate", columns="commission_scenario", values="expected_monthly_platform_revenue_inr")
    assert pivot.loc[0.80, "GLOBAL_10_PCT"] > pivot.loc[0.40, "GLOBAL_10_PCT"]
    assert pivot.loc[0.40, "GLOBAL_20_PCT"] > pivot.loc[0.40, "GLOBAL_10_PCT"]

