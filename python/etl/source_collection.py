"""Collect and cache the public OpenStreetMap inputs used by the data pipeline.

The normal pipeline never calls a live API. ``--refresh`` performs one bounded
collection for the selected micro-markets and writes a local snapshot under
``data/external``. Subsequent builds use that snapshot offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from python.config import PATHS, settings  # noqa: E402

MARKETS_PATH = PATHS["data_external"] / "micro_markets.csv"
GEOCODE_PATH = PATHS["data_external"] / "osm_geocoding_snapshot.json"
OVERPASS_PATH = PATHS["data_external"] / "osm_features_snapshot.json"
MANIFEST_PATH = PATHS["data_external"] / "source_manifest.json"
BATCH_DIR = PATHS["data_external"] / "osm_batches"
NOMINATIM_BATCH_DIR = PATHS["data_external"] / "nominatim_fallback_batches"

USER_AGENT = (
    "PARK-It-Up-Acquisition-Intelligence/2.0 "
    "(portfolio research; cached offline after collection)"
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# --------------------------------------------------------------------------
# Personal-contact tag removal.
#
# OpenStreetMap is open data, but individual mappers add real phone numbers and
# personal email addresses to small-business and residential objects. Those tags
# are personal data about identifiable third parties who never agreed to appear
# in a portfolio repository, and this project has no analytical use for them:
# cleaning.py reads only amenity/shop/office/railway/capacity/name/access/
# parking/opening_hours. They are therefore stripped at write time so they never
# enter the committed snapshot.
#
# `operator` and `website` are deliberately KEPT. `operator` is an organisation
# name that ODbL attribution benefits from, and `website` is a business URL, not
# a personal contact channel.
# --------------------------------------------------------------------------
PII_TAG_KEYS = frozenset(
    {
        "phone", "mobile", "fax",
        "contact:phone", "contact:mobile", "contact:fax",
        "contact:email", "email",
        "contact:whatsapp", "whatsapp",
        "operator:phone", "operator:email",
        "addr:email", "addr:phone",
    }
)

# A fixed key list is not enough. Real OSM data contains ad-hoc keys such as
# `contact:nodal_officer_email`, which an exact-match list silently misses. Any
# key containing one of these tokens is treated as a personal contact channel.
PII_TAG_TOKENS = ("email", "phone", "mobile", "fax", "whatsapp")


def _is_pii_tag(key: str) -> bool:
    lowered = key.lower()
    if lowered in PII_TAG_KEYS:
        return True
    return any(token in lowered for token in PII_TAG_TOKENS)


def strip_personal_tags(element: dict[str, Any]) -> dict[str, Any]:
    """Return the element with personal-contact tags removed.

    Applied to every element before it is written to the local cache, so the
    committed snapshot contains no third-party phone numbers or email
    addresses. Idempotent: safe to run over an already-clean element.
    """
    tags = element.get("tags")
    if not isinstance(tags, dict):
        return element
    kept = {key: value for key, value in tags.items() if not _is_pii_tag(key)}
    if len(kept) == len(tags):
        return element
    cleaned = dict(element)
    cleaned["tags"] = kept
    return cleaned


def strip_personal_tags_all(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [strip_personal_tags(element) for element in elements]


def _stable_write_json(path: Path, payload: Any) -> None:
    # Every cache file that carries OSM elements is scrubbed here rather than at
    # each call site, so a future collection path cannot bypass the policy.
    if isinstance(payload, dict) and isinstance(payload.get("elements"), list):
        payload = dict(payload)
        payload["elements"] = strip_personal_tags_all(payload["elements"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int,
    **kwargs: Any,
) -> dict[str, Any] | list[dict[str, Any]]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.json()


def geocode_markets(session: requests.Session, markets: pd.DataFrame) -> list[dict[str, Any]]:
    """Resolve the deliberately small market list through Nominatim once."""
    results: list[dict[str, Any]] = []
    for row in markets.itertuples(index=False):
        payload = _request_json(
            session,
            "GET",
            NOMINATIM_URL,
            timeout=45,
            params={
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "in",
                "q": row.geocode_query,
            },
        )
        if not payload:
            raise RuntimeError(f"Nominatim returned no result for {row.geocode_query!r}")
        match = payload[0]
        results.append(
            {
                "locality_id": int(row.locality_id),
                "locality_name": row.locality_name,
                "query": row.geocode_query,
                "latitude": float(match["lat"]),
                "longitude": float(match["lon"]),
                "osm_type": match.get("osm_type"),
                "osm_id": match.get("osm_id"),
                "display_name": match.get("display_name"),
                "licence": match.get("licence"),
            }
        )
        # Nominatim's public-use policy requests a maximum of one request/sec.
        time.sleep(1.05)
    return results


def _overpass_query(markets: list[dict[str, Any]]) -> str:
    clauses: list[str] = []
    selectors = [
        '["amenity"="parking"]',
        '["railway"="station"]["station"~"subway|light_rail"]',
        '["railway"="subway_entrance"]',
        '["office"]',
        '["shop"~"mall|supermarket|department_store|electronics"]',
        '["building"="retail"]',
        '["amenity"="marketplace"]',
        '["amenity"~"restaurant|cafe|fast_food|food_court"]',
        '["amenity"~"hospital|clinic"]',
        '["healthcare"~"hospital|clinic"]',
        '["amenity"~"school|college|university"]',
        '["highway"="bus_stop"]',
    ]
    for market in markets:
        lat = market["latitude"]
        lon = market["longitude"]
        lat_delta = settings.market_radius_m / 111_320
        lon_delta = settings.market_radius_m / (111_320 * math.cos(math.radians(lat)))
        bbox = (
            f"{lat - lat_delta:.7f},{lon - lon_delta:.7f},"
            f"{lat + lat_delta:.7f},{lon + lon_delta:.7f}"
        )
        for selector in selectors:
            clauses.append(f"nwr{selector}({bbox});")
    return "\n".join(
        [
            f"[out:json][timeout:{settings.overpass_timeout_seconds}];",
            "(",
            *clauses,
            ");",
            "out center tags qt;",
        ]
    )


def collect_overpass(
    session: requests.Session, geocoded: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect one bounded market at a time; de-duplicate overlapping features."""
    alternate = "https://overpass.kumi.systems/api/interpreter"
    endpoints = [alternate, settings.overpass_api_url]

    features: dict[tuple[str, int], dict[str, Any]] = {}
    used_endpoints: list[str] = []
    # Dense Delhi shop data made four-market payloads exceed public endpoint
    # gateway limits. One request per selected market stays bounded and makes
    # failures attributable without broad re-queries.
    batch_size = 1
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(geocoded), batch_size):
        batch = geocoded[start : start + batch_size]
        market = batch[0]
        batch_path = BATCH_DIR / f'{int(market["locality_id"]):02d}.json'
        if batch_path.exists():
            cached = json.loads(batch_path.read_text(encoding="utf-8"))
            for element in cached["elements"]:
                key = (str(element["type"]), int(element["id"]))
                features[key] = element
            used_endpoints.append(cached["source_url"])
            print(f'cached {market["locality_name"]}: {len(cached["elements"])} elements', flush=True)
            continue
        query = _overpass_query(batch)
        last_error: Exception | None = None
        for endpoint in endpoints:
            try:
                payload = _request_json(
                    session,
                    "POST",
                    endpoint,
                    timeout=settings.overpass_timeout_seconds + 30,
                    data={"data": query},
                )
                used_endpoints.append(endpoint)
                batch_elements = payload.get("elements", [])
                _stable_write_json(
                    batch_path,
                    {
                        "locality_id": int(market["locality_id"]),
                        "locality_name": market["locality_name"],
                        "observed_on": settings.source_observed_on.isoformat(),
                        "source_url": endpoint,
                        "elements": batch_elements,
                    },
                )
                print(f'collected {market["locality_name"]}: {len(batch_elements)} elements', flush=True)
                for element in batch_elements:
                    key = (str(element["type"]), int(element["id"]))
                    features[key] = element
                last_error = None
                break
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
        if last_error is not None:
            names = ", ".join(item["locality_name"] for item in batch)
            raise RuntimeError(
                f"Overpass failed for bounded batch [{names}]. "
                "No further live retries were attempted; use the cached snapshot or "
                "the curated fallback."
            ) from last_error
    return list(features.values()), sorted(set(used_endpoints))


