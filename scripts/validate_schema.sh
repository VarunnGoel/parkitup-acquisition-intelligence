#!/usr/bin/env bash
# =====================================================================
# validate_schema.sh - execute and prove the schema against real PostgreSQL
#
# WHY THIS SCRIPT EXISTS
#   The development sandbox has no PostgreSQL and no network route to one, so
#   the DDL cannot be executed where it is written. This script closes that
#   loop: you run it on your machine, it writes a detailed report into
#   validation/report.txt inside this repository, and that report can then be
#   read and acted on directly.
#
#   It does not merely check that the SQL parses. It:
#     1. builds the schema in a THROWAWAY database (your real data is never
#        touched),
#     2. applies the baseline seeds,
#     3. fires deliberately invalid statements and asserts the database
#        REJECTS each one - a constraint that has never been tested against
#        bad input is only a comment,
#     4. asserts one valid insert SUCCEEDS, guarding against a schema so
#        strict it accepts nothing,
#     5. dumps the catalogue PostgreSQL actually built,
#     6. runs the data-quality checks to confirm they execute.
#
# USAGE
#   bash scripts/validate_schema.sh
#
# CONFIGURATION (override by exporting before running)
#   PGHOST, PGPORT, PGUSER, PGPASSWORD  - standard libpq variables
#   VALIDATE_DB                         - scratch database name
#
# SAFETY
#   The scratch database is dropped and recreated on every run. The script
#   refuses to proceed if VALIDATE_DB looks like a real database name.
# =====================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

VALIDATE_DB="${VALIDATE_DB:-parkitup_validate}"
REPORT_DIR="$REPO_ROOT/validation"
REPORT="$REPORT_DIR/report.txt"
mkdir -p "$REPORT_DIR"

case "$VALIDATE_DB" in
  postgres|template0|template1|parkitup|parkitup_prod)
    echo "REFUSING to use '$VALIDATE_DB' as a scratch database." >&2
    exit 2 ;;
esac

PASS=0; FAIL=0
: > "$REPORT"

log()  { printf '%s\n' "$*" | tee -a "$REPORT"; }
head1() { log ""; log "=============================================================="; log "$*"; log "=============================================================="; }

ok()   { PASS=$((PASS+1)); log "  PASS  $*"; }
bad()  { FAIL=$((FAIL+1)); log "  FAIL  $*"; }

log "PARK It Up Acquisition Intelligence - schema validation report"
log "generated : $(date '+%Y-%m-%d %H:%M:%S %Z')"
log "repo      : $REPO_ROOT"
log "scratch db: $VALIDATE_DB"

# ---------------------------------------------------------------------
head1 "0. ENVIRONMENT"
if ! command -v psql >/dev/null 2>&1; then
  log "  FAIL  psql not found on PATH."
  log ""
  log "  Common fixes:"
  log "    Homebrew    : export PATH=\"/opt/homebrew/opt/postgresql@16/bin:\$PATH\""
  log "    Postgres.app: export PATH=\"/Applications/Postgres.app/Contents/Versions/latest/bin:\$PATH\""
  exit 1
fi
log "  psql      : $(command -v psql)"
log "  version   : $(psql --version 2>&1)"

if ! psql -d postgres -Atc 'SELECT 1' >/dev/null 2>&1; then
  log "  FAIL  cannot connect to the 'postgres' database."
  log "        Check the server is running and PGUSER/PGHOST are correct."
  log "        Detail: $(psql -d postgres -Atc 'SELECT 1' 2>&1 | head -3)"
  exit 1
fi
log "  server    : reachable"
log "  server ver: $(psql -d postgres -Atc 'SHOW server_version' 2>&1)"

# ---------------------------------------------------------------------
head1 "1. BUILD SCHEMA IN SCRATCH DATABASE"
dropdb --if-exists "$VALIDATE_DB" >/dev/null 2>&1
if ! createdb "$VALIDATE_DB" 2>>"$REPORT"; then
  log "  FAIL  could not create scratch database '$VALIDATE_DB'"
  exit 1
