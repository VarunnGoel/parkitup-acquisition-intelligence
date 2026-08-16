"""Regression tests for the deterministic source data layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402
from python.etl.cleaning import public_pipeline  # noqa: E402
from python.etl.lineage import build_field_dictionary  # noqa: E402
from python.etl.synthetic_generation import generate_synthetic_tables  # noqa: E402
from python.etl.validation import business_logic_checks, validate_tables  # noqa: E402


def _build_in_memory() -> dict[str, pd.DataFrame]:
    public = public_pipeline()
    generated = generate_synthetic_tables(public)
    return {
        "dim_locality": public["dim_locality"],
        "location_demand": public["location_demand"],
        **generated,
    }


def test_public_snapshot_is_cached_and_bounded():
    manifest = json.loads((PATHS["data_external"] / "source_manifest.json").read_text())
    assert manifest["runtime_dependency"] is False
    assert manifest["files"]["osm_features_snapshot.json"]["rows"] >= 100
    assert manifest["files"]["micro_markets.csv"]["rows"] == 20


def test_build_has_required_scope_and_grains():
    tables = _build_in_memory()
    lots = tables["parking_lots"]
    assert 100 <= len(lots) <= 200
    assert 15 <= len(tables["dim_locality"]) <= 25
    assert set(lots["record_source"]) == {"public_osm"}
    assert lots["source_reference"].str.startswith("https://www.openstreetmap.org/").all()
    assert len(tables["fact_lot_daily"]) == len(lots) * settings.observation_days()
    assert len(tables["fact_lot_hourly_profile"]) == len(lots) * 48
    assert len(tables["outreach"]) == len(lots)


def test_generation_is_deterministic_for_major_outputs():
    first = _build_in_memory()
    second = _build_in_memory()
    for table in ("owners", "parking_lots", "fact_lot_daily", "outreach", "outreach_events"):
        pd.testing.assert_frame_equal(first[table], second[table], check_dtype=True)


def test_all_python_and_business_logic_rules_pass():
    tables = _build_in_memory()
    structural = validate_tables(tables)
    relationships = business_logic_checks(tables)
    assert not (structural["status"] == "FAIL").any(), structural.to_string()
    assert not (relationships["status"] == "FAIL").any(), relationships.to_string()


def test_field_dictionary_covers_every_exported_column():
    tables = _build_in_memory()
    dictionary = build_field_dictionary(tables)
    expected = {
        (table, column)
        for table, frame in tables.items()
        for column in frame.columns
    }
    actual = set(zip(dictionary["table_name"], dictionary["column_name"]))
    assert actual == expected
    assert set(dictionary["source_type"]) <= {
        "PUBLIC", "DERIVED", "SYNTHETIC", "ASSUMED", "CONFIG"
    }


def test_exports_no_acquisition_score_or_recommendation():
    tables = _build_in_memory()
    prohibited = {"acquisition_score", "recommended", "segment_code"}
    exported = {column for frame in tables.values() for column in frame.columns}
    assert prohibited.isdisjoint(exported)