FALLBACK_QUERIES = {
    "parking": ("parking", 30),
    "metro": ("metro station", 15),
    "mall": ("shopping mall", 15),
    "office": ("office", 25),
    "restaurant": ("restaurant", 30),
    "hospital": ("hospital", 20),
    "education": ("school", 25),
    "transit": ("bus stop", 30),
}


def _fallback_tags(kind: str, result: dict[str, Any]) -> dict[str, Any] | None:
    category = str(result.get("category", ""))
    feature_type = str(result.get("type", ""))
    allowed = {
        "parking": category == "amenity" and feature_type == "parking",
        "metro": (
            (category == "railway" and feature_type in {"station", "halt", "subway_entrance"})
            or (category == "public_transport" and feature_type == "station")
        ),
        "mall": category == "shop" and feature_type in {"mall", "department_store"},
        "office": category in {"office", "building"} and feature_type not in {"house", "residential"},
        "restaurant": category == "amenity" and feature_type in {"restaurant", "cafe", "fast_food", "food_court"},
        "hospital": category in {"amenity", "healthcare"} and feature_type in {"hospital", "clinic"},
        "education": category == "amenity" and feature_type in {"school", "college", "university"},
        "transit": (
            (category == "highway" and feature_type == "bus_stop")
            or (category == "public_transport" and feature_type in {"platform", "station"})
        ),
    }[kind]
    if not allowed:
        return None
    tags: dict[str, Any]
    if kind == "parking":
        tags = {"amenity": "parking"}
    elif kind == "metro":
        tags = {"railway": "subway_entrance"} if feature_type == "subway_entrance" else {"railway": "station", "station": "subway"}
    elif kind == "mall":
        tags = {"shop": "mall" if feature_type == "mall" else "department_store"}
    elif kind == "office":
        tags = {"office": feature_type or "yes"}
    elif kind == "restaurant":
        tags = {"amenity": feature_type}
    elif kind == "hospital":
        tags = {"amenity": feature_type}
    elif kind == "education":
        tags = {"amenity": feature_type}
    else:
        tags = {"highway": "bus_stop"} if category == "highway" else {"public_transport": feature_type}
    if result.get("name"):
        tags["name"] = result["name"]
    return tags


