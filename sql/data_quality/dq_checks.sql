-- =====================================================================
-- dq_checks.sql : data quality rule catalogue, executable
--
-- HOW TO RUN
--   psql -d parkitup -v ON_ERROR_STOP=1 -f sql/data_quality/dq_checks.sql
--
-- OUTPUT SHAPE
--   rule_id | severity | table_name | rule_description | violations | status
--   One row per rule, always. A rule that finds nothing still reports PASS,
--   because "the check ran and found nothing" and "the check never ran" are
--   very different states and a report that only shows failures cannot tell
--   them apart.
--
-- DIVISION OF LABOUR - the important design point
--   A large share of the rules in the brief are already enforced by CHECK
--   constraints in database/schema/, so bad data cannot be inserted at all.
--   Those are listed under "ENFORCED AT WRITE TIME" below and are not
--   re-tested here. This file covers only what a row-scoped CHECK constraint
--   fundamentally cannot express:
--     - cross-row invariants   (weights within a set must sum to 1.0)
--     - cross-table invariants (every lot needs a location_demand row)
--     - reconciliation         (stored total vs sum of its parts)
--     - distributional smells  (all-zero series, implausible revenue)
--
-- ENFORCED AT WRITE TIME BY CHECK CONSTRAINTS - deliberately not re-tested
--   negative prices .................. parking_lots.hourly_rate_inr >= 0
--   occupancy above 100% ............. NUMERIC(5,4) + BETWEEN 0 AND 1
--   invalid coordinates .............. NCR bounding box on lat/long
--   impossible capacities ............ capacity_cars BETWEEN 10 AND 2000
--   invalid operating hours .......... ck_lot_hours_consistent
--   bookings exceeding entries ....... ck_daily_bookings_subset_of_entries
--   cancellations exceeding bookings . ck_daily_cancellations_subset_of_bookings
--   mean occupancy above peak ........ ck_daily_avg_not_above_peak
--   competitor radius nesting ........ ck_competitor_radius_nesting
--   broken foreign keys .............. FK constraints throughout
--   lost lead with no reason ......... ck_outreach_lost_reason_iff_lost
--   conversion before first contact .. ck_outreach_conversion_after_contact
--
-- SCOPE NOTE
--   Rules touching source tables return PASS trivially while those tables are
--   empty. That is intended: the framework is installed before the data, so
--   source gets immediate feedback rather than retrofitted checks.
-- =====================================================================
SET search_path TO parkitup, public;

