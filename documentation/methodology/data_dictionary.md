# Data Dictionary

**Project:** PARK It Up Acquisition Intelligence
**Schema:** `parkitup` (PostgreSQL 14+)
**Coverage:** 21 tables, 181 columns
**source field register:** `data_dictionary_source.csv` documents all 117 columns populated by the data pipeline with source reference and generation logic.

---

## Purpose

This document is the contract that the analytical layers build against. Every ETL script, every analytical query and every dashboard measure depends on the names, types and meanings recorded here. A wrong type or a missed column in this file causes real downstream bugs, so it is written to be exhaustive rather than readable in one sitting.

It also serves a second function that matters more than reference lookup. The project deliberately mixes publicly sourced data with simulated data, and the **Source Type** column is where that separation is made explicit at column level. The governing rule is that public and synthetic data are never conflated: a figure invented to make the model runnable is labelled as such, and no result derived from it is ever presented as a finding about the real world. Table-level provenance travels with the DDL, while `parkitup.data_lineage` and `data_dictionary_source.csv` add executable field-level lineage, source references, and generation logic.

**How to read Source Type.** *Public (OSM)* means extracted from OpenStreetMap and traceable to an element ID. *Public (curated)* means recorded from publicly available sources. *Synthetic* means invented, carrying no evidential weight whatsoever. *Assumed* means a transparent analyst classification used where public coverage is incomplete. *Config* means a project design decision. *Derived* means computed from other values rather than asserted. In the executed source build, all parking identities and coordinates are public OSM records, while every capacity and tariff is synthetic; the `*_source_type` columns make that mixed provenance explicit per row.

**How to read Raw/Derived.** *Raw* means the value is stored as measured or asserted. *Derived* means the database or a later layer computes it — the two generated columns (`dim_date.day_type`, `outreach.days_to_conversion`) and the entire scoring output.

---

## Reference tables

### dim_city

Administrative reference data for the Delhi NCR study area. **Grain:** one row per city. **Provenance:** public.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `city_id` | SMALLINT | NO | Surrogate primary key. | `1` | Config | Raw | Structural / join key |
| `city_name` | TEXT | NO | City name. Unique across the table. | `New Delhi` | Public (curated) | Raw | Market roll-up label |
| `state_name` | TEXT | NO | State or union territory the city sits in. | `Haryana` | Public (curated) | Raw | Context; regulatory grouping |
| `ncr_zone` | TEXT | NO | Analyst-assigned NCR sub-region, one of `Central NCR`, `South NCR`, `East NCR`, `West NCR`, `North NCR`. Not an official designation. | `South NCR` | Config | Raw | STRATEGIC_FIT — regional expansion grouping |
| `is_core_delhi` | BOOLEAN | NO | Whether the city is Delhi proper rather than a satellite. Defaults to false. | `true` | Public (curated) | Raw | STRATEGIC_FIT — core versus periphery weighting |

### dim_locality

The unit of market-level analysis, populated in the data pipeline. **Grain:** one row per locality. **Provenance:** public (OpenStreetMap plus curated desk research). Promoted to a dimension rather than left as a text column on `parking_lots` because four of the sixteen business questions are asked at this grain.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `locality_id` | SMALLINT | NO | Surrogate primary key. | `12` | Config | Raw | Structural / join key |
| `city_id` | SMALLINT | NO | Parent city. FK to `dim_city`. | `1` | Config | Raw | Structural / join key |
| `locality_name` | TEXT | NO | Locality name. Unique within a city. | `Connaught Place` | Public (curated) | Raw | Market reporting label |
| `micro_market_type` | TEXT | NO | Dominant land-use character, one of `CBD`, `Commercial`, `Retail High Street`, `IT/Office Park`, `Residential`, `Transit Hub`, `Hospital/Institutional`, `Mixed Use`. Drives expected demand pattern. | `CBD` | Public (curated) | Raw | DEMAND — sets expected demand shape; STRATEGIC_FIT — market priority |
| `has_metro_station` | BOOLEAN | NO | Whether a metro station lies within the locality. | `true` | Public (OSM) | Raw | DEMAND — transit accessibility |
| `metro_line_count` | SMALLINT | NO | Number of metro lines serving the locality, 0–6. Must be at least 1 when `has_metro_station` is true and exactly 0 when false. | `3` | Public (OSM) | Raw | DEMAND — interchange localities generate more footfall |
| `population_density_band` | TEXT | NO | One of `Low`, `Medium`, `High`, `Very High`. | `Very High` | Public (curated) | Raw | DEMAND — ambient demand context |
| `record_source` | TEXT | NO | Row provenance, `public_osm` or `public_curated`. No synthetic localities are permitted. | `public_curated` | Config | Raw | Provenance audit |

### dim_date

