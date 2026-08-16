# Data Profile

Generated from the deterministic source build using seed `20260815` and the public source snapshot observed on `2026-08-16`. This report profiles the data layer only; it does not rank acquisition opportunities.

## Dataset size

| Dataset | Rows |
|---|---|
| Parking lots | 120 |
| Localities | 17 |
| Owners | 72 |
| Daily performance records | 43800 |
| Hourly profile records | 5760 |
| Outreach leads | 120 |
| Outreach stage events | 385 |
| Hypothetical network sites | 14 |

## Geographic coverage

Connaught Place, Nehru Place, Saket, Dwarka Sector 21, Rajouri Garden, Karol Bagh, Lajpat Nagar, Vasant Kunj, DLF Cyber City, Sector 29 Gurugram, Golf Course Road, Udyog Vihar, Noida Sector 18, Noida Sector 62, Botanical Garden Noida, Indirapuram, Faridabad Sector 15

All candidate coordinates are sourced from OpenStreetMap. Market type and population-density bands are explicit analyst assumptions recorded in the field lineage table.

## Parking-type coverage

| Parking type | Lots |
|---|---|
| Surface Lot | 47 |
| Office Complex | 16 |
| Basement | 15 |
| Multi-Level (MLCP) | 15 |
| On-Street Authorised | 15 |
| Metro Station Parking | 6 |
| Mall Parking | 6 |

## Row-level provenance

| Record source | Lots |
|---|---|
| public_osm | 120 |

Row-level public provenance applies to the parking identity and coordinates, not automatically to every attribute. Capacity, price, hours and amenity provenance are separately labelled on `parking_lots`.

## Basic distributions

| Metric | min | p25 | median | mean | p75 | max |
|---|---|---|---|---|---|---|
| Capacity (cars) | 27.00 | 94.50 | 149.00 | 197.38 | 269.75 | 706.00 |
| Hourly price (INR) | 15.00 | 35.00 | 45.00 | 50.67 | 60.00 | 125.00 |
| Average occupancy | 0.04 | 0.24 | 0.32 | 0.34 | 0.42 | 0.93 |
| Peak occupancy | 0.10 | 0.39 | 0.48 | 0.49 | 0.58 | 0.99 |
| Daily bookings | 0.00 | 18.00 | 44.00 | 82.63 | 93.00 | 1141.00 |
| Daily revenue (INR) | 246.27 | 15758.99 | 30283.83 | 50823.37 | 64821.54 | 381774.13 |
| Competitors within 1km | 0.00 | 3.00 | 5.00 | 6.65 | 10.00 | 29.00 |

## Missing values and duplicates

| Table | Rows | Missing cells | Duplicate full rows |
|---|---|---|---|
| dim_locality | 17 | 0 | 0 |
| owners | 72 | 0 | 0 |
| parking_lots | 120 | 110 | 0 |
| location_demand | 120 | 0 | 0 |
| competition | 120 | 132 | 0 |
| lot_acquisition_terms | 120 | 0 | 0 |
| existing_network_sites | 14 | 0 | 0 |
| fact_lot_daily | 43800 | 0 | 0 |
| fact_lot_hourly_profile | 5760 | 0 | 0 |
| outreach | 120 | 324 | 0 |
| outreach_events | 385 | 0 | 0 |

Expected nullable fields account for most missing cells: monthly passes, unpublished competitor capacities/prices, first-contact/conversion fields for early-stage leads, and loss reasons for non-lost leads.

## Automated data quality

- Python structural/business-rule checks: 30 executed, 0 failed.
- Business-logic tendency checks: 6 executed, 0 failed.
- Full check outputs: `validation/python_data_quality_results.csv` and `validation/business_logic_results.csv`.

