"""Run the complete validation Python analytics and model-validation layer."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep the documented direct-script entry point working as well as
# ``python -m python.analysis.run_validation``.  When a file below ``python/`` is
# executed directly, Python otherwise places only that subdirectory on
# ``sys.path`` and cannot resolve the repository-level ``python`` package.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from python.analysis.data_access import load_analysis_inputs, source_contract_checks
from python.analysis.eda import (
    bd_conversion_breakdowns,
    classify_markets,
    competition_quadrants,
    demand_summary,
    parking_characteristics,
    peak_hour_windows,
    relationship_summary,
    revenue_efficiency_segments,
    score_distribution_summary,
)
from python.analysis.profiling import profile_datasets, suspicious_distributions
from python.config import PATHS, REPO_ROOT, settings
from python.model_validation.diagnostics import (
    base_case_reconciliation,
    component_influence,
    monotonicity_tests,
    outlier_review,
    score_correlations,
)
from python.model_validation.sensitivity import (
    default_weight_map,
    locality_scenario_summary,
    rank_stability,
    revenue_sensitivity_grid,
    run_business_scenarios,
    scenario_summary,
    segment_thresholds,
)
from python.model_validation.stress_tests import run_stress_tests
from python.visualization.charts import create_analysis_charts


PROFILE_DATASETS = {
    "parking": "parking",
    "owners": "owners",
    "competition": "competition",
    "location_demand": "location_demand",
    "acquisition_terms": "acquisition_terms",
    "daily_performance": "daily_performance",
    "hourly_profile": "hourly_profile",
    "outreach": "outreach",
    "acquisition_scores": "acquisition_scores",
    "component_scores": "component_scores",
    "parking_performance": "parking_performance",
    "locality_summary": "locality_summary",
}

LOAD_DATASETS = sorted(set(PROFILE_DATASETS.values()) | {"bd_funnel", "segment_rules", "scoring_weights"})


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = frame.copy()
    for column in result.columns:
        if result[column].map(lambda value: isinstance(value, (list, tuple, dict))).any():
            result[column] = result[column].map(
                lambda value: "|".join(map(str, value)) if isinstance(value, (list, tuple)) else json.dumps(value, default=str)
            )
    result.to_csv(path, index=False, lineterminator="\n")


def _serialise(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    return value


def _dashboard_parking_export(scores: pd.DataFrame, performance: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    perf_columns = [
        "parking_id",
        "avg_occupancy_pct",
        "p90_peak_occupancy_pct",
        "avg_daily_bookings",
        "avg_daily_revenue_inr",
        "revenue_per_space_inr",
        "bookings_per_space",
        "revenue_per_occupied_space_inr",
        "competitor_count_1km",
        "competitor_avg_hourly_rate_inr",
    ]
    columns = [
        "parking_id",
        "lot_code",
        "lot_name",
        "locality_id",
        "locality_name",
        "city_name",
        "owner_id",
        "owner_type",
        "latitude",
        "longitude",
        "parking_type",
        "capacity_cars",
        "hourly_rate_inr",
        "avg_occupancy_rate",
        "p90_peak_occupancy_rate",
        "demand_score",
        "revenue_score",
        "competition_score",
        "strategic_fit_score",
        "feasibility_score",
        "attractiveness_score",
        "acquisition_score",
        "priority_segment",
        "acquisition_rank",
        "expected_monthly_platform_revenue_inr",
        "rank_stability_pct",
        "stability_class",
        "positive_reason_flags",
        "constraint_reason_flags",
        "recommendation",
        "expected_commission_pct",
        "estimated_onboarding_cost_inr",
        "willingness_to_digitize",
        "documentation_readiness",
        "decision_maker_accessible",
    ]
    result = scores[columns].merge(performance[perf_columns], on="parking_id", how="left")
    result = result.merge(
        stability[
            [
                "parking_id",
                "top_10_frequency_pct",
                "top_20_frequency_pct",
                "average_rank",
                "best_rank",
                "worst_rank",
                "rank_standard_deviation",
            ]
        ],
        on="parking_id",
        how="left",
    )
    return result.sort_values("acquisition_rank").reset_index(drop=True)


def _business_insights(
    scores: pd.DataFrame,
    markets: pd.DataFrame,
    relationships: pd.DataFrame,
    efficiency: pd.DataFrame,
    quadrants: pd.DataFrame,
    stability: pd.DataFrame,
    bd_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    """Create evidence-linked findings without causal language."""
    rows: list[dict[str, Any]] = []
    booking_relationship = relationships[relationships["relationship"] == "Bookings vs occupancy"].iloc[0]
    rows.append(
        {
            "insight_area": "Demand",
            "finding": f"Bookings and observed occupancy are positively associated in the modelled lots (Spearman {booking_relationship['spearman']:.2f}).",
            "evidence": f"n={int(booking_relationship['n'])}; relationship is descriptive and synthetic.",
            "caveat": "This does not establish that occupancy causes bookings.",
        }
    )
    large_count = int((efficiency["efficiency_pattern"] == "LARGE_INEFFICIENT").sum())
    small_count = int((efficiency["efficiency_pattern"] == "SMALL_HIGH_UTILIZATION").sum())
    rows.append(
        {
            "insight_area": "Economics",
            "finding": f"The portfolio contains {large_count} large/low-efficiency lots and {small_count} small/high-utilisation lots under the documented comparison rules.",
            "evidence": "Capacity and utilisation are evaluated together; capacity alone is not an acquisition recommendation.",
            "caveat": "Revenue and utilisation inputs are synthetic demonstrations.",
        }
    )
    quadrant_counts = quadrants["competition_quadrant"].value_counts()
    rows.append(
        {
            "insight_area": "Competition",
            "finding": f"Demand and competition form distinct contexts: {int(quadrant_counts.get('HIGH_DEMAND_LOW_COMPETITION', 0))} lots are high-demand/low-competition and {int(quadrant_counts.get('HIGH_DEMAND_HIGH_COMPETITION', 0))} are high-demand/high-competition.",
            "evidence": "Quadrants use portfolio medians for Demand Score and competitor count within 1 km.",
            "caveat": "Competitor capacity is unavailable, so count-based pressure is a proxy.",
        }
    )
    top_markets = markets.sort_values("market_whitespace_score", ascending=False).head(3)
    rows.append(
        {
            "insight_area": "Market",
            "finding": "The highest whitespace scores are in " + ", ".join(top_markets["locality_name"].tolist()) + ".",
            "evidence": "Whitespace is the analytics demand score adjusted for hypothetical live-network capacity coverage.",
            "caveat": "The network baseline is synthetic and the classification is relative to these 17 markets.",
        }
    )
    top = scores.sort_values("acquisition_rank").iloc[0]
    top10_markets = scores.nsmallest(10, "acquisition_rank")["locality_name"].value_counts().head(3)
    rows.append(
        {
            "insight_area": "Acquisition",
            "finding": f"The base-case leader is parking {int(top['parking_id'])}, {top['lot_name']} in {top['locality_name']} with score {top['acquisition_score']:.2f}; the base Top 10 concentrates in " + ", ".join(f"{locality} ({count})" for locality, count in top10_markets.items()) + ".",
            "evidence": "Official scoring acquisition score, rank, and segment are used.",
            "caveat": "This is a relative ranking in a controlled synthetic universe, not a predictive probability.",
        }
    )
    robust = stability.sort_values(["top_10_frequency_pct", "average_rank"], ascending=[False, True]).iloc[0]
    rows.append(
        {
            "insight_area": "Robustness",
            "finding": f"Parking {int(robust['parking_id'])} is the most robust target under the validation scenario set with {robust['top_10_frequency_pct']:.0f}% Top-10 frequency and average rank {robust['average_rank']:.1f}.",
            "evidence": f"{int(robust['scenarios_evaluated'])} scenarios; best rank {int(robust['best_rank'])}, worst rank {int(robust['worst_rank'])}.",
            "caveat": "Robustness depends on the selected scenario bounds and does not validate real conversion.",
        }
    )
    source = bd_breakdowns[bd_breakdowns["dimension"] == "lead_source"].query("leads >= 5")
    if len(source):
        best_source = source.sort_values(["acquisition_rate_pct", "leads"], ascending=[False, False]).iloc[0]
        rows.append(
            {
                "insight_area": "BD",
                "finding": f"The highest synthetic acquisition rate among lead sources with at least five leads is {best_source['segment']} at {best_source['acquisition_rate_pct']:.2f}%.",
                "evidence": f"{int(best_source['acquired'])} acquired of {int(best_source['leads'])} leads.",
                "caveat": "This is a generator-shaped sample and should not be interpreted as causal source performance.",
            }
        )
    return pd.DataFrame(rows)


def _write_findings_markdown(
    path: Path,
    summary: dict[str, Any],
    insights: pd.DataFrame,
    stress: pd.DataFrame,
    monotonicity: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> None:
    lines = [
        "# validation Python Analytics Findings",
        "",
        "This report is generated from the verified the validation layer run. Operational, economic, owner, outreach, and network fields are synthetic; relative rankings demonstrate method rather than real-world performance.",
        "",
        "## EDA findings",
        "",
    ]
    for row in insights.itertuples(index=False):
        lines.append(f"- **{row.insight_area}.** {row.finding} Evidence: {row.evidence} Caveat: {row.caveat}")
    lines.extend(["", "## Stress tests", ""])
    for row in stress.itertuples(index=False):
        lines.append(f"- {row.test_id}: **{row.status}** — {row.expected}; observed `{row.observed_metric}` (rank/score `{row.rank_or_score}`).")
    lines.extend(["", "## Monotonicity tests", ""])
    for row in monotonicity.itertuples(index=False):
        lines.append(f"- {row.test_id}: **{row.status}** — {row.description}; violations `{row.violations}`.")
    lines.extend(
        [
            "",
            "## Base-case reconciliation",
            "",
            f"Maximum acquisition-score absolute difference versus scoring: `{reconciliation['acquisition_score_abs_diff'].max():.8f}`. Exact rank matches: `{int(reconciliation['rank_equal'].sum())}/{len(reconciliation)}`. Exact segment matches: `{int(reconciliation['segment_equal'].sum())}/{len(reconciliation)}`.",
            "",
            "## Limitations",
            "",
            "- The data contains no real acquisition outcomes, so model quality cannot be described as predictive accuracy.",
            "- OSM POI coverage is bounded and sparse; zero counts do not prove zero local activity.",
            "- Competitor capacity is unavailable, so competition diagnostics use transparent count/distance/price proxies.",
            "- Scores and thresholds are relative to the controlled 120-lot universe and shift when the population changes.",
            "- Python intentionally does not replace analytics relational logic; it reads views and applies statistical and scenario diagnostics.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_validation() -> dict[str, Any]:
    """Execute extraction, EDA, validation, charts, and dashboard exports."""
    validation_dir = PATHS["validation"]
    processed_dir = PATHS["data_processed"]
    figure_dir = validation_dir / "figures"
    validation_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    inputs = load_analysis_inputs(LOAD_DATASETS)
    source_checks = source_contract_checks(inputs)
    if (source_checks["status"] == "FAIL").any():
        raise ValueError("validation source contract failed:\n" + source_checks.to_string(index=False))

    profile_inputs = {key: inputs[value] for key, value in PROFILE_DATASETS.items()}
    profile, profile_summary = profile_datasets(profile_inputs)
    suspicious = suspicious_distributions(profile)

    scores = inputs["acquisition_scores"]
    components = inputs["component_scores"]
    performance = inputs["parking_performance"]
    daily = inputs["daily_performance"]
    hourly = inputs["hourly_profile"]
    markets, market_cutoffs = classify_markets(inputs["locality_summary"])
    quadrants, quadrant_cutoffs = competition_quadrants(scores)
    efficiency = revenue_efficiency_segments(performance)
    relationships = relationship_summary(scores)
    demand = demand_summary(scores, daily, hourly)
    peaks = peak_hour_windows(hourly)
    characteristics = parking_characteristics(scores)
    bd_breakdowns = bd_conversion_breakdowns(inputs["outreach"])
    score_distribution = score_distribution_summary(scores)
    score_correlation = score_correlations(scores)

    base_weights = default_weight_map(inputs["scoring_weights"])
    thresholds = segment_thresholds(inputs["segment_rules"])
    scenarios = run_business_scenarios(components, base_weights, thresholds)
    scenario_stats = scenario_summary(scenarios)
    locality_scenarios = locality_scenario_summary(scenarios)
    stability = rank_stability(scenarios)
    robust_targets = stability.head(10).copy()
    influence = component_influence(scores, base_weights, thresholds)
    reconciliation = base_case_reconciliation(components, scores, base_weights, thresholds)
    monotonicity = monotonicity_tests(components)
    stress = run_stress_tests(components, base_weights, thresholds)
    outliers = outlier_review(scores)
    revenue_lot, revenue_portfolio = revenue_sensitivity_grid(scores)
    insights = _business_insights(scores, markets, relationships, efficiency, quadrants, stability, bd_breakdowns)

    dashboard_parking = _dashboard_parking_export(scores, performance, stability)
    dashboard_targets = dashboard_parking.sort_values("acquisition_rank").copy()
    compact_scenarios = scenarios[
        [
            "parking_id",
            "lot_name",
            "locality_name",
            "scenario_code",
            "scenario_group",
            "scenario_description",
            "demand_score",
            "revenue_score",
            "competition_score",
            "strategic_fit_score",
            "feasibility_score",
            "attractiveness_score",
            "acquisition_score",
            "expected_monthly_platform_revenue_inr",
            "adjusted_onboarding_cost_inr",
            "segment_code",
            "rank_overall",
            "base_rank",
            "rank_change_vs_base",
            "score_change_vs_base",
            "demand_multiplier",
            "commission_multiplier",
            "booking_share_multiplier",
            "dwell_multiplier",
            "onboarding_cost_multiplier",
            "competition_multiplier",
            "network_variant",
            "demand_weight",
            "revenue_weight",
            "competition_weight",
            "strategic_fit_weight",
            "feasibility_weight",
        ]
    ].copy()

    _write_csv(source_checks, validation_dir / "validation_source_contract.csv")
    _write_csv(profile, validation_dir / "validation_data_quality_profile.csv")
    _write_csv(profile_summary, validation_dir / "validation_data_quality_summary.csv")
    _write_csv(suspicious, validation_dir / "validation_suspicious_distributions.csv")
    _write_csv(characteristics["by_type"], validation_dir / "validation_parking_type_summary.csv")
    _write_csv(characteristics["by_locality"], validation_dir / "validation_parking_locality_summary.csv")
    _write_csv(demand["by_day"], validation_dir / "validation_demand_by_day.csv")
    _write_csv(demand["by_locality"], validation_dir / "validation_demand_by_locality.csv")
    _write_csv(demand["hourly"], validation_dir / "validation_hourly_patterns.csv")
    _write_csv(peaks, validation_dir / "validation_peak_hour_windows.csv")
    _write_csv(relationships, validation_dir / "validation_relationships.csv")
    _write_csv(efficiency, validation_dir / "validation_revenue_efficiency_segments.csv")
    _write_csv(quadrants, validation_dir / "validation_competition_quadrants.csv")
    _write_csv(markets, validation_dir / "validation_market_classification.csv")
    _write_csv(score_distribution, validation_dir / "validation_score_distributions.csv")
    _write_csv(score_correlation, validation_dir / "validation_score_correlations.csv")
    _write_csv(influence, validation_dir / "validation_component_diagnostics.csv")
    _write_csv(scenario_stats, validation_dir / "validation_scenario_summary.csv")
    _write_csv(compact_scenarios, validation_dir / "validation_sensitivity_dashboard.csv")
    _write_csv(locality_scenarios, validation_dir / "validation_locality_sensitivity.csv")
    _write_csv(stability, validation_dir / "validation_rank_stability.csv")
    _write_csv(robust_targets, validation_dir / "validation_robust_targets.csv")
    _write_csv(stress, validation_dir / "validation_stress_tests.csv")
    _write_csv(monotonicity, validation_dir / "validation_monotonicity_tests.csv")
    _write_csv(outliers, validation_dir / "validation_outlier_review.csv")
    _write_csv(reconciliation, validation_dir / "validation_base_reconciliation.csv")
    _write_csv(bd_breakdowns, validation_dir / "validation_bd_conversion_breakdowns.csv")
    _write_csv(revenue_lot, validation_dir / "validation_revenue_sensitivity_lot.csv")
    _write_csv(revenue_portfolio, validation_dir / "validation_revenue_sensitivity.csv")
    _write_csv(insights, validation_dir / "validation_business_insights.csv")

    _write_csv(dashboard_parking, processed_dir / "parking_dashboard.csv")
    _write_csv(markets, processed_dir / "locality_dashboard.csv")
    _write_csv(dashboard_targets, processed_dir / "acquisition_targets.csv")
    _write_csv(inputs["bd_funnel"], processed_dir / "bd_funnel_dashboard.csv")
    _write_csv(compact_scenarios, processed_dir / "sensitivity_dashboard.csv")
    _write_csv(locality_scenarios, processed_dir / "locality_sensitivity_dashboard.csv")
    _write_csv(revenue_portfolio, processed_dir / "revenue_sensitivity_dashboard.csv")
    _write_csv(bd_breakdowns, processed_dir / "bd_conversion_dashboard.csv")

    chart_paths = create_analysis_charts(
        scores=scores,
        performance=performance,
        daily_summary=demand,
        efficiency=efficiency,
        quadrants=quadrants,
        quadrant_cutoffs=quadrant_cutoffs,
        markets=markets,
        market_cutoffs=market_cutoffs,
        influence=influence,
        scenario_summary=scenario_stats,
        stability=stability,
        revenue_sensitivity=revenue_portfolio,
        output_dir=figure_dir,
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": settings.summary(),
        "source_contract": source_checks.to_dict(orient="records"),
        "row_counts": {name: int(len(frame)) for name, frame in inputs.items()},
        "base_weights": base_weights,
        "segment_thresholds": thresholds,
        "score_distribution": score_distribution.to_dict(orient="records"),
        "top_10": dashboard_parking.nsmallest(10, "acquisition_rank")[["acquisition_rank", "parking_id", "lot_name", "locality_name", "acquisition_score", "priority_segment"]].to_dict(orient="records"),
        "robust_top_10": robust_targets[["parking_id", "parking_name", "locality_name", "base_rank", "average_rank", "best_rank", "worst_rank", "top_10_frequency_pct", "top_20_frequency_pct", "stability_class"]].to_dict(orient="records"),
        "scenario_summary": scenario_stats.to_dict(orient="records"),
        "monotonicity_status": monotonicity["status"].value_counts().to_dict(),
        "stress_status": stress["status"].value_counts().to_dict(),
        "base_reconciliation": {
            "max_acquisition_score_abs_diff": float(reconciliation["acquisition_score_abs_diff"].max()),
            "rank_matches": int(reconciliation["rank_equal"].sum()),
            "segment_matches": int(reconciliation["segment_equal"].sum()),
            "records": int(len(reconciliation)),
        },
        "charts": chart_paths,
        "dashboard_exports": [
            "data/processed/parking_dashboard.csv",
            "data/processed/locality_dashboard.csv",
            "data/processed/acquisition_targets.csv",
            "data/processed/bd_funnel_dashboard.csv",
            "data/processed/sensitivity_dashboard.csv",
            "data/processed/locality_sensitivity_dashboard.csv",
            "data/processed/revenue_sensitivity_dashboard.csv",
            "data/processed/bd_conversion_dashboard.csv",
        ],
    }
    (validation_dir / "validation_execution_summary.json").write_text(
        json.dumps(_serialise(summary), indent=2) + "\n", encoding="utf-8"
    )
    _write_findings_markdown(validation_dir / "validation_findings.md", summary, insights, stress, monotonicity, reconciliation)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-only", action="store_true", help="Reserved for future lightweight runs; full validation remains the default.")
    parser.parse_args()
    summary = run_validation()
    print("validation Python analytics and model validation completed")
    print(json.dumps(_serialise(summary), indent=2))


if __name__ == "__main__":
    main()