Calendar dimension covering the simulated observation window, 2025-08-01 to 2026-07-31. **Grain:** one row per calendar day. **Provenance:** public and deterministic. `DATE` is used directly as the primary key; a surrogate integer date key would add nothing and make ad-hoc SQL harder to read.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `activity_date` | DATE | NO | Calendar date. Primary key. | `2025-11-14` | Config | Raw | Structural / join key |
| `day_of_week` | SMALLINT | NO | ISO day number, 1–7 where 1 is Monday. | `5` | Derived | Derived | Weekday/weekend demand split |
| `day_name` | TEXT | NO | Day name. | `Friday` | Derived | Derived | Reporting label |
| `is_weekend` | BOOLEAN | NO | True for Saturday and Sunday. | `false` | Derived | Derived | DEMAND — weekend versus weekday patterns |
| `is_public_holiday` | BOOLEAN | NO | True for a public holiday. Defaults false. **Deliberately incomplete** — only fixed-date national holidays are flagged; movable festivals were not asserted from memory (assumption A-19). | `false` | Public (curated) | Raw | DEMAND — holiday effects, currently out of scope |
| `month_num` | SMALLINT | NO | Month number, 1–12. | `11` | Derived | Derived | Seasonality analysis |
| `month_name` | TEXT | NO | Month name. | `November` | Derived | Derived | Reporting label |
| `quarter_num` | SMALLINT | NO | Quarter, 1–4. | `4` | Derived | Derived | Period roll-up |
| `year_num` | SMALLINT | NO | Calendar year. | `2025` | Derived | Derived | Period roll-up |
| `iso_week` | SMALLINT | NO | ISO week number, 1–53. | `46` | Derived | Derived | Weekly trend analysis |
| `day_type` | TEXT | NO | **Generated column.** `Holiday` if a public holiday, else `Weekend`, else `Weekday`. Holiday takes precedence over weekend. Joins to `fact_lot_hourly_profile`. | `Weekday` | Derived | **Derived** | DEMAND — the day-type join key |

### dim_funnel_stage

Ordered business development funnel ladder, seeded in the schema layer because the scoring and funnel framework depends on it. **Grain:** one row per stage. **Provenance:** synthetic / config. Loss reasons are deliberately *not* stages — they live on `outreach.lost_reason`, because encoding them here would destroy the stage ordering.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `stage_id` | SMALLINT | NO | Surrogate primary key, 1–7. | `3` | Config | Raw | Structural / join key |
| `stage_code` | TEXT | NO | Stable machine-readable code. Unique. | `MEETING_DONE` | Config | Raw | Structural / join key |
| `stage_name` | TEXT | NO | Display name. | `Meeting Held` | Config | Raw | Reporting label |
| `stage_order` | SMALLINT | NO | Position in the ladder, unique, minimum 1. | `3` | Config | Raw | Funnel drop-off ordering (question 12) |
| `is_success_stage` | BOOLEAN | NO | True only for the terminal success stage. Defaults false. | `false` | Config | Raw | Conversion rate numerator |
| `stage_description` | TEXT | NO | What must have happened for a lead to have reached this stage. | `Substantive discussion completed…` | Config | Raw | Definitional clarity for BD reporting |

### dim_score_dimension

The five scoring pillars, held as data rather than as hard-coded strings. **Grain:** one row per pillar. **Provenance:** config.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `dimension_code` | TEXT | NO | Primary key, one of `DEMAND`, `REVENUE`, `COMPETITION`, `STRATEGIC_FIT`, `FEASIBILITY`. | `DEMAND` | Config | Raw | Structural / join key |
| `dimension_name` | TEXT | NO | Display name. Unique. | `Demand Potential` | Config | Raw | Reporting label |
| `pillar_group` | TEXT | NO | `Attractiveness` or `Feasibility`. Splits the score into the two axes of the Acquisition Matrix. | `Attractiveness` | Config | Raw | Defines dashboard page 3 axes |
| `description` | TEXT | NO | What the pillar measures. | `Latent parking demand around the lot…` | Config | Raw | Explainability |
| `display_order` | SMALLINT | NO | Presentation order. Unique. | `1` | Config | Raw | Consistent chart ordering |

### data_lineage

Machine-readable field provenance populated by the data pipeline. **Grain:** one row per populated table/column pair. **Provenance:** config. It separates row origin from attribute origin, which is essential when a public OSM parking coordinate carries synthetic capacity and tariff values.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `table_name` | TEXT | NO | Database table containing the field. Part of the primary key. | `parking_lots` | Config | Raw | Lineage lookup key |
| `column_name` | TEXT | NO | Column being classified. Part of the primary key. | `capacity_cars` | Config | Raw | Lineage lookup key |
| `lineage_type` | TEXT | NO | One of `PUBLIC`, `DERIVED`, `SYNTHETIC`, `ASSUMED`, `CONFIG`. | `SYNTHETIC` | Config | Raw | Prevents public/synthetic conflation |
| `source_name` | TEXT | NO | Human-readable source or generator name. | `Deterministic generator` | Config | Raw | Explainability |
| `source_reference` | TEXT | YES | Local file or public-source reference. | `python/etl/synthetic_generation.py` | Config | Raw | Reproducibility |
| `methodology_note` | TEXT | NO | How the field was sourced or generated. | `Generated from type and market...` | Config | Raw | Interview defensibility |
| `business_purpose` | TEXT | NO | Why the field exists in the analytical layer. | `Revenue input` | Config | Raw | Model traceability |

---

## Core entities

### owners

