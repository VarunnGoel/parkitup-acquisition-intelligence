"""Prepare and validate the portable Power BI model package.

Power BI Desktop is not available on macOS.  These extracts mirror the
documented PostgreSQL-first star schema so the report can be assembled quickly
on Windows without making CSVs a second modelling source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.analysis.data_access import load_analysis_inputs
from python.config import PATHS, REPO_ROOT, settings


POWERBI_DATA_DIR = REPO_ROOT / "data" / "powerbi"
POWERBI_PACKAGE_DIR = REPO_ROOT / "dashboard" / "powerbi"


def _normalise_for_csv(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        series = result[column]
        if series.dtype == "object":
            result[column] = series.map(
                lambda value: "|".join(map(str, value))
                if isinstance(value, (list, tuple, np.ndarray))
                else json.dumps(value, default=str)
                if isinstance(value, dict)
                else value
            )
    return result


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _normalise_for_csv(frame).to_csv(path, index=False, lineterminator="\n")


def _require_processed(name: str) -> pd.DataFrame:
    path = PATHS["data_processed"] / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run validation first: make validate")
    return pd.read_csv(path)


def _readable_lot_labels(parking: pd.DataFrame) -> pd.Series:
    """Build a label a BD rep can act on.

    98 of the 120 candidates have no `name` tag in OpenStreetMap, so their
    lot_name is a machine identifier like "OSM Parking node-786590777". Prefixing
    the lot code made that longer, not clearer, and a business-facing target list
    that reads "OSM Parking node-786590777" cannot be worked from.

    We do not invent names. Where OSM supplies one it is used verbatim; otherwise
    the label states what the asset is and where it is, which is exactly what the
    public data supports. `lot_code` and `osm_id` remain on the table for exact
    identification, and the code is appended only to break a genuine tie.
    """
    names = parking["lot_name"].fillna("").astype(str)
    machine_generated = names.str.match(r"OSM Parking (node|way|relation)-\d+")
    locality_name = parking["locality_name"].fillna("Delhi NCR").astype(str)
    descriptive = parking["parking_type"].fillna("Parking").astype(str) + " · " + locality_name
    labels = names.where(~machine_generated, descriptive)
    # Several unnamed lots can share a type and locality. Disambiguate only those,
    # and keep the suffix short: a "[LOT-0001]" tail was truncated away in table
    # cells, leaving three different lots displaying identical text.
    duplicated = labels.duplicated(keep=False)
    short_code = parking["lot_code"].astype(str).str.extract(r"(\d+)", expand=False).str.lstrip("0")
    return labels.where(~duplicated, labels + " #" + short_code.fillna(""))


def build_powerbi_frames(inputs: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build a star-schema-shaped set of portable tables."""
    parking_dashboard = _require_processed("parking_dashboard.csv")
    locality_dashboard = _require_processed("locality_dashboard.csv")
    sensitivity = _require_processed("sensitivity_dashboard.csv")
    locality_sensitivity = _require_processed("locality_sensitivity_dashboard.csv")
    funnel = _require_processed("bd_funnel_dashboard.csv")
    bd_conversion = _require_processed("bd_conversion_dashboard.csv")

    parking_columns = [
        "parking_id",
        "lot_code",
        "lot_name",
        "locality_id",
        "owner_id",
        "latitude",
        "longitude",
        "parking_type",
        "surface_type",
        "capacity_cars",
        "hourly_rate_inr",
        "monthly_pass_inr",
        "is_24x7",
        "opens_at",
        "closes_at",
        "has_covered_parking",
        "has_security_staff",
        "has_cctv",
        "record_source",
        "source_name",
        "source_reference",
        "source_observed_on",
        "data_quality_flag",
        "osm_id",
    ]
    dim_parking = inputs["parking"][parking_columns].copy()
    dim_parking["parking_display_name"] = _readable_lot_labels(inputs["parking"])
    dim_parking["capacity_segment"] = pd.qcut(
        dim_parking["capacity_cars"],
        q=4,
        labels=["Q1 Small", "Q2 Medium", "Q3 Large", "Q4 Very Large"],
        duplicates="drop",
    ).astype(str)
    dim_parking["operating_hours_label"] = np.where(
        dim_parking["is_24x7"].astype(bool),
        "24 hours",
        dim_parking["opens_at"].fillna("").astype(str).str[:5]
        + "-"
        + dim_parking["closes_at"].fillna("").astype(str).str[:5],
    )

    locality_metric_columns = [
        "locality_id",
        "parking_count",
        "total_capacity",
        "avg_occupancy_pct",
        "avg_demand_score",
        "avg_revenue_score",
        "avg_competition_score",
        "avg_strategic_fit",
        "avg_feasibility",
        "avg_acquisition_score",
        "high_priority_count",
        "acquisition_opportunities",
        "avg_competitor_count_1km",
        "parkitup_site_count",
        "parkitup_capacity",
        "parkitup_coverage_pct",
        "market_whitespace_score",
        "whitespace_rank",
        "market_class",
        "whitespace_indicator",
    ]
    dim_locality = inputs["localities"].merge(
        locality_dashboard[locality_metric_columns], on="locality_id", how="left", validate="one_to_one"
    )

    score_columns = [
        "parking_id",
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
        "expected_commission_pct",
        "estimated_onboarding_cost_inr",
        "documentation_readiness",
        "operational_complexity",
        "requires_capex",
        "exclusivity_possible",
        "estimated_setup_days",
        "competitor_count_500m",
        "competitor_count_1km",
        "competitor_distance_proxy_m",
        "aggregator_listed_count_1km",
        "aggregator_penetration_rate",
        "competitor_avg_hourly_rate_inr",
        "nearest_live_network_distance_km",
        "live_network_site_count",
        "live_network_capacity_cars",
        "avg_daily_platform_bookings",
        "avg_daily_gross_revenue_inr",
    ]
    fact_acquisition = inputs["acquisition_scores"][score_columns].copy()
    dashboard_columns = [
        "parking_id",
        "rank_stability_pct",
        "stability_class",
        "top_10_frequency_pct",
        "top_20_frequency_pct",
        "average_rank",
        "best_rank",
        "worst_rank",
        "rank_standard_deviation",
        "positive_reason_flags",
        "constraint_reason_flags",
        "recommendation",
        "avg_daily_bookings",
        "avg_daily_revenue_inr",
        "revenue_per_space_inr",
        "bookings_per_space",
        "revenue_per_occupied_space_inr",
    ]
    fact_acquisition = fact_acquisition.merge(
        parking_dashboard[dashboard_columns], on="parking_id", how="left", validate="one_to_one"
    )

    scenario_dimension_columns = [
        "scenario_code",
        "scenario_group",
        "scenario_description",
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
    dim_scenario = (
        sensitivity[scenario_dimension_columns]
        .drop_duplicates("scenario_code")
        .sort_values(["scenario_group", "scenario_code"])
        .reset_index(drop=True)
    )
    dim_scenario.insert(0, "scenario_id", np.arange(1, len(dim_scenario) + 1, dtype=int))
    scenario_id = dim_scenario.set_index("scenario_code")["scenario_id"]
    fact_scenario = sensitivity.copy()
    fact_scenario.insert(0, "scenario_id", fact_scenario["scenario_code"].map(scenario_id).astype(int))
    fact_scenario = fact_scenario.drop(columns=scenario_dimension_columns)

    score_dimension_lookup = inputs["score_dimensions"][
        ["dimension_code", "dimension_name", "pillar_group", "display_order", "description"]
    ].copy()
    base_components = inputs["dimension_scores"]
    default_weight_set = inputs["scoring_weights"].loc[
        inputs["scoring_weights"]["is_default"].astype(bool), "weight_set_id"
    ].drop_duplicates()
    if len(default_weight_set) != 1:
        raise ValueError("Exactly one default weight set is required for FactScoreComponent")
    fact_score_component = base_components[
        base_components["weight_set_id"].eq(int(default_weight_set.iloc[0]))
    ][
        ["parking_id", "dimension_code", "subscore", "weight_applied", "weighted_contribution"]
    ].copy()

    scenario_component_rows: list[pd.DataFrame] = []
    component_map = {
        "DEMAND": "demand_score",
        "REVENUE": "revenue_score",
        "COMPETITION": "competition_score",
        "STRATEGIC_FIT": "strategic_fit_score",
        "FEASIBILITY": "feasibility_score",
    }
    weight_map = {
        "DEMAND": "demand_weight",
        "REVENUE": "revenue_weight",
        "COMPETITION": "competition_weight",
        "STRATEGIC_FIT": "strategic_fit_weight",
        "FEASIBILITY": "feasibility_weight",
    }
    scenario_source = sensitivity.copy()
    for dimension_code, score_column in component_map.items():
        part = scenario_source[["parking_id", "scenario_code", score_column, weight_map[dimension_code]]].copy()
        part["scenario_id"] = part["scenario_code"].map(scenario_id).astype(int)
        part["dimension_code"] = dimension_code
        part = part.rename(columns={score_column: "subscore", weight_map[dimension_code]: "weight_applied"})
        part["weighted_contribution"] = part["subscore"] * part["weight_applied"]
        scenario_component_rows.append(
            part[["parking_id", "scenario_id", "dimension_code", "subscore", "weight_applied", "weighted_contribution"]]
        )
    fact_scenario_component = pd.concat(scenario_component_rows, ignore_index=True)
    fact_locality_scenario = locality_sensitivity.copy()
    fact_locality_scenario.insert(
        0, "scenario_id", fact_locality_scenario["scenario_code"].map(scenario_id).astype(int)
    )
    fact_locality_scenario = fact_locality_scenario.drop(columns=["scenario_code", "scenario_group"])

    outreach_columns = [
        "lead_id",
        "parking_id",
        "lead_source",
        "first_contact_date",
        "contact_attempts",
        "furthest_stage_id",
        "furthest_stage_order",
        "pipeline_status",
        "lost_reason",
        "documents_available",
        "owner_interest_level",
        "conversion_date",
        "assigned_bd_rep",
        "days_to_conversion",
    ]
    fact_outreach = inputs["outreach"][outreach_columns].copy()
    fact_outreach_event = inputs["outreach_events"][
        ["event_id", "lead_id", "stage_id", "event_date", "channel"]
    ].copy()

    daily_columns = [
        "parking_id",
        "activity_date",
        "peak_occupancy_rate",
        "avg_occupancy_rate",
        "vehicle_entries",
        "platform_bookings",
        "booking_cancellations",
        "gross_parking_revenue_inr",
        "avg_park_duration_hours",
    ]
    hourly_columns = ["parking_id", "day_type", "hour_of_day", "avg_occupancy_rate", "avg_entries"]

    dim_owner = inputs["owners"].copy()
    dim_owner["digital_readiness"] = np.where(
        dim_owner["digital_payment_enabled"].astype(bool)
        & dim_owner["management_system"].ne("Manual"),
        "Digitally Ready",
        "Needs Enablement",
    )
    segment_order = {"ACQUIRE_NOW": 1, "PURSUE": 2, "DEVELOP": 3, "AVOID": 4}
    segment_colour = {
        "ACQUIRE_NOW": "#0B6E4F",
        "PURSUE": "#D97706",
        "DEVELOP": "#2563EB",
        "AVOID": "#6B7280",
    }
    dim_priority = inputs["segment_rules"].copy()
    dim_priority["segment_sort_order"] = dim_priority["segment_code"].map(segment_order).astype(int)
    dim_priority["segment_colour_hex"] = dim_priority["segment_code"].map(segment_colour)

    return {
        "DimParking": dim_parking,
        "DimOwner": dim_owner,
        "DimLocality": dim_locality,
        "DimDate": inputs["dates"].copy(),
        "DimFunnelStage": inputs["funnel_stages"].copy(),
        "DimScenario": dim_scenario,
        "DimScoreDimension": score_dimension_lookup,
        "DimPrioritySegment": dim_priority,
        "FactDailyPerformance": inputs["daily_performance"][daily_columns].copy(),
        "FactHourlyProfile": inputs["hourly_profile"][hourly_columns].copy(),
        "FactAcquisitionScore": fact_acquisition,
        "FactScoreComponent": fact_score_component,
        "FactScenarioScore": fact_scenario,
        "FactScenarioComponent": fact_scenario_component,
        "FactLocalityScenario": fact_locality_scenario,
        "FactOutreach": fact_outreach,
        "FactOutreachEvent": fact_outreach_event,
        "AggBDFunnel": funnel,
        "AggBDConversion": bd_conversion,
    }


def _selected_parking_ids(frames: Mapping[str, pd.DataFrame], context: Mapping[str, Any]) -> set[int]:
    parking = frames["DimParking"].copy()
    locality = frames["DimLocality"]
    scores = frames["FactAcquisitionScore"]
    ids = set(parking["parking_id"].astype(int))
    if context.get("locality_name") is not None:
        locality_ids = set(
            locality.loc[locality["locality_name"].eq(context["locality_name"]), "locality_id"].astype(int)
        )
        ids &= set(parking.loc[parking["locality_id"].isin(locality_ids), "parking_id"].astype(int))
    if context.get("priority_segment") is not None:
        ids &= set(
            scores.loc[scores["priority_segment"].eq(context["priority_segment"]), "parking_id"].astype(int)
        )
    if context.get("parking_id") is not None:
        ids &= {int(context["parking_id"])}
    return ids


def compute_powerbi_metrics(
    frames: Mapping[str, pd.DataFrame], context: Mapping[str, Any] | None = None
) -> dict[str, float]:
    """Python equivalents of the documented core DAX measures."""
    filters = dict(context or {})
    parking_ids = _selected_parking_ids(frames, filters)
    parking = frames["DimParking"]
    locality = frames["DimLocality"]
    scores = frames["FactAcquisitionScore"]
    daily = frames["FactDailyPerformance"]
    outreach = frames["FactOutreach"]

    selected_parking = parking[parking["parking_id"].isin(parking_ids)]
    selected_scores = scores[scores["parking_id"].isin(parking_ids)]
    selected_daily = daily[daily["parking_id"].isin(parking_ids)]
    selected_outreach = outreach[outreach["parking_id"].isin(parking_ids)]
    selected_locality_ids = set(selected_parking["locality_id"].astype(int))
    selected_localities = locality[locality["locality_id"].isin(selected_locality_ids)]

    lead_count = selected_outreach["lead_id"].nunique()
    won_count = selected_outreach.loc[selected_outreach["pipeline_status"].eq("Won"), "lead_id"].nunique()
    return {
        "Total Parking Lots": float(selected_parking["parking_id"].nunique()),
        "Total Capacity": float(selected_parking["capacity_cars"].sum()),
        "Average Occupancy Pct": float(selected_daily["avg_occupancy_rate"].mean() * 100.0)
        if len(selected_daily)
        else 0.0,
        "Total Revenue INR": float(selected_daily["gross_parking_revenue_inr"].sum()),
        "High Priority Count": float((selected_scores["priority_segment"] == "ACQUIRE_NOW").sum()),
        "Expected Monthly Platform Revenue INR": float(
            selected_scores["expected_monthly_platform_revenue_inr"].sum()
        ),
        "Average Acquisition Score": float(selected_scores["acquisition_score"].mean())
        if len(selected_scores)
        else 0.0,
        "Markets Analyzed": float(selected_localities["locality_id"].nunique()),
        "High Opportunity Markets": float((selected_localities["market_class"] == "STRONG").sum()),
        "BD Conversion Rate Pct": float(won_count / lead_count * 100.0) if lead_count else 0.0,
    }


def _frame_checks(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check_id: str, description: str, passed: bool, observed: Any) -> None:
        rows.append(
            {
                "check_id": check_id,
                "description": description,
                "observed": observed,
                "status": "PASS" if passed else "FAIL",
            }
        )

    expected_rows = {
        "DimParking": 120,
        "DimOwner": 72,
        "DimLocality": 17,
        "DimDate": 365,
        "DimFunnelStage": 7,
        "DimScenario": 11,
        "DimScoreDimension": 5,
        "DimPrioritySegment": 4,
        "FactDailyPerformance": 43_800,
        "FactHourlyProfile": 5_760,
        "FactAcquisitionScore": 120,
        "FactScoreComponent": 600,
        "FactScenarioScore": 1_320,
        "FactScenarioComponent": 6_600,
        "FactLocalityScenario": 187,
        "FactOutreach": 120,
        "FactOutreachEvent": 385,
        "AggBDFunnel": 7,
        "AggBDConversion": 36,
    }
    for name, expected in expected_rows.items():
        add(f"ROWS-{name}", f"{name} has its documented grain", len(frames[name]) == expected, len(frames[name]))

    unique_keys = {
        "DimParking": ["parking_id"],
        "DimOwner": ["owner_id"],
        "DimLocality": ["locality_id"],
        "DimDate": ["activity_date"],
        "DimFunnelStage": ["stage_id"],
        "DimScenario": ["scenario_id"],
        "DimScoreDimension": ["dimension_code"],
        "DimPrioritySegment": ["segment_code"],
        "FactAcquisitionScore": ["parking_id"],
        "FactScoreComponent": ["parking_id", "dimension_code"],
        "FactScenarioScore": ["parking_id", "scenario_id"],
        "FactScenarioComponent": ["parking_id", "scenario_id", "dimension_code"],
        "FactLocalityScenario": ["locality_id", "scenario_id"],
        "FactOutreach": ["lead_id"],
        "FactOutreachEvent": ["event_id"],
    }
    for name, columns in unique_keys.items():
        duplicates = int(frames[name].duplicated(columns).sum())
        add(f"KEY-{name}", f"{name} key is unique", duplicates == 0, duplicates)

    parking_ids = set(frames["DimParking"]["parking_id"].astype(int))
    locality_ids = set(frames["DimLocality"]["locality_id"].astype(int))
    owner_ids = set(frames["DimOwner"]["owner_id"].astype(int))
    lead_ids = set(frames["FactOutreach"]["lead_id"].astype(int))
    add(
        "FK-DimParking-Locality",
        "Every parking locality exists",
        set(frames["DimParking"]["locality_id"].astype(int)) <= locality_ids,
        len(set(frames["DimParking"]["locality_id"].astype(int)) - locality_ids),
    )
    add(
        "FK-DimParking-Owner",
        "Every parking owner exists",
        set(frames["DimParking"]["owner_id"].astype(int)) <= owner_ids,
        len(set(frames["DimParking"]["owner_id"].astype(int)) - owner_ids),
    )
    for name in [
        "FactDailyPerformance",
        "FactHourlyProfile",
        "FactAcquisitionScore",
        "FactScoreComponent",
        "FactScenarioScore",
        "FactScenarioComponent",
        "FactOutreach",
    ]:
        orphans = set(frames[name]["parking_id"].astype(int)) - parking_ids
        add(f"FK-{name}-Parking", f"{name} parking keys resolve", not orphans, len(orphans))
    event_orphans = set(frames["FactOutreachEvent"]["lead_id"].astype(int)) - lead_ids
    add("FK-Event-Lead", "Outreach-event leads resolve", not event_orphans, len(event_orphans))
    return pd.DataFrame(rows)


def _reconciliation(source_frames: Mapping[str, pd.DataFrame], exported_frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    contexts = {
        "ALL": {},
        "CONNAUGHT_PLACE": {"locality_name": "Connaught Place"},
        "ACQUIRE_NOW": {"priority_segment": "ACQUIRE_NOW"},
        "CONNAUGHT_ACQUIRE_NOW": {"locality_name": "Connaught Place", "priority_segment": "ACQUIRE_NOW"},
        "PARKING_52": {"parking_id": 52},
    }
    rows: list[dict[str, Any]] = []
    for scope, context in contexts.items():
        expected = compute_powerbi_metrics(source_frames, context)
        observed = compute_powerbi_metrics(exported_frames, context)
        for metric, expected_value in expected.items():
            observed_value = observed[metric]
            difference = abs(expected_value - observed_value)
            tolerance = 1e-6 * max(1.0, abs(expected_value))
            rows.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "source_value": expected_value,
                    "portable_model_value": observed_value,
                    "absolute_difference": difference,
                    "status": "PASS" if difference <= tolerance else "FAIL",
                }
            )

    source_top10 = source_frames["FactAcquisitionScore"].nsmallest(10, "acquisition_rank")[
        ["parking_id", "acquisition_rank", "acquisition_score"]
    ]
    exported_top10 = exported_frames["FactAcquisitionScore"].nsmallest(10, "acquisition_rank")[
        ["parking_id", "acquisition_rank", "acquisition_score"]
    ]
    for expected, observed in zip(source_top10.itertuples(index=False), exported_top10.itertuples(index=False)):
        passed = (
            int(expected.parking_id) == int(observed.parking_id)
            and int(expected.acquisition_rank) == int(observed.acquisition_rank)
            and abs(float(expected.acquisition_score) - float(observed.acquisition_score)) <= 1e-8
        )
        rows.append(
            {
                "scope": "TOP_10",
                "metric": f"Rank {int(expected.acquisition_rank)} parking_id",
                "source_value": int(expected.parking_id),
                "portable_model_value": int(observed.parking_id),
                "absolute_difference": abs(int(expected.parking_id) - int(observed.parking_id)),
                "status": "PASS" if passed else "FAIL",
            }
        )
    return pd.DataFrame(rows)


