from math import log

import pytest

from deport_ai.evaluation import brier_score, calibration_bins, log_loss


def test_brier_and_log_loss():
    assert brier_score([0.7, 0.2], [1, 0]) == pytest.approx(0.065)
    assert log_loss([0.7, 0.2], [1, 0]) == pytest.approx(-(log(0.7) + log(0.8)) / 2)


def test_calibration_bins_group_predictions():
    bins = calibration_bins([0.7, 0.2], [1, 0], bins=2)
    assert bins[0].count == 1 and bins[1].count == 1
    assert bins[1].observed_frequency == 1.0


def test_calibration_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        calibration_bins([1.1], [1])
