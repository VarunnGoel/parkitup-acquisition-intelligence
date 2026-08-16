from __future__ import annotations

import json
from pathlib import Path

import matplotlib.image as mpimg
import pandas as pd
import pytest

from python.analysis.prepare_powerbi import compute_powerbi_metrics
from python.config import REPO_ROOT


DATA_DIR = REPO_ROOT / "data" / "powerbi"
PACKAGE_DIR = REPO_ROOT / "dashboard" / "powerbi"


def _metric_frames() -> dict[str, pd.DataFrame]:
    return {
        "DimParking": pd.read_csv(DATA_DIR / "DimParking.csv"),
        "DimLocality": pd.read_csv(DATA_DIR / "DimLocality.csv"),
        "FactAcquisitionScore": pd.read_csv(DATA_DIR / "FactAcquisitionScore.csv"),
        "FactDailyPerformance": pd.read_csv(DATA_DIR / "FactDailyPerformance.csv"),
        "FactOutreach": pd.read_csv(DATA_DIR / "FactOutreach.csv"),
    }


def test_powerbi_portable_model_reconciles_core_and_filtered_metrics() -> None:
    frames = _metric_frames()
    base = compute_powerbi_metrics(frames)
    assert base["Total Parking Lots"] == 120
    assert base["Total Capacity"] == 23_685
    assert base["High Priority Count"] == 25
    assert base["Average Occupancy Pct"] == pytest.approx(33.8952006849)
    assert base["Expected Monthly Platform Revenue INR"] == pytest.approx(6_052_472.71)
    assert base["BD Conversion Rate Pct"] == pytest.approx(10.0)

    connaught = compute_powerbi_metrics(frames, {"locality_name": "Connaught Place"})
    assert connaught["Total Parking Lots"] == 11
    assert connaught["Total Capacity"] == 1_849
    assert connaught["High Priority Count"] == 8
    assert connaught["Average Acquisition Score"] == pytest.approx(63.8872727273)

    combined = compute_powerbi_metrics(
        frames,
        {"locality_name": "Connaught Place", "priority_segment": "ACQUIRE_NOW"},
    )
    assert combined["Total Parking Lots"] == 8
    assert combined["Expected Monthly Platform Revenue INR"] == pytest.approx(1_231_621.74)


def test_powerbi_top10_matches_base_ranking() -> None:
    scores = pd.read_csv(DATA_DIR / "FactAcquisitionScore.csv")
    top10 = scores.nsmallest(10, "acquisition_rank")
    assert top10["parking_id"].tolist() == [52, 18, 1, 51, 6, 17, 41, 3, 8, 13]
    assert top10["acquisition_rank"].tolist() == list(range(1, 11))


def test_powerbi_model_keys_and_scenario_grains_are_valid() -> None:
    parking = pd.read_csv(DATA_DIR / "DimParking.csv")
    scenario = pd.read_csv(DATA_DIR / "DimScenario.csv")
    scenario_scores = pd.read_csv(DATA_DIR / "FactScenarioScore.csv")
    scenario_components = pd.read_csv(DATA_DIR / "FactScenarioComponent.csv")
    assert not parking["parking_id"].duplicated().any()
    assert len(scenario) == 11
    assert len(scenario_scores) == 1_320
    assert not scenario_scores.duplicated(["parking_id", "scenario_id"]).any()
    assert len(scenario_components) == 6_600
    assert not scenario_components.duplicated(["parking_id", "scenario_id", "dimension_code"]).any()


def test_powerbi_package_and_theme_are_complete() -> None:
    required = [
        "README.md",
        "data_sources.md",
        "data_model.md",
        "relationships.md",
        "dax_measures.md",
        "field_mappings.md",
        "theme.md",
        "validation.md",
        "page_01_executive.md",
        "page_02_market.md",
        "page_03_acquisition.md",
        "page_04_deep_dive.md",
        "page_05_bd_strategy.md",
        "parkitup_theme.json",
    ]
    for filename in required:
        assert (PACKAGE_DIR / filename).exists(), filename
    theme = json.loads((PACKAGE_DIR / "parkitup_theme.json").read_text(encoding="utf-8"))
    assert theme["name"] == "PARK It Up Decision"
    assert len(theme["dataColors"]) >= 6
    dax = (PACKAGE_DIR / "dax_measures.md").read_text(encoding="utf-8")
    assert "DIVIDE(" in dax
    assert "Funnel Stage Leads" in dax
    assert "Acquire Now Attractiveness Threshold" in dax


def test_powerbi_mockups_are_nonblank_16_by_9_images() -> None:
    screenshots = sorted((PACKAGE_DIR / "screenshots").glob("page_*.png"))
    assert len(screenshots) == 5
    for path in screenshots:
        image = mpimg.imread(path)
        height, width = image.shape[:2]
        assert width / height == pytest.approx(16 / 9, rel=0.01)
        assert float(image.std()) > 0.05
