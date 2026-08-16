"""Audit regression tests.

Every test here exists because the final audit found a way for this project to
become quietly wrong. They run offline against the committed extracts and the
source files, so `pytest` needs no PostgreSQL and no network.

Grouped by what they defend:

  Privacy        the committed OSM snapshot must carry no third-party contact data
  Single source  SQL and Python hold two copies of Demand/Revenue and two copies
                 of two sub-weights; nothing previously forced them to agree
  Model          scores stay in range, the composite is exactly the weighted sum,
                 no input encodes the outcome
  Monotonicity   every pillar responds in the correct direction
  Reconciliation Power BI extracts and the BD funnel match the analytical layer
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from python.analysis.scoring_engine import (  # noqa: E402
    COMPONENT_COLUMNS,
    FEASIBILITY_ONBOARDING_COST_WEIGHT,
    RECONCILIATION_TOLERANCE,
    STRATEGIC_NETWORK_DISTANCE_WEIGHT,
    network_score,
    reconcile_base_case_against_sql,
    winsor_score,
)
from python.config import settings  # noqa: E402

PROCESSED = REPO_ROOT / "data" / "processed"
POWERBI = REPO_ROOT / "data" / "powerbi"
EXTERNAL = REPO_ROOT / "data" / "external"

# Baseline weights live in database/seeds/01_seed_reference.sql and are read from
# the database at runtime. Restated here only so the offline tests can verify the
# published composite; test_baseline_weights_match_seed proves they agree.
BASE_WEIGHTS = {
    "demand_score": 0.30,
    "revenue_score": 0.25,
    "competition_score": 0.15,
    "strategic_fit_score": 0.15,
    "feasibility_score": 0.15,
}

# Generated data is not committed, so on a fresh clone the tests that read it
# must skip. This is deliberately NOT a module-level mark: the privacy sweep and
# the SQL/Python parity checks read only committed source files, and they are the
# two checks most worth running on a clone that has never built anything.
needs_scores = pytest.mark.skipif(
    not (PROCESSED / "parking_acquisition_score.csv").exists(),
    reason="Scoring outputs absent; run `make pipeline && make score` first.",
)
needs_validation = pytest.mark.skipif(
    not (REPO_ROOT / "validation" / "rank_stability_results.csv").exists(),
    reason="Validation outputs absent; run `make score` first.",
)
needs_powerbi = pytest.mark.skipif(
    not (POWERBI / "FactAcquisitionScore.csv").exists(),
    reason="Power BI extracts absent; run `make powerbi-data`.",
)


@pytest.fixture(scope="module")
def scores() -> pd.DataFrame:
    path = PROCESSED / "parking_acquisition_score.csv"
    if not path.exists():
        pytest.skip("scoring outputs absent")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def components() -> pd.DataFrame:
    path = PROCESSED / "parking_component_scores.csv"
    if not path.exists():
        pytest.skip("scoring outputs absent")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

PII_PATTERN = re.compile(r'"[^"]*(email|phone|mobile|fax|whatsapp)[^"]*"\s*:', re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def test_committed_osm_snapshot_has_no_personal_contact_tags():
    """OSM carries real phone numbers and personal emails on small-business
    objects. The snapshot is committed, so those tags must be stripped. The
    pipeline reads only amenity/shop/office/railway/capacity/name/access/
    parking/opening_hours, so removing them costs nothing analytically."""
    offenders: list[str] = []
    for path in sorted(EXTERNAL.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        keys = set(PII_PATTERN.findall(text))
        emails = set(EMAIL_PATTERN.findall(text))
        if keys or emails:
            offenders.append(f"{path.name}: tag keys={sorted(keys)} emails={len(emails)}")
    assert not offenders, "personal contact data in committed snapshot:\n" + "\n".join(offenders)


def test_attribution_tags_are_retained():
    """The strip must not be overzealous. `operator` is an organisation name that
    ODbL attribution benefits from and it must survive."""
    snapshot = json.loads((EXTERNAL / "osm_features_snapshot.json").read_text(encoding="utf-8"))
    operators = sum(1 for element in snapshot["elements"] if "operator" in (element.get("tags") or {}))
    assert operators > 100, f"expected operator tags to survive the strip, found {operators}"


# ---------------------------------------------------------------------------
# Single source of truth
# ---------------------------------------------------------------------------

def test_python_patch_coefficients_match_the_sql_view():
    """score_scenario() re-derives two subcomponents by subtracting the baseline
    contribution and adding the scenario-adjusted one. That is only valid while
    its coefficients equal the SQL ones.

    Both patches cancel exactly in the base case, so a drift here would leave the
    headline ranking correct and silently corrupt only the sensitivity and rank
    stability outputs. Nothing else in the suite would notice.
    """
    sql = (REPO_ROOT / "sql" / "analysis" / "component_scores.sql").read_text(encoding="utf-8")

    onboarding = re.search(r"([0-9.]+)\s*\*\s*s\.onboarding_cost_score", sql)
    assert onboarding, "could not locate the onboarding_cost_score term in component_scores.sql"
    assert float(onboarding.group(1)) == pytest.approx(FEASIBILITY_ONBOARDING_COST_WEIGHT), (
        f"SQL applies {onboarding.group(1)} to onboarding_cost_score but "
        f"scoring_engine.FEASIBILITY_ONBOARDING_COST_WEIGHT is {FEASIBILITY_ONBOARDING_COST_WEIGHT}"
    )

    network = re.search(r"\(\s*([0-9.]+)\s*\*\s*s\.network_distance_score", sql)
    assert network, "could not locate the network_distance_score term in component_scores.sql"
    assert float(network.group(1)) == pytest.approx(STRATEGIC_NETWORK_DISTANCE_WEIGHT), (
        f"SQL applies {network.group(1)} to network_distance_score but "
        f"scoring_engine.STRATEGIC_NETWORK_DISTANCE_WEIGHT is {STRATEGIC_NETWORK_DISTANCE_WEIGHT}"
    )


@needs_scores
def test_base_case_python_pillars_reconcile_with_sql(components, scores):
    """The load-bearing test. SQL defines the baseline pillars; Python recomputes
    Demand and Revenue so scenario multipliers can apply. In the base case every
    multiplier is 1.0, so the two must agree exactly. This one assertion covers
    roughly a dozen constants duplicated across the two files, including the 0.76
    realisation factor, the 0.85 utilisation cap and the 1.35 uplift cap."""
    report = reconcile_base_case_against_sql(components, scores)
    failures = report[report.status == "FAIL"]
    assert failures.empty, (
        "SQL and Python disagree on the base case, so a shared constant was edited "
        f"in only one file:\n{report.to_string(index=False)}"
    )
    assert (report.status == "PASS").sum() >= 13, "reconciliation covered fewer measures than expected"


def test_baseline_weights_match_seed():
    """The runtime weights come from the database seed. Confirm the seed still
    declares the documented 30/25/15/15/15 split, so the offline tests and the
    documentation are describing the deployed model."""
    seed = (REPO_ROOT / "database" / "seeds" / "01_seed_reference.sql").read_text(encoding="utf-8")
    expected = {"DEMAND": 0.30, "REVENUE": 0.25, "COMPETITION": 0.15,
                "STRATEGIC_FIT": 0.15, "FEASIBILITY": 0.15}
    for dimension, weight in expected.items():
        assert re.search(rf"\(\s*1\s*,\s*'{dimension}'\s*,\s*{weight:g}0*\s*\)", seed), (
            f"weight set 1 no longer declares {dimension} = {weight} in the seed"
        )


def test_winsor_score_agrees_with_sql_semantics():
    """winsor_score mirrors SQL normalize_winsor. Two branches used to disagree:
    a non-positive denominator, and NULL precedence. The Series and scalar call
    paths also disagreed with each other, and both are used in production."""
    cases = [
        ("normal", 50.0, 0.0, 100.0, 50.0),
        ("clip below lower", -10.0, 0.0, 100.0, 0.0),
        ("clip above upper", 200.0, 0.0, 100.0, 100.0),
        ("degenerate upper == lower", 5.0, 5.0, 5.0, 50.0),
        ("inverted bounds", 5.0, 10.0, 2.0, 50.0),
    ]
    for name, value, low, high, expected in cases:
        series_path = winsor_score(pd.Series([value]), pd.Series([low]), pd.Series([high])).iloc[0]
        scalar_path = winsor_score(pd.Series([value]), low, high).iloc[0]
        assert series_path == pytest.approx(expected), f"{name}: series path returned {series_path}"
        assert scalar_path == pytest.approx(expected), f"{name}: scalar path returned {scalar_path}"

    assert pd.isna(winsor_score(pd.Series([float("nan")]), 0.0, 100.0).iloc[0]), (
        "a NULL input must stay NULL, matching SQL's value IS NULL short-circuit"
    )
    assert winsor_score(pd.Series([25.0]), 0.0, 100.0, invert=True).iloc[0] == pytest.approx(75.0)


def test_network_band_score_breakpoints():
    """Distance band must be continuous and match the documented shape: penalise
    cannibalisation under 400 m, reward 1.5-6 km spacing, taper beyond 6 km."""
    assert network_score(pd.Series([0.0])).iloc[0] == pytest.approx(10.0)
    assert network_score(pd.Series([0.40])).iloc[0] == pytest.approx(35.0)
    assert network_score(pd.Series([1.50])).iloc[0] == pytest.approx(100.0)
    assert network_score(pd.Series([6.00])).iloc[0] == pytest.approx(100.0)
    assert network_score(pd.Series([9.00])).iloc[0] == pytest.approx(65.0)
    assert network_score(pd.Series([50.0])).iloc[0] == pytest.approx(65.0)
    # Clamped, unlike the SQL version, which would return a negative score for a
    # negative distance and breach the 0-100 CHECK constraint.
    assert network_score(pd.Series([-2.0])).iloc[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Model integrity
# ---------------------------------------------------------------------------

@needs_scores
def test_expected_lot_count(scores):
    assert len(scores) == settings.target_lot_count
    assert scores.parking_id.is_unique


@needs_scores
def test_all_scores_within_range(scores):
    columns = [*COMPONENT_COLUMNS.values(), "attractiveness_score", "acquisition_score"]
    block = scores[columns]
    assert not block.isna().to_numpy().any(), "NaN present in a pillar or composite score"
    assert block.to_numpy().min() >= 0.0
    assert block.to_numpy().max() <= 100.0


@needs_scores
def test_composite_is_exactly_the_weighted_sum(scores):
    """No hidden term, no manual override, no post-hoc adjustment. If someone
    nudges a favourite lot, this fails."""
    reconstructed = sum(scores[column] * weight for column, weight in BASE_WEIGHTS.items())
    assert (reconstructed - scores.acquisition_score).abs().max() < 1e-9


@needs_scores
def test_attractiveness_excludes_feasibility(scores):
    """Feasibility is deliberately on a separate axis: a lot that is wonderful
    and unobtainable needs a different BD response from one that is mediocre and
    easy. Attractiveness must therefore renormalise over the other four."""
    non_feasibility = {k: v for k, v in BASE_WEIGHTS.items() if k != "feasibility_score"}
    expected = sum(scores[c] * w for c, w in non_feasibility.items()) / sum(non_feasibility.values())
    assert (expected - scores.attractiveness_score).abs().max() < 1e-9


@needs_scores
def test_ranks_are_unique_and_contiguous(scores):
    assert sorted(scores.rank_overall) == list(range(1, len(scores) + 1))
    ordered = scores.sort_values("rank_overall")
    assert ordered.acquisition_score.is_monotonic_decreasing


@needs_scores
def test_no_input_encodes_the_recommendation(components):
    """Leakage guard. The recommendation must emerge from the model, so no source
    source column may carry a pre-baked verdict. Derived `*_score` columns are
    legitimate model internals; a raw flag would not be."""
    banned = re.compile(r"recommend|is_target|should_acquire|priority|acquisition_difficulty|shortlist", re.IGNORECASE)
    offenders = [c for c in components.columns if banned.search(c)]
    assert not offenders, f"outcome-encoding column in the feature layer: {offenders}"


@needs_scores
def test_segment_thresholds_are_derived_from_the_distribution(scores):
    """Thresholds were provisional placeholders in the schema layer. They must be
    calibrated from the observed base-case distribution, not hard-coded."""
    summary = json.loads((REPO_ROOT / "validation" / "scoring_execution_summary.json").read_text(encoding="utf-8"))
    thresholds = summary["thresholds"]
    assert thresholds["attractiveness_high"] == pytest.approx(round(float(scores.attractiveness_score.quantile(0.67)), 2), abs=0.02)
    assert thresholds["attractiveness_develop"] == pytest.approx(round(float(scores.attractiveness_score.quantile(0.33)), 2), abs=0.02)
    assert thresholds["feasibility_mid"] == pytest.approx(round(float(scores.feasibility_score.quantile(0.50)), 2), abs=0.02)


@needs_scores
def test_segmentation_uses_three_thresholds_not_a_2x2_quadrant(scores):
    """A 2x2 attractiveness/feasibility wash would colour low-attractiveness,
    high-feasibility lots as DEVELOP. DEVELOP has an attractiveness floor, so
    AVOID lots must exist above the feasibility median."""
    summary = json.loads((REPO_ROOT / "validation" / "scoring_execution_summary.json").read_text(encoding="utf-8"))
    floor = summary["thresholds"]["attractiveness_develop"]
    feasibility_mid = summary["thresholds"]["feasibility_mid"]
    below_floor_but_feasible = scores[
        (scores.attractiveness_score < floor) & (scores.feasibility_score >= feasibility_mid)
    ]
    assert len(below_floor_but_feasible) > 0, "no lot exercises the DEVELOP attractiveness floor"
    assert (below_floor_but_feasible.segment_code == "AVOID").all()


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

@needs_scores
def test_all_monotonicity_directions_hold(components):
    """Higher demand, revenue potential, tariff, owner readiness and whitespace
    must never reduce their pillar; more competition and higher acquisition cost
    must never improve theirs."""
    from python.model_validation.diagnostics import monotonicity_tests

    report = monotonicity_tests(components)
    failures = report[report.status != "PASS"]
    assert failures.empty, f"monotonicity violated:\n{report.to_string(index=False)}"
    expected = {"MONO-DEMAND", "MONO-REVENUE", "MONO-COST", "MONO-FEASIBILITY",
                "MONO-COMPETITION", "MONO-STRATEGIC", "MONO-TARIFF"}
    assert expected.issubset(set(report.test_id)), f"missing coverage: {expected - set(report.test_id)}"


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

@needs_powerbi
@needs_scores
def test_powerbi_extract_reconciles_with_the_analytical_layer(scores):
    """The dashboard must not be a third opinion. Extracts are written rounded to
    2dp, so the tolerance is half a unit in the last place, not exact equality."""
    fact = pd.read_csv(POWERBI / "FactAcquisitionScore.csv").set_index("parking_id").sort_index()
    base = scores.set_index("parking_id").sort_index()
    assert len(fact) == len(base)
    for column in [*COMPONENT_COLUMNS.values(), "attractiveness_score", "acquisition_score"]:
        difference = (base[column] - fact[column]).abs().max()
        assert difference <= 0.005, f"{column} differs by {difference}, beyond 2dp rounding"
    assert (base.rank_overall == fact.acquisition_rank).all(), "Power BI rank disagrees"
    assert (base.segment_code == fact.priority_segment).all(), "Power BI segment disagrees"


@needs_powerbi
def test_powerbi_component_contributions_sum_to_the_score():
    """Page 4 explains a lot by decomposing its score. The parts must sum to the
    whole or the explanation is fiction."""
    component = pd.read_csv(POWERBI / "FactScoreComponent.csv")
    fact = pd.read_csv(POWERBI / "FactAcquisitionScore.csv").set_index("parking_id")
    assert len(component) == settings.target_lot_count * len(COMPONENT_COLUMNS)
    totals = component.groupby("parking_id").weighted_contribution.sum()
    assert (totals - fact.acquisition_score).abs().max() <= 0.02
    per_lot = component.groupby("parking_id").weight_applied.sum()
    assert (per_lot - 1.0).abs().max() < 1e-6, "weights do not sum to 1 for every lot"


@needs_scores
def test_bd_funnel_recalculates_from_raw_events():
    """Recompute the funnel independently from the 385 event rows rather than
    trusting the published aggregate."""
    events = pd.read_csv(PROCESSED / "outreach_events.csv")
    leads = pd.read_csv(PROCESSED / "outreach.csv")
    published = pd.read_csv(PROCESSED / "bd_funnel_dashboard.csv").set_index("stage_id").sort_index()

    recalculated = events.groupby("stage_id").lead_id.nunique().sort_index()
    assert (recalculated.reindex(published.index) == published.leads_reached).all(), (
        "funnel stage counts do not match a recount from the event rows"
    )
    # Monotonically narrowing: nobody reaches a later stage without an earlier one.
    assert published.sort_values("stage_order").leads_reached.is_monotonic_decreasing

    furthest = events.groupby("lead_id").stage_id.max()
    assert (leads.set_index("lead_id").furthest_stage_id == furthest).all(), (
        "furthest_stage_id disagrees with the maximum recorded event stage"
    )
    won = int((leads.pipeline_status == "Won").sum())
    final_stage = int(published.sort_values("stage_order").leads_reached.iloc[-1])
    assert won == final_stage, f"{won} leads marked Won but {final_stage} reached the final stage"


@needs_validation
def test_rank_stability_covers_every_lot_over_the_primary_scenarios():
    """rank_stability_pct means top-10 persistence across the primary scenarios,
    not general rank stability. Guard the grain so the label keeps its meaning."""
    stability = pd.read_csv(REPO_ROOT / "validation" / "rank_stability_results.csv")
    assert len(stability) == settings.target_lot_count
    assert stability.scenarios_evaluated.nunique() == 1
    evaluated = int(stability.scenarios_evaluated.iloc[0])
    assert stability.top_10_scenario_count.max() <= evaluated
    expected = stability.top_10_scenario_count / evaluated * 100.0
    assert (expected - stability.rank_stability_pct).abs().max() < 0.01
    assert stability.min_rank.le(stability.median_rank).all()
    assert stability.median_rank.le(stability.max_rank).all()


@needs_scores
def test_scenario_scores_exist_for_every_lot_and_scenario():
    scenario = pd.read_csv(PROCESSED / "lot_scenario_score.csv")
    counts = scenario.groupby("scenario_id").parking_id.nunique()
    assert (counts == settings.target_lot_count).all(), "a scenario is missing lots"
    assert len(counts) >= 10, "fewer scenarios than the documented primary set"
    block = scenario[[*COMPONENT_COLUMNS.values(), "acquisition_score"]]
    assert block.to_numpy().min() >= 0.0 and block.to_numpy().max() <= 100.0
    for _, group in scenario.groupby("scenario_id"):
        assert sorted(group.rank_overall) == list(range(1, len(group) + 1))


@needs_scores
def test_reproducibility_manifest_records_generating_versions():
    """numpy's Generator.binomial uses rejection sampling once n*p >= 30 and its
    output is not guaranteed stable across numpy releases. Recording the versions
    turns a future hash mismatch into a diagnosable fact."""
    manifest = json.loads((PROCESSED / "build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["random_seed"] == settings.random_seed
    assert "generated_with" in manifest, "build manifest does not record library versions"
    assert {"numpy", "pandas"} <= set(manifest["generated_with"])
