-- =====================================================================
-- 03_facts.sql : operational performance facts
-- Depends on: 02_core_entities.sql
-- =====================================================================
SET search_path TO parkitup, public;

-- ---------------------------------------------------------------------
-- fact_lot_daily
-- GRAIN: one row per parking lot per calendar day.
--
-- GRAIN DECISION (important, and the thing to defend in an interview):
-- The brief proposed a single performance table keyed by date AND hour. At
-- roughly 120 lots x 365 days x 24 hours that is ~1.05 million rows of
-- synthetic data to support questions that are almost all asked at daily or
-- typical-hour grain. The design here splits that into two tables at two
-- honest grains:
--     fact_lot_daily           - the additive daily time series (~22k rows)
--     fact_lot_hourly_profile  - a typical-week shape per lot (~5.8k rows)
-- This preserves peak-hour analysis while keeping the dataset small enough to
-- reason about, load into Power BI, and hand-verify.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_lot_daily (
    parking_id               INT           NOT NULL
                             REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    activity_date            DATE          NOT NULL
                             REFERENCES dim_date (activity_date),
    -- Stored 0-1 rather than 0-100 so the "occupancy > 100%" data-quality
    -- rule is enforced by the database instead of discovered later.
    peak_occupancy_rate      NUMERIC(5,4)  NOT NULL
                             CHECK (peak_occupancy_rate BETWEEN 0 AND 1),
    avg_occupancy_rate       NUMERIC(5,4)  NOT NULL
                             CHECK (avg_occupancy_rate BETWEEN 0 AND 1),
    vehicle_entries          SMALLINT      NOT NULL CHECK (vehicle_entries >= 0),
    platform_bookings        SMALLINT      NOT NULL CHECK (platform_bookings >= 0),
    booking_cancellations    SMALLINT      NOT NULL CHECK (booking_cancellations >= 0),
    gross_parking_revenue_inr NUMERIC(10,2) NOT NULL
                             CHECK (gross_parking_revenue_inr >= 0),
    avg_park_duration_hours  NUMERIC(4,2)  NOT NULL
                             CHECK (avg_park_duration_hours > 0 AND avg_park_duration_hours <= 24),

    CONSTRAINT pk_fact_lot_daily PRIMARY KEY (parking_id, activity_date),
    -- Platform bookings are a subset of all vehicles that used the lot.
    CONSTRAINT ck_daily_bookings_subset_of_entries
        CHECK (platform_bookings <= vehicle_entries),
    -- You cannot cancel more than was booked.
    CONSTRAINT ck_daily_cancellations_subset_of_bookings
        CHECK (booking_cancellations <= platform_bookings),
    -- Average occupancy cannot exceed the day's peak.
    CONSTRAINT ck_daily_avg_not_above_peak
        CHECK (avg_occupancy_rate <= peak_occupancy_rate)
);

CREATE INDEX IF NOT EXISTS ix_fact_lot_daily_date ON fact_lot_daily (activity_date);

COMMENT ON TABLE fact_lot_daily IS
  'PROVENANCE: synthetic. Simulated daily operating performance. These are '
  'NOT observed PARK It Up or operator figures. Grain: one row per lot per day.';
COMMENT ON COLUMN fact_lot_daily.vehicle_entries IS
  'Total vehicles entering that day, across all channels. NOTE: daily entries '
  'legitimately EXCEED capacity_cars because of turnover - a 100-bay lot can '
  'serve 400 vehicles a day. Only concurrent occupancy is capped at capacity, '
  'which is why occupancy is modelled as a rate and entries as a count.';
COMMENT ON COLUMN fact_lot_daily.platform_bookings IS
  'Subset of vehicle_entries originating from the platform. The commission '
  'base for revenue modelling - platform contribution is earned on these '
  'bookings only, not on total lot revenue.';
COMMENT ON COLUMN fact_lot_daily.gross_parking_revenue_inr IS
  'Total revenue collected by the OPERATOR for the day. Platform contribution '
  'is a modelled share of the platform-booked portion, computed in the scoring engine.';
COMMENT ON CONSTRAINT ck_daily_avg_not_above_peak ON fact_lot_daily IS
  'Internal consistency: a mean cannot exceed the maximum of the same series.';

-- ---------------------------------------------------------------------
-- fact_lot_hourly_profile
-- GRAIN: one row per lot per day_type per hour-of-day.
-- A typical-week demand shape, not a dated time series. Answers "when does
-- this lot peak, and does its peak align with the surrounding land use?"
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_lot_hourly_profile (
    parking_id          INT           NOT NULL
                        REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    day_type            TEXT          NOT NULL
                        CHECK (day_type IN ('Weekday','Weekend')),
    hour_of_day         SMALLINT      NOT NULL
                        CHECK (hour_of_day BETWEEN 0 AND 23),
    avg_occupancy_rate  NUMERIC(5,4)  NOT NULL
                        CHECK (avg_occupancy_rate BETWEEN 0 AND 1),
    avg_entries         NUMERIC(6,2)  NOT NULL CHECK (avg_entries >= 0),

    CONSTRAINT pk_fact_lot_hourly_profile
        PRIMARY KEY (parking_id, day_type, hour_of_day)
);

COMMENT ON TABLE fact_lot_hourly_profile IS
  'PROVENANCE: synthetic. Typical-week hourly demand shape per lot. Grain: '
  'lot x day_type x hour. Deliberately NOT a dated time series - see the '
  'grain decision note in this file.';
COMMENT ON COLUMN fact_lot_hourly_profile.day_type IS
  'Weekday or Weekend only. Holidays are not profiled separately: the volume '
  'of synthetic data required would not change any scoring conclusion. Joins '
  'to dim_date.day_type, which additionally emits Holiday - scoring maps '
  'Holiday to the Weekend profile and documents that simplification.';