fi
log "  created scratch database '$VALIDATE_DB'"

PSQL_STRICT=(psql -d "$VALIDATE_DB" -v ON_ERROR_STOP=1 -q)

for f in database/schema/00_init.sql \
         database/schema/01_reference.sql \
         database/schema/02_core_entities.sql \
         database/schema/03_facts.sql \
         database/schema/04_bd_pipeline.sql \
         database/schema/05_scoring.sql ; do
  if out=$("${PSQL_STRICT[@]}" -f "$f" 2>&1); then
    ok "applied $f"
  else
    bad "applied $f"
    log "        ---- psql output ----"
    printf '%s\n' "$out" | sed 's/^/        /' | tee -a /dev/null >> "$REPORT"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
done

# ---------------------------------------------------------------------
head1 "2. APPLY REFERENCE SEEDS"
for f in database/seeds/01_seed_reference.sql \
         database/seeds/02_seed_calendar.sql ; do
  if out=$("${PSQL_STRICT[@]}" -f "$f" 2>&1); then
    ok "applied $f"
  else
    bad "applied $f"
    printf '%s\n' "$out" | sed 's/^/        /' >> "$REPORT"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
done

log ""
log "  seeded row counts:"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT 'dim_city',            COUNT(*) FROM parkitup.dim_city
  UNION ALL SELECT 'dim_date',            COUNT(*) FROM parkitup.dim_date
  UNION ALL SELECT 'dim_date holidays',   COUNT(*) FROM parkitup.dim_date WHERE is_public_holiday
  UNION ALL SELECT 'dim_funnel_stage',    COUNT(*) FROM parkitup.dim_funnel_stage
  UNION ALL SELECT 'dim_score_dimension', COUNT(*) FROM parkitup.dim_score_dimension
  UNION ALL SELECT 'scoring_weight_set',  COUNT(*) FROM parkitup.scoring_weight_set
  UNION ALL SELECT 'scoring_weight',      COUNT(*) FROM parkitup.scoring_weight
  UNION ALL SELECT 'segment_rule',        COUNT(*) FROM parkitup.segment_rule
  ORDER BY 1;" 2>&1 | sed 's/^/    /' | tee -a "$REPORT"

