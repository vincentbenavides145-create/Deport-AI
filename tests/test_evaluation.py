from math import log

import pytest

from deport_ai.evaluation import calibration_bins, evaluate_binary_predictions


def test_evaluates_binary_probabilities_without_persisting_data():
    result = evaluate_binary_predictions([0.7, 0.2], [1, 0], bins=2)
    assert result.brier_score == pytest.approx(0.065)
    assert result.log_loss == pytest.approx(-(log(0.7) + log(0.8)) / 2)
    assert result.calibration[0].count == 1
    assert result.calibration[1].observed_frequency == 1.0


def test_calibration_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        calibration_bins([1.1], [1])


def test_evaluates_multiclass_1x2():
    from deport_ai.evaluation import evaluate_multiclass_1x2

    probs = [
        (0.70, 0.20, 0.10),  # Predicted Home, actual Home -> correct
        (0.25, 0.50, 0.25),  # Predicted Draw, actual Draw -> correct
        (0.30, 0.30, 0.40),  # Predicted Away, actual Home -> incorrect
    ]
    outcomes = ["1", "X", "1"]
    res = evaluate_multiclass_1x2(probs, outcomes)

    assert res.sample_size == 3
    assert res.accuracy == pytest.approx(2 / 3, 0.01)
    assert res.brier_score > 0.0
    assert res.log_loss > 0.0
    assert res.home_accuracy == 0.5  # 1 out of 2 home wins predicted
    assert res.draw_accuracy == 1.0  # 1 out of 1 draw predicted

