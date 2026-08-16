-- Returns zero rows when all analytics assertions pass.
SET search_path TO parkitup, public;
WITH assertions AS (
 SELECT 'P4-01 top-ranked lot exists' AS test, (SELECT COUNT(*)=1 FROM vw_bd_acquisition_targets WHERE rank=1) AS passed
 UNION ALL SELECT 'P4-02 scores within 0-100', NOT EXISTS (SELECT 1 FROM vw_bd_acquisition_targets WHERE acquisition_score NOT BETWEEN 0 AND 100)
 UNION ALL SELECT 'P4-03 every lot has a rank', (SELECT COUNT(*) FROM vw_bd_acquisition_targets)=(SELECT COUNT(*) FROM parking_lots)
 UNION ALL SELECT 'P4-04 every locality summarized', (SELECT COUNT(*) FROM vw_locality_summary)=(SELECT COUNT(*) FROM dim_locality)
 UNION ALL SELECT 'P4-05 no duplicate target parking IDs', NOT EXISTS (SELECT 1 FROM vw_bd_acquisition_targets GROUP BY parking_id HAVING COUNT(*)>1)
 UNION ALL SELECT 'P4-06 won leads reached success stage', NOT EXISTS (
   SELECT 1 FROM outreach o JOIN dim_funnel_stage s ON s.stage_id=o.furthest_stage_id
   WHERE o.pipeline_status='Won' AND NOT s.is_success_stage)
 UNION ALL SELECT 'P4-07 benchmark grain is one row per lot', (SELECT COUNT(*) FROM vw_parking_benchmarks)=(SELECT COUNT(DISTINCT parking_id) FROM vw_parking_benchmarks)
)
SELECT * FROM assertions WHERE NOT passed;