# Functional test of seeded config, not just that the INSERT ran.
sum_bad=$(psql -d "$VALIDATE_DB" -Atc "
  SELECT COUNT(*) FROM (
    SELECT weight_set_id FROM parkitup.scoring_weight
    GROUP BY weight_set_id HAVING ABS(SUM(weight) - 1.0) > 0.0001) x;" 2>&1)
if [ "$sum_bad" = "0" ]; then
  ok "every scoring_weight_set sums to exactly 1.0 (rule DQ-020)"
else
  bad "weight sets not summing to 1.0: $sum_bad"
fi

cal=$(psql -d "$VALIDATE_DB" -Atc "
  SELECT CASE WHEN COUNT(*) = (MAX(activity_date) - MIN(activity_date) + 1)
              THEN 'contiguous' ELSE 'GAPS' END FROM parkitup.dim_date;" 2>&1)
if [ "$cal" = "contiguous" ]; then
  ok "dim_date is gap-free across its span (rule DQ-042)"
else
  bad "dim_date has gaps: $cal"
fi

gen=$(psql -d "$VALIDATE_DB" -Atc "
  SELECT COUNT(*) FROM parkitup.dim_date
   WHERE day_type <> CASE WHEN is_public_holiday THEN 'Holiday'
                          WHEN is_weekend THEN 'Weekend' ELSE 'Weekday' END;" 2>&1)
if [ "$gen" = "0" ]; then
  ok "dim_date.day_type generated column agrees with its inputs on all rows"
else
  bad "day_type generated column mismatch on $gen row(s)"
fi

# ---------------------------------------------------------------------
head1 "3. CONSTRAINT PROBES (invalid input must be REJECTED)"

# Minimal valid fixtures so the probes have something to hang off.
psql -d "$VALIDATE_DB" -v ON_ERROR_STOP=1 -q <<'SQL' 2>>"$REPORT"
SET search_path TO parkitup, public;
INSERT INTO dim_locality (locality_id, city_id, locality_name, micro_market_type,
    has_metro_station, metro_line_count, population_density_band, record_source)
VALUES (901, 1, 'ZZ Validation Locality', 'Commercial', TRUE, 1, 'High', 'public_curated');
INSERT INTO owners (owner_code, owner_name, owner_type, years_operating,
    digital_payment_enabled, management_system, willingness_to_digitize,
    contract_flexibility, decision_maker_accessible)
VALUES ('OWN-VAL1', 'ZZ Validation Owner', 'Private Company', 5,
    TRUE, 'Spreadsheet', 4, 3, TRUE);
SQL

OWNER_ID=$(psql -d "$VALIDATE_DB" -Atc \
  "SELECT owner_id FROM parkitup.owners WHERE owner_code='OWN-VAL1';" 2>&1)

# expect_fail <label> <sql>   : the statement MUST error
expect_fail() {
  local label="$1"; shift
  local sql="$1"
  if psql -d "$VALIDATE_DB" -v ON_ERROR_STOP=1 -q -c "SET search_path TO parkitup, public; $sql" >/dev/null 2>&1; then
    bad "$label - accepted invalid data (constraint NOT working)"
  else
    ok "$label - correctly rejected"
  fi
}
# expect_ok <label> <sql>     : the statement MUST succeed
expect_ok() {
  local label="$1"; shift
  local sql="$1"
  local out
  if out=$(psql -d "$VALIDATE_DB" -v ON_ERROR_STOP=1 -q -c "SET search_path TO parkitup, public; $sql" 2>&1); then
    ok "$label - accepted as expected"
  else
    bad "$label - valid data was REJECTED"
    printf '%s\n' "$out" | sed 's/^/        /' >> "$REPORT"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

LOT_COLS="lot_code, lot_name, locality_id, owner_id, latitude, longitude, parking_type, surface_type, capacity_cars, hourly_rate_inr, is_24x7, record_source, source_name, source_reference, source_observed_on, capacity_source_type, price_source_type, hours_source_type, amenities_source_type, data_quality_flag"
LOT_PROV="'Validation Fixture','validation://fixture',CURRENT_DATE,'SYNTHETIC','SYNTHETIC','ASSUMED','SYNTHETIC','Fallback'"

# --- geography ---
expect_fail "latitude outside the Delhi NCR bounding box" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V01','Bad Lat',901,$OWNER_ID,19.0760,77.10,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV);"
expect_fail "longitude outside the Delhi NCR bounding box" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V02','Bad Lon',901,$OWNER_ID,28.60,72.87,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV);"

# --- domain ranges ---
expect_fail "capacity below the 10-bay floor" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V03','Tiny',901,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',5,20,TRUE,'synthetic',$LOT_PROV);"
expect_fail "negative hourly tariff" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V04','Negative',901,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',100,-10,TRUE,'synthetic',$LOT_PROV);"
expect_fail "parking_type outside the permitted vocabulary" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V05','Bad Type',901,$OWNER_ID,28.60,77.20,'Helipad','Paved',100,20,TRUE,'synthetic',$LOT_PROV);"

# --- business rules ---
expect_fail "24x7 lot that also declares opening hours" \
  "INSERT INTO parking_lots ($LOT_COLS, opens_at, closes_at) VALUES ('PKL-V06','Contradiction',901,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV,'08:00','20:00');"
expect_fail "non-24x7 lot with no opening hours" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V07','No Hours',901,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',100,20,FALSE,'synthetic',$LOT_PROV);"
expect_fail "synthetic record carrying an osm_id" \
  "INSERT INTO parking_lots ($LOT_COLS, osm_id) VALUES ('PKL-V08','Fake OSM',901,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV,12345);"

# --- the one that must succeed ---
expect_ok "a fully valid parking lot" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V99','ZZ Valid Lot',901,$OWNER_ID,28.6304,77.2177,'Multi-Level (MLCP)','Paved',250,30,TRUE,'synthetic',$LOT_PROV);"

LOT_ID=$(psql -d "$VALIDATE_DB" -Atc \
  "SELECT parking_id FROM parkitup.parking_lots WHERE lot_code='PKL-V99';" 2>&1)
expect_fail "duplicate lot_code" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V99','ZZ Dup',901,$OWNER_ID,28.6304,77.2177,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV);"
expect_fail "foreign key to a non-existent locality" \
  "INSERT INTO parking_lots ($LOT_COLS) VALUES ('PKL-V10','Orphan',9999,$OWNER_ID,28.60,77.20,'Surface Lot','Paved',100,20,TRUE,'synthetic',$LOT_PROV);"

# --- competition nesting ---
expect_fail "competitor count at 500m exceeding the 1km count" \
  "INSERT INTO competition (parking_id, competitor_count_500m, competitor_count_1km, nearest_competitor_distance_m, measured_on, record_source) VALUES ($LOT_ID, 9, 3, 200, CURRENT_DATE, 'public_osm');"
expect_fail "zero competitors but a nearest-competitor distance recorded" \
  "INSERT INTO competition (parking_id, competitor_count_500m, competitor_count_1km, nearest_competitor_distance_m, measured_on, record_source) VALUES ($LOT_ID, 0, 0, 150, CURRENT_DATE, 'public_osm');"
expect_fail "aggregator-listed count exceeding total competitors" \
  "INSERT INTO competition (parking_id, competitor_count_500m, competitor_count_1km, nearest_competitor_distance_m, aggregator_listed_count_1km, measured_on, record_source) VALUES ($LOT_ID, 1, 2, 150, 5, CURRENT_DATE, 'public_osm');"
expect_ok  "valid competition row" \
  "INSERT INTO competition (parking_id, competitor_count_500m, competitor_count_1km, nearest_competitor_distance_m, competitor_avg_hourly_rate_inr, competitor_total_capacity_1km, aggregator_listed_count_1km, measured_on, record_source) VALUES ($LOT_ID, 2, 5, 180, 25.00, 600, 1, CURRENT_DATE, 'public_osm');"

# --- daily facts ---
DAY=$(psql -d "$VALIDATE_DB" -Atc "SELECT MIN(activity_date) FROM parkitup.dim_date;" 2>&1)
FD_COLS="parking_id, activity_date, peak_occupancy_rate, avg_occupancy_rate, vehicle_entries, platform_bookings, booking_cancellations, gross_parking_revenue_inr, avg_park_duration_hours"
expect_fail "occupancy above 100%" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',1.5000,0.5000,100,10,1,5000,2.5);"
expect_fail "mean occupancy above peak occupancy" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.4000,0.9000,100,10,1,5000,2.5);"
expect_fail "platform bookings exceeding total vehicle entries" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.8000,0.5000,50,80,1,5000,2.5);"
expect_fail "cancellations exceeding bookings" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.8000,0.5000,100,10,25,5000,2.5);"
expect_fail "negative revenue" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.8000,0.5000,100,10,1,-500,2.5);"
expect_fail "average parking duration above 24 hours" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.8000,0.5000,100,10,1,5000,30.0);"
expect_ok  "valid daily fact row, with entries deliberately exceeding capacity (turnover)" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.9200,0.6100,800,120,6,42000,2.75);"
expect_fail "duplicate daily fact for the same lot and date" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'$DAY',0.5000,0.3000,100,10,1,5000,2.5);"
expect_fail "daily fact for a date absent from dim_date" \
  "INSERT INTO fact_lot_daily ($FD_COLS) VALUES ($LOT_ID,'1999-01-01',0.5000,0.3000,100,10,1,5000,2.5);"

