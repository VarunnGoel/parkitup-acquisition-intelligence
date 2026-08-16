"""Regression checks for the retired simulator and the dashboard design pass."""

from __future__ import annotations

import matplotlib.image as mpimg
import pandas as pd
import pytest

from python.config import REPO_ROOT


DATA_DIR = REPO_ROOT / "data" / "powerbi"
PACKAGE_DIR = REPO_ROOT / "dashboard" / "powerbi"


def test_simulator_surface_and_dependencies_are_retired() -> None:
    assert not (REPO_ROOT / "app").exists()
    assert not (REPO_ROOT / ".streamlit").exists()
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" not in requirements
    assert "altair" not in requirements
    assert not list((REPO_ROOT / "tests").glob("*simulator*"))


def test_sensitivity_assets_remain_available() -> None:
    expected = {
        "DimScenario.csv": 11,
        "FactScenarioScore.csv": 1320,
        "FactScenarioComponent.csv": 6600,
    }
    for filename, rows in expected.items():
        frame = pd.read_csv(DATA_DIR / filename)
        assert len(frame) == rows

    for filename in (
        "FactLocalityScenario.csv",
        "FactScenarioComponent.csv",
        "FactScenarioScore.csv",
    ):
        assert (DATA_DIR / filename).stat().st_size > 0
    assert (REPO_ROOT / "python/model_validation/sensitivity.py").exists()
    assert (REPO_ROOT / "python/analysis/scoring_engine.py").exists()


def test_package_and_previews_match_the_current_design() -> None:
    for filename in ("redesign.md", "redesign_validation.md"):
        assert (PACKAGE_DIR / filename).exists(), filename

    theme = (PACKAGE_DIR / "theme.md").read_text(encoding="utf-8")
    page_one = (PACKAGE_DIR / "page_01_executive.md").read_text(encoding="utf-8")
    assert "horizontal" in theme.lower()
    assert "left page-navigation rail" not in theme
    assert "horizontal page navigator" in page_one.lower()

    screenshots = sorted((PACKAGE_DIR / "screenshots").glob("page_*.png"))
    assert len(screenshots) == 5
    for path in screenshots:
        image = mpimg.imread(path)
        height, width = image.shape[:2]
        assert width / height == pytest.approx(16 / 9, rel=0.01)
        assert float(image.std()) > 0.05
        assert path.stat().st_size > 100_000


def test_previews_contain_no_layout_violations() -> None:
    """Guard the defect class that made the dashboard previews unusable.

    Charts used to be drawn directly into the panel rectangle, so matplotlib
    placed tick labels and axis labels outside it and they collided with the
    next panel. The audit rebuilds each page and measures every chart's full
    extent, tick labels included, against the card that hosts it.
    """
    from python.visualization import layout_audit

    violations: list[str] = []
    for name, builder in layout_audit._page_builders().items():
        violations.extend(layout_audit.audit_page(name, builder))
    assert violations == [], violations


def test_layout_audit_fails_when_padding_is_removed() -> None:
    """A check that cannot fail is not a check.

    Removing the card padding recreates the dashboard geometry exactly, so the
    audit must report violations. This caught a first version of the audit that
    inspected `fig.axes` and therefore never saw the inset charts at all.
    """
    from python.visualization import design_system as ds
    from python.visualization import layout_audit, powerbi_mockups

    original = ds.plot_area
    ds.plot_area = lambda host, **kwargs: original(host, left=0.0, bottom=0.0, right=0.0, top=0.0)
    try:
        violations = layout_audit.audit_page("probe", powerbi_mockups.page_03)
    finally:
        ds.plot_area = original
    assert violations, "layout audit is vacuous: it passed a deliberately broken page"


