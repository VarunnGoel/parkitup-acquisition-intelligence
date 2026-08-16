# source Data Generation Methodology

## Scope and provenance policy

The pipeline builds a controlled analytical universe of 120 parking opportunities across 17 Delhi NCR micro-markets. It does not claim to represent the complete parking market and contains no confidential PARK It Up data.

Every field is classified as `PUBLIC`, `DERIVED`, `SYNTHETIC`, `ASSUMED`, or `CONFIG` in `parkitup.data_lineage` and `data_dictionary_source.csv`. A public parking row does not make all of its attributes public: coordinates and OSM identity are public, while tariff, owner, operational performance, and most capacity values are explicitly synthetic.

## Public sources

The geographic source is OpenStreetMap, licensed under ODbL 1.0.

- `micro_markets.csv` defines the intentionally small study scope.
- `osm_geocoding_snapshot.json` stores the Nominatim-resolved market references.
- `osm_features_snapshot.json` stores 3,518 unique OSM features used by the build.
- `source_manifest.json` records source date, row counts, SHA-256 hashes, and the fact that runtime API access is not required.
- Per-market raw responses are retained under `data/external/osm_batches/` and `data/external/nominatim_fallback_batches/`.

The normal pipeline reads only local files. A source refresh is a separate, explicit operation.

## Curated fallback

The initial bounded Overpass extraction was attempted against `overpass-api.de` and `overpass.kumi.systems`. Both endpoints returned gateway timeouts, including for a minimal single-market parking request. Two successful market batches were retained.

For the remaining coverage, the collector used cached Nominatim searches bounded to each market box. Results were accepted only when the returned OSM `category` and `type` matched the requested feature class. This fallback is public and traceable, but it is not an exhaustive OSM census. Office and retail coverage is especially incomplete, so the corresponding counts should be treated as minimum observed counts. No invented value was labelled public to fill those gaps.

The initial 20-market reference list was reduced to 17 final markets because three markets returned fewer than three public parking candidates. This avoids weak one- or two-lot market aggregates while staying inside the requested 15-25 market range.

## Cleaning and geographic derivation

OSM nodes use their coordinates; ways and relations use returned centroids. Duplicate `(element_type, osm_id)` features are removed. Candidate lots must be motor-vehicle parking and cannot have `access=private`, `access=no`, or `access=members`.

Distances use the haversine formula. POI counts use unique cached features inside the stated radius. No walking-network claim is made.

A direct competitor is an OSM `amenity=parking` feature that:

1. is not the candidate itself;
2. is public or customer-accessible, excluding private/member/permit-only supply;
3. lies within the 500m or 1km radius; and
4. serves a comparable motor-vehicle parking use case.

Competitor capacity is summed only where OSM publishes a capacity tag and otherwise remains null. Competitor price and rival-platform listing counts are synthetic because reliable public coverage was unavailable.

## Assumed geographic attributes

`micro_market_type` and `population_density_band` are analyst classifications, not official statistics. `metro_line_count` is conservatively set to one when a station is observed because route-relation extraction was unavailable in the fallback. Generic OSM parking features receive an assumed, market-aware parking-type mix; the source coordinates remain public and the type is labelled `ASSUMED`.

## Synthetic generation

The fixed random seed is `20260815`. Generated data is deterministic for a fixed source snapshot and configuration.

### Owners and acquisition terms

Owner type is related to parking use. A latent digital-maturity tendency influences digital payment, current management system, willingness to digitize, and contract flexibility, with independent noise added to every relationship. Documentation readiness, operational complexity, capex need, onboarding cost, setup time, commission, and exclusivity then depend on owner maturity, lot size, parking type, and infrastructure.

### Daily performance

The observation window is 2025-08-01 through 2026-07-31, producing 365 rows per lot.

Public location inputs and market type create a demand tendency. Competition reduces expected occupancy modestly. Daily occupancy then includes weekday/weekend patterns, market-specific seasonality, weekly variation, and daily noise. Entries follow capacity, occupancy, operating hours, and dwell time. Platform bookings are a subset of entries and depend on digital readiness, demand, and a gradual adoption trend. Cancellations are a subset of bookings. Revenue follows entries, duration, tariff, and a noisy realization factor.

The hourly table is a compact typical-week profile: 24 hours for `Weekday` and 24 for `Weekend` per lot. Office, retail, residential, transit, hospital, and mixed-use markets use different curve shapes. It is not a dated hourly time series.

### BD funnel

Every lot starts at `Identified`. Sequential transition probabilities depend on willingness, flexibility, documentation, digital readiness, decision-maker access, demand attractiveness, capacity, and lead-source quality. Random noise prevents deterministic outcomes. Events are contiguous, dated in stage order, and a lead is `Won` only after stage 7 (`Onboarded`).

No acquisition score, recommendation flag, target segment, or equivalent hidden answer is generated in the data pipeline.

## Automated validation

Python checks cover primary-key uniqueness, coordinates, ranges, one-to-one companion rows, 365-day coverage, 48-row hourly coverage, occupancy/bookings/revenue consistency, acquisition-term ranges, and sequential outreach logic.

PostgreSQL adds foreign keys, nullability, controlled vocabularies, numeric checks, generated columns, and 35 cross-row/cross-table SQL rules. Business-logic checks measure tendencies rather than requiring perfect correlations. Actual results are written to `validation/` and summarized in `data_profile.md`.

## Reproducibility

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
make db-build db-seed
make pipeline
make test
```

`make pipeline` uses the cached snapshot, regenerates raw/processed CSVs, loads PostgreSQL, and runs both Python and SQL validation. Refreshing public sources is intentionally separate: `make data-source`.

## Limitations

- The fallback POI snapshot is search-based and incomplete, especially for offices, shops, malls, and unnamed features.
- Nominatim/OSM centroids are not surveyed entrances, and haversine distance is not walking distance.
- All 120 capacities are synthetic because selected OSM records did not publish reliable capacity.
- Parking type is assumed where OSM did not provide a usable structure tag.
- Tariffs, amenities, owners, performance, commercial terms, hypothetical network sites, and outreach are synthetic.
- Fixed-date holidays only are flagged; movable festival effects are not claimed.
- Synthetic relationships demonstrate analysis mechanics and must not be reported as discoveries about PARK It Up or Delhi NCR.
