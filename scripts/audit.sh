#!/usr/bin/env bash
# =====================================================================
# audit — the parts that require a live PostgreSQL server.
#
# Everything in tests/test_audit.py runs offline. This script covers
# what only a real database can prove: DDL integrity, the 35-rule data-quality
# catalogue, referential integrity, join-grain correctness, and independent
# recalculation of headline figures in SQL rather than in pandas.
#
# It is READ-MOSTLY. It rebuilds the pipeline and rescores, because the audit
# audit changed two things that only take effect on a rerun:
#   1. personal-contact tags were stripped from the committed OSM snapshot;
#   2. anchor_capacity_raw was corrected (see sql/analysis/component_scores.sql).
# It does not drop your database unless you pass --reset.
#
# USAGE
#   bash scripts/audit.sh            # audit the current database
#   bash scripts/audit.sh --reset    # drop, rebuild, reload, rescore first
#
# BEFORE YOU RUN — avoid ~90 password prompts
#   This script makes many separate psql calls. libpq will prompt on every one
#   unless a password file exists. If your local server needs a password:
#
#     echo "localhost:5432:*:$(whoami):YOUR_PASSWORD" >> ~/.pgpass
#     chmod 600 ~/.pgpass
#
#   The chmod is mandatory. libpq SILENTLY ignores a group- or world-readable
#   .pgpass and you will get every prompt back with no explanation.
#
# OUTPUT
#   validation/audit_report.txt  — read this; it is the deliverable.
# =====================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB="${PGDATABASE:-parkitup}"
SCHEMA="${PG_SCHEMA:-parkitup}"
PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"
REPORT="validation/audit_report.txt"
RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

mkdir -p validation
: > "$REPORT"

pass_count=0
fail_count=0
warn_count=0

say() { printf '%s\n' "$*" | tee -a "$REPORT"; }
rule() { say "----------------------------------------------------------------------"; }
head1() { say ""; rule; say "$*"; rule; }

# Run a query and print the result. Never redirect stderr away: the error text
# is the whole point of a validation loop.
q() {
  psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -At -c "SET search_path TO ${SCHEMA},public; $1" 2>&1
}

# check <label> <sql returning a single number> <expected> [WARN]
check() {
  local label="$1" sql="$2" expect="$3" severity="${4:-ERROR}"
  local got
  got="$(q "$sql")"
  if [ "$got" = "$expect" ]; then
    say "  PASS  ${label}  (= ${got})"
    pass_count=$((pass_count + 1))
  elif [ "$severity" = "WARN" ]; then
    say "  WARN  ${label}  expected ${expect}, got ${got}"
    warn_count=$((warn_count + 1))
  else
    say "  FAIL  ${label}  expected ${expect}, got ${got}"
    fail_count=$((fail_count + 1))
  fi
}

show() {
  local label="$1" sql="$2"
  say ""
  say "  ${label}"
  psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "SET search_path TO ${SCHEMA},public; $sql" 2>&1 \
    | sed 's/^/    /' | tee -a "$REPORT" > /dev/null
  psql -X -q -d "$DB" -c "SET search_path TO ${SCHEMA},public; $sql" 2>&1 | sed 's/^/    /'
}

say "PARK It Up Acquisition Intelligence — audit database audit"
say "generated : $(date '+%Y-%m-%d %H:%M:%S %Z')"
say "database  : ${DB}   schema: ${SCHEMA}"
say "python    : $($PY --version 2>&1)"
say "postgres  : $(psql -X -At -d "$DB" -c 'SHOW server_version' 2>&1 | head -1)"
say "libraries : $($PY -c 'import numpy,pandas;print("numpy",numpy.__version__,"pandas",pandas.__version__)' 2>&1)"

