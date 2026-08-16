"""Deterministic, relationship-aware synthetic source data generation."""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import settings  # noqa: E402


MARKET_BASE = {
    "CBD": 0.88,
    "Commercial": 0.78,
    "Retail High Street": 0.82,
    "IT/Office Park": 0.77,
    "Residential": 0.55,
    "Transit Hub": 0.84,
    "Hospital/Institutional": 0.68,
    "Mixed Use": 0.72,
}

TYPE_CAPACITY = {
    "Surface Lot": (45, 220),
    "Multi-Level (MLCP)": (180, 850),
    "Basement": (70, 350),
    "Mall Parking": (180, 900),
    "Metro Station Parking": (120, 650),
    "On-Street Authorised": (25, 140),
    "Hospital Parking": (70, 420),
    "Office Complex": (100, 600),
}

OWNER_TYPE_BY_PARKING = {
    "Mall Parking": "Mall Management",
    "Metro Station Parking": "Government/Municipal",
    "On-Street Authorised": "Government/Municipal",
    "Hospital Parking": "Hospital/Institution",
    "Office Complex": "Private Company",
    "Basement": "Private Company",
    "Multi-Level (MLCP)": "Private Company",
}


def _normalised_log(series: pd.Series) -> np.ndarray:
    values = np.log1p(series.astype(float).to_numpy())
    upper = float(np.quantile(values, 0.95)) if len(values) else 1.0
    return np.clip(values / max(upper, 1e-9), 0, 1)


def demand_signal(
    lots: pd.DataFrame, demand: pd.DataFrame, localities: pd.DataFrame, rng: np.random.Generator
) -> np.ndarray:
    frame = (
        lots[["parking_id", "locality_id"]]
        .merge(demand, on="parking_id", validate="one_to_one")
        .merge(
            localities[["locality_id", "micro_market_type"]],
            on="locality_id",
            validate="many_to_one",
        )
    )
    metro = np.exp(-frame["metro_distance_m"].to_numpy(dtype=float) / 1200.0)
    commercial = (
        0.35 * _normalised_log(frame["office_count_500m"])
        + 0.35 * _normalised_log(frame["retail_count_500m"])
        + 0.30 * _normalised_log(frame["restaurant_count_500m"])
    )
    destinations = (
        0.5 * _normalised_log(frame["hospital_count_1km"])
        + 0.5 * _normalised_log(frame["education_count_1km"])
    )
    transit = _normalised_log(frame["transit_stop_count_500m"])
    market = frame["micro_market_type"].map(MARKET_BASE).to_numpy(dtype=float)
    signal = (
        0.23 * metro
        + 0.29 * commercial
        + 0.12 * destinations
        + 0.13 * transit
        + 0.23 * market
        + rng.normal(0, 0.055, len(frame))
    )
    return np.clip(signal, 0.08, 0.98)


def _capacity_for_type(parking_type: str, rng: np.random.Generator) -> int:
    low, high = TYPE_CAPACITY[parking_type]
    centre = math.sqrt(low * high)
    value = int(round(rng.lognormal(math.log(centre), 0.38)))
    return int(np.clip(value, low, high))


def _preferred_owner_type(parking_type: str, rng: np.random.Generator) -> str:
    if parking_type in OWNER_TYPE_BY_PARKING:
        return OWNER_TYPE_BY_PARKING[parking_type]
    return str(
        rng.choice(
            ["Individual", "Family Trust", "Private Company", "RWA", "Government/Municipal"],
            p=[0.19, 0.15, 0.38, 0.17, 0.11],
        )
    )


