"""Focused exploratory summaries for the validation analytical layer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from python.analysis.statistics import spearman_correlation


def add_relationship_features(scores: pd.DataFrame) -> pd.DataFrame:
    """Add transparent EDA-only density proxies without changing score inputs."""
    frame = scores.copy()
    frame["commercial_density_proxy"] = frame[
        ["office_count_500m", "retail_count_500m", "restaurant_count_500m"]
    ].sum(axis=1, min_count=1)
    frame["destination_density_proxy"] = frame[
        ["retail_count_500m", "restaurant_count_500m", "hospital_count_1km", "education_count_1km"]
    ].sum(axis=1, min_count=1)
    return frame


def _corr_row(frame: pd.DataFrame, x: str, y: str, label: str) -> dict[str, Any]:
    pair = frame[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) < 3:
        return {"relationship": label, "x": x, "y": y, "n": len(pair), "spearman": None, "pearson": None}
    return {
        "relationship": label,
        "x": x,
        "y": y,
        "n": int(len(pair)),
        "spearman": round(spearman_correlation(pair[x], pair[y]), 4),
        "pearson": round(float(pair[x].corr(pair[y], method="pearson")), 4),
    }


def relationship_summary(scores: pd.DataFrame) -> pd.DataFrame:
    """Summarise associations without implying causation."""
    frame = add_relationship_features(scores)
    relationships = [
        ("occupancy_capacity", "avg_occupancy_rate", "capacity_cars", "Occupancy vs capacity"),
        ("occupancy_price", "avg_occupancy_rate", "hourly_rate_inr", "Occupancy vs hourly price"),
        ("occupancy_metro_distance", "avg_occupancy_rate", "metro_distance_m", "Occupancy vs metro distance"),
        ("occupancy_commercial_density", "avg_occupancy_rate", "commercial_density_proxy", "Occupancy vs commercial density proxy"),
        ("occupancy_destination_density", "avg_occupancy_rate", "destination_density_proxy", "Occupancy vs destination density proxy"),
        ("bookings_occupancy", "avg_daily_platform_bookings", "avg_occupancy_rate", "Bookings vs occupancy"),
        ("revenue_capacity", "expected_monthly_platform_revenue_inr", "capacity_cars", "Platform revenue vs capacity"),
        ("revenue_occupancy", "expected_monthly_platform_revenue_inr", "avg_occupancy_rate", "Platform revenue vs occupancy"),
    ]
    return pd.DataFrame([_corr_row(frame, x, y, label) for _, x, y, label in relationships])


def peak_hour_windows(hourly: pd.DataFrame) -> pd.DataFrame:
    """Identify portfolio peak windows from the observed hourly profile."""
    portfolio = (
        hourly.groupby(["day_type", "hour_of_day"], as_index=False)["avg_occupancy_rate"]
        .mean()
        .rename(columns={"avg_occupancy_rate": "portfolio_avg_occupancy_rate"})
    )
    rows: list[dict[str, Any]] = []
    for day_type, group in portfolio.groupby("day_type", sort=True):
        cutoff = float(group["portfolio_avg_occupancy_rate"].quantile(0.75))
        peak = group[group["portfolio_avg_occupancy_rate"] >= cutoff].sort_values("hour_of_day")
        hours = peak["hour_of_day"].astype(int).tolist()
        windows: list[str] = []
        if hours:
            start = prior = hours[0]
            for hour in hours[1:]:
                if hour == prior + 1:
                    prior = hour
                    continue
                windows.append(f"{start:02d}:00-{prior:02d}:00")
                start = prior = hour
            windows.append(f"{start:02d}:00-{prior:02d}:00")
        rows.append(
            {
                "day_type": day_type,
                "peak_cutoff_occupancy_pct": round(cutoff * 100.0, 2),
                "peak_hours": ", ".join(f"{hour:02d}:00" for hour in hours),
                "peak_windows": "; ".join(windows),
                "peak_hour_count": len(hours),
                "peak_mean_occupancy_pct": round(float(peak["portfolio_avg_occupancy_rate"].mean() * 100.0), 2) if len(peak) else None,
            }
        )
    return pd.DataFrame(rows)


def parking_characteristics(scores: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return concise capacity, price, type and locality summaries."""
    capacity = scores[["parking_id", "lot_name", "locality_name", "capacity_cars"]].copy()
    price = scores[["parking_id", "lot_name", "parking_type", "hourly_rate_inr"]].copy()
    by_type = (
        scores.groupby("parking_type", as_index=False)
        .agg(
            parking_lots=("parking_id", "count"),
            median_capacity_cars=("capacity_cars", "median"),
            mean_capacity_cars=("capacity_cars", "mean"),
            median_hourly_rate_inr=("hourly_rate_inr", "median"),
            mean_hourly_rate_inr=("hourly_rate_inr", "mean"),
        )
        .sort_values("parking_lots", ascending=False)
    )
    by_locality = (
        scores.groupby("locality_name", as_index=False)
        .agg(
            parking_lots=("parking_id", "count"),
            total_capacity_cars=("capacity_cars", "sum"),
            average_capacity_cars=("capacity_cars", "mean"),
            average_hourly_rate_inr=("hourly_rate_inr", "mean"),
        )
        .sort_values("total_capacity_cars", ascending=False)
    )
    return {"lot_capacity": capacity, "lot_price": price, "by_type": by_type, "by_locality": by_locality}


