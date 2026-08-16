"""Weight, business-scenario, revenue, and rank-stability analysis.

All component recalculation delegates to the official score_scenario
function. the validation layer adds controlled scenario composition and diagnostics; it does
not define a second baseline scoring model.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from python.analysis.scoring_engine import COMPONENT_COLUMNS, classify_segments, score_scenario


DIMENSIONS = tuple(COMPONENT_COLUMNS)


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Validate five non-negative weights and return proportions summing to 1."""
    canonical = {str(key).upper(): float(value) for key, value in weights.items()}
    if set(canonical) != set(DIMENSIONS):
        raise ValueError(f"Weights must contain exactly {DIMENSIONS}; got {sorted(canonical)}")
    if any(value < 0 for value in canonical.values()):
        raise ValueError("Weights cannot be negative")
    total = sum(canonical.values())
    if np.isclose(total, 100.0, atol=1e-8):
        canonical = {key: value / 100.0 for key, value in canonical.items()}
        total = 1.0
    if not np.isclose(total, 1.0, atol=1e-8):
        raise ValueError(f"Weights must sum to 1.0 or 100%, got {total}")
    return canonical


def weight_arguments(
    demand_weight: float,
    revenue_weight: float,
    competition_weight: float,
    strategic_weight: float,
    feasibility_weight: float,
) -> dict[str, float]:
    """Build the reusable five-weight contract requested by the validation layer."""
    return validate_weights(
        {
            "DEMAND": demand_weight,
            "REVENUE": revenue_weight,
            "COMPETITION": competition_weight,
            "STRATEGIC_FIT": strategic_weight,
            "FEASIBILITY": feasibility_weight,
        }
    )


def default_weight_map(scoring_weights: pd.DataFrame) -> dict[str, float]:
    """Read the authoritative default weight set from PostgreSQL."""
    default = scoring_weights[scoring_weights["is_default"].astype(bool)]
    if default["weight_set_id"].nunique() != 1:
        raise ValueError("Exactly one default scoring weight set is required")
    return validate_weights(dict(zip(default["dimension_code"], default["weight"])))


def segment_thresholds(segment_rules: pd.DataFrame) -> dict[str, float]:
    """Read calibrated attractiveness/feasibility boundaries from PostgreSQL."""
    rules = segment_rules.set_index("segment_code")
    required = {"ACQUIRE_NOW", "DEVELOP"}
    if not required.issubset(rules.index):
        raise ValueError(f"Segment rules missing {required - set(rules.index)}")
    return {
        "attractiveness_high": float(rules.loc["ACQUIRE_NOW", "min_attractiveness"]),
        "attractiveness_develop": float(rules.loc["DEVELOP", "min_attractiveness"]),
        "feasibility_mid": float(rules.loc["ACQUIRE_NOW", "min_feasibility"]),
    }


