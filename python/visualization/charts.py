"""Purposeful matplotlib charts for the validation layer analytical outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from python.analysis.statistics import spearman_matrix


PALETTE = {
    "ACQUIRE_NOW": "#0B6E4F",
    "PURSUE": "#D97706",
    "DEVELOP": "#2563EB",
    "AVOID": "#6B7280",
    "HIGH_DEMAND_LOW_COMPETITION": "#0B6E4F",
    "HIGH_DEMAND_HIGH_COMPETITION": "#D97706",
    "LOW_DEMAND_LOW_COMPETITION": "#2563EB",
    "LOW_DEMAND_HIGH_COMPETITION": "#6B7280",
}
SOURCE_NOTE = "Source: PostgreSQL analytics views and source facts; operational/economic fields are synthetic."


def _finish(fig: plt.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, 0.01, SOURCE_NOTE, fontsize=7, color="#4B5563")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def plot_parking_characteristics(scores: pd.DataFrame, path: Path) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].hist(scores["capacity_cars"], bins=18, color="#1D4ED8", alpha=0.85)
    axes[0, 0].set_title("Capacity distribution")
    axes[0, 0].set_xlabel("Cars")
    axes[0, 0].set_ylabel("Parking lots")
    axes[0, 1].hist(scores["hourly_rate_inr"], bins=14, color="#0F766E", alpha=0.85)
    axes[0, 1].set_title("Hourly price distribution")
    axes[0, 1].set_xlabel("INR per hour")
    axes[0, 1].set_ylabel("Parking lots")
    type_order = scores.groupby("parking_type")["capacity_cars"].median().sort_values().index
    axes[1, 0].boxplot(
        [scores.loc[scores["parking_type"] == parking_type, "capacity_cars"] for parking_type in type_order],
        tick_labels=type_order,
        vert=False,
        patch_artist=True,
        boxprops={"facecolor": "#BFDBFE"},
    )
    axes[1, 0].set_title("Capacity by parking type")
    axes[1, 0].set_xlabel("Cars")
    axes[1, 0].tick_params(axis="y", labelsize=8)
    locality = scores.groupby("locality_name", as_index=False)["parking_id"].count().sort_values("parking_id", ascending=True)
    axes[1, 1].barh(locality["locality_name"], locality["parking_id"], color="#334155")
    axes[1, 1].set_title("Parking lots by locality")
    axes[1, 1].set_xlabel("Lots")
    axes[1, 1].tick_params(axis="y", labelsize=7)
    return _finish(fig, path)


def plot_demand_patterns(scores: pd.DataFrame, daily_summary: dict[str, pd.DataFrame], path: Path) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].hist(scores["avg_occupancy_rate"] * 100.0, bins=18, color="#7C3AED", alpha=0.85)
    axes[0, 0].set_title("Average occupancy distribution")
    axes[0, 0].set_xlabel("Average occupancy (%)")
    axes[0, 0].set_ylabel("Parking lots")
    by_day = daily_summary["by_day"]
    axes[0, 1].bar(by_day["day_of_week"], by_day["average_occupancy_pct"], color="#0F766E")
    axes[0, 1].set_title("Observed occupancy by day of week")
    axes[0, 1].set_ylabel("Average occupancy (%)")
    axes[0, 1].tick_params(axis="x", rotation=45)
    hourly = daily_summary["hourly"]
    for day_type, group in hourly.groupby("day_type"):
        axes[1, 0].plot(group["hour_of_day"], group["average_occupancy_pct"], marker="o", label=day_type)
    axes[1, 0].set_title("Portfolio occupancy by hour")
    axes[1, 0].set_xlabel("Hour of day")
    axes[1, 0].set_ylabel("Average occupancy (%)")
    axes[1, 0].set_xticks(range(0, 24, 2))
    axes[1, 0].legend(frameon=False)
    locality = daily_summary["by_locality"].sort_values("average_occupancy_pct")
    axes[1, 1].barh(locality["locality_name"], locality["average_occupancy_pct"], color="#475569")
    axes[1, 1].set_title("Average occupancy by locality")
    axes[1, 1].set_xlabel("Average occupancy (%)")
    axes[1, 1].tick_params(axis="y", labelsize=7)
    return _finish(fig, path)


def _scatter_with_trend(ax: plt.Axes, frame: pd.DataFrame, x: str, y: str, title: str, xlabel: str, ylabel: str) -> None:
    data = frame[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    ax.scatter(data[x], data[y], s=24, alpha=0.62, color="#2563EB", edgecolor="none")
    if len(data) >= 3 and data[x].nunique() > 1:
        coefficients = np.polyfit(data[x], data[y], 1)
        domain = np.linspace(data[x].min(), data[x].max(), 40)
        ax.plot(domain, coefficients[0] * domain + coefficients[1], color="#DC2626", linewidth=1.2, label="Descriptive linear trend")
        ax.legend(frameon=False, fontsize=7)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)


def plot_relationships(scores: pd.DataFrame, path: Path) -> str:
    frame = scores.copy()
    frame["commercial_density_proxy"] = frame[["office_count_500m", "retail_count_500m", "restaurant_count_500m"]].sum(axis=1)
    frame["destination_density_proxy"] = frame[["retail_count_500m", "restaurant_count_500m", "hospital_count_1km", "education_count_1km"]].sum(axis=1)
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    _scatter_with_trend(axes[0, 0], frame, "capacity_cars", "avg_occupancy_rate", "Occupancy vs capacity", "Capacity (cars)", "Occupancy rate")
    _scatter_with_trend(axes[0, 1], frame, "hourly_rate_inr", "avg_occupancy_rate", "Occupancy vs hourly price", "INR per hour", "Occupancy rate")
    _scatter_with_trend(axes[0, 2], frame, "metro_distance_m", "avg_occupancy_rate", "Occupancy vs metro distance", "Metro distance (m)", "Occupancy rate")
    _scatter_with_trend(axes[1, 0], frame, "commercial_density_proxy", "avg_occupancy_rate", "Occupancy vs commercial proxy", "Nearby commercial POI count", "Occupancy rate")
    _scatter_with_trend(axes[1, 1], frame, "destination_density_proxy", "avg_occupancy_rate", "Occupancy vs destination proxy", "Nearby destination POI count", "Occupancy rate")
    _scatter_with_trend(axes[1, 2], frame, "avg_occupancy_rate", "avg_daily_platform_bookings", "Bookings vs occupancy", "Occupancy rate", "Average daily platform bookings")
    return _finish(fig, path)


def plot_revenue_efficiency(performance: pd.DataFrame, efficiency: pd.DataFrame, path: Path) -> str:
    frame = performance.copy()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(frame["capacity"], frame["revenue_per_space_inr"], s=frame["avg_occupancy_pct"] * 3 + 18, color="#94A3B8", alpha=0.65, label="Other lots")
    for pattern, color in [("LARGE_INEFFICIENT", "#DC2626"), ("SMALL_HIGH_UTILIZATION", "#0B6E4F")]:
        selected = efficiency[efficiency["efficiency_pattern"] == pattern]
        ax.scatter(selected["capacity"], selected["revenue_per_space_inr"], s=55, color=color, label=pattern.replace("_", " ").title(), edgecolor="white", linewidth=0.5)
    ax.set_title("Capacity does not determine economic efficiency")
    ax.set_xlabel("Capacity (cars)")
    ax.set_ylabel("Gross revenue per space per day (INR)")
    ax.legend(frameon=False)
    return _finish(fig, path)


def plot_competition_quadrant(quadrants: pd.DataFrame, cutoffs: dict[str, float], path: Path) -> str:
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, group in quadrants.groupby("competition_quadrant"):
        ax.scatter(group["competitor_count_1km"], group["demand_score"], s=group["capacity_cars"] * 0.8 + 18, alpha=0.72, color=PALETTE.get(label, "#64748B"), label=label.replace("_", " ").title())
    ax.axvline(cutoffs["competitor_count_median"], color="#64748B", linestyle="--", linewidth=1)
    ax.axhline(cutoffs["demand_score_median"], color="#64748B", linestyle="--", linewidth=1)
    ax.set_title("Demand and competition must be read together")
    ax.set_xlabel("Competitor count within 1 km")
    ax.set_ylabel("Demand score")
    ax.legend(frameon=False, fontsize=8)
    return _finish(fig, path)


def plot_market_opportunity(markets: pd.DataFrame, cutoffs: dict[str, float], path: Path) -> str:
    fig, ax = plt.subplots(figsize=(11, 7))
    for market_class, group in markets.groupby("market_class"):
        ax.scatter(group["market_whitespace_score"], group["avg_acquisition_score"], s=group["parking_count"] * 30 + 28, alpha=0.82, label=market_class.title(), color={"STRONG": "#0B6E4F", "EMERGING": "#2563EB", "SATURATED": "#D97706", "WEAK": "#6B7280"}.get(market_class, "#64748B"))
    for _, row in markets.sort_values("market_whitespace_score", ascending=False).head(6).iterrows():
        ax.annotate(row["locality_name"], (row["market_whitespace_score"], row["avg_acquisition_score"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    ax.axvline(cutoffs["market_whitespace_score_median"], color="#64748B", linestyle="--", linewidth=1)
    ax.axhline(cutoffs["avg_acquisition_score_median"], color="#64748B", linestyle="--", linewidth=1)
    ax.set_title("Locality opportunity: acquisition strength vs network whitespace")
    ax.set_xlabel("Market whitespace score")
    ax.set_ylabel("Average acquisition score")
    ax.legend(frameon=False)
    return _finish(fig, path)


def plot_score_diagnostics(scores: pd.DataFrame, correlation_matrix: pd.DataFrame, path: Path) -> str:
    score_columns = ["demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score", "acquisition_score"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    for ax, column in zip(axes.flat, score_columns):
        ax.hist(scores[column], bins=14, color="#1E3A8A" if column == "acquisition_score" else "#64748B", alpha=0.85)
        ax.set_title(column.replace("_", " ").title(), fontsize=10)
        ax.set_xlabel("Score (0-100)")
        ax.set_ylabel("Lots")
    return _finish(fig, path)


def plot_score_correlation_heatmap(scores: pd.DataFrame, path: Path) -> str:
    fields = ["demand_score", "revenue_score", "competition_score", "strategic_fit_score", "feasibility_score", "acquisition_score"]
    matrix = spearman_matrix(scores[fields])
    fig, ax = plt.subplots(figsize=(8, 7))
    image = ax.imshow(matrix.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(fields)), [field.replace("_score", "").replace("_", " ").title() for field in fields], rotation=45, ha="right")
    ax.set_yticks(range(len(fields)), [field.replace("_score", "").replace("_", " ").title() for field in fields])
    for row in range(len(fields)):
        for col in range(len(fields)):
            ax.text(col, row, f"{matrix.iloc[row, col]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title("Score component Spearman correlations")
    fig.colorbar(image, ax=ax, label="Spearman correlation")
    return _finish(fig, path)


def plot_component_influence(influence: pd.DataFrame, path: Path) -> str:
    frame = influence.sort_values("weighted_contribution_std", ascending=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh(frame["dimension"], frame["weighted_contribution_std"], color="#1D4ED8")
    axes[0].set_title("Weighted contribution spread")
    axes[0].set_xlabel("Standard deviation of weighted contribution")
    axes[1].barh(frame["dimension"], frame["mean_abs_rank_change_when_neutralized"], color="#D97706")
    axes[1].set_title("Rank movement when component is neutralized")
    axes[1].set_xlabel("Mean absolute rank change")
    return _finish(fig, path)


def plot_scenario_summary(summary: pd.DataFrame, path: Path) -> str:
    frame = summary[summary["scenario_code"] != "BASE_CASE"].copy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh(frame["scenario_code"], frame["top_10_changes"], color="#DC2626")
    axes[0].set_title("Top-10 changes from base case")
    axes[0].set_xlabel("Lots leaving/replacing base Top 10")
    axes[1].barh(frame["scenario_code"], frame["mean_abs_rank_change"], color="#7C3AED")
    axes[1].set_title("Average absolute rank movement")
    axes[1].set_xlabel("Rank positions")
    return _finish(fig, path)


def plot_rank_stability(stability: pd.DataFrame, path: Path) -> str:
    frame = stability.sort_values("base_rank").head(20).copy()
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.errorbar(frame["base_rank"], frame["average_rank"], yerr=[frame["average_rank"] - frame["best_rank"], frame["worst_rank"] - frame["average_rank"]], fmt="o", color="#1D4ED8", ecolor="#94A3B8", capsize=3)
    ax.plot([1, 20], [1, 20], linestyle="--", color="#64748B", linewidth=1)
    for _, row in frame.head(10).iterrows():
        ax.annotate(str(int(row["parking_id"])), (row["base_rank"], row["average_rank"]), xytext=(4, 3), textcoords="offset points", fontsize=8)
    ax.set_title("Top-20 rank stability across validation scenarios")
    ax.set_xlabel("Base rank")
    ax.set_ylabel("Average scenario rank; whiskers show best/worst")
    ax.invert_yaxis()
    return _finish(fig, path)


def plot_revenue_sensitivity(portfolio: pd.DataFrame, path: Path) -> str:
    frame = portfolio[portfolio["price_multiplier"] == 1.0].copy()
    fig, ax = plt.subplots(figsize=(10, 6))
    for commission, group in frame.groupby("commission_scenario"):
        group = group.sort_values("occupancy_rate")
        ax.plot(group["occupancy_rate"] * 100.0, group["total_expected_monthly_platform_revenue_inr"] / 100000.0, marker="o", label=commission.replace("GLOBAL_", "").replace("_PCT", "%") if isinstance(commission, str) else str(commission))
    ax.set_title("Expected platform revenue sensitivity to occupancy and commission")
    ax.set_xlabel("Scenario occupancy (%)")
    ax.set_ylabel("Portfolio expected monthly platform revenue (INR lakh)")
    ax.legend(frameon=False, title="Commission scenario")
    return _finish(fig, path)


def create_analysis_charts(
    *,
    scores: pd.DataFrame,
    performance: pd.DataFrame,
    daily_summary: dict[str, pd.DataFrame],
    efficiency: pd.DataFrame,
    quadrants: pd.DataFrame,
    quadrant_cutoffs: dict[str, float],
    markets: pd.DataFrame,
    market_cutoffs: dict[str, float],
    influence: pd.DataFrame,
    scenario_summary: pd.DataFrame,
    stability: pd.DataFrame,
    revenue_sensitivity: pd.DataFrame,
    output_dir: Path,
) -> dict[str, str]:
    """Create the restrained validation chart set and return paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "parking_characteristics": plot_parking_characteristics(scores, output_dir / "01_parking_characteristics.png"),
        "demand_patterns": plot_demand_patterns(scores, daily_summary, output_dir / "02_demand_patterns.png"),
        "relationships": plot_relationships(scores, output_dir / "03_demand_relationships.png"),
        "revenue_efficiency": plot_revenue_efficiency(performance, efficiency, output_dir / "04_revenue_efficiency.png"),
        "competition_quadrant": plot_competition_quadrant(quadrants, quadrant_cutoffs, output_dir / "05_competition_quadrant.png"),
        "market_opportunity": plot_market_opportunity(markets, market_cutoffs, output_dir / "06_market_opportunity.png"),
        "score_distributions": plot_score_diagnostics(scores, pd.DataFrame(), output_dir / "07_score_distributions.png"),
        "score_correlations": plot_score_correlation_heatmap(scores, output_dir / "08_score_correlations.png"),
        "component_influence": plot_component_influence(influence, output_dir / "09_component_influence.png"),
        "scenario_summary": plot_scenario_summary(scenario_summary, output_dir / "10_scenario_summary.png"),
        "rank_stability": plot_rank_stability(stability, output_dir / "11_rank_stability.png"),
        "revenue_sensitivity": plot_revenue_sensitivity(revenue_sensitivity, output_dir / "12_revenue_sensitivity.png"),
    }
    return outputs
