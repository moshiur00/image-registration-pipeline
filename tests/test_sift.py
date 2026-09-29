from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.feature_matching import match_feature_knn_ratio
from image_registration.sift import (
    SIFTConfig,
    detect_sift_features,
    draw_sift_keypoints,
    sift_keypoint_response_summary,
    sift_spatial_coverage,
)


def _textured_image(height: int = 180, width: int = 220) -> np.ndarray:
    rng = np.random.default_rng(8123)
    image = rng.normal(0.5, 0.16, size=(height, width)).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 0.7)
    cv2.rectangle(image, (16, 20), (82, 88), 1.0, thickness=-1)
    cv2.circle(image, (165, 125), 24, 0.05, thickness=-1)
    cv2.line(image, (18, 150), (200, 28), 0.92, thickness=4)
    cv2.putText(image, "SIFT", (88, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.75, 0.12, 2)
    return np.clip(image, 0.0, 1.0)


def test_sift_detects_float_descriptors() -> None:
    result = detect_sift_features(_textured_image(), config=SIFTConfig(n_features=300))
    assert result.success
    assert result.keypoint_count > 0
    assert result.descriptors is not None
    assert result.descriptors.dtype == np.float32
    assert result.descriptors.ndim == 2
    assert result.descriptors.shape[0] == result.keypoint_count
    assert result.descriptors.shape[1] == 128


def test_sift_points_use_xy_order() -> None:
    image = _textured_image()
    result = detect_sift_features(image)
    assert result.success
    points = result.points_xy
    assert np.all(points[:, 0] >= 0.0)
    assert np.all(points[:, 0] < image.shape[1])
    assert np.all(points[:, 1] >= 0.0)
    assert np.all(points[:, 1] < image.shape[0])


def test_sift_respects_feature_limit() -> None:
    result = detect_sift_features(_textured_image(), config=SIFTConfig(n_features=60))
    assert result.keypoint_count <= 60


def test_sift_is_deterministic_for_same_input() -> None:
    image = _textured_image()
    config = SIFTConfig(n_features=220)
    first = detect_sift_features(image, config=config)
    second = detect_sift_features(image, config=config)
    assert first.success and second.success
    assert np.array_equal(first.points_xy, second.points_xy)
    assert first.descriptors is not None and second.descriptors is not None
    assert np.array_equal(first.descriptors, second.descriptors)


def test_sift_mask_limits_detection() -> None:
    image = _textured_image()
    mask = np.zeros(image.shape, dtype=np.uint8)
    mask[:, : image.shape[1] // 2] = 1
    result = detect_sift_features(image, mask=mask, config=SIFTConfig(n_features=250))
    assert result.success
    assert np.all(result.points_xy[:, 0] < image.shape[1] // 2 + 2)


def test_constant_image_returns_safe_failure() -> None:
    result = detect_sift_features(np.ones((128, 128), dtype=np.float32))
    assert not result.success
    assert result.descriptors is None
    assert result.failure_reason == "no_keypoints_detected"


def test_invalid_sift_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="2D grayscale"):
        detect_sift_features(np.zeros((64, 64, 3), dtype=np.uint8))
    image = _textured_image()
    image[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        detect_sift_features(image)


def test_sift_configuration_validation() -> None:
    image = _textured_image()
    with pytest.raises(ValueError, match="n_features"):
        detect_sift_features(image, config=SIFTConfig(n_features=-1))
    with pytest.raises(ValueError, match="n_octave_layers"):
        detect_sift_features(image, config=SIFTConfig(n_octave_layers=0))
    with pytest.raises(ValueError, match="sigma"):
        detect_sift_features(image, config=SIFTConfig(sigma=0.0))


def test_sift_l2_knn_ratio_matches_identical_image() -> None:
    image = _textured_image()
    fixed = detect_sift_features(image, config=SIFTConfig(n_features=250))
    moving = detect_sift_features(image.copy(), config=SIFTConfig(n_features=250))
    result = match_feature_knn_ratio(
        fixed,
        moving,
        metric="l2",
        ratio_threshold=0.75,
        minimum_matches=8,
    )
    assert result.success
    assert result.accepted_count >= 8
    assert all(match.distance == pytest.approx(0.0) for match in result.accepted_matches)


def test_l2_matching_rejects_binary_descriptors() -> None:
    from image_registration.orb import ORBConfig, detect_orb_features

    image = _textured_image()
    fixed = detect_orb_features(image, config=ORBConfig(n_features=200))
    moving = detect_orb_features(image.copy(), config=ORBConfig(n_features=200))
    with pytest.raises(ValueError, match="floating-point"):
        match_feature_knn_ratio(fixed, moving, metric="l2")


def test_hamming_matching_rejects_sift_descriptors() -> None:
    image = _textured_image()
    fixed = detect_sift_features(image, config=SIFTConfig(n_features=200))
    moving = detect_sift_features(image.copy(), config=SIFTConfig(n_features=200))
    with pytest.raises(ValueError, match="uint8"):
        match_feature_knn_ratio(fixed, moving, metric="hamming")


def test_sift_spatial_coverage_and_response_summary() -> None:
    result = detect_sift_features(_textured_image(), config=SIFTConfig(n_features=250))
    coverage = sift_spatial_coverage(result, rows=4, columns=4)
    summary = sift_keypoint_response_summary(result)
    assert 0.0 < coverage <= 1.0
    assert summary["median"] is not None


def test_draw_sift_keypoints_returns_rgb_uint8() -> None:
    image = _textured_image()
    result = detect_sift_features(image)
    rendered = draw_sift_keypoints(image, result)
    assert rendered.dtype == np.uint8
    assert rendered.shape == (image.shape[0], image.shape[1], 3)
