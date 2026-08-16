-- analytics reusable business analytics views.
SET search_path TO parkitup, public;

CREATE OR REPLACE VIEW vw_parking_performance_summary AS
SELECT
    p.parking_id, p.lot_code, p.lot_name AS parking_name,
    p.locality_id, p.locality_name, p.parking_type, p.capacity_cars AS capacity,
    p.hourly_rate_inr AS average_price_inr,
    ROUND(p.avg_occupancy_rate * 100, 2) AS avg_occupancy_pct,
    ROUND(p.p90_peak_occupancy_rate::numeric * 100, 2) AS p90_peak_occupancy_pct,
    ROUND(p.avg_daily_platform_bookings, 2) AS avg_daily_bookings,
    ROUND(p.avg_daily_gross_revenue_inr, 2) AS avg_daily_revenue_inr,
    ROUND(p.avg_daily_gross_revenue_inr / NULLIF(p.capacity_cars, 0), 2) AS revenue_per_space_inr,
    ROUND(p.avg_daily_platform_bookings / NULLIF(p.capacity_cars, 0), 4) AS bookings_per_space,
    ROUND(p.avg_daily_gross_revenue_inr /
          NULLIF(p.capacity_cars * p.avg_occupancy_rate, 0), 2) AS revenue_per_occupied_space_inr,
    p.competitor_count_1km, p.competitor_avg_hourly_rate_inr,
    p.demand_score, p.revenue_score, p.competition_score,
    p.strategic_fit_score, p.feasibility_score, p.acquisition_score,
    p.priority_segment, p.acquisition_rank,
    p.expected_monthly_platform_revenue_inr, p.rank_stability_pct,
    p.stability_class, p.nearest_live_network_distance_km,
    p.live_network_site_count, p.live_network_capacity_cars
FROM parking_acquisition_score p;

