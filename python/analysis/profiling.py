"""Data-quality profiling helpers for the validation layer.

The profiler is intentionally descriptive. It reports suspicious shapes for
review, but it does not silently winsorise or remove records.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


PERCENTILES = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)


def _string_unique_count(series: pd.Series) -> int:
    return int(series.map(lambda value: repr(value)).nunique(dropna=True))


def _numeric_series(series: pd.Series) -> pd.Series | None:
    if pd.api.types.is_bool_dtype(series):
        return None
    converted = pd.to_numeric(series, errors="coerce")
    if converted.notna().sum() == series.notna().sum() and converted.notna().any():
        return converted.astype(float)
    return None


def profile_frame(frame: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
    """Return one row per column with quality and distribution diagnostics."""
    duplicate_full_rows = int(frame.astype(str).duplicated().sum())
    rows: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        missing_count = int(series.isna().sum())
        non_null = series.dropna()
        numeric = _numeric_series(series)
        row: dict[str, Any] = {
            "dataset": dataset_name,
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "column": column,
            "dtype": str(series.dtype),
            "missing_count": missing_count,
            "missing_pct": round(missing_count / len(frame) * 100.0, 2) if len(frame) else 0.0,
            "unique_count": _string_unique_count(series),
            "duplicate_full_rows": duplicate_full_rows,
            "min": None,
            "p01": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
            "std": None,
            "zero_pct": None,
            "skew": None,
            "suspicious_flags": [],
        }
        flags: list[str] = []
        if row["missing_pct"] >= 20.0:
            flags.append("HIGH_MISSINGNESS")
        if row["unique_count"] <= 1 and len(frame) > 1:
            flags.append("CONSTANT")
        if numeric is not None:
            quantiles = numeric.quantile(PERCENTILES)
            row.update(
                {
                    "min": float(numeric.min()),
                    "p01": float(quantiles.loc[0.01]),
                    "p05": float(quantiles.loc[0.05]),
                    "p25": float(quantiles.loc[0.25]),
                    "median": float(quantiles.loc[0.50]),
                    "p75": float(quantiles.loc[0.75]),
                    "p95": float(quantiles.loc[0.95]),
                    "p99": float(quantiles.loc[0.99]),
                    "max": float(numeric.max()),
                    "mean": float(numeric.mean()),
                    "std": float(numeric.std(ddof=1)) if numeric.count() > 1 else 0.0,
                    "zero_pct": float((numeric == 0).mean() * 100.0),
                    "skew": float(numeric.skew()) if numeric.count() > 2 else 0.0,
                }
            )
            if row["zero_pct"] >= 50.0:
                flags.append("ZERO_INFLATED")
            if row["skew"] is not None and abs(row["skew"]) >= 1.5:
                flags.append("SKEWED")
            if np.isclose(row["p95"], row["max"], rtol=0.0, atol=1e-9) and numeric.nunique() > 4:
                flags.append("UPPER_BOUND_CONCENTRATION")
        row["suspicious_flags"] = "|".join(flags)
        rows.append(row)
    return pd.DataFrame(rows)


def profile_datasets(frames: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Profile every supplied frame and return column and dataset summaries."""
    profiles = pd.concat(
        [profile_frame(frame, name) for name, frame in frames.items()],
        ignore_index=True,
    )
    summary = (
        profiles.groupby("dataset", as_index=False)
        .agg(
            row_count=("row_count", "first"),
            column_count=("column_count", "first"),
            missing_cells=("missing_count", "sum"),
            columns_with_missing=("missing_count", lambda values: int((values > 0).sum())),
            duplicate_full_rows=("duplicate_full_rows", "first"),
            suspicious_columns=("suspicious_flags", lambda values: int((values != "").sum())),
        )
    )
    return profiles, summary


def suspicious_distributions(profile: pd.DataFrame) -> pd.DataFrame:
    """Return only columns needing analyst review."""
    result = profile[profile["suspicious_flags"].astype(str).str.len() > 0].copy()
    return result.sort_values(["dataset", "column"]).reset_index(drop=True)

