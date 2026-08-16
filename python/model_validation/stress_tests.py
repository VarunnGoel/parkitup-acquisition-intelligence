"""Synthetic adversarial cases for the score logic."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from python.analysis.scoring_engine import score_scenario
from python.model_validation.diagnostics import _feasibility_from_inputs
from python.model_validation.sensitivity import validate_weights


def _candidate(base: pd.Series, name: str, parking_id: int) -> pd.Series:
    result = base.copy()
    result["parking_id"] = parking_id
    result["lot_code"] = f"SYN-{parking_id}"
    result["lot_name"] = name
    result["locality_name"] = "Synthetic Stress Market"
    return result


def build_stress_cases(component_scores: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Construct intentionally difficult cases from a neutral observed row."""
    median = component_scores.iloc[
        (component_scores["acquisition_score"] if "acquisition_score" in component_scores else component_scores["capacity_cars"]).sub(
            (component_scores["acquisition_score"] if "acquisition_score" in component_scores else component_scores["capacity_cars"]).median()
        ).abs().argsort().iloc[0]
    ].copy()

    def base_case(name: str, parking_id: int) -> pd.Series:
        return _candidate(median, name, parking_id)

    cases: dict[str, pd.DataFrame] = {}

    huge_low = base_case("Synthetic huge lot with low occupancy", -1)
    huge_low.update(
        {
            "capacity_cars": 1500,
            "avg_occupancy_rate": 0.05,
            "p90_peak_occupancy_rate": 0.12,
            "avg_daily_platform_bookings": 4.0,
            "hourly_rate_inr": 50.0,
            "location_demand_score": 45.0,
            "competition_score": 55.0,
            "strategic_fit_score": 55.0,
            "feasibility_score": 60.0,
        }
    )
    cases["TEST_A_HUGE_LOW_OCCUPANCY"] = pd.DataFrame([huge_low])

    small_strong = base_case("Synthetic small lot with strong utilization", -2)
    small_strong.update(
        {
            "capacity_cars": 50,
            "avg_occupancy_rate": 0.88,
            "p90_peak_occupancy_rate": 0.98,
            "avg_daily_platform_bookings": 70.0,
            "hourly_rate_inr": 65.0,
            "location_demand_score": 90.0,
            "competition_score": 78.0,
            "strategic_fit_score": 80.0,
            "feasibility_score": 78.0,
        }
    )
    cases["TEST_B_SMALL_HIGH_UTILIZATION"] = pd.DataFrame([small_strong])

    high_price_weak = base_case("Synthetic expensive lot with weak demand", -3)
    high_price_weak.update(
        {
            "capacity_cars": 200,
            "avg_occupancy_rate": 0.08,
            "p90_peak_occupancy_rate": 0.15,
            "avg_daily_platform_bookings": 3.0,
            "hourly_rate_inr": 200.0,
            "location_demand_score": 15.0,
            "competition_score": 55.0,
            "strategic_fit_score": 55.0,
            "feasibility_score": 65.0,
        }
    )
    cases["TEST_C_HIGH_PRICE_WEAK_DEMAND"] = pd.DataFrame([high_price_weak])

    high_comp = base_case("Synthetic high-demand lot under extreme competition", -4)
    high_comp.update(
        {
            "capacity_cars": 180,
            "avg_occupancy_rate": 0.80,
            "p90_peak_occupancy_rate": 0.95,
            "avg_daily_platform_bookings": 100.0,
            "hourly_rate_inr": 55.0,
            "location_demand_score": 90.0,
            "competition_score": 5.0,
            "strategic_fit_score": 70.0,
            "feasibility_score": 72.0,
        }
    )
    low_comp = high_comp.copy()
    low_comp["parking_id"] = -5
    low_comp["lot_code"] = "SYN-5"
    low_comp["lot_name"] = "Synthetic high-demand lot with thin competition"
    low_comp["competition_score"] = 80.0
    cases["TEST_D_HIGH_DEMAND_EXTREME_COMPETITION"] = pd.DataFrame([high_comp, low_comp])

    hard_close = base_case("Synthetic high-demand lot with unwilling owner", -6)
    hard_close.update(
        {
            "capacity_cars": 180,
            "avg_occupancy_rate": 0.82,
            "p90_peak_occupancy_rate": 0.96,
            "avg_daily_platform_bookings": 95.0,
            "hourly_rate_inr": 55.0,
            "location_demand_score": 92.0,
            "competition_score": 70.0,
            "strategic_fit_score": 75.0,
            "willingness_to_digitize": 1,
            "contract_flexibility": 1,
            "digital_payment_enabled": False,
            "management_maturity_score": 0.15,
            "documentation_readiness": 1,
            "decision_maker_accessible": False,
            "operational_complexity": 5,
            "exclusivity_possible": False,
            "requires_capex": True,
        }
    )
    hard_close["feasibility_score"] = float(_feasibility_from_inputs(pd.DataFrame([hard_close])).iloc[0])
    cases["TEST_E_HIGH_DEMAND_LOW_FEASIBILITY"] = pd.DataFrame([hard_close])

    network_gap = base_case("Synthetic moderate lot in a network gap", -7)
    network_gap.update(
        {
            "capacity_cars": 160,
            "avg_occupancy_rate": 0.42,
            "p90_peak_occupancy_rate": 0.65,
            "avg_daily_platform_bookings": 40.0,
            "hourly_rate_inr": 50.0,
            "location_demand_score": 55.0,
            "competition_score": 55.0,
            "strategic_fit_score": 90.0,
            "feasibility_score": 70.0,
        }
    )
    saturated = network_gap.copy()
    saturated["parking_id"] = -8
    saturated["lot_code"] = "SYN-8"
    saturated["lot_name"] = "Synthetic moderate lot in a saturated network"
    saturated["strategic_fit_score"] = 20.0
    cases["TEST_F_MODERATE_NETWORK_GAP"] = pd.DataFrame([network_gap, saturated])
    return cases