Simulated parking operators. **Grain:** one row per operator. **Provenance:** synthetic — names, willingness and commercial posture are generated and are **not** derived from any real operator or from PARK It Up records. Promoted to its own entity because one operator can control several lots, which is a real BD lever: a single negotiation can unlock four sites.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `owner_id` | INT | NO | Surrogate primary key, generated as identity. | `17` | Config | Raw | Structural / join key |
| `owner_code` | TEXT | NO | Stable business key. Unique. | `OWN-0017` | Synthetic | Raw | Structural / stable export key |
| `owner_name` | TEXT | NO | Operator name. Synthetic; not a real business. | `Saket Facilities Pvt Ltd` | Synthetic | Raw | Reporting label |
| `owner_type` | TEXT | NO | One of `Individual`, `Family Trust`, `Private Company`, `RWA`, `Mall Management`, `Government/Municipal`, `Hospital/Institution`. | `Mall Management` | Synthetic | Raw | FEASIBILITY — owner-type difficulty adjustment |
| `years_operating` | SMALLINT | NO | Years the operator has run parking, 0–80. | `12` | Synthetic | Raw | FEASIBILITY — establishment and process maturity |
| `digital_payment_enabled` | BOOLEAN | NO | Whether digital payment is already accepted. | `true` | Synthetic | Raw | FEASIBILITY — digital readiness |
| `management_system` | TEXT | NO | Current system, one of `None/Manual`, `Paper Register`, `Spreadsheet`, `Basic POS`, `Third-party App`. | `Basic POS` | Synthetic | Raw | FEASIBILITY — integration effort |
| `willingness_to_digitize` | SMALLINT | NO | 1–5 ordinal. 1 = actively resistant, 5 = already seeking a digital partner. | `4` | Synthetic | Raw | FEASIBILITY — primary driver |
| `contract_flexibility` | SMALLINT | NO | 1–5 ordinal. 1 = rigid, demands fixed rent and refuses revenue share; 5 = open to commission terms and pilots. | `3` | Synthetic | Raw | FEASIBILITY — commercial negotiability |
| `decision_maker_accessible` | BOOLEAN | NO | Whether BD can reach the person able to sign. A common real blocker for RWA and municipal owners. | `true` | Synthetic | Raw | FEASIBILITY — hard blocker |

### parking_lots

The central entity and the hub of the model. **Grain:** one row per physical parking facility. **Provenance: MIXED by attribute.** In the executed source build, all 120 identities and coordinates are public OSM records, parking type is assumed when OSM is silent, and all capacities, prices, owners and amenity flags are synthetic.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Surrogate primary key, generated as identity. | `42` | Config | Raw | Structural / join key |
| `lot_code` | TEXT | NO | Stable business key. Unique. | `PKL-0042` | Config | Raw | Structural / stable export key |
| `lot_name` | TEXT | NO | OSM name where present, otherwise a stable label derived from element type and ID. | `Palika Bazaar Parking` | Derived from public | Derived | Reporting label |
| `locality_id` | SMALLINT | NO | FK to `dim_locality`. | `12` | Public (curated) | Raw | Structural / market roll-up |
| `owner_id` | INT | NO | FK to `owners`. | `17` | Synthetic | Raw | Structural / FEASIBILITY join |
| `latitude` | NUMERIC(9,6) | NO | Decimal latitude. Constrained to 28.30–28.95, the Delhi NCR study area. | `28.630400` | Public (OSM) | Raw | DEMAND, COMPETITION, STRATEGIC_FIT — all distance work |
| `longitude` | NUMERIC(9,6) | NO | Decimal longitude. Constrained to 76.80–77.60. | `77.217700` | Public (OSM) | Raw | DEMAND, COMPETITION, STRATEGIC_FIT — all distance work |
| `parking_type` | TEXT | NO | OSM type where present; otherwise an assumed market-aware type from the permitted vocabulary. | `Multi-Level (MLCP)` | Assumed / public-derived | Raw | DEMAND and REVENUE — facility class expectations |
| `surface_type` | TEXT | NO | One of `Paved`, `Unpaved`, `Mixed`. | `Paved` | Synthetic | Raw | FEASIBILITY — capex likelihood |
| `capacity_cars` | SMALLINT | NO | Four-wheeler bays, 10–2000. All source values are synthetic because selected OSM records did not publish reliable capacity. | `250` | Synthetic | Raw | REVENUE — volume ceiling |
| `hourly_rate_inr` | NUMERIC(6,2) | NO | Tariff per hour in rupees, 0–500. | `30.00` | Synthetic | Raw | REVENUE — price point; COMPETITION — price position |
| `monthly_pass_inr` | NUMERIC(8,2) | YES | Monthly pass price in rupees if offered, otherwise null. Non-negative. | `2500.00` | Synthetic | Raw | REVENUE — secondary income line |
| `is_24x7` | BOOLEAN | NO | Whether the lot operates continuously. See `hours_source_type`. | `true` | Public / Assumed | Raw | REVENUE — available operating hours |
| `opens_at` | TIME | YES | Opening time. Must be null when `is_24x7`, and present when not. | `08:00:00` | Public / Assumed | Raw | REVENUE — operating window |
| `closes_at` | TIME | YES | Closing time. May be earlier than `opens_at` for lots trading past midnight. | `22:00:00` | Public / Assumed | Raw | REVENUE — operating window |
| `has_covered_parking` | BOOLEAN | NO | Whether covered bays exist. Defaults false. | `true` | Synthetic | Raw | DEMAND — willingness to pay a premium |
| `has_security_staff` | BOOLEAN | NO | Whether staff are present. Defaults false. | `true` | Synthetic | Raw | DEMAND — perceived safety |
| `has_cctv` | BOOLEAN | NO | Whether CCTV is installed. Defaults false. | `false` | Synthetic | Raw | DEMAND and FEASIBILITY — existing infrastructure |
| `record_source` | TEXT | NO | Row-level provenance, one of `public_osm`, `public_curated`, `synthetic`. Never mix these in a report without disclosing the split. | `public_osm` | Config | Raw | Provenance audit — credibility disclosure |
| `source_name` | TEXT | NO | Public source name for the parking identity and coordinates. | `OpenStreetMap` | Public (OSM) | Raw | Source audit |
| `source_reference` | TEXT | NO | Stable OSM element URL. | `https://www.openstreetmap.org/way/123` | Public (OSM) | Raw | Record traceability |
| `source_observed_on` | DATE | NO | Date associated with the cached public snapshot. | `2026-08-16` | Config | Raw | Reproducibility audit |
| `capacity_source_type` | TEXT | NO | Per-value source classification: `PUBLIC`, `SYNTHETIC`, or `ASSUMED`. | `SYNTHETIC` | Config | Raw | Prevents inferred capacity from appearing public |
| `price_source_type` | TEXT | NO | Per-value tariff provenance. | `SYNTHETIC` | Config | Raw | Revenue-model disclosure |
| `hours_source_type` | TEXT | NO | Per-value operating-hours provenance. | `ASSUMED` | Config | Raw | Operating-window disclosure |
| `amenities_source_type` | TEXT | NO | Per-value amenity provenance. | `SYNTHETIC` | Config | Raw | Infrastructure disclosure |
| `data_quality_flag` | TEXT | NO | `High`, `Medium`, or `Fallback` traceability/completeness flag. | `Fallback` | Derived | Derived | Source-quality filtering |
| `osm_id` | BIGINT | YES | OpenStreetMap element ID. Permitted **only** when `record_source` is `public_osm`, so synthetic rows cannot masquerade as extracted data. | `123456789` | Public (OSM) | Raw | Traceability |
| `created_at` | TIMESTAMPTZ | NO | Row insertion timestamp. Defaults to `now()`. | `2026-08-15 14:22:01+05:30` | Derived | Raw | Load audit |

