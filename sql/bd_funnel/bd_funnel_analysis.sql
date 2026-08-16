-- Q32-Q40: funnel conversion, source/owner performance, cycle time and lead traits.
SET search_path TO parkitup, public;
SELECT * FROM vw_bd_funnel ORDER BY stage_order;

-- The implemented funnel has no INTERESTED stage. This is a labeled proxy,
-- not a replacement stage: interest level >= 3 among contacted leads.
SELECT COUNT(*) FILTER (WHERE contact_attempts > 0) AS contacted,
       COUNT(*) FILTER (WHERE contact_attempts > 0 AND owner_interest_level >= 3) AS interested_proxy,
       ROUND(COUNT(*) FILTER (WHERE contact_attempts > 0 AND owner_interest_level >= 3)::numeric /
             NULLIF(COUNT(*) FILTER (WHERE contact_attempts > 0), 0) * 100, 2) AS contact_to_interest_proxy_pct
FROM outreach;

SELECT o.lead_source, COUNT(*) AS leads,
       COUNT(*) FILTER (WHERE o.pipeline_status='Won') AS acquired,
       ROUND(COUNT(*) FILTER (WHERE o.pipeline_status='Won')::numeric / COUNT(*) * 100, 2) AS acquisition_rate_pct,
       ROUND(AVG(o.days_to_conversion) FILTER (WHERE o.pipeline_status='Won'), 1) AS avg_days_to_acquisition
FROM outreach o GROUP BY o.lead_source ORDER BY acquisition_rate_pct DESC, leads DESC;

SELECT ow.owner_type, COUNT(*) AS leads,
       ROUND(AVG(p.capacity_cars), 1) AS avg_capacity,
       ROUND(AVG((ow.digital_payment_enabled)::int) * 100, 2) AS digital_payment_pct,
       ROUND(AVG((o.pipeline_status='Won')::int) * 100, 2) AS acquisition_rate_pct,
       ROUND(AVG(o.days_to_conversion) FILTER (WHERE o.pipeline_status='Won'), 1) AS avg_days_to_acquisition
FROM outreach o JOIN parking_lots p USING (parking_id) JOIN owners ow USING (owner_id)
GROUP BY ow.owner_type ORDER BY acquisition_rate_pct DESC;

WITH lead_features AS (
 SELECT o.*, p.capacity_cars, ow.digital_payment_enabled, ow.management_system,
        NTILE(4) OVER (ORDER BY p.capacity_cars) AS capacity_quartile
 FROM outreach o JOIN parking_lots p USING (parking_id) JOIN owners ow USING (owner_id)
)
SELECT capacity_quartile, digital_payment_enabled, COUNT(*) AS leads,
       ROUND(AVG((pipeline_status='Won')::int) * 100, 2) AS acquisition_rate_pct
FROM lead_features GROUP BY capacity_quartile, digital_payment_enabled
ORDER BY capacity_quartile, digital_payment_enabled;
