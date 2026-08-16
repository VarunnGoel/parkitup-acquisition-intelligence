-- =====================================================================
-- 02_seed_calendar.sql : dim_date population
--
-- OBSERVATION WINDOW: 2025-08-01 to 2026-07-31 (365 days).
-- Rationale: a full year captures Delhi NCR seasonality that materially
-- affects parking demand - monsoon (Jul-Sep), the festive retail peak
-- (Oct-Nov) and the winter smog/GRAP period when restrictions bite. A
-- six-month window would have hidden all three. Recorded as assumption A-02.
-- At ~120 lots this yields roughly 43,800 rows in fact_lot_daily, which is
-- comfortable for both PostgreSQL and Power BI.
-- =====================================================================
SET search_path TO parkitup, public;

INSERT INTO dim_date (
    activity_date, day_of_week, day_name, is_weekend, is_public_holiday,
    month_num, month_name, quarter_num, year_num, iso_week
)
SELECT
    d::DATE                                    AS activity_date,
    EXTRACT(ISODOW FROM d)::SMALLINT            AS day_of_week,
    TRIM(TO_CHAR(d, 'Day'))                     AS day_name,
    EXTRACT(ISODOW FROM d) IN (6,7)             AS is_weekend,
    FALSE                                       AS is_public_holiday,
    EXTRACT(MONTH   FROM d)::SMALLINT           AS month_num,
    TRIM(TO_CHAR(d, 'Month'))                   AS month_name,
    EXTRACT(QUARTER FROM d)::SMALLINT           AS quarter_num,
    EXTRACT(YEAR    FROM d)::SMALLINT           AS year_num,
    EXTRACT(WEEK    FROM d)::SMALLINT           AS iso_week
FROM generate_series(DATE '2025-08-01', DATE '2026-07-31', INTERVAL '1 day') AS d
ON CONFLICT (activity_date) DO NOTHING;

-- ---------------------------------------------------------------------
-- Public holidays.
--
-- HONESTY NOTE: only fixed-date national holidays are set here, because those
-- are the ones that can be stated without risk of error. India's major
-- festivals (Holi, Diwali, Eid, Raksha Bandhan, Dussehra) follow lunar and
-- regional calendars, and asserting specific 2025-26 dates from memory would
-- be exactly the kind of quiet fabrication this project is trying to avoid.
-- the data pipeline must extend this list from an authoritative published calendar
-- before any holiday-effect claim is made. Until then, holiday analysis is
-- explicitly out of scope and is_public_holiday understates reality.
-- ---------------------------------------------------------------------
UPDATE dim_date
   SET is_public_holiday = TRUE
 WHERE activity_date IN (
    DATE '2025-08-15',   -- Independence Day
    DATE '2025-10-02',   -- Gandhi Jayanti
    DATE '2025-12-25',   -- Christmas Day
    DATE '2026-01-26'    -- Republic Day
 );
