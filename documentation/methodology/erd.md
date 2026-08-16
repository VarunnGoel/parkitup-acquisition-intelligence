# Entity Relationship Model

**Project:** PARK It Up Acquisition Intelligence
**Schema:** `parkitup` (PostgreSQL 14+)
**Tables:** 21 · **Foreign keys:** 22 · **CHECK expressions:** 101

---

## Reading this document

The model is deliberately split into three diagrams rather than presented as one. Twenty-one tables in a single ERD is technically complete and practically unreadable, and the groups correspond to what a parking lot *is*, how it *performs*, how it *scores*, and how field provenance is audited.

`parking_lots` is the hub of the entire model. Every fact and nearly every attribute table hangs off it, which makes it the natural bridge table for Power BI and the natural join anchor for almost every analytical query.

---

## 1. Core entities — what a parking lot is

Location and ownership context, plus the three one-to-one attribute tables that describe a lot's surroundings and deal terms.

```mermaid
erDiagram
    dim_city             ||--o{ dim_locality           : "contains"
    dim_locality         ||--o{ parking_lots           : "situates"
    dim_locality         ||--o{ existing_network_sites : "situates"
    owners               ||--o{ parking_lots           : "operates"
    parking_lots         ||--|| location_demand        : "described by"
    parking_lots         ||--|| competition            : "faces"
    parking_lots         ||--|| lot_acquisition_terms  : "priced by"

    dim_city {
        smallint city_id PK
        text     city_name UK
        text     state_name
        text     ncr_zone
        boolean  is_core_delhi
    }
    dim_locality {
        smallint locality_id PK
        smallint city_id FK
        text     locality_name
        text     micro_market_type
        boolean  has_metro_station
        smallint metro_line_count
        text     population_density_band
        text     record_source
    }
    owners {
        int      owner_id PK
        text     owner_code UK
        text     owner_name
        text     owner_type
        smallint years_operating
        boolean  digital_payment_enabled
        text     management_system
        smallint willingness_to_digitize
        smallint contract_flexibility
        boolean  decision_maker_accessible
    }
    parking_lots {
        int      parking_id PK
        text     lot_code UK
        text     lot_name
        smallint locality_id FK
        int      owner_id FK
        numeric  latitude
        numeric  longitude
        text     parking_type
        text     surface_type
        smallint capacity_cars
        numeric  hourly_rate_inr
        numeric  monthly_pass_inr
        boolean  is_24x7
        time     opens_at
        time     closes_at
        text     source_name
        text     source_reference
        date     source_observed_on
        text     capacity_source_type
        text     price_source_type
        text     hours_source_type
        text     amenities_source_type
        text     data_quality_flag
        text     record_source
        bigint   osm_id
    }
    location_demand {
        int      parking_id PK_FK
        int      metro_distance_m
        text     nearest_metro_station
        int      mall_distance_m
        smallint office_count_500m
        smallint retail_count_500m
        smallint restaurant_count_500m
        smallint hospital_count_1km
        smallint education_count_1km
        smallint transit_stop_count_500m
        date     measured_on
        text     record_source
    }
    competition {
        int      parking_id PK_FK
        smallint competitor_count_500m
        smallint competitor_count_1km
        int      nearest_competitor_distance_m
        numeric  competitor_avg_hourly_rate_inr
        int      competitor_total_capacity_1km
        smallint aggregator_listed_count_1km
        date     measured_on
        text     record_source
    }
    lot_acquisition_terms {
        int      parking_id PK_FK
        numeric  expected_commission_pct
        numeric  estimated_onboarding_cost_inr
        smallint documentation_readiness
        smallint operational_complexity
        boolean  exclusivity_possible
        boolean  requires_capex
        smallint estimated_setup_days
        date     quoted_on
    }
    existing_network_sites {
        int      network_site_id PK
        text     site_code UK
        smallint locality_id FK
        numeric  latitude
        numeric  longitude
        smallint capacity_cars
        date     live_since
        text     site_status
    }
```

## 2. Performance and pipeline — how a lot behaves

The measured (simulated) time series and the business development funnel.