def _owner_traits(owner_id: int, owner_type: str, rng: np.random.Generator) -> dict[str, Any]:
    maturity_base = {
        "Individual": 0.43,
        "Family Trust": 0.42,
        "Private Company": 0.69,
        "RWA": 0.46,
        "Mall Management": 0.78,
        "Government/Municipal": 0.34,
        "Hospital/Institution": 0.61,
    }[owner_type]
    maturity = float(np.clip(maturity_base + rng.normal(0, 0.16), 0.05, 0.97))
    if maturity < 0.27:
        system = str(rng.choice(["None/Manual", "Paper Register"], p=[0.65, 0.35]))
    elif maturity < 0.52:
        system = str(rng.choice(["Paper Register", "Spreadsheet"], p=[0.52, 0.48]))
    elif maturity < 0.76:
        system = str(rng.choice(["Spreadsheet", "Basic POS"], p=[0.38, 0.62]))
    else:
        system = str(rng.choice(["Basic POS", "Third-party App"], p=[0.45, 0.55]))
    willingness = int(np.clip(round(1 + 4 * maturity + rng.normal(0, 0.65)), 1, 5))
    rigidity = 0.12 if owner_type in {"Government/Municipal", "RWA"} else 0
    flexibility = int(
        np.clip(round(1 + 3.7 * maturity - rigidity * 5 + rng.normal(0, 0.8)), 1, 5)
    )
    access_probability = {
        "Government/Municipal": 0.37,
        "RWA": 0.58,
        "Mall Management": 0.72,
        "Private Company": 0.76,
    }.get(owner_type, 0.70)
    return {
        "owner_id": owner_id,
        "owner_code": f"OWN-{owner_id:04d}",
        "owner_name": f"Synthetic Operator {owner_id:03d}",
        "owner_type": owner_type,
        "years_operating": int(np.clip(round(rng.gamma(2.3, 5.0)), 0, 55)),
        "digital_payment_enabled": bool(rng.random() < 0.15 + 0.77 * maturity),
        "management_system": system,
        "willingness_to_digitize": willingness,
        "contract_flexibility": flexibility,
        "decision_maker_accessible": bool(rng.random() < access_probability),
        "_digital_maturity": maturity,
    }


