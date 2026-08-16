-- =====================================================================
-- PARK It Up Acquisition Intelligence
-- 00_init.sql : schema namespace, conventions, and teardown helper
-- Target: PostgreSQL 14+
-- =====================================================================
--
-- NAMING CONVENTIONS (applied consistently across all schema files)
--   dim_*    : reference / dimension table, slowly changing, small row count
--   fact_*   : additive measures at a declared grain
--   <entity> : business entity tables carry a plain noun (parking_lots, owners)
--   *_id     : surrogate key, integer
--   *_code   : human-readable stable business key, TEXT, UNIQUE
--   *_inr    : monetary amount in Indian Rupees
--   *_m      : distance in metres
--   *_pct    : percentage expressed 0-100
--   *_rate   : ratio expressed 0-1
--
-- KEY POLICY
--   Every table has an explicit PRIMARY KEY.
--   Surrogate integer keys are used for joins; *_code columns exist so that
--   CSV extracts and Power BI reports stay readable and stable across reloads.
--
-- PROVENANCE POLICY
--   This project mixes publicly sourced and synthetic data. Provenance is
--   recorded in three places:
--     1. COMMENT ON TABLE  - declares the provenance class of the whole table.
--     2. record_source column - ONLY on tables where provenance genuinely
--        varies row by row (e.g. some parking lots come from OpenStreetMap,
--        others are synthetic fill). Adding it everywhere would be noise.
--     3. data_lineage - field-level PUBLIC / DERIVED / SYNTHETIC / ASSUMED /
--        CONFIG classification, source reference and generation method.
--   documentation/methodology/data_dictionary.md and data_lineage are the
--   human-readable and machine-readable provenance registers respectively.
--
-- DELIBERATE OMISSIONS (see documentation/decisions/ for full rationale)
--   - No two-wheeler capacity/pricing. Single vehicle class (cars) keeps the
--     revenue model explainable. Documented as a scoping assumption.
--   - No PostGIS. Distances are computed with the haversine formula in SQL /
--     Python so the project runs on a stock PostgreSQL install.
--   - Derived metrics (footfall estimates, density indices, acquisition
--     difficulty, days-to-conversion where non-trivial) are NOT stored as if
--     they were observed facts. They are computed in the scoring feature
--     layer. Storing a derived value next to a measured one is how analytical
--     projects quietly become indefensible.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS parkitup;

COMMENT ON SCHEMA parkitup IS
  'PARK It Up Acquisition Intelligence. Portfolio project. Contains a mix of '
  'publicly sourced reference data and clearly labelled synthetic data. '
  'Contains no confidential PARK It Up information.';

-- Keep search_path explicit in scripts rather than relying on session state.
SET search_path TO parkitup, public;