# ---------------------------------------------------------------------
head1 "0. CONNECTIVITY"
if ! q "SELECT 1" > /dev/null 2>&1; then
  say "  FAIL  cannot connect to database '${DB}'."
  say "        Try: createdb ${DB} && bash scripts/audit.sh --reset"
  say ""
  say "RESULT: audit aborted."
  exit 1
fi
say "  PASS  connected"

# ---------------------------------------------------------------------
if [ "$RESET" = "1" ]; then
  head1 "1. FULL REBUILD (--reset)"
  say "  This is the audit reproducibility test: schema, seed, ETL, load, score."
  for step in \
    "make db-reset" \
    "$PY python/etl/build_dataset.py --load-postgres" \
    "$PY python/analysis/scoring_engine.py" \
    "make analytics-test" \
    "$PY python/analysis/run_validation.py" \
    "$PY python/analysis/prepare_powerbi.py"
  do
    say ""
    say "  -> ${step}"
    start=$(date +%s)
    if eval "$step" > /tmp/audit_step.log 2>&1; then
      say "     PASS in $(( $(date +%s) - start ))s"
      pass_count=$((pass_count + 1))
    else
      say "     FAIL in $(( $(date +%s) - start ))s — last 25 lines:"
      tail -25 /tmp/audit_step.log | sed 's/^/       /' | tee -a "$REPORT"
      fail_count=$((fail_count + 1))
    fi
  done
else
  head1 "1. REBUILD SKIPPED"
  say "  Running against the existing database. Pass --reset to prove the"
  say "  end-to-end pipeline reproduces from a clean schema."
  say ""
  say "  NOTE: two audit changes only take effect after a rerun —"
  say "        the corrected anchor_capacity_raw, and the scrubbed OSM snapshot."
fi

# ---------------------------------------------------------------------
head1 "2. SCHEMA AND CONSTRAINT CENSUS"
show "tables, columns, and row counts" "
SELECT c.relname AS table_name,
       (SELECT COUNT(*) FROM information_schema.columns
         WHERE table_schema='${SCHEMA}' AND table_name=c.relname) AS cols,
       c.reltuples::BIGINT AS est_rows
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='${SCHEMA}' AND c.relkind='r'
ORDER BY 1;"

show "constraint counts by type" "
SELECT CASE contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                    WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK' ELSE contype::TEXT END AS kind,
       COUNT(*) AS n
FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace
WHERE n.nspname='${SCHEMA}' GROUP BY 1 ORDER BY 2 DESC;"

check "every base table has a primary key" "
SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='${SCHEMA}' AND c.relkind='r'
  AND NOT EXISTS (SELECT 1 FROM pg_constraint k
                  WHERE k.conrelid=c.oid AND k.contype='p');" "0"

check "no foreign key points at a missing parent" "
SELECT COUNT(*) FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace
WHERE n.nspname='${SCHEMA}' AND con.contype='f' AND NOT con.convalidated;" "0"

# ---------------------------------------------------------------------
head1 "3. DATA-QUALITY RULE CATALOGUE"
say "  Running sql/data_quality/dq_checks.sql (35 rules, 20 ERROR / 15 WARN)."
show "rule results, failures first" "
$(cat sql/data_quality/dq_checks.sql | sed 's/^SET search_path.*$//')"