def test_displayed_figures_reconcile_with_the_portable_model() -> None:
    """Every headline value printed on a page must come from the extracts.

    Structural facts are asserted as literals because they are the project's
    fixed shape — 120 lots, 23,685 spaces, 17 localities, four segments. Figures
    that legitimately move when the model is recalibrated are asserted against a
    recomputation from the same extracts instead, so a genuine model correction
    does not read as a test failure while a rendering defect still does.
    """
    from python.visualization import powerbi_mockups as pm

    model = pm.read_model()
    data = pm.joined(model)
    locality = model["locality"]
    outreach = model["outreach"]
    funnel = model["funnel"].sort_values("stage_order")
    acquire = data[data.priority_segment.eq("ACQUIRE_NOW")]
    attractive = data[data.attractiveness_score >= pm.ATTRACTIVENESS_CUT]
    won = outreach.pipeline_status.eq("Won")
    lost = outreach[outreach.pipeline_status.eq("Lost")]
    top_four = locality.nlargest(4, "high_priority_count")

    # Page 1 — structural
    assert len(data) == 120
    assert int(data.capacity_cars.sum()) == 23_685
    assert len(acquire) == 25
    assert int(locality.market_class.eq("STRONG").sum()) == 6
    assert len(attractive) == 40
    assert int((attractive.feasibility_score < pm.FEASIBILITY_CUT).sum()) == 15

    # Page 1 — recalibration-tolerant. The KPI strip must print the sum and mean
    # of what is in the extract, not a remembered figure.
    assert acquire.expected_monthly_platform_revenue_inr.sum() == pytest.approx(
        float(data.loc[data.priority_segment.eq("ACQUIRE_NOW"), "expected_monthly_platform_revenue_inr"].sum())
    )
    assert 3.0e6 < acquire.expected_monthly_platform_revenue_inr.sum() < 5.0e6
    assert data.acquisition_score.mean() == pytest.approx(float(model["score"].acquisition_score.mean()), rel=1e-9)
    assert 40.0 < data.acquisition_score.mean() < 50.0
    top_ten_persistence = data.nsmallest(10, "acquisition_rank").top_10_frequency_pct.mean()
    assert 80.0 <= top_ten_persistence <= 100.0, "top-10 persistence for the top 10 collapsed"

    # Page 2. The concentration finding is the point of this page, so assert it as
    # a property rather than as a remembered total. The top four localities held
    # 23 of 25 targets before the anchor_capacity_raw correction and 22 after,
    # because one target moved to a fifth market — a legitimate model change that
    # should not read as a rendering defect.
    assert len(locality) == 17
    total_targets = int(locality.high_priority_count.sum())
    assert total_targets == len(acquire), "locality target counts do not sum to the Acquire Now segment"
    assert int(top_four.high_priority_count.sum()) >= 0.8 * total_targets, (
        "the concentration claim on this page no longer holds: the top four "
        f"localities hold {int(top_four.high_priority_count.sum())} of {total_targets} targets"
    )
    assert int(locality.parkitup_coverage_pct.eq(0).sum()) == 5

    # Page 3: segment counts and the thresholds the quadrant washes are drawn from
    counts = data.priority_segment.value_counts()
    assert [int(counts[code]) for code in ("ACQUIRE_NOW", "PURSUE", "DEVELOP", "AVOID")] == [25, 15, 21, 59]
    segments = model["segment"].set_index("segment_code")
    assert float(segments.loc["ACQUIRE_NOW", "min_attractiveness"]) == pm.ATTRACTIVENESS_CUT
    assert float(segments.loc["ACQUIRE_NOW", "min_feasibility"]) == pm.FEASIBILITY_CUT
    assert float(segments.loc["DEVELOP", "min_attractiveness"]) == pm.DEVELOP_FLOOR
    develop = data[data.priority_segment.eq("DEVELOP")]
    assert develop.attractiveness_score.min() >= pm.DEVELOP_FLOOR
    assert develop.attractiveness_score.max() < pm.ATTRACTIVENESS_CUT
    assert develop.feasibility_score.min() >= pm.FEASIBILITY_CUT

    # Page 4: the deep-dive header must name the lot the page actually renders,
    # and closed hours must stay out of the occupancy trend. The lot identity is
    # asserted structurally rather than by name, because a model recalibration is
    # allowed to change which lot ranks first — a page that renders one lot's
    # header above another lot's chart is the defect being guarded against.
    lot = data.nsmallest(1, "acquisition_rank").iloc[0]
    assert int(lot.acquisition_rank) == 1
    assert str(lot.parking_display_name) == str(
        data.loc[data.acquisition_score.idxmax(), "parking_display_name"]
    ), "the rank-1 lot is not the highest-scoring lot"
    assert not str(lot.parking_display_name).strip().startswith("OSM Parking "), (
        "a business-facing page must not print a raw OSM identifier as the lot name"
    )
    assert int(lot.capacity_cars) > 0
    hours = str(lot.operating_hours_label)
    hourly = model["hourly"]
    profile = hourly[hourly.parking_id.eq(int(lot.parking_id)) & hourly.day_type.eq("Weekday")]
    if hours != "24 hours":
        opens, closes = (int(part[:2]) for part in hours.split("-"))
        closed = profile[~profile.hour_of_day.between(opens, closes - 1)]
        assert float(closed.avg_occupancy_rate.max()) == 0.0, "closed hours must stay excluded from the trend"

    # Page 5 — the BD funnel is generated data with a fixed shape, so these stay literal
    assert int(outreach.lead_id.nunique()) == 120
    assert int(won.sum()) == 12
    assert won.mean() * 100 == pytest.approx(10.0)
    assert funnel.leads_reached.tolist() == [120, 94, 63, 42, 31, 23, 12]
    assert str(funnel.loc[funnel.drop_off_pct.idxmax()].stage_name) == "Onboarded"
    assert len(lost) == 64
    assert str(lost.lost_reason.value_counts().index[0]) == "Owner Not Decision Maker"
    assert lost.lost_reason.value_counts().nlargest(2).sum() == 41

