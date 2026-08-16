-- =====================================================================
-- 06_analysis.sql : scoring acquisition intelligence outputs
-- Depends on: 01_reference.sql, 02_core_entities.sql, 03_facts.sql,
--             04_bd_pipeline.sql, 05_scoring.sql
-- =====================================================================
SET search_path TO parkitup, public;

-- Small, explicit helpers keep the normalisation rules readable in the
-- analysis views. Values are always clipped, never silently allowed outside
-- the required 0-100 score range.
CREATE OR REPLACE FUNCTION normalize_winsor(value DOUBLE PRECISION,
                                            lower_bound DOUBLE PRECISION,
                                            upper_bound DOUBLE PRECISION,
                                            invert BOOLEAN DEFAULT FALSE)
RETURNS DOUBLE PRECISION
LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE
        WHEN value IS NULL THEN NULL
        WHEN upper_bound <= lower_bound THEN 50.0
        WHEN invert THEN GREATEST(0.0, LEAST(100.0,
             100.0 * (upper_bound - GREATEST(lower_bound, LEAST(upper_bound, value)))
             / (upper_bound - lower_bound)))
        ELSE GREATEST(0.0, LEAST(100.0,
             100.0 * (GREATEST(lower_bound, LEAST(upper_bound, value)) - lower_bound)
             / (upper_bound - lower_bound)))
    END;
$$;

CREATE OR REPLACE FUNCTION network_band_score(distance_km DOUBLE PRECISION)
RETURNS DOUBLE PRECISION
LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE
        WHEN distance_km IS NULL THEN 35.0
        WHEN distance_km < 0.40 THEN 10.0 + 25.0 * distance_km / 0.40
        WHEN distance_km < 1.50 THEN 35.0 + 65.0 * (distance_km - 0.40) / 1.10
        WHEN distance_km < 6.00 THEN 100.0
        WHEN distance_km < 9.00 THEN 100.0 - 35.0 * (distance_km - 6.00) / 3.00
        ELSE 65.0
    END;
$$;