# --- outreach ---
expect_fail "lost lead with no loss reason" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, assigned_bd_rep) VALUES ($LOT_ID,'Cold Call','2026-01-10',3,2,'Lost','BD-01');"
expect_fail "active lead carrying a loss reason" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, lost_reason, assigned_bd_rep) VALUES ($LOT_ID,'Cold Call','2026-01-10',3,2,'Active','No Response','BD-01');"
expect_fail "won lead with no conversion date" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, assigned_bd_rep) VALUES ($LOT_ID,'Referral','2026-01-10',4,7,'Won','BD-01');"
expect_fail "conversion dated before first contact" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, conversion_date, assigned_bd_rep) VALUES ($LOT_ID,'Referral','2026-03-10',4,7,'Won','2026-01-01','BD-01');"
expect_fail "contact attempts recorded with no first contact date" \
  "INSERT INTO outreach (parking_id, lead_source, contact_attempts, furthest_stage_id, pipeline_status, assigned_bd_rep) VALUES ($LOT_ID,'Referral',5,2,'Active','BD-01');"
expect_ok  "valid won lead" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, conversion_date, documents_available, owner_interest_level, assigned_bd_rep) VALUES ($LOT_ID,'Referral','2026-01-10',4,7,'Won','2026-02-19',TRUE,5,'BD-01');"

