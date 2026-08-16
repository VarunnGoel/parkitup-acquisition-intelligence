-- =====================================================================
-- 02_core_entities.sql : owners, parking lots, and their 1:1 attribute tables
-- Depends on: 01_reference.sql
-- =====================================================================
SET search_path TO parkitup, public;

-- ---------------------------------------------------------------------
-- owners
-- MODELLING DECISION: the brief placed owner attributes in a per-lot table.
-- Owner is promoted to its own entity because a single operator can control
-- several lots. That is a real BD lever ("this operator runs 4 lots in Saket,
-- one negotiation unlocks all four") and it removes the owner_type column
-- that was duplicated between parking_lots and owner_profiles.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS owners (
    owner_id                  INT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_code                TEXT     NOT NULL UNIQUE,
    owner_name                TEXT     NOT NULL,
    owner_type                TEXT     NOT NULL
                              CHECK (owner_type IN (
                                  'Individual','Family Trust','Private Company',
                                  'RWA','Mall Management','Government/Municipal',
                                  'Hospital/Institution')),
    years_operating           SMALLINT NOT NULL
                              CHECK (years_operating BETWEEN 0 AND 80),
    digital_payment_enabled   BOOLEAN  NOT NULL,
    management_system         TEXT     NOT NULL
                              CHECK (management_system IN (
                                  'None/Manual','Paper Register','Spreadsheet',
                                  'Basic POS','Third-party App')),
    willingness_to_digitize   SMALLINT NOT NULL
                              CHECK (willingness_to_digitize BETWEEN 1 AND 5),
    contract_flexibility      SMALLINT NOT NULL
                              CHECK (contract_flexibility BETWEEN 1 AND 5),
    decision_maker_accessible BOOLEAN  NOT NULL
);

COMMENT ON TABLE owners IS
  'PROVENANCE: synthetic. Simulated parking operators. Names, willingness and '
  'commercial posture are generated, NOT derived from any real operator or '
  'from PARK It Up records.';
COMMENT ON COLUMN owners.willingness_to_digitize IS
  '1-5 ordinal. 1 = actively resistant, 5 = already seeking a digital partner. '
  'Primary driver of the Acquisition Feasibility score.';
COMMENT ON COLUMN owners.contract_flexibility IS
  '1-5 ordinal. 1 = rigid, demands fixed rent and refuses revenue share. '
  '5 = open to commission-based terms and pilot arrangements.';
COMMENT ON COLUMN owners.decision_maker_accessible IS
  'Whether BD can reach the person who can actually sign. A common real-world '
  'blocker for RWA and Government/Municipal owners.';

-- ---------------------------------------------------------------------
-- parking_lots
-- The central entity. One row per physical parking facility.
--
-- REMOVED from the proposed field list, with reasons:
--   locality, city        -> normalised into dim_locality (FK)
--   owner_type            -> belongs to owners, was duplicated
--   operating_hours TEXT  -> split into is_24x7 / opens_at / closes_at so
--                            "invalid operating hours" is machine-checkable
--   current_occupancy     -> a point-in-time measure of a time series. Derived
--                            from fact_lot_daily, never stored here.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parking_lots (
    parking_id           INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_code             TEXT          NOT NULL UNIQUE,
    lot_name             TEXT          NOT NULL,
    locality_id          SMALLINT      NOT NULL
                         REFERENCES dim_locality (locality_id),
    owner_id             INT           NOT NULL
                         REFERENCES owners (owner_id),
    -- Geographic guard rail: the study area is Delhi NCR. These bounds turn
    -- "invalid coordinates" from a downstream data-quality report into an
    -- error the database itself refuses to accept.
    latitude             NUMERIC(9,6)  NOT NULL
                         CHECK (latitude  BETWEEN 28.30 AND 28.95),
    longitude            NUMERIC(9,6)  NOT NULL
                         CHECK (longitude BETWEEN 76.80 AND 77.60),
    parking_type         TEXT          NOT NULL
                         CHECK (parking_type IN (
                             'Surface Lot','Multi-Level (MLCP)','Basement',
                             'Mall Parking','Metro Station Parking',
                             'On-Street Authorised','Hospital Parking',
                             'Office Complex')),
    surface_type         TEXT          NOT NULL
                         CHECK (surface_type IN ('Paved','Unpaved','Mixed')),
    capacity_cars        SMALLINT      NOT NULL
                         CHECK (capacity_cars BETWEEN 10 AND 2000),
    hourly_rate_inr      NUMERIC(6,2)  NOT NULL
                         CHECK (hourly_rate_inr >= 0 AND hourly_rate_inr <= 500),
    monthly_pass_inr     NUMERIC(8,2)
                         CHECK (monthly_pass_inr IS NULL OR monthly_pass_inr >= 0),
    is_24x7              BOOLEAN       NOT NULL,
    opens_at             TIME,
    closes_at            TIME,
    has_covered_parking  BOOLEAN       NOT NULL DEFAULT FALSE,
    has_security_staff   BOOLEAN       NOT NULL DEFAULT FALSE,
    has_cctv             BOOLEAN       NOT NULL DEFAULT FALSE,
    record_source        TEXT          NOT NULL
                         CHECK (record_source IN ('public_osm','public_curated','synthetic')),
    source_name          TEXT          NOT NULL,
    source_reference     TEXT          NOT NULL,
    source_observed_on   DATE          NOT NULL,
    capacity_source_type TEXT          NOT NULL
                         CHECK (capacity_source_type IN ('PUBLIC','SYNTHETIC','ASSUMED')),
    price_source_type    TEXT          NOT NULL
                         CHECK (price_source_type IN ('PUBLIC','SYNTHETIC','ASSUMED')),
    hours_source_type    TEXT          NOT NULL
                         CHECK (hours_source_type IN ('PUBLIC','SYNTHETIC','ASSUMED')),
    amenities_source_type TEXT         NOT NULL
                         CHECK (amenities_source_type IN ('PUBLIC','SYNTHETIC','ASSUMED')),
    data_quality_flag    TEXT          NOT NULL
                         CHECK (data_quality_flag IN ('High','Medium','Fallback')),
    osm_id               BIGINT,       -- traceability back to the OSM element
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- A 24x7 lot must not declare opening hours; a non-24x7 lot must.
    CONSTRAINT ck_lot_hours_consistent CHECK (
        (is_24x7     AND opens_at IS NULL     AND closes_at IS NULL)
     OR (NOT is_24x7 AND opens_at IS NOT NULL AND closes_at IS NOT NULL)
    ),
    -- Only OSM-sourced rows may carry an osm_id.
    CONSTRAINT ck_lot_osm_id_only_when_osm CHECK (
        (record_source = 'public_osm') OR (osm_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_parking_lots_locality ON parking_lots (locality_id);
CREATE INDEX IF NOT EXISTS ix_parking_lots_owner    ON parking_lots (owner_id);

COMMENT ON TABLE parking_lots IS
  'PROVENANCE: MIXED - see record_source per row. Location, name, type and '
  'capacity may be public (OpenStreetMap or curated desk research); pricing '
  'and amenity flags are synthetic where not publicly listed. One row per '
  'physical parking facility.';
COMMENT ON COLUMN parking_lots.record_source IS
  'Row-level provenance. public_osm = extracted from OpenStreetMap; '
  'public_curated = manually recorded from public sources; synthetic = '
  'generated to give the model adequate coverage. Never mix these silently '
  'in a report without disclosing the split.';
COMMENT ON COLUMN parking_lots.capacity_source_type IS
  'Per-value provenance. OSM rows commonly lack capacity; when absent, the '
  'generator supplies a plausible synthetic value and labels it SYNTHETIC.';
COMMENT ON COLUMN parking_lots.source_reference IS
  'Stable URL or local reference that resolves the public geographic source.';
COMMENT ON COLUMN parking_lots.data_quality_flag IS
  'High = named OSM feature with published capacity; Medium = named feature '
  'with one or more synthetic attributes; Fallback = unnamed or curated record.';
COMMENT ON COLUMN parking_lots.capacity_cars IS
  'Four-wheeler bays only. Two-wheeler capacity is deliberately out of scope '
  'so the revenue model stays single-rate and explainable.';
COMMENT ON COLUMN parking_lots.closes_at IS
  'May be earlier than opens_at for lots that trade past midnight. Duration '
  'logic must handle the wrap-around; a naive closes_at > opens_at constraint '
  'would wrongly reject a legitimate 18:00-02:00 lot.';

-- ---------------------------------------------------------------------
-- location_demand  (1:1 with parking_lots)
-- Holds only derived public proximity/POI facts.
--
-- DELIBERATELY ABSENT: estimated_daily_footfall, commercial_density,
-- weekday_activity, weekend_activity. All four are derived quantities. They
-- are computed in the scoring feature layer from the columns below plus
-- locality attributes. Storing an estimate in the same table as a measurement
-- invites an interviewer to ask "how did you observe footfall?" - and there
-- is no good answer. Weekday/weekend activity is served instead by
-- fact_lot_hourly_profile, which is real (simulated) measurement at a
-- declared grain.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS location_demand (
    parking_id               INT      PRIMARY KEY
                             REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    metro_distance_m         INT      NOT NULL
                             CHECK (metro_distance_m BETWEEN 0 AND 20000),
    nearest_metro_station    TEXT,
    mall_distance_m          INT
                             CHECK (mall_distance_m IS NULL OR mall_distance_m BETWEEN 0 AND 20000),
    office_count_500m        SMALLINT NOT NULL CHECK (office_count_500m     >= 0),
    retail_count_500m        SMALLINT NOT NULL CHECK (retail_count_500m     >= 0),
    restaurant_count_500m    SMALLINT NOT NULL CHECK (restaurant_count_500m >= 0),
    hospital_count_1km       SMALLINT NOT NULL CHECK (hospital_count_1km    >= 0),
    education_count_1km      SMALLINT NOT NULL CHECK (education_count_1km   >= 0),
    transit_stop_count_500m  SMALLINT NOT NULL CHECK (transit_stop_count_500m >= 0),
    measured_on              DATE     NOT NULL,
    record_source            TEXT     NOT NULL
                             CHECK (record_source IN ('public_osm','public_curated','synthetic')),

    -- If a station name is recorded, the distance must be a real measurement.
    CONSTRAINT ck_demand_metro_named CHECK (
        nearest_metro_station IS NULL OR metro_distance_m IS NOT NULL
    )
);

COMMENT ON TABLE location_demand IS
  'PROVENANCE: derived from public OpenStreetMap coordinates. One row per '
  'parking lot. Contains reproducible distances and POI counts only - no '
  'footfall estimates or demand scores. The scoring engine builds indices from these inputs.';
COMMENT ON COLUMN location_demand.metro_distance_m IS
  'Straight-line distance to the nearest metro station entrance, metres. '
  'Walking distance would be better but is not freely available at scale; '
  'this is a documented proxy.';
COMMENT ON COLUMN location_demand.measured_on IS
  'Date the POI extract was taken. OSM changes over time, so POI counts are '
  'only reproducible with reference to an extract date.';

-- ---------------------------------------------------------------------
-- competition  (1:1 with parking_lots)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competition (
    parking_id                     INT          PRIMARY KEY
                                   REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    competitor_count_500m          SMALLINT     NOT NULL
                                   CHECK (competitor_count_500m >= 0),
    competitor_count_1km           SMALLINT     NOT NULL
                                   CHECK (competitor_count_1km >= 0),
    nearest_competitor_distance_m  INT
                                   CHECK (nearest_competitor_distance_m IS NULL
                                          OR nearest_competitor_distance_m BETWEEN 0 AND 20000),
    competitor_avg_hourly_rate_inr NUMERIC(6,2)
                                   CHECK (competitor_avg_hourly_rate_inr IS NULL
                                          OR competitor_avg_hourly_rate_inr >= 0),
    competitor_total_capacity_1km  INT
                                   CHECK (competitor_total_capacity_1km IS NULL
                                          OR competitor_total_capacity_1km >= 0),
    aggregator_listed_count_1km    SMALLINT     NOT NULL DEFAULT 0
                                   CHECK (aggregator_listed_count_1km >= 0),
    measured_on                    DATE         NOT NULL,
    record_source                  TEXT         NOT NULL
                                   CHECK (record_source IN ('public_osm','public_curated','synthetic')),

    -- A 1 km radius strictly contains a 500 m radius.
    CONSTRAINT ck_competitor_radius_nesting
        CHECK (competitor_count_1km >= competitor_count_500m),
    -- Zero competitors within 1 km means there is no nearest competitor to
    -- measure, and no competitor pricing to average.
    CONSTRAINT ck_competitor_presence_consistent CHECK (
        (competitor_count_1km = 0
            AND nearest_competitor_distance_m IS NULL
            AND competitor_avg_hourly_rate_inr IS NULL)
     OR (competitor_count_1km > 0
            AND nearest_competitor_distance_m IS NOT NULL)
    ),
    -- Lots already listed by a rival aggregator must be competitors we found.
    CONSTRAINT ck_aggregator_within_competitors
        CHECK (aggregator_listed_count_1km <= competitor_count_1km)
);

COMMENT ON TABLE competition IS
  'PROVENANCE: MIXED. Competitor counts and distances are derived from public '
  'OSM parking amenities; competitor pricing is synthetic because '
  'informal Delhi NCR parking rates are not published. One row per lot.';
COMMENT ON COLUMN competition.aggregator_listed_count_1km IS
  'Count of nearby lots already listed on a rival parking platform. Replaces '
  'the vaguer "existing_platform_presence" - this is countable and testable. '
  'High values signal a market a competitor has already digitised.';
COMMENT ON CONSTRAINT ck_competitor_radius_nesting ON competition IS
  'Radius nesting rule. A frequent and silent ETL bug: computing the two '
  'counts in separate passes and letting the 500m figure exceed the 1km one.';

-- ---------------------------------------------------------------------
-- lot_acquisition_terms  (1:1 with parking_lots)
-- Lot-level deal economics. Split from owners because commission and
-- onboarding cost are negotiated per site, while willingness and contract
-- posture are properties of the operator.
--
-- DELIBERATELY ABSENT: acquisition_difficulty. That is the OUTPUT of the
-- Feasibility score, computed from owner willingness, documentation
-- readiness, operational complexity and owner type. Storing it as an input
-- would make the scoring circular.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lot_acquisition_terms (
    parking_id                    INT           PRIMARY KEY
                                  REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    expected_commission_pct       NUMERIC(4,2)  NOT NULL
                                  CHECK (expected_commission_pct BETWEEN 0 AND 40),
    estimated_onboarding_cost_inr NUMERIC(10,2) NOT NULL
                                  CHECK (estimated_onboarding_cost_inr >= 0),
    documentation_readiness       SMALLINT      NOT NULL
                                  CHECK (documentation_readiness BETWEEN 1 AND 5),
    operational_complexity        SMALLINT      NOT NULL
                                  CHECK (operational_complexity BETWEEN 1 AND 5),
    exclusivity_possible          BOOLEAN       NOT NULL,
    requires_capex                BOOLEAN       NOT NULL,
    estimated_setup_days          SMALLINT      NOT NULL
                                  CHECK (estimated_setup_days BETWEEN 0 AND 365),
    quoted_on                     DATE          NOT NULL
);

COMMENT ON TABLE lot_acquisition_terms IS
  'PROVENANCE: synthetic. Simulated per-site deal terms. These are NOT PARK '
  'It Up commercial terms and must not be presented as such. One row per lot.';
COMMENT ON COLUMN lot_acquisition_terms.expected_commission_pct IS
  'Commission percentage the operator is modelled as willing to concede on '
  'platform-originated bookings. Central assumption of the revenue model; '
  'sensitivity-tested in the scoring engine (business question 10).';
COMMENT ON COLUMN lot_acquisition_terms.operational_complexity IS
  '1-5 ordinal. 1 = plug-and-play signage only. 5 = boom barriers, multiple '
  'entry points, shared access rights, or municipal permissions required.';

-- ---------------------------------------------------------------------
-- existing_network_sites
-- Supports the Strategic Fit pillar, which needs distance from the current
-- footprint. Real PARK It Up inventory is confidential and is NOT used. This
-- table is an explicitly hypothetical network so that coverage-gap logic can
-- be demonstrated and audited.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS existing_network_sites (
    network_site_id  INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_code        TEXT          NOT NULL UNIQUE,
    locality_id      SMALLINT      NOT NULL
                     REFERENCES dim_locality (locality_id),
    latitude         NUMERIC(9,6)  NOT NULL
                     CHECK (latitude  BETWEEN 28.30 AND 28.95),
    longitude        NUMERIC(9,6)  NOT NULL
                     CHECK (longitude BETWEEN 76.80 AND 77.60),
    capacity_cars    SMALLINT      NOT NULL CHECK (capacity_cars BETWEEN 10 AND 2000),
    live_since       DATE          NOT NULL,
    site_status      TEXT          NOT NULL
                     CHECK (site_status IN ('Live','Paused'))
);

COMMENT ON TABLE existing_network_sites IS
  'PROVENANCE: synthetic - HYPOTHETICAL network footprint. This does NOT '
  'represent real PARK It Up inventory and contains no confidential data. It '
  'exists so the Strategic Fit pillar has a defined baseline to measure '
  'coverage gaps and cannibalisation risk against.';