def recalculate_weighted_scores(
    frame: pd.DataFrame,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> pd.DataFrame:
    """Reweight already validated scoring component scores and rerank lots."""
    clean_weights = validate_weights(weights)
    result = frame.copy()
    non_feasibility_total = sum(value for key, value in clean_weights.items() if key != "FEASIBILITY")
    if non_feasibility_total <= 0:
        raise ValueError("At least one attractiveness component must have positive weight")
    result["attractiveness_score"] = sum(
        pd.to_numeric(result[column], errors="raise") * clean_weights[dimension]
        for dimension, column in COMPONENT_COLUMNS.items()
        if dimension != "FEASIBILITY"
    ) / non_feasibility_total
    result["acquisition_score"] = sum(
        pd.to_numeric(result[column], errors="raise") * clean_weights[dimension]
        for dimension, column in COMPONENT_COLUMNS.items()
    )
    result = result.sort_values(["acquisition_score", "parking_id"], ascending=[False, True]).reset_index(drop=True)
    result["rank_overall"] = np.arange(1, len(result) + 1, dtype=int)
    result["segment_code"] = classify_segments(result, dict(thresholds))
    return result


def calculate_weight_scenario(
    frame: pd.DataFrame,
    thresholds: Mapping[str, float],
    *,
    demand_weight: float,
    revenue_weight: float,
    competition_weight: float,
    strategic_weight: float,
    feasibility_weight: float,
) -> pd.DataFrame:
    """Public reusable function accepting the five explicit validation weights."""
    weights = weight_arguments(
        demand_weight,
        revenue_weight,
        competition_weight,
        strategic_weight,
        feasibility_weight,
    )
    return recalculate_weighted_scores(frame, weights, thresholds)


def scenario_catalog(base_weights: Mapping[str, float]) -> list[dict[str, Any]]:
    """Return documented validation business and weight scenarios."""
    base = validate_weights(base_weights)
    equal = weight_arguments(20, 20, 20, 20, 20)
    demand_heavy = weight_arguments(40, 20, 15, 15, 10)
    revenue_heavy = weight_arguments(20, 40, 15, 15, 10)
    feasibility_heavy = weight_arguments(25, 20, 15, 15, 25)
    strategic_growth = weight_arguments(25, 20, 10, 30, 15)

    def item(code: str, group: str, description: str, **overrides: Any) -> dict[str, Any]:
        scenario: dict[str, Any] = {
            "scenario_code": code,
            "scenario_group": group,
            "description": description,
            "weights": base,
            "demand_multiplier": 1.0,
            "commission_multiplier": 1.0,
            "booking_share_multiplier": 1.0,
            "dwell_multiplier": 1.0,
            "onboarding_cost_multiplier": 1.0,
            "network_variant": "LIVE",
            "competition_multiplier": 1.0,
        }
        scenario.update(overrides)
        scenario["weights"] = validate_weights(scenario["weights"])
        return scenario

    return [
        item("BASE_CASE", "Base", "Official scoring baseline assumptions and weights."),
        item(
            "CONSERVATIVE",
            "Business",
            "15% lower demand, 10% lower booking share, 20% lower commission, 5% lower dwell and 25% higher onboarding cost.",
            demand_multiplier=0.85,
            booking_share_multiplier=0.90,
            commission_multiplier=0.80,
            dwell_multiplier=0.95,
            onboarding_cost_multiplier=1.25,
        ),
        item(
            "GROWTH",
            "Business",
            "15% higher demand, 10% higher booking share and 5% higher commission under baseline weights.",
            demand_multiplier=1.15,
            booking_share_multiplier=1.10,
            commission_multiplier=1.05,
        ),
        item(
            "ACQUISITION_COST_PRESSURE",
            "Business",
            "Onboarding cost increases to 1.5x while all other assumptions remain fixed.",
            onboarding_cost_multiplier=1.50,
        ),
        item(
            "COMPETITIVE_PRESSURE",
            "Business",
            "Competition opportunity scores deteriorate by 25% as a pillar-level stress shock.",
            competition_multiplier=0.75,
        ),
        item(
            "NETWORK_EXPANSION",
            "Business",
            "Planned hypothetical sites are treated as part of the network footprint.",
            network_variant="ALL_SITES",
        ),
        item("DEMAND_HEAVY", "Weights", "Demand-led allocation: 40/20/15/15/10.", weights=demand_heavy),
        item("REVENUE_HEAVY", "Weights", "Revenue-led allocation: 20/40/15/15/10.", weights=revenue_heavy),
        item("FEASIBILITY_HEAVY", "Weights", "Feasibility-led allocation: 25/20/15/15/25.", weights=feasibility_heavy),
        item("STRATEGIC_GROWTH", "Weights", "Strategic expansion allocation: 25/20/10/30/15.", weights=strategic_growth),
        item("EQUAL_WEIGHT_CONTROL", "Weights", "Equal-weight analytical control: 20% per pillar.", weights=equal),
    ]


def _recompute_after_component_shock(
    frame: pd.DataFrame,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> pd.DataFrame:
    return recalculate_weighted_scores(frame, weights, thresholds)


def run_business_scenarios(
    component_scores: pd.DataFrame,
    base_weights: Mapping[str, float],
    thresholds: Mapping[str, float],
    scenarios: Iterable[Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Run validation scenarios through the official scoring scenario engine."""
    catalog = list(scenarios or scenario_catalog(base_weights))
    outputs: list[pd.DataFrame] = []
    for index, scenario in enumerate(catalog, start=1):
        base_scenario = {
            "scenario_id": index,
            "demand_multiplier": float(scenario["demand_multiplier"]),
            "commission_multiplier": float(scenario["commission_multiplier"]),
            "booking_share_multiplier": float(scenario["booking_share_multiplier"]),
            "dwell_multiplier": float(scenario["dwell_multiplier"]),
            "onboarding_cost_multiplier": float(scenario["onboarding_cost_multiplier"]),
            "network_variant": str(scenario["network_variant"]),
        }
        weights = validate_weights(scenario["weights"])
        scored = score_scenario(component_scores, base_scenario, weights, dict(thresholds))
        competition_multiplier = float(scenario.get("competition_multiplier", 1.0))
        if not np.isclose(competition_multiplier, 1.0):
            scored["competition_score"] = (
                pd.to_numeric(scored["competition_score"], errors="raise") * competition_multiplier
            ).clip(0.0, 100.0)
            scored = _recompute_after_component_shock(scored, weights, thresholds)
        scored["scenario_index"] = index
        scored["scenario_code"] = str(scenario["scenario_code"])
        scored["scenario_group"] = str(scenario["scenario_group"])
        scored["scenario_description"] = str(scenario["description"])
        scored["demand_multiplier"] = float(scenario["demand_multiplier"])
        scored["commission_multiplier"] = float(scenario["commission_multiplier"])
        scored["booking_share_multiplier"] = float(scenario["booking_share_multiplier"])
        scored["dwell_multiplier"] = float(scenario["dwell_multiplier"])
        scored["onboarding_cost_multiplier"] = float(scenario["onboarding_cost_multiplier"])
        scored["competition_multiplier"] = competition_multiplier
        scored["network_variant"] = str(scenario["network_variant"])
        for dimension, value in weights.items():
            scored[f"{dimension.lower()}_weight"] = value
        outputs.append(scored)
    combined = pd.concat(outputs, ignore_index=True)
    base = combined[combined["scenario_code"] == "BASE_CASE"].set_index("parking_id")
    combined["base_rank"] = combined["parking_id"].map(base["rank_overall"])
    combined["base_score"] = combined["parking_id"].map(base["acquisition_score"])
    combined["rank_change_vs_base"] = combined["base_rank"] - combined["rank_overall"]
    combined["score_change_vs_base"] = combined["acquisition_score"] - combined["base_score"]
    return combined


def rank_stability(scenario_scores: pd.DataFrame) -> pd.DataFrame:
    """Calculate top-10, top-20 and top-50 robustness across scenarios."""
    ranks = scenario_scores.pivot(index="parking_id", columns="scenario_code", values="rank_overall")
    scenario_count = ranks.shape[1]
    base = scenario_scores[scenario_scores["scenario_code"] == "BASE_CASE"].set_index("parking_id")
    result = pd.DataFrame(
        {
            "parking_id": ranks.index.astype(int),
            "scenarios_evaluated": scenario_count,
            "top_10_scenario_count": (ranks <= 10).sum(axis=1).astype(int).to_numpy(),
            "top_10_frequency_pct": ((ranks <= 10).mean(axis=1) * 100.0).round(2).to_numpy(),
            "top_20_scenario_count": (ranks <= 20).sum(axis=1).astype(int).to_numpy(),
            "top_20_frequency_pct": ((ranks <= 20).mean(axis=1) * 100.0).round(2).to_numpy(),
            "top_50_scenario_count": (ranks <= 50).sum(axis=1).astype(int).to_numpy(),
            "top_50_frequency_pct": ((ranks <= 50).mean(axis=1) * 100.0).round(2).to_numpy(),
            "average_rank": ranks.mean(axis=1).round(2).to_numpy(),
            "best_rank": ranks.min(axis=1).astype(int).to_numpy(),
            "worst_rank": ranks.max(axis=1).astype(int).to_numpy(),
            "rank_standard_deviation": ranks.std(axis=1, ddof=0).round(2).to_numpy(),
        }
    ).set_index("parking_id")
    result["stability_class"] = np.select(
        [
            result["top_10_frequency_pct"] >= 90,
            result["top_10_frequency_pct"] >= 70,
            result["top_10_frequency_pct"] >= 40,
        ],
        ["Very Stable", "Stable", "Sensitive"],
        default="Highly Sensitive",
    )
    metadata = base[
        ["lot_name", "locality_name", "acquisition_score", "rank_overall", "segment_code"]
    ].rename(
        columns={
            "lot_name": "parking_name",
            "acquisition_score": "base_score",
            "rank_overall": "base_rank",
            "segment_code": "priority_segment",
        }
    )
    result = metadata.join(result).reset_index()
    return result.sort_values(
        ["top_10_frequency_pct", "top_20_frequency_pct", "average_rank", "base_rank"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


def scenario_summary(scenario_scores: pd.DataFrame) -> pd.DataFrame:
    """Summarise score, segment, and ranking movement for every scenario."""
    base = scenario_scores[scenario_scores["scenario_code"] == "BASE_CASE"].set_index("parking_id")
    base_top10 = set(base.index[base["rank_overall"] <= 10])
    base_top20 = set(base.index[base["rank_overall"] <= 20])
    rows: list[dict[str, Any]] = []
    for code, group in scenario_scores.groupby("scenario_code", sort=False):
        current = group.set_index("parking_id").reindex(base.index)
        top10 = set(current.index[current["rank_overall"] <= 10])
        top20 = set(current.index[current["rank_overall"] <= 20])
        delta = current["rank_overall"] - base["rank_overall"]
        rows.append(
            {
                "scenario_code": code,
                "scenario_group": group["scenario_group"].iloc[0],
                "description": group["scenario_description"].iloc[0],
                "top_10_overlap_count": len(base_top10 & top10),
                "top_10_changes": 10 - len(base_top10 & top10),
                "top_20_overlap_count": len(base_top20 & top20),
                "top_20_changes": 20 - len(base_top20 & top20),
                "average_acquisition_score": round(float(group["acquisition_score"].mean()), 3),
                "mean_abs_rank_change": round(float(delta.abs().mean()), 3),
                "max_abs_rank_change": int(delta.abs().max()),
                "acquire_now_count": int((group["segment_code"] == "ACQUIRE_NOW").sum()),
                "pursue_count": int((group["segment_code"] == "PURSUE").sum()),
                "develop_count": int((group["segment_code"] == "DEVELOP").sum()),
                "avoid_count": int((group["segment_code"] == "AVOID").sum()),
                "segment_change_count": int((current["segment_code"] != base["segment_code"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def locality_scenario_summary(scenario_scores: pd.DataFrame) -> pd.DataFrame:
    """Measure scenario effects at locality grain for the dashboard market page."""
    grouped = (
        scenario_scores.groupby(["scenario_code", "scenario_group", "locality_id", "locality_name"], as_index=False)
        .agg(
            parking_count=("parking_id", "count"),
            average_acquisition_score=("acquisition_score", "mean"),
            high_priority_count=("segment_code", lambda s: int((s == "ACQUIRE_NOW").sum())),
            expected_monthly_platform_revenue_inr=("expected_monthly_platform_revenue_inr", "sum"),
        )
    )
    grouped["scenario_locality_rank"] = grouped.groupby("scenario_code")["average_acquisition_score"].rank(
        method="min", ascending=False
    ).astype(int)
    base = grouped[grouped["scenario_code"] == "BASE_CASE"].set_index("locality_id")
    grouped["base_locality_rank"] = grouped["locality_id"].map(base["scenario_locality_rank"])
    grouped["base_average_acquisition_score"] = grouped["locality_id"].map(base["average_acquisition_score"])
    grouped["locality_rank_change_vs_base"] = grouped["base_locality_rank"] - grouped["scenario_locality_rank"]
    grouped["locality_score_change_vs_base"] = (
        grouped["average_acquisition_score"] - grouped["base_average_acquisition_score"]
    )
    return grouped.sort_values(["scenario_code", "scenario_locality_rank"])


def revenue_sensitivity_grid(
    scores: pd.DataFrame,
    *,
    occupancy_levels: Iterable[float] = (0.40, 0.50, 0.60, 0.70, 0.80),
    price_multipliers: Iterable[float] = (0.85, 1.00, 1.15),
    commission_rates: Iterable[float | None] = (None, 10.0, 15.0, 20.0, 25.0),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate transparent revenue what-ifs without mutating source facts.

    Platform bookings scale proportionally from each lot's observed occupancy.
    This is a sensitivity device, not a forecast or a replacement for the
    official scoring expected-revenue baseline.
    """
    rows: list[pd.DataFrame] = []
    base_occupancy = pd.to_numeric(scores["avg_occupancy_rate"], errors="raise").clip(lower=0.05)
    base_bookings = pd.to_numeric(scores["avg_daily_platform_bookings"], errors="raise")
    cancellation = pd.to_numeric(scores["cancellation_rate"], errors="raise").fillna(0.0)
    dwell = pd.to_numeric(scores["avg_park_duration_hours"], errors="raise")
    price = pd.to_numeric(scores["hourly_rate_inr"], errors="raise")
    documented_commission = pd.to_numeric(scores["expected_commission_pct"], errors="raise")
    for occupancy in occupancy_levels:
        if not 0 <= float(occupancy) <= 1:
            raise ValueError(f"Occupancy must be within 0-1, got {occupancy}")
        booking_scale = float(occupancy) / base_occupancy
        for price_multiplier in price_multipliers:
            if float(price_multiplier) < 0:
                raise ValueError("Price multiplier cannot be negative")
            for commission_rate in commission_rates:
                if commission_rate is not None and not 0 <= float(commission_rate) <= 100:
                    raise ValueError("Commission rate must be within 0-100")
                commission = documented_commission if commission_rate is None else float(commission_rate)
                monthly = (
                    base_bookings
                    * booking_scale
                    * (1.0 - cancellation)
                    * dwell
                    * price
                    * float(price_multiplier)
                    * 0.76
                    * commission
                    / 100.0
                    * 30.0
                ).clip(lower=0.0)
                scenario = pd.DataFrame(
                    {
                        "parking_id": scores["parking_id"].astype(int),
                        "parking_name": scores["lot_name"],
                        "locality_name": scores["locality_name"],
                        "occupancy_rate": float(occupancy),
                        "price_multiplier": float(price_multiplier),
                        "commission_scenario": "DOCUMENTED_PER_LOT" if commission_rate is None else f"GLOBAL_{float(commission_rate):g}_PCT",
                        "commission_pct": documented_commission if commission_rate is None else float(commission_rate),
                        "expected_monthly_platform_revenue_inr": monthly,
                    }
                )
                rows.append(scenario)
    lot_level = pd.concat(rows, ignore_index=True)
    portfolio = (
        lot_level.groupby(
            ["occupancy_rate", "price_multiplier", "commission_scenario"], as_index=False
        )
        .agg(
            total_expected_monthly_platform_revenue_inr=("expected_monthly_platform_revenue_inr", "sum"),
            median_lot_expected_monthly_revenue_inr=("expected_monthly_platform_revenue_inr", "median"),
            mean_lot_expected_monthly_revenue_inr=("expected_monthly_platform_revenue_inr", "mean"),
        )
    )
    return lot_level, portfolio