```mermaid
erDiagram
    parking_lots     ||--o{ fact_lot_daily           : "performs"
    dim_date         ||--o{ fact_lot_daily           : "dates"
    parking_lots     ||--o{ fact_lot_hourly_profile  : "shapes"
    parking_lots     ||--|| outreach                 : "pursued via"
    outreach         ||--o{ outreach_events          : "progresses through"
    dim_funnel_stage ||--o{ outreach                 : "furthest reached"
    dim_funnel_stage ||--o{ outreach_events          : "classifies"

    dim_date {
        date     activity_date PK
        smallint day_of_week
        text     day_name
        boolean  is_weekend
        boolean  is_public_holiday
        smallint month_num
        text     month_name
        smallint quarter_num
        smallint year_num
        smallint iso_week
        text     day_type "GENERATED"
    }
    fact_lot_daily {
        int      parking_id PK_FK
        date     activity_date PK_FK
        numeric  peak_occupancy_rate
        numeric  avg_occupancy_rate
        smallint vehicle_entries
        smallint platform_bookings
        smallint booking_cancellations
        numeric  gross_parking_revenue_inr
        numeric  avg_park_duration_hours
    }
    fact_lot_hourly_profile {
        int      parking_id PK_FK
        text     day_type PK
        smallint hour_of_day PK
        numeric  avg_occupancy_rate
        numeric  avg_entries
    }
    dim_funnel_stage {
        smallint stage_id PK
        text     stage_code UK
        text     stage_name
        smallint stage_order UK
        boolean  is_success_stage
        text     stage_description
    }
    outreach {
        int      lead_id PK
        int      parking_id FK_UK
        text     lead_source
        date     first_contact_date
        smallint contact_attempts
        smallint furthest_stage_id FK
        text     pipeline_status
        text     lost_reason
        boolean  documents_available
        smallint owner_interest_level
        date     conversion_date
        text     assigned_bd_rep
        int      days_to_conversion "GENERATED"
    }
    outreach_events {
        bigint   event_id PK
        int      lead_id FK
        smallint stage_id FK
        date     event_date
        text     channel
    }
```

## 3. Scoring — how a lot is judged

Configuration on the left, results on the right. The defining feature is that `weight_set_id` runs through both, which is what allows several weighting scenarios to coexist rather than overwrite one another.

```mermaid
erDiagram
    dim_score_dimension ||--o{ scoring_weight       : "weighted in"
    scoring_weight_set  ||--o{ scoring_weight       : "comprises"
    scoring_weight_set  ||--o{ lot_dimension_score  : "produces"
    scoring_weight_set  ||--o{ lot_score            : "produces"
    dim_score_dimension ||--o{ lot_dimension_score  : "decomposes into"
    parking_lots        ||--o{ lot_dimension_score  : "explained by"
    parking_lots        ||--o{ lot_score            : "ranked by"
    segment_rule        ||--o{ lot_score            : "classifies"

    dim_score_dimension {
        text     dimension_code PK
        text     dimension_name UK
        text     pillar_group
        text     description
        smallint display_order UK
    }
    scoring_weight_set {
        smallint    weight_set_id PK
        text        weight_set_code UK
        text        description
        boolean     is_default
        timestamptz created_at
    }
    scoring_weight {
        smallint weight_set_id PK_FK
        text     dimension_code PK_FK
        numeric  weight
    }
    segment_rule {
        text     segment_code PK
        text     segment_label UK
        smallint eval_priority UK
        numeric  min_attractiveness
        numeric  min_feasibility
        numeric  max_feasibility
        text     bd_action
        text     rationale
    }
    lot_dimension_score {
        int      parking_id PK_FK
        smallint weight_set_id PK_FK
        text     dimension_code PK_FK
        numeric  subscore
        numeric  weight_applied
        numeric  weighted_contribution
    }
    lot_score {
        int         parking_id PK_FK
        smallint    weight_set_id PK_FK
        numeric     attractiveness_score
        numeric     feasibility_score
        numeric     acquisition_score
        text        segment_code FK
        int         rank_overall
        timestamptz scored_at
    }
```

---

## Complete relationship register

