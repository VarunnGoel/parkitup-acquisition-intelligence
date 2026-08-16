"""Build, validate, document, and optionally load the complete source data layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402
from python.etl.cleaning import public_pipeline  # noqa: E402
from python.etl.lineage import build_field_dictionary, database_lineage  # noqa: E402
from python.etl.postgres_loader import (  # noqa: E402
    database_integrity_summary,
    load_tables,
    run_sql_quality_checks,
)
from python.etl.source_collection import ensure_cached_sources, refresh_sources  # noqa: E402
from python.etl.synthetic_generation import generate_synthetic_tables  # noqa: E402
from python.etl.validation import assert_valid, business_logic_checks, validate_tables  # noqa: E402

PROCESSED_TABLES = [
    "dim_locality", "owners", "parking_lots", "location_demand", "competition",
    "lot_acquisition_terms", "existing_network_sites", "fact_lot_daily",
    "fact_lot_hourly_profile", "outreach", "outreach_events", "data_lineage",
]


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, na_rep="", float_format="%.6f", lineterminator="\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _distribution(series: pd.Series) -> dict[str, float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return {
        "min": float(values.min()),
        "p25": float(values.quantile(0.25)),
        "median": float(values.median()),
        "mean": float(values.mean()),
        "p75": float(values.quantile(0.75)),
        "max": float(values.max()),
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join("---" for _ in columns) + "|"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def build_profile_report(
    tables: dict[str, pd.DataFrame], quality: pd.DataFrame, business: pd.DataFrame
) -> str:
    lots = tables["parking_lots"]
    localities = tables["dim_locality"]
    daily = tables["fact_lot_daily"]
    competition = tables["competition"]
    counts = pd.DataFrame(
        [
            ("Parking lots", len(lots)),
            ("Localities", len(localities)),
            ("Owners", len(tables["owners"])),
            ("Daily performance records", len(daily)),
            ("Hourly profile records", len(tables["fact_lot_hourly_profile"])),
            ("Outreach leads", len(tables["outreach"])),
            ("Outreach stage events", len(tables["outreach_events"])),
            ("Hypothetical network sites", len(tables["existing_network_sites"])),
        ],
        columns=["Dataset", "Rows"],
    )
    type_counts = lots["parking_type"].value_counts().rename_axis("Parking type").reset_index(name="Lots")
    provenance = lots["record_source"].value_counts().rename_axis("Record source").reset_index(name="Lots")

    metrics = {
        "Capacity (cars)": _distribution(lots["capacity_cars"]),
        "Hourly price (INR)": _distribution(lots["hourly_rate_inr"]),
        "Average occupancy": _distribution(daily["avg_occupancy_rate"]),
        "Peak occupancy": _distribution(daily["peak_occupancy_rate"]),
        "Daily bookings": _distribution(daily["platform_bookings"]),
        "Daily revenue (INR)": _distribution(daily["gross_parking_revenue_inr"]),
        "Competitors within 1km": _distribution(competition["competitor_count_1km"]),
    }
    distribution_rows = []
    for metric, stats in metrics.items():
        distribution_rows.append(
            {
                "Metric": metric,
                **{key: f"{value:.2f}" for key, value in stats.items()},
            }
        )
    distributions = pd.DataFrame(distribution_rows)

    missing_rows = []
    for table_name, frame in tables.items():
        if table_name == "data_lineage":
            continue
        missing_rows.append(
            {
                "Table": table_name,
                "Rows": len(frame),
                "Missing cells": int(frame.isna().sum().sum()),
                "Duplicate full rows": int(frame.duplicated().sum()),
            }
        )
    missing = pd.DataFrame(missing_rows)
    failure_count = int((quality["status"] == "FAIL").sum())
    business_failures = int((business["status"] == "FAIL").sum())
    localities_text = ", ".join(localities.sort_values("locality_id")["locality_name"])

    return f"""# source Data Profile

Generated from the deterministic source build using seed `{settings.random_seed}` and the public source snapshot observed on `{settings.source_observed_on}`. This report profiles the data layer only; it does not rank acquisition opportunities.