### location_demand

Public-derived proximity and observed POI counts. **Grain:** one row per parking lot, one-to-one. **Provenance:** derived from the cached OSM snapshot. The Nominatim fallback is not exhaustive, so office/retail counts are minimum observed coverage rather than complete censuses. No footfall estimate or demand score is stored.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Primary key and FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `metro_distance_m` | INT | NO | Haversine distance to the nearest observed metro station, metres. | `320` | Derived from public | Derived | DEMAND — transit accessibility |
| `nearest_metro_station` | TEXT | YES | Name or stable OSM label for that station. | `Rajiv Chowk` | Derived from public | Derived | Explainability in the deep dive |
| `mall_distance_m` | INT | YES | Haversine distance to the nearest observed mall/retail building, or null. | `850` | Derived from public | Derived | DEMAND — retail trip generation |
| `office_count_500m` | SMALLINT | NO | Observed cached office features within 500 m; fallback coverage is incomplete. | `24` | Derived from public | Derived | DEMAND — weekday demand driver |
| `retail_count_500m` | SMALLINT | NO | Observed cached retail destinations within 500 m; fallback coverage is incomplete. | `78` | Derived from public | Derived | DEMAND — weekend demand driver |
| `restaurant_count_500m` | SMALLINT | NO | Observed restaurants and cafes within 500 m. | `35` | Derived from public | Derived | DEMAND — evening demand driver |
| `hospital_count_1km` | SMALLINT | NO | Observed hospitals and clinics within 1 km. | `2` | Derived from public | Derived | DEMAND — steady all-day demand |
| `education_count_1km` | SMALLINT | NO | Observed schools and colleges within 1 km. | `5` | Derived from public | Derived | DEMAND — institutional context |
| `transit_stop_count_500m` | SMALLINT | NO | Observed bus and other transit stops within 500 m. | `6` | Derived from public | Derived | DEMAND — multimodal accessibility |
| `measured_on` | DATE | NO | Date the POI extract was taken. OSM changes over time, so counts are reproducible only with reference to an extract date. | `2026-08-10` | Config | Raw | Reproducibility audit |
| `record_source` | TEXT | NO | One of `public_osm`, `public_curated`, `synthetic`. | `public_osm` | Config | Raw | Provenance audit |

### competition

The local competitive supply picture. **Grain:** one row per parking lot, one-to-one. **Provenance: MIXED** — competitor counts and distances are public (OSM parking amenities within radius); competitor pricing is synthetic, because informal Delhi NCR parking rates are not published.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Primary key and FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `competitor_count_500m` | SMALLINT | NO | Comparable cached OSM parking facilities within 500 m. | `3` | Derived from public | Derived | COMPETITION — primary competitive pressure |
| `competitor_count_1km` | SMALLINT | NO | Comparable cached OSM parking facilities within 1 km; never below the 500 m count. | `7` | Derived from public | Derived | COMPETITION — market saturation |
| `nearest_competitor_distance_m` | INT | YES | Haversine distance to the closest direct competitor within 1 km. | `180` | Derived from public | Derived | COMPETITION — immediacy of substitution |
| `competitor_avg_hourly_rate_inr` | NUMERIC(6,2) | YES | Mean competitor tariff in rupees. Null when no competitors exist. | `25.00` | Synthetic | Raw | COMPETITION — price positioning; a high local price is rewarded |
| `competitor_total_capacity_1km` | INT | YES | Sum of published OSM capacities among direct competitors; null when none publish capacity. | `600` | Derived from public | Derived | COMPETITION — known supply only |
| `aggregator_listed_count_1km` | SMALLINT | NO | Synthetic subset of competitors modelled as rival-platform listings. | `1` | Synthetic | Raw | COMPETITION and STRATEGIC_FIT — digitised supply pressure |
| `measured_on` | DATE | NO | Date the competitive extract was taken. | `2026-08-10` | Config | Raw | Reproducibility audit |
| `record_source` | TEXT | NO | One of `public_osm`, `public_curated`, `synthetic`. | `public_osm` | Config | Raw | Provenance audit |

### lot_acquisition_terms