# ---------------------------------------------------------------------
head1 "4. REFERENTIAL AND GRAIN INTEGRITY"
check "lots without an owner"            "SELECT COUNT(*) FROM parking_lots p LEFT JOIN owners o USING (owner_id) WHERE o.owner_id IS NULL;" "0"
check "lots without a locality"          "SELECT COUNT(*) FROM parking_lots p LEFT JOIN dim_locality l USING (locality_id) WHERE l.locality_id IS NULL;" "0"
check "daily facts orphaned from lots"   "SELECT COUNT(*) FROM fact_lot_daily f LEFT JOIN parking_lots p USING (parking_id) WHERE p.parking_id IS NULL;" "0"
check "duplicate lot-day facts"          "SELECT COUNT(*) FROM (SELECT parking_id, activity_date FROM fact_lot_daily GROUP BY 1,2 HAVING COUNT(*)>1) d;" "0"
check "one feature row per lot"          "SELECT COUNT(*) FROM (SELECT parking_id FROM parking_acquisition_features GROUP BY 1 HAVING COUNT(*)>1) d;" "0"
check "one component row per lot"        "SELECT COUNT(*) FROM (SELECT parking_id FROM parking_component_scores GROUP BY 1 HAVING COUNT(*)>1) d;" "0"
check "five pillar rows per lot per set" "SELECT COUNT(*) FROM (SELECT parking_id, weight_set_id FROM lot_dimension_score GROUP BY 1,2 HAVING COUNT(*)<>5) d;" "0"
check "outreach events orphaned"         "SELECT COUNT(*) FROM outreach_events e LEFT JOIN outreach o USING (lead_id) WHERE o.lead_id IS NULL;" "0" "WARN"

say ""
say "  Join-grain proof: a many-to-many join would inflate these counts."
check "feature view row count"           "SELECT COUNT(*) FROM parking_acquisition_features;" "120"
check "component view row count"         "SELECT COUNT(*) FROM parking_component_scores;" "120"
check "baseline score row count"         "SELECT COUNT(*) FROM parking_acquisition_score;" "120"

# ---------------------------------------------------------------------
head1 "5. INDEPENDENT RECALCULATION IN SQL"
say "  Each figure below is recomputed from base tables, NOT read from a"
say "  precomputed column, then compared with what the model published."

show "composite score = sum of weighted pillar contributions (worst 5 lots)" "
SELECT s.parking_id,
       ROUND(s.acquisition_score, 4) AS published,
       ROUND(SUM(d.subscore * d.weight_applied), 4) AS recomputed,
       ROUND(ABS(s.acquisition_score - SUM(d.subscore * d.weight_applied)), 6) AS abs_diff
FROM lot_score s
JOIN lot_dimension_score d USING (parking_id, weight_set_id)
WHERE s.weight_set_id = 1
GROUP BY s.parking_id, s.acquisition_score
ORDER BY abs_diff DESC
LIMIT 5;"

check "lots where recomputed score differs by > 0.02" "
SELECT COUNT(*) FROM (
  SELECT s.parking_id
  FROM lot_score s JOIN lot_dimension_score d USING (parking_id, weight_set_id)
  WHERE s.weight_set_id=1
  GROUP BY s.parking_id, s.acquisition_score
  HAVING ABS(s.acquisition_score - SUM(d.subscore*d.weight_applied)) > 0.02
) x;" "0"

check "every weight set sums to 1.0" "
SELECT COUNT(*) FROM (SELECT weight_set_id FROM scoring_weight GROUP BY 1
                      HAVING ABS(SUM(weight)-1.0) > 1e-9) d;" "0"

show "top acquisition target, rank recomputed with a window function" "
SELECT DENSE_RANK() OVER (ORDER BY acquisition_score DESC) AS recomputed_rank,
       rank_overall AS published_rank, parking_id, ROUND(acquisition_score,2) AS score
FROM lot_score WHERE weight_set_id=1
ORDER BY acquisition_score DESC LIMIT 5;"

show "average occupancy recomputed from 43,800 daily rows" "
SELECT ROUND(AVG(avg_occupancy_rate)::NUMERIC, 6) AS mean_daily_occupancy,
       COUNT(*) AS rows_used,
       COUNT(DISTINCT parking_id) AS lots,
       MIN(activity_date) AS from_date, MAX(activity_date) AS to_date
FROM fact_lot_daily;"

show "BD funnel recomputed from raw event rows (not the view)" "
SELECT s.stage_order, s.stage_code,
       COUNT(DISTINCT e.lead_id) AS leads_reached,
       ROUND(100.0*COUNT(DISTINCT e.lead_id)/NULLIF(
         (SELECT COUNT(DISTINCT lead_id) FROM outreach_events),0), 2) AS pct_of_all_leads
