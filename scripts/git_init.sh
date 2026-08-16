#!/usr/bin/env bash
# =====================================================================
# Initialise the git repository and make the first commit.
#
# WHY THIS SCRIPT EXISTS. A `git init` was attempted from a sandbox that cannot
# unlink files inside this folder. The result is a `.git` directory that is
# present but has no history, plus a stale `.git/index.lock` and six orphaned
# temporary objects that could not be cleaned up. Git refuses to write while that
# lock exists, so this script clears it first. Running on macOS, where deletion
# works, everything below succeeds.
#
# USAGE
#   bash scripts/git_init.sh              # verify, clean, init, commit
#   bash scripts/git_init.sh --check-only # verify what would be committed, no writes
#
# Run scripts/cleanup.sh --apply FIRST if you want the dead files gone before
# they enter history.
# =====================================================================
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CHECK_ONLY=0
[ "${1:-}" = "--check-only" ] && CHECK_ONLY=1

echo "PARK It Up Acquisition Intelligence — repository initialisation"
echo ""

# ---------------------------------------------------------------------
# 1. Clear the sandbox leftovers
# ---------------------------------------------------------------------
if [ -d .git ]; then
  echo "Existing .git found."
  if [ -f .git/index.lock ]; then
    if [ "$CHECK_ONLY" = "1" ]; then
      echo "  WOULD remove stale .git/index.lock"
    else
      rm -f .git/index.lock
      echo "  removed stale .git/index.lock"
    fi
  fi
  stale=$(find .git/objects -name 'tmp_obj*' 2>/dev/null | wc -l | tr -d ' ')
  if [ "$stale" != "0" ]; then
    if [ "$CHECK_ONLY" = "1" ]; then
      echo "  WOULD remove ${stale} orphaned temporary object(s)"
    else
      find .git/objects -name 'tmp_obj*' -delete 2>/dev/null || true
      echo "  removed ${stale} orphaned temporary object(s)"
    fi
  fi
  if [ "$(git rev-list --count HEAD 2>/dev/null || echo 0)" != "0" ]; then
    echo ""
    echo "  This repository already has history. Refusing to re-initialise."
    echo "  Commit your changes normally instead."
    exit 0
  fi
else
  [ "$CHECK_ONLY" = "1" ] && echo "No .git; would run 'git init'." || { git init -q; echo "Initialised empty repository."; }
fi

# ---------------------------------------------------------------------
# 2. Prove the ignore rules work before anything is committed
# ---------------------------------------------------------------------
echo ""
echo "Verifying .gitignore. Anything marked MUST-IGNORE that reports TRACKED is a"
echo "defect and this script will stop."
echo ""

fail=0
must_ignore=(
  ".env"
  "validation/report.txt"
  "data/processed/parking_lots.csv"
  "data/raw/osm_features.csv"
  ".DS_Store"
  ".pytest_cache"
  "data/external/osm_batches"
  "data/external/nominatim_fallback_batches"
  "resume.tex"
  "resume.pdf"
)
must_track=(
  "README.md"
  ".env.example"
  "requirements.txt"
  "data/external/osm_features_snapshot.json"
  "data/external/source_manifest.json"
  "data/powerbi/DimParking.csv"
  "dashboard/powerbi/screenshots/page_01_executive_overview.png"
  "documentation/interview_guide.md"
  "tests/test_audit.py"
)

for p in "${must_ignore[@]}"; do
  if git check-ignore -q "$p" 2>/dev/null; then
    printf '  ok        ignored   %s\n' "$p"
  else
    # A path that does not exist is fine; a path that exists and is not ignored is not.
    if [ -e "$p" ]; then
      printf '  DEFECT    TRACKED   %s   <-- must not be committed\n' "$p"
      fail=1
    else
      printf '  n/a       absent    %s\n' "$p"
    fi
  fi
