"""
Tests that the Python configuration and the SQL schema cannot drift apart.

WHY THESE TESTS
    The most dangerous class of bug in a project split between Python and SQL is
    a constant defined twice. The Delhi NCR bounding box exists as a CHECK
    constraint in the DDL and as float bounds in python/config.py. If someone
    widens one and not the other, the source generator will emit rows that
    PostgreSQL silently refuses, and the failure will surface far from its
    cause. These tests read the DDL and assert the two agree.

    They need no database, so they run anywhere.

RUN
    python3 -m pytest tests/ -v
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from python.config import settings  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "database" / "schema"
CORE_DDL = SCHEMA_DIR / "02_core_entities.sql"


def _bbox_from_ddl(column: str) -> tuple[float, float]:
    """Extract the BETWEEN bounds for a lat/long CHECK constraint from the DDL."""
    sql = CORE_DDL.read_text(encoding="utf-8")
    pattern = rf"CHECK\s*\(\s*{column}\s+BETWEEN\s+([\d.]+)\s+AND\s+([\d.]+)\s*\)"
    matches = re.findall(pattern, sql, re.IGNORECASE)
    assert matches, f"no BETWEEN bounds found for {column} in {CORE_DDL.name}"
    lows = {float(a) for a, _ in matches}
    highs = {float(b) for _, b in matches}
    # parking_lots and existing_network_sites both constrain coordinates; they
    # must use identical bounds or "inside the study area" means two things.
    assert len(lows) == 1 and len(highs) == 1, (
        f"{column} is constrained with inconsistent bounds across tables: "
        f"lows={lows}, highs={highs}"
    )
    return lows.pop(), highs.pop()


def test_latitude_bounds_match_config():
    low, high = _bbox_from_ddl("latitude")
    assert low == pytest.approx(settings.lat_min), (
        f"DDL latitude lower bound {low} != config lat_min {settings.lat_min}"
    )
    assert high == pytest.approx(settings.lat_max), (
        f"DDL latitude upper bound {high} != config lat_max {settings.lat_max}"
    )


def test_longitude_bounds_match_config():
    low, high = _bbox_from_ddl("longitude")
    assert low == pytest.approx(settings.lon_min)
    assert high == pytest.approx(settings.lon_max)


def test_bounding_box_actually_contains_delhi_ncr():
    """Guards against a transposed or truncated bounding box. Connaught Place
    is the centre of Delhi; if the box excludes it, something is badly wrong."""
    cp_lat, cp_lon = 28.6315, 77.2167
    assert settings.lat_min < cp_lat < settings.lat_max
    assert settings.lon_min < cp_lon < settings.lon_max
    # Gurugram Cyber City and Noida Sector 18 sit near opposite edges.
    for name, lat, lon in [
        ("Gurugram Cyber City", 28.4950, 77.0890),
        ("Noida Sector 18", 28.5700, 77.3260),
        ("Faridabad", 28.4089, 77.3178),
    ]:
        assert settings.lat_min <= lat <= settings.lat_max, f"{name} outside lat bounds"
        assert settings.lon_min <= lon <= settings.lon_max, f"{name} outside lon bounds"


def test_observation_window_is_inside_seeded_calendar():
    """The performance facts reference dim_date, so the generator's window must
    sit inside the range the calendar seed creates, or every insert will fail
    on a foreign key."""
    seed_sql = (REPO_ROOT / "database" / "seeds" / "02_seed_calendar.sql").read_text(
        encoding="utf-8"
    )
    dates = re.findall(r"DATE\s+'(\d{4}-\d{2}-\d{2})'", seed_sql)
    assert len(dates) >= 2, "could not find the generate_series bounds in the calendar seed"
    from datetime import date as _date

    seeded = [_date.fromisoformat(d) for d in dates]
    # The first two DATE literals are the generate_series bounds.
    cal_start, cal_end = seeded[0], seeded[1]
    assert settings.obs_start_date >= cal_start, (
        f"observation window starts {settings.obs_start_date}, before the "
        f"calendar begins at {cal_start}"
    )
    assert settings.obs_end_date <= cal_end, (
        f"observation window ends {settings.obs_end_date}, after the calendar "
        f"ends at {cal_end}"
    )


def test_observation_window_is_ordered_and_non_trivial():
    assert settings.obs_start_date < settings.obs_end_date
    # A year is the documented intent (assumption A-02); anything much shorter
    # would silently drop the seasonality the window exists to capture.
    assert settings.observation_days() >= 180, (
        f"observation window is only {settings.observation_days()} days; "
        f"assumption A-02 requires enough span to show NCR seasonality"
    )


def test_no_credentials_committed_in_env_example():
    """.env.example must stay a template. A real password reaching git history
    is not fixable by deleting it later."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("PGPASSWORD="):
            value = line.split("=", 1)[1].strip()
            assert value in ("", "your_postgres_password"), (
                "PGPASSWORD in .env.example looks like a real credential"
            )


def test_gitignore_excludes_dotenv():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [l.strip() for l in ignored], ".env must be git-ignored"


def test_target_lot_count_is_plausible():
    """Sanity bound on the modelled universe. Small enough to hand-verify,
    large enough for locality-level aggregation to mean anything."""
    assert 50 <= settings.target_lot_count <= 500
