from __future__ import annotations

import numpy as np
import pytest

from image_registration.preprocessing import (
    crop_to_mask,
    gaussian_smooth,
    preprocess_image,
    resize_image,
    robust_normalize,
    to_grayscale,
)


def test_to_grayscale_accepts_rgb() -> None:
    rgb = np.zeros((4, 5, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255
    gray = to_grayscale(rgb)
    assert gray.shape == (4, 5)
    assert gray.dtype == np.uint8
    assert np.all(gray > 0)


def test_robust_normalize_returns_zero_to_one() -> None:
    image = np.linspace(0, 1000, 100, dtype=np.float32).reshape(10, 10)
    normalized = robust_normalize(image, lower=5.0, upper=95.0)
    assert normalized.dtype == np.float32
    assert float(normalized.min()) == pytest.approx(0.0)
    assert float(normalized.max()) == pytest.approx(1.0)


def test_robust_normalize_constant_image_returns_zero() -> None:
    image = np.full((8, 8), 12.0, dtype=np.float32)
    normalized = robust_normalize(image)
    assert np.array_equal(normalized, np.zeros_like(image))


def test_gaussian_smooth_preserves_shape() -> None:
    image = np.zeros((15, 17), dtype=np.float32)
    image[7, 8] = 1.0
    smoothed = gaussian_smooth(image, sigma=1.2)
    assert smoothed.shape == image.shape
    assert 0.0 < smoothed[7, 8] < 1.0


def test_resize_image_uses_height_width_order() -> None:
    image = np.zeros((10, 20), dtype=np.uint8)
    resized = resize_image(image, (6, 9), interpolation="nearest")
    assert resized.shape == (6, 9)


def test_crop_to_mask_returns_expected_bbox() -> None:
    image = np.arange(100, dtype=np.uint8).reshape(10, 10)
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[3:7, 2:8] = 1
    cropped_image, cropped_mask, bbox = crop_to_mask(image, mask, margin=1)
    assert bbox == (1, 2, 9, 8)
    assert cropped_image.shape == (6, 8)
    assert cropped_mask.shape == (6, 8)


def test_preprocess_image_reports_output() -> None:
    image = np.arange(256, dtype=np.uint8).reshape(16, 16)
    config = {
        "grayscale": True,
        "clip_lower_percentile": 1.0,
        "clip_upper_percentile": 99.0,
        "normalize": True,
        "gaussian_sigma": 0.5,
        "resize": {"height": 8, "width": 10, "interpolation": "linear"},
    }
    processed, report = preprocess_image(image, config)
    assert processed.shape == (8, 10)
    assert processed.dtype == np.float32
    assert report["output_shape"] == [8, 10]
    assert report["resize"]["height"] == 8
