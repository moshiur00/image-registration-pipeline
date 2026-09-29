from __future__ import annotations

import numpy as np

from image_registration.affine_ransac import estimate_affine_ransac_from_matches
from image_registration.feature_matching import FeatureMatch, FeatureMatchResult
from image_registration.ransac import estimate_similarity_ransac_from_matches
from image_registration.sift import SIFTFeatureResult, SIFTKeypoint
from image_registration.transforms import affine_matrix, apply_transform, similarity_matrix


def _sift_features(points: np.ndarray) -> SIFTFeatureResult:
    keypoints = tuple(
        SIFTKeypoint(
            x=float(x),
            y=float(y),
            size=8.0,
            angle_degrees=0.0,
            response=1.0,
            octave=0,
            class_id=-1,
        )
        for x, y in points
    )
    descriptors = np.zeros((len(keypoints), 128), dtype=np.float32)
    return SIFTFeatureResult(
        keypoints=keypoints,
        descriptors=descriptors,
        success=True,
        runtime_seconds=0.0,
        image_shape=(256, 256),
    )


def _matches(count: int) -> FeatureMatchResult:
    items = tuple(
        FeatureMatch(moving_index=index, fixed_index=index, distance=float(index + 1))
        for index in range(count)
    )
    return FeatureMatchResult(
        strategy="knn_ratio",
        tentative_matches=items,
        accepted_matches=items,
        success=True,
        runtime_seconds=0.0,
        minimum_matches=4,
    )


def _points() -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(25.0, 225.0, 5), np.linspace(25.0, 225.0, 5))
    return np.column_stack([xs.ravel(), ys.ravel()])


def test_similarity_ransac_from_matches_accepts_sift_features() -> None:
    moving_points = _points()
    transform = similarity_matrix(1.08, 12.0, tx=14.0, ty=-9.0, center=[128.0, 128.0])
    fixed_points = apply_transform(moving_points, transform)
    result = estimate_similarity_ransac_from_matches(
        _matches(len(moving_points)),
        _sift_features(fixed_points),
        _sift_features(moving_points),
        reprojection_threshold=0.5,
        minimum_matches=8,
        minimum_inliers=8,
        random_seed=42,
    )
    assert result.success
    assert result.estimated_transform is not None
    assert np.allclose(result.estimated_transform, transform, atol=1e-6)


def test_affine_ransac_from_matches_accepts_sift_features() -> None:
    moving_points = _points()
    linear = np.asarray([[1.05, 0.08], [-0.03, 0.94]], dtype=np.float64)
    transform = affine_matrix(linear, tx=12.0, ty=-7.0)
    fixed_points = apply_transform(moving_points, transform)
    result = estimate_affine_ransac_from_matches(
        _matches(len(moving_points)),
        _sift_features(fixed_points),
        _sift_features(moving_points),
        fixed_shape=(256, 256),
        moving_shape=(256, 256),
        reprojection_threshold=0.5,
        minimum_matches=8,
        minimum_inliers=8,
        minimum_spatial_coverage=0.1,
        random_seed=42,
    )
    assert result.success
    assert result.estimated_transform is not None
    assert np.allclose(result.estimated_transform, transform, atol=1e-6)