FROM dim_funnel_stage s
LEFT JOIN outreach_events e ON e.stage_id = s.stage_id
GROUP BY s.stage_order, s.stage_code
ORDER BY s.stage_order;"

show "conversion rate recomputed two independent ways" "
SELECT (SELECT COUNT(*) FROM outreach WHERE pipeline_status='Won') AS won_from_status,
       (SELECT COUNT(DISTINCT e.lead_id) FROM outreach_events e
         JOIN dim_funnel_stage s USING (stage_id)
        WHERE s.is_success_stage) AS won_from_events,
       (SELECT COUNT(*) FROM outreach) AS leads,
       ROUND(100.0*(SELECT COUNT(*) FROM outreach WHERE pipeline_status='Won')
             / NULLIF((SELECT COUNT(*) FROM outreach),0), 2) AS conversion_pct;"

check "status-based and event-based Won counts agree" "
SELECT ABS((SELECT COUNT(*) FROM outreach WHERE pipeline_status='Won')
         - (SELECT COUNT(DISTINCT e.lead_id) FROM outreach_events e
             JOIN dim_funnel_stage s USING (stage_id) WHERE s.is_success_stage));" "0"

show "locality averages recomputed from lot grain" "
SELECT l.locality_name,
       COUNT(*) AS lots,
       ROUND(AVG(s.acquisition_score),2) AS recomputed_avg,
       ROUND(MAX(a.average_acquisition_score),2) AS published_avg,
       ROUND(ABS(AVG(s.acquisition_score)-MAX(a.average_acquisition_score)),4) AS abs_diff
FROM lot_score s
JOIN parking_lots p USING (parking_id)
JOIN dim_locality l USING (locality_id)
JOIN locality_acquisition_summary a USING (locality_id)
WHERE s.weight_set_id=1
GROUP BY l.locality_name
ORDER BY abs_diff DESC
LIMIT 5;"

# ---------------------------------------------------------------------
head1 "6. MODEL CORRECTION — anchor_capacity_raw"
say "  Before the correction, anchor_capacity_raw was capacity/(live_capacity+capacity),"
say "  which is exactly 1.0 wherever the platform has no live site. Strategic Fit"
say "  then became a locality-level constant. Both checks below must pass."

check "no locality has a constant Strategic Fit across >1 lot" "
SELECT COUNT(*) FROM (
  SELECT locality_id FROM parking_component_scores
  GROUP BY locality_id HAVING COUNT(*) > 1 AND COUNT(DISTINCT strategic_fit_score) = 1
) d;" "0"

check "anchor_capacity_score is not pinned at 100 for a quarter of the portfolio" "
SELECT CASE WHEN COUNT(*) FILTER (WHERE anchor_capacity_score >= 99.99) > 12
            THEN COUNT(*) FILTER (WHERE anchor_capacity_score >= 99.99) ELSE 0 END
FROM parking_component_scores;" "0"

show "anchor capacity must now increase with lot capacity" "
SELECT width_bucket(capacity_cars, 27, 706, 4) AS capacity_quartile,
       COUNT(*) AS lots,
       MIN(capacity_cars) AS min_cap, MAX(capacity_cars) AS max_cap,
       ROUND(AVG(anchor_capacity_score),2) AS avg_anchor_score
FROM parking_component_scores
GROUP BY 1 ORDER BY 1;"