## Dataset size

{_markdown_table(counts)}

## Geographic coverage

{localities_text}

All candidate coordinates are sourced from OpenStreetMap. Market type and population-density bands are explicit analyst assumptions recorded in the field lineage table.

## Parking-type coverage

{_markdown_table(type_counts)}

## Row-level provenance

{_markdown_table(provenance)}

Row-level public provenance applies to the parking identity and coordinates, not automatically to every attribute. Capacity, price, hours and amenity provenance are separately labelled on `parking_lots`.

## Basic distributions

{_markdown_table(distributions)}

## Missing values and duplicates

{_markdown_table(missing)}

Expected nullable fields account for most missing cells: monthly passes, unpublished competitor capacities/prices, first-contact/conversion fields for early-stage leads, and loss reasons for non-lost leads.

## Automated data quality

- Python structural/business-rule checks: {len(quality)} executed, {failure_count} failed.
- Business-logic tendency checks: {len(business)} executed, {business_failures} failed.
- Full check outputs: `validation/python_data_quality_results.csv` and `validation/business_logic_results.csv`.

{_markdown_table(quality[["rule_id", "dataset", "description", "violations", "status"]])}

## Business-logic tendencies

These checks test whether the simulation behaves plausibly without requiring perfect correlation.

{_markdown_table(business[["rule_id", "description", "observed_value", "status"]])}
"""


def update_profile_with_postgres(
    counts: dict[str, int], sql_quality: pd.DataFrame, integrity: dict[str, int]
) -> None:
    path = PATHS["documentation_methodology"] / "data_profile.md"
    current = path.read_text(encoding="utf-8")
    marker = "\n## PostgreSQL execution\n"
    current = current.split(marker, 1)[0].rstrip() + "\n"
    count_frame = pd.DataFrame(
        sorted(counts.items()), columns=["Table", "Loaded rows"]
    )
    status_frame = (
        sql_quality.groupby(["severity", "status"])
        .size()
        .rename("Rules")
        .reset_index()
    )
    integrity_frame = pd.DataFrame(
        sorted(integrity.items()), columns=["Integrity check", "Orphans"]
    )
    failed_warnings = sql_quality[
        (sql_quality["status"] == "FAIL") & (sql_quality["severity"] == "WARN")
    ]
    warning_text = (
        "; ".join(
            f'{row.rule_id}: {int(row.violations)} - {row.rule_description}'
            for row in failed_warnings.itertuples(index=False)
        )
        or "None"
    )
    section = f"""
## PostgreSQL execution

The full cached pipeline loaded the generated tables into PostgreSQL and ran the SQL rule catalog.

{_markdown_table(count_frame)}

{_markdown_table(status_frame)}

Non-passing warnings: {warning_text}. The unscored-lot warning is expected until the scoring engine; it is not suppressed or relabelled as a pass.

