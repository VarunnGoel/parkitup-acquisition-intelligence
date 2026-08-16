"""
Central configuration for the PARK It Up Acquisition Intelligence project.

Every script reads its settings from here rather than defining its own
constants, so the observation window, random seed and connection details have
exactly one definition.

CREDENTIAL POLICY
    Nothing sensitive is stored in this file. Values come from the environment,
    optionally loaded from a git-ignored .env (see .env.example). Import fails
    loudly rather than silently defaulting when a required secret is absent.

USAGE
    from python.config import settings, get_engine

    with get_engine().connect() as conn:
        df = pd.read_sql("SELECT * FROM parkitup.parking_lots", conn)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------
# Paths. Anchored to the repository root so scripts work from any cwd.
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

PATHS = {
    "data_raw": REPO_ROOT / "data" / "raw",
    "data_processed": REPO_ROOT / "data" / "processed",
    "data_external": REPO_ROOT / "data" / "external",
    "schema": REPO_ROOT / "database" / "schema",
    "seeds": REPO_ROOT / "database" / "seeds",
    "sql_dq": REPO_ROOT / "sql" / "data_quality",
    "validation": REPO_ROOT / "validation",
    "documentation_methodology": REPO_ROOT / "documentation" / "methodology",
}


def _load_dotenv() -> None:
    """Load .env if python-dotenv is installed. Optional by design: the
    project must still run in an environment where variables are exported
    directly, such as CI."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Minimal fallback parser so a missing dependency is not a hard stop.
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())
        return
    load_dotenv(env_file)


_load_dotenv()


def _env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(
            f"Required environment variable {key} is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return val or ""


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be an integer, got {raw!r}") from exc


def _env_date(key: str, default: str) -> date:
    raw = os.environ.get(key) or default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be ISO YYYY-MM-DD, got {raw!r}") from exc


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """Resolved project configuration."""

    # --- database ---
    pg_host: str = field(default_factory=lambda: _env("PGHOST", "localhost"))
    pg_port: int = field(default_factory=lambda: _env_int("PGPORT", 5432))
    pg_database: str = field(default_factory=lambda: _env("PGDATABASE", "parkitup"))
    pg_user: str = field(default_factory=lambda: _env("PGUSER", os.environ.get("USER", "postgres")))
    pg_password: str = field(default_factory=lambda: _env("PGPASSWORD", ""))
    pg_schema: str = field(default_factory=lambda: _env("PG_SCHEMA", "parkitup"))

    # --- synthetic generation (source) ---
    random_seed: int = field(default_factory=lambda: _env_int("RANDOM_SEED", 20260815))
    obs_start_date: date = field(default_factory=lambda: _env_date("OBS_START_DATE", "2025-08-01"))
    obs_end_date: date = field(default_factory=lambda: _env_date("OBS_END_DATE", "2026-07-31"))
    target_lot_count: int = field(default_factory=lambda: _env_int("TARGET_LOT_COUNT", 120))

    # --- external data (source) ---
    overpass_api_url: str = field(
        default_factory=lambda: _env("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
    )
    overpass_timeout_seconds: int = field(
        default_factory=lambda: _env_int("OVERPASS_TIMEOUT_SECONDS", 180)
    )
    use_osm_cache: bool = field(default_factory=lambda: _env_bool("USE_OSM_CACHE", True))
    source_observed_on: date = field(
        default_factory=lambda: _env_date("SOURCE_OBSERVED_ON", "2026-08-16")
    )
    market_radius_m: int = field(default_factory=lambda: _env_int("MARKET_RADIUS_M", 3000))

    # --- study area: Delhi NCR bounding box -------------------------------
    # These MUST match the CHECK constraints on parking_lots.latitude /
    # longitude in database/schema/02_core_entities.sql. If one moves, the
    # other must move with it or the ETL will generate rows the database
    # refuses to accept. tests/ asserts they agree.
    lat_min: float = 28.30
    lat_max: float = 28.95
    lon_min: float = 76.80
    lon_max: float = 77.60

    def sqlalchemy_url(self, *, database: str | None = None) -> str:
        """Build a SQLAlchemy URL. Password is included only when set, so
        local trust/peer authentication works without a dummy value."""
        db = database or self.pg_database
        auth = self.pg_user
        if self.pg_password:
            from urllib.parse import quote_plus

            auth = f"{self.pg_user}:{quote_plus(self.pg_password)}"
        return f"postgresql+psycopg://{auth}@{self.pg_host}:{self.pg_port}/{db}"

    def observation_days(self) -> int:
        return (self.obs_end_date - self.obs_start_date).days + 1

    def summary(self) -> str:
        """Connection summary safe to print or log. Never includes the password."""
        return (
            f"host={self.pg_host}:{self.pg_port} db={self.pg_database} "
            f"user={self.pg_user} schema={self.pg_schema} "
            f"password={'set' if self.pg_password else 'not set (trust/peer auth)'}"
        )


settings = Settings()


def get_engine(*, database: str | None = None, echo: bool = False):
    """Return a SQLAlchemy engine with the project schema on the search path."""
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "SQLAlchemy is not installed. Run: pip install -r requirements.txt"
        ) from exc

    return create_engine(
        settings.sqlalchemy_url(database=database),
        echo=echo,
        future=True,
        connect_args={"options": f"-csearch_path={settings.pg_schema},public"},
    )


if __name__ == "__main__":
    print("PARK It Up - resolved configuration")
    print(f"  repo root   : {REPO_ROOT}")
    print(f"  connection  : {settings.summary()}")
    print(f"  seed        : {settings.random_seed}")
    print(
        f"  window      : {settings.obs_start_date} -> {settings.obs_end_date} "
        f"({settings.observation_days()} days)"
    )
    print(f"  target lots : {settings.target_lot_count}")
    print(f"  OSM cache   : {settings.use_osm_cache}")
    print(
        f"  NCR bbox    : lat {settings.lat_min}-{settings.lat_max}, "
        f"lon {settings.lon_min}-{settings.lon_max}"
    )
