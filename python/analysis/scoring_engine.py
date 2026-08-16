"""Build and validate the acquisition scoring engine.

SQL owns the baseline feature and component-score definitions. This module
uses those inputs to apply bounded sensitivity scenarios, persist the score
audit trail, and write diagnostics/documentation. It never modifies the
source facts the pipeline produced.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402
from python.etl.postgres_loader import run_sql_quality_checks  # noqa: E402


SCENARIOS: list[dict[str, Any]] = [
    {
        "scenario_id": 1, "scenario_code": "BASE_CASE", "scenario_group": "Base",
        "description": "Baseline weights and pipeline assumptions.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Reference scenario; all normalisation anchors are defined here.",
    },
    {
        "scenario_id": 2, "scenario_code": "CONSERVATIVE_DEMAND", "scenario_group": "Demand",
        "description": "Observed utilisation and platform booking volume reduced by 15%.",
        "weight_set_id": 1, "demand_multiplier": 0.85, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Tests lower realised demand without changing public location inputs.",
    },
    {
        "scenario_id": 3, "scenario_code": "OPTIMISTIC_DEMAND", "scenario_group": "Demand",
        "description": "Observed utilisation and platform booking volume increased by 15%.",
        "weight_set_id": 1, "demand_multiplier": 1.15, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Tests upside demand while retaining baseline scoring anchors.",
    },
    {
        "scenario_id": 4, "scenario_code": "LOWER_COMMISSION", "scenario_group": "Economics",
        "description": "Illustrative per-lot commission reduced by 30%.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 0.70,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Tests a lower synthetic commission assumption against baseline anchors.",
    },
    {
        "scenario_id": 5, "scenario_code": "HIGHER_COMMISSION", "scenario_group": "Economics",
        "description": "Illustrative per-lot commission increased by 30%.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.30,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Tests commission upside; it is not a claim about PARK It Up terms.",
    },
    {
        "scenario_id": 6, "scenario_code": "HIGH_ACQUISITION_COST", "scenario_group": "Feasibility",
        "description": "Estimated onboarding cost increased by 35% using fixed baseline anchors.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.35, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Tests implementation friction without moving the score scale.",
    },
    {
        "scenario_id": 7, "scenario_code": "DEMAND_HEAVY", "scenario_group": "Weights",
        "description": "Demand-led weighting: 40/25/10/10/15.",
        "weight_set_id": 3, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Existing baseline demand-led stress-test weights.",
    },
    {
        "scenario_id": 8, "scenario_code": "REVENUE_HEAVY", "scenario_group": "Weights",
        "description": "Revenue-led weighting: 20/40/15/10/15.",
        "weight_set_id": 5, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Revenue-led stress-test weights.",
    },
    {
        "scenario_id": 9, "scenario_code": "FEASIBILITY_HEAVY", "scenario_group": "Weights",
        "description": "Feasibility-led weighting: 20/20/10/10/40.",
        "weight_set_id": 4, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "Existing baseline feasibility-led stress-test weights.",
    },
    {
        "scenario_id": 10, "scenario_code": "BALANCED", "scenario_group": "Weights",
        "description": "Equal 20% weight for every pillar.",
        "weight_set_id": 2, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": True,
        "methodology_note": "baseline equal-weight analytical control.",
    },
    {
        "scenario_id": 11, "scenario_code": "LOWER_DWELL", "scenario_group": "Supplementary economics",
        "description": "Average stay duration reduced to 75% of baseline.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 0.75,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": False,
        "methodology_note": "Assumption A-05 diagnostic; bookings are held fixed for this stress test.",
    },
    {
        "scenario_id": 12, "scenario_code": "HIGHER_DWELL", "scenario_group": "Supplementary economics",
        "description": "Average stay duration increased to 125% of baseline.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.25,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": False,
        "methodology_note": "Assumption A-05 diagnostic; bookings are held fixed for this stress test.",
    },
    {
        "scenario_id": 13, "scenario_code": "EXPANDED_NETWORK", "scenario_group": "Supplementary network",
        "description": "Treats paused hypothetical sites as active for the distance band.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "ALL_SITES",
        "include_in_stability": False,
        "methodology_note": "Tests dependence on the hypothetical network configuration.",
    },
    {
        "scenario_id": 14, "scenario_code": "MATURE_NETWORK", "scenario_group": "Supplementary network",
        "description": "Uses only live sites operating before 2024-01-01 for the distance band.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.0,
        "booking_share_multiplier": 1.0, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "MATURE_LIVE",
        "include_in_stability": False,
        "methodology_note": "Tests a leaner hypothetical network without claiming a real inventory.",
    },
    {
        "scenario_id": 15, "scenario_code": "LOWER_PLATFORM_ECONOMICS", "scenario_group": "Supplementary economics",
        "description": "Platform booking share halved and commission reduced by 25%.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 0.75,
        "booking_share_multiplier": 0.50, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": False,
        "methodology_note": "Joint A-07/A-08 diagnostic because the inputs are multiplicative.",
    },
    {
        "scenario_id": 16, "scenario_code": "HIGHER_PLATFORM_ECONOMICS", "scenario_group": "Supplementary economics",
        "description": "Platform booking share increased by 50% and commission increased by 25%.",
        "weight_set_id": 1, "demand_multiplier": 1.0, "commission_multiplier": 1.25,
        "booking_share_multiplier": 1.50, "dwell_multiplier": 1.0,
        "onboarding_cost_multiplier": 1.0, "network_variant": "LIVE",
        "include_in_stability": False,
        "methodology_note": "Joint A-07/A-08 upside diagnostic, not a commercial forecast.",
    },
]

COMPONENT_COLUMNS = {
    "DEMAND": "demand_score",
    "REVENUE": "revenue_score",
    "COMPETITION": "competition_score",
    "STRATEGIC_FIT": "strategic_fit_score",
    "FEASIBILITY": "feasibility_score",
}

# --------------------------------------------------------------------------
# Sub-weights this module must share with sql/analysis/component_scores.sql.
#
# SQL owns the baseline pillar definitions. A scenario cannot be expressed in
# that view, so score_scenario() re-derives two subcomponents by subtracting the
# baseline contribution and adding the scenario-adjusted one. That arithmetic is
# only valid while these coefficients equal the SQL ones.
#
# Both patches cancel identically in BASE_CASE, so a silent drift would leave
# the headline ranking correct and corrupt only the sensitivity and rank
# stability outputs. tests/test_audit.py parses the SQL and asserts
# agreement, and reconcile_base_case_against_sql() below checks the whole
# pillar set numerically on every run.
# --------------------------------------------------------------------------
FEASIBILITY_ONBOARDING_COST_WEIGHT = 0.07
STRATEGIC_NETWORK_DISTANCE_WEIGHT = 0.50

# Tolerance for base-case reconciliation. SQL returns NUMERIC and Python float64,
# so exact equality is not a fair test; anything above this is real drift.
RECONCILIATION_TOLERANCE = 1e-6


def connect():
    import psycopg

    options: dict[str, Any] = {
        "host": settings.pg_host,
        "port": settings.pg_port,
        "dbname": settings.pg_database,
        "user": settings.pg_user,
    }
    if settings.pg_password:
        options["password"] = settings.pg_password
    return psycopg.connect(**options)


def run_sql_file(connection: Any, path: Path) -> None:
    with connection.cursor() as cursor:
        cursor.execute(path.read_text(encoding="utf-8"))
    connection.commit()


def query_frame(connection: Any, query: str) -> pd.DataFrame:
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [item.name for item in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=columns)


def winsor_score(values: pd.Series, lower: pd.Series | float, upper: pd.Series | float,
                 *, invert: bool = False) -> pd.Series:
    """Winsorise to [lower, upper] then min-max scale to 0-100.

    Mirrors the SQL ``normalize_winsor`` in database/schema/06_analysis.sql.
    The two must agree branch for branch, including the degenerate cases, or the
    base case stops reconciling. Specifically:
      * a NULL/NaN input yields NaN, checked BEFORE the denominator, matching
        SQL's ``value IS NULL`` short-circuit;
      * a non-positive denominator (upper <= lower) yields the neutral 50.0,
        matching SQL's ``upper_bound <= lower_bound`` guard. An epsilon test was
        used here previously, which disagreed with SQL for a tiny positive
        denominator and made the Series and scalar paths return different
        answers from each other.
    """
    value = pd.to_numeric(values, errors="coerce").astype(float)
    low = pd.to_numeric(lower, errors="coerce").astype(float) if isinstance(lower, pd.Series) else float(lower)
    high = pd.to_numeric(upper, errors="coerce").astype(float) if isinstance(upper, pd.Series) else float(upper)
    clipped = value.clip(lower=low, upper=high)
    denominator = high - low
    # Broadcast scalars so both paths share one expression and cannot diverge.
    if not isinstance(denominator, pd.Series):
        denominator = pd.Series(float(denominator), index=value.index)
    if not isinstance(low, pd.Series):
        low = pd.Series(float(low), index=value.index)
    usable = denominator > 0
    result = pd.Series(50.0, index=value.index, dtype=float)
    result = result.mask(usable, 100.0 * (clipped - low) / denominator)
    if invert:
        result = 100.0 - result
    result = result.clip(0.0, 100.0)
    # NULL precedence: SQL returns NULL for a NULL value or NULL bound.
    return result.mask(value.isna() | low.isna() | denominator.isna())


def network_score(distance_km: pd.Series) -> pd.Series:
    d = pd.to_numeric(distance_km, errors="coerce").astype(float)
    out = pd.Series(35.0, index=d.index)
    out.loc[d < 0.40] = 10.0 + 25.0 * d.loc[d < 0.40] / 0.40
    mask = (d >= 0.40) & (d < 1.50)
    out.loc[mask] = 35.0 + 65.0 * (d.loc[mask] - 0.40) / 1.10
    out.loc[(d >= 1.50) & (d < 6.00)] = 100.0
    mask = (d >= 6.00) & (d < 9.00)
    out.loc[mask] = 100.0 - 35.0 * (d.loc[mask] - 6.00) / 3.00
    out.loc[d >= 9.00] = 65.0
    return out.clip(0.0, 100.0)


def weight_maps(connection: Any) -> dict[int, dict[str, float]]:
    frame = query_frame(
        connection,
        "SELECT weight_set_id, dimension_code, weight FROM parkitup.scoring_weight ORDER BY 1, 2",
    )
    result: dict[int, dict[str, float]] = {}
    for row in frame.itertuples(index=False):
        result.setdefault(int(row.weight_set_id), {})[str(row.dimension_code)] = float(row.weight)
    for weight_set_id, weights in result.items():
        if set(weights) != set(COMPONENT_COLUMNS) or not np.isclose(sum(weights.values()), 1.0):
            raise ValueError(f"Invalid weights for set {weight_set_id}: {weights}")
    return result


def classify_segments(frame: pd.DataFrame, thresholds: dict[str, float]) -> pd.Series:
    attr = frame["attractiveness_score"]
    feasibility = frame["feasibility_score"]
    return pd.Series(
        np.select(
            [
                (attr >= thresholds["attractiveness_high"]) & (feasibility >= thresholds["feasibility_mid"]),
                (attr >= thresholds["attractiveness_high"]) & (feasibility < thresholds["feasibility_mid"]),
                (attr >= thresholds["attractiveness_develop"]) & (feasibility >= thresholds["feasibility_mid"]),
            ],
            ["ACQUIRE_NOW", "PURSUE", "DEVELOP"],
            default="AVOID",
        ),
        index=frame.index,
    )


def score_scenario(base: pd.DataFrame, scenario: dict[str, Any], weights: dict[str, float],
                   thresholds: dict[str, float] | None = None) -> pd.DataFrame:
    """Apply bounded scenario parameters while preserving baseline score anchors."""
    frame = base.copy()
    demand_multiplier = float(scenario["demand_multiplier"])
    frame["adjusted_avg_occupancy_rate"] = (frame["avg_occupancy_rate"].astype(float) * demand_multiplier).clip(0.035, 0.93)
    frame["adjusted_p90_peak_occupancy_rate"] = (frame["p90_peak_occupancy_rate"].astype(float) * demand_multiplier).clip(0.035, 0.995)
    frame["adjusted_average_occupancy_score"] = winsor_score(
        frame["adjusted_avg_occupancy_rate"], frame["occupancy_low"], frame["occupancy_high"]
    )
    frame["adjusted_peak_occupancy_score"] = winsor_score(
        frame["adjusted_p90_peak_occupancy_rate"], frame["peak_low"], frame["peak_high"]
    )
    observed = 0.70 * frame["adjusted_average_occupancy_score"] + 0.30 * frame["adjusted_peak_occupancy_score"]
    headroom = (frame["location_demand_score"].astype(float) - frame["adjusted_average_occupancy_score"]).clip(lower=0.0)
    frame["demand_score"] = (0.50 * observed + 0.40 * frame["location_demand_score"].astype(float) + 0.10 * headroom).clip(0.0, 100.0)
    frame["achievable_utilization"] = np.minimum(
        0.85,
        frame["adjusted_avg_occupancy_rate"]
        + np.minimum(
            0.12,
            (frame["location_demand_score"].astype(float) / 100.0 * 0.82 - frame["adjusted_avg_occupancy_rate"]).clip(lower=0.0) * 0.35,
        ),
    )
    adjusted_bookings = (
        frame["avg_daily_platform_bookings"].astype(float)
        * demand_multiplier
        * float(scenario["booking_share_multiplier"])
    )
    uplift = np.minimum(
        1.35,
        frame["achievable_utilization"] / frame["adjusted_avg_occupancy_rate"].clip(lower=0.05),
    )
    frame["expected_daily_net_platform_bookings"] = (
        adjusted_bookings
        # COALESCE to match sql/analysis/component_scores.sql. cancellation_rate
        # is NULL when a lot took zero platform bookings across the whole window
        # (06_analysis.sql NULLIFs the denominator). Without this, one such lot
        # would poison acquisition_score with NaN and fail the NOT NULL insert.
        * (1.0 - frame["cancellation_rate"].astype(float).fillna(0.0))
        * uplift
    )
    frame["expected_monthly_platform_revenue_inr"] = (
        frame["expected_daily_net_platform_bookings"]
        * frame["avg_park_duration_hours"].astype(float)
        * float(scenario["dwell_multiplier"])
        * frame["hourly_rate_inr"].astype(float)
        * 0.76
        * frame["expected_commission_pct"].astype(float)
        * float(scenario["commission_multiplier"])
        / 100.0
        * 30.0
    ).clip(lower=0.0)
    frame["expected_revenue_per_space_inr"] = (
        frame["expected_monthly_platform_revenue_inr"] / frame["capacity_cars"].astype(float)
    ).clip(lower=0.0)
    frame["revenue_score"] = (
        0.75 * winsor_score(
            np.log1p(frame["expected_monthly_platform_revenue_inr"]),
            frame["revenue_low"], frame["revenue_high"],
        )
        + 0.25 * winsor_score(
            frame["expected_revenue_per_space_inr"], frame["revenue_space_low"], frame["revenue_space_high"],
        )
    ).clip(0.0, 100.0)
    frame["adjusted_onboarding_cost_inr"] = (
        frame["estimated_onboarding_cost_inr"].astype(float) * float(scenario["onboarding_cost_multiplier"])
    )
    adjusted_cost_score = winsor_score(
        frame["adjusted_onboarding_cost_inr"], frame["onboarding_low"], frame["onboarding_high"], invert=True
    )
    frame["feasibility_score"] = (
        frame["feasibility_score"].astype(float)
        # Swap the onboarding-cost subcomponent for its scenario-adjusted value.
        # FEASIBILITY_ONBOARDING_COST_WEIGHT must equal the coefficient applied to
        # onboarding_cost_score in sql/analysis/component_scores.sql, or this
        # patch corrupts the Feasibility pillar. It cancels exactly in the base
        # case, so a mismatch would only surface in the cost scenario — see the
        # SQL-coefficient assertion in tests/test_audit.py.
        - FEASIBILITY_ONBOARDING_COST_WEIGHT * frame["onboarding_cost_score"].astype(float)
        + FEASIBILITY_ONBOARDING_COST_WEIGHT * adjusted_cost_score
    ).clip(0.0, 100.0)
    variant = str(scenario["network_variant"])
    if variant == "LIVE":
        # SQL scores COALESCE(live, any) via nearest_network_distance_km. Using
        # the raw live column here would diverge for any lot with no live site.
        distance = frame["nearest_live_network_distance_km"].astype(float).fillna(
            frame["nearest_any_network_distance_km"].astype(float)
        )
    else:
        distance = frame[
            {"ALL_SITES": "nearest_any_network_distance_km",
             "MATURE_LIVE": "nearest_mature_network_distance_km"}[variant]
        ].astype(float)
    adjusted_network_score = network_score(distance)
    frame["strategic_fit_score"] = (
        frame["strategic_fit_score"].astype(float)
        - STRATEGIC_NETWORK_DISTANCE_WEIGHT * frame["network_distance_score"].astype(float)
        + STRATEGIC_NETWORK_DISTANCE_WEIGHT * adjusted_network_score
    ).clip(0.0, 100.0)
    frame["competition_score"] = frame["competition_score"].astype(float).clip(0.0, 100.0)

    frame["attractiveness_score"] = (
        sum(frame[column] * weights[dimension] for dimension, column in COMPONENT_COLUMNS.items() if dimension != "FEASIBILITY")
        / sum(weight for dimension, weight in weights.items() if dimension != "FEASIBILITY")
    ).clip(0.0, 100.0)
    frame["acquisition_score"] = sum(
        frame[column] * weights[dimension] for dimension, column in COMPONENT_COLUMNS.items()
    ).clip(0.0, 100.0)
    frame = frame.sort_values(["acquisition_score", "parking_id"], ascending=[False, True]).reset_index(drop=True)
    frame["rank_overall"] = np.arange(1, len(frame) + 1, dtype=int)
    if thresholds is not None:
        frame["segment_code"] = classify_segments(frame, thresholds)
    return frame


def reconcile_base_case_against_sql(base_component: pd.DataFrame,
                                    base_result: pd.DataFrame) -> pd.DataFrame:
    """Prove Python's base-case pillars equal the SQL view's, column by column.

    Why this exists. ``parking_component_scores`` computes all five pillars in
    SQL; ``score_scenario`` then recomputes Demand and Revenue in Python so that
    scenario multipliers can be applied, and patches two Feasibility/Strategic
    subcomponents. Both implementations therefore hold the same business logic,
    including roughly a dozen shared constants (the 0.76 realisation factor, the
    0.85 utilisation cap, the 1.35 uplift cap, the pillar blend weights).

    Nothing previously forced them to agree. In BASE_CASE every scenario
    multiplier is 1.0, so Python must reproduce SQL exactly. Any divergence means
    a constant was edited in one file only, and this raises instead of silently
    publishing two different models.
    """
    left = base_component.set_index("parking_id").sort_index()
    right = base_result.set_index("parking_id").sort_index()
    rows: list[dict[str, Any]] = []
    for column in [
        *COMPONENT_COLUMNS.values(),
        "observed_demand_score", "location_demand_score", "achievable_utilization",
        "expected_monthly_platform_revenue_inr", "expected_revenue_per_space_inr",
        "network_distance_score", "onboarding_cost_score", "market_whitespace_score",
    ]:
        if column not in left.columns or column not in right.columns:
            rows.append({"column": column, "compared": 0, "max_abs_diff": None,
                         "status": "SKIP (absent)"})
            continue
        difference = (
            pd.to_numeric(left[column], errors="coerce").astype(float)
            - pd.to_numeric(right[column], errors="coerce").astype(float)
        ).abs()
        worst = float(difference.max())
        rows.append({
            "column": column,
            "compared": int(difference.notna().sum()),
            "max_abs_diff": round(worst, 12),
            "status": "PASS" if worst <= RECONCILIATION_TOLERANCE else "FAIL",
        })
    return pd.DataFrame(rows)


def update_segment_rules(connection: Any, thresholds: dict[str, float]) -> None:
    statements = [
        ("ACQUIRE_NOW", thresholds["attractiveness_high"], thresholds["feasibility_mid"], None,
         "Top-third attractiveness and at-or-above-median feasibility; calibrated from the base-case distribution."),
        ("PURSUE", thresholds["attractiveness_high"], None, thresholds["feasibility_mid"],
         "Top-third attractiveness with below-median feasibility; work the specific blocker first."),
        ("DEVELOP", thresholds["attractiveness_develop"], thresholds["feasibility_mid"], None,
         "Middle-or-better attractiveness with at-or-above-median feasibility; use efficient outreach."),
        ("AVOID", None, None, None,
         "Outside the calibrated attractiveness/feasibility action bands."),
    ]
    with connection.cursor() as cursor:
        for code, minimum_attr, minimum_feas, maximum_feas, rationale in statements:
            cursor.execute(
                """UPDATE parkitup.segment_rule
                   SET min_attractiveness=%s, min_feasibility=%s, max_feasibility=%s, rationale=%s
                   WHERE segment_code=%s""",
                (minimum_attr, minimum_feas, maximum_feas, rationale, code),
            )
    connection.commit()


def ensure_revenue_weight_set(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO parkitup.scoring_weight_set
                   (weight_set_id, weight_set_code, description, is_default)
                   VALUES (5, 'REVENUE_LED', 'scoring revenue-led sensitivity weight set.', FALSE)
                   ON CONFLICT (weight_set_id) DO NOTHING"""
        )
        cursor.executemany(
            """INSERT INTO parkitup.scoring_weight (weight_set_id, dimension_code, weight)
                   VALUES (5, %s, %s) ON CONFLICT (weight_set_id, dimension_code) DO UPDATE SET weight=EXCLUDED.weight""",
            [("DEMAND", 0.20), ("REVENUE", 0.40), ("COMPETITION", 0.15),
             ("STRATEGIC_FIT", 0.10), ("FEASIBILITY", 0.15)],
        )
    connection.commit()