def _reload_exports(frames: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    date_columns = {
        "DimDate": ["activity_date"],
        "FactDailyPerformance": ["activity_date"],
        "FactOutreach": ["first_contact_date", "conversion_date"],
        "FactOutreachEvent": ["event_date"],
    }
    result: dict[str, pd.DataFrame] = {}
    for name in frames:
        path = POWERBI_DATA_DIR / f"{name}.csv"
        result[name] = pd.read_csv(path, parse_dates=[c for c in date_columns.get(name, []) if c in pd.read_csv(path, nrows=0).columns])
    return result


def run_powerbi_data_prep() -> dict[str, Any]:
    names = [
        "parking",
        "owners",
        "localities",
        "dates",
        "funnel_stages",
        "score_dimensions",
        "segment_rules",
        "scoring_weights",
        "dimension_scores",
        "acquisition_scores",
        "daily_performance",
        "hourly_profile",
        "outreach",
        "outreach_events",
    ]
    inputs = load_analysis_inputs(names)
    frames = build_powerbi_frames(inputs)
    checks = _frame_checks(frames)
    if (checks["status"] == "FAIL").any():
        raise ValueError("Power BI model contract failed:\n" + checks[checks["status"] == "FAIL"].to_string(index=False))

    for name, frame in frames.items():
        _write_csv(frame, POWERBI_DATA_DIR / f"{name}.csv")
    exported = _reload_exports(frames)
    reconciliation = _reconciliation(frames, exported)
    if (reconciliation["status"] == "FAIL").any():
        raise ValueError(
            "Power BI reconciliation failed:\n"
            + reconciliation[reconciliation["status"] == "FAIL"].to_string(index=False)
        )

    validation_dir = PATHS["validation"]
    _write_csv(checks, validation_dir / "powerbi_model_checks.csv")
    _write_csv(reconciliation, validation_dir / "powerbi_reconciliation.csv")
    metrics = compute_powerbi_metrics(frames)
    top10 = frames["FactAcquisitionScore"].nsmallest(10, "acquisition_rank").merge(
        frames["DimParking"][["parking_id", "lot_name", "locality_id"]], on="parking_id", how="left"
    ).merge(
        frames["DimLocality"][["locality_id", "locality_name"]], on="locality_id", how="left"
    )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": "macOS ARM64",
        "powerbi_desktop_available": False,
        "pbix_created": False,
        "pbip_created": False,
        "implementation_package_created": True,
        "database": settings.summary(),
        "row_counts": {name: int(len(frame)) for name, frame in frames.items()},
        "core_metrics": metrics,
        "top_10": top10[
            ["acquisition_rank", "parking_id", "lot_name", "locality_name", "acquisition_score", "priority_segment"]
        ].to_dict(orient="records"),
        "model_checks": checks["status"].value_counts().to_dict(),
        "reconciliation_checks": reconciliation["status"].value_counts().to_dict(),
        "portable_data_directory": str(POWERBI_DATA_DIR.relative_to(REPO_ROOT)),
        "package_directory": str(POWERBI_PACKAGE_DIR.relative_to(REPO_ROOT)),
    }
    (validation_dir / "powerbi_execution_summary.json").write_text(
        json.dumps(summary, indent=2, default=lambda value: value.item() if isinstance(value, np.generic) else str(value))
        + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    summary = run_powerbi_data_prep()
    print("dashboard portable Power BI model prepared and reconciled")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