# ---------------------------------------------------------------------
head1 "7. SCORE RANGE AND SEGMENT INTEGRITY"
check "pillar scores outside 0-100"  "
SELECT COUNT(*) FROM lot_dimension_score WHERE subscore < 0 OR subscore > 100;" "0"
check "composite scores outside 0-100" "
SELECT COUNT(*) FROM lot_score WHERE acquisition_score < 0 OR acquisition_score > 100;" "0"
check "NULL composite scores"        "SELECT COUNT(*) FROM lot_score WHERE acquisition_score IS NULL;" "0"
check "lots without a segment"       "SELECT COUNT(*) FROM lot_score WHERE segment_code IS NULL;" "0"
check "duplicate ranks in the default weight set" "
SELECT COUNT(*) FROM (SELECT rank_overall FROM lot_score WHERE weight_set_id=1
                      GROUP BY 1 HAVING COUNT(*)>1) d;" "0"

show "segment distribution" "
SELECT segment_code, COUNT(*) AS lots,
       ROUND(MIN(attractiveness_score),2) AS min_attr, ROUND(MAX(attractiveness_score),2) AS max_attr,
       ROUND(MIN(feasibility_score),2) AS min_feas,  ROUND(MAX(feasibility_score),2) AS max_feas
FROM lot_score WHERE weight_set_id=1 GROUP BY 1 ORDER BY 1;"

# ---------------------------------------------------------------------
head1 "8. PRIVACY RE-CHECK ON THE COMMITTED SNAPSHOT"
pii_keys=$(grep -rhoiE '"[^"]*(email|phone|mobile|fax|whatsapp)[^"]*"[[:space:]]*:' data/external --include=*.json 2>/dev/null | sort -u | wc -l | tr -d ' ')
pii_mails=$(grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' data/external --include=*.json 2>/dev/null | sort -u | wc -l | tr -d ' ')
if [ "$pii_keys" = "0" ] && [ "$pii_mails" = "0" ]; then
  say "  PASS  no contact tag keys and no email addresses in data/external"
  pass_count=$((pass_count + 1))
else
  say "  FAIL  ${pii_keys} contact tag key(s) and ${pii_mails} email address(es) still present"
  say "        Fix: $PY python/etl/source_collection.py --scrub-cache"
  fail_count=$((fail_count + 1))
fi

# ---------------------------------------------------------------------
head1 "9. OFFLINE TEST SUITE"
say "  Running pytest (this is the run that counts; the sandbox could not)."
if $PY -m pytest tests/ -q > /tmp/audit_pytest.log 2>&1; then
  tail -12 /tmp/audit_pytest.log | sed 's/^/    /' | tee -a "$REPORT"
  say "  PASS  test suite green"
  pass_count=$((pass_count + 1))
else
  tail -40 /tmp/audit_pytest.log | sed 's/^/    /' | tee -a "$REPORT"
  say "  FAIL  test suite red — see /tmp/audit_pytest.log"
  fail_count=$((fail_count + 1))
fi

# ---------------------------------------------------------------------
head1 "10. RUNTIME"
say "  Measured where a rebuild ran; otherwise timing a read-only query."
start=$(date +%s%N)
q "SELECT COUNT(*) FROM parking_acquisition_features" > /dev/null
say "  feature view materialisation : $(( ($(date +%s%N) - start) / 1000000 )) ms"
start=$(date +%s%N)
q "SELECT COUNT(*) FROM parking_component_scores" > /dev/null
say "  component score view        : $(( ($(date +%s%N) - start) / 1000000 )) ms"
start=$(date +%s%N)
q "SELECT AVG(avg_occupancy_rate) FROM fact_lot_daily" > /dev/null
say "  43,800-row daily aggregate  : $(( ($(date +%s%N) - start) / 1000000 )) ms"

# ---------------------------------------------------------------------
head1 "SUMMARY"
say "  passed : ${pass_count}"
say "  warned : ${warn_count}"
say "  failed : ${fail_count}"
say ""
if [ "$fail_count" -eq 0 ]; then
  say "RESULT: PASS — database layer validated."
else
  say "RESULT: FAIL — ${fail_count} check(s) failed. Search this file for 'FAIL'."
fi
say ""
say "Full report: ${REPORT}"
exit 0