Simulated per-site deal economics. **Grain:** one row per parking lot, one-to-one. **Provenance:** synthetic. These are **not** PARK It Up commercial terms and must not be presented as such. Split from `owners` because commission and onboarding cost are negotiated per site, while willingness and contract posture are properties of the operator.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Primary key and FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `expected_commission_pct` | NUMERIC(4,2) | NO | Commission percentage the operator is modelled as willing to concede on platform-originated bookings, 0–40. Central to the revenue model; sensitivity-tested as question 10 (assumption A-08). | `12.50` | Synthetic | Raw | REVENUE — the commission rate itself |
| `estimated_onboarding_cost_inr` | NUMERIC(10,2) | NO | One-off setup cost in rupees. The source population spans ₹33,000–₹270,000 (assumption A-18). | `87500.00` | Synthetic | Raw | FEASIBILITY — cost to acquire |
| `documentation_readiness` | SMALLINT | NO | 1–5 ordinal. 1 = no ownership proof or licences available, 5 = complete and to hand. | `4` | Synthetic | Raw | FEASIBILITY — closing friction |
| `operational_complexity` | SMALLINT | NO | 1–5 ordinal. 1 = plug-and-play signage only; 5 = boom barriers, multiple entries, shared access rights or municipal permissions. | `2` | Synthetic | Raw | FEASIBILITY — implementation effort, inverted |
| `exclusivity_possible` | BOOLEAN | NO | Whether the operator would consider platform exclusivity. | `false` | Synthetic | Raw | STRATEGIC_FIT and FEASIBILITY — defensibility |
| `requires_capex` | BOOLEAN | NO | Whether physical investment is needed before going live. | `true` | Synthetic | Raw | FEASIBILITY — capital gate |
| `estimated_setup_days` | SMALLINT | NO | Working days from signature to live, 0–365. | `21` | Synthetic | Raw | FEASIBILITY — time to revenue |
| `quoted_on` | DATE | NO | Date these terms were captured. | `2026-07-28` | Config | Raw | Freshness audit |

### existing_network_sites

**Hypothetical** network footprint supporting the Strategic Fit pillar. **Grain:** one row per network site. **Provenance:** synthetic. This does **not** represent real PARK It Up inventory and contains no confidential data. It exists so coverage-gap and cannibalisation logic has a defined baseline to measure against (assumption A-13).

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `network_site_id` | INT | NO | Surrogate primary key, generated as identity. | `8` | Config | Raw | Structural / join key |
| `site_code` | TEXT | NO | Stable business key. Unique. | `NET-0008` | Synthetic | Raw | Structural / stable export key |
| `locality_id` | SMALLINT | NO | FK to `dim_locality`. | `12` | Synthetic | Raw | STRATEGIC_FIT — locality coverage counts |
| `latitude` | NUMERIC(9,6) | NO | Decimal latitude, constrained to 28.30–28.95. | `28.552300` | Synthetic | Raw | STRATEGIC_FIT — distance to nearest existing site |
| `longitude` | NUMERIC(9,6) | NO | Decimal longitude, constrained to 76.80–77.60. | `77.216800` | Synthetic | Raw | STRATEGIC_FIT — distance to nearest existing site |
| `capacity_cars` | SMALLINT | NO | Bays at the existing site, 10–2000. | `180` | Synthetic | Raw | STRATEGIC_FIT — incremental capacity contribution |
| `live_since` | DATE | NO | Date the site went live. | `2024-06-15` | Synthetic | Raw | Network maturity context |
| `site_status` | TEXT | NO | `Live` or `Paused`. | `Live` | Synthetic | Raw | STRATEGIC_FIT — only live sites cannibalise |

---

## Fact tables

### fact_lot_daily

Simulated daily operating performance. **Grain:** one row per parking lot per calendar day. **Provenance:** synthetic — these are **not** observed PARK It Up or operator figures. At roughly 120 lots over 365 days this is about 43,800 rows.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Part of the composite primary key; FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `activity_date` | DATE | NO | Part of the composite primary key; FK to `dim_date`. | `2025-11-14` | Config | Raw | Structural / join key |
| `peak_occupancy_rate` | NUMERIC(5,4) | NO | Highest concurrent occupancy that day as a ratio, 0–1. Stored as a rate rather than a percentage so the "occupancy above 100%" rule is enforced by the database rather than discovered later. | `0.9200` | Synthetic | Raw | DEMAND — peak pressure; REVENUE — headroom |
| `avg_occupancy_rate` | NUMERIC(5,4) | NO | Mean occupancy across operating hours, 0–1. Can never exceed the same day's peak. | `0.6100` | Synthetic | Raw | DEMAND and REVENUE — sustainable utilisation basis |
| `vehicle_entries` | SMALLINT | NO | Total vehicles entering that day across all channels. Non-negative. **Legitimately exceeds `capacity_cars`** because of turnover — a 100-bay lot can serve 400 vehicles a day; only concurrent occupancy is capped. | `800` | Synthetic | Raw | DEMAND — throughput volume |
| `platform_bookings` | SMALLINT | NO | Subset of entries originating from the platform. Cannot exceed `vehicle_entries`. The commission base — contribution is earned on these only, not on total lot revenue (assumption A-07). | `120` | Synthetic | Raw | REVENUE — the commission base |
| `booking_cancellations` | SMALLINT | NO | Platform bookings cancelled. Cannot exceed `platform_bookings`. | `6` | Synthetic | Raw | REVENUE — realisation quality |
| `gross_parking_revenue_inr` | NUMERIC(10,2) | NO | Total revenue collected by the **operator** that day, all channels. Non-negative. Platform contribution is a modelled share of the platform-booked portion, computed in the scoring engine (assumption A-20). | `42000.00` | Synthetic | Raw | REVENUE — economic base |
| `avg_park_duration_hours` | NUMERIC(4,2) | NO | Mean dwell time in hours, greater than 0 and at most 24. | `2.75` | Synthetic | Raw | REVENUE — multiplies directly into revenue (assumption A-05) |

### fact_lot_hourly_profile