def generate_owners_and_lots(
    candidates: pd.DataFrame, localities: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, float]]:
    owners: list[dict[str, Any]] = []
    owner_ids_by_type: dict[str, list[int]] = {}
    lot_rows: list[dict[str, Any]] = []
    owner_maturity: dict[int, float] = {}

    locality_type = localities.set_index("locality_id")["micro_market_type"].to_dict()
    for candidate in candidates.itertuples(index=False):
        parking_type = candidate.parking_type
        market_type = locality_type[int(candidate.locality_id)]
        if parking_type == "Surface Lot" and pd.isna(candidate.capacity_public):
            assumed_mix = {
                "CBD": (["Surface Lot", "Basement", "Multi-Level (MLCP)", "Office Complex"], [0.30, 0.24, 0.24, 0.22]),
                "Commercial": (["Surface Lot", "Basement", "Multi-Level (MLCP)", "Office Complex"], [0.36, 0.20, 0.18, 0.26]),
                "Retail High Street": (["Surface Lot", "Mall Parking", "Basement", "Multi-Level (MLCP)", "On-Street Authorised"], [0.30, 0.24, 0.14, 0.14, 0.18]),
                "IT/Office Park": (["Surface Lot", "Office Complex", "Basement", "Multi-Level (MLCP)"], [0.31, 0.38, 0.17, 0.14]),
                "Residential": (["Surface Lot", "Basement", "On-Street Authorised"], [0.55, 0.22, 0.23]),
                "Transit Hub": (["Surface Lot", "Metro Station Parking", "On-Street Authorised", "Multi-Level (MLCP)"], [0.27, 0.39, 0.17, 0.17]),
                "Hospital/Institutional": (["Surface Lot", "Hospital Parking", "Basement"], [0.42, 0.40, 0.18]),
                "Mixed Use": (["Surface Lot", "Basement", "Office Complex", "On-Street Authorised", "Mall Parking"], [0.36, 0.17, 0.18, 0.15, 0.14]),
            }
            types, probabilities = assumed_mix[market_type]
            parking_type = str(rng.choice(types, p=probabilities))
        owner_type = _preferred_owner_type(parking_type, rng)
        existing = owner_ids_by_type.get(owner_type, [])
        reuse_probability = 0.42 if owner_type in {
            "Mall Management",
            "Private Company",
            "Government/Municipal",
            "Hospital/Institution",
        } else 0.16
        if existing and rng.random() < reuse_probability:
            owner_id = int(rng.choice(existing))
        else:
            owner_id = len(owners) + 1
            owner = _owner_traits(owner_id, owner_type, rng)
            owner_maturity[owner_id] = float(owner.pop("_digital_maturity"))
            owners.append(owner)
            owner_ids_by_type.setdefault(owner_type, []).append(owner_id)

        if pd.notna(candidate.capacity_public):
            capacity = int(candidate.capacity_public)
            capacity_source = "PUBLIC"
        else:
            capacity = _capacity_for_type(parking_type, rng)
            capacity_source = "SYNTHETIC"

        market_price = {
            "CBD": 70,
            "Commercial": 55,
            "Retail High Street": 50,
            "IT/Office Park": 48,
            "Residential": 28,
            "Transit Hub": 42,
            "Hospital/Institutional": 38,
            "Mixed Use": 40,
        }[market_type]
        price = float(np.clip(round(rng.lognormal(math.log(market_price), 0.28) / 5) * 5, 10, 180))

        opening_hours = str(candidate.opening_hours or "")
        if opening_hours.strip() == "24/7":
            is_24x7 = True
            opens_at = None
            closes_at = None
            hours_source = "PUBLIC"
        else:
            p_24 = 0.70 if parking_type in {
                "Hospital Parking",
                "Metro Station Parking",
                "On-Street Authorised",
            } else 0.20
            is_24x7 = bool(rng.random() < p_24)
            opens_at = None if is_24x7 else "06:00:00"
            closes_at = None if is_24x7 else str(
                rng.choice(["22:00:00", "23:00:00", "00:00:00"], p=[0.30, 0.55, 0.15])
            )
            hours_source = "ASSUMED"

        covered_base = parking_type in {
            "Multi-Level (MLCP)", "Basement", "Mall Parking", "Office Complex"
        }
        covered = bool(rng.random() < (0.88 if covered_base else 0.13))
        security = bool(rng.random() < (0.82 if owner_type != "Individual" else 0.55))
        cctv = bool(rng.random() < (0.75 if security else 0.34))
        monthly_pass = (
            round(price * 8 * 22 * rng.uniform(0.34, 0.55) / 100) * 100
            if parking_type not in {"Mall Parking", "Hospital Parking"} and rng.random() < 0.72
            else None
        )
        data_quality = (
            "High"
            if bool(candidate.is_named) and capacity_source == "PUBLIC"
            else "Medium"
            if bool(candidate.is_named)
            else "Fallback"
        )
        lot_rows.append(
            {
                "parking_id": int(candidate.parking_id),
                "lot_code": candidate.lot_code,
                "lot_name": candidate.lot_name,
                "locality_id": int(candidate.locality_id),
                "owner_id": owner_id,
                "latitude": round(float(candidate.latitude), 6),
                "longitude": round(float(candidate.longitude), 6),
                "parking_type": parking_type,
                "surface_type": "Paved" if rng.random() < 0.88 else "Mixed",
                "capacity_cars": capacity,
                "hourly_rate_inr": price,
                "monthly_pass_inr": monthly_pass,
                "is_24x7": is_24x7,
                "opens_at": opens_at,
                "closes_at": closes_at,
                "has_covered_parking": covered,
                "has_security_staff": security,
                "has_cctv": cctv,
                "record_source": "public_osm",
                "source_name": "OpenStreetMap",
                "source_reference": candidate.source_reference,
                "source_observed_on": settings.source_observed_on.isoformat(),
                "capacity_source_type": capacity_source,
                "price_source_type": "SYNTHETIC",
                "hours_source_type": hours_source,
                "amenities_source_type": "SYNTHETIC",
                "data_quality_flag": data_quality,
                "osm_id": int(candidate.osm_id),
                "created_at": f"{settings.source_observed_on.isoformat()}T00:00:00+05:30",
            }
        )
    return pd.DataFrame(owners), pd.DataFrame(lot_rows), owner_maturity


