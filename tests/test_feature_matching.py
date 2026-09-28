from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.feature_matching import (
    correspondence_grid_coverage,
    correspondence_points,
    draw_feature_matches,
    match_distance_summary,
    match_orb_cross_check,
    match_orb_knn_ratio,
)
from image_registration.orb import ORBConfig, detect_orb_features


def _textured_image(height: int = 180, width: int = 220) -> np.ndarray:
    rng = np.random.default_rng(4321)
    image = rng.normal(0.5, 0.18, size=(height, width)).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 0.7)
    cv2.rectangle(image, (18, 24), (82, 86), 1.0, thickness=-1)
    cv2.circle(image, (160, 120), 22, 0.05, thickness=-1)
    cv2.line(image, (20, 150), (195, 30), 0.9, thickness=4)
    cv2.putText(image, "ORB", (92, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0.1, 2)
    return np.clip(image, 0.0, 1.0)


def _features(image: np.ndarray):
    return detect_orb_features(image, config=ORBConfig(n_features=400))


def test_knn_ratio_matches_identical_image() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_knn_ratio(fixed, moving, ratio_threshold=0.75, minimum_matches=8)
    assert result.success
    assert result.accepted_count >= 8
    assert result.tentative_count >= result.accepted_count
    assert result.failure_reason is None
    assert result.acceptance_rate is not None
    assert 0.0 <= result.acceptance_rate <= 1.0
    assert all(match.distance == pytest.approx(0.0) for match in result.accepted_matches)


def test_cross_check_matches_identical_image() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_cross_check(fixed, moving, minimum_matches=8)
    assert result.success
    assert result.accepted_count >= 8
    assert all(match.distance == pytest.approx(0.0) for match in result.accepted_matches)


def test_ratio_threshold_controls_accepted_match_count() -> None:
    fixed_image = _textured_image()
    matrix = cv2.getRotationMatrix2D((110.0, 90.0), 12.0, 1.0)
    moving_image = cv2.warpAffine(fixed_image, matrix, (220, 180))
    fixed = _features(fixed_image)
    moving = _features(moving_image)
    strict = match_orb_knn_ratio(fixed, moving, ratio_threshold=0.60, minimum_matches=1)
    loose = match_orb_knn_ratio(fixed, moving, ratio_threshold=0.90, minimum_matches=1)
    assert loose.accepted_count >= strict.accepted_count


def test_maximum_distance_filters_matches() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    unrestricted = match_orb_cross_check(fixed, moving, minimum_matches=1)
    restricted = match_orb_cross_check(
        fixed, moving, maximum_distance=0.0, minimum_matches=1
    )
    assert unrestricted.accepted_count == restricted.accepted_count


def test_missing_features_return_safe_failure() -> None:
    blank = np.ones((128, 128), dtype=np.float32)
    textured = _textured_image(128, 128)
    fixed = _features(textured)
    moving = _features(blank)
    result = match_orb_knn_ratio(fixed, moving)
    assert result.success is False
    assert result.accepted_count == 0
    assert result.failure_reason == "moving_descriptors_unavailable"


def test_invalid_ratio_threshold_is_rejected() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image)
    with pytest.raises(ValueError, match="ratio_threshold"):
        match_orb_knn_ratio(fixed, moving, ratio_threshold=1.0)


def test_invalid_minimum_matches_is_rejected() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image)
    with pytest.raises(ValueError, match="minimum_matches"):
        match_orb_cross_check(fixed, moving, minimum_matches=0)


def test_correspondence_points_follow_fixed_and_moving_indexing() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_cross_check(fixed, moving, minimum_matches=1)
    fixed_points, moving_points = correspondence_points(result, fixed, moving)
    assert fixed_points.shape == moving_points.shape
    assert fixed_points.shape[1] == 2
    assert np.allclose(fixed_points, moving_points)


def test_correspondence_coverage_is_bounded() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_cross_check(fixed, moving, minimum_matches=1)
    coverage = correspondence_grid_coverage(result, fixed, moving, rows=4, columns=4)
    assert 0.0 <= coverage.fixed_coverage <= 1.0
    assert 0.0 <= coverage.moving_coverage <= 1.0
    assert coverage.minimum_coverage == pytest.approx(
        min(coverage.fixed_coverage, coverage.moving_coverage)
    )


def test_distance_summary_empty_is_explicit() -> None:
    summary = match_distance_summary(())
    assert summary == {
        "mean": None,
        "median": None,
        "minimum": None,
        "maximum": None,
        "q25": None,
        "q75": None,
    }


def test_distance_summary_for_identity_is_zero() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_cross_check(fixed, moving, minimum_matches=1)
    summary = match_distance_summary(result.accepted_matches)
    assert summary["median"] == pytest.approx(0.0)
    assert summary["maximum"] == pytest.approx(0.0)


def test_draw_feature_matches_returns_rgb_uint8() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    result = match_orb_cross_check(fixed, moving, minimum_matches=1)
    rendered = draw_feature_matches(
        image,
        image,
        fixed,
        moving,
        result.accepted_matches,
        maximum_drawn=30,
    )
    assert rendered.dtype == np.uint8
    assert rendered.ndim == 3
    assert rendered.shape[2] == 3
    assert rendered.shape[0] == image.shape[0]
    assert rendered.shape[1] == image.shape[1] * 2


def test_matching_is_deterministic_for_same_inputs() -> None:
    image = _textured_image()
    fixed = _features(image)
    moving = _features(image.copy())
    first = match_orb_knn_ratio(fixed, moving, ratio_threshold=0.75, minimum_matches=1)
    second = match_orb_knn_ratio(fixed, moving, ratio_threshold=0.75, minimum_matches=1)
    assert first.tentative_matches == second.tentative_matches
    assert first.accepted_matches == second.accepted_matches