Typical-week hourly demand shape per lot. **Grain:** one row per lot per day type per hour of day — exactly 48 rows per lot. **Provenance:** synthetic. Deliberately *not* a dated time series: a single date-and-hour table would have needed roughly 1.05 million synthetic rows to answer questions asked at daily or typical-hour grain.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Part of the composite primary key; FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `day_type` | TEXT | NO | `Weekday` or `Weekend` only. Holidays are not profiled separately; scoring maps `Holiday` from `dim_date.day_type` onto the weekend profile and documents that simplification. | `Weekday` | Config | Raw | DEMAND — weekday versus weekend shape |
| `hour_of_day` | SMALLINT | NO | Hour, 0–23. Part of the composite primary key. | `18` | Config | Raw | DEMAND — peak-hour identification |
| `avg_occupancy_rate` | NUMERIC(5,4) | NO | Mean occupancy in that hour as a ratio, 0–1. | `0.8400` | Synthetic | Raw | DEMAND — peak intensity and duration |
| `avg_entries` | NUMERIC(6,2) | NO | Mean vehicles entering in that hour. Non-negative. | `62.50` | Synthetic | Raw | DEMAND — arrival pattern |

---

## Business development pipeline

### outreach

Simulated BD lead records. **Grain:** one row per parking lot — the one-to-one rule is enforced by a unique constraint. **Provenance:** synthetic. Contains no real PARK It Up pipeline data, no real contact details and no real operator names.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `lead_id` | INT | NO | Surrogate primary key, generated as identity. | `31` | Config | Raw | Structural / join key |
| `parking_id` | INT | NO | FK to `parking_lots`, unique, cascade delete. Enforces one lead per lot (assumption A-23). | `42` | Config | Raw | Structural / join key |
| `lead_source` | TEXT | NO | One of `Field Survey`, `Inbound Enquiry`, `Referral`, `Cold Call`, `Desk Research`, `Broker`, `Partner Network`. | `Referral` | Synthetic | Raw | Question 13 — lead-source effectiveness |
| `first_contact_date` | DATE | YES | Date of first contact. Null exactly when `contact_attempts` is 0. | `2026-01-10` | Synthetic | Raw | Cycle-time basis |
| `contact_attempts` | SMALLINT | NO | Number of contact attempts, 0–50. Defaults 0. Implies `first_contact_date` and vice versa. | `4` | Synthetic | Raw | Question 12 — effort per lead |
| `furthest_stage_id` | SMALLINT | NO | Deepest stage the lead ever reached. FK to `dim_funnel_stage`. Funnel drop-off is the distribution of this column. | `7` | Synthetic | Raw | Question 12 — funnel drop-off |
| `pipeline_status` | TEXT | NO | `Active`, `Won` or `Lost`. Kept separate from `furthest_stage_id` because a lead can die at any stage, and encoding losses as stages would destroy stage ordering. | `Won` | Synthetic | Raw | Conversion rate denominator |
| `lost_reason` | TEXT | YES | Required when status is `Lost` and forbidden otherwise. One of `No Response`, `Commission Too Low`, `Wants Fixed Rent`, `Exclusivity Refused`, `Documentation Unavailable`, `Competitor Signed`, `Owner Not Decision Maker`. | `null` | Synthetic | Raw | Question 12 — loss analysis |
| `documents_available` | BOOLEAN | NO | Whether required documents were obtained. Defaults false. | `true` | Synthetic | Raw | FEASIBILITY — closing friction |
| `owner_interest_level` | SMALLINT | YES | 1–5 ordinal recording observed enthusiasm, or null if never assessed. | `5` | Synthetic | Raw | Question 13 — conversion correlate |
| `conversion_date` | DATE | YES | Required when status is `Won` and forbidden otherwise. Cannot precede `first_contact_date`. | `2026-02-19` | Synthetic | Raw | Cycle-time basis |
| `assigned_bd_rep` | TEXT | NO | Synthetic rep identifier. Deliberately not a real person's name. | `BD-03` | Synthetic | Raw | BD workload distribution |
| `days_to_conversion` | INT | YES | **Generated column:** `conversion_date - first_contact_date` in days. Null for any lead that has not converted. Generated so the metric cannot disagree with the dates it derives from. | `40` | Derived | **Derived** | BD cycle-time analysis |

### outreach_events

Log of funnel stage entries. **Grain:** one row per lead per stage reached. **Provenance:** synthetic. Small, but it is what makes stage-to-stage conversion rates and inter-stage cycle times computable — without it only the final resting stage is knowable. Business rule: the stages present for a lead must be contiguous from 1 up to `outreach.furthest_stage_id`, validated by data-quality rules DQ-030 and DQ-031 because the invariant spans rows.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `event_id` | BIGINT | NO | Surrogate primary key, generated as identity. | `214` | Config | Raw | Structural / join key |
| `lead_id` | INT | NO | FK to `outreach`, cascade delete. | `31` | Config | Raw | Structural / join key |
| `stage_id` | SMALLINT | NO | FK to `dim_funnel_stage`. Unique per lead, so a stage cannot be logged twice and inflate conversion denominators. | `3` | Config | Raw | Question 12 — stage-to-stage conversion |
| `event_date` | DATE | NO | Date the lead entered this stage. | `2026-01-24` | Synthetic | Raw | Inter-stage cycle time |
| `channel` | TEXT | NO | One of `Phone`, `In-Person`, `Email`, `WhatsApp`, `Video Call`. | `In-Person` | Synthetic | Raw | Question 13 — channel effectiveness |

---

## Scoring configuration and results

### scoring_weight_set