def collect_nominatim_fallback(
    session: requests.Session, geocoded: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Curated public fallback when Overpass cannot serve bounded extracts.

    Nominatim is not treated as an exhaustive census. Only matching OSM
    category/type results inside the market viewbox are retained, and every raw
    response is cached so the normal pipeline remains offline.
    """
    NOMINATIM_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    elements: dict[tuple[str, int], dict[str, Any]] = {}
    for market in geocoded:
        lat = float(market["latitude"])
        lon = float(market["longitude"])
        lat_delta = settings.market_radius_m / 111_320
        lon_delta = settings.market_radius_m / (111_320 * math.cos(math.radians(lat)))
        viewbox = f"{lon - lon_delta:.7f},{lat + lat_delta:.7f},{lon + lon_delta:.7f},{lat - lat_delta:.7f}"
        for kind, (query, limit) in FALLBACK_QUERIES.items():
            path = NOMINATIM_BATCH_DIR / f'{int(market["locality_id"]):02d}_{kind}.json'
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))["results"]
            else:
                payload = _request_json(
                    session,
                    "GET",
                    NOMINATIM_URL,
                    timeout=45,
                    params={
                        "format": "jsonv2",
                        "limit": limit,
                        "countrycodes": "in",
                        "bounded": 1,
                        "viewbox": viewbox,
                        "q": query,
                    },
                )
                _stable_write_json(
                    path,
                    {
                        "locality_id": int(market["locality_id"]),
                        "locality_name": market["locality_name"],
                        "kind": kind,
                        "query": query,
                        "observed_on": settings.source_observed_on.isoformat(),
                        "results": payload,
                    },
                )
                time.sleep(1.05)
            retained = 0
            for result in payload:
                tags = _fallback_tags(kind, result)
                if tags is None or not result.get("osm_type") or not result.get("osm_id"):
                    continue
                osm_type = str(result["osm_type"])
                osm_id = int(result["osm_id"])
                element: dict[str, Any] = {
                    "type": osm_type,
                    "id": osm_id,
                    "tags": tags,
                }
                if osm_type == "node":
                    element["lat"] = float(result["lat"])
                    element["lon"] = float(result["lon"])
                else:
                    element["center"] = {
                        "lat": float(result["lat"]),
                        "lon": float(result["lon"]),
                    }
                elements[(osm_type, osm_id)] = element
                retained += 1
            print(f'fallback {market["locality_name"]} {kind}: {retained} retained', flush=True)
    # Preserve richer successful Overpass batches without querying them again.
    for path in sorted(BATCH_DIR.glob("*.json")):
        cached = json.loads(path.read_text(encoding="utf-8"))
        for element in cached["elements"]:
            elements[(str(element["type"]), int(element["id"]))] = element
    return list(elements.values()), [NOMINATIM_URL, *sorted({
        json.loads(path.read_text(encoding="utf-8"))["source_url"]
        for path in BATCH_DIR.glob("*.json")
    })]


def refresh_sources(*, curated_fallback: bool = False) -> dict[str, Any]:
    markets = pd.read_csv(MARKETS_PATH)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    if GEOCODE_PATH.exists():
        geocoded = json.loads(GEOCODE_PATH.read_text(encoding="utf-8"))["results"]
    else:
        geocoded = geocode_markets(session, markets)
        _stable_write_json(
            GEOCODE_PATH,
            {
                "observed_on": settings.source_observed_on.isoformat(),
                "source": "OpenStreetMap Nominatim",
                "source_url": NOMINATIM_URL,
                "results": geocoded,
            },
        )

    if curated_fallback:
        elements, endpoints = collect_nominatim_fallback(session, geocoded)
        source_name = "OpenStreetMap via Nominatim curated fallback and cached Overpass batches"
    else:
        elements, endpoints = collect_overpass(session, geocoded)
        source_name = "OpenStreetMap Overpass"
    _stable_write_json(
        OVERPASS_PATH,
        {
            "observed_on": settings.source_observed_on.isoformat(),
            "source": source_name,
            "source_urls": endpoints,
            "licence": "OpenStreetMap data, ODbL 1.0, https://www.openstreetmap.org/copyright",
            "market_radius_m": settings.market_radius_m,
            "elements": elements,
        },
    )

    manifest = {
        "observed_on": settings.source_observed_on.isoformat(),
        "runtime_dependency": False,
        "collection_policy": (
            "One bounded refresh for 20 selected micro-markets. Successful Overpass "
            "batches were retained and unavailable markets used cached, category-filtered "
            "Nominatim fallback searches. Normal builds make no API calls."
        ),
        "files": {
            GEOCODE_PATH.name: {"sha256": _sha256(GEOCODE_PATH), "rows": len(geocoded)},
            OVERPASS_PATH.name: {"sha256": _sha256(OVERPASS_PATH), "rows": len(elements)},
            MARKETS_PATH.name: {"sha256": _sha256(MARKETS_PATH), "rows": len(markets)},
        },
    }
    _stable_write_json(MANIFEST_PATH, manifest)
    return manifest


def ensure_cached_sources() -> dict[str, Any]:
    missing = [path for path in (GEOCODE_PATH, OVERPASS_PATH, MANIFEST_PATH) if not path.exists()]
    if missing:
        paths = ", ".join(str(path.relative_to(REPO_ROOT)) for path in missing)
        raise FileNotFoundError(
            f"Public source cache is incomplete ({paths}). Run source_collection.py --refresh once."
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def scrub_cached_sources() -> dict[str, Any]:
    """Remove personal-contact tags from an existing local cache, in place.

    ``strip_personal_tags`` runs on every write, so a cache collected after that
    policy existed is already clean. This exists for a cache collected before
    it, and as an auditable command that can be re-run to prove the committed
    snapshot carries no third-party phone numbers or email addresses.

    Element identity, coordinates and every analytical tag are untouched, so the
    downstream build is bit-for-bit unaffected. Manifest hashes are refreshed
    because the snapshot bytes change.
    """
    report: dict[str, Any] = {"files": {}, "tags_removed": 0, "elements_touched": 0}
    targets = [GEOCODE_PATH, OVERPASS_PATH]
    targets.extend(sorted(BATCH_DIR.glob("*.json")))
    targets.extend(sorted(NOMINATIM_BATCH_DIR.glob("*.json")))
    for path in targets:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        elements = payload.get("elements")
        if not isinstance(elements, list):
            continue
        removed = 0
        touched = 0
        for element in elements:
            tags = element.get("tags")
            if not isinstance(tags, dict):
                continue
            hits = [key for key in tags if _is_pii_tag(key)]
            if hits:
                touched += 1
                removed += len(hits)
        if removed:
            # _stable_write_json applies the strip, so this both cleans and rewrites.
            _stable_write_json(path, payload)
        report["files"][str(path.relative_to(REPO_ROOT))] = {
            "elements": len(elements),
            "elements_touched": touched,
            "tags_removed": removed,
        }
        report["tags_removed"] += removed
        report["elements_touched"] += touched

    if MANIFEST_PATH.exists() and report["tags_removed"]:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for path in (GEOCODE_PATH, OVERPASS_PATH, MARKETS_PATH):
            entry = manifest.get("files", {}).get(path.name)
            if entry is not None and path.exists():
                entry["sha256"] = _sha256(path)
        manifest["personal_contact_tags_removed"] = True
        _stable_write_json(MANIFEST_PATH, manifest)
        report["manifest_hashes_refreshed"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Call Nominatim/Overpass once and replace the local public snapshot.",
    )
    parser.add_argument(
        "--curated-fallback",
        action="store_true",
        help="Use cached, bounded Nominatim category searches when Overpass is unavailable.",
    )
    parser.add_argument(
        "--scrub-cache",
        action="store_true",
        help="Strip personal-contact tags from the existing cache in place and refresh manifest hashes.",
    )
    args = parser.parse_args()
    if args.scrub_cache:
        print(json.dumps(scrub_cached_sources(), indent=2, sort_keys=True))
        return
    manifest = (
        refresh_sources(curated_fallback=args.curated_fallback)
        if args.refresh
        else ensure_cached_sources()
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