-- ---------------------------------------------------------------------
-- parking_acquisition_features : one row per candidate lot
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW parking_acquisition_features AS
WITH daily AS (
    SELECT
        f.parking_id,
        AVG(f.avg_occupancy_rate) AS avg_occupancy_rate,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY f.peak_occupancy_rate)
            AS p90_peak_occupancy_rate,
        AVG(f.avg_occupancy_rate) FILTER (WHERE d.is_weekend = FALSE)
            AS weekday_occupancy_rate,
        AVG(f.avg_occupancy_rate) FILTER (WHERE d.is_weekend = TRUE)
            AS weekend_occupancy_rate,
        AVG(f.vehicle_entries) AS avg_daily_entries,
        AVG(f.platform_bookings) AS avg_daily_platform_bookings,
        AVG(f.booking_cancellations) AS avg_daily_cancellations,
        SUM(f.platform_bookings)::NUMERIC / NULLIF(SUM(f.vehicle_entries), 0)
            AS platform_booking_share,
        SUM(f.booking_cancellations)::NUMERIC / NULLIF(SUM(f.platform_bookings), 0)
            AS cancellation_rate,
        AVG(f.gross_parking_revenue_inr) AS avg_daily_gross_revenue_inr,
        SUM(f.gross_parking_revenue_inr) AS observation_gross_revenue_inr,
        AVG(f.avg_park_duration_hours) AS avg_park_duration_hours
    FROM fact_lot_daily f
    JOIN dim_date d USING (activity_date)
    GROUP BY f.parking_id
), hourly AS (
    SELECT
        parking_id,
        MAX(avg_occupancy_rate) FILTER (WHERE day_type = 'Weekday')
            AS weekday_hourly_peak_occupancy_rate,
        MAX(avg_occupancy_rate) FILTER (WHERE day_type = 'Weekend')
            AS weekend_hourly_peak_occupancy_rate,
        AVG((avg_occupancy_rate >= 0.60)::INT)
            FILTER (WHERE day_type = 'Weekday') AS weekday_busy_hour_share,
        AVG((avg_occupancy_rate >= 0.60)::INT)
            FILTER (WHERE day_type = 'Weekend') AS weekend_busy_hour_share
    FROM fact_lot_hourly_profile
    GROUP BY parking_id
), network_distance AS (
    SELECT
        p.parking_id,
        MIN(6371.0 * 2.0 * ASIN(SQRT(
            POWER(SIN(RADIANS((n.latitude - p.latitude) / 2.0)), 2)
            + COS(RADIANS(p.latitude)) * COS(RADIANS(n.latitude))
            * POWER(SIN(RADIANS((n.longitude - p.longitude) / 2.0)), 2)
        ))) FILTER (WHERE n.site_status = 'Live') AS nearest_live_network_distance_km,
        MIN(6371.0 * 2.0 * ASIN(SQRT(
            POWER(SIN(RADIANS((n.latitude - p.latitude) / 2.0)), 2)
            + COS(RADIANS(p.latitude)) * COS(RADIANS(n.latitude))
            * POWER(SIN(RADIANS((n.longitude - p.longitude) / 2.0)), 2)
        ))) AS nearest_any_network_distance_km
        ,MIN(6371.0 * 2.0 * ASIN(SQRT(
            POWER(SIN(RADIANS((n.latitude - p.latitude) / 2.0)), 2)
            + COS(RADIANS(p.latitude)) * COS(RADIANS(n.latitude))
            * POWER(SIN(RADIANS((n.longitude - p.longitude) / 2.0)), 2)
        ))) FILTER (WHERE n.site_status = 'Live' AND n.live_since < DATE '2024-01-01')
            AS nearest_mature_network_distance_km
    FROM parking_lots p
    CROSS JOIN existing_network_sites n
    GROUP BY p.parking_id
), network_locality AS (
    SELECT
        locality_id,
        COUNT(*) FILTER (WHERE site_status = 'Live') AS live_network_site_count,
        COALESCE(SUM(capacity_cars) FILTER (WHERE site_status = 'Live'), 0)
            AS live_network_capacity_cars,
        COUNT(*) AS all_network_site_count
    FROM existing_network_sites
    GROUP BY locality_id
), base AS (
    SELECT
        p.parking_id,
        p.lot_code,
        p.lot_name,
        p.locality_id,
        l.locality_name,
        c.city_name,
        l.micro_market_type,
        l.population_density_band,
        p.owner_id,
        o.owner_type,
        p.latitude,
        p.longitude,
        p.parking_type,
        p.capacity_cars,
        p.hourly_rate_inr,
        p.is_24x7,
        CASE WHEN p.is_24x7 THEN 24.0
             ELSE GREATEST(1.0, MOD(
                 EXTRACT(HOUR FROM p.closes_at)::INT
                 - EXTRACT(HOUR FROM p.opens_at)::INT + 24, 24))::NUMERIC
        END AS operating_hours,
        p.record_source,
        p.source_name,
        p.source_reference,
        p.data_quality_flag,
        d.metro_distance_m,
        d.nearest_metro_station,
        d.mall_distance_m,
        d.office_count_500m,
        d.retail_count_500m,
        d.restaurant_count_500m,
        d.hospital_count_1km,
        d.education_count_1km,
        d.transit_stop_count_500m,
        cpt.competitor_count_500m,
        cpt.competitor_count_1km,
        cpt.nearest_competitor_distance_m,
        cpt.competitor_avg_hourly_rate_inr,
        cpt.aggregator_listed_count_1km,
        CASE WHEN cpt.competitor_count_1km = 0 THEN 0.0
             ELSE cpt.aggregator_listed_count_1km::NUMERIC / cpt.competitor_count_1km
        END AS aggregator_penetration_rate,
        CASE WHEN cpt.nearest_competitor_distance_m IS NULL THEN 1500.0
             ELSE cpt.nearest_competitor_distance_m::NUMERIC END
            AS competitor_distance_proxy_m,
        CASE WHEN cpt.competitor_avg_hourly_rate_inr IS NULL THEN NULL
             ELSE cpt.competitor_avg_hourly_rate_inr / NULLIF(p.hourly_rate_inr, 0)
        END AS competitor_price_ratio,
        t.expected_commission_pct,
        t.estimated_onboarding_cost_inr,
        t.documentation_readiness,
        t.operational_complexity,
        t.exclusivity_possible,
        t.requires_capex,
        t.estimated_setup_days,
        o.years_operating,
        o.digital_payment_enabled,
        o.management_system,
        o.willingness_to_digitize,
        o.contract_flexibility,
        o.decision_maker_accessible,
        daily.avg_occupancy_rate,
        daily.p90_peak_occupancy_rate,
        daily.weekday_occupancy_rate,
        daily.weekend_occupancy_rate,
        daily.avg_daily_entries,
        daily.avg_daily_platform_bookings,
        daily.avg_daily_cancellations,
        daily.platform_booking_share,
        daily.cancellation_rate,
        daily.avg_daily_gross_revenue_inr,
        daily.observation_gross_revenue_inr,
        daily.avg_park_duration_hours,
        hourly.weekday_hourly_peak_occupancy_rate,
        hourly.weekend_hourly_peak_occupancy_rate,
        hourly.weekday_busy_hour_share,
        hourly.weekend_busy_hour_share,
        COALESCE(nd.nearest_live_network_distance_km, nd.nearest_any_network_distance_km)
            AS nearest_network_distance_km,
        nd.nearest_live_network_distance_km,
        nd.nearest_any_network_distance_km,
        nd.nearest_mature_network_distance_km,
        COALESCE(nl.live_network_site_count, 0) AS live_network_site_count,
        COALESCE(nl.live_network_capacity_cars, 0) AS live_network_capacity_cars,
        COALESCE(nl.all_network_site_count, 0) AS all_network_site_count,
        EXP(-1.25 * d.metro_distance_m::NUMERIC / 1200.0) AS metro_access_raw,
        (0.35 * LN(1 + d.office_count_500m)
         + 0.30 * LN(1 + d.retail_count_500m)
         + 0.25 * LN(1 + d.restaurant_count_500m)
         + 0.07 * LN(1 + d.hospital_count_1km)
         + 0.03 * LN(1 + d.education_count_1km)) AS poi_activity_raw,
        LN(1 + d.transit_stop_count_500m) AS transit_access_raw,
        CASE l.micro_market_type
            WHEN 'CBD' THEN 0.88
            WHEN 'Commercial' THEN 0.78
            WHEN 'Retail High Street' THEN 0.82
            WHEN 'IT/Office Park' THEN 0.77
            WHEN 'Residential' THEN 0.55
            WHEN 'Transit Hub' THEN 0.84
            WHEN 'Hospital/Institutional' THEN 0.68
            ELSE 0.72
        END AS market_demand_prior,
        CASE o.management_system
            WHEN 'None/Manual' THEN 0.00
            WHEN 'Paper Register' THEN 0.25
            WHEN 'Spreadsheet' THEN 0.50
            WHEN 'Basic POS' THEN 0.75
            ELSE 0.90
        END AS management_maturity_score
    FROM parking_lots p
    JOIN dim_locality l USING (locality_id)
    JOIN dim_city c USING (city_id)
    JOIN owners o USING (owner_id)
    JOIN location_demand d USING (parking_id)
    JOIN competition cpt USING (parking_id)
    JOIN lot_acquisition_terms t USING (parking_id)
    LEFT JOIN daily USING (parking_id)
    LEFT JOIN hourly USING (parking_id)
    LEFT JOIN network_distance nd USING (parking_id)
    LEFT JOIN network_locality nl USING (locality_id)
), locality_context AS (
    SELECT
        locality_id,
        COUNT(*) AS locality_lot_count,
        SUM(capacity_cars) AS locality_candidate_capacity_cars,
        AVG(market_demand_prior) AS locality_market_demand_prior,
        AVG(metro_access_raw) AS locality_metro_access_raw
    FROM base
    GROUP BY locality_id
)
SELECT
    b.*,
    lc.locality_lot_count,
    lc.locality_candidate_capacity_cars,
    lc.locality_market_demand_prior,
    lc.locality_metro_access_raw,
    LN(1 + b.competitor_count_1km)::NUMERIC
        / GREATEST(b.market_demand_prior, 0.10) AS competitor_supply_pressure_raw,
    GREATEST(0.0, b.market_demand_prior - b.avg_occupancy_rate)
        AS latent_demand_headroom_raw