CREATE OR REPLACE VIEW vw_parking_benchmarks AS
SELECT
    p.*,
    ROUND(AVG(p.avg_occupancy_pct) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_occupancy_pct,
    ROUND(p.avg_occupancy_pct - AVG(p.avg_occupancy_pct) OVER (PARTITION BY p.locality_id), 2) AS occupancy_vs_locality_pct_pt,
    ROUND(AVG(p.avg_daily_revenue_inr) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_daily_revenue_inr,
    ROUND(p.avg_daily_revenue_inr - AVG(p.avg_daily_revenue_inr) OVER (PARTITION BY p.locality_id), 2) AS revenue_vs_locality_inr,
    ROUND(AVG(p.revenue_per_space_inr) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_revenue_per_space_inr,
    ROUND(AVG(p.average_price_inr) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_price_inr,
    ROUND(AVG(p.capacity) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_capacity,
    ROUND(AVG(p.competitor_count_1km) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_competitors_1km,
    ROUND(AVG(p.acquisition_score) OVER (PARTITION BY p.locality_id), 2) AS locality_avg_acquisition_score,
    ROUND(AVG(p.avg_occupancy_pct) OVER (PARTITION BY p.parking_type), 2) AS type_avg_occupancy_pct,
    ROUND(AVG(p.revenue_per_space_inr) OVER (PARTITION BY p.parking_type), 2) AS type_avg_revenue_per_space_inr,
    RANK() OVER (PARTITION BY p.locality_id ORDER BY p.acquisition_score DESC) AS locality_acquisition_rank,
    DENSE_RANK() OVER (PARTITION BY p.locality_id ORDER BY p.revenue_per_space_inr DESC) AS locality_efficiency_rank
FROM vw_parking_performance_summary p;

CREATE OR REPLACE VIEW vw_locality_summary AS
WITH candidate AS (
    SELECT locality_id, locality_name,
           COUNT(*) AS parking_count, SUM(capacity) AS total_capacity,
           ROUND(AVG(avg_occupancy_pct), 2) AS avg_occupancy_pct,
           ROUND(AVG(demand_score), 2) AS avg_demand_score,
           ROUND(AVG(revenue_score), 2) AS avg_revenue_score,
           ROUND(AVG(competition_score), 2) AS avg_competition_score,
           ROUND(AVG(strategic_fit_score), 2) AS avg_strategic_fit,
           ROUND(AVG(feasibility_score), 2) AS avg_feasibility,
           ROUND(AVG(acquisition_score), 2) AS avg_acquisition_score,
           COUNT(*) FILTER (WHERE priority_segment = 'ACQUIRE_NOW') AS high_priority_count,
           COUNT(*) FILTER (WHERE priority_segment IN ('ACQUIRE_NOW','PURSUE')) AS acquisition_opportunities,
           ROUND(AVG(competitor_count_1km), 2) AS avg_competitor_count_1km,
           MAX(live_network_site_count) AS parkitup_site_count,
           MAX(live_network_capacity_cars) AS parkitup_capacity
    FROM vw_parking_performance_summary GROUP BY locality_id, locality_name
), competitor AS (
    SELECT p.locality_id,
           ROUND(AVG(c.competitor_count_1km), 2) AS competitor_count_proxy,
           SUM(c.competitor_total_capacity_1km) AS competitor_capacity_proxy
    FROM parking_lots p JOIN competition c USING (parking_id) GROUP BY p.locality_id
)
SELECT c.*,
       COALESCE(x.competitor_count_proxy, 0) AS competitor_count_proxy,
       x.competitor_capacity_proxy,
       ROUND(c.parkitup_capacity::numeric / NULLIF(c.total_capacity + c.parkitup_capacity, 0) * 100, 2) AS parkitup_coverage_pct,
       ROUND(c.avg_demand_score * (1 - COALESCE(c.parkitup_capacity::numeric /
             NULLIF(c.total_capacity + c.parkitup_capacity, 0), 0)), 2) AS market_whitespace_score,
       DENSE_RANK() OVER (ORDER BY c.avg_demand_score * (1 - COALESCE(c.parkitup_capacity::numeric /
             NULLIF(c.total_capacity + c.parkitup_capacity, 0), 0)) DESC) AS whitespace_rank
FROM candidate c LEFT JOIN competitor x USING (locality_id);

CREATE OR REPLACE VIEW vw_bd_funnel AS
WITH reached AS (
    SELECT s.stage_id, s.stage_code, s.stage_name, s.stage_order,
           COUNT(o.lead_id) FILTER (WHERE fs.stage_order >= s.stage_order) AS leads_reached
    FROM dim_funnel_stage s
    CROSS JOIN outreach o
    JOIN dim_funnel_stage fs ON fs.stage_id = o.furthest_stage_id
    GROUP BY s.stage_id, s.stage_code, s.stage_name, s.stage_order
), rates AS (
    SELECT r.*,
           LAG(r.leads_reached) OVER (ORDER BY r.stage_order) AS prior_stage_leads,
           LEAD(r.leads_reached) OVER (ORDER BY r.stage_order) AS next_stage_leads
    FROM reached r
)
SELECT *,
       ROUND(leads_reached::numeric / NULLIF(FIRST_VALUE(leads_reached) OVER (ORDER BY stage_order), 0) * 100, 2) AS lead_to_stage_pct,
       ROUND(leads_reached::numeric / NULLIF(prior_stage_leads, 0) * 100, 2) AS prior_stage_conversion_pct,
       prior_stage_leads - leads_reached AS drop_off_from_prior,
       ROUND((prior_stage_leads - leads_reached)::numeric / NULLIF(prior_stage_leads, 0) * 100, 2) AS drop_off_pct
FROM rates;

CREATE OR REPLACE VIEW vw_bd_acquisition_targets AS
SELECT
    ROW_NUMBER() OVER (
      ORDER BY CASE p.priority_segment WHEN 'ACQUIRE_NOW' THEN 1 WHEN 'PURSUE' THEN 2
               WHEN 'DEVELOP' THEN 3 ELSE 4 END,
               p.acquisition_score DESC, p.parking_id) AS rank,
    p.parking_id, p.parking_name, p.locality_name AS locality, p.capacity,
    p.acquisition_score, p.priority_segment,
    p.expected_monthly_platform_revenue_inr AS expected_platform_revenue,
    p.demand_score, p.competition_score, p.strategic_fit_score,
    p.feasibility_score, p.rank_stability_pct AS rank_stability,
    s.positive_reason_flags, s.constraint_reason_flags,
    CASE
      WHEN p.priority_segment = 'ACQUIRE_NOW' THEN 'IMMEDIATE_OUTREACH'
      WHEN p.priority_segment = 'PURSUE' THEN 'STRATEGIC_PURSUIT'
      WHEN p.priority_segment = 'DEVELOP' THEN 'SEQUENCED_OUTREACH'
      ELSE 'MONITOR'
    END AS bd_action_group
FROM vw_parking_performance_summary p
JOIN parking_score_explanation s USING (parking_id);

CREATE OR REPLACE VIEW vw_parking_rank_explanation AS
SELECT
    b.parking_id, b.parking_name, b.locality_name,
    b.demand_score, b.revenue_score, b.competition_score,
    b.strategic_fit_score, b.feasibility_score, b.acquisition_score,
    b.locality_acquisition_rank, b.acquisition_rank AS overall_rank,
    ROUND(b.demand_score - AVG(b.demand_score) OVER (PARTITION BY b.locality_id), 2) AS demand_vs_locality,
    ROUND(b.revenue_score - AVG(b.revenue_score) OVER (PARTITION BY b.locality_id), 2) AS revenue_vs_locality,
    ROUND(b.competition_score - AVG(b.competition_score) OVER (PARTITION BY b.locality_id), 2) AS competition_vs_locality,
    ROUND(b.strategic_fit_score - AVG(b.strategic_fit_score) OVER (PARTITION BY b.locality_id), 2) AS strategic_fit_vs_locality,
    ROUND(b.feasibility_score - AVG(b.feasibility_score) OVER (PARTITION BY b.locality_id), 2) AS feasibility_vs_locality,
    e.positive_reason_flags, e.constraint_reason_flags,
    CASE WHEN b.acquisition_score >= AVG(b.acquisition_score) OVER () THEN 'WHY_RANKED_HIGH'
         ELSE 'WHY_RANKED_LOW' END AS explanation_type
FROM vw_parking_benchmarks b JOIN parking_score_explanation e USING (parking_id);
