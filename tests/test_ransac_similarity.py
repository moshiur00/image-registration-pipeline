from __future__ import annotations

import numpy as np
import pytest

from image_registration.ransac import (
    estimate_similarity_ransac,
    residual_summary,
    similarity_scale,
)
from image_registration.transforms import apply_transform, similarity_matrix


def _points() -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(30.0, 220.0, 7), np.linspace(25.0, 210.0, 6))
    return np.column_stack([xs.ravel(), ys.ravel()]).astype(np.float64)


def test_similarity_ransac_recovers_exact_correspondences() -> None:
    moving = _points()
    transform = similarity_matrix(1.12, 17.0, tx=24.0, ty=-13.0, center=[128.0, 128.0])
    fixed = apply_transform(moving, transform)

    result = estimate_similarity_ransac(
        fixed,
        moving,
        reprojection_threshold=0.5,
        minimum_matches=8,
        minimum_inliers=8,
        minimum_inlier_ratio=0.8,
    )

    assert result.success
    assert result.estimated_transform is not None
    assert result.inlier_count == moving.shape[0]
    assert np.allclose(result.estimated_transform, transform, atol=1e-6)


def test_similarity_ransac_rejects_injected_outliers() -> None:
    rng = np.random.default_rng(7)
    moving = _points()
    transform = similarity_matrix(0.93, -21.0, tx=-16.0, ty=19.0, center=[128.0, 128.0])
    fixed = apply_transform(moving, transform)

    outlier_indices = rng.choice(moving.shape[0], size=12, replace=False)
    corrupted = fixed.copy()
    corrupted[outlier_indices] = rng.uniform([0.0, 0.0], [255.0, 255.0], size=(12, 2))

    result = estimate_similarity_ransac(
        corrupted,
        moving,
        reprojection_threshold=1.5,
        minimum_matches=8,
        minimum_inliers=20,
        minimum_inlier_ratio=0.6,
        random_seed=17,
    )

    assert result.success
    assert result.estimated_transform is not None
    assert result.outlier_count >= 10
    assert np.allclose(result.estimated_transform, transform, atol=1e-5)


def test_similarity_ransac_fails_safely_with_too_few_matches() -> None:
    moving = np.asarray([[10.0, 10.0], [20.0, 20.0], [30.0, 15.0]], dtype=np.float64)
    fixed = moving.copy()
    result = estimate_similarity_ransac(fixed, moving, minimum_matches=4)
    assert not result.success
    assert result.failure_reason == "insufficient_matches"
    assert result.estimated_transform is None


def test_similarity_ransac_requires_equal_point_counts() -> None:
    with pytest.raises(ValueError, match="same number"):
        estimate_similarity_ransac(np.zeros((5, 2)), np.zeros((4, 2)))


def test_similarity_ransac_rejects_invalid_point_shape() -> None:
    with pytest.raises(ValueError, match="shape"):
        estimate_similarity_ransac(np.zeros((5, 3)), np.zeros((5, 2)))


def test_similarity_ransac_rejects_nonfinite_points() -> None:
    fixed = np.zeros((5, 2), dtype=np.float64)
    moving = fixed.copy()
    moving[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        estimate_similarity_ransac(fixed, moving)


@pytest.mark.parametrize("threshold", [0.0, -1.0, np.inf])
def test_similarity_ransac_rejects_invalid_reprojection_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="reprojection_threshold"):
        estimate_similarity_ransac(_points(), _points(), reprojection_threshold=threshold)


def test_similarity_ransac_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        estimate_similarity_ransac(_points(), _points(), confidence=1.0)


def test_similarity_scale_extracts_isotropic_scale() -> None:
    transform = similarity_matrix(1.27, 28.0, tx=5.0, ty=-3.0, center=[80.0, 90.0])
    assert similarity_scale(transform) == pytest.approx(1.27, abs=1e-12)


def test_residual_summary_reports_inlier_statistics() -> None:
    moving = _points()
    transform = similarity_matrix(1.05, 8.0, tx=4.0, ty=-7.0, center=[128.0, 128.0])
    fixed = apply_transform(moving, transform)
    result = estimate_similarity_ransac(fixed, moving, reprojection_threshold=0.5)
    summary = residual_summary(result)
    assert summary["inlier_mean"] is not None
    assert summary["inlier_mean"] < 1e-5
    assert summary["all_maximum"] is not None


def test_similarity_ransac_is_repeatable_for_same_seed() -> None:
    rng = np.random.default_rng(19)
    moving = _points()
    transform = similarity_matrix(1.08, -13.0, tx=17.0, ty=9.0, center=[128.0, 128.0])
    fixed = apply_transform(moving, transform)
    corrupted = fixed.copy()
    corrupted[:10] = rng.uniform([0.0, 0.0], [255.0, 255.0], size=(10, 2))

    a = estimate_similarity_ransac(corrupted, moving, random_seed=123, reprojection_threshold=1.5)
    b = estimate_similarity_ransac(corrupted, moving, random_seed=123, reprojection_threshold=1.5)
    assert a.success == b.success
    assert np.array_equal(a.inlier_mask, b.inlier_mask)
    assert np.allclose(a.estimated_transform, b.estimated_transform)
