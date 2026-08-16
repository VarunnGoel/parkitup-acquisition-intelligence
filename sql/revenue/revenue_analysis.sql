-- Q14-Q18: absolute economics versus efficiency and pricing candidates.
SET search_path TO parkitup, public;
WITH ranked AS (
 SELECT p.*,
   CUME_DIST() OVER (ORDER BY average_price_inr) AS price_pct,
   CUME_DIST() OVER (ORDER BY avg_daily_revenue_inr) AS revenue_pct,
   CUME_DIST() OVER (ORDER BY avg_occupancy_pct) AS occupancy_pct
 FROM vw_parking_performance_summary p
)
SELECT parking_id, parking_name, locality_name, capacity, avg_daily_bookings,
       average_price_inr, avg_daily_revenue_inr, revenue_per_space_inr,
       revenue_per_occupied_space_inr, bookings_per_space,
       CASE WHEN price_pct >= .75 AND revenue_pct <= .50 THEN 'HIGH_PRICE_WEAK_REVENUE'
            WHEN occupancy_pct >= .75 AND price_pct <= .50 THEN 'HIGH_USE_LOWER_PRICE_CANDIDATE'
            ELSE 'BENCHMARK' END AS analytical_flag
FROM ranked
WHERE revenue_pct >= .75 OR price_pct >= .75 AND revenue_pct <= .50
   OR occupancy_pct >= .75 AND price_pct <= .50
ORDER BY avg_daily_revenue_inr DESC;

SELECT locality_name, SUM(avg_daily_revenue_inr) AS total_avg_daily_revenue_inr,
       ROUND(AVG(revenue_per_space_inr), 2) AS avg_revenue_per_space_inr,
       SUM(expected_monthly_platform_revenue_inr) AS expected_monthly_platform_revenue_inr
FROM vw_parking_performance_summary GROUP BY locality_name
ORDER BY expected_monthly_platform_revenue_inr DESC;
