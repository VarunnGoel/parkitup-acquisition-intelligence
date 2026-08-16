-- Q28-Q31: portfolio, locality, and major-market ranking.
SET search_path TO parkitup, public;
SELECT rank, parking_id, parking_name, locality, acquisition_score, demand_score,
       expected_platform_revenue, competition_score, strategic_fit_score,
       feasibility_score, priority_segment
FROM vw_bd_acquisition_targets ORDER BY rank LIMIT 20;

WITH locality_ranked AS (
 SELECT b.*,
   ROW_NUMBER() OVER (PARTITION BY locality_name ORDER BY acquisition_score DESC, parking_id) AS row_num,
   RANK() OVER (PARTITION BY locality_name ORDER BY acquisition_score DESC) AS score_rank,
   SUM(expected_monthly_platform_revenue_inr) OVER (PARTITION BY locality_name) AS locality_revenue_pipeline
 FROM vw_parking_performance_summary b
)
SELECT parking_id, parking_name, locality_name, acquisition_score, priority_segment,
       row_num, score_rank, locality_revenue_pipeline
FROM locality_ranked WHERE row_num <= 3 ORDER BY locality_name, row_num;