Named, versioned weighting scenarios. **Grain:** one row per scenario. **Provenance:** config. The baseline encodes the initial business judgement; the alternates exist to test how fragile the recommendations are to that judgement.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `weight_set_id` | SMALLINT | NO | Surrogate primary key. | `1` | Config | Raw | Structural / join key |
| `weight_set_code` | TEXT | NO | Stable code. Unique. One of `BASELINE_V1`, `EQUAL_WEIGHT`, `DEMAND_LED`, `FEASIBILITY_LED`. | `BASELINE_V1` | Config | Raw | Questions 9 and 10 — scenario selector |
| `description` | TEXT | NO | What the scenario represents and why it exists. | `Initial business judgement…` | Config | Raw | Explainability |
| `is_default` | BOOLEAN | NO | Marks the scenario used for headline results. A partial unique index permits **at most one**, so reports cannot silently use the wrong weighting. | `true` | Config | Raw | Governs published results |
| `created_at` | TIMESTAMPTZ | NO | Creation timestamp. Defaults to `now()`. | `2026-08-15 14:22:01+05:30` | Derived | Raw | Audit |

### scoring_weight

Pillar weights within each scenario. **Grain:** one row per pillar per weight set — five rows per set. **Provenance:** config. Weights within a set must sum to 1.0, enforced by data-quality rule DQ-020 rather than a `CHECK` constraint, because the invariant spans rows and PostgreSQL evaluates `CHECK` per row.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `weight_set_id` | SMALLINT | NO | Part of the composite primary key; FK to `scoring_weight_set`, cascade delete. | `1` | Config | Raw | Structural / join key |
| `dimension_code` | TEXT | NO | Part of the composite primary key; FK to `dim_score_dimension`. | `DEMAND` | Config | Raw | Structural / join key |
| `weight` | NUMERIC(5,4) | NO | Pillar weight, 0–1. Baseline values are Demand 0.30, Revenue 0.25, Competition 0.15, Strategic Fit 0.15, Feasibility 0.15 (assumption A-15). | `0.3000` | Config | Raw | Determines the composite score |

### segment_rule

The ACQUIRE NOW / PURSUE / DEVELOP / AVOID decision table. **Grain:** one row per segment. **Provenance:** config. Held as data so thresholds are visible, versionable and arguable rather than buried in a `CASE` statement. Rules are evaluated in `eval_priority` order, first match wins, and the lowest-priority rule has no bounds, so every lot receives exactly one segment.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `segment_code` | TEXT | NO | Primary key, one of `ACQUIRE_NOW`, `PURSUE`, `DEVELOP`, `AVOID`. | `ACQUIRE_NOW` | Config | Raw | Structural / the project's output |
| `segment_label` | TEXT | NO | Display label. Unique. | `Acquire Now` | Config | Raw | Reporting label |
| `eval_priority` | SMALLINT | NO | Evaluation order, unique, minimum 1. First match wins. | `1` | Config | Raw | Guarantees deterministic assignment |
| `min_attractiveness` | NUMERIC(5,2) | YES | Inclusive lower bound on attractiveness, 0–100, or null for no bound. **Provisional** (assumption A-14). | `65.00` | Config | Raw | Segment boundary |
| `min_feasibility` | NUMERIC(5,2) | YES | Inclusive lower bound on feasibility, 0–100, or null. Must be below `max_feasibility` when both are present. | `60.00` | Config | Raw | Segment boundary |
| `max_feasibility` | NUMERIC(5,2) | YES | Exclusive upper bound on feasibility, 0–100, or null. | `null` | Config | Raw | Segment boundary |
| `bd_action` | TEXT | NO | The concrete instruction handed to the BD team. A segment that does not change what somebody does on Monday morning is not worth computing. | `Assign a named owner this week…` | Config | Raw | The actionable output |
| `rationale` | TEXT | NO | Why the segment exists and why its bounds are set where they are. | `Attractive market AND a closeable counterparty…` | Config | Raw | Explainability |

### lot_dimension_score

The explainability layer and the audit trail behind every headline score. **Grain:** one row per lot per weight set per pillar — five rows per lot per scenario. **Provenance:** derived, scoring output. This table is what makes the model explainable: the deep-dive dashboard page reads directly from it.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Part of the composite primary key; FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `weight_set_id` | SMALLINT | NO | Part of the composite primary key; FK to `scoring_weight_set`, cascade delete. | `1` | Config | Raw | Structural / scenario key |
| `dimension_code` | TEXT | NO | Part of the composite primary key; FK to `dim_score_dimension`. | `DEMAND` | Config | Raw | Structural / join key |
| `subscore` | NUMERIC(5,2) | NO | Pillar score on a 0–100 scale, min-max normalised within the study area (assumption A-16). | `82.40` | Derived | **Derived** | The pillar-level result |
| `weight_applied` | NUMERIC(5,4) | NO | Weight used, 0–1. Must match the weight set it claims to use (rule DQ-023). | `0.3000` | Derived | **Derived** | Audit of the calculation |
| `weighted_contribution` | NUMERIC(6,3) | NO | `subscore × weight_applied`. Non-negative. Stored rather than recomputed so a published score can be reconciled long after the code has moved on. | `24.720` | Derived | **Derived** | Explainability — "why this score" |

### lot_score

Headline results. **Grain:** one row per lot per weight set. **Provenance:** derived, scoring output. Including `weight_set_id` in the primary key is what makes sensitivity analysis non-destructive: alternative scenarios coexist with the baseline instead of overwriting it. The five pillar subscores are deliberately *not* repeated here — they live in `lot_dimension_score`, and rule DQ-021 reconciles `acquisition_score` against the sum of the components within 0.05, making this a *verified* redundancy rather than a latent inconsistency.

