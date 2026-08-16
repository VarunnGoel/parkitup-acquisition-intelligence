-- =====================================================================
-- 99_drop_all.sql : teardown, reverse dependency order
-- Use for rebuilds and for the validation harness. Destructive.
-- =====================================================================
SET search_path TO parkitup, public;

DROP TABLE IF EXISTS locality_acquisition_summary CASCADE;
DROP TABLE IF EXISTS sensitivity_summary          CASCADE;
DROP TABLE IF EXISTS lot_rank_stability           CASCADE;
DROP TABLE IF EXISTS parking_score_explanation    CASCADE;
DROP TABLE IF EXISTS lot_scenario_score           CASCADE;
DROP TABLE IF EXISTS acquisition_scenario         CASCADE;

DROP TABLE IF EXISTS lot_score              CASCADE;
DROP TABLE IF EXISTS lot_dimension_score    CASCADE;
DROP TABLE IF EXISTS segment_rule           CASCADE;
DROP TABLE IF EXISTS scoring_weight         CASCADE;
DROP TABLE IF EXISTS scoring_weight_set     CASCADE;

DROP TABLE IF EXISTS outreach_events        CASCADE;
DROP TABLE IF EXISTS outreach               CASCADE;

DROP TABLE IF EXISTS fact_lot_hourly_profile CASCADE;
DROP TABLE IF EXISTS fact_lot_daily         CASCADE;

DROP TABLE IF EXISTS existing_network_sites CASCADE;
DROP TABLE IF EXISTS lot_acquisition_terms  CASCADE;
DROP TABLE IF EXISTS competition            CASCADE;
DROP TABLE IF EXISTS location_demand        CASCADE;
DROP TABLE IF EXISTS parking_lots           CASCADE;
DROP TABLE IF EXISTS owners                 CASCADE;

DROP TABLE IF EXISTS dim_score_dimension    CASCADE;
DROP TABLE IF EXISTS data_lineage           CASCADE;
DROP TABLE IF EXISTS dim_funnel_stage       CASCADE;
DROP TABLE IF EXISTS dim_date               CASCADE;
DROP TABLE IF EXISTS dim_locality           CASCADE;
DROP TABLE IF EXISTS dim_city               CASCADE;