dtc=$(psql -d "$VALIDATE_DB" -Atc \
  "SELECT days_to_conversion FROM parkitup.outreach WHERE parking_id=$LOT_ID;" 2>&1)
if [ "$dtc" = "40" ]; then
  ok "days_to_conversion generated column computed correctly (2026-01-10 -> 2026-02-19 = 40)"
else
  bad "days_to_conversion expected 40, got '$dtc'"
fi

expect_fail "second lead for a lot that already has one (1:1 rule)" \
  "INSERT INTO outreach (parking_id, lead_source, first_contact_date, contact_attempts, furthest_stage_id, pipeline_status, assigned_bd_rep) VALUES ($LOT_ID,'Broker','2026-01-10',1,2,'Active','BD-02');"

LEAD_ID=$(psql -d "$VALIDATE_DB" -Atc \
  "SELECT lead_id FROM parkitup.outreach WHERE parking_id=$LOT_ID;" 2>&1)
expect_ok  "valid funnel event" \
  "INSERT INTO outreach_events (lead_id, stage_id, event_date, channel) VALUES ($LEAD_ID,1,'2026-01-10','Phone');"
expect_fail "the same stage logged twice for one lead" \
  "INSERT INTO outreach_events (lead_id, stage_id, event_date, channel) VALUES ($LEAD_ID,1,'2026-01-12','Email');"

# --- scoring config ---
expect_fail "a second default weight set (partial unique index)" \
  "UPDATE scoring_weight_set SET is_default = TRUE WHERE weight_set_code = 'EQUAL_WEIGHT';"
expect_fail "weight above 1.0" \
  "INSERT INTO scoring_weight (weight_set_id, dimension_code, weight) VALUES (1,'DEMAND',1.5);"
expect_fail "unknown scoring dimension" \
  "INSERT INTO scoring_weight (weight_set_id, dimension_code, weight) VALUES (1,'VIBES',0.1);"
expect_fail "subscore above 100" \
  "INSERT INTO lot_dimension_score (parking_id, weight_set_id, dimension_code, subscore, weight_applied, weighted_contribution) VALUES ($LOT_ID,1,'DEMAND',150,0.30,45);"
expect_fail "segment code outside the permitted four" \
  "INSERT INTO lot_score (parking_id, weight_set_id, attractiveness_score, feasibility_score, acquisition_score, segment_code) VALUES ($LOT_ID,1,70,70,70,'MAYBE');"
expect_ok  "valid lot_score row" \
  "INSERT INTO lot_score (parking_id, weight_set_id, attractiveness_score, feasibility_score, acquisition_score, segment_code, rank_overall) VALUES ($LOT_ID,1,72.50,64.00,70.25,'ACQUIRE_NOW',1);"
expect_fail "the same lot scored twice under one weight set" \
  "INSERT INTO lot_score (parking_id, weight_set_id, attractiveness_score, feasibility_score, acquisition_score, segment_code) VALUES ($LOT_ID,1,50,50,50,'PURSUE');"