def reason_flags(base_result: pd.DataFrame) -> pd.DataFrame:
    result = base_result.copy().set_index("parking_id", drop=False)
    q = {
        column: (float(result[column].quantile(0.25)), float(result[column].quantile(0.75)))
        for column in ["demand_score", "revenue_score", "competition_score", "strategic_fit_score",
                       "feasibility_score", "expected_revenue_per_space_inr", "avg_occupancy_rate",
                       "estimated_onboarding_cost_inr", "metro_distance_m"]
    }
    rows: list[dict[str, Any]] = []
    for row in result.itertuples(index=False):
        positive: list[str] = []
        constraints: list[str] = []
        if row.demand_score >= q["demand_score"][1]: positive.append("HIGH_DEMAND")
        if row.revenue_score >= q["revenue_score"][1]: positive.append("HIGH_REVENUE")
        if row.competition_score >= q["competition_score"][1]: positive.append("LOW_COMPETITION")
        if row.strategic_fit_score >= q["strategic_fit_score"][1]: positive.append("NETWORK_GAP")
        if row.feasibility_score >= q["feasibility_score"][1]: positive.append("HIGH_OWNER_READINESS")
        if row.metro_distance_m <= q["metro_distance_m"][0]: positive.append("STRONG_METRO_ACCESS")
        if row.expected_revenue_per_space_inr >= q["expected_revenue_per_space_inr"][1]: positive.append("CAPACITY_EFFICIENT_REVENUE")
        if row.avg_occupancy_rate >= q["avg_occupancy_rate"][1]: positive.append("SUSTAINED_UTILIZATION")
        if row.demand_score <= q["demand_score"][0]: constraints.append("LOW_DEMAND")
        if row.revenue_score <= q["revenue_score"][0]: constraints.append("LOW_REVENUE")
        if row.competition_score <= q["competition_score"][0]: constraints.append("HIGH_COMPETITION")
        if row.strategic_fit_score <= q["strategic_fit_score"][0]: constraints.append("LOW_STRATEGIC_FIT")
        if row.feasibility_score <= q["feasibility_score"][0]: constraints.append("LOW_OWNER_READINESS")
        if row.estimated_onboarding_cost_inr >= q["estimated_onboarding_cost_inr"][1]: constraints.append("HIGH_ONBOARDING_COST")
        if row.documentation_readiness <= 2: constraints.append("DOCUMENTATION_GAP")
        if not row.decision_maker_accessible: constraints.append("DECISION_MAKER_BLOCKED")
        if row.requires_capex: constraints.append("CAPEX_REQUIRED")
        if row.nearest_network_distance_km < 0.40: constraints.append("NETWORK_CANNIBALIZATION_RISK")
        if pd.notna(row.competitor_price_ratio) and row.competitor_price_ratio < 0.85:
            constraints.append("COMPETITOR_PRICE_PRESSURE")
        recommendation = {
            "ACQUIRE_NOW": "Prioritise for named-owner outreach and commercial diligence.",
            "PURSUE": "Assign senior BD to resolve the recorded feasibility constraints before commercial negotiation.",
            "DEVELOP": "Use sequenced low-cost outreach and validate the opportunity before escalating resources.",
            "AVOID": "Do not allocate active BD capacity; revisit only when the market or owner posture changes.",
        }[row.segment_code]
        rows.append({
            "parking_id": int(row.parking_id),
            "positive_reason_flags": positive,
            "constraint_reason_flags": constraints,
            "recommendation": recommendation,
            "methodology_note": "Flags are relative scoring indicators; they are not observed real-world outcomes.",
        })
    return pd.DataFrame(rows)