| Column | Data Type | Null | Definition | Example | Source Type | Raw/Derived | Business Relevance |
|--------|-----------|------|------------|---------|-------------|-------------|--------------------|
| `parking_id` | INT | NO | Part of the composite primary key; FK to `parking_lots`, cascade delete. | `42` | Config | Raw | Structural / join key |
| `weight_set_id` | SMALLINT | NO | Part of the composite primary key; FK to `scoring_weight_set`, cascade delete. | `1` | Config | Raw | Structural / scenario key |
| `attractiveness_score` | NUMERIC(5,2) | NO | Weighted blend of DEMAND, REVENUE, COMPETITION and STRATEGIC_FIT, renormalised to 0–100. The X axis of the Acquisition Matrix. | `72.50` | Derived | **Derived** | Questions 4, 15, 16 |
| `feasibility_score` | NUMERIC(5,2) | NO | The FEASIBILITY pillar on its own 0–100 scale. Kept separate because a lot that is wonderful and unobtainable needs a different BD response from one that is mediocre and easy — averaging them would hide exactly the distinction the BD team needs. The Y axis of the Matrix. | `64.00` | Derived | **Derived** | Question 11 |
| `acquisition_score` | NUMERIC(5,2) | NO | The headline Parking Acquisition Priority Score, 0–100. Structurally bounded as a convex combination of bounded subscores; no clipping is applied, so a normalisation bug fails loudly instead of being masked. | `70.25` | Derived | **Derived** | Questions 4 and 15 — the primary output |
| `segment_code` | TEXT | NO | FK to `segment_rule`. The assigned BD action. | `ACQUIRE_NOW` | Derived | **Derived** | The actionable output |
| `rank_overall` | INT | YES | Rank within the weight set, minimum 1. Unique per scenario, which catches tie-handling bugs in the ranking logic. | `1` | Derived | **Derived** | Question 4 — the priority list |
| `scored_at` | TIMESTAMPTZ | NO | When the score was computed. Defaults to `now()`. | `2026-08-16 09:14:22+05:30` | Derived | Raw | Reproducibility audit |

---

## Columns deliberately excluded

The original specification proposed several fields that were removed during modelling. Each removal has a reason, and the reasons matter more than the fields: together they are the difference between a schema that stores facts and one that quietly launders estimates into observations.

| Column proposed | Where it would have gone | Why excluded |
|-----------------|--------------------------|--------------|
| `current_occupancy` | `parking_lots` | A point-in-time reading of a time series. Derived from `fact_lot_daily` on demand; storing it on the entity would go stale immediately and would invite comparison against the facts it duplicates. |
| `estimated_daily_footfall` | `location_demand` | An estimate, not a measurement. `location_demand` holds only measured POI facts. Computed in the scoring feature layer, because the question "how did you observe footfall?" has no good answer (assumption A-11). |
| `commercial_density` | `location_demand` | A derived index over the POI counts already stored. Storing it beside its own inputs creates two sources of truth that can disagree. |
| `weekday_activity` | `location_demand` | Vague and derived. Replaced by `fact_lot_hourly_profile`, which is measurement at a declared grain rather than an unexplained score. |
| `weekend_activity` | `location_demand` | Same reason. The weekday/weekend distinction is now `fact_lot_hourly_profile.day_type`. |
| `acquisition_difficulty` | `owner_profiles` | The **output** of the Feasibility pillar, computed from willingness, documentation readiness, operational complexity and owner type. Storing it as an input would have made the scoring circular. |
| `exits` | `parking_performance` | Over a full day, exits approximately equal entries. The difference is overnight vehicles, which `peak_occupancy_rate` and `avg_park_duration_hours` already capture. A redundant column that would need its own consistency rule. |
| `contacted` | `outreach` | Exactly equivalent to `contact_attempts > 0`. A boolean that can contradict the count beside it. |
| `meeting_completed` | `outreach` | A funnel stage, not an attribute. Now `dim_funnel_stage.MEETING_DONE`, reachable via `furthest_stage_id` and logged in `outreach_events`. |
| `owner_interested` | `outreach` | A funnel stage masquerading as a flag. Interest level is now the richer 1–5 `owner_interest_level`, and stage progress is tracked properly. |
| `partnership_status` | `outreach` | Replaced by `furthest_stage_id` plus `pipeline_status`, which cannot contradict each other. A single free-text status column could say "Won" while the stage said "Contacted". |
| `owner_type` | `parking_lots` | Duplicated between `parking_lots` and `owner_profiles`. Now lives once on `owners`, which was promoted to its own entity because one operator can control several lots. |
| `locality` (text) | `parking_lots` | Normalised into `dim_locality`. Four business questions are asked at locality grain, and text matching would have made them fragile with nowhere to record locality attributes. |
| `city` (text) | `parking_lots` | Normalised into `dim_city` via `dim_locality`. Reachable by join; storing it too would permit a lot in "Noida" whose locality sits in Gurugram. |
| `operating_hours` (free text) | `parking_lots` | Unparseable and unvalidatable. Split into `is_24x7`, `opens_at` and `closes_at`, so "invalid operating hours" becomes a machine-checkable constraint rather than a data-quality report finding. |
| `hour` | `parking_performance` | Combining date and hour in one table meant roughly 1.05 million synthetic rows for questions asked at daily or typical-hour grain. Split into `fact_lot_daily` and `fact_lot_hourly_profile`, preserving peak-hour analysis at about 4% of the row count. |
| two-wheeler capacity and rate | `parking_lots` | Would have required a second capacity, a second tariff, a second occupancy series and a bay-equivalence factor. Excluded to keep the revenue model single-rate and explainable; the limitation is recorded as assumption A-04 and understates demand at retail and hospital locations. |