expect_ok  "the same lot scored under a DIFFERENT weight set (sensitivity analysis must coexist)" \
  "INSERT INTO lot_score (parking_id, weight_set_id, attractiveness_score, feasibility_score, acquisition_score, segment_code, rank_overall) VALUES ($LOT_ID,2,68.00,64.00,66.40,'ACQUIRE_NOW',1);"

# --- cascade behaviour ---
before=$(psql -d "$VALIDATE_DB" -Atc "SELECT COUNT(*) FROM parkitup.outreach_events;" 2>&1)
psql -d "$VALIDATE_DB" -q -c "DELETE FROM parkitup.parking_lots WHERE lot_code='PKL-V99';" >/dev/null 2>&1
after=$(psql -d "$VALIDATE_DB" -Atc "SELECT COUNT(*) FROM parkitup.outreach_events;" 2>&1)
orphans=$(psql -d "$VALIDATE_DB" -Atc "
  SELECT (SELECT COUNT(*) FROM parkitup.competition)
       + (SELECT COUNT(*) FROM parkitup.fact_lot_daily)
       + (SELECT COUNT(*) FROM parkitup.outreach)
       + (SELECT COUNT(*) FROM parkitup.lot_score);" 2>&1)
if [ "$orphans" = "0" ] && [ "$after" = "0" ]; then
  ok "deleting a lot cascaded cleanly to competition, facts, outreach, events and scores (was $before events)"
else
  bad "cascade delete left orphans (dependent rows remaining: $orphans, events: $after)"
fi

# ---------------------------------------------------------------------
# Remove the validation fixtures. Without this, the locality and owner created
# above survive the cascade test with no lots attached, and rules DQ-040 and
# DQ-041 (dead reference rows) fire in section 4 - a false alarm caused by the
# harness itself, which would train the reader to ignore real warnings.
psql -d "$VALIDATE_DB" -q >/dev/null 2>&1 <<'SQL'
SET search_path TO parkitup, public;
DELETE FROM owners       WHERE owner_code   = 'OWN-VAL1';
DELETE FROM dim_locality WHERE locality_id  = 901;
SQL
fixtures_left=$(psql -d "$VALIDATE_DB" -Atc "
  SELECT (SELECT COUNT(*) FROM parkitup.owners       WHERE owner_code  = 'OWN-VAL1')
       + (SELECT COUNT(*) FROM parkitup.dim_locality WHERE locality_id = 901);" 2>&1)
if [ "$fixtures_left" = "0" ]; then
  ok "validation fixtures removed, so the data-quality run below is clean"
else
  bad "validation fixtures could not be removed ($fixtures_left remaining)"
fi

# ---------------------------------------------------------------------
head1 "4. DATA QUALITY CHECKS EXECUTE"
if out=$(psql -d "$VALIDATE_DB" -v ON_ERROR_STOP=1 -f sql/data_quality/dq_checks.sql 2>&1); then
  ok "sql/data_quality/dq_checks.sql executed without error"
  log ""
  printf '%s\n' "$out" | sed 's/^/    /' >> "$REPORT"
  printf '%s\n' "$out" | sed 's/^/    /'
else
  bad "dq_checks.sql failed to execute"
  printf '%s\n' "$out" | sed 's/^/        /' >> "$REPORT"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# ---------------------------------------------------------------------
head1 "5. CATALOGUE AS POSTGRESQL BUILT IT"
log ""
log "--- tables and column counts ---"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT c.relname, COUNT(a.attname)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
   WHERE n.nspname = 'parkitup' AND c.relkind = 'r'
   GROUP BY c.relname ORDER BY c.relname;" 2>&1 | sed 's/^/    /' | tee -a "$REPORT"

log ""
log "--- constraint census by type ---"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT CASE contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                      WHEN 'u' THEN 'UNIQUE'      WHEN 'c' THEN 'CHECK'
                      ELSE contype::TEXT END, COUNT(*)
    FROM pg_constraint co
    JOIN pg_namespace n ON n.oid = co.connamespace
   WHERE n.nspname = 'parkitup'
   GROUP BY 1 ORDER BY 1;" 2>&1 | sed 's/^/    /' | tee -a "$REPORT"

log ""
log "--- full constraint definitions ---"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT cl.relname, co.conname, pg_get_constraintdef(co.oid)
    FROM pg_constraint co
    JOIN pg_class cl     ON cl.oid = co.conrelid
    JOIN pg_namespace n  ON n.oid  = co.connamespace
   WHERE n.nspname = 'parkitup'
   ORDER BY cl.relname, co.contype DESC, co.conname;" 2>&1 | sed 's/^/    /' >> "$REPORT"
log "    (written to the report file - $(psql -d "$VALIDATE_DB" -Atc "SELECT COUNT(*) FROM pg_constraint co JOIN pg_namespace n ON n.oid=co.connamespace WHERE n.nspname='parkitup';" 2>&1) constraints)"

log ""
log "--- columns, types, nullability ---"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT table_name, ordinal_position, column_name, data_type,
         COALESCE(character_maximum_length::TEXT,
                  numeric_precision::TEXT || ',' || numeric_scale::TEXT, '-'),
         is_nullable, COALESCE(is_generated,'-')
    FROM information_schema.columns
   WHERE table_schema = 'parkitup'
   ORDER BY table_name, ordinal_position;" 2>&1 | sed 's/^/    /' >> "$REPORT"
log "    (written to the report file)"

log ""
log "--- indexes ---"
psql -d "$VALIDATE_DB" -At -F' | ' -c "
  SELECT tablename, indexname FROM pg_indexes
   WHERE schemaname = 'parkitup' ORDER BY tablename, indexname;" 2>&1 | sed 's/^/    /' | tee -a "$REPORT"

# ---------------------------------------------------------------------
head1 "6. TEARDOWN SCRIPT"
if out=$("${PSQL_STRICT[@]}" -f database/schema/99_drop_all.sql 2>&1); then
  remaining=$(psql -d "$VALIDATE_DB" -Atc "
    SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='parkitup' AND c.relkind='r';" 2>&1)
  if [ "$remaining" = "0" ]; then
    ok "99_drop_all.sql removed every table"
  else
    bad "99_drop_all.sql left $remaining table(s) behind"
  fi
else
  bad "99_drop_all.sql failed"
  printf '%s\n' "$out" | sed 's/^/        /' >> "$REPORT"
fi

# ---------------------------------------------------------------------
head1 "7. IDEMPOTENCE (rebuild from scratch in the same database)"
# Pass 1 rebuilds after the section 6 teardown. Pass 2 re-applies everything on
# top of itself, which must be a no-op thanks to IF NOT EXISTS / ON CONFLICT.
# Any error is captured and reported with the exact pass and file, because
# "not idempotent" without a filename is not an actionable finding.
rebuild_ok=1
rebuild_pass=""
rebuild_file=""
rebuild_err=""
for pass in 1 2; do
  for f in database/schema/0*.sql database/seeds/*.sql ; do
    if ! out=$("${PSQL_STRICT[@]}" -f "$f" 2>&1); then
      rebuild_ok=0
      rebuild_pass="$pass"
      rebuild_file="$f"
      rebuild_err="$out"
      break 2
    fi
  done
done
if [ "$rebuild_ok" = "1" ]; then
  ok "schema and seeds are re-runnable (applied twice with no error)"
else
  bad "not idempotent - pass $rebuild_pass failed on $rebuild_file"
  log "        ---- psql output ----"
  printf '%s\n' "$rebuild_err" | sed 's/^/        /' | tee -a "$REPORT"
fi

# ---------------------------------------------------------------------
head1 "SUMMARY"
log "  passed : $PASS"
log "  failed : $FAIL"
log ""
if [ "$FAIL" -eq 0 ]; then
  log "  RESULT: schema validated successfully."
else
  log "  RESULT: $FAIL check(s) FAILED - see detail above."
fi
log ""
log "  Full report: validation/report.txt"

dropdb --if-exists "$VALIDATE_DB" >/dev/null 2>&1 \
  && log "  scratch database dropped." \
  || log "  NOTE: could not drop scratch database '$VALIDATE_DB'."

[ "$FAIL" -eq 0 ] || exit 1