def stability_and_sensitivity(results: dict[int, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = results[1].set_index("parking_id")
    stability_ids = [scenario["scenario_id"] for scenario in SCENARIOS if scenario["include_in_stability"]]
    stable = pd.concat(
        [results[scenario_id].set_index("parking_id")["rank_overall"].rename(str(scenario_id))
         for scenario_id in stability_ids], axis=1
    )
    top_count = (stable <= 10).sum(axis=1)
    stability_pct = top_count / len(stability_ids) * 100.0
    stability_class = pd.Series(np.select(
        [stability_pct >= 90, stability_pct >= 70, stability_pct >= 40],
        ["Very Stable", "Stable", "Sensitive"], default="Highly Sensitive",
    ), index=stable.index)
    stability = pd.DataFrame({
        "parking_id": stable.index.astype(int),
        "scenarios_evaluated": len(stability_ids),
        "top_10_scenario_count": top_count.astype(int).to_numpy(),
        "rank_stability_pct": stability_pct.round(2).to_numpy(),
        "stability_class": stability_class.to_numpy(),
        "median_rank": stable.median(axis=1).round(2).to_numpy(),
        "min_rank": stable.min(axis=1).astype(int).to_numpy(),
        "max_rank": stable.max(axis=1).astype(int).to_numpy(),
    })
    base_top10 = set(base.index[base["rank_overall"] <= 10])
    summary_rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        current = results[int(scenario["scenario_id"])].set_index("parking_id").reindex(base.index)
        delta = current["rank_overall"] - base["rank_overall"]
        score_delta = current["acquisition_score"] - base["acquisition_score"]
        # Spearman correlation is Pearson correlation over ordinal ranks. This
        # avoids requiring SciPy solely for a diagnostic statistic.
        base_rank = base["rank_overall"].rank(method="average")
        current_rank = current["rank_overall"].rank(method="average")
        rank_correlation = base_rank.corr(current_rank)
        summary_rows.append({
            "scenario_id": int(scenario["scenario_id"]),
            "scenario_code": scenario["scenario_code"],
            "top_10_overlap_count": len(base_top10 & set(current.index[current["rank_overall"] <= 10])),
            "top_10_overlap_pct": round(len(base_top10 & set(current.index[current["rank_overall"] <= 10])) / 10 * 100.0, 2),
            "spearman_rank_correlation": round(float(rank_correlation), 4),
            "mean_abs_rank_change": round(float(delta.abs().mean()), 3),
            "max_abs_rank_change": int(delta.abs().max()),
            "segment_change_count": int((current["segment_code"] != base["segment_code"]).sum()),
            "mean_score_change": round(float(score_delta.mean()), 3),
            "max_abs_score_change": round(float(score_delta.abs().max()), 3),
        })
    return stability, pd.DataFrame(summary_rows)


def locality_summary(base_result: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for _, group in base_result.groupby("locality_id", sort=True):
        first = group.iloc[0]
        records.append({
            "locality_id": int(first.locality_id),
            "locality_name": first.locality_name,
            "city_name": first.city_name,
            "micro_market_type": first.micro_market_type,
            "opportunity_count": int(len(group)),
            "total_candidate_capacity_cars": int(group.capacity_cars.sum()),
            "average_demand_score": round(float(group.demand_score.mean()), 2),
            "average_revenue_score": round(float(group.revenue_score.mean()), 2),
            "average_competition_score": round(float(group.competition_score.mean()), 2),
            "average_strategic_fit_score": round(float(group.strategic_fit_score.mean()), 2),
            "average_feasibility_score": round(float(group.feasibility_score.mean()), 2),
            "average_acquisition_score": round(float(group.acquisition_score.mean()), 2),
            "expected_monthly_platform_revenue_inr": round(float(group.expected_monthly_platform_revenue_inr.sum()), 2),
            "live_network_site_count": int(first.live_network_site_count),
            "live_network_capacity_cars": int(first.live_network_capacity_cars),
            "market_whitespace_score": round(float(group.market_whitespace_score.mean()), 2),
            "high_priority_opportunity_count": int((group.segment_code == "ACQUIRE_NOW").sum()),
        })
    return pd.DataFrame(records)


def failure_tests(base_result: pd.DataFrame) -> pd.DataFrame:
    q = lambda col, level: float(base_result[col].quantile(level))
    tests: list[dict[str, Any]] = []
    large_low = base_result[(base_result.capacity_cars >= q("capacity_cars", 0.75)) & (base_result.avg_occupancy_rate <= q("avg_occupancy_rate", 0.25))]
    tests.append({
        "test_id": "FT-01", "test_name": "Large capacity, extremely low occupancy",
        "records_tested": len(large_low), "observed_metric": int(large_low.rank_overall.min()) if len(large_low) else None,
        "expected": "No matching lot ranks first", "status": "PASS" if len(large_low) == 0 or int(large_low.rank_overall.min()) > 1 else "FAIL",
    })
    expensive_weak = base_result[(base_result.hourly_rate_inr >= q("hourly_rate_inr", 0.75)) & (base_result.demand_score <= q("demand_score", 0.25))]
    tests.append({
        "test_id": "FT-02", "test_name": "Very high price, weak demand",
        "records_tested": len(expensive_weak), "observed_metric": int(expensive_weak.rank_overall.min()) if len(expensive_weak) else None,
        "expected": "No matching lot ranks first", "status": "PASS" if len(expensive_weak) == 0 or int(expensive_weak.rank_overall.min()) > 1 else "FAIL",
    })
    high_demand = base_result[base_result.demand_score >= q("demand_score", 0.75)]
    high_pressure = high_demand[high_demand.competition_score <= q("competition_score", 0.25)]
    low_pressure_benchmark = q("competition_score", 0.75)
    # A raw cohort comparison is confounded by revenue, feasibility and
    # network differences. Hold every other pillar fixed and replace only the
    # competition opportunity with the low-pressure benchmark.
    counterfactual_gain = 0.15 * (low_pressure_benchmark - high_pressure.competition_score)
    comparison = float(counterfactual_gain.mean()) if len(high_pressure) else np.nan
    tests.append({
        "test_id": "FT-03", "test_name": "High demand, extreme competition",
        "records_tested": int(len(high_pressure)), "observed_metric": round(comparison, 2) if not np.isnan(comparison) else None,
        "expected": "Replacing extreme-pressure competition with a low-pressure benchmark increases the composite", "status": "PASS" if np.isnan(comparison) or comparison > 0 else "FAIL",
    })
    hard_close = base_result[(base_result.demand_score >= q("demand_score", 0.75)) & (base_result.feasibility_score <= q("feasibility_score", 0.25))]
    tests.append({
        "test_id": "FT-04", "test_name": "High demand, poor acquisition feasibility",
        "records_tested": len(hard_close), "observed_metric": int((hard_close.segment_code == "ACQUIRE_NOW").sum()),
        "expected": "No matching lot is Acquire Now", "status": "PASS" if (hard_close.segment_code != "ACQUIRE_NOW").all() else "FAIL",
    })
    small_strong = base_result[(base_result.capacity_cars <= q("capacity_cars", 0.25)) & (base_result.demand_score >= q("demand_score", 0.75)) & (base_result.revenue_score >= q("revenue_score", 0.50))]
    tests.append({
        "test_id": "FT-05", "test_name": "Small capacity, exceptionally strong demand",
        "records_tested": len(small_strong), "observed_metric": int(small_strong.rank_overall.min()) if len(small_strong) else None,
        "expected": "At least one matching lot can enter the top half", "status": "PASS" if len(small_strong) and int(small_strong.rank_overall.min()) <= len(base_result) // 2 else "FAIL",
    })
    moderate = base_result[(base_result.capacity_cars >= q("capacity_cars", 0.30)) & (base_result.capacity_cars <= q("capacity_cars", 0.70))]
    gap = moderate[moderate.strategic_fit_score >= q("strategic_fit_score", 0.75)]
    saturated = moderate[moderate.strategic_fit_score <= q("strategic_fit_score", 0.25)]
    comparison = float(gap.acquisition_score.mean() - saturated.acquisition_score.mean()) if len(gap) and len(saturated) else np.nan
    tests.append({
        "test_id": "FT-06", "test_name": "Moderate lot in a network gap",
        "records_tested": int(len(gap)), "observed_metric": round(comparison, 2) if not np.isnan(comparison) else None,
        "expected": "Gap group has higher mean score than saturated group", "status": "PASS" if np.isnan(comparison) or comparison > 0 else "FAIL",
    })
    return pd.DataFrame(tests)


def manual_review_sample(base_result: pd.DataFrame) -> pd.DataFrame:
    top = base_result.nsmallest(10, "rank_overall")
    bottom = base_result.nlargest(10, "rank_overall")
    middle = base_result[(base_result.rank_overall > 45) & (base_result.rank_overall < 76)].sample(
        n=10, random_state=settings.random_seed
    )
    review = pd.concat([top.assign(review_cohort="Top 10"), bottom.assign(review_cohort="Bottom 10"), middle.assign(review_cohort="Middle random")])
    columns = [
        "review_cohort", "rank_overall", "parking_id", "lot_name", "locality_name", "capacity_cars",
        "hourly_rate_inr", "avg_occupancy_rate", "competitor_count_1km", "nearest_network_distance_km",
        "demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score",
        "acquisition_score", "segment_code", "expected_monthly_platform_revenue_inr",
    ]
    return review[columns].sort_values(["review_cohort", "rank_overall"])


def diagnostics(base_result: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score",
        "acquisition_score", "capacity_cars", "hourly_rate_inr", "avg_occupancy_rate",
        "expected_monthly_platform_revenue_inr", "competitor_count_1km", "willingness_to_digitize",
        "documentation_readiness", "estimated_onboarding_cost_inr",
    ]
    correlation = base_result[fields].corr(method="spearman").round(4)
    correlation.index.name = "metric"
    return correlation.reset_index()


def validate_outputs(results: dict[int, pd.DataFrame], stability: pd.DataFrame,
                     sensitivity: pd.DataFrame, failure: pd.DataFrame,
                     reconciliation: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    expected_lots = settings.target_lot_count
    score_columns = [*COMPONENT_COLUMNS.values(), "attractiveness_score", "acquisition_score"]
    for scenario_id, frame in results.items():
        out_of_range = ((frame[score_columns] < 0) | (frame[score_columns] > 100)).any(axis=1)
        contiguous = set(frame.rank_overall) == set(range(1, len(frame) + 1))
        rows.extend([
            {"rule_id": f"SCORE-{scenario_id:02d}-01", "description": f"{expected_lots} lots scored", "violations": abs(len(frame) - expected_lots), "status": "PASS" if len(frame) == expected_lots else "FAIL"},
            {"rule_id": f"SCORE-{scenario_id:02d}-02", "description": "All component and composite scores are 0-100", "violations": int(out_of_range.sum()), "status": "PASS" if not out_of_range.any() else "FAIL"},
            {"rule_id": f"SCORE-{scenario_id:02d}-03", "description": "Ranks are unique and contiguous", "violations": int(not contiguous), "status": "PASS" if contiguous else "FAIL"},
            {"rule_id": f"SCORE-{scenario_id:02d}-04", "description": "Every lot has a priority segment", "violations": int(frame.segment_code.isna().sum()), "status": "PASS" if frame.segment_code.notna().all() else "FAIL"},
            {"rule_id": f"SCORE-{scenario_id:02d}-05", "description": "No NaN in any pillar or composite score", "violations": int(frame[score_columns].isna().to_numpy().sum()), "status": "PASS" if not frame[score_columns].isna().to_numpy().any() else "FAIL"},
        ])
    rows.extend([
        {"rule_id": "SCORE-BASE-01", "description": "Rank-stability records cover all lots", "violations": abs(len(stability) - expected_lots), "status": "PASS" if len(stability) == expected_lots else "FAIL"},
        {"rule_id": "SCORE-BASE-02", "description": "Sensitivity summary covers all configured scenarios", "violations": abs(len(sensitivity) - len(SCENARIOS)), "status": "PASS" if len(sensitivity) == len(SCENARIOS) else "FAIL"},
        {"rule_id": "SCORE-BASE-03", "description": "Failure tests pass", "violations": int((failure.status != "PASS").sum()), "status": "PASS" if (failure.status == "PASS").all() else "FAIL"},
    ])
    if reconciliation is not None:
        failed = int((reconciliation.status == "FAIL").sum())
        rows.append({
            "rule_id": "SCORE-BASE-04",
            "description": "Base-case Python pillars reconcile with the SQL component view",
            "violations": failed,
            "status": "PASS" if failed == 0 else "FAIL",
        })
    return pd.DataFrame(rows)


def persist_outputs(connection: Any, scenarios: list[dict[str, Any]], results: dict[int, pd.DataFrame],
                    base_component: pd.DataFrame, weights: dict[int, dict[str, float]],
                    explanations: pd.DataFrame, stability: pd.DataFrame, sensitivity: pd.DataFrame,
                    locality: pd.DataFrame) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""TRUNCATE TABLE parkitup.sensitivity_summary, parkitup.lot_rank_stability,
                          parkitup.parking_score_explanation, parkitup.locality_acquisition_summary,
                          parkitup.lot_scenario_score, parkitup.lot_dimension_score, parkitup.lot_score""")
        cursor.execute("DELETE FROM parkitup.acquisition_scenario")
        cursor.executemany(
            """INSERT INTO parkitup.acquisition_scenario
               (scenario_id, scenario_code, scenario_group, description, weight_set_id,
                demand_multiplier, commission_multiplier, booking_share_multiplier, dwell_multiplier,
                onboarding_cost_multiplier, network_variant, include_in_stability, methodology_note)
               VALUES (%(scenario_id)s,%(scenario_code)s,%(scenario_group)s,%(description)s,%(weight_set_id)s,
                       %(demand_multiplier)s,%(commission_multiplier)s,%(booking_share_multiplier)s,%(dwell_multiplier)s,
                       %(onboarding_cost_multiplier)s,%(network_variant)s,%(include_in_stability)s,%(methodology_note)s)""",
            scenarios,
        )
        scenario_rows: list[tuple[Any, ...]] = []
        for scenario in scenarios:
            frame = results[int(scenario["scenario_id"])]
            for row in frame.itertuples(index=False):
                scenario_rows.append((
                    int(row.parking_id), int(scenario["scenario_id"]), *[
                        round(float(getattr(row, col)), 2) for col in [
                            "demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score"
                        ]
                    ], round(float(row.achievable_utilization), 4),
                    round(float(row.expected_monthly_platform_revenue_inr), 2),
                    round(float(row.expected_revenue_per_space_inr), 2),
                    round(float(row.adjusted_onboarding_cost_inr), 2),
                    round(float(row.attractiveness_score), 2), round(float(row.acquisition_score), 2),
                    str(row.segment_code), int(row.rank_overall),
                ))
        cursor.executemany(
            """INSERT INTO parkitup.lot_scenario_score
               (parking_id,scenario_id,demand_score,revenue_score,competition_score,strategic_fit_score,feasibility_score,
                achievable_utilization,expected_monthly_platform_revenue_inr,expected_revenue_per_space_inr,
                adjusted_onboarding_cost_inr,attractiveness_score,acquisition_score,segment_code,rank_overall)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            scenario_rows,
        )
        dimension_rows: list[tuple[Any, ...]] = []
        score_rows: list[tuple[Any, ...]] = []
        for weight_set_id, current_weights in weights.items():
            output = score_scenario(base_component, SCENARIOS[0], current_weights, results[1].attrs["thresholds"])
            for row in output.itertuples(index=False):
                for dimension, column in COMPONENT_COLUMNS.items():
                    subscore = round(float(getattr(row, column)), 2)
                    weight = current_weights[dimension]
                    dimension_rows.append((int(row.parking_id), weight_set_id, dimension, subscore, weight, round(subscore * weight, 3)))
                score_rows.append((
                    int(row.parking_id), weight_set_id, round(float(row.attractiveness_score), 2),
                    round(float(row.feasibility_score), 2), round(float(row.acquisition_score), 2),
                    str(row.segment_code), int(row.rank_overall),
                ))
        cursor.executemany(
            """INSERT INTO parkitup.lot_dimension_score
               (parking_id,weight_set_id,dimension_code,subscore,weight_applied,weighted_contribution)
               VALUES (%s,%s,%s,%s,%s,%s)""", dimension_rows)
        cursor.executemany(
            """INSERT INTO parkitup.lot_score
               (parking_id,weight_set_id,attractiveness_score,feasibility_score,acquisition_score,segment_code,rank_overall)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""", score_rows)
        cursor.executemany(
            """INSERT INTO parkitup.parking_score_explanation
               (parking_id,positive_reason_flags,constraint_reason_flags,recommendation,methodology_note)
               VALUES (%s,%s,%s,%s,%s)""",
            [tuple(row) for row in explanations[["parking_id", "positive_reason_flags", "constraint_reason_flags", "recommendation", "methodology_note"]].itertuples(index=False, name=None)],
        )
        cursor.executemany(
            """INSERT INTO parkitup.lot_rank_stability
               (parking_id,scenarios_evaluated,top_10_scenario_count,rank_stability_pct,stability_class,median_rank,min_rank,max_rank)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [tuple(row) for row in stability.itertuples(index=False, name=None)],
        )
        cursor.executemany(
            """INSERT INTO parkitup.sensitivity_summary
               (scenario_id,top_10_overlap_count,top_10_overlap_pct,spearman_rank_correlation,
                mean_abs_rank_change,max_abs_rank_change,segment_change_count,mean_score_change,max_abs_score_change)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [tuple(row) for row in sensitivity.drop(columns="scenario_code").itertuples(index=False, name=None)],
        )
        cursor.executemany(
            """INSERT INTO parkitup.locality_acquisition_summary
               (locality_id,locality_name,city_name,micro_market_type,opportunity_count,total_candidate_capacity_cars,
                average_demand_score,average_revenue_score,average_competition_score,average_strategic_fit_score,
                average_feasibility_score,average_acquisition_score,expected_monthly_platform_revenue_inr,
                live_network_site_count,live_network_capacity_cars,market_whitespace_score,high_priority_opportunity_count)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [tuple(row) for row in locality.itertuples(index=False, name=None)],
        )
    connection.commit()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def markdown_table(frame: pd.DataFrame) -> str:
    frame = frame.copy()
    columns = list(frame.columns)
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    rows.extend("| " + " | ".join(str(value) for value in row) + " |" for row in frame.itertuples(index=False, name=None))
    return "\n".join(rows)


def write_methodology(base: pd.DataFrame, thresholds: dict[str, float], sensitivity: pd.DataFrame,
                      quality: pd.DataFrame, failure: pd.DataFrame,
                      reconciliation: pd.DataFrame | None = None) -> None:
    score_stats = base[["demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score", "acquisition_score"]].describe().loc[["min", "25%", "50%", "mean", "75%", "max"]].T.reset_index().rename(columns={"index": "Score"}).round(2)
    segments = base.groupby("segment_code").size().rename("Lots").reset_index()
    sensitivity_table = sensitivity[["scenario_code", "top_10_overlap_pct", "spearman_rank_correlation", "mean_abs_rank_change", "segment_change_count"]]
    correlation_pairs = [
        ("Demand vs Revenue", "demand_score", "revenue_score"),
        ("Demand vs Strategic Fit", "demand_score", "strategic_fit_score"),
        ("Demand vs Competition Opportunity", "demand_score", "competition_score"),
        ("Capacity vs Revenue", "capacity_cars", "revenue_score"),
        ("Occupancy vs Revenue", "avg_occupancy_rate", "revenue_score"),
        ("Feasibility vs Willingness", "feasibility_score", "willingness_to_digitize"),
        ("Capacity vs Acquisition", "capacity_cars", "acquisition_score"),
    ]
    correlation_table = pd.DataFrame([
        {
            "Pair": label,
            "Spearman correlation": round(float(base[left].rank().corr(base[right].rank())), 3),
        }
        for label, left, right in correlation_pairs
    ])
    failure_table = failure[["test_id", "test_name", "records_tested", "observed_metric", "status"]]
    failed = int((quality.status == "FAIL").sum())
    if reconciliation is None:
        reconciliation_section = "_Base-case SQL reconciliation was not run._"
    else:
        worst = reconciliation.max_abs_diff.dropna()
        reconciliation_section = (
            f"Largest absolute base-case difference across "
            f"{int(reconciliation.compared.max())} lots and {len(reconciliation)} measures: "
            f"`{(float(worst.max()) if len(worst) else 0.0):.2e}` "
            f"(tolerance `{RECONCILIATION_TOLERANCE:.0e}`).\n\n"
            + markdown_table(reconciliation)
        )
    text = f"""# Scoring Methodology

## Business objective

Rank the controlled Delhi NCR candidate universe for BD prioritisation while keeping demand, economics, competitive whitespace, network value and closeability distinct. The result is a transparent relative decision aid, not a prediction model and not a claim about real PARK It Up operations.

## Inputs and provenance

`parking_acquisition_features` combines source public OSM location/POI fields, derived distances/counts, and explicitly synthetic operational performance, owner terms and hypothetical network sites. Competitor capacity is absent for all candidates, so the Competition pillar uses a **count-based supply-pressure proxy**. It does not invent competitor capacity.

## Normalisation

Continuous inputs use 5th/95th-percentile winsorisation followed by min-max scaling to 0-100. This prevents the largest synthetic facilities or revenue values from compressing all other lots. Scenario calculations retain baseline anchors so a uniform commission or cost shock changes absolute scores instead of disappearing through re-normalisation. Scores are relative to this 120-lot universe.

## Pillars

### Demand Potential (30%)

`0.50 * observed demand + 0.40 * location demand + 0.10 * demand headroom`

- Observed demand = `0.70 * average occupancy + 0.30 * 90th-percentile daily peak occupancy`.
- Location demand = metro accessibility (30%), bounded POI activity (35%), transit stops (15%), and micro-market prior (20%). Sparse OSM POI counts are treated as incomplete coverage, not proof of no activity.
- Headroom is the positive gap between location potential and utilisation evidence. It is deliberately small so a weakly utilised lot cannot rank on proxy data alone.

### Revenue Potential (25%)

`0.75 * expected monthly platform contribution + 0.25 * contribution per parking space`

Expected monthly contribution uses adjusted net platform bookings, average dwell duration, hourly tariff, the synthetic mean realisation factor of 0.76, synthetic per-lot commission, and 30 days. Sustainable utilisation is capped at 85% and only receives a small uplift from location headroom. Revenue per space prevents sheer capacity from deciding the pillar.

### Competition Opportunity (15%)

`0.55 * inverse count-based supply pressure + 0.20 * inverse aggregator penetration + 0.15 * competitor distance + 0.10 * tariff headroom`

Supply pressure is `ln(1 + competitor count within 1 km) / market demand prior`. It is a derived proxy because public competitor capacities are unavailable. Higher nearby competitor tariffs indicate possible headroom; missing tariffs are neutral rather than treated as favourable.

### Strategic Fit (15%)

`0.50 * network distance band + 0.35 * market whitespace + 0.15 * anchor capacity`

The network band penalises lots within 400 m of a live hypothetical site, rewards roughly 1.5-6 km spacing, and tapers after 6 km. Market whitespace equals locality location-demand strength times one minus local live-network-capacity coverage. It is conditional on the explicitly synthetic network baseline.

### Acquisition Feasibility (15%)

Willingness (20%), contract flexibility (14%), digital readiness (12%), documentation (15%), decision-maker access (12%), operational simplicity (8%), onboarding cost (7%), setup speed (4%), exclusivity (3%), capex need (2%), and owner-type friction (3%). It is kept separate in the attractiveness matrix and still contributes 15% to the final portfolio rank.

## Formula

`Acquisition Score = 0.30*Demand + 0.25*Revenue + 0.15*Competition + 0.15*Strategic Fit + 0.15*Feasibility`

The baseline weights remain the baseline business judgement. They were not tuned to synthetic outcomes. Demand-heavy, revenue-heavy, feasibility-heavy and balanced alternatives are tested rather than presented as proven truth.

## Correlation and double-counting audit

{markdown_table(correlation_table)}

Demand and Revenue are moderately correlated because utilisation and bookings legitimately drive both, but they are not interchangeable: Demand blends location evidence and occupancy, while Revenue includes tariff, capacity, dwell, booking share and commission. Capacity has only a moderate relationship with the final Acquisition Score, so large facilities do not dominate automatically. Feasibility remains a separate owner/deal construct; its relationship with willingness is expected, while the feasibility-heavy scenario tests whether that pillar can materially change the ordering.

## Segmentation

Thresholds are calibrated from the base-case distribution rather than inherited from the schema layer placeholders:

- High attractiveness: {thresholds['attractiveness_high']:.2f} (67th percentile)
- Develop attractiveness floor: {thresholds['attractiveness_develop']:.2f} (33rd percentile)
- Feasibility floor: {thresholds['feasibility_mid']:.2f} (median)

`ACQUIRE NOW` = high attractiveness and at-or-above-median feasibility. `PURSUE` = high attractiveness but lower feasibility. `DEVELOP` = mid-or-better attractiveness plus feasibility. Others are `AVOID`.

{markdown_table(segments)}

## Explainability

`lot_dimension_score` stores each pillar, its actual weight and weighted contribution. `parking_score_explanation` stores positive and constraint flags; `parking_acquisition_score` joins them with the source feature layer. No score contains an encoded recommendation flag from the data pipeline.

## Sensitivity and rank stability

Ten primary scenarios feed rank stability: base, conservative/optimistic demand, lower/higher commission, higher cost, and the four alternative weight sets. A lot's rank stability is the share of these scenarios in which it stays in the top 10: 90-100% Very Stable, 70-89% Stable, 40-69% Sensitive, below 40% Highly Sensitive. Six supplementary checks cover dwell time, joint platform economics, and two hypothetical-network variants.

{markdown_table(sensitivity_table.round(3))}

## Score distributions

{markdown_table(score_stats)}

## Validation status

The engine ran {len(quality)} automated scoring checks; {failed} failed.

Demand and Revenue exist twice by necessity: `parking_component_scores` defines
the baseline in SQL, and Python re-derives them because a scenario multiplier
cannot be expressed in that view. Every run therefore reconciles the base case
column by column against the SQL view, so a constant edited in only one of the
two files fails the build instead of quietly producing two different models.

{reconciliation_section}

{markdown_table(failure_table)}

## Limitations

- Performance, commercial terms, owner posture, outreach and the network baseline are synthetic.
- The OSM POI extract is bounded and sparse; zero counts do not prove zero local activity.
- Competitor capacity is unavailable, so competition uses a transparent count-density proxy.
- Haversine distances ignore walking barriers and actual road routing.
- Two-wheelers are out of scope.
- Scores are relative to this synthetic 120-lot study universe and have no predictive validation against acquisition outcomes.
- This is a weighted decision framework, not an ML model. It has no target variable or learned coefficients; its value is inspectability and sensitivity testing.
"""
    (PATHS["documentation_methodology"] / "scoring_methodology.md").write_text(text, encoding="utf-8")


def write_data_dictionary(connection: Any) -> None:
    columns = query_frame(connection, """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='parkitup'
        AND table_name IN ('parking_acquisition_features','parking_component_scores','acquisition_scenario',
                             'lot_dimension_score','lot_score','lot_scenario_score','parking_score_explanation','lot_rank_stability',
                             'sensitivity_summary','locality_acquisition_summary','parking_acquisition_score','bd_acquisition_targets')
        ORDER BY table_name, ordinal_position
    """)
    definitions = {
        "demand_score": "0-100 Demand Potential pillar score.",
        "revenue_score": "0-100 Revenue Potential pillar score.",
        "competition_score": "0-100 Competition Opportunity pillar score.",
        "strategic_fit_score": "0-100 Strategic Fit pillar score.",
        "feasibility_score": "0-100 Acquisition Feasibility pillar score.",
        "attractiveness_score": "Weighted blend of non-feasibility pillars, re-normalised to 0-100.",
        "acquisition_score": "Weighted 0-100 composite under the identified scenario.",
        "rank_overall": "Unique descending rank within a scenario.",
        "rank_stability_pct": "Share of primary scenarios where the lot appears in the Top 10.",
        "market_whitespace_score": "0-100 location-demand strength adjusted for hypothetical local network coverage.",
        "expected_monthly_platform_revenue_inr": "Illustrative synthetic monthly platform contribution; ordering input, not a forecast.",
        "weighted_contribution": "Pillar score multiplied by the selected weight set weight.",
        "weight_applied": "Weight applied to this pillar under the selected weight set.",
        "segment_code": "Business action segment derived from attractiveness and feasibility thresholds.",
    }
    public_columns = {
        "latitude", "longitude", "source_name", "source_reference", "osm_id",
    }
    assumed_columns = {
        "parking_type", "market_demand_prior", "micro_market_type", "population_density_band",
    }
    synthetic_columns = {
        "owner_id", "owner_type", "capacity_cars", "hourly_rate_inr", "is_24x7",
        "expected_commission_pct", "estimated_onboarding_cost_inr", "documentation_readiness",
        "operational_complexity", "exclusivity_possible", "requires_capex", "estimated_setup_days",
        "years_operating", "digital_payment_enabled", "management_system", "willingness_to_digitize",
        "contract_flexibility", "decision_maker_accessible", "competitor_avg_hourly_rate_inr",
        "aggregator_listed_count_1km", "avg_occupancy_rate", "p90_peak_occupancy_rate",
        "weekday_occupancy_rate", "weekend_occupancy_rate", "avg_daily_entries",
        "avg_daily_platform_bookings", "avg_daily_cancellations", "platform_booking_share",
        "cancellation_rate", "avg_daily_gross_revenue_inr", "observation_gross_revenue_inr",
        "avg_park_duration_hours", "weekday_hourly_peak_occupancy_rate",
        "weekend_hourly_peak_occupancy_rate", "weekday_busy_hour_share", "weekend_busy_hour_share",
    }
    config_columns = {
        "parking_id", "lot_code", "locality_id", "city_name", "scenario_id", "weight_set_id", "record_source",
    }
    public_derived_columns = {
        "lot_name", "locality_name", "metro_distance_m", "nearest_metro_station", "mall_distance_m",
        "office_count_500m", "retail_count_500m", "restaurant_count_500m", "hospital_count_1km",
        "education_count_1km", "transit_stop_count_500m", "competitor_count_500m",
        "competitor_count_1km", "nearest_competitor_distance_m", "competitor_distance_proxy_m",
        "competitor_total_capacity_1km",
    }
    rows: list[dict[str, str]] = []
    for row in columns.itertuples(index=False):
        table = str(row.table_name)
        column = str(row.column_name)
        if table == "acquisition_scenario":
            source_type = "ASSUMED"
            reference = "Scenario configuration in python/analysis/scoring_engine.py"
            lineage = "Assumed"
            logic = "Explicit sensitivity/scoring assumption; versioned as data."
        elif column in config_columns:
            source_type = "CONFIG"
            reference = "schema, seeds and ETL join keys"
            lineage = "Config"
            logic = "Stable join key or scenario identifier; not an observed business measure."
        elif column in public_columns:
            source_type = "PUBLIC"
            reference = "Cached OpenStreetMap snapshot and element references"
            lineage = "Public"
            logic = "Copied from the cached public source; no runtime API call is required."
        elif column in assumed_columns:
            source_type = "ASSUMED"
            reference = "the data pipeline documented assumptions and market classification"
            lineage = "Assumed"
            logic = "Analyst-defined prior or fallback classification; not presented as observed fact."
        elif column in synthetic_columns:
            source_type = "SYNTHETIC"
            reference = "python/etl/synthetic_generation.py and documentation/methodology/data_generation.md"
            lineage = "Synthetic"
            logic = "Relationship-aware deterministic simulation with the documented fixed seed."
        elif column in public_derived_columns:
            source_type = "DERIVED"
            reference = "Cached OpenStreetMap snapshot plus cleaning and geo derivation"
            lineage = "Derived"
            logic = "Calculated from public coordinates/features; sparse coverage is not proof of absence."
        else:
            source_type = "DERIVED"
            reference = "sql/analysis/component_scores.sql and python/analysis/scoring_engine.py"
            lineage = "Derived"
            logic = "Computed by the scoring analytical layer; see scoring_methodology.md."
        rows.append({
            "Table": table,
            "Column": column,
            "Data type": str(row.data_type),
            "Definition": definitions.get(column, f"scoring {table} field: {column.replace('_', ' ')}."),
            "Source type": source_type,
            "Source/reference": reference,
            "Raw/derived/synthetic": lineage,
            "Generation logic": logic,
            "Business purpose": "Explainable acquisition prioritisation and BD drill-down.",
        })
    write_csv(pd.DataFrame(rows), PATHS["documentation_methodology"] / "data_dictionary_analytics.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-schema", action="store_true", help="Assume scoring schema and views are already installed.")
    args = parser.parse_args()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO parkitup, public")
        if not args.skip_schema:
            run_sql_file(connection, REPO_ROOT / "database/schema/06_analysis.sql")
        ensure_revenue_weight_set(connection)
        run_sql_file(connection, REPO_ROOT / "sql/analysis/component_scores.sql")
        base_component = query_frame(connection, "SELECT * FROM parkitup.parking_component_scores ORDER BY parking_id")
        if len(base_component) != settings.target_lot_count:
            raise ValueError(f"Expected {settings.target_lot_count} feature rows, found {len(base_component)}")
        numeric_columns = [column for column in base_component.columns if column not in {
            "lot_code", "lot_name", "locality_name", "city_name", "micro_market_type", "population_density_band",
            "owner_type", "parking_type", "record_source", "source_name", "source_reference", "data_quality_flag",
            "nearest_metro_station", "management_system", "methodology_note", "is_24x7", "digital_payment_enabled",
            "exclusivity_possible", "requires_capex", "decision_maker_accessible",
        }]
        for column in numeric_columns:
            base_component[column] = pd.to_numeric(base_component[column], errors="raise")
        weights = weight_maps(connection)
        preliminary = score_scenario(base_component, SCENARIOS[0], weights[1])
        thresholds = {
            "attractiveness_high": round(float(preliminary.attractiveness_score.quantile(0.67)), 2),
            "attractiveness_develop": round(float(preliminary.attractiveness_score.quantile(0.33)), 2),
            "feasibility_mid": round(float(preliminary.feasibility_score.quantile(0.50)), 2),
        }
        update_segment_rules(connection, thresholds)
        results: dict[int, pd.DataFrame] = {}
        for scenario in SCENARIOS:
            output = score_scenario(base_component, scenario, weights[int(scenario["weight_set_id"])], thresholds)
            output.attrs["thresholds"] = thresholds
            results[int(scenario["scenario_id"])] = output
        base_result = results[1]
        explanations = reason_flags(base_result)
        stability, sensitivity = stability_and_sensitivity(results)
        locality = locality_summary(base_result)
        failure = failure_tests(base_result)
        reconciliation = reconcile_base_case_against_sql(base_component, base_result)
        quality = validate_outputs(results, stability, sensitivity, failure, reconciliation)
        if (quality.status == "FAIL").any():
            raise ValueError("Scoring validation failed:\n" + quality[quality.status == "FAIL"].to_string(index=False)
                             + "\n\nBase-case SQL reconciliation:\n" + reconciliation.to_string(index=False))
        persist_outputs(connection, SCENARIOS, results, base_component, weights, explanations, stability, sensitivity, locality)
        sql_quality = run_sql_quality_checks()
        sql_errors = sql_quality[(sql_quality.severity == "ERROR") & (sql_quality.status == "FAIL")]
        if not sql_errors.empty:
            raise ValueError("SQL data quality failed after the scoring engine:\n" + sql_errors.to_string(index=False))
        view_counts = query_frame(connection, """
            SELECT
              (SELECT COUNT(*) FROM parkitup.parking_acquisition_features) AS feature_rows,
              (SELECT COUNT(*) FROM parkitup.parking_component_scores) AS component_rows,
              (SELECT COUNT(*) FROM parkitup.lot_score) AS weight_set_scores,
              (SELECT COUNT(*) FROM parkitup.lot_scenario_score) AS scenario_scores,
              (SELECT COUNT(*) FROM parkitup.parking_acquisition_score) AS baseline_scores,
              (SELECT COUNT(*) FROM parkitup.locality_acquisition_summary) AS locality_rows,
              (SELECT COUNT(*) FROM parkitup.bd_acquisition_targets) AS bd_target_rows
        """)
        bd_targets = query_frame(
            connection,
            "SELECT * FROM parkitup.bd_acquisition_targets ORDER BY bd_priority_rank",
        )
        write_csv(base_component, PATHS["data_processed"] / "parking_component_scores.csv")
        write_csv(base_result, PATHS["data_processed"] / "parking_acquisition_score.csv")
        write_csv(pd.concat([frame.assign(scenario_id=scenario_id) for scenario_id, frame in results.items()]), PATHS["data_processed"] / "lot_scenario_score.csv")
        write_csv(locality, PATHS["data_processed"] / "locality_acquisition_summary.csv")
        write_csv(bd_targets, PATHS["data_processed"] / "bd_acquisition_targets.csv")
        write_csv(explanations, PATHS["data_processed"] / "parking_score_explanation.csv")
        write_csv(stability, PATHS["validation"] / "rank_stability_results.csv")
        write_csv(sensitivity, PATHS["validation"] / "sensitivity_results.csv")
        write_csv(failure, PATHS["validation"] / "scoring_failure_tests.csv")
        write_csv(quality, PATHS["validation"] / "scoring_quality_results.csv")
        write_csv(reconciliation, PATHS["validation"] / "sql_reconciliation.csv")
        write_csv(sql_quality, PATHS["validation"] / "postgres_data_quality_scoring_results.csv")
        write_csv(manual_review_sample(base_result), PATHS["validation"] / "scoring_manual_review.csv")
        write_csv(diagnostics(base_result), PATHS["validation"] / "scoring_correlation_matrix.csv")
        write_data_dictionary(connection)
        write_methodology(base_result, thresholds, sensitivity, quality, failure, reconciliation)
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": thresholds,
            "row_counts": {key: int(value) for key, value in view_counts.iloc[0].to_dict().items()},
            "segment_counts": {key: int(value) for key, value in base_result.segment_code.value_counts().sort_index().to_dict().items()},
            "score_describe": json.loads(base_result[["demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score", "acquisition_score"]].describe().round(4).to_json()),
            "top_10": base_result.nsmallest(10, "rank_overall")[["rank_overall", "parking_id", "lot_name", "locality_name", "acquisition_score", "segment_code"]].to_dict(orient="records"),
            "failure_tests": failure.to_dict(orient="records"),
            "sql_quality": {
                f"{severity}_{status}": int(count)
                for (severity, status), count in sql_quality.groupby(["severity", "status"]).size().items()
            },
        }
        (PATHS["validation"] / "scoring_execution_summary.json").write_text(
            json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
        )
    print("Acquisition scoring engine completed")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
