#!/usr/bin/env bash
# =====================================================================
# Dead-file cleanup, with a justification for every deletion.
#
# Nothing here was inferred from a filename. Each path below was proven
# unreferenced by grepping the whole repository — code, SQL, Makefile, tests and
# documentation. The evidence is stated inline so you can disagree with any
# individual line rather than having to trust the whole script.
#
# USAGE
#   bash scripts/cleanup.sh --dry-run    # default: print, delete nothing
#   bash scripts/cleanup.sh --apply      # actually delete
#
# Run this BEFORE `git init`, so the deleted files never enter history.
# =====================================================================
set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

APPLY=0
case "${1:-}" in
  --apply)   APPLY=1 ;;
  --dry-run|"") APPLY=0 ;;
  *) echo "usage: $0 [--dry-run|--apply]"; exit 2 ;;
esac

removed=0
kept=0

# drop <path> <reason>
drop() {
  local path="$1" reason="$2"
  if [ ! -e "$path" ]; then
    printf '  SKIP    %-52s (already absent)\n' "$path"
    return
  fi
  local size
  size=$(du -sh "$path" 2>/dev/null | cut -f1)
  if [ "$APPLY" = "1" ]; then
    rm -rf -- "$path"
    printf '  DELETED %-52s %6s  %s\n' "$path" "$size" "$reason"
  else
    printf '  WOULD   %-52s %6s  %s\n' "$path" "$size" "$reason"
  fi
  removed=$((removed + 1))
}

# keep <path> <reason>  — recorded so a future reader does not re-litigate it
keep() {
  printf '  KEEP    %-52s %s\n' "$1" "$2"
  kept=$((kept + 1))
}

echo "PARK It Up — dead-file cleanup"
[ "$APPLY" = "1" ] && echo "MODE: APPLY (files will be deleted)" || echo "MODE: DRY RUN (nothing will be deleted)"
echo ""

echo "OS and tooling debris"
echo "---------------------"
# .gitignore already excludes these, so they would never be committed. Removing
# them anyway keeps the working tree clean and the file listing honest.
find . -name '.DS_Store' -not -path './.venv/*' -print0 2>/dev/null | while IFS= read -r -d '' f; do
  if [ "$APPLY" = "1" ]; then rm -f -- "$f"; printf '  DELETED %s\n' "$f"; else printf '  WOULD   %s\n' "$f"; fi
done
drop ".pytest_cache" "pytest scratch; regenerated on every run; git-ignored"
if [ "$APPLY" = "1" ]; then
  find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null
  find . -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null
  echo "  DELETED __pycache__ directories and .pyc files"
else
  echo "  WOULD   __pycache__ directories and .pyc files"
fi

echo ""
echo "Empty placeholder directories for work that lives elsewhere"
echo "----------------------------------------------------------"
# Proven by: grep -rn "python/scoring" over the whole repo returns nothing except
# the README tree diagram, which has been corrected. scoring actually
# lives in python/analysis/scoring_engine.py.
drop "python/scoring" "contains only .gitkeep; scoring lives in python/analysis/scoring_engine.py"

# Proven by: grep -rn "dashboard/screenshots" returns zero hits. The live output
# directory is dashboard/powerbi/screenshots, written by powerbi_mockups.py:32
# and asserted by two test modules. This is the retired Streamlit app's output
# directory, whose contents were removed but whose shell survived.
drop "dashboard/screenshots" "contains only .gitkeep; live previews are in dashboard/powerbi/screenshots"

# sql/analysis/ contains component_scores.sql, so the .gitkeep is redundant.
drop "sql/analysis/.gitkeep" "directory is no longer empty; component_scores.sql lives here"

echo ""
echo "Re-query caches that are not build inputs"
echo "-----------------------------------------"
# The decisive evidence: source_collection.py's ensure_cached_sources() gates on
# exactly three paths — osm_geocoding_snapshot.json, osm_features_snapshot.json
# and source_manifest.json — and the manifest hashes only those plus
# micro_markets.csv. The batch directories are written by --refresh and read only
# by a subsequent --refresh. No build step touches them.
#
# They are now git-ignored as well, so this deletion only reclaims local disk.
# Deleting osm_batches/ would slightly degrade a future --curated-fallback
# re-collection, which merges the richer Overpass batches back in. It changes
# nothing about the committed snapshot the pipeline actually reads.
drop "data/external/nominatim_fallback_batches" "160 files; written by --refresh, read only by --refresh; not in the manifest"
drop "data/external/osm_batches" "2 files; per-market Overpass cache; not in the manifest"

echo ""
echo "Stale validation artifacts"
echo "--------------------------"
# validation/* is git-ignored, so none of this would be committed. These two are
# deleted because their content is actively misleading if read.
#
# report.txt attests "58 checks passed" against a schema that no longer exists:
# its table census omits all six tables created by 06_analysis.sql, and four
# schema files have been edited since it was generated.
drop "validation/report.txt" "schema census predates 06_analysis.sql; regenerate with 'make validate-schema'"

# postgres_data_quality_results.csv records DQ-024 as a 120-row FAIL — lots present
# but unscored — which was true when the pipeline ran and false an hour later once
# scoring completed. The current equivalent is
# postgres_data_quality_scoring_results.csv, which records the same rule as PASS.
drop "validation/postgres_data_quality_results.csv" "records a 120-row failure that scoring resolved; superseded by the scoring results file"

echo ""
echo "Deliberately kept — do not delete these"
echo "---------------------------------------"
keep "data/external/osm_features_snapshot.json" "the committed public input; offline reproducibility depends on it"
keep "data/external/osm_geocoding_snapshot.json" "committed public input, read by cleaning.py"
keep "data/external/source_manifest.json"        "provenance and SHA-256 hashes for the above"
keep "data/external/micro_markets.csv"           "committed market definition, read by cleaning.py"
keep "data/powerbi/"                             "generated, but it is what the .pbix binds to; whitelisted in .gitignore"
keep "python/analysis/statistics.py"             "imported by eda.py, diagnostics.py and charts.py"
keep "python/analysis/profiling.py"              "imported by run_validation.py and 01_data_quality.ipynb"
keep "python/visualization/charts.py"            "imported by run_validation.py; not superseded by design_system.py"
keep "validation/business_logic_results.csv"     "current output of validation.py; asserted by tests"
keep "validation/figures/"                       "the 12 charts the notebooks and docs reference"
keep "sql/data_quality/analytics_view_checks.sql" "overlaps dq_checks.sql but targets the analytics views specifically"

echo ""
echo "----------------------------------------------------------------------"
if [ "$APPLY" = "1" ]; then
  echo "Removed ${removed} path(s); ${kept} kept deliberately."
  echo ""
  echo "Now verify nothing broke:"
  echo "  make test        # 54 tests"
  echo "  make powerbi      # rebuild the dashboard package"
else
  echo "${removed} path(s) would be removed; ${kept} kept deliberately."
  echo ""
  echo "Re-run with --apply to delete."
fi
