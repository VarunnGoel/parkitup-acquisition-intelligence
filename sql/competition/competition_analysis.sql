-- Q19-Q23: competitive pressure must be interpreted jointly with demand.
SET search_path TO parkitup, public;
WITH bands AS (
 SELECT p.*,
   NTILE(4) OVER (ORDER BY competitor_count_1km) AS competition_quartile,
   NTILE(4) OVER (ORDER BY demand_score) AS demand_quartile
 FROM vw_parking_performance_summary p
)
SELECT parking_id, parking_name, locality_name, capacity, demand_score,
       competitor_count_1km, competition_score, avg_occupancy_pct,
       CASE WHEN demand_quartile = 4 AND competition_quartile <= 2 THEN 'HIGH_DEMAND_LOW_COMPETITION'
            WHEN demand_quartile = 4 AND competition_quartile = 4 THEN 'HIGH_COMPETITION_STRONG_DEMAND'
            WHEN demand_quartile <= 2 AND competition_quartile = 4 THEN 'HIGH_COMPETITION_WEAK_DEMAND'
       END AS market_pattern
FROM bands
WHERE (demand_quartile = 4 AND competition_quartile <= 2)
   OR (competition_quartile = 4 AND (demand_quartile = 4 OR demand_quartile <= 2))
ORDER BY market_pattern, demand_score DESC;

SELECT parking_id, parking_name, locality_name, average_price_inr,
       competitor_avg_hourly_rate_inr,
       ROUND((average_price_inr / NULLIF(competitor_avg_hourly_rate_inr, 0) - 1) * 100, 2) AS price_premium_pct,
       avg_occupancy_pct
FROM vw_parking_performance_summary
WHERE competitor_avg_hourly_rate_inr IS NOT NULL
ORDER BY price_premium_pct DESC LIMIT 20;
