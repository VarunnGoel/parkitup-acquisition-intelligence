-- Q9-Q13: demand and utilization. Peak hours are empirically defined as the
-- top occupancy quartile of portfolio hours within each day type.
SET search_path TO parkitup, public;

SELECT parking_id, parking_name, locality_name, capacity, avg_occupancy_pct,
       p90_peak_occupancy_pct, avg_daily_bookings
FROM vw_parking_performance_summary
ORDER BY avg_occupancy_pct DESC, avg_daily_bookings DESC LIMIT 20;

WITH portfolio_hours AS (
  SELECT day_type, hour_of_day, AVG(avg_occupancy_rate) AS portfolio_occupancy
  FROM fact_lot_hourly_profile GROUP BY day_type, hour_of_day
), thresholds AS (
  SELECT day_type, percentile_cont(0.75) WITHIN GROUP (ORDER BY portfolio_occupancy) AS cutoff
  FROM portfolio_hours GROUP BY day_type
), peak_hours AS (
  SELECT h.day_type, h.hour_of_day FROM portfolio_hours h JOIN thresholds t USING (day_type)
  WHERE h.portfolio_occupancy >= t.cutoff
)
SELECT p.parking_id, p.lot_name AS parking_name, l.locality_name,
       ROUND(AVG(h.avg_occupancy_rate) * 100, 2) AS peak_hour_occupancy_pct,
       STRING_AGG(DISTINCT h.hour_of_day::text, ', ' ORDER BY h.hour_of_day::text) AS peak_hours
FROM fact_lot_hourly_profile h JOIN peak_hours ph USING (day_type, hour_of_day)
JOIN parking_lots p USING (parking_id) JOIN dim_locality l USING (locality_id)
GROUP BY p.parking_id, p.lot_name, l.locality_name
ORDER BY peak_hour_occupancy_pct DESC LIMIT 20;

WITH sizes AS (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY capacity) AS median_capacity FROM vw_parking_performance_summary)
SELECT parking_id, parking_name, locality_name, capacity, avg_occupancy_pct,
       CASE WHEN capacity >= median_capacity AND avg_occupancy_pct < 40 THEN 'HIGH_CAPACITY_LOW_USE'
            WHEN capacity < median_capacity AND avg_occupancy_pct >= 70 THEN 'SMALL_LOT_OUTPERFORMER' END AS utilization_pattern
FROM vw_parking_performance_summary CROSS JOIN sizes
WHERE (capacity >= median_capacity AND avg_occupancy_pct < 40)
   OR (capacity < median_capacity AND avg_occupancy_pct >= 70)
ORDER BY utilization_pattern, avg_occupancy_pct DESC;