done
echo ""
for p in "${must_track[@]}"; do
  if [ ! -e "$p" ]; then
    printf '  DEFECT    missing   %s   <-- expected to exist\n' "$p"; fail=1
  elif git check-ignore -q "$p" 2>/dev/null; then
    printf '  DEFECT    ignored   %s   <-- must be committed\n' "$p"; fail=1
  else
    printf '  ok        tracked   %s\n' "$p"
  fi
done

if [ "$fail" != "0" ]; then
  echo ""
  echo "STOPPING: fix .gitignore before committing. Nothing was staged."
  exit 1
fi

# ---------------------------------------------------------------------
# 3. Secret sweep over exactly the set of files that would be committed
# ---------------------------------------------------------------------
echo ""
echo "Scanning the files that would actually be committed for secrets and PII."

candidates=$(git ls-files --others --cached --exclude-standard)
count=$(printf '%s\n' "$candidates" | grep -c . || true)
echo "  ${count} file(s) in scope"

emails=$(printf '%s\n' "$candidates" | tr '\n' '\0' \
  | xargs -0 grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' 2>/dev/null \
  | grep -viE 'example\.(com|org)|@local$|^git@(github|gitlab|bitbucket)\.com$|your[._-]?email' \
  | sort -u || true)
if [ -n "$emails" ]; then
  echo "  DEFECT: email address(es) found in files that would be committed:"
  printf '%s\n' "$emails" | sed 's/^/    /'
  echo "  Fix: python3 python/etl/source_collection.py --scrub-cache"
  exit 1
fi
echo "  ok  no email addresses"

keys=$(printf '%s\n' "$candidates" | tr '\n' '\0' \
  | xargs -0 grep -rlE 'BEGIN (RSA|OPENSSH|EC|DSA|PRIVATE)|xox[baprs]-|gh[pousr]_[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}' 2>/dev/null || true)
if [ -n "$keys" ]; then
  echo "  DEFECT: credential-shaped string(s) found in:"
  printf '%s\n' "$keys" | sed 's/^/    /'
  exit 1
fi
echo "  ok  no private keys, tokens or cloud credentials"

if [ "$CHECK_ONLY" = "1" ]; then
  echo ""
  echo "Check-only mode. Nothing staged, nothing committed."
  echo "Re-run without --check-only to commit."
  exit 0
fi

# ---------------------------------------------------------------------
# 4. Commit
# ---------------------------------------------------------------------
echo ""
git add -A
staged=$(git diff --cached --name-only | wc -l | tr -d ' ')
echo "Staged ${staged} file(s)."

git commit -q -F - <<'MSG'
PARK It Up Acquisition Intelligence

A decision-support system that ranks 120 Delhi NCR parking lots for business
development prioritisation, built on PostgreSQL, SQL, Python and Power BI.

Five weighted pillars — demand, revenue potential, competition opportunity,
strategic fit and acquisition feasibility — combine into a 0-100 acquisition
score, with feasibility held on a separate axis so that an attractive but
unobtainable lot is distinguished from an ordinary but easily signed one. The
output is four BD action segments: 25 Acquire Now, 15 Pursue, 21 Develop,
59 Avoid.

Candidate locations and geography are real, from a hash-verified OpenStreetMap
snapshot committed for offline reproducibility. Operational and commercial
figures are modelled and labelled synthetic at column, table and document
level. No confidential information is included.

Validation: 54 automated tests, 35 SQL data-quality rules, 30 Python structural
checks, 7 monotonicity tests, 6 adversarial stress cases and 16 scenarios. The
base case reconciles Python's pillars against the SQL view on every run, so the
two implementations of the shared logic cannot drift apart.
MSG

echo ""
echo "Committed:"
git --no-pager log --stat --oneline -1 | head -3
echo ""
echo "Repository size: $(du -sh .git | cut -f1)"
echo ""
echo "Next steps:"
echo "  git branch -M main"
echo "  git remote add origin git@github.com:<you>/parkitup-acquisition-intelligence.git"
echo "  git push -u origin main"
