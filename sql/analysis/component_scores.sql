-- =====================================================================
-- scoring core scoring logic (baseline assumptions)
--
-- This view deliberately exposes intermediate measures. It is not a black
-- box: reviewers can see the location proxy, capacity-neutral revenue
-- efficiency, count-based competition pressure, network band and every
-- feasibility subcomponent before any final weight is applied.
-- =====================================================================
SET search_path TO parkitup, public;

CREATE OR REPLACE VIEW parking_component_scores AS
WITH feature AS (
    SELECT * FROM parking_acquisition_features
), anchors AS (
    SELECT
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY poi_activity_raw)::NUMERIC AS poi_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY poi_activity_raw)::NUMERIC AS poi_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY transit_access_raw)::NUMERIC AS transit_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY transit_access_raw)::NUMERIC AS transit_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY avg_occupancy_rate)::NUMERIC AS occupancy_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY avg_occupancy_rate)::NUMERIC AS occupancy_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY p90_peak_occupancy_rate)::NUMERIC AS peak_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY p90_peak_occupancy_rate)::NUMERIC AS peak_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY competitor_supply_pressure_raw)::NUMERIC AS competition_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY competitor_supply_pressure_raw)::NUMERIC AS competition_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY estimated_onboarding_cost_inr)::NUMERIC AS onboarding_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY estimated_onboarding_cost_inr)::NUMERIC AS onboarding_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY estimated_setup_days)::NUMERIC AS setup_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY estimated_setup_days)::NUMERIC AS setup_high
    FROM feature
), normalized_inputs AS (
    SELECT
        f.*,
        normalize_winsor(f.poi_activity_raw, a.poi_low, a.poi_high) AS poi_activity_score,
        normalize_winsor(f.transit_access_raw, a.transit_low, a.transit_high) AS transit_access_score,
        normalize_winsor(f.avg_occupancy_rate, a.occupancy_low, a.occupancy_high) AS average_occupancy_score,
        normalize_winsor(f.p90_peak_occupancy_rate, a.peak_low, a.peak_high) AS peak_occupancy_score,
        normalize_winsor(f.competitor_supply_pressure_raw, a.competition_low, a.competition_high, TRUE)
            AS competitor_supply_score,
        normalize_winsor(f.estimated_onboarding_cost_inr, a.onboarding_low, a.onboarding_high, TRUE)
            AS onboarding_cost_score,
        normalize_winsor(f.estimated_setup_days, a.setup_low, a.setup_high, TRUE) AS setup_speed_score,
        a.poi_low, a.poi_high, a.transit_low, a.transit_high,
        a.occupancy_low, a.occupancy_high, a.peak_low, a.peak_high,
        a.competition_low, a.competition_high, a.onboarding_low, a.onboarding_high,
        a.setup_low, a.setup_high
    FROM feature f CROSS JOIN anchors a
), demand_inputs AS (
    SELECT
        n.*,
        100.0 * n.metro_access_raw AS metro_access_score,
        100.0 * GREATEST(0.0, LEAST(1.0, (n.market_demand_prior - 0.45) / 0.45)) AS market_prior_score,
        (0.30 * (100.0 * n.metro_access_raw)
         + 0.35 * n.poi_activity_score
         + 0.15 * n.transit_access_score
         + 0.20 * (100.0 * GREATEST(0.0, LEAST(1.0, (n.market_demand_prior - 0.45) / 0.45))))
            AS location_demand_score,
        (0.70 * n.average_occupancy_score + 0.30 * n.peak_occupancy_score)
            AS observed_demand_score
    FROM normalized_inputs n
), demand_score AS (
    SELECT
        d.*,
        GREATEST(0.0, d.location_demand_score - d.average_occupancy_score) AS demand_headroom_score,
        (0.50 * d.observed_demand_score
         + 0.40 * d.location_demand_score
         + 0.10 * GREATEST(0.0, d.location_demand_score - d.average_occupancy_score))
            AS demand_score,
        LEAST(0.85,
            d.avg_occupancy_rate
            + LEAST(0.12,
                GREATEST(0.0, d.location_demand_score / 100.0 * 0.82 - d.avg_occupancy_rate) * 0.35)
        ) AS achievable_utilization
    FROM demand_inputs d
), economics_raw AS (
    SELECT
        d.*,
        d.avg_daily_platform_bookings * (1.0 - COALESCE(d.cancellation_rate, 0.0))
            * LEAST(1.35, d.achievable_utilization / GREATEST(d.avg_occupancy_rate, 0.05))
            AS expected_daily_net_platform_bookings,
        d.avg_daily_platform_bookings * (1.0 - COALESCE(d.cancellation_rate, 0.0))
            * LEAST(1.35, d.achievable_utilization / GREATEST(d.avg_occupancy_rate, 0.05))
            * d.avg_park_duration_hours * d.hourly_rate_inr * 0.76
            * d.expected_commission_pct / 100.0 * 30.0
            AS expected_monthly_platform_revenue_inr
    FROM demand_score d
), economics AS (
    SELECT
        e.*,
        e.expected_monthly_platform_revenue_inr / NULLIF(e.capacity_cars, 0)
            AS expected_revenue_per_space_inr
    FROM economics_raw e
), revenue_anchors AS (
    SELECT
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY LN(1 + expected_monthly_platform_revenue_inr))::NUMERIC AS revenue_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY LN(1 + expected_monthly_platform_revenue_inr))::NUMERIC AS revenue_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY expected_revenue_per_space_inr)::NUMERIC AS revenue_space_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY expected_revenue_per_space_inr)::NUMERIC AS revenue_space_high
    FROM economics
), with_revenue AS (
    SELECT
        e.*,
        normalize_winsor(LN(1 + e.expected_monthly_platform_revenue_inr), r.revenue_low, r.revenue_high)
            AS expected_revenue_score,
        normalize_winsor(e.expected_revenue_per_space_inr, r.revenue_space_low, r.revenue_space_high)
            AS revenue_efficiency_score,
        (0.75 * normalize_winsor(LN(1 + e.expected_monthly_platform_revenue_inr), r.revenue_low, r.revenue_high)
         + 0.25 * normalize_winsor(e.expected_revenue_per_space_inr, r.revenue_space_low, r.revenue_space_high))
            AS revenue_score,
        r.revenue_low, r.revenue_high, r.revenue_space_low, r.revenue_space_high
    FROM economics e CROSS JOIN revenue_anchors r
), locality_metrics AS (
    SELECT
        locality_id,
        AVG(location_demand_score) AS locality_demand_score,
        MAX(live_network_capacity_cars)::NUMERIC
            / NULLIF(MAX(locality_candidate_capacity_cars)::NUMERIC + MAX(live_network_capacity_cars)::NUMERIC, 0)
            AS locality_network_coverage_ratio
    FROM with_revenue
    GROUP BY locality_id
), strategic_raw AS (
    SELECT
        w.*,
        lm.locality_demand_score,
        lm.locality_network_coverage_ratio,
        lm.locality_demand_score * (1.0 - COALESCE(lm.locality_network_coverage_ratio, 0.0))
            AS market_whitespace_raw,
        -- Anchor capacity: does this lot represent a meaningful share of the
        -- supply that matters in its locality?
        --
        -- CORRECTION. This was capacity / (live_network_capacity +
        -- capacity), which collapses to exactly 1.0 whenever the platform has no
        -- live site in the locality. 32 of 120 lots sat in that case, so a
        -- 27-space lot and a 643-space lot both scored the maximum 100, and
        -- Strategic Fit became a locality-level constant for 4 localities -
        -- including Lajpat Nagar, home of the top-ranked lot, where all 6 lots
        -- scored an identical 84.202159. The subcomponent was not measuring
        -- anything: every lot is 100% of nothing.
        --
        -- Including the locality candidate pool in the denominator keeps the
        -- "share of relevant supply" meaning, stays monotone in capacity, and
        -- cannot degenerate because the lot itself is always in that pool.
        w.capacity_cars::NUMERIC
            / NULLIF(w.live_network_capacity_cars + w.locality_candidate_capacity_cars, 0)
            AS anchor_capacity_raw,
        network_band_score(w.nearest_network_distance_km) AS network_distance_score,
        100.0 * (1.0 - w.aggregator_penetration_rate) AS aggregator_opportunity_score,
        LEAST(100.0, w.competitor_distance_proxy_m / 1500.0 * 100.0) AS competitor_distance_score,
        CASE
            WHEN w.competitor_price_ratio IS NULL THEN 55.0
            ELSE 100.0 * GREATEST(0.0, LEAST(1.0, (w.competitor_price_ratio - 0.70) / 0.60))
        END AS competitor_price_headroom_score
    FROM with_revenue w
    JOIN locality_metrics lm USING (locality_id)
), strategic_anchors AS (
    SELECT
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY market_whitespace_raw)::NUMERIC AS whitespace_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY market_whitespace_raw)::NUMERIC AS whitespace_high,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY anchor_capacity_raw)::NUMERIC AS anchor_low,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY anchor_capacity_raw)::NUMERIC AS anchor_high
    FROM strategic_raw
), scored AS (
    SELECT
        s.*,
        normalize_winsor(s.market_whitespace_raw, a.whitespace_low, a.whitespace_high)
            AS market_whitespace_score,
        normalize_winsor(s.anchor_capacity_raw, a.anchor_low, a.anchor_high)
            AS anchor_capacity_score,
        (0.55 * s.competitor_supply_score
         + 0.20 * s.aggregator_opportunity_score
         + 0.15 * s.competitor_distance_score
         + 0.10 * s.competitor_price_headroom_score) AS competition_score,
        (0.50 * s.network_distance_score
         + 0.35 * normalize_winsor(s.market_whitespace_raw, a.whitespace_low, a.whitespace_high)
         + 0.15 * normalize_winsor(s.anchor_capacity_raw, a.anchor_low, a.anchor_high))
            AS strategic_fit_score,
        (0.20 * ((s.willingness_to_digitize - 1)::NUMERIC / 4.0 * 100.0)
         + 0.14 * ((s.contract_flexibility - 1)::NUMERIC / 4.0 * 100.0)
         + 0.12 * (0.30 * CASE WHEN s.digital_payment_enabled THEN 100.0 ELSE 0.0 END
                  + 0.70 * s.management_maturity_score * 100.0)
         + 0.15 * ((s.documentation_readiness - 1)::NUMERIC / 4.0 * 100.0)
         + 0.12 * CASE WHEN s.decision_maker_accessible THEN 100.0 ELSE 0.0 END
         + 0.08 * ((5 - s.operational_complexity)::NUMERIC / 4.0 * 100.0)
         + 0.07 * s.onboarding_cost_score
         + 0.04 * s.setup_speed_score
         + 0.03 * CASE WHEN s.exclusivity_possible THEN 100.0 ELSE 35.0 END
         + 0.02 * CASE WHEN s.requires_capex THEN 20.0 ELSE 100.0 END
         + 0.03 * CASE s.owner_type
             WHEN 'Government/Municipal' THEN 25.0
             WHEN 'RWA' THEN 45.0
             WHEN 'Individual' THEN 65.0
             WHEN 'Family Trust' THEN 60.0
             WHEN 'Private Company' THEN 80.0
             WHEN 'Mall Management' THEN 75.0
             ELSE 70.0 END) AS feasibility_score,
        a.whitespace_low, a.whitespace_high, a.anchor_low, a.anchor_high
    FROM strategic_raw s CROSS JOIN strategic_anchors a
)
SELECT
    scored.*,
    'Derived from OSM proximity/counts plus synthetic performance and terms; '
    'competitor capacity is intentionally excluded because it is null for every candidate.'
        AS methodology_note
FROM scored;

COMMENT ON VIEW parking_component_scores IS
  'PROVENANCE: derived (scoring). Baseline pillar inputs and five unweighted '
  'scores. Winsorised 5th/95th percentile anchors stop extreme capacity or '
  'revenue values from dominating the ranking.';