def demand_summary(scores: pd.DataFrame, daily: pd.DataFrame, hourly: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return distribution and time-pattern summaries at their native grain."""
    daily_frame = daily.copy()
    daily_frame["day_of_week"] = daily_frame["activity_date"].dt.day_name()
    daily_frame["day_order"] = daily_frame["activity_date"].dt.dayofweek
    by_day = (
        daily_frame.groupby(["day_order", "day_of_week"], as_index=False)
        .agg(
            average_occupancy_pct=("avg_occupancy_rate", lambda s: float(s.mean() * 100.0)),
            average_peak_occupancy_pct=("peak_occupancy_rate", lambda s: float(s.mean() * 100.0)),
            average_entries=("vehicle_entries", "mean"),
            average_bookings=("platform_bookings", "mean"),
        )
        .sort_values("day_order")
    )
    by_locality = (
        scores.groupby("locality_name", as_index=False)
        .agg(
            parking_lots=("parking_id", "count"),
            average_occupancy_pct=("avg_occupancy_rate", lambda s: float(s.mean() * 100.0)),
            average_peak_occupancy_pct=("p90_peak_occupancy_rate", lambda s: float(s.mean() * 100.0)),
            average_demand_score=("demand_score", "mean"),
        )
        .sort_values("average_occupancy_pct", ascending=False)
    )
    hourly_summary = (
        hourly.groupby(["day_type", "hour_of_day"], as_index=False)
        .agg(
            average_occupancy_pct=("avg_occupancy_rate", lambda s: float(s.mean() * 100.0)),
            average_entries=("avg_entries", "mean"),
        )
    )
    return {"by_day": by_day, "by_locality": by_locality, "hourly": hourly_summary}


def revenue_efficiency_segments(performance: pd.DataFrame) -> pd.DataFrame:
    """Compare large/inefficient and small/high-utilisation facilities."""
    frame = performance.copy()
    median_capacity = float(frame["capacity"].median())
    p25_efficiency = float(frame["revenue_per_space_inr"].quantile(0.25))
    p75_occupancy = float(frame["avg_occupancy_pct"].quantile(0.75))
    frame["efficiency_pattern"] = np.select(
        [
            (frame["capacity"] >= median_capacity) & (frame["revenue_per_space_inr"] <= p25_efficiency),
            (frame["capacity"] < median_capacity) & (frame["avg_occupancy_pct"] >= p75_occupancy),
        ],
        ["LARGE_INEFFICIENT", "SMALL_HIGH_UTILIZATION"],
        default="OTHER",
    )
    return frame[frame["efficiency_pattern"] != "OTHER"].sort_values(
        ["efficiency_pattern", "avg_occupancy_pct"], ascending=[True, False]
    )


def competition_quadrants(scores: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Classify demand and raw competitor pressure into four contextual bands."""
    frame = scores.copy()
    demand_cutoff = float(frame["demand_score"].median())
    competition_cutoff = float(frame["competitor_count_1km"].median())
    frame["competition_quadrant"] = np.select(
        [
            (frame["demand_score"] >= demand_cutoff) & (frame["competitor_count_1km"] < competition_cutoff),
            (frame["demand_score"] >= demand_cutoff) & (frame["competitor_count_1km"] >= competition_cutoff),
            (frame["demand_score"] < demand_cutoff) & (frame["competitor_count_1km"] < competition_cutoff),
        ],
        ["HIGH_DEMAND_LOW_COMPETITION", "HIGH_DEMAND_HIGH_COMPETITION", "LOW_DEMAND_LOW_COMPETITION"],
        default="LOW_DEMAND_HIGH_COMPETITION",
    )
    return frame, {"demand_score_median": demand_cutoff, "competitor_count_median": competition_cutoff}


def classify_markets(locality: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Classify markets using median opportunity and documented whitespace axes."""
    frame = locality.copy()
    opportunity_cutoff = float(frame["avg_acquisition_score"].median())
    whitespace_cutoff = float(frame["market_whitespace_score"].median())
    frame["market_class"] = np.select(
        [
            (frame["avg_acquisition_score"] >= opportunity_cutoff) & (frame["market_whitespace_score"] >= whitespace_cutoff),
            (frame["avg_acquisition_score"] < opportunity_cutoff) & (frame["market_whitespace_score"] >= whitespace_cutoff),
            (frame["avg_acquisition_score"] >= opportunity_cutoff) & (frame["market_whitespace_score"] < whitespace_cutoff),
        ],
        ["STRONG", "EMERGING", "SATURATED"],
        default="WEAK",
    )
    frame["whitespace_indicator"] = np.where(
        frame["market_whitespace_score"] >= whitespace_cutoff, "HIGH_WHITESPACE", "LOW_WHITESPACE"
    )
    return frame, {
        "avg_acquisition_score_median": opportunity_cutoff,
        "market_whitespace_score_median": whitespace_cutoff,
    }


def bd_conversion_breakdowns(outreach: pd.DataFrame) -> pd.DataFrame:
    """Return descriptive BD conversion cuts, explicitly retaining sample size."""
    frame = outreach.copy()
    frame["acquired"] = frame["pipeline_status"].eq("Won")
    frame["capacity_segment"] = pd.qcut(
        frame["capacity_cars"], q=4, labels=["Q1 Small", "Q2", "Q3", "Q4 Large"], duplicates="drop"
    )
    frame["digital_readiness"] = np.where(
        frame["digital_payment_enabled"] & frame["management_system"].ne("Manual"), "Digitally Ready", "Needs Enablement"
    )
    dimensions = ["lead_source", "owner_type", "capacity_segment", "digital_readiness", "locality_name"]
    rows: list[dict[str, Any]] = []
    for dimension in dimensions:
        grouped = frame.groupby(dimension, dropna=False, observed=False)
        for value, group in grouped:
            rows.append(
                {
                    "dimension": dimension,
                    "segment": str(value),
                    "leads": int(len(group)),
                    "acquired": int(group["acquired"].sum()),
                    "acquisition_rate_pct": round(float(group["acquired"].mean() * 100.0), 2) if len(group) else None,
                    "avg_days_to_acquisition": round(float(group.loc[group["acquired"], "days_to_conversion"].mean()), 2)
                    if group["acquired"].any()
                    else None,
                    "synthetic_caveat": "Descriptive synthetic funnel cut; not causal evidence.",
                }
            )
    return pd.DataFrame(rows).sort_values(["dimension", "acquisition_rate_pct", "leads"], ascending=[True, False, False])


def score_distribution_summary(scores: pd.DataFrame) -> pd.DataFrame:
    """Return percentile summaries for the five pillars and final score."""
    columns = [
        "demand_score",
        "revenue_score",
        "competition_score",
        "strategic_fit_score",
        "feasibility_score",
        "attractiveness_score",
        "acquisition_score",
    ]
    rows: list[dict[str, Any]] = []
    for column in columns:
        series = pd.to_numeric(scores[column], errors="coerce").dropna()
        quantiles = series.quantile([0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
        rows.append(
            {
                "metric": column,
                "min": float(series.min()),
                "p01": float(quantiles.loc[0.01]),
                "p05": float(quantiles.loc[0.05]),
                "p25": float(quantiles.loc[0.25]),
                "median": float(quantiles.loc[0.50]),
                "mean": float(series.mean()),
                "p75": float(quantiles.loc[0.75]),
                "p95": float(quantiles.loc[0.95]),
                "p99": float(quantiles.loc[0.99]),
                "max": float(series.max()),
                "std": float(series.std(ddof=1)),
            }
        )
    return pd.DataFrame(rows)
