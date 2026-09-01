from __future__ import annotations

import numpy as np
import pytest

from image_registration.evaluation import (
    evaluate_pair,
    mean_absolute_error,
    normalized_cross_correlation,
    structural_similarity,
)


def test_identical_images_have_expected_metrics() -> None:
    image = np.arange(100, dtype=np.float32).reshape(10, 10) / 100.0
    metrics = evaluate_pair(image, image)
    assert metrics["mae"] == pytest.approx(0.0)
    assert metrics["mse"] == pytest.approx(0.0)
    assert metrics["ncc"] == pytest.approx(1.0)
    assert metrics["ssim"] == pytest.approx(1.0)


def test_changed_image_reduces_similarity() -> None:
    fixed = np.zeros((12, 12), dtype=np.float32)
    fixed[3:9, 3:9] = 1.0
    moving = np.roll(fixed, shift=2, axis=1)
    assert mean_absolute_error(fixed, moving) > 0.0
    assert normalized_cross_correlation(fixed, moving) < 1.0
    assert structural_similarity(fixed, moving) < 1.0


def test_mask_limits_metric_region() -> None:
    fixed = np.zeros((10, 10), dtype=np.float32)
    moving = fixed.copy()
    moving[0, 0] = 1.0
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:, 2:] = True
    assert mean_absolute_error(fixed, moving, mask=mask) == pytest.approx(0.0)


def test_evaluation_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="identical shapes"):
        evaluate_pair(np.zeros((8, 8)), np.zeros((9, 8)))
