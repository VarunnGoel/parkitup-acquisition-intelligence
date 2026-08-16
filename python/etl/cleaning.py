"""Clean cached OSM features and derive the public geographic inputs."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402

MARKETS_PATH = PATHS["data_external"] / "micro_markets.csv"
GEOCODE_PATH = PATHS["data_external"] / "osm_geocoding_snapshot.json"
OVERPASS_PATH = PATHS["data_external"] / "osm_features_snapshot.json"

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> np.ndarray:
    """Vectorised great-circle distance in metres."""
    lat1_r = np.radians(lat1)
    lon1_r = np.radians(lon1)
    lat2_r = np.radians(lat2)
    lon2_r = np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def _coordinate(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if element.get("type") == "node":
        return element.get("lat"), element.get("lon")
    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def _parse_capacity(tags: dict[str, Any]) -> int | None:
    for key in ("capacity:car", "capacity"):
        raw = tags.get(key)
        if raw is None:
            continue
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if digits:
            value = int(digits)
            if 10 <= value <= 2000:
                return value
    return None


def _categories(tags: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    amenity = tags.get("amenity")
    if amenity == "parking":
        categories.append("parking")
    if tags.get("railway") == "station" and tags.get("station") in {"subway", "light_rail"}:
        categories.append("metro_station")
    if tags.get("railway") == "subway_entrance":
        categories.append("metro_entrance")
    if "office" in tags:
        categories.append("office")
    if "shop" in tags:
        categories.append("retail")
    if tags.get("shop") == "mall" or tags.get("building") == "retail":
        categories.append("mall")
    if amenity in {"restaurant", "cafe", "fast_food", "food_court"}:
        categories.append("restaurant")
    if amenity in {"hospital", "clinic"} or tags.get("healthcare") in {"hospital", "clinic"}:
        categories.append("hospital")
    if amenity in {"school", "college", "university"}:
        categories.append("education")
    if tags.get("public_transport") in {"platform", "station"} or tags.get("highway") == "bus_stop":
        categories.append("transit_stop")
    return categories


def load_public_features() -> tuple[pd.DataFrame, pd.DataFrame]:
    markets = pd.read_csv(MARKETS_PATH)
    geocoded = json.loads(GEOCODE_PATH.read_text(encoding="utf-8"))["results"]
    geo = pd.DataFrame(geocoded)[["locality_id", "latitude", "longitude", "display_name"]]
    markets = markets.merge(geo, on="locality_id", validate="one_to_one")

    raw = json.loads(OVERPASS_PATH.read_text(encoding="utf-8"))["elements"]
    records: list[dict[str, Any]] = []
    for element in raw:
        latitude, longitude = _coordinate(element)
        if latitude is None or longitude is None:
            continue
        tags = element.get("tags") or {}
        cats = _categories(tags)
        if not cats:
            continue
        records.append(
            {
                "osm_type": str(element["type"]),
                "osm_id": int(element["id"]),
                "feature_key": f'{element["type"]}/{element["id"]}',
                "latitude": float(latitude),
                "longitude": float(longitude),
                "name": tags.get("name") or tags.get("name:en"),
                "categories": ";".join(sorted(set(cats))),
                "access": str(tags.get("access", "unspecified")).lower(),
                "parking_tag": tags.get("parking"),
                "capacity_public": _parse_capacity(tags),
                "opening_hours": tags.get("opening_hours"),
                "tags_json": json.dumps(tags, sort_keys=True, ensure_ascii=True),
                "source_reference": (
                    f'https://www.openstreetmap.org/{element["type"]}/{element["id"]}'
                ),
            }
        )
    features = pd.DataFrame(records).drop_duplicates("feature_key").reset_index(drop=True)
    return markets, features


def _has_category(series: pd.Series, category: str) -> pd.Series:
    return series.fillna("").str.split(";").apply(lambda values: category in values)


def _parking_type(row: pd.Series) -> str:
    tags = json.loads(row["tags_json"])
    parking = str(tags.get("parking", "")).lower()
    name = str(row.get("name") or "").lower()
    if parking in {"multi-storey", "multistorey"}:
        return "Multi-Level (MLCP)"
    if parking == "underground":
        return "Basement"
    if parking in {"street_side", "lane", "on_street"}:
        return "On-Street Authorised"
    if "metro" in name or "station" in name:
        return "Metro Station Parking"
    if "hospital" in name or "medical" in name:
        return "Hospital Parking"
    if "mall" in name or "plaza" in name:
        return "Mall Parking"
    return "Surface Lot"


def _access_class(access: str) -> str:
    if access in {"private", "no", "members"}:
        return "private"
    if access in {"customers", "customer"}:
        return "destination"
    if access in {"permit", "residents"}:
        return "controlled"
    return "public"


def select_candidate_lots(
    markets: pd.DataFrame, features: pd.DataFrame, target_count: int
) -> pd.DataFrame:
    parking = features[_has_category(features["categories"], "parking")].copy()
    parking["access_class"] = parking["access"].map(_access_class)
    parking = parking[parking["access_class"] != "private"].copy()
    if parking.empty:
        raise RuntimeError("The OSM snapshot contains no usable parking features")

    market_lat = markets["latitude"].to_numpy()
    market_lon = markets["longitude"].to_numpy()
    assigned_ids: list[int] = []
    assigned_distances: list[float] = []
    for row in parking.itertuples(index=False):
        distances = haversine_m(row.latitude, row.longitude, market_lat, market_lon)
        nearest = int(np.argmin(distances))
        assigned_ids.append(int(markets.iloc[nearest]["locality_id"]))
        assigned_distances.append(float(distances[nearest]))
    parking["locality_id"] = assigned_ids
    parking["market_center_distance_m"] = assigned_distances
    # Keep candidates inside the extract by one kilometre so every 1km demand
    # and competition radius is fully covered by the cached market snapshot.
    candidate_radius = max(settings.market_radius_m - 1000, 1200)
    parking = parking[parking["market_center_distance_m"] <= candidate_radius]
    parking["is_named"] = parking["name"].notna()
    parking["parking_type"] = parking.apply(_parking_type, axis=1)
    parking = parking.sort_values(
        ["locality_id", "is_named", "market_center_distance_m", "feature_key"],
        ascending=[True, False, True, True],
    )

    groups = {
        int(locality_id): group.reset_index(drop=True)
        for locality_id, group in parking.groupby("locality_id")
        if len(group) >= 3
    }
    eligible_locality_ids = set(groups)
    parking = parking[parking["locality_id"].isin(eligible_locality_ids)].copy()
    selected_keys: list[str] = []
    # Round-robin selection keeps the universe geographically balanced.
    rank = 0
    while len(selected_keys) < target_count and rank < 12:
        added = False
        for locality_id in markets.loc[
            markets["locality_id"].isin(eligible_locality_ids), "locality_id"
        ].astype(int):
            group = groups.get(locality_id)
            if group is not None and rank < len(group):
                selected_keys.append(str(group.iloc[rank]["feature_key"]))
                added = True
                if len(selected_keys) == target_count:
                    break
        if not added:
            break
        rank += 1

    if len(selected_keys) < target_count:
        remaining = parking[~parking["feature_key"].isin(selected_keys)].sort_values(
            ["market_center_distance_m", "feature_key"]
        )
        selected_keys.extend(
            remaining.head(target_count - len(selected_keys))["feature_key"].tolist()
        )

    selected = parking[parking["feature_key"].isin(selected_keys)].copy()
    selected = selected.sort_values(["locality_id", "market_center_distance_m", "feature_key"])
    if len(selected) < 100:
        raise RuntimeError(
            f"Only {len(selected)} public candidate lots were available. "
            "The source minimum is 100; refresh or add an explicitly sourced curated fallback."
        )
    # The brief allows adjusting the exact row count when source coverage is uneven.
    selected = selected.head(min(target_count, len(selected))).reset_index(drop=True)
    selected["parking_id"] = np.arange(1, len(selected) + 1)
    selected["lot_code"] = selected["parking_id"].map(lambda value: f"LOT-{value:04d}")
    selected["lot_name"] = selected.apply(
        lambda row: str(row["name"]).strip()
        if pd.notna(row["name"]) and str(row["name"]).strip()
        else f'OSM Parking {row["osm_type"]}-{int(row["osm_id"])}',
        axis=1,
    )
    return selected


def build_localities(markets: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    metro = features[_has_category(features["categories"], "metro_station")]
    rows: list[dict[str, Any]] = []
    for market in markets.itertuples(index=False):
        if metro.empty:
            nearby_count = 0
        else:
            distances = haversine_m(
                market.latitude,
                market.longitude,
                metro["latitude"].to_numpy(),
                metro["longitude"].to_numpy(),
            )
            nearby_count = int(np.sum(distances <= 1800))
        rows.append(
            {
                "locality_id": int(market.locality_id),
                "city_id": int(market.city_id),
                "locality_name": market.locality_name,
                "micro_market_type": market.micro_market_type,
                "has_metro_station": nearby_count > 0,
                # Route relations are not part of the bounded POI extract. One
                # line is conservatively assumed where a station is observed.
                "metro_line_count": 1 if nearby_count > 0 else 0,
                "population_density_band": market.population_density_band,
                "record_source": "public_osm",
            }
        )
    return pd.DataFrame(rows)


def _subset(features: pd.DataFrame, category: str) -> pd.DataFrame:
    return features[_has_category(features["categories"], category)].copy()


def _count_within(latitude: float, longitude: float, frame: pd.DataFrame, radius: int) -> int:
    if frame.empty:
        return 0
    distances = haversine_m(
        latitude, longitude, frame["latitude"].to_numpy(), frame["longitude"].to_numpy()
    )
    return int(np.sum(distances <= radius))


def derive_location_demand(candidates: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    category_frames = {
        category: _subset(features, category)
        for category in (
            "metro_station",
            "mall",
            "office",
            "retail",
            "restaurant",
            "hospital",
            "education",
            "transit_stop",
        )
    }
    rows: list[dict[str, Any]] = []
    for lot in candidates.itertuples(index=False):
        metro = category_frames["metro_station"]
        if metro.empty:
            metro_distance = 20_000
            metro_name = None
        else:
            distances = haversine_m(
                lot.latitude,
                lot.longitude,
                metro["latitude"].to_numpy(),
                metro["longitude"].to_numpy(),
            )
            nearest_idx = int(np.argmin(distances))
            metro_distance = int(min(round(float(distances[nearest_idx])), 20_000))
            nearest = metro.iloc[nearest_idx]
            metro_name = nearest["name"] or f'OSM Metro {nearest["feature_key"]}'

        malls = category_frames["mall"]
        if malls.empty:
            mall_distance: int | None = None
        else:
            distances = haversine_m(
                lot.latitude,
                lot.longitude,
                malls["latitude"].to_numpy(),
                malls["longitude"].to_numpy(),
            )
            mall_distance = int(min(round(float(np.min(distances))), 20_000))

        rows.append(
            {
                "parking_id": int(lot.parking_id),
                "metro_distance_m": metro_distance,
                "nearest_metro_station": metro_name,
                "mall_distance_m": mall_distance,
                "office_count_500m": _count_within(
                    lot.latitude, lot.longitude, category_frames["office"], 500
                ),
                "retail_count_500m": _count_within(
                    lot.latitude, lot.longitude, category_frames["retail"], 500
                ),
                "restaurant_count_500m": _count_within(
                    lot.latitude, lot.longitude, category_frames["restaurant"], 500
                ),
                "hospital_count_1km": _count_within(
                    lot.latitude, lot.longitude, category_frames["hospital"], 1000
                ),
                "education_count_1km": _count_within(
                    lot.latitude, lot.longitude, category_frames["education"], 1000
                ),
                "transit_stop_count_500m": _count_within(
                    lot.latitude, lot.longitude, category_frames["transit_stop"], 500
                ),
                "measured_on": settings.source_observed_on.isoformat(),
                "record_source": "public_osm",
            }
        )
    return pd.DataFrame(rows)


def derive_competition(candidates: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    parking = _subset(features, "parking")
    parking["access_class"] = parking["access"].map(_access_class)
    comparable = parking[parking["access_class"].isin({"public", "destination"})].copy()
    rows: list[dict[str, Any]] = []
    for lot in candidates.itertuples(index=False):
        pool = comparable[comparable["feature_key"] != lot.feature_key]
        if pool.empty:
            distances = np.array([], dtype=float)
        else:
            distances = haversine_m(
                lot.latitude,
                lot.longitude,
                pool["latitude"].to_numpy(),
                pool["longitude"].to_numpy(),
            )
        within_500 = distances <= 500
        within_1km = distances <= 1000
        count_500 = int(np.sum(within_500))
        count_1km = int(np.sum(within_1km))
        nearest = int(round(float(np.min(distances)))) if count_1km > 0 else None
        capacities = pool.loc[within_1km, "capacity_public"].dropna()
        total_capacity = int(capacities.sum()) if not capacities.empty else None
        rows.append(
            {
                "parking_id": int(lot.parking_id),
                "competitor_count_500m": count_500,
                "competitor_count_1km": count_1km,
                "nearest_competitor_distance_m": nearest,
                "competitor_total_capacity_1km": total_capacity,
                "measured_on": settings.source_observed_on.isoformat(),
                "record_source": "public_osm",
            }
        )
    return pd.DataFrame(rows)


def public_pipeline(target_count: int | None = None) -> dict[str, pd.DataFrame]:
    markets, features = load_public_features()
    candidates = select_candidate_lots(markets, features, target_count or settings.target_lot_count)
    selected_localities = set(candidates["locality_id"].astype(int))
    markets = markets[markets["locality_id"].isin(selected_localities)].copy()
    return {
        "markets": markets,
        "osm_features": features,
        "candidate_parking": candidates,
        "dim_locality": build_localities(markets, features),
        "location_demand": derive_location_demand(candidates, features),
        "competition_public": derive_competition(candidates, features),
    }
