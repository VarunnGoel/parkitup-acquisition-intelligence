"""PostgreSQL access for the validation analytical layer.

The SQL layer remains the source of relational business logic. This module
only defines reusable, named reads from the analytics views and the small number
of base-grain tables needed for time-pattern and validation work.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Iterable

import pandas as pd
from sqlalchemy.engine import Engine

from python.config import get_engine, settings


def _schema_name() -> str:
    """Return a safe SQL identifier for the configured project schema."""
    schema = settings.pg_schema
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError(f"PG_SCHEMA must be a simple SQL identifier, got {schema!r}")
    return schema


def dataset_queries() -> dict[str, str]:
    """Named source queries used by the validation layer.

    Parking/locality aggregates are deliberately read from the SQL analytics layer views.
    Daily and hourly facts are read only where the time grain is analytically
    necessary and cannot be recovered from the aggregate views.
    """
    s = _schema_name()
    return {
        "cities": f"SELECT * FROM {s}.dim_city ORDER BY city_id",
        "localities": f"""
            SELECT l.*, c.city_name, c.state_name, c.ncr_zone, c.is_core_delhi
            FROM {s}.dim_locality l
            JOIN {s}.dim_city c USING (city_id)
            ORDER BY l.locality_id
        """,
        "dates": f"SELECT * FROM {s}.dim_date ORDER BY activity_date",
        "funnel_stages": f"SELECT * FROM {s}.dim_funnel_stage ORDER BY stage_order",
        "score_dimensions": f"SELECT * FROM {s}.dim_score_dimension ORDER BY display_order",
        "parking_performance": f"SELECT * FROM {s}.vw_parking_performance_summary ORDER BY parking_id",
        "parking_benchmarks": f"SELECT * FROM {s}.vw_parking_benchmarks ORDER BY parking_id",
        "acquisition_scores": f"SELECT * FROM {s}.parking_acquisition_score ORDER BY parking_id",
        "component_scores": f"SELECT * FROM {s}.parking_component_scores ORDER BY parking_id",
        "locality_summary": f"SELECT * FROM {s}.vw_locality_summary ORDER BY whitespace_rank, locality_id",
        "bd_funnel": f"SELECT * FROM {s}.vw_bd_funnel ORDER BY stage_order",
        "bd_targets": f"SELECT * FROM {s}.vw_bd_acquisition_targets ORDER BY rank",
        "rank_explanations": f"SELECT * FROM {s}.vw_parking_rank_explanation ORDER BY overall_rank",
        "parking": f"""
            SELECT p.*, l.locality_name, c.city_name, o.owner_type,
                   o.owner_name, o.digital_payment_enabled, o.management_system,
                   o.willingness_to_digitize, o.contract_flexibility,
                   o.decision_maker_accessible
            FROM {s}.parking_lots p
            JOIN {s}.dim_locality l USING (locality_id)
            JOIN {s}.dim_city c USING (city_id)
            JOIN {s}.owners o USING (owner_id)
            ORDER BY p.parking_id
        """,
        "owners": f"SELECT * FROM {s}.owners ORDER BY owner_id",
        "competition": f"""
            SELECT c.*, p.lot_name AS parking_name, p.locality_id, l.locality_name
            FROM {s}.competition c
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            ORDER BY c.parking_id
        """,
        "location_demand": f"""
            SELECT d.*, p.lot_name AS parking_name, p.locality_id, l.locality_name
            FROM {s}.location_demand d
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            ORDER BY d.parking_id
        """,
        "acquisition_terms": f"""
            SELECT t.*, p.lot_name AS parking_name, p.locality_id, l.locality_name
            FROM {s}.lot_acquisition_terms t
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            ORDER BY t.parking_id
        """,
        "daily_performance": f"""
            SELECT f.*, p.lot_name AS parking_name, p.locality_id, l.locality_name
            FROM {s}.fact_lot_daily f
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            ORDER BY f.activity_date, f.parking_id
        """,
        "hourly_profile": f"""
            SELECT h.*, p.lot_name AS parking_name, p.locality_id, l.locality_name
            FROM {s}.fact_lot_hourly_profile h
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            ORDER BY h.day_type, h.hour_of_day, h.parking_id
        """,
        "outreach": f"""
            SELECT o.*, p.lot_name AS parking_name, p.capacity_cars,
                   p.parking_type, p.locality_id, l.locality_name,
                   ow.owner_type, ow.digital_payment_enabled,
                   ow.management_system, ow.willingness_to_digitize,
                   ow.contract_flexibility, ow.decision_maker_accessible,
                   fs.stage_code AS furthest_stage_code,
                   fs.stage_name AS furthest_stage_name,
                   fs.stage_order AS furthest_stage_order
            FROM {s}.outreach o
            JOIN {s}.parking_lots p USING (parking_id)
            JOIN {s}.dim_locality l USING (locality_id)
            JOIN {s}.owners ow USING (owner_id)
            JOIN {s}.dim_funnel_stage fs ON fs.stage_id = o.furthest_stage_id
            ORDER BY o.lead_id
        """,
        "outreach_events": f"SELECT * FROM {s}.outreach_events ORDER BY lead_id, event_date, stage_id",
        "scenario_scores": f"""
            SELECT l.*, a.scenario_code, a.scenario_group, a.description,
                   a.include_in_stability, a.methodology_note
            FROM {s}.lot_scenario_score l
            JOIN {s}.acquisition_scenario a USING (scenario_id)
            ORDER BY a.scenario_id, l.rank_overall
        """,
        "rank_stability": f"SELECT * FROM {s}.lot_rank_stability ORDER BY parking_id",
        "dimension_scores": f"""
            SELECT l.parking_id, l.weight_set_id, ws.weight_set_code,
                   l.dimension_code, d.dimension_name, d.pillar_group,
                   d.display_order, l.subscore, l.weight_applied,
                   l.weighted_contribution
            FROM {s}.lot_dimension_score l
            JOIN {s}.scoring_weight_set ws USING (weight_set_id)
            JOIN {s}.dim_score_dimension d USING (dimension_code)
            ORDER BY l.weight_set_id, l.parking_id, d.display_order
        """,
        "sensitivity_summary": f"""
            SELECT ss.*, a.scenario_code, a.scenario_group, a.description,
                   a.include_in_stability
            FROM {s}.sensitivity_summary ss
            JOIN {s}.acquisition_scenario a USING (scenario_id)
            ORDER BY ss.scenario_id
        """,
        "segment_rules": f"SELECT * FROM {s}.segment_rule ORDER BY eval_priority",
        "scoring_weights": f"""
            SELECT ws.weight_set_id, ws.weight_set_code, ws.description,
                   ws.is_default, w.dimension_code, w.weight
            FROM {s}.scoring_weight_set ws
            JOIN {s}.scoring_weight w USING (weight_set_id)
            ORDER BY ws.weight_set_id, w.dimension_code
        """,
    }


def _normalise_database_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert Decimal/date object columns while preserving PostgreSQL arrays."""
    result = frame.copy()
    for column in result.columns:
        series = result[column]
        if series.dtype != "object":
            continue
        non_null = series.dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[:100]
        if sample.map(lambda value: isinstance(value, (Decimal, int, float)) and not isinstance(value, bool)).all():
            result[column] = pd.to_numeric(series, errors="coerce")
        elif sample.map(lambda value: isinstance(value, (date, datetime))).all():
            result[column] = pd.to_datetime(series, errors="coerce")
    return result