{_markdown_table(integrity_frame)}
"""
    path.write_text(current + section, encoding="utf-8")


def build_data() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    ensure_cached_sources()
    public = public_pipeline()
    synthetic = generate_synthetic_tables(public)
    tables = {
        "dim_locality": public["dim_locality"],
        "owners": synthetic["owners"],
        "parking_lots": synthetic["parking_lots"],
        "location_demand": public["location_demand"],
        "competition": synthetic["competition"],
        "lot_acquisition_terms": synthetic["lot_acquisition_terms"],
        "existing_network_sites": synthetic["existing_network_sites"],
        "fact_lot_daily": synthetic["fact_lot_daily"],
        "fact_lot_hourly_profile": synthetic["fact_lot_hourly_profile"],
        "outreach": synthetic["outreach"],
        "outreach_events": synthetic["outreach_events"],
    }
    field_dictionary = build_field_dictionary(tables)
    tables["data_lineage"] = database_lineage(field_dictionary)

    quality = validate_tables(tables)
    business = business_logic_checks(tables)
    assert_valid(quality, label="Python data-quality validation")
    assert_valid(business, label="Business-logic validation")

    raw_frames = {
        "markets_geocoded": public["markets"],
        "osm_features": public["osm_features"],
        "candidate_parking": public["candidate_parking"],
        "competition_public": public["competition_public"],
    }
    for name, frame in raw_frames.items():
        _write_csv(frame, PATHS["data_raw"] / f"{name}.csv")
    for name, frame in tables.items():
        _write_csv(frame, PATHS["data_processed"] / f"{name}.csv")

    dictionary_path = PATHS["documentation_methodology"] / "data_dictionary_source.csv"
    _write_csv(field_dictionary, dictionary_path)
    _write_csv(quality, PATHS["validation"] / "python_data_quality_results.csv")
    _write_csv(business, PATHS["validation"] / "business_logic_results.csv")
    profile = build_profile_report(tables, quality, business)
    (PATHS["documentation_methodology"] / "data_profile.md").write_text(
        profile, encoding="utf-8"
    )

    files = {}
    for name in PROCESSED_TABLES:
        path = PATHS["data_processed"] / f"{name}.csv"
        files[path.name] = {"rows": len(tables[name]), "sha256": _sha256(path)}
    manifest = {
        "build_as_of": f"{settings.source_observed_on.isoformat()}T00:00:00+05:30",
        "random_seed": settings.random_seed,
        "observation_start": settings.obs_start_date.isoformat(),
        "observation_end": settings.obs_end_date.isoformat(),
        "public_source_snapshot": "data/external/source_manifest.json",
        # The seed fixes the draw sequence, but numpy's Generator.binomial uses
        # rejection sampling (BTPE) once n*p >= 30, and its acceptance arithmetic
        # is not guaranteed identical across numpy releases. Recording the
        # generating versions makes a hash mismatch diagnosable instead of
        # mysterious: an observed numpy 2.2.6 -> 2.5.2 change moved one
        # platform_bookings value in 43,800 rows. See README "Reproducibility".
        "generated_with": {"numpy": np.__version__, "pandas": pd.__version__},
        "files": files,
    }
    (PATHS["data_processed"] / "build_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return tables, quality, business


def load_processed() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for table in PROCESSED_TABLES:
        path = PATHS["data_processed"] / f"{table}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing processed dataset: {path}")
        tables[table] = pd.read_csv(path)
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-sources", action="store_true", help="Refresh the bounded public OSM cache before building.")
    parser.add_argument("--load-postgres", action="store_true", help="Load the generated datasets into the configured PostgreSQL database.")
    parser.add_argument("--no-build", action="store_true", help="Load existing processed CSVs without rebuilding them.")
    args = parser.parse_args()

    if args.refresh_sources:
        refresh_sources()
    if args.no_build:
        tables = load_processed()
    else:
        tables, _, _ = build_data()

    summary: dict[str, Any] = {"processed_rows": {name: len(frame) for name, frame in tables.items()}}
    if args.load_postgres:
        summary["postgres_rows"] = load_tables(tables)
        sql_quality = run_sql_quality_checks()
        _write_csv(sql_quality, PATHS["validation"] / "postgres_data_quality_results.csv")
        sql_failures = sql_quality[
            (sql_quality["status"] == "FAIL") & (sql_quality["severity"] == "ERROR")
        ]
        if not sql_failures.empty:
            raise ValueError(
                "PostgreSQL data-quality checks failed:\n"
                + sql_failures[["rule_id", "rule_description", "violations"]].to_string(index=False)
            )
        integrity = database_integrity_summary()
        summary["postgres_integrity"] = integrity
        if any(integrity.values()):
            raise ValueError(f"PostgreSQL referential integrity checks failed: {integrity}")
        update_profile_with_postgres(summary["postgres_rows"], sql_quality, integrity)
        execution_summary = {
            "database": settings.pg_database,
            "loaded_rows": summary["postgres_rows"],
            "sql_rule_status": {
                f"{severity}_{status}": int(count)
                for (severity, status), count in sql_quality.groupby(["severity", "status"]).size().items()
            },
            "referential_integrity": integrity,
        }
        (PATHS["validation"] / "pipeline_execution_summary.json").write_text(
            json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