| # | Parent | Child | Child FK column | Cardinality | On delete | Meaning |
|---|--------|-------|-----------------|-------------|-----------|---------|
| 1 | `dim_city` | `dim_locality` | `city_id` | 1 : many | restrict | A city contains many localities |
| 2 | `dim_locality` | `parking_lots` | `locality_id` | 1 : many | restrict | A locality holds many lots |
| 3 | `dim_locality` | `existing_network_sites` | `locality_id` | 1 : many | restrict | A locality holds many network sites |
| 4 | `owners` | `parking_lots` | `owner_id` | 1 : many | restrict | An operator may run several lots |
| 5 | `parking_lots` | `location_demand` | `parking_id` | 1 : 1 | cascade | Each lot has one demand profile |
| 6 | `parking_lots` | `competition` | `parking_id` | 1 : 1 | cascade | Each lot has one competitive picture |
| 7 | `parking_lots` | `lot_acquisition_terms` | `parking_id` | 1 : 1 | cascade | Each lot has one set of deal terms |
| 8 | `parking_lots` | `fact_lot_daily` | `parking_id` | 1 : many | cascade | Each lot has many daily observations |
| 9 | `dim_date` | `fact_lot_daily` | `activity_date` | 1 : many | restrict | Each date has many lot observations |
| 10 | `parking_lots` | `fact_lot_hourly_profile` | `parking_id` | 1 : many | cascade | Each lot has 48 profile rows |
| 11 | `parking_lots` | `outreach` | `parking_id` | 1 : 1 | cascade | Each lot has at most one lead |
| 12 | `dim_funnel_stage` | `outreach` | `furthest_stage_id` | 1 : many | restrict | Many leads rest at a given stage |
| 13 | `outreach` | `outreach_events` | `lead_id` | 1 : many | cascade | A lead logs many stage entries |
| 14 | `dim_funnel_stage` | `outreach_events` | `stage_id` | 1 : many | restrict | A stage classifies many events |
| 15 | `dim_score_dimension` | `scoring_weight` | `dimension_code` | 1 : many | restrict | A pillar is weighted in many sets |
| 16 | `scoring_weight_set` | `scoring_weight` | `weight_set_id` | 1 : many | cascade | A set comprises five weights |
| 17 | `parking_lots` | `lot_dimension_score` | `parking_id` | 1 : many | cascade | A lot has five components per set |
| 18 | `scoring_weight_set` | `lot_dimension_score` | `weight_set_id` | 1 : many | cascade | A set produces many components |
| 19 | `dim_score_dimension` | `lot_dimension_score` | `dimension_code` | 1 : many | restrict | A pillar appears in many components |
| 20 | `parking_lots` | `lot_score` | `parking_id` | 1 : many | cascade | A lot is scored once per set |
| 21 | `scoring_weight_set` | `lot_score` | `weight_set_id` | 1 : many | cascade | A set produces many scores |
| 22 | `segment_rule` | `lot_score` | `segment_code` | 1 : many | restrict | A segment classifies many lots |

Cascade is used deliberately and narrowly: deleting a parking lot removes everything that describes, measures or scores that lot, because none of those rows mean anything without it. Dimension and configuration tables restrict instead, so a locality or a funnel stage cannot be deleted while anything still refers to it. `scripts/validate_schema.sh` proves this behaviour by deleting a lot and confirming that its competition row, daily facts, lead, funnel events and scores all disappear with it.

---

## Key design decisions

**Owner is an entity, not a lot attribute.** The original field list placed owner characteristics in a per-lot table, which duplicated `owner_type` between two tables and made a common BD situation inexpressible: one operator controlling four lots in the same locality, where a single negotiation unlocks all four. Promoting `owners` removes the duplication and turns operator-level analysis into a simple `GROUP BY`.

**Locality is a dimension, not a text column.** Four of the sixteen business questions are asked at locality grain. Storing the locality as free text on `parking_lots` would have made those questions depend on string matching, and would have left nowhere to record locality attributes such as metro presence and land-use character.

**Performance is split across two grains.** A single date-and-hour performance table would have meant roughly 1.05 million synthetic rows to answer questions asked almost entirely at daily or typical-hour grain. `fact_lot_daily` carries the dated series at about 43,800 rows; `fact_lot_hourly_profile` carries a typical-week shape at 48 rows per lot. Peak-hour analysis survives intact and the dataset stays small enough to inspect by hand when a number looks wrong.