| rule_id | dataset | description | violations | status |
|---|---|---|---|---|
| PY-001 | parking_lots | parking_id is unique | 0 | PASS |
| PY-002 | parking_lots | lot_code is unique | 0 | PASS |
| PY-003 | parking_lots | capacity is between 10 and 2000 | 0 | PASS |
| PY-004 | parking_lots | hourly price is between 0 and 500 | 0 | PASS |
| PY-005 | parking_lots | coordinates are inside the configured NCR box | 0 | PASS |
| PY-006 | parking_lots | every lot references a valid locality | 0 | PASS |
| PY-007 | parking_lots | all public OSM lots carry an OSM id and source reference | 0 | PASS |
| PY-008 | parking_lots | no approximate duplicate coordinates at six decimal places | 0 | PASS |
| PY-010 | location_demand | one demand row exists per lot | 0 | PASS |
| PY-011 | location_demand | all POI counts and distances are non-negative | 0 | PASS |
| PY-012 | competition | one competition row exists per lot | 0 | PASS |
| PY-013 | competition | 500m count never exceeds 1km count | 0 | PASS |
| PY-014 | competition | competition counts and distances are non-negative | 0 | PASS |
| PY-015 | competition | aggregator count is a subset of competitors | 0 | PASS |
| PY-020 | fact_lot_daily | daily primary key is unique | 0 | PASS |
| PY-021 | fact_lot_daily | every lot has exactly the full observation window | 0 | PASS |
| PY-022 | fact_lot_daily | occupancy is within 0-1 and mean does not exceed peak | 0 | PASS |
| PY-023 | fact_lot_daily | bookings and cancellations are logical subsets | 0 | PASS |
| PY-024 | fact_lot_daily | revenue is non-negative and non-zero when paid activity exists | 0 | PASS |
| PY-025 | fact_lot_hourly_profile | every lot has exactly 48 hourly profile rows | 0 | PASS |
| PY-026 | fact_lot_hourly_profile | hourly keys are unique and values valid | 0 | PASS |
| PY-030 | owners | owner codes and ids are unique | 0 | PASS |
| PY-031 | owners | owner readiness ordinals are within 1-5 | 0 | PASS |
| PY-032 | lot_acquisition_terms | one non-negative, valid terms row exists per lot | 0 | PASS |
| PY-040 | outreach | one outreach row exists per lot | 0 | PASS |
| PY-041 | outreach | won status and conversion fields are consistent | 0 | PASS |
| PY-042 | outreach | lost status and lost reason are consistent | 0 | PASS |
| PY-043 | outreach | contact attempts and contact date are consistent | 0 | PASS |
| PY-044 | outreach_events | events are contiguous from stage 1 through the furthest stage | 0 | PASS |
| PY-045 | outreach_events | event dates are non-decreasing within each lead | 0 | PASS |

## Business-logic tendencies

These checks test whether the simulation behaves plausibly without requiring perfect correlation.

| rule_id | description | observed_value | status |
|---|---|---|---|
| BL-001 | Demand proxy has a positive, non-perfect tendency with occupancy | correlation=0.7917; expected 0.18 to 0.92 | PASS |
| BL-002 | Higher tariff contributes to revenue but does not determine it | correlation=0.4309; expected 0.05 to 0.85 | PASS |
| BL-003 | Capacity helps revenue without becoming a perfect proxy | correlation=0.6770; expected 0.18 to 0.92 | PASS |
| BL-004 | Competition does not create an implausibly strong positive occupancy effect | correlation=0.2734; expected at most 0.55 | PASS |
| BL-005 | Owner readiness tends to improve funnel progress without determining it | correlation=0.3317; expected 0.12 to 0.88 | PASS |
| BL-006 | Observed owner interest tends to improve funnel progress | correlation=0.2259; expected 0.12 to 0.92 | PASS |

## PostgreSQL execution

The full cached pipeline loaded the generated tables into PostgreSQL and ran the SQL rule catalog.

| Table | Loaded rows |
|---|---|
| competition | 120 |
| data_lineage | 117 |
| dim_locality | 17 |
| existing_network_sites | 14 |
| fact_lot_daily | 43800 |
| fact_lot_hourly_profile | 5760 |
| location_demand | 120 |
| lot_acquisition_terms | 120 |
| outreach | 120 |
| outreach_events | 385 |
| owners | 72 |
| parking_lots | 120 |

| severity | status | Rules |
|---|---|---|
| ERROR | PASS | 20 |
| WARN | FAIL | 1 |
| WARN | PASS | 14 |

Non-passing warnings: DQ-024: 120 - Lots present in the model but never scored under the default weight set. The unscored-lot warning is expected until the scoring engine; it is not suppressed or relabelled as a pass.

| Integrity check | Orphans |
|---|---|
| orphan_daily_date | 0 |
| orphan_daily_lot | 0 |
| orphan_event_lead | 0 |
| orphan_lot_locality | 0 |
| orphan_lot_owner | 0 |