def load_dataset(name: str, *, engine: Engine | None = None) -> pd.DataFrame:
    """Load one named validation dataset from PostgreSQL."""
    queries = dataset_queries()
    if name not in queries:
        raise KeyError(f"Unknown dataset {name!r}. Available: {sorted(queries)}")
    owned_engine = engine is None
    active_engine = engine or get_engine()
    try:
        with active_engine.connect() as connection:
            frame = pd.read_sql_query(queries[name], connection)
    finally:
        if owned_engine:
            active_engine.dispose()
    return _normalise_database_types(frame)


def load_analysis_inputs(
    names: Iterable[str] | None = None,
    *,
    engine: Engine | None = None,
) -> dict[str, pd.DataFrame]:
    """Load a collection of datasets through one reusable connection pool."""
    selected = list(names or dataset_queries().keys())
    active_engine = engine or get_engine()
    owned_engine = engine is None
    try:
        return {name: load_dataset(name, engine=active_engine) for name in selected}
    finally:
        if owned_engine:
            active_engine.dispose()


def source_contract_checks(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Validate the expected analytics/scoring source grains before analysis."""
    checks: list[dict[str, object]] = []

    def add(check_id: str, description: str, passed: bool, observed: object) -> None:
        checks.append(
            {
                "check_id": check_id,
                "description": description,
                "observed": observed,
                "status": "PASS" if passed else "FAIL",
            }
        )

    expected_rows = {
        "parking_performance": 120,
        "parking_benchmarks": 120,
        "acquisition_scores": 120,
        "component_scores": 120,
        "locality_summary": 17,
        "daily_performance": 43_800,
        "hourly_profile": 5_760,
        "outreach": 120,
    }
    for name, expected in expected_rows.items():
        if name in inputs:
            observed = len(inputs[name])
            add(f"SRC-{name}", f"{name} has its documented row grain", observed == expected, observed)

    for name in ("parking_performance", "acquisition_scores", "component_scores"):
        if name in inputs:
            duplicates = int(inputs[name]["parking_id"].duplicated().sum())
            add(f"KEY-{name}", f"{name} has one row per parking_id", duplicates == 0, duplicates)

    if "daily_performance" in inputs:
        daily_counts = inputs["daily_performance"].groupby("parking_id").size()
        add("GRAIN-daily", "Every lot has 365 daily rows", bool((daily_counts == 365).all()), daily_counts.value_counts().to_dict())
    if "hourly_profile" in inputs:
        hourly_counts = inputs["hourly_profile"].groupby("parking_id").size()
        add("GRAIN-hourly", "Every lot has 48 hourly-profile rows", bool((hourly_counts == 48).all()), hourly_counts.value_counts().to_dict())
    return pd.DataFrame(checks)
