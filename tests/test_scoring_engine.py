from __future__ import annotations

import pandas as pd

from python.analysis.scoring_engine import classify_segments, network_score, winsor_score


def test_winsor_score_clips_and_inverts() -> None:
    values = pd.Series([-5.0, 0.0, 5.0, 10.0, 15.0])
    assert winsor_score(values, 0.0, 10.0).tolist() == [0.0, 0.0, 50.0, 100.0, 100.0]
    assert winsor_score(values, 0.0, 10.0, invert=True).tolist() == [100.0, 100.0, 50.0, 0.0, 0.0]


def test_network_band_penalises_cannibalisation_and_rewards_cluster_extension() -> None:
    scores = network_score(pd.Series([0.1, 0.4, 1.5, 4.0, 8.5]))
    assert scores.iloc[0] < scores.iloc[1]
    assert scores.iloc[2] == 100.0
    assert scores.iloc[3] == 100.0
    assert scores.iloc[4] < scores.iloc[3]


def test_segment_logic_keeps_attractiveness_and_feasibility_separate() -> None:
    frame = pd.DataFrame(
        {
            "attractiveness_score": [80.0, 80.0, 55.0, 35.0],
            "feasibility_score": [70.0, 30.0, 70.0, 30.0],
        }
    )
    thresholds = {
        "attractiveness_high": 65.0,
        "attractiveness_develop": 45.0,
        "feasibility_mid": 60.0,
    }
    assert classify_segments(frame, thresholds).tolist() == [
        "ACQUIRE_NOW", "PURSUE", "DEVELOP", "AVOID"
    ]