def complete_competition(
    public_competition: pd.DataFrame,
    lots: pd.DataFrame,
    localities: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    frame = public_competition.merge(
        lots[["parking_id", "hourly_rate_inr", "locality_id"]], on="parking_id"
    ).merge(localities[["locality_id", "micro_market_type"]], on="locality_id")
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        if row.competitor_count_1km > 0:
            avg_price = float(
                np.clip(round(row.hourly_rate_inr * rng.lognormal(-0.03, 0.25) / 5) * 5, 5, 220)
            )
            digitisation_p = 0.08 + 0.12 * MARKET_BASE[row.micro_market_type]
            listed = int(rng.binomial(row.competitor_count_1km, digitisation_p))
        else:
            avg_price = None
            listed = 0
        rows.append(
            {
                "parking_id": int(row.parking_id),
                "competitor_count_500m": int(row.competitor_count_500m),
                "competitor_count_1km": int(row.competitor_count_1km),
                "nearest_competitor_distance_m": row.nearest_competitor_distance_m,
                "competitor_avg_hourly_rate_inr": avg_price,
                "competitor_total_capacity_1km": row.competitor_total_capacity_1km,
                "aggregator_listed_count_1km": listed,
                "measured_on": row.measured_on,
                "record_source": "public_osm",
            }
        )
    return pd.DataFrame(rows)


def generate_acquisition_terms(
    lots: pd.DataFrame,
    owners: pd.DataFrame,
    owner_maturity: dict[int, float],
    rng: np.random.Generator,
) -> pd.DataFrame:
    owner_index = owners.set_index("owner_id")
    rows: list[dict[str, Any]] = []
    for lot in lots.itertuples(index=False):
        owner = owner_index.loc[lot.owner_id]
        maturity = owner_maturity[int(lot.owner_id)]
        documentation = int(
            np.clip(round(1 + 3.5 * maturity + rng.normal(0, 0.75)), 1, 5)
        )
        type_complexity = {
            "On-Street Authorised": 4.1,
            "Multi-Level (MLCP)": 3.4,
            "Metro Station Parking": 3.8,
            "Mall Parking": 3.0,
            "Basement": 2.8,
        }.get(lot.parking_type, 2.4)
        complexity = int(np.clip(round(type_complexity + rng.normal(0, 0.75)), 1, 5))
        capex_probability = 0.18 + 0.13 * complexity + (0.15 if not lot.has_cctv else -0.06)
        requires_capex = bool(rng.random() < np.clip(capex_probability, 0.08, 0.85))
        cost = (
            12_000
            + lot.capacity_cars * rng.uniform(110, 320)
            + complexity * 7_500
            + (35_000 if requires_capex else 0)
        )
        commission = float(
            np.clip(
                round(
                    (8.0 + 2.0 * owner.contract_flexibility + 2.0 * maturity + rng.normal(0, 2.1))
                    * 2
                )
                / 2,
                5,
                28,
            )
        )
        rows.append(
            {
                "parking_id": int(lot.parking_id),
                "expected_commission_pct": commission,
                "estimated_onboarding_cost_inr": round(cost / 500) * 500,
                "documentation_readiness": documentation,
                "operational_complexity": complexity,
                "exclusivity_possible": bool(
                    rng.random() < 0.18 + 0.12 * owner.contract_flexibility
                ),
                "requires_capex": requires_capex,
                "estimated_setup_days": int(
                    np.clip(round(4 + complexity * 8 + (12 if requires_capex else 0) + rng.normal(0, 6)), 3, 90)
                ),
                "quoted_on": settings.obs_end_date.isoformat(),
            }
        )
    return pd.DataFrame(rows)


def generate_network_sites(
    markets: pd.DataFrame, lots: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    selected = markets.sample(n=min(14, len(markets)), random_state=settings.random_seed).copy()
    rows: list[dict[str, Any]] = []
    for index, market in enumerate(selected.itertuples(index=False), start=1):
        local_capacity = lots.loc[lots["locality_id"] == market.locality_id, "capacity_cars"]
        capacity = int(np.clip(round(local_capacity.median() * rng.uniform(0.65, 1.15)), 20, 1200))
        rows.append(
            {
                "network_site_id": index,
                "site_code": f"NET-{index:04d}",
                "locality_id": int(market.locality_id),
                "latitude": round(float(market.latitude + rng.normal(0, 0.004)), 6),
                "longitude": round(float(market.longitude + rng.normal(0, 0.004)), 6),
                "capacity_cars": capacity,
                "live_since": (
                    settings.obs_start_date - timedelta(days=int(rng.integers(90, 900)))
                ).isoformat(),
                "site_status": str(rng.choice(["Live", "Paused"], p=[0.86, 0.14])),
            }
        )
    return pd.DataFrame(rows)


def _operating_hours(lot: pd.Series) -> float:
    if bool(lot["is_24x7"]):
        return 24.0
    open_hour = int(str(lot["opens_at"]).split(":")[0])
    close_hour = int(str(lot["closes_at"]).split(":")[0])
    duration = (close_hour - open_hour) % 24
    return float(duration if duration else 24)


def generate_daily_performance(
    lots: pd.DataFrame,
    owners: pd.DataFrame,
    localities: pd.DataFrame,
    signals: np.ndarray,
    competition: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    dates = pd.date_range(settings.obs_start_date, settings.obs_end_date, freq="D")
    owner_index = owners.set_index("owner_id")
    locality_type = localities.set_index("locality_id")["micro_market_type"].to_dict()
    competitor_index = competition.set_index("parking_id")
    rows: list[dict[str, Any]] = []
    day_index = np.arange(len(dates))

    for position, lot in lots.reset_index(drop=True).iterrows():
        market_type = locality_type[int(lot["locality_id"])]
        signal = float(signals[position])
        comp_count = float(competitor_index.loc[lot["parking_id"], "competitor_count_1km"])
        comp_pressure = min(math.log1p(comp_count) / math.log(15), 1.0)
        base_occupancy = float(
            np.clip(0.19 + 0.52 * signal - 0.10 * comp_pressure + rng.normal(0, 0.075), 0.12, 0.84)
        )
        weekend_factor = {
            "CBD": 0.58,
            "Commercial": 0.72,
            "Retail High Street": 1.18,
            "IT/Office Park": 0.53,
            "Residential": 1.10,
            "Transit Hub": 0.84,
            "Hospital/Institutional": 0.98,
            "Mixed Use": 1.03,
        }[market_type]
        is_weekend = dates.dayofweek.to_numpy() >= 5
        day_factor = np.where(is_weekend, weekend_factor, 1.0)
        months = dates.month.to_numpy()
        seasonal = 1.0 + 0.035 * np.sin(2 * np.pi * (day_index + 30) / 365)
        if market_type in {"Retail High Street", "Mixed Use"}:
            seasonal += np.where(np.isin(months, [10, 11]), 0.11, 0.0)
        if lot["parking_type"] == "Surface Lot":
            seasonal -= np.where(np.isin(months, [7, 8, 9]), 0.045, 0.0)
        weekly_noise = rng.normal(0, 0.035, math.ceil(len(dates) / 7)).repeat(7)[: len(dates)]
        daily_noise = rng.normal(0, 0.055, len(dates))
        avg_occupancy = np.clip(
            base_occupancy * day_factor * seasonal + weekly_noise + daily_noise, 0.035, 0.93
        )
        peak_occupancy = np.clip(
            avg_occupancy + 0.13 + rng.normal(0.025, 0.035, len(dates)),
            avg_occupancy,
            0.995,
        )
        duration_base = {
            "CBD": 2.6,
            "Commercial": 2.8,
            "Retail High Street": 2.0,
            "IT/Office Park": 5.7,
            "Residential": 5.0,
            "Transit Hub": 5.9,
            "Hospital/Institutional": 3.2,
            "Mixed Use": 2.8,
        }[market_type]
        durations = np.clip(
            duration_base * np.where(is_weekend, 0.92 if market_type == "IT/Office Park" else 1.05, 1.0)
            + rng.normal(0, 0.32, len(dates)),
            0.65,
            10.5,
        )
        hours = _operating_hours(lot)
        entries_expected = (
            lot["capacity_cars"] * avg_occupancy * hours / durations * rng.uniform(0.86, 1.08)
        )
        entries = np.maximum(0, rng.poisson(np.clip(entries_expected, 0, 10_000))).astype(int)
        owner = owner_index.loc[int(lot["owner_id"])]
        digital_factor = 0.04 * int(owner["digital_payment_enabled"]) + 0.012 * int(
            owner["willingness_to_digitize"]
        )
        trend = np.linspace(0, 0.055, len(dates))
        booking_share = np.clip(0.035 + digital_factor + 0.10 * signal + trend, 0.04, 0.34)
        bookings = np.array(
            [rng.binomial(int(entry), float(share)) for entry, share in zip(entries, booking_share)]
        )
        cancel_rate = np.clip(
            0.035 + 0.035 * is_weekend + 0.025 * (1 - signal) + rng.normal(0, 0.006, len(dates)),
            0.015,
            0.14,
        )
        cancellations = np.array(
            [rng.binomial(int(booked), float(rate)) for booked, rate in zip(bookings, cancel_rate)]
        )
        realisation = np.clip(rng.normal(0.76, 0.085, len(dates)), 0.46, 1.08)
        revenue = np.maximum(
            0,
            entries * durations * float(lot["hourly_rate_inr"]) * realisation,
        )
        for idx, activity_date in enumerate(dates):
            rows.append(
                {
                    "parking_id": int(lot["parking_id"]),
                    "activity_date": activity_date.date().isoformat(),
                    "peak_occupancy_rate": round(float(peak_occupancy[idx]), 4),
                    "avg_occupancy_rate": round(float(avg_occupancy[idx]), 4),
                    "vehicle_entries": int(entries[idx]),
                    "platform_bookings": int(bookings[idx]),
                    "booking_cancellations": int(cancellations[idx]),
                    "gross_parking_revenue_inr": round(float(revenue[idx]), 2),
                    "avg_park_duration_hours": round(float(durations[idx]), 2),
                }
            )
    return pd.DataFrame(rows)


def _hour_curve(market_type: str, day_type: str) -> np.ndarray:
    hours = np.arange(24)
    gaussian = lambda centre, width: np.exp(-0.5 * ((hours - centre) / width) ** 2)
    if market_type in {"CBD", "Commercial", "IT/Office Park"}:
        curve = 0.10 + 0.80 * gaussian(13, 4.0) + 0.24 * gaussian(18, 2.2)
        if day_type == "Weekend":
            curve *= 0.56 if market_type == "IT/Office Park" else 0.72
    elif market_type == "Retail High Street":
        curve = 0.09 + 0.58 * gaussian(14, 3.5) + 0.72 * gaussian(19, 2.6)
        if day_type == "Weekend":
            curve *= 1.14
    elif market_type == "Residential":
        curve = 0.23 + 0.40 * gaussian(8, 2.0) + 0.72 * gaussian(20, 3.0)
        if day_type == "Weekend":
            curve += 0.17 * gaussian(14, 4.5)
    elif market_type == "Transit Hub":
        curve = 0.10 + 0.82 * gaussian(9, 2.3) + 0.86 * gaussian(18, 2.5)
        if day_type == "Weekend":
            curve *= 0.84
    elif market_type == "Hospital/Institutional":
        curve = 0.27 + 0.47 * gaussian(12, 5.5) + 0.22 * gaussian(19, 3.0)
    else:
        curve = 0.13 + 0.56 * gaussian(12, 4.0) + 0.62 * gaussian(19, 3.0)
        if day_type == "Weekend":
            curve *= 1.02
    return curve / max(float(np.max(curve)), 1e-9)


def generate_hourly_profile(
    lots: pd.DataFrame,
    localities: pd.DataFrame,
    daily: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    locality_type = localities.set_index("locality_id")["micro_market_type"].to_dict()
    daily_means = daily.groupby("parking_id")["avg_occupancy_rate"].mean().to_dict()
    rows: list[dict[str, Any]] = []
    for lot in lots.itertuples(index=False):
        market_type = locality_type[int(lot.locality_id)]
        hours_open = _operating_hours(pd.Series(lot._asdict()))
        if lot.is_24x7:
            open_mask = np.ones(24, dtype=bool)
        else:
            start = int(str(lot.opens_at).split(":")[0])
            end = int(str(lot.closes_at).split(":")[0])
            open_mask = np.array([((hour - start) % 24) < ((end - start) % 24) for hour in range(24)])
        for day_type in ("Weekday", "Weekend"):
            curve = _hour_curve(market_type, day_type)
            scale = min(0.98, daily_means[int(lot.parking_id)] * (1.48 if day_type == "Weekday" else 1.38))
            occupancy = np.clip(curve * scale + rng.normal(0, 0.018, 24), 0, 0.995)
            occupancy = np.where(open_mask, occupancy, 0)
            arrivals_shape = np.maximum(0.08, np.roll(curve, -1) - 0.35 * curve + 0.22)
            entries = (
                lot.capacity_cars
                * arrivals_shape
                * max(daily_means[int(lot.parking_id)], 0.05)
                / max(hours_open / 10, 0.5)
            )
            entries = np.where(open_mask, entries, 0)
            for hour in range(24):
                rows.append(
                    {
                        "parking_id": int(lot.parking_id),
                        "day_type": day_type,
                        "hour_of_day": hour,
                        "avg_occupancy_rate": round(float(occupancy[hour]), 4),
                        "avg_entries": round(float(entries[hour]), 2),
                    }
                )
    return pd.DataFrame(rows)


def generate_outreach(
    lots: pd.DataFrame,
    owners: pd.DataFrame,
    terms: pd.DataFrame,
    signals: np.ndarray,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = lots.merge(owners, on="owner_id", suffixes=("", "_owner")).merge(
        terms, on="parking_id"
    )
    sources = [
        "Field Survey", "Inbound Enquiry", "Referral", "Cold Call",
        "Desk Research", "Broker", "Partner Network",
    ]
    source_p = [0.17, 0.08, 0.16, 0.24, 0.18, 0.08, 0.09]
    source_quality = {
        "Inbound Enquiry": 0.14,
        "Referral": 0.11,
        "Partner Network": 0.09,
        "Broker": 0.04,
        "Field Survey": 0.02,
        "Desk Research": -0.01,
        "Cold Call": -0.06,
    }
    outreach_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    event_id = 1
    lead_window_days = (date(2026, 4, 30) - settings.obs_start_date).days

    for idx, row in frame.reset_index(drop=True).iterrows():
        lead_id = idx + 1
        source = str(rng.choice(sources, p=source_p))
        readiness = (
            0.22 * (row["willingness_to_digitize"] - 1) / 4
            + 0.18 * (row["contract_flexibility"] - 1) / 4
            + 0.14 * (row["documentation_readiness"] - 1) / 4
            + 0.10 * int(row["digital_payment_enabled"])
            + 0.10 * int(row["decision_maker_accessible"])
            + 0.13 * float(signals[idx])
            + 0.05 * min(row["capacity_cars"] / 500, 1)
            + source_quality[source]
            + rng.normal(0, 0.07)
        )
        transition_base = [0.69, 0.57, 0.67, 0.62, 0.57, 0.48]
        stage = 1
        for stage_number, base in enumerate(transition_base, start=2):
            stage_bias = (readiness - 0.38) * (0.42 if stage_number < 5 else 0.55)
            if rng.random() < np.clip(base + stage_bias, 0.20, 0.94):
                stage = stage_number
            else:
                break

        identified_date = settings.obs_start_date + timedelta(days=int(rng.integers(0, lead_window_days + 1)))
        event_dates = [identified_date]
        for stage_number in range(2, stage + 1):
            typical_gap = [0, 0, 4, 8, 7, 11, 13, 12][stage_number]
            gap = max(1, int(round(rng.gamma(2.0, typical_gap / 2))))
            event_dates.append(event_dates[-1] + timedelta(days=gap))
        if event_dates[-1] > settings.obs_end_date:
            valid_count = sum(event_date <= settings.obs_end_date for event_date in event_dates)
            stage = max(1, valid_count)
            event_dates = event_dates[:stage]

        if stage == 7:
            status = "Won"
        elif stage == 1:
            status = "Active"
        else:
            status = str(rng.choice(["Active", "Lost"], p=[0.24, 0.76]))

        if stage >= 2:
            first_contact = event_dates[1]
            contact_attempts = int(
                np.clip(1 + rng.poisson(1.4 + (0 if row["decision_maker_accessible"] else 1.2)), 1, 12)
            )
        else:
            first_contact = None
            contact_attempts = 0

        if status == "Lost":
            if not row["decision_maker_accessible"]:
                reason = "Owner Not Decision Maker"
            elif row["documentation_readiness"] <= 2 and stage >= 4:
                reason = "Documentation Unavailable"
            elif row["contract_flexibility"] <= 2:
                reason = str(rng.choice(["Wants Fixed Rent", "Commission Too Low"]))
            elif not row["exclusivity_possible"] and stage >= 4:
                reason = "Exclusivity Refused"
            else:
                reason = str(rng.choice(["No Response", "Commission Too Low", "Competitor Signed"]))
        else:
            reason = None

        interest = None if stage < 2 else int(
            np.clip(round(1.2 + 3.4 * readiness + rng.normal(0, 0.65)), 1, 5)
        )
        conversion_date = event_dates[-1] if status == "Won" else None
        outreach_rows.append(
            {
                "lead_id": lead_id,
                "parking_id": int(row["parking_id"]),
                "lead_source": source,
                "first_contact_date": first_contact.isoformat() if first_contact else None,
                "contact_attempts": contact_attempts,
                "furthest_stage_id": stage,
                "pipeline_status": status,
                "lost_reason": reason,
                "documents_available": bool(stage >= 6),
                "owner_interest_level": interest,
                "conversion_date": conversion_date.isoformat() if conversion_date else None,
                "assigned_bd_rep": f"BD-{1 + (idx % 6):02d}",
                "days_to_conversion": (
                    (conversion_date - first_contact).days
                    if conversion_date is not None and first_contact is not None
                    else None
                ),
            }
        )
        for stage_id, event_date in enumerate(event_dates, start=1):
            channel = (
                "Phone"
                if stage_id == 2
                else str(
                    rng.choice(
                        ["Phone", "In-Person", "Email", "WhatsApp", "Video Call"],
                        p=[0.18, 0.25, 0.18, 0.25, 0.14],
                    )
                )
            )
            event_rows.append(
                {
                    "event_id": event_id,
                    "lead_id": lead_id,
                    "stage_id": stage_id,
                    "event_date": event_date.isoformat(),
                    "channel": channel,
                }
            )
            event_id += 1
    return pd.DataFrame(outreach_rows), pd.DataFrame(event_rows)


def generate_synthetic_tables(public: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(settings.random_seed)
    owners, lots, owner_maturity = generate_owners_and_lots(
        public["candidate_parking"], public["dim_locality"], rng
    )
    signals = demand_signal(lots, public["location_demand"], public["dim_locality"], rng)
    competition = complete_competition(
        public["competition_public"], lots, public["dim_locality"], rng
    )
    terms = generate_acquisition_terms(lots, owners, owner_maturity, rng)
    daily = generate_daily_performance(
        lots, owners, public["dim_locality"], signals, competition, rng
    )
    hourly = generate_hourly_profile(lots, public["dim_locality"], daily, rng)
    outreach, events = generate_outreach(lots, owners, terms, signals, rng)
    return {
        "owners": owners,
        "parking_lots": lots,
        "competition": competition,
        "lot_acquisition_terms": terms,
        "existing_network_sites": generate_network_sites(public["markets"], lots, rng),
        "fact_lot_daily": daily,
        "fact_lot_hourly_profile": hourly,
        "outreach": outreach,
        "outreach_events": events,
    }
