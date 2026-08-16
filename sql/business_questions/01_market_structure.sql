-- Q1-Q8: establish the candidate market structure before deeper analysis.
SET search_path TO parkitup, public;

-- Q1 total candidate lots.
SELECT COUNT(*) AS parking_lot_count FROM parking_lots;

-- Q2/Q3/Q8 capacity by locality.
SELECT l.locality_name, COUNT(*) AS parking_count,
       SUM(p.capacity_cars) AS total_spaces,
       ROUND(AVG(p.capacity_cars), 2) AS avg_capacity
FROM parking_lots p JOIN dim_locality l USING (locality_id)
GROUP BY l.locality_name ORDER BY total_spaces DESC;

-- Q4 dominant type per locality, retaining ties with DENSE_RANK.
WITH type_counts AS (
 SELECT l.locality_name, p.parking_type, COUNT(*) AS lot_count,
        DENSE_RANK() OVER (PARTITION BY l.locality_name ORDER BY COUNT(*) DESC) AS type_rank
 FROM parking_lots p JOIN dim_locality l USING (locality_id)
 GROUP BY l.locality_name, p.parking_type
)
SELECT locality_name, parking_type, lot_count FROM type_counts
WHERE type_rank = 1 ORDER BY locality_name, parking_type;

-- Q5 price distribution using stable business-readable bands.
SELECT CASE WHEN hourly_rate_inr < 30 THEN '01 Under INR 30'
            WHEN hourly_rate_inr < 50 THEN '02 INR 30-49'
            WHEN hourly_rate_inr < 75 THEN '03 INR 50-74'
            WHEN hourly_rate_inr < 100 THEN '04 INR 75-99'
            ELSE '05 INR 100+' END AS price_band,
       COUNT(*) AS parking_count,
       MIN(hourly_rate_inr) AS min_price, MAX(hourly_rate_inr) AS max_price
FROM parking_lots GROUP BY price_band ORDER BY price_band;

-- Q6/Q7 locality price and occupancy.
SELECT locality_name, ROUND(AVG(average_price_inr), 2) AS avg_price_inr,
       ROUND(AVG(avg_occupancy_pct), 2) AS avg_occupancy_pct,
       SUM(capacity) AS total_capacity
FROM vw_parking_performance_summary GROUP BY locality_name
ORDER BY avg_occupancy_pct DESC, avg_price_inr DESC;
