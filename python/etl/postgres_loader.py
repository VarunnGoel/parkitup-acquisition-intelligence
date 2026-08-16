"""Load processed source frames into the baseline PostgreSQL schema."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402


LOAD_ORDER = [
    "dim_locality",
    "data_lineage",
    "owners",
    "parking_lots",
    "location_demand",
    "competition",
    "lot_acquisition_terms",
    "existing_network_sites",
    "fact_lot_daily",
    "fact_lot_hourly_profile",
    "outreach",
    "outreach_events",
]

IDENTITY_TABLES = {
    "owners": "owner_id",
    "parking_lots": "parking_id",
    "existing_network_sites": "network_site_id",
    "outreach": "lead_id",
    "outreach_events": "event_id",
}


def _connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required; install requirements.txt") from exc
    kwargs: dict[str, Any] = {
        "host": settings.pg_host,
        "port": settings.pg_port,
        "dbname": settings.pg_database,
        "user": settings.pg_user,
    }
    if settings.pg_password:
        kwargs["password"] = settings.pg_password
    return psycopg.connect(**kwargs)


def _python_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if pd.isna(value):
        return None
    return value


def _copy_frame(cursor: Any, table: str, frame: pd.DataFrame) -> None:
    columns = list(frame.columns)
    if table == "outreach" and "days_to_conversion" in columns:
        columns.remove("days_to_conversion")
    quoted = ", ".join(f'"{column}"' for column in columns)
    override = " OVERRIDING SYSTEM VALUE" if table in IDENTITY_TABLES else ""
    sql = f'COPY {settings.pg_schema}."{table}" ({quoted}) FROM STDIN'
    # COPY accepts explicit identity values directly; OVERRIDING is INSERT-only.
    with cursor.copy(sql) as copy:
        for values in frame[columns].itertuples(index=False, name=None):
            copy.write_row(tuple(_python_value(value) for value in values))


def _reset_identity(cursor: Any, table: str, column: str) -> None:
    cursor.execute(
        "SELECT pg_get_serial_sequence(%s, %s)",
        (f"{settings.pg_schema}.{table}", column),
    )
    sequence = cursor.fetchone()[0]
    if sequence:
        cursor.execute(
            f"SELECT setval(%s, COALESCE((SELECT MAX(\"{column}\") FROM "
            f'{settings.pg_schema}."{table}"), 1), true)',
            (sequence,),
        )


def load_tables(tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Atomically replace all source rows and return loaded row counts."""
    missing = [table for table in LOAD_ORDER if table not in tables]
    if missing:
        raise KeyError(f"Missing frames required for PostgreSQL load: {missing}")
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {settings.pg_schema}, public")
            cursor.execute(
                "TRUNCATE TABLE "
                + ", ".join(
                    f'{settings.pg_schema}."{table}"'
                    for table in [
                        "lot_score", "lot_dimension_score", "outreach_events", "outreach",
                        "fact_lot_hourly_profile", "fact_lot_daily", "existing_network_sites",
                        "lot_acquisition_terms", "competition", "location_demand", "parking_lots",
                        "owners", "dim_locality", "data_lineage",
                    ]
                )
                + " RESTART IDENTITY CASCADE"
            )
            for table in LOAD_ORDER:
                _copy_frame(cursor, table, tables[table])
            for table, column in IDENTITY_TABLES.items():
                _reset_identity(cursor, table, column)
        connection.commit()

    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {settings.pg_schema}, public")
            counts: dict[str, int] = {}
            for table in LOAD_ORDER:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = int(cursor.fetchone()[0])
    return counts


def run_sql_quality_checks() -> pd.DataFrame:
    sql = (PATHS["sql_dq"] / "dq_checks.sql").read_text(encoding="utf-8")
    query = sql[sql.index("WITH checks AS") :]
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {settings.pg_schema}, public")
            cursor.execute(query)
            columns = [description.name for description in cursor.description]
            rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)


def database_integrity_summary() -> dict[str, int]:
    queries = {
        "orphan_lot_locality": "SELECT COUNT(*) FROM parking_lots p LEFT JOIN dim_locality l USING(locality_id) WHERE l.locality_id IS NULL",
        "orphan_lot_owner": "SELECT COUNT(*) FROM parking_lots p LEFT JOIN owners o USING(owner_id) WHERE o.owner_id IS NULL",
        "orphan_daily_lot": "SELECT COUNT(*) FROM fact_lot_daily f LEFT JOIN parking_lots p USING(parking_id) WHERE p.parking_id IS NULL",
        "orphan_daily_date": "SELECT COUNT(*) FROM fact_lot_daily f LEFT JOIN dim_date d USING(activity_date) WHERE d.activity_date IS NULL",
        "orphan_event_lead": "SELECT COUNT(*) FROM outreach_events e LEFT JOIN outreach o USING(lead_id) WHERE o.lead_id IS NULL",
    }
    results: dict[str, int] = {}
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {settings.pg_schema}, public")
            for name, query in queries.items():
                cursor.execute(query)
                results[name] = int(cursor.fetchone()[0])
    return results
