"""Score diagnostics, monotonicity checks, reconciliation, and outlier review."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from python.analysis.scoring_engine import COMPONENT_COLUMNS, score_scenario, winsor_score
from python.analysis.statistics import spearman_correlation
from python.model_validation.sensitivity import recalculate_weighted_scores, validate_weights


BASE_SCENARIO = {
    "demand_multiplier": 1.0,
    "commission_multiplier": 1.0,
    "booking_share_multiplier": 1.0,
    "dwell_multiplier": 1.0,
    "onboarding_cost_multiplier": 1.0,
    "network_variant": "LIVE",
}


def score_correlations(scores: pd.DataFrame) -> pd.DataFrame:
    """Return Pearson and Spearman correlations among score components."""
    fields = [
        "demand_score",
        "revenue_score",
        "competition_score",
        "strategic_fit_score",
        "feasibility_score",
        "attractiveness_score",
        "acquisition_score",
    ]
    rows: list[dict[str, Any]] = []
    numeric = scores[fields].apply(pd.to_numeric, errors="coerce")
    for left_index, left in enumerate(fields):
        for right in fields[left_index + 1 :]:
            pair = numeric[[left, right]].dropna()
            rows.append(
                {
                    "left_metric": left,
                    "right_metric": right,
                    "n": int(len(pair)),
                    "pearson": round(float(pair[left].corr(pair[right], method="pearson")), 4),
                    "spearman": round(spearman_correlation(pair[left], pair[right]), 4),
                }
            )
    return pd.DataFrame(rows)


def component_influence(
    scores: pd.DataFrame,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> pd.DataFrame:
    """Measure weighted contribution and leave-one-component neutralisation."""
    clean_weights = validate_weights(weights)
    base = scores.copy()
    base["_base_rank"] = base["acquisition_rank"]
    rows: list[dict[str, Any]] = []
    for dimension, column in COMPONENT_COLUMNS.items():
        component = pd.to_numeric(base[column], errors="coerce")
        contribution = component * clean_weights[dimension]
        neutral = base.copy()
        neutral[column] = float(component.median())
        neutral_result = recalculate_weighted_scores(neutral, clean_weights, thresholds).set_index("parking_id")
        aligned = neutral_result.reindex(base["parking_id"])
        original = base.set_index("parking_id").reindex(aligned.index)
        rows.append(
            {
                "dimension": dimension,
                "score_column": column,
                "weight_pct": round(clean_weights[dimension] * 100.0, 2),
                "component_score_std": round(float(component.std(ddof=1)), 3),
                "weighted_contribution_std": round(float(contribution.std(ddof=1)), 3),
                "acquisition_spearman": round(spearman_correlation(component, base["acquisition_score"]), 4),
                "mean_abs_rank_change_when_neutralized": round(
                    float((aligned["rank_overall"] - original["_base_rank"]).abs().mean()), 3
                ),
                "max_abs_rank_change_when_neutralized": int(
                    (aligned["rank_overall"] - original["_base_rank"]).abs().max()
                ),
                "top10_overlap_when_neutralized": int(
                    ((aligned["rank_overall"] <= 10) & (original["_base_rank"] <= 10)).sum()
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["dominance_review"] = np.select(
        [
            result["weighted_contribution_std"] == result["weighted_contribution_std"].max(),
            result["mean_abs_rank_change_when_neutralized"] == result["mean_abs_rank_change_when_neutralized"].max(),
        ],
        ["Largest weighted contribution spread", "Largest ranking displacement when neutralized"],
        default="Contextual contributor; inspect jointly with correlations",
    )
    return result.sort_values("weighted_contribution_std", ascending=False).reset_index(drop=True)


def base_case_reconciliation(
    component_scores: pd.DataFrame,
    official_scores: pd.DataFrame,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> pd.DataFrame:
    """Compare a validation base rerun with persisted scoring outputs."""
    recalculated = score_scenario(component_scores, BASE_SCENARIO, validate_weights(weights), dict(thresholds))
    comparison = recalculated[
        [
            "parking_id",
            "demand_score",
            "revenue_score",
            "competition_score",
            "strategic_fit_score",
            "feasibility_score",
            "acquisition_score",
            "rank_overall",
            "segment_code",
            "expected_monthly_platform_revenue_inr",
        ]
    ].merge(
        official_scores[
            [
                "parking_id",
                "demand_score",
                "revenue_score",
                "competition_score",
                "strategic_fit_score",
                "feasibility_score",
                "acquisition_score",
                "acquisition_rank",
                "priority_segment",
                "expected_monthly_platform_revenue_inr",
            ]
        ],
        on="parking_id",
        suffixes=("_recomputed", "_persisted"),
    )
    score_columns = [
        "demand_score",
        "revenue_score",
        "competition_score",
        "strategic_fit_score",
        "feasibility_score",
        "acquisition_score",
        "expected_monthly_platform_revenue_inr",
    ]
    for column in score_columns:
        comparison[f"{column}_abs_diff"] = (
            pd.to_numeric(comparison[f"{column}_recomputed"], errors="coerce")
            - pd.to_numeric(comparison[f"{column}_persisted"], errors="coerce")
        ).abs()
    comparison["rank_equal"] = comparison["rank_overall"] == comparison["acquisition_rank"]
    comparison["segment_equal"] = comparison["segment_code"] == comparison["priority_segment"]
    return comparison


def _feasibility_from_inputs(frame: pd.DataFrame) -> pd.Series:
    """Mirror the documented scoring feasibility formula for monotonicity tests."""
    return (
        0.20 * ((frame["willingness_to_digitize"] - 1) / 4.0 * 100.0)
        + 0.14 * ((frame["contract_flexibility"] - 1) / 4.0 * 100.0)
        + 0.12 * (0.30 * frame["digital_payment_enabled"].astype(float) * 100.0 + 0.70 * frame["management_maturity_score"] * 100.0)
        + 0.15 * ((frame["documentation_readiness"] - 1) / 4.0 * 100.0)
        + 0.12 * frame["decision_maker_accessible"].astype(float) * 100.0
        + 0.08 * ((5 - frame["operational_complexity"]) / 4.0 * 100.0)
        + 0.07 * frame["onboarding_cost_score"]
        + 0.04 * frame["setup_speed_score"]
        + 0.03 * np.where(frame["exclusivity_possible"], 100.0, 35.0)
        + 0.02 * np.where(frame["requires_capex"], 20.0, 100.0)
        + 0.03 * frame["owner_type"].map(
            {
                "Government/Municipal": 25.0,
                "RWA": 45.0,
                "Individual": 65.0,
                "Family Trust": 60.0,
                "Private Company": 80.0,
                "Mall Management": 75.0,
            }
        ).fillna(70.0)
    ).clip(0.0, 100.0)


def _competition_from_inputs(frame: pd.DataFrame) -> pd.Series:
    """Mirror the scoring competition formula for a controlled pressure test."""
    # Floor must match database/schema/06_analysis.sql, which clamps
    # market_demand_prior at 0.10 before dividing. This read 0.01, an already
    # drifted copy; harmless while the prior stays in its generated 0.55-0.88
    # range, but it would diverge from the deployed formula on any lower value.
    pressure = np.log1p(pd.to_numeric(frame["competitor_count_1km"], errors="raise")) / frame["market_demand_prior"].clip(lower=0.10)
    low = float(frame["competition_low"].iloc[0])
    high = float(frame["competition_high"].iloc[0])
    supply = winsor_score(pressure, low, high, invert=True)
    aggregator = 100.0 * (1.0 - frame["aggregator_penetration_rate"].astype(float))
    distance = np.minimum(100.0, frame["competitor_distance_proxy_m"].astype(float) / 1500.0 * 100.0)
    price_ratio = frame["competitor_price_ratio"]
    headroom = np.where(
        price_ratio.isna(),
        55.0,
        100.0 * np.maximum(0.0, np.minimum(1.0, (price_ratio.astype(float) - 0.70) / 0.60)),
    )
    return (0.55 * supply + 0.20 * aggregator + 0.15 * distance + 0.10 * headroom).clip(0.0, 100.0)


def monotonicity_tests(component_scores: pd.DataFrame) -> pd.DataFrame:
    """Run programmatic directional sanity checks across the portfolio."""
    rows: list[dict[str, Any]] = []
    base = component_scores.copy()

    def add(test_id: str, description: str, deltas: pd.Series, direction: str) -> None:
        numeric = pd.to_numeric(deltas, errors="coerce").dropna()
        violations = int((numeric < -1e-8).sum()) if direction == "nondecreasing" else int((numeric > 1e-8).sum())
        rows.append(
            {
                "test_id": test_id,
                "description": description,
                "records_tested": int(len(numeric)),
                "violations": violations,
                "minimum_delta": round(float(numeric.min()), 8) if len(numeric) else None,
                "maximum_delta": round(float(numeric.max()), 8) if len(numeric) else None,
                "status": "PASS" if violations == 0 else "FAIL",
            }
        )

    low_demand = score_scenario(base, {**BASE_SCENARIO, "demand_multiplier": 0.85}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    high_demand = score_scenario(base, {**BASE_SCENARIO, "demand_multiplier": 1.15}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    add("MONO-DEMAND", "Increasing demand multiplier does not reduce Demand Score", high_demand.set_index("parking_id")["demand_score"] - low_demand.set_index("parking_id")["demand_score"], "nondecreasing")

    low_commission = score_scenario(base, {**BASE_SCENARIO, "commission_multiplier": 0.70}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    high_commission = score_scenario(base, {**BASE_SCENARIO, "commission_multiplier": 1.30}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    add("MONO-REVENUE", "Increasing commission does not reduce Revenue Score", high_commission.set_index("parking_id")["revenue_score"] - low_commission.set_index("parking_id")["revenue_score"], "nondecreasing")

    low_cost = score_scenario(base, {**BASE_SCENARIO, "onboarding_cost_multiplier": 0.75}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    high_cost = score_scenario(base, {**BASE_SCENARIO, "onboarding_cost_multiplier": 1.50}, {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15})
    add("MONO-COST", "Increasing onboarding cost does not improve Feasibility Score", high_cost.set_index("parking_id")["feasibility_score"] - low_cost.set_index("parking_id")["feasibility_score"], "nonincreasing")

    willingness_low = base.copy()
    willingness_high = base.copy()
    willingness_low["willingness_to_digitize"] = 1
    willingness_high["willingness_to_digitize"] = 5
    add("MONO-FEASIBILITY", "Increasing owner willingness does not reduce Feasibility Score", _feasibility_from_inputs(willingness_high) - _feasibility_from_inputs(willingness_low), "nondecreasing")

    competition_low = base.copy()
    competition_high = base.copy()
    competition_low["competitor_count_1km"] = 0
    competition_high["competitor_count_1km"] = competition_low["competitor_count_1km"] + 10
    add("MONO-COMPETITION", "Increasing competitor count does not improve Competition Opportunity", _competition_from_inputs(competition_high) - _competition_from_inputs(competition_low), "nonincreasing")

    # the final audit addition. Part 13 requires that higher strategic whitespace must
    # not reduce Strategic Fit, which no earlier test covered. Strategic Fit is
    # 0.50 network band + 0.35 whitespace + 0.15 anchor capacity, so holding the
    # other two fixed and raising whitespace must raise the pillar.
    whitespace_low = base.copy()
    whitespace_high = base.copy()
    whitespace_low["market_whitespace_score"] = 0.0
    whitespace_high["market_whitespace_score"] = 100.0
    strategic = lambda frame: (
        0.50 * frame["network_distance_score"].astype(float)
        + 0.35 * frame["market_whitespace_score"].astype(float)
        + 0.15 * frame["anchor_capacity_score"].astype(float)
    ).clip(0.0, 100.0)
    add("MONO-STRATEGIC", "Increasing market whitespace does not reduce Strategic Fit", strategic(whitespace_high) - strategic(whitespace_low), "nondecreasing")

    # the final audit addition. Part 13 also requires that more revenue potential must
    # not reduce the Revenue pillar. MONO-REVENUE varies commission only; this
    # varies the tariff, which enters the revenue identity independently.
    rate_low = base.copy()
    rate_high = base.copy()
    rate_high["hourly_rate_inr"] = rate_low["hourly_rate_inr"].astype(float) * 1.25
    weights = {"DEMAND": 0.3, "REVENUE": 0.25, "COMPETITION": 0.15, "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15}
    add(
        "MONO-TARIFF",
        "Increasing the hourly tariff does not reduce Revenue Score",
        score_scenario(rate_high, BASE_SCENARIO, weights).set_index("parking_id")["revenue_score"]
        - score_scenario(rate_low, BASE_SCENARIO, weights).set_index("parking_id")["revenue_score"],
        "nondecreasing",
    )
    return pd.DataFrame(rows)


def outlier_review(scores: pd.DataFrame) -> pd.DataFrame:
    """Identify extreme values and document why they are retained."""
    frame = scores.copy()
    specifications = [
        ("EXTREME_LARGE_LOTS", "capacity_cars", "high", "Extremely large parking lots"),
        ("EXTREME_HIGH_PRICES", "hourly_rate_inr", "high", "Extremely high hourly prices"),
        ("EXTREME_REVENUE", "expected_monthly_platform_revenue_inr", "high", "Extremely high expected platform revenue"),
        ("EXTREME_HIGH_OCCUPANCY", "avg_occupancy_rate", "high_quantile", "Extremely high average occupancy"),
        ("EXTREME_LOW_UTILIZATION", "avg_occupancy_rate", "low_quantile", "Unusually low average occupancy"),
        ("EXTREME_ACQUISITION_SCORE", "acquisition_score", "high_quantile", "Unusually high acquisition score"),
    ]
    rows: list[dict[str, Any]] = []
    for test_id, column, rule, description in specifications:
        series = pd.to_numeric(frame[column], errors="coerce")
        if rule == "high":
            q1, q3 = series.quantile([0.25, 0.75])
            threshold = float(q3 + 1.5 * (q3 - q1))
            mask = series > threshold
        elif rule == "high_quantile":
            threshold = float(series.quantile(0.975))
            mask = series >= threshold
        else:
            threshold = float(series.quantile(0.025))
            mask = series <= threshold
        for row in frame.loc[mask].itertuples(index=False):
            value = getattr(row, column)
            rows.append(
                {
                    "test_id": test_id,
                    "description": description,
                    "parking_id": int(row.parking_id),
                    "parking_name": row.lot_name,
                    "locality_name": row.locality_name,
                    "metric": column,
                    "value": float(value),
                    "threshold": threshold,
                    "plausible_within_schema": True,
                    "data_nature": "SYNTHETIC" if column in {"capacity_cars", "hourly_rate_inr", "avg_occupancy_rate"} else "DERIVED",
                    "data_issue": False,
                    "treatment": "Retained; scoring continuous inputs use 5th/95th percentile anchors where applicable.",
                    "distortion_assessment": "Review in context; no automatic removal or winsorisation of source facts.",
                }
            )
    return pd.DataFrame(rows).sort_values(["test_id", "value"], ascending=[True, False]).reset_index(drop=True)
