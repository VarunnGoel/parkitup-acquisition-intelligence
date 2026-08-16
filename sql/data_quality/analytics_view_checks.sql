-- analytics rerunnable quality report. Constraints prevent many invalid rows;
-- these queries report cross-table, duplicate, missing, and funnel issues.
SET search_path TO parkitup, public;
WITH checks AS (
 SELECT 'orphan_location_demand' AS check_name, COUNT(*) AS issue_count FROM location_demand d LEFT JOIN parking_lots p USING(parking_id) WHERE p.parking_id IS NULL
 UNION ALL SELECT 'orphan_competition', COUNT(*) FROM competition c LEFT JOIN parking_lots p USING(parking_id) WHERE p.parking_id IS NULL
 UNION ALL SELECT 'orphan_performance', COUNT(*) FROM fact_lot_daily f LEFT JOIN parking_lots p USING(parking_id) WHERE p.parking_id IS NULL
 UNION ALL SELECT 'orphan_owner_reference', COUNT(*) FROM parking_lots p LEFT JOIN owners o USING(owner_id) WHERE o.owner_id IS NULL
 UNION ALL SELECT 'orphan_outreach', COUNT(*) FROM outreach o LEFT JOIN parking_lots p USING(parking_id) WHERE p.parking_id IS NULL
 UNION ALL SELECT 'duplicate_parking_ids', COUNT(*) FROM (SELECT parking_id FROM parking_lots GROUP BY parking_id HAVING COUNT(*)>1) x
 UNION ALL SELECT 'duplicate_locality_lot_names', COUNT(*) FROM (SELECT locality_id,LOWER(lot_name) FROM parking_lots GROUP BY locality_id,LOWER(lot_name) HAVING COUNT(*)>1) x
 UNION ALL SELECT 'duplicate_daily_performance', COUNT(*) FROM (SELECT parking_id,activity_date FROM fact_lot_daily GROUP BY parking_id,activity_date HAVING COUNT(*)>1) x
 UNION ALL SELECT 'invalid_negative_prices', COUNT(*) FROM parking_lots WHERE hourly_rate_inr < 0
 UNION ALL SELECT 'invalid_negative_revenue', COUNT(*) FROM fact_lot_daily WHERE gross_parking_revenue_inr < 0
 UNION ALL SELECT 'invalid_occupancy', COUNT(*) FROM fact_lot_daily WHERE avg_occupancy_rate NOT BETWEEN 0 AND 1 OR peak_occupancy_rate NOT BETWEEN 0 AND 1
 UNION ALL SELECT 'invalid_capacity', COUNT(*) FROM parking_lots WHERE capacity_cars < 5 OR capacity_cars > 5000
 UNION ALL SELECT 'invalid_performance_dates', COUNT(*) FROM fact_lot_daily WHERE activity_date > CURRENT_DATE
 UNION ALL SELECT 'impossible_funnel_state', COUNT(*) FROM outreach o JOIN dim_funnel_stage s ON s.stage_id=o.furthest_stage_id WHERE (o.pipeline_status='Won') <> s.is_success_stage
 UNION ALL SELECT 'missing_critical_lot_fields', COUNT(*) FROM parking_lots WHERE lot_name IS NULL OR locality_id IS NULL OR owner_id IS NULL OR capacity_cars IS NULL OR hourly_rate_inr IS NULL
 UNION ALL SELECT 'missing_competitor_capacity', COUNT(*) FROM competition WHERE competitor_total_capacity_1km IS NULL
 UNION ALL SELECT 'missing_competitor_price', COUNT(*) FROM competition WHERE competitor_count_1km > 0 AND competitor_avg_hourly_rate_inr IS NULL
 UNION ALL SELECT 'missing_first_contact_for_identified_leads', COUNT(*) FROM outreach WHERE first_contact_date IS NULL
)
SELECT *, CASE WHEN issue_count=0 THEN 'PASS' ELSE 'REVIEW' END AS status
FROM checks ORDER BY status DESC, check_name;
