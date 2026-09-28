from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.orb import (
    ORBConfig,
    detect_orb_features,
    draw_orb_keypoints,
    keypoint_grid_coverage,
    keypoint_response_summary,
)


def _textured_image(height: int = 160, width: int = 192) -> np.ndarray:
    rng = np.random.default_rng(1234)
    image = rng.normal(0.5, 0.18, size=(height, width)).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 0.8)
    cv2.rectangle(image, (20, 22), (72, 76), 1.0, thickness=-1)
    cv2.circle(image, (135, 105), 18, 0.05, thickness=-1)
    cv2.line(image, (15, 135), (170, 25), 0.9, thickness=3)
    return np.clip(image, 0.0, 1.0)


def test_orb_detects_keypoints_and_binary_descriptors() -> None:
    result = detect_orb_features(_textured_image(), config=ORBConfig(n_features=300))
    assert result.success
    assert result.keypoint_count > 0
    assert result.descriptors is not None
    assert result.descriptors.dtype == np.uint8
    assert result.descriptors.ndim == 2
    assert result.descriptors.shape[0] == result.keypoint_count
    assert result.descriptors.shape[1] == 32


def test_orb_keypoints_use_xy_coordinate_order() -> None:
    image = _textured_image()
    result = detect_orb_features(image)
    assert result.success
    points = result.points_xy
    assert points.ndim == 2
    assert points.shape[1] == 2
    assert np.all(points[:, 0] >= 0.0)
    assert np.all(points[:, 0] < image.shape[1])
    assert np.all(points[:, 1] >= 0.0)
    assert np.all(points[:, 1] < image.shape[0])


def test_orb_respects_requested_feature_limit() -> None:
    result = detect_orb_features(_textured_image(), config=ORBConfig(n_features=80))
    assert result.keypoint_count <= 80


def test_orb_is_deterministic_for_same_image_and_configuration() -> None:
    image = _textured_image()
    config = ORBConfig(n_features=250)
    first = detect_orb_features(image, config=config)
    second = detect_orb_features(image, config=config)
    assert first.success and second.success
    assert np.array_equal(first.points_xy, second.points_xy)
    assert first.descriptors is not None and second.descriptors is not None
    assert np.array_equal(first.descriptors, second.descriptors)


def test_orb_accepts_float_image_and_returns_valid_runtime() -> None:
    result = detect_orb_features(_textured_image().astype(np.float64))
    assert result.success
    assert result.runtime_seconds >= 0.0


def test_orb_mask_limits_detected_coordinates() -> None:
    image = _textured_image()
    mask = np.zeros(image.shape, dtype=np.uint8)
    mask[:, : image.shape[1] // 2] = 1
    result = detect_orb_features(image, mask=mask, config=ORBConfig(n_features=300))
    assert result.success
    assert np.all(result.points_xy[:, 0] < image.shape[1] // 2 + 1)


def test_constant_image_returns_safe_no_keypoints_failure() -> None:
    image = np.ones((128, 128), dtype=np.float32)
    result = detect_orb_features(image)
    assert result.success is False
    assert result.keypoint_count == 0
    assert result.descriptors is None
    assert result.failure_reason == "no_keypoints_detected"


def test_invalid_image_dimensionality_is_rejected() -> None:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="2D grayscale"):
        detect_orb_features(image)


def test_nonfinite_image_is_rejected() -> None:
    image = _textured_image()
    image[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        detect_orb_features(image)


def test_invalid_mask_shape_is_rejected() -> None:
    image = _textured_image()
    mask = np.ones((32, 32), dtype=np.uint8)
    with pytest.raises(ValueError, match="same shape"):
        detect_orb_features(image, mask=mask)


def test_orb_configuration_validation() -> None:
    with pytest.raises(ValueError, match="n_features"):
        detect_orb_features(_textured_image(), config=ORBConfig(n_features=0))
    with pytest.raises(ValueError, match="scale_factor"):
        detect_orb_features(_textured_image(), config=ORBConfig(scale_factor=1.0))
    with pytest.raises(ValueError, match="wta_k"):
        detect_orb_features(_textured_image(), config=ORBConfig(wta_k=5))


def test_keypoint_grid_coverage_has_expected_fraction() -> None:
    points = np.array(
        [
            [10.0, 10.0],
            [60.0, 10.0],
            [10.0, 60.0],
            [60.0, 60.0],
        ]
    )
    coverage = keypoint_grid_coverage(points, (100, 100), rows=2, columns=2)
    assert coverage == pytest.approx(1.0)


def test_empty_keypoint_grid_coverage_is_zero() -> None:
    coverage = keypoint_grid_coverage(np.empty((0, 2)), (100, 100))
    assert coverage == 0.0


def test_response_summary_reports_none_for_empty_result() -> None:
    result = detect_orb_features(np.ones((64, 64), dtype=np.float32))
    summary = keypoint_response_summary(result)
    assert summary == {
        "mean": None,
        "median": None,
        "minimum": None,
        "maximum": None,
    }


def test_draw_orb_keypoints_returns_rgb_uint8() -> None:
    image = _textured_image()
    result = detect_orb_features(image)
    rendered = draw_orb_keypoints(image, result)
    assert rendered.dtype == np.uint8
    assert rendered.shape == (image.shape[0], image.shape[1], 3)
