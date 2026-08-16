"""Build the machine-readable source field lineage and dictionary supplement."""

from __future__ import annotations

from typing import Any

import pandas as pd


PUBLIC_PARKING_FIELDS = {
    "latitude", "longitude", "osm_id", "source_name", "source_reference", "source_observed_on"
}
DERIVED_PARKING_FIELDS = {"lot_name", "data_quality_flag"}
SYNTHETIC_PARKING_FIELDS = {
    "owner_id", "surface_type", "capacity_cars", "hourly_rate_inr", "monthly_pass_inr",
    "is_24x7", "opens_at", "closes_at", "has_covered_parking", "has_security_staff",
    "has_cctv", "created_at",
}
CONFIG_FIELDS = {
    "parking_id", "lot_code", "locality_id", "owner_code", "lead_id", "event_id",
    "network_site_id", "site_code", "record_source", "measured_on", "quoted_on",
    "capacity_source_type", "price_source_type", "hours_source_type",
    "amenities_source_type", "assigned_bd_rep",
}

DEFINITIONS = {
    "parking_id": "Stable key for one candidate parking facility.",
    "locality_id": "Key for the selected Delhi NCR micro-market.",
    "owner_id": "Key for the simulated operator controlling the lot.",
    "latitude": "WGS84 latitude of the OSM parking feature centroid or node.",
    "longitude": "WGS84 longitude of the OSM parking feature centroid or node.",
    "capacity_cars": "Concurrent four-wheeler bay capacity.",
    "hourly_rate_inr": "Synthetic customer tariff in Indian rupees per hour.",
    "metro_distance_m": "Great-circle distance to the nearest OSM metro station, metres.",
    "mall_distance_m": "Great-circle distance to the nearest OSM mall/retail building, metres.",
    "competitor_count_500m": "Directly comparable OSM parking facilities within 500 metres.",
    "competitor_count_1km": "Directly comparable OSM parking facilities within one kilometre.",
    "nearest_competitor_distance_m": "Great-circle distance to the nearest direct competitor within one kilometre.",
    "competitor_total_capacity_1km": "Sum of published OSM capacities among direct competitors within one kilometre; null when none publish capacity.",
    "avg_occupancy_rate": "Mean occupied share of capacity, expressed from 0 to 1.",
    "peak_occupancy_rate": "Maximum concurrent occupied share that day, expressed from 0 to 1.",
    "vehicle_entries": "Vehicles served across all channels during the day.",
    "platform_bookings": "Synthetic subset of vehicle entries attributed to the platform.",
    "booking_cancellations": "Synthetic cancelled subset of platform bookings.",
    "gross_parking_revenue_inr": "Synthetic gross daily parking revenue earned by the operator.",
    "days_to_conversion": "Conversion date minus first contact date in calendar days.",
    "furthest_stage_id": "Deepest sequential BD funnel stage reached by the lead.",
    "data_quality_flag": "Traceability/attribute completeness flag: High, Medium or Fallback.",
}

TYPE_OVERRIDES = {
    "latitude": "NUMERIC(9,6)",
    "longitude": "NUMERIC(9,6)",
    "hourly_rate_inr": "NUMERIC(6,2)",
    "monthly_pass_inr": "NUMERIC(8,2)",
    "expected_commission_pct": "NUMERIC(4,2)",
    "estimated_onboarding_cost_inr": "NUMERIC(10,2)",
    "gross_parking_revenue_inr": "NUMERIC(10,2)",
    "peak_occupancy_rate": "NUMERIC(5,4)",
    "avg_occupancy_rate": "NUMERIC(5,4)",
    "avg_park_duration_hours": "NUMERIC(4,2)",
    "avg_entries": "NUMERIC(6,2)",
    "created_at": "TIMESTAMPTZ",
    "opens_at": "TIME",
    "closes_at": "TIME",
}

BOOLEAN_FIELDS = {
    "has_metro_station", "digital_payment_enabled", "decision_maker_accessible", "is_24x7",
    "has_covered_parking", "has_security_staff", "has_cctv", "exclusivity_possible",
    "requires_capex", "documents_available",
}
DATE_FIELDS = {
    "source_observed_on", "measured_on", "quoted_on", "activity_date", "live_since",
    "first_contact_date", "conversion_date", "event_date",
}


def _postgres_type(column: str) -> str:
    if column in TYPE_OVERRIDES:
        return TYPE_OVERRIDES[column]
    if column in BOOLEAN_FIELDS:
        return "BOOLEAN"
    if column in DATE_FIELDS:
        return "DATE"
    if column.endswith("_id") or column in {
        "capacity_cars", "years_operating", "metro_line_count", "office_count_500m",
        "retail_count_500m", "restaurant_count_500m", "hospital_count_1km",
        "education_count_1km", "transit_stop_count_500m", "competitor_count_500m",
        "competitor_count_1km", "competitor_total_capacity_1km",
        "aggregator_listed_count_1km", "documentation_readiness", "operational_complexity",
        "estimated_setup_days", "hour_of_day", "vehicle_entries", "platform_bookings",
        "booking_cancellations", "contact_attempts", "owner_interest_level",
        "days_to_conversion",
    }:
        return "INTEGER"
    return "TEXT"