FROM base b
JOIN locality_context lc USING (locality_id);

-- Scenario and result tables are intentionally separate from the source
-- facts. Re-running the scoring engine replaces these outputs without touching source data.
CREATE TABLE IF NOT EXISTS acquisition_scenario (
    scenario_id                  SMALLINT PRIMARY KEY,
    scenario_code                TEXT NOT NULL UNIQUE,
    scenario_group               TEXT NOT NULL,
    description                  TEXT NOT NULL,
    weight_set_id                SMALLINT NOT NULL REFERENCES scoring_weight_set(weight_set_id),
    demand_multiplier            NUMERIC(5,3) NOT NULL CHECK (demand_multiplier BETWEEN 0.50 AND 1.50),
    commission_multiplier        NUMERIC(5,3) NOT NULL CHECK (commission_multiplier BETWEEN 0.50 AND 1.50),
    booking_share_multiplier     NUMERIC(5,3) NOT NULL CHECK (booking_share_multiplier BETWEEN 0.50 AND 1.50),
    dwell_multiplier             NUMERIC(5,3) NOT NULL CHECK (dwell_multiplier BETWEEN 0.50 AND 1.50),
    onboarding_cost_multiplier   NUMERIC(5,3) NOT NULL CHECK (onboarding_cost_multiplier BETWEEN 0.50 AND 2.00),
    network_variant               TEXT NOT NULL CHECK (network_variant IN ('LIVE','ALL_SITES','MATURE_LIVE')),
    include_in_stability          BOOLEAN NOT NULL DEFAULT TRUE,
    methodology_note              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lot_scenario_score (
    parking_id             INT NOT NULL REFERENCES parking_lots(parking_id) ON DELETE CASCADE,
    scenario_id            SMALLINT NOT NULL REFERENCES acquisition_scenario(scenario_id) ON DELETE CASCADE,
    demand_score           NUMERIC(5,2) NOT NULL CHECK (demand_score BETWEEN 0 AND 100),
    revenue_score          NUMERIC(5,2) NOT NULL CHECK (revenue_score BETWEEN 0 AND 100),
    competition_score      NUMERIC(5,2) NOT NULL CHECK (competition_score BETWEEN 0 AND 100),
    strategic_fit_score    NUMERIC(5,2) NOT NULL CHECK (strategic_fit_score BETWEEN 0 AND 100),
    feasibility_score      NUMERIC(5,2) NOT NULL CHECK (feasibility_score BETWEEN 0 AND 100),
    achievable_utilization NUMERIC(6,4) NOT NULL CHECK (achievable_utilization BETWEEN 0 AND 1),
    expected_monthly_platform_revenue_inr NUMERIC(14,2) NOT NULL
                              CHECK (expected_monthly_platform_revenue_inr >= 0),
    expected_revenue_per_space_inr NUMERIC(12,2) NOT NULL
                              CHECK (expected_revenue_per_space_inr >= 0),
    adjusted_onboarding_cost_inr NUMERIC(12,2) NOT NULL
                              CHECK (adjusted_onboarding_cost_inr >= 0),
    attractiveness_score   NUMERIC(5,2) NOT NULL CHECK (attractiveness_score BETWEEN 0 AND 100),
    acquisition_score      NUMERIC(5,2) NOT NULL CHECK (acquisition_score BETWEEN 0 AND 100),
    segment_code           TEXT NOT NULL REFERENCES segment_rule(segment_code),
    rank_overall           INT NOT NULL CHECK (rank_overall >= 1),
    scored_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (parking_id, scenario_id),
    UNIQUE (scenario_id, rank_overall)
);
CREATE INDEX IF NOT EXISTS ix_lot_scenario_score_scenario
    ON lot_scenario_score (scenario_id, rank_overall);

CREATE TABLE IF NOT EXISTS parking_score_explanation (
    parking_id              INT PRIMARY KEY REFERENCES parking_lots(parking_id) ON DELETE CASCADE,
    positive_reason_flags   TEXT[] NOT NULL DEFAULT '{}',
    constraint_reason_flags TEXT[] NOT NULL DEFAULT '{}',
    recommendation          TEXT NOT NULL,
    methodology_note        TEXT NOT NULL,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lot_rank_stability (
    parking_id              INT PRIMARY KEY REFERENCES parking_lots(parking_id) ON DELETE CASCADE,
    scenarios_evaluated     SMALLINT NOT NULL CHECK (scenarios_evaluated >= 1),
    top_10_scenario_count   SMALLINT NOT NULL CHECK (top_10_scenario_count >= 0),
    rank_stability_pct      NUMERIC(6,2) NOT NULL CHECK (rank_stability_pct BETWEEN 0 AND 100),
    stability_class         TEXT NOT NULL CHECK (stability_class IN ('Very Stable','Stable','Sensitive','Highly Sensitive')),
    median_rank             NUMERIC(7,2) NOT NULL,
    min_rank                INT NOT NULL,
    max_rank                INT NOT NULL,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sensitivity_summary (
    scenario_id             SMALLINT PRIMARY KEY REFERENCES acquisition_scenario(scenario_id) ON DELETE CASCADE,
    top_10_overlap_count    SMALLINT NOT NULL CHECK (top_10_overlap_count >= 0),
    top_10_overlap_pct      NUMERIC(6,2) NOT NULL CHECK (top_10_overlap_pct BETWEEN 0 AND 100),
    spearman_rank_correlation NUMERIC(7,4),
    mean_abs_rank_change    NUMERIC(10,3),
    max_abs_rank_change     INT,
    segment_change_count    INT NOT NULL CHECK (segment_change_count >= 0),
    mean_score_change       NUMERIC(10,3),
    max_abs_score_change    NUMERIC(10,3),
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS locality_acquisition_summary (
    locality_id                    SMALLINT PRIMARY KEY REFERENCES dim_locality(locality_id),
    locality_name                  TEXT NOT NULL,
    city_name                      TEXT NOT NULL,
    micro_market_type              TEXT NOT NULL,
    opportunity_count              INT NOT NULL CHECK (opportunity_count >= 0),
    total_candidate_capacity_cars  INT NOT NULL CHECK (total_candidate_capacity_cars >= 0),
    average_demand_score           NUMERIC(5,2) NOT NULL CHECK (average_demand_score BETWEEN 0 AND 100),
    average_revenue_score          NUMERIC(5,2) NOT NULL CHECK (average_revenue_score BETWEEN 0 AND 100),
    average_competition_score      NUMERIC(5,2) NOT NULL CHECK (average_competition_score BETWEEN 0 AND 100),
    average_strategic_fit_score    NUMERIC(5,2) NOT NULL CHECK (average_strategic_fit_score BETWEEN 0 AND 100),
    average_feasibility_score      NUMERIC(5,2) NOT NULL CHECK (average_feasibility_score BETWEEN 0 AND 100),
    average_acquisition_score      NUMERIC(5,2) NOT NULL CHECK (average_acquisition_score BETWEEN 0 AND 100),
    expected_monthly_platform_revenue_inr NUMERIC(14,2) NOT NULL CHECK (expected_monthly_platform_revenue_inr >= 0),
    live_network_site_count        INT NOT NULL CHECK (live_network_site_count >= 0),
    live_network_capacity_cars     INT NOT NULL CHECK (live_network_capacity_cars >= 0),
    market_whitespace_score        NUMERIC(5,2) NOT NULL CHECK (market_whitespace_score BETWEEN 0 AND 100),
    high_priority_opportunity_count INT NOT NULL CHECK (high_priority_opportunity_count >= 0),
    generated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Baseline dashboard surface. The underlying feature view remains visible so
-- every displayed score can be traced back to raw/derived inputs.
CREATE OR REPLACE VIEW parking_acquisition_score AS
SELECT
    f.*,
    s.scenario_id,
    s.demand_score,
    s.revenue_score,
    s.competition_score,
    s.strategic_fit_score,
    s.feasibility_score,
    s.achievable_utilization,
    s.expected_monthly_platform_revenue_inr,
    s.expected_revenue_per_space_inr,
    s.adjusted_onboarding_cost_inr,
    s.attractiveness_score,
    s.acquisition_score,
    s.segment_code AS priority_segment,
    s.rank_overall AS acquisition_rank,
    rs.rank_stability_pct,
    rs.stability_class,
    e.positive_reason_flags,
    e.constraint_reason_flags,
    e.recommendation
FROM parking_acquisition_features f
JOIN acquisition_scenario sc ON sc.scenario_code = 'BASE_CASE'
JOIN lot_scenario_score s ON s.parking_id = f.parking_id AND s.scenario_id = sc.scenario_id
LEFT JOIN lot_rank_stability rs ON rs.parking_id = f.parking_id
LEFT JOIN parking_score_explanation e ON e.parking_id = f.parking_id;

CREATE OR REPLACE VIEW bd_acquisition_targets AS
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            ORDER BY CASE s.segment_code
                WHEN 'ACQUIRE_NOW' THEN 1 WHEN 'PURSUE' THEN 2
                WHEN 'DEVELOP' THEN 3 ELSE 4 END,
                s.acquisition_score DESC, s.rank_overall
        )::INT AS bd_priority_rank
    FROM lot_scenario_score s
    JOIN acquisition_scenario sc
      ON sc.scenario_code = 'BASE_CASE' AND s.scenario_id = sc.scenario_id
)
SELECT
    r.bd_priority_rank,
    r.rank_overall AS acquisition_rank,
    f.parking_id,
    f.lot_name AS parking_name,
    f.locality_name,
    r.acquisition_score,
    r.demand_score,
    r.revenue_score,
    r.competition_score,
    r.strategic_fit_score,
    r.feasibility_score,
    r.segment_code AS priority_segment,
    r.expected_monthly_platform_revenue_inr,
    f.estimated_onboarding_cost_inr,
    f.willingness_to_digitize,
    f.nearest_network_distance_km,
    e.positive_reason_flags,
    e.constraint_reason_flags,
    e.recommendation,
    (r.bd_priority_rank <= 10) AS is_top_10,
    (r.bd_priority_rank <= 20) AS is_top_20,
    (r.bd_priority_rank <= 50) AS is_top_50
FROM ranked r
JOIN parking_acquisition_features f ON f.parking_id = r.parking_id
LEFT JOIN parking_score_explanation e ON e.parking_id = r.parking_id
WHERE r.bd_priority_rank <= 50;

COMMENT ON VIEW parking_acquisition_features IS
  'PROVENANCE: derived (scoring). One row per candidate lot, aggregating '
  'source facts and deriving demand, competition and network inputs. '
  'Competitor capacity is absent in the public extract; pressure uses a '
  'count-based proxy and does not invent capacity.';
COMMENT ON VIEW parking_acquisition_score IS
  'PROVENANCE: derived (scoring). Baseline acquisition intelligence surface '
  'with scores, ranks, stability and reason flags.';
COMMENT ON VIEW bd_acquisition_targets IS
  'PROVENANCE: derived (scoring). Dynamic BD queue. Top-10/20/50 membership '
  'is calculated from the current baseline scores, never hard-coded.';