WITH checks AS (

-- === COMPLETENESS: the 1:1 companions of parking_lots ================
SELECT 'DQ-001' AS rule_id, 'ERROR' AS severity, 'location_demand' AS table_name,
       'Every parking lot must have exactly one location_demand row' AS rule_description,
       COUNT(*) AS violations
  FROM parking_lots pl
  LEFT JOIN location_demand ld ON ld.parking_id = pl.parking_id
 WHERE ld.parking_id IS NULL

UNION ALL
SELECT 'DQ-002', 'ERROR', 'competition',
       'Every parking lot must have exactly one competition row',
       COUNT(*)
  FROM parking_lots pl
  LEFT JOIN competition c ON c.parking_id = pl.parking_id
 WHERE c.parking_id IS NULL

UNION ALL
SELECT 'DQ-003', 'ERROR', 'lot_acquisition_terms',
       'Every parking lot must have exactly one lot_acquisition_terms row',
       COUNT(*)
  FROM parking_lots pl
  LEFT JOIN lot_acquisition_terms t ON t.parking_id = pl.parking_id
 WHERE t.parking_id IS NULL

UNION ALL
SELECT 'DQ-004', 'WARN', 'outreach',
       'Every parking lot should have an outreach lead record',
       COUNT(*)
  FROM parking_lots pl
  LEFT JOIN outreach o ON o.parking_id = pl.parking_id
 WHERE o.parking_id IS NULL

-- === DUPLICATES ======================================================
UNION ALL
SELECT 'DQ-005', 'ERROR', 'parking_lots',
       'lot_code must be unique (UNIQUE constraint backstop)',
       COALESCE(SUM(cnt - 1), 0)::BIGINT
  FROM (SELECT lot_code, COUNT(*) AS cnt FROM parking_lots
         GROUP BY lot_code HAVING COUNT(*) > 1) d

UNION ALL
SELECT 'DQ-006', 'WARN', 'parking_lots',
       'Lots sharing coordinates to 4dp (~11m) are probably the same physical lot entered twice',
       COALESCE(SUM(cnt - 1), 0)::BIGINT
  FROM (SELECT ROUND(latitude, 4) AS la, ROUND(longitude, 4) AS lo, COUNT(*) AS cnt
          FROM parking_lots GROUP BY 1, 2 HAVING COUNT(*) > 1) d

UNION ALL
SELECT 'DQ-007', 'WARN', 'parking_lots',
       'Identical lot_name within the same locality suggests a duplicate record',
       COALESCE(SUM(cnt - 1), 0)::BIGINT
  FROM (SELECT locality_id, LOWER(TRIM(lot_name)) AS nm, COUNT(*) AS cnt
          FROM parking_lots GROUP BY 1, 2 HAVING COUNT(*) > 1) d

-- === PROVENANCE INTEGRITY ============================================
UNION ALL
SELECT 'DQ-008', 'ERROR', 'parking_lots',
       'OSM-sourced lots must carry an osm_id for traceability',
       COUNT(*)
  FROM parking_lots
 WHERE record_source = 'public_osm' AND osm_id IS NULL

UNION ALL
SELECT 'DQ-009', 'WARN', 'parking_lots',
       'Synthetic lots should not exceed 60% of the population, or public grounding is lost',
       CASE WHEN COUNT(*) = 0 THEN 0
            WHEN COUNT(*) FILTER (WHERE record_source = 'synthetic')::NUMERIC
                 / COUNT(*) > 0.60 THEN 1 ELSE 0 END
  FROM parking_lots

-- === FACT COVERAGE AND GRAIN =========================================
UNION ALL
SELECT 'DQ-010', 'WARN', 'fact_lot_daily',
       'Lots with no daily performance rows at all',
       COUNT(*)
  FROM parking_lots pl
 WHERE NOT EXISTS (SELECT 1 FROM fact_lot_daily f WHERE f.parking_id = pl.parking_id)

UNION ALL
SELECT 'DQ-011', 'ERROR', 'fact_lot_hourly_profile',
       'Hourly profile must be complete: exactly 48 rows per lot (2 day types x 24 hours)',
       COUNT(*)
  FROM (SELECT parking_id, COUNT(*) AS cnt
          FROM fact_lot_hourly_profile GROUP BY parking_id HAVING COUNT(*) <> 48) d

UNION ALL
SELECT 'DQ-012', 'WARN', 'fact_lot_daily',
       'Gaps in the daily series: lots whose row count differs from their observed date span',
       COUNT(*)
  FROM (SELECT parking_id,
               COUNT(*) AS rows_present,
               (MAX(activity_date) - MIN(activity_date) + 1) AS span_days
          FROM fact_lot_daily
         GROUP BY parking_id
        HAVING COUNT(*) <> (MAX(activity_date) - MIN(activity_date) + 1)) d

-- === PLAUSIBILITY: silent generator failures ==========================
UNION ALL
SELECT 'DQ-013', 'WARN', 'fact_lot_daily',
       'Lots with zero entries on every observed day - a dead lot or a broken generator',
       COUNT(*)
  FROM (SELECT parking_id FROM fact_lot_daily
         GROUP BY parking_id HAVING SUM(vehicle_entries) = 0) d

UNION ALL
SELECT 'DQ-014', 'ERROR', 'fact_lot_daily',
       'Revenue recorded as zero on days with vehicle entries and a non-zero tariff',
       COUNT(*)
  FROM fact_lot_daily f
  JOIN parking_lots pl ON pl.parking_id = f.parking_id
 WHERE f.gross_parking_revenue_inr = 0
   AND f.vehicle_entries > 0
   AND pl.hourly_rate_inr > 0

UNION ALL
SELECT 'DQ-015', 'WARN', 'fact_lot_daily',
       'Revenue outside 30%-300% of entries x duration x tariff (discounts and passes widen the band, but not this far)',
       COUNT(*)
  FROM fact_lot_daily f
  JOIN parking_lots pl ON pl.parking_id = f.parking_id
 WHERE pl.hourly_rate_inr > 0
   AND f.vehicle_entries > 0
   AND ( f.gross_parking_revenue_inr
           < 0.30 * f.vehicle_entries * f.avg_park_duration_hours * pl.hourly_rate_inr
      OR f.gross_parking_revenue_inr
           > 3.00 * f.vehicle_entries * f.avg_park_duration_hours * pl.hourly_rate_inr )

UNION ALL
SELECT 'DQ-016', 'WARN', 'fact_lot_daily',
       'Peak occupancy at exactly 100% on more than half a lot''s days - suggests a clipped simulation',
       COUNT(*)
  FROM (SELECT parking_id
          FROM fact_lot_daily
         GROUP BY parking_id
        HAVING COUNT(*) > 0
           AND COUNT(*) FILTER (WHERE peak_occupancy_rate >= 1.0)::NUMERIC
               / COUNT(*) > 0.50) d

UNION ALL
SELECT 'DQ-017', 'WARN', 'competition',
       'Published competitor capacity within 1km recorded as zero while competitors are present',
       COUNT(*)
  FROM competition
 WHERE competitor_count_1km > 0
   AND competitor_total_capacity_1km = 0

-- === TEMPORAL SANITY =================================================
UNION ALL
SELECT 'DQ-018', 'ERROR', 'outreach',
       'Conversion dated in the future',
       COUNT(*)
  FROM outreach
 WHERE conversion_date > CURRENT_DATE

UNION ALL
SELECT 'DQ-019', 'ERROR', 'outreach_events',
       'Funnel event dated before the lead''s first contact',
       COUNT(*)
  FROM outreach_events e
  JOIN outreach o ON o.lead_id = e.lead_id
 WHERE o.first_contact_date IS NOT NULL
   AND e.event_date < o.first_contact_date
   AND e.stage_id > 1

-- === SCORING CONFIGURATION ===========================================
UNION ALL
SELECT 'DQ-020', 'ERROR', 'scoring_weight',
       'Weights within a weight set must sum to exactly 1.0 (cannot be a CHECK - spans rows)',
       COUNT(*)
  FROM (SELECT weight_set_id FROM scoring_weight
         GROUP BY weight_set_id HAVING ABS(SUM(weight) - 1.0) > 0.0001) d

UNION ALL
SELECT 'DQ-021', 'ERROR', 'lot_score',
       'acquisition_score must reconcile with SUM(weighted_contribution) within 0.05',
       COUNT(*)
  FROM lot_score s
  JOIN (SELECT parking_id, weight_set_id, SUM(weighted_contribution) AS total
          FROM lot_dimension_score GROUP BY 1, 2) c
    ON c.parking_id = s.parking_id AND c.weight_set_id = s.weight_set_id
 WHERE ABS(s.acquisition_score - c.total) > 0.05

UNION ALL
SELECT 'DQ-022', 'ERROR', 'lot_dimension_score',
       'Every scored lot must have all five pillar components',
       COUNT(*)
  FROM (SELECT parking_id, weight_set_id, COUNT(*) AS cnt
          FROM lot_dimension_score
         GROUP BY 1, 2 HAVING COUNT(*) <> 5) d

UNION ALL
SELECT 'DQ-023', 'ERROR', 'lot_dimension_score',
       'weight_applied must match the weight set it claims to use',
       COUNT(*)
  FROM lot_dimension_score lds
  JOIN scoring_weight sw
    ON sw.weight_set_id = lds.weight_set_id
   AND sw.dimension_code = lds.dimension_code
 WHERE ABS(lds.weight_applied - sw.weight) > 0.0001

UNION ALL
SELECT 'DQ-024', 'WARN', 'lot_score',
       'Lots present in the model but never scored under the default weight set',
       COUNT(*)
  FROM parking_lots pl
 WHERE EXISTS (SELECT 1 FROM scoring_weight_set WHERE is_default)
   AND NOT EXISTS (
        SELECT 1 FROM lot_score s
          JOIN scoring_weight_set ws ON ws.weight_set_id = s.weight_set_id
         WHERE s.parking_id = pl.parking_id AND ws.is_default)

-- === BD FUNNEL INTEGRITY =============================================
UNION ALL
SELECT 'DQ-030', 'ERROR', 'outreach_events',
       'Funnel stages must be contiguous from 1: event count must equal furthest_stage_id',
       COUNT(*)
  FROM (SELECT o.lead_id
          FROM outreach o
          JOIN outreach_events e ON e.lead_id = o.lead_id
         GROUP BY o.lead_id, o.furthest_stage_id
        HAVING COUNT(*) <> o.furthest_stage_id) d

UNION ALL
SELECT 'DQ-031', 'ERROR', 'outreach',
       'furthest_stage_id must equal the maximum stage present in outreach_events',
       COUNT(*)
  FROM outreach o
  JOIN (SELECT lead_id, MAX(stage_id) AS max_stage
          FROM outreach_events GROUP BY lead_id) e
    ON e.lead_id = o.lead_id
 WHERE e.max_stage <> o.furthest_stage_id

UNION ALL
SELECT 'DQ-032', 'ERROR', 'outreach',
       'A Won lead must have reached the ONBOARDED stage, and only a Won lead may have',
       COUNT(*)
  FROM outreach o
  JOIN dim_funnel_stage fs ON fs.stage_id = o.furthest_stage_id
 WHERE (o.pipeline_status = 'Won'  AND NOT fs.is_success_stage)
    OR (o.pipeline_status <> 'Won' AND      fs.is_success_stage)

UNION ALL
SELECT 'DQ-033', 'WARN', 'outreach',
       'Lead past the Contacted stage with no recorded contact attempts',
       COUNT(*)
  FROM outreach
 WHERE furthest_stage_id >= 2 AND contact_attempts = 0

UNION ALL
SELECT 'DQ-034', 'WARN', 'outreach',
       'Lead reached Documents Collected but documents_available is false',
       COUNT(*)
  FROM outreach
 WHERE furthest_stage_id >= 6 AND documents_available = FALSE

UNION ALL
SELECT 'DQ-035', 'ERROR', 'outreach_events',
       'Every outreach lead must have at least its Identified event',
       COUNT(*)
  FROM outreach o
 WHERE NOT EXISTS (SELECT 1 FROM outreach_events e WHERE e.lead_id = o.lead_id)

UNION ALL
SELECT 'DQ-036', 'ERROR', 'outreach_events',
       'Funnel event dates must be non-decreasing in stage order',
       COUNT(*)
  FROM (
        SELECT lead_id, stage_id, event_date,
               LAG(event_date) OVER (PARTITION BY lead_id ORDER BY stage_id) AS prior_date
          FROM outreach_events
       ) e
 WHERE prior_date IS NOT NULL AND event_date < prior_date

-- === REFERENCE INTEGRITY =============================================
UNION ALL
SELECT 'DQ-040', 'WARN', 'dim_locality',
       'Localities with no parking lots - dead reference rows',
       COUNT(*)
  FROM dim_locality dl
 WHERE NOT EXISTS (SELECT 1 FROM parking_lots pl WHERE pl.locality_id = dl.locality_id)

UNION ALL
SELECT 'DQ-041', 'WARN', 'owners',
       'Owners with no parking lots - dead reference rows',
       COUNT(*)
  FROM owners o
 WHERE NOT EXISTS (SELECT 1 FROM parking_lots pl WHERE pl.owner_id = o.owner_id)

UNION ALL
SELECT 'DQ-042', 'ERROR', 'dim_date',
       'Calendar must be gap-free across its own span',
       CASE WHEN COUNT(*) = 0 THEN 0
            WHEN COUNT(*) <> (MAX(activity_date) - MIN(activity_date) + 1)
            THEN 1 ELSE 0 END
  FROM dim_date

UNION ALL
SELECT 'DQ-043', 'ERROR', 'data_lineage',
       'Every source database column must have a field-level lineage record',
       COUNT(*)
 FROM information_schema.columns c
 WHERE c.table_schema = 'parkitup'
   AND EXISTS (SELECT 1 FROM parking_lots)
   AND c.table_name IN (
       'dim_locality','owners','parking_lots','location_demand','competition',
       'lot_acquisition_terms','existing_network_sites','fact_lot_daily',
       'fact_lot_hourly_profile','outreach','outreach_events'
   )
   AND NOT EXISTS (
       SELECT 1 FROM data_lineage dl
        WHERE dl.table_name = c.table_name AND dl.column_name = c.column_name
   )

)
SELECT rule_id,
       severity,
       table_name,
       rule_description,
       violations,
       CASE WHEN violations = 0 THEN 'PASS' ELSE 'FAIL' END AS status
  FROM checks
 ORDER BY CASE WHEN violations > 0 THEN 0 ELSE 1 END,   -- failures first
          CASE severity WHEN 'ERROR' THEN 0 ELSE 1 END,
          rule_id;