def run_stress_tests(
    component_scores: pd.DataFrame,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> pd.DataFrame:
    """Insert each adversarial case into the real portfolio and evaluate it."""
    clean_weights = validate_weights(weights)
    scenario = {
        "demand_multiplier": 1.0,
        "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0,
        "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0,
        "network_variant": "LIVE",
    }
    rows: list[dict[str, Any]] = []
    for test_name, synthetic in build_stress_cases(component_scores).items():
        portfolio = pd.concat([component_scores, synthetic], ignore_index=True)
        scored = score_scenario(portfolio, scenario, clean_weights, dict(thresholds))
        selected = scored[scored["parking_id"].isin(synthetic["parking_id"].tolist())].copy()
        if test_name == "TEST_D_HIGH_DEMAND_EXTREME_COMPETITION":
            pressure = selected.sort_values("competition_score").reset_index(drop=True)
            low_pressure = pressure.iloc[-1]
            high_pressure = pressure.iloc[0]
            rows.append(
                {
                    "test_id": "TEST_D",
                    "test_name": "High demand + extreme competition",
                    "case": "Extreme pressure vs thin competition twin",
                    "records_tested": 2,
                    "observed_metric": round(float(low_pressure.acquisition_score - high_pressure.acquisition_score), 3),
                    "rank_or_score": f"{int(high_pressure.rank_overall)} vs {int(low_pressure.rank_overall)}",
                    "expected": "Extreme competition lowers the composite versus an otherwise identical low-pressure twin",
                    "status": "PASS" if low_pressure.acquisition_score > high_pressure.acquisition_score else "FAIL",
                }
            )
            continue
        if test_name == "TEST_F_MODERATE_NETWORK_GAP":
            gap = selected[selected["parking_id"] == -7].iloc[0]
            saturated = selected[selected["parking_id"] == -8].iloc[0]
            rows.append(
                {
                    "test_id": "TEST_F",
                    "test_name": "Moderate economics + major network gap",
                    "case": "Network-gap twin comparison",
                    "records_tested": 2,
                    "observed_metric": round(float(gap.acquisition_score - saturated.acquisition_score), 3),
                    "rank_or_score": f"{int(gap.rank_overall)} vs {int(saturated.rank_overall)}",
                    "expected": "Strategic fit creates a visible score and rank improvement",
                    "status": "PASS" if gap.acquisition_score > saturated.acquisition_score + 5.0 else "FAIL",
                }
            )
            continue
        row = selected.iloc[0]
        if test_name == "TEST_A_HUGE_LOW_OCCUPANCY":
            passed = int(row.rank_overall) > 10 and row.segment_code != "ACQUIRE_NOW"
            expected = "Huge capacity with very low occupancy does not become a top acquisition"
            test_id = "TEST_A"
        elif test_name == "TEST_B_SMALL_HIGH_UTILIZATION":
            passed = int(row.rank_overall) <= 25
            expected = "Small, highly utilised, high-demand lot has a realistic top-quartile chance"
            test_id = "TEST_B"
        elif test_name == "TEST_C_HIGH_PRICE_WEAK_DEMAND":
            passed = int(row.rank_overall) > 10 and row.segment_code != "ACQUIRE_NOW"
            expected = "High price with weak demand does not become a top acquisition"
            test_id = "TEST_C"
        elif test_name == "TEST_E_HIGH_DEMAND_LOW_FEASIBILITY":
            passed = row.segment_code != "ACQUIRE_NOW" and float(row.feasibility_score) < float(thresholds["feasibility_mid"])
            expected = "Low feasibility materially blocks an otherwise high-demand lot"
            test_id = "TEST_E"
        else:
            raise AssertionError(test_name)
        rows.append(
            {
                "test_id": test_id,
                "test_name": test_name.replace("_", " ").title(),
                "case": str(row.lot_name),
                "records_tested": 1,
                "observed_metric": round(float(row.acquisition_score), 3),
                "rank_or_score": int(row.rank_overall),
                "expected": expected,
                "priority_segment": row.segment_code,
                "status": "PASS" if passed else "FAIL",
            }
        )
    return pd.DataFrame(rows).sort_values("test_id").reset_index(drop=True)

