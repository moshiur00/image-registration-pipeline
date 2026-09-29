from __future__ import annotations

import numpy as np
import pytest

from image_registration.affine_ransac import (
    affine_transform_diagnostics,
    correspondence_geometry_diagnostics,
    estimate_affine_ransac,
    point_grid_coverage,
    point_linearity_ratio,
)
from image_registration.transforms import affine_matrix, apply_transform, rotation_matrix


def _distributed_points() -> np.ndarray:
    return np.asarray(
        [
            [20.0, 20.0],
            [100.0, 20.0],
            [180.0, 20.0],
            [20.0, 100.0],
            [100.0, 100.0],
            [180.0, 100.0],
            [20.0, 180.0],
            [100.0, 180.0],
            [180.0, 180.0],
        ],
        dtype=np.float64,
    )


def _affine_transform() -> np.ndarray:
    rotation = rotation_matrix(12.0)[:2, :2]
    shear = np.asarray([[1.0, 0.08], [0.0, 1.0]], dtype=np.float64)
    scale = np.diag([1.08, 0.93])
    return affine_matrix(rotation @ shear @ scale, tx=14.0, ty=-11.0)


def test_point_grid_coverage_for_distributed_points() -> None:
    coverage = point_grid_coverage(_distributed_points(), (200, 200), rows=4, cols=4)
    assert coverage >= 0.5


def test_linearity_ratio_detects_collinear_points() -> None:
    x = np.linspace(10.0, 190.0, 20)
    points = np.column_stack([x, 0.5 * x + 3.0])
    assert point_linearity_ratio(points) < 1e-10


def test_correspondence_geometry_records_both_images() -> None:
    moving = _distributed_points()
    fixed = apply_transform(moving, _affine_transform())
    diagnostics = correspondence_geometry_diagnostics(
        fixed,
        moving,
        fixed_shape=(220, 220),
        moving_shape=(220, 220),
    )
    assert diagnostics.minimum_grid_coverage > 0.0
    assert diagnostics.fixed_linearity_ratio > 0.1
    assert diagnostics.moving_linearity_ratio > 0.1


def test_affine_transform_diagnostics_accept_plausible_transform() -> None:
    diagnostics = affine_transform_diagnostics(_affine_transform(), image_shape=(256, 256))
    assert diagnostics.plausible
    assert diagnostics.rejection_reasons == ()


def test_affine_transform_diagnostics_reject_large_scale() -> None:
    transform = affine_matrix(np.diag([2.5, 2.2]), tx=0.0, ty=0.0)
    diagnostics = affine_transform_diagnostics(transform, image_shape=(256, 256))
    assert not diagnostics.plausible
    assert "implausible_principal_scale" in diagnostics.rejection_reasons


def test_affine_transform_diagnostics_reject_near_singular_transform() -> None:
    transform = affine_matrix(np.asarray([[1.0, 0.0], [0.0, 0.01]]), tx=0.0, ty=0.0)
    diagnostics = affine_transform_diagnostics(transform, image_shape=(256, 256))
    assert not diagnostics.plausible
    assert "near_singular_transform" in diagnostics.rejection_reasons


def test_affine_ransac_recovers_known_transform() -> None:
    moving = _distributed_points()
    expected = _affine_transform()
    fixed = apply_transform(moving, expected)
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(220, 220),
        moving_shape=(220, 220),
        reprojection_threshold=0.5,
        minimum_matches=6,
        minimum_inliers=6,
        minimum_spatial_coverage=0.1,
    )
    assert result.success
    assert result.estimated_transform is not None
    assert np.allclose(result.estimated_transform, expected, atol=1e-8)
    assert result.inlier_count == moving.shape[0]


def test_affine_ransac_rejects_injected_outliers() -> None:
    rng = np.random.default_rng(7)
    moving = rng.uniform(10.0, 190.0, size=(80, 2))
    expected = _affine_transform()
    fixed = apply_transform(moving, expected)
    fixed[:20] = rng.uniform(10.0, 190.0, size=(20, 2))
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(200, 200),
        moving_shape=(200, 200),
        reprojection_threshold=1.0,
        minimum_matches=8,
        minimum_inliers=20,
        minimum_spatial_coverage=0.1,
        random_seed=42,
    )
    assert result.success
    assert result.inlier_count >= 55
    assert np.count_nonzero(result.inlier_mask[:20]) <= 2


def test_affine_ransac_fails_safely_for_collinear_points() -> None:
    x = np.linspace(10.0, 190.0, 12)
    moving = np.column_stack([x, 0.4 * x + 5.0])
    fixed = apply_transform(moving, _affine_transform())
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(200, 200),
        moving_shape=(200, 200),
        minimum_matches=6,
        minimum_inliers=6,
        minimum_spatial_coverage=0.0,
        minimum_linearity_ratio=0.01,
    )
    assert not result.success
    assert result.failure_reason == "degenerate_correspondences_collinear"


def test_affine_ransac_fails_safely_for_poor_spatial_coverage() -> None:
    moving = np.asarray(
        [[10, 10], [15, 12], [20, 15], [12, 20], [18, 22], [24, 18], [25, 25], [30, 22]],
        dtype=np.float64,
    )
    fixed = apply_transform(moving, _affine_transform())
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(400, 400),
        moving_shape=(400, 400),
        minimum_matches=6,
        minimum_inliers=6,
        minimum_spatial_coverage=0.125,
        minimum_linearity_ratio=0.001,
    )
    assert not result.success
    assert result.failure_reason == "poor_spatial_coverage"


def test_affine_ransac_rejects_implausible_estimated_scale() -> None:
    moving = _distributed_points()
    expected = affine_matrix(np.diag([2.2, 2.1]), tx=3.0, ty=4.0)
    fixed = apply_transform(moving, expected)
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(600, 600),
        moving_shape=(220, 220),
        reprojection_threshold=0.5,
        minimum_matches=6,
        minimum_inliers=6,
        minimum_spatial_coverage=0.1,
        max_principal_scale=1.8,
    )
    assert not result.success
    assert result.failure_reason == "implausible_principal_scale"


def test_affine_ransac_reports_insufficient_matches() -> None:
    moving = _distributed_points()[:2]
    fixed = moving.copy()
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(200, 200),
        moving_shape=(200, 200),
        minimum_matches=6,
        minimum_inliers=6,
    )
    assert not result.success
    assert result.failure_reason == "insufficient_matches"


def test_invalid_affine_ransac_threshold_is_rejected() -> None:
    with pytest.raises(ValueError):
        estimate_affine_ransac(
            _distributed_points(),
            _distributed_points(),
            fixed_shape=(200, 200),
            moving_shape=(200, 200),
            reprojection_threshold=0.0,
        )
