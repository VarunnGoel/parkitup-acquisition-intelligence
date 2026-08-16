-- Peer benchmarks and multivariate outliers for recommendation review.
SET search_path TO parkitup, public;
SELECT parking_id, parking_name, locality_name, capacity, locality_avg_capacity,
       avg_occupancy_pct, occupancy_vs_locality_pct_pt,
       revenue_per_space_inr, locality_avg_revenue_per_space_inr,
       acquisition_score, locality_avg_acquisition_score,
       locality_acquisition_rank, locality_efficiency_rank
FROM vw_parking_benchmarks ORDER BY locality_name, locality_acquisition_rank;

WITH z AS (
 SELECT b.*,
   (avg_daily_revenue_inr - AVG(avg_daily_revenue_inr) OVER ()) / NULLIF(STDDEV_SAMP(avg_daily_revenue_inr) OVER (),0) AS revenue_z,
   (avg_occupancy_pct - AVG(avg_occupancy_pct) OVER ()) / NULLIF(STDDEV_SAMP(avg_occupancy_pct) OVER (),0) AS occupancy_z
 FROM vw_parking_benchmarks b
)
SELECT parking_id, parking_name, locality_name, revenue_z, occupancy_z,
       CASE WHEN revenue_z >= 2 THEN 'HIGH_REVENUE_OUTLIER'
            WHEN occupancy_z >= 2 THEN 'HIGH_OCCUPANCY_OUTLIER'
            WHEN occupancy_z <= -2 THEN 'LOW_UTILIZATION_OUTLIER'
            WHEN demand_score >= 70 AND feasibility_score < 40 THEN 'HIGH_DEMAND_LOW_FEASIBILITY'
            WHEN acquisition_score >= 60 AND revenue_score < 40 THEN 'HIGH_SCORE_LOW_REVENUE'
       END AS outlier_type
FROM z WHERE ABS(revenue_z) >= 2 OR ABS(occupancy_z) >= 2
   OR demand_score >= 70 AND feasibility_score < 40
   OR acquisition_score >= 60 AND revenue_score < 40
ORDER BY outlier_type, acquisition_score DESC;
