"""Automated row, relationship, and business-logic checks for the data pipeline."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable

import numpy as np
import pandas as pd

from python.config import settings


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    severity: str
    dataset: str
    description: str
    violations: int
    status: str
    observed_value: str = ""


def _result(
    rule_id: str,
    severity: str,
    dataset: str,
    description: str,
    violations: int,
    observed_value: str = "",
) -> CheckResult:
    return CheckResult(
        rule_id,
        severity,
        dataset,
        description,
        int(violations),
        "PASS" if int(violations) == 0 else "FAIL",
        observed_value,
    )


def validate_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lots = tables["parking_lots"]
    localities = tables["dim_locality"]
    demand = tables["location_demand"]
    competition = tables["competition"]
    daily = tables["fact_lot_daily"]
    hourly = tables["fact_lot_hourly_profile"]
    owners = tables["owners"]
    terms = tables["lot_acquisition_terms"]
    outreach = tables["outreach"]
    events = tables["outreach_events"]
    expected_days = settings.observation_days()
    lot_ids = set(lots["parking_id"])

    checks = [
        _result("PY-001", "ERROR", "parking_lots", "parking_id is unique", lots["parking_id"].duplicated().sum()),
        _result("PY-002", "ERROR", "parking_lots", "lot_code is unique", lots["lot_code"].duplicated().sum()),
        _result("PY-003", "ERROR", "parking_lots", "capacity is between 10 and 2000", (~lots["capacity_cars"].between(10, 2000)).sum()),
        _result("PY-004", "ERROR", "parking_lots", "hourly price is between 0 and 500", (~lots["hourly_rate_inr"].between(0, 500)).sum()),
        _result("PY-005", "ERROR", "parking_lots", "coordinates are inside the configured NCR box", ((~lots["latitude"].between(settings.lat_min, settings.lat_max)) | (~lots["longitude"].between(settings.lon_min, settings.lon_max))).sum()),
        _result("PY-006", "ERROR", "parking_lots", "every lot references a valid locality", (~lots["locality_id"].isin(localities["locality_id"])).sum()),
        _result("PY-007", "ERROR", "parking_lots", "all public OSM lots carry an OSM id and source reference", ((lots["record_source"] == "public_osm") & (lots["osm_id"].isna() | lots["source_reference"].isna())).sum()),
        _result("PY-008", "ERROR", "parking_lots", "no approximate duplicate coordinates at six decimal places", lots.duplicated(["latitude", "longitude"]).sum()),
        _result("PY-010", "ERROR", "location_demand", "one demand row exists per lot", len(lot_ids.symmetric_difference(set(demand["parking_id"]))), f"rows={len(demand)}"),
        _result("PY-011", "ERROR", "location_demand", "all POI counts and distances are non-negative", (demand[["metro_distance_m", "office_count_500m", "retail_count_500m", "restaurant_count_500m", "hospital_count_1km", "education_count_1km", "transit_stop_count_500m"]].fillna(0) < 0).any(axis=1).sum()),
        _result("PY-012", "ERROR", "competition", "one competition row exists per lot", len(lot_ids.symmetric_difference(set(competition["parking_id"]))), f"rows={len(competition)}"),
        _result("PY-013", "ERROR", "competition", "500m count never exceeds 1km count", (competition["competitor_count_500m"] > competition["competitor_count_1km"]).sum()),
        _result("PY-014", "ERROR", "competition", "competition counts and distances are non-negative", ((competition[["competitor_count_500m", "competitor_count_1km"]] < 0).any(axis=1) | (competition["nearest_competitor_distance_m"].dropna() < 0).reindex(competition.index, fill_value=False)).sum()),
        _result("PY-015", "ERROR", "competition", "aggregator count is a subset of competitors", (competition["aggregator_listed_count_1km"] > competition["competitor_count_1km"]).sum()),
        _result("PY-020", "ERROR", "fact_lot_daily", "daily primary key is unique", daily.duplicated(["parking_id", "activity_date"]).sum()),
        _result("PY-021", "ERROR", "fact_lot_daily", "every lot has exactly the full observation window", (daily.groupby("parking_id").size().reindex(lots["parking_id"], fill_value=0) != expected_days).sum(), f"expected_per_lot={expected_days}"),
        _result("PY-022", "ERROR", "fact_lot_daily", "occupancy is within 0-1 and mean does not exceed peak", ((~daily["avg_occupancy_rate"].between(0, 1)) | (~daily["peak_occupancy_rate"].between(0, 1)) | (daily["avg_occupancy_rate"] > daily["peak_occupancy_rate"])).sum()),
        _result("PY-023", "ERROR", "fact_lot_daily", "bookings and cancellations are logical subsets", ((daily["vehicle_entries"] < 0) | (daily["platform_bookings"] < 0) | (daily["platform_bookings"] > daily["vehicle_entries"]) | (daily["booking_cancellations"] > daily["platform_bookings"])).sum()),
        _result("PY-024", "ERROR", "fact_lot_daily", "revenue is non-negative and non-zero when paid activity exists", ((daily["gross_parking_revenue_inr"] < 0) | ((daily["vehicle_entries"] > 0) & (daily["gross_parking_revenue_inr"] <= 0))).sum()),
        _result("PY-025", "ERROR", "fact_lot_hourly_profile", "every lot has exactly 48 hourly profile rows", (hourly.groupby("parking_id").size().reindex(lots["parking_id"], fill_value=0) != 48).sum()),
        _result("PY-026", "ERROR", "fact_lot_hourly_profile", "hourly keys are unique and values valid", hourly.duplicated(["parking_id", "day_type", "hour_of_day"]).sum() + ((~hourly["avg_occupancy_rate"].between(0, 1)) | (hourly["avg_entries"] < 0)).sum()),
        _result("PY-030", "ERROR", "owners", "owner codes and ids are unique", owners["owner_id"].duplicated().sum() + owners["owner_code"].duplicated().sum()),
        _result("PY-031", "ERROR", "owners", "owner readiness ordinals are within 1-5", ((~owners["willingness_to_digitize"].between(1, 5)) | (~owners["contract_flexibility"].between(1, 5))).sum()),
        _result("PY-032", "ERROR", "lot_acquisition_terms", "one non-negative, valid terms row exists per lot", len(lot_ids.symmetric_difference(set(terms["parking_id"]))) + ((terms["estimated_onboarding_cost_inr"] < 0) | (~terms["documentation_readiness"].between(1, 5)) | (~terms["operational_complexity"].between(1, 5))).sum()),
        _result("PY-040", "ERROR", "outreach", "one outreach row exists per lot", len(lot_ids.symmetric_difference(set(outreach["parking_id"]))), f"rows={len(outreach)}"),
        _result("PY-041", "ERROR", "outreach", "won status and conversion fields are consistent", (((outreach["pipeline_status"] == "Won") != outreach["conversion_date"].notna()) | ((outreach["pipeline_status"] == "Won") != (outreach["furthest_stage_id"] == 7))).sum()),
        _result("PY-042", "ERROR", "outreach", "lost status and lost reason are consistent", ((outreach["pipeline_status"] == "Lost") != outreach["lost_reason"].notna()).sum()),
        _result("PY-043", "ERROR", "outreach", "contact attempts and contact date are consistent", ((outreach["contact_attempts"] > 0) != outreach["first_contact_date"].notna()).sum()),
        _result("PY-044", "ERROR", "outreach_events", "events are contiguous from stage 1 through the furthest stage", sum(set(group["stage_id"]) != set(range(1, int(outreach.set_index("lead_id").loc[lead_id, "furthest_stage_id"]) + 1)) for lead_id, group in events.groupby("lead_id"))),
        _result("PY-045", "ERROR", "outreach_events", "event dates are non-decreasing within each lead", sum((pd.to_datetime(group.sort_values("stage_id")["event_date"]).diff().dropna().dt.days < 0).any() for _, group in events.groupby("lead_id"))),
    ]
    return pd.DataFrame(asdict(check) for check in checks)


def business_logic_checks(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lots = tables["parking_lots"]
    demand = tables["location_demand"]
    competition = tables["competition"]
    daily = tables["fact_lot_daily"]
    owners = tables["owners"]
    outreach = tables["outreach"]
    terms = tables["lot_acquisition_terms"]

    lot_perf = daily.groupby("parking_id").agg(
        avg_occupancy=("avg_occupancy_rate", "mean"),
        avg_daily_revenue=("gross_parking_revenue_inr", "mean"),
        avg_daily_bookings=("platform_bookings", "mean"),
    ).reset_index()
    joined = lots.merge(demand, on="parking_id").merge(competition, on="parking_id").merge(
        lot_perf, on="parking_id"
    )
    demand_proxy = (
        0.30 * np.exp(-joined["metro_distance_m"].astype(float) / 1200)
        + 0.25 * joined["office_count_500m"].rank(pct=True)
        + 0.20 * joined["retail_count_500m"].rank(pct=True)
        + 0.15 * joined["restaurant_count_500m"].rank(pct=True)
        + 0.10 * joined["transit_stop_count_500m"].rank(pct=True)
    )
    demand_occ = float(demand_proxy.corr(joined["avg_occupancy"]))
    price_revenue = float(joined["hourly_rate_inr"].corr(joined["avg_daily_revenue"]))
    capacity_revenue = float(joined["capacity_cars"].corr(joined["avg_daily_revenue"]))
    competition_occ = float(joined["competitor_count_1km"].corr(joined["avg_occupancy"]))

    owner_funnel = (
        lots[["parking_id", "owner_id"]]
        .merge(owners, on="owner_id")
        .merge(terms[["parking_id", "documentation_readiness"]], on="parking_id")
        .merge(outreach[["parking_id", "furthest_stage_id", "pipeline_status"]], on="parking_id")
    )
    readiness = (
        owner_funnel["willingness_to_digitize"]
        + owner_funnel["contract_flexibility"]
        + owner_funnel["documentation_readiness"]
        + owner_funnel["digital_payment_enabled"].astype(int) * 2
        + owner_funnel["decision_maker_accessible"].astype(int) * 2
    )
    readiness_stage = float(readiness.corr(owner_funnel["furthest_stage_id"]))
    interest_stage = float(
        outreach["owner_interest_level"].corr(outreach["furthest_stage_id"])
    )

    specs = [
        ("BL-001", "Demand proxy has a positive, non-perfect tendency with occupancy", demand_occ, 0.18 <= demand_occ <= 0.92, "0.18 to 0.92"),
        ("BL-002", "Higher tariff contributes to revenue but does not determine it", price_revenue, 0.05 <= price_revenue <= 0.85, "0.05 to 0.85"),
        ("BL-003", "Capacity helps revenue without becoming a perfect proxy", capacity_revenue, 0.18 <= capacity_revenue <= 0.92, "0.18 to 0.92"),
        ("BL-004", "Competition does not create an implausibly strong positive occupancy effect", competition_occ, competition_occ <= 0.55, "at most 0.55"),
        ("BL-005", "Owner readiness tends to improve funnel progress without determining it", readiness_stage, 0.12 <= readiness_stage <= 0.88, "0.12 to 0.88"),
        ("BL-006", "Observed owner interest tends to improve funnel progress", interest_stage, 0.12 <= interest_stage <= 0.92, "0.12 to 0.92"),
    ]
    return pd.DataFrame(
        {
            "rule_id": rule_id,
            "severity": "ERROR",
            "dataset": "cross_table",
            "description": description,
            "violations": 0 if passed else 1,
            "status": "PASS" if passed else "FAIL",
            "observed_value": f"correlation={value:.4f}; expected {expected}",
        }
        for rule_id, description, value, passed, expected in specs
    )


def assert_valid(results: pd.DataFrame, *, label: str) -> None:
    failures = results[(results["status"] == "FAIL") & (results["severity"] == "ERROR")]
    if not failures.empty:
        rendered = failures[["rule_id", "description", "observed_value"]].to_string(index=False)
        raise ValueError(f"{label} failed:\n{rendered}")