def _classification(table: str, column: str) -> tuple[str, str, str, str]:
    """Return lineage type, source name, reference, and generation method."""
    osm_ref = "data/external/osm_features_snapshot.json"
    if table == "dim_locality":
        if column in {"locality_name", "has_metro_station"}:
            return "DERIVED", "OpenStreetMap", osm_ref, "Locality name from the curated scope; station presence calculated within 1.8km of its OSM centre."
        if column in {"micro_market_type", "population_density_band", "metro_line_count"}:
            return "ASSUMED", "Analyst classification", "data/external/micro_markets.csv", "Transparent market classification; metro line count is conservatively one when a station is observed."
        return "CONFIG", "source scope", "data/external/micro_markets.csv", "Stable key or row-level source label."
    if table == "owners":
        return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Owner digital maturity drives related payment, system, willingness and flexibility variables with noise."
    if table == "parking_lots":
        if column == "parking_type":
            return "ASSUMED", "OSM tags plus analyst type mix", "python/etl/synthetic_generation.py", "Uses an explicit OSM parking tag/name where present; otherwise applies a market-aware assumed type mix."
        if column in PUBLIC_PARKING_FIELDS:
            return "PUBLIC", "OpenStreetMap", osm_ref, "Copied from the cached OSM element or its source URL."
        if column in DERIVED_PARKING_FIELDS:
            return "DERIVED", "OpenStreetMap plus deterministic mapping", "python/etl/cleaning.py", "Normalised OSM name/type or calculated traceability flag."
        if column in SYNTHETIC_PARKING_FIELDS:
            return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Generated from parking type, market character and owner profile with a fixed seed."
        return "CONFIG", "ETL configuration", "python/config.py", "Stable key or explicit per-value provenance label."
    if table == "location_demand":
        if column in {"parking_id", "measured_on", "record_source"}:
            return "CONFIG", "ETL configuration", "python/config.py", "Join key, snapshot date or source label."
        return "DERIVED", "OpenStreetMap", osm_ref, "Haversine distance or radius count calculated from cached OSM coordinates."
    if table == "competition":
        if column == "competitor_avg_hourly_rate_inr" or column == "aggregator_listed_count_1km":
            return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Generated because comparable public tariff/platform-listing coverage is unavailable."
        if column in {"parking_id", "measured_on", "record_source"}:
            return "CONFIG", "ETL configuration", "python/config.py", "Join key, snapshot date or source label."
        return "DERIVED", "OpenStreetMap", osm_ref, "Radius count/distance from accessible comparable OSM parking; capacity sums only published capacity tags."
    if table in {"lot_acquisition_terms", "existing_network_sites", "fact_lot_daily", "fact_lot_hourly_profile"}:
        if column in CONFIG_FIELDS or column in {"activity_date", "day_type", "hour_of_day"}:
            return "CONFIG", "ETL configuration", "python/config.py", "Stable key or deterministic time grain."
        return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Relationship-aware simulation with fixed seed and documented noise."
    if table == "outreach":
        if column == "days_to_conversion":
            return "DERIVED", "PostgreSQL generated column", "database/schema/04_bd_pipeline.sql", "conversion_date minus first_contact_date."
        if column in {"lead_id", "parking_id", "assigned_bd_rep"}:
            return "CONFIG", "ETL configuration", "python/etl/synthetic_generation.py", "Stable join key or anonymous workload label."
        return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Sequential transition model driven by readiness, accessibility and lead-source quality with noise."
    if table == "outreach_events":
        if column in {"event_id", "lead_id", "stage_id"}:
            return "CONFIG", "Funnel configuration", "database/seeds/01_seed_reference.sql", "Stable key or sequential stage key."
        return "SYNTHETIC", "Deterministic generator", "python/etl/synthetic_generation.py", "Contiguous dated stage-entry sequence."
    return "CONFIG", "Project configuration", "README.md", "Project-managed field."


def _business_purpose(table: str, column: str) -> str:
    if table in {"location_demand", "fact_lot_daily", "fact_lot_hourly_profile"}:
        return "Demand and revenue analysis input"
    if table == "competition":
        return "Competition opportunity input"
    if table in {"owners", "lot_acquisition_terms", "outreach", "outreach_events"}:
        return "Acquisition feasibility and BD funnel input"
    if table == "existing_network_sites":
        return "Strategic coverage-gap input"
    if table == "dim_locality":
        return "Geographic grouping and market context"
    return "Master inventory, joins and auditability"


def build_field_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ordered_tables = [
        "dim_locality", "owners", "parking_lots", "location_demand", "competition",
        "lot_acquisition_terms", "existing_network_sites", "fact_lot_daily",
        "fact_lot_hourly_profile", "outreach", "outreach_events",
    ]
    rows: list[dict[str, Any]] = []
    for table in ordered_tables:
        for column in tables[table].columns:
            lineage, source, reference, method = _classification(table, column)
            definition = DEFINITIONS.get(
                column, column.replace("_", " ").capitalize() + "."
            )
            storage_class = {
                "PUBLIC": "RAW",
                "DERIVED": "DERIVED",
                "SYNTHETIC": "SYNTHETIC",
                "ASSUMED": "ASSUMED",
                "CONFIG": "CONFIG",
            }[lineage]
            rows.append(
                {
                    "table_name": table,
                    "column_name": column,
                    "data_type": _postgres_type(column),
                    "definition": definition,
                    "source_type": lineage,
                    "source_name": source,
                    "source_reference": reference,
                    "raw_derived_synthetic": storage_class,
                    "generation_logic": method,
                    "business_purpose": _business_purpose(table, column),
                }
            )
    return pd.DataFrame(rows)


def database_lineage(field_dictionary: pd.DataFrame) -> pd.DataFrame:
    return field_dictionary.rename(
        columns={"source_type": "lineage_type", "generation_logic": "methodology_note"}
    )[
        [
            "table_name", "column_name", "lineage_type", "source_name",
            "source_reference", "methodology_note", "business_purpose",
        ]
    ].copy()