**Deal terms are separated from owner posture.** Commission and onboarding cost are negotiated per site; willingness to digitise and contract flexibility are properties of the operator. Keeping them in `lot_acquisition_terms` and `owners` respectively means neither has to be repeated.

**Funnel stages are an ordered ladder; losses are not stages.** Encoding loss reasons as funnel stages would have destroyed the stage ordering and made drop-off analysis meaningless. `outreach.furthest_stage_id` records how far a lead got, `pipeline_status` records whether it is alive, and `lost_reason` records why it died.

**Weight set identity is part of every scoring primary key.** This is what makes sensitivity analysis non-destructive. Running the model under `DEMAND_LED` does not overwrite `BASELINE_V1`; both sit in `lot_score` simultaneously and can be compared with a self-join. The alternative — recomputing and overwriting — would make rank-stability analysis impossible after the fact.

---

## Business rules enforced in the schema

`data_lineage` is a metadata table with no business foreign keys. Its composite key is `(table_name, column_name)`, and it records lineage type, source, reference, methodology and business purpose for every source field.

These are constraints a reader can verify by opening the DDL, not claims made in prose.

**Geography.** Latitude must fall between 28.30 and 28.95 and longitude between 76.80 and 77.60, on both `parking_lots` and `existing_network_sites`. Coordinates outside Delhi NCR are rejected at write time rather than discovered in a report later.

**Operating hours.** A lot flagged `is_24x7` must have null opening and closing times; a lot not so flagged must have both. `closes_at` is deliberately permitted to be earlier than `opens_at`, because a lot trading from 18:00 to 02:00 is legitimate and a naive ordering constraint would wrongly reject it.

**Radius nesting.** `competitor_count_1km` can never be less than `competitor_count_500m`. This catches a specific and silent ETL bug: computing the two counts in separate passes and letting them contradict each other.

**Competitive presence coherence.** If no competitors exist within a kilometre, there can be no nearest-competitor distance and no competitor average price. If competitors do exist, a nearest distance is mandatory.

**Subset relationships in the daily facts.** Platform bookings cannot exceed total vehicle entries, and cancellations cannot exceed bookings. Average occupancy cannot exceed the same day's peak. Note what is deliberately *not* constrained: daily entries may freely exceed `capacity_cars`, because a 100-bay lot genuinely serves several hundred vehicles a day through turnover. Only concurrent occupancy is capped, which is why occupancy is modelled as a rate and entries as a count.

**Pipeline coherence.** A lost lead must carry a loss reason and a live one must not. A won lead must have a conversion date and nothing else may. Contact attempts and a first-contact date imply each other. A conversion cannot predate first contact.

**Provenance integrity.** Only rows sourced from OpenStreetMap may carry an `osm_id`, so a synthetic record cannot masquerade as extracted data.

**Single default weighting.** A partial unique index permits at most one `scoring_weight_set` to be flagged default, so a report cannot silently pick a different weighting than intended.

**One lead per lot, one stage entry per lead.** Enforced by unique constraints, which keeps funnel conversion denominators honest.

---

## Rules that cannot live in the schema

Two important invariants span rows and therefore cannot be `CHECK` constraints, since PostgreSQL evaluates those per row. Rather than hide the logic in a trigger, both are enforced in the data-quality layer where they are visible:

The weights within a scoring weight set must sum to exactly 1.0 — rule **DQ-020** in `sql/data_quality/dq_checks.sql`. A stored `acquisition_score` must reconcile with the sum of its `weighted_contribution` components within a tolerance of 0.05 — rule **DQ-021**. That second rule is what makes the redundancy between `lot_score` and `lot_dimension_score` a *verified* redundancy rather than a latent inconsistency.

A third spans rows in a subtler way: the funnel stages recorded for a lead must be contiguous from stage 1 up to its `furthest_stage_id`, checked by rules **DQ-030** and **DQ-031**.

---

## Verification

The structural integrity of this model is machine-checked rather than asserted. `python/etl/validate_ddl.py` confirms every primary key, all 22 foreign keys, dependency order and teardown completeness. It currently reports 21 tables, 181 columns, 22 foreign keys and 101 CHECK expressions with no failures.

Semantic verification — that PostgreSQL accepts the DDL and that the constraints actually reject bad input — is the job of `scripts/validate_schema.sh`, which must be run against a live server.
