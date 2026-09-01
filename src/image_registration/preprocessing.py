"""Baseline preprocessing utilities for 2D registration experiments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatImage = NDArray[np.float32]


def _as_array(image: ArrayLike) -> NDArray[np.generic]:
    array = np.asarray(image)
    if array.ndim not in {2, 3}:
        raise ValueError("Expected a 2D image or a 2D image with channels.")
    if array.size == 0:
        raise ValueError("Image must be non-empty.")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("Image must contain numeric values.")
    return array


def to_grayscale(image: ArrayLike) -> NDArray[np.generic]:
    """Convert an RGB or RGBA image to grayscale, or copy an existing 2D image."""
    array = _as_array(image)
    if array.ndim == 2:
        return array.copy()
    if array.shape[2] == 3:
        return cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    if array.shape[2] == 4:
        return cv2.cvtColor(array, cv2.COLOR_RGBA2GRAY)
    raise ValueError("Color images must have 3 RGB channels or 4 RGBA channels.")


def _selected_values(array: NDArray[np.generic], mask: ArrayLike | None) -> NDArray[np.generic]:
    if mask is None:
        return array.reshape(-1)
    mask_array = np.asarray(mask, dtype=bool)
    if mask_array.shape != array.shape:
        raise ValueError("Mask shape must match the image shape.")
    values = array[mask_array]
    if values.size == 0:
        raise ValueError("Mask does not select any pixels.")
    return values


def clip_percentiles(
    image: ArrayLike,
    lower: float = 1.0,
    upper: float = 99.0,
    *,
    mask: ArrayLike | None = None,
) -> FloatImage:
    """Clip image intensities to robust percentile bounds."""
    array = _as_array(image)
    if array.ndim != 2:
        raise ValueError("Percentile clipping expects a 2D grayscale image.")
    if not (0.0 <= lower < upper <= 100.0):
        raise ValueError("Percentiles must satisfy 0 <= lower < upper <= 100.")

    values = _selected_values(array, mask).astype(np.float64)
    lo, hi = np.percentile(values, [lower, upper])
    return np.clip(array.astype(np.float32), float(lo), float(hi)).astype(np.float32)


def robust_normalize(
    image: ArrayLike,
    lower: float = 1.0,
    upper: float = 99.0,
    *,
    mask: ArrayLike | None = None,
) -> FloatImage:
    """Percentile-clip a grayscale image and scale intensities to [0, 1]."""
    clipped = clip_percentiles(image, lower=lower, upper=upper, mask=mask)
    values = _selected_values(clipped, mask).astype(np.float64)
    lo = float(np.min(values))
    hi = float(np.max(values))
    if np.isclose(hi, lo):
        return np.zeros_like(clipped, dtype=np.float32)
    normalized = (clipped - lo) / (hi - lo)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def gaussian_smooth(image: ArrayLike, sigma: float) -> NDArray[np.generic]:
    """Apply Gaussian smoothing without changing image dimensions."""
    array = _as_array(image)
    if sigma < 0 or not np.isfinite(sigma):
        raise ValueError("Gaussian sigma must be finite and non-negative.")
    if sigma == 0:
        return array.copy()
    return cv2.GaussianBlur(array, ksize=(0, 0), sigmaX=float(sigma), sigmaY=float(sigma))


def resize_image(
    image: ArrayLike,
    output_shape: tuple[int, int],
    *,
    interpolation: str = "linear",
) -> NDArray[np.generic]:
    """Resize an image to ``(height, width)``."""
    array = _as_array(image)
    if len(output_shape) != 2 or output_shape[0] <= 0 or output_shape[1] <= 0:
        raise ValueError("output_shape must contain positive (height, width).")

    flags = {
        "nearest": cv2.INTER_NEAREST,
        "linear": cv2.INTER_LINEAR,
        "cubic": cv2.INTER_CUBIC,
        "area": cv2.INTER_AREA,
    }
    if interpolation not in flags:
        raise ValueError("Unsupported resize interpolation.")

    height, width = int(output_shape[0]), int(output_shape[1])
    return cv2.resize(array, dsize=(width, height), interpolation=flags[interpolation])


def crop_to_mask(
    image: ArrayLike,
    mask: ArrayLike,
    *,
    margin: int = 0,
) -> tuple[NDArray[np.generic], NDArray[np.generic], tuple[int, int, int, int]]:
    """Crop an image and mask to the non-zero mask bounding box.

    Returns ``(cropped_image, cropped_mask, (x0, y0, x1, y1))`` where ``x1``
    and ``y1`` are exclusive bounds.
    """
    array = _as_array(image)
    mask_array = np.asarray(mask)
    if mask_array.ndim != 2:
        raise ValueError("Mask must be 2D.")
    if array.shape[:2] != mask_array.shape:
        raise ValueError("Mask height and width must match the image.")
    if margin < 0:
        raise ValueError("margin must be non-negative.")

    ys, xs = np.nonzero(mask_array)
    if xs.size == 0:
        raise ValueError("Mask contains no non-zero pixels.")

    height, width = mask_array.shape
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(width, int(xs.max()) + 1 + margin)
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(height, int(ys.max()) + 1 + margin)
    return array[y0:y1, x0:x1].copy(), mask_array[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)


def preprocess_image(
    image: ArrayLike,
    config: Mapping[str, Any],
) -> tuple[FloatImage, dict[str, Any]]:
    """Apply the configured baseline preprocessing sequence."""
    result = _as_array(image)
    report: dict[str, Any] = {
        "input_shape": list(result.shape),
        "input_dtype": str(result.dtype),
    }

    if bool(config.get("grayscale", True)):
        result = to_grayscale(result)
        report["grayscale"] = True
    else:
        if result.ndim != 2:
            raise ValueError("Configured preprocessing output must be grayscale for evaluation.")
        report["grayscale"] = False

    lower = float(config.get("clip_lower_percentile", 1.0))
    upper = float(config.get("clip_upper_percentile", 99.0))
    if bool(config.get("normalize", True)):
        result = robust_normalize(result, lower=lower, upper=upper)
        report["normalization"] = "robust_percentile_to_0_1"
    else:
        result = clip_percentiles(result, lower=lower, upper=upper)
        report["normalization"] = "percentile_clip_only"

    sigma = float(config.get("gaussian_sigma", 0.0))
    result = gaussian_smooth(result, sigma=sigma).astype(np.float32)
    report["gaussian_sigma"] = sigma

    resize_cfg = config.get("resize")
    if resize_cfg:
        output_shape = (int(resize_cfg["height"]), int(resize_cfg["width"]))
        interpolation = str(resize_cfg.get("interpolation", "linear"))
        result = resize_image(result, output_shape, interpolation=interpolation).astype(np.float32)
        report["resize"] = {
            "height": output_shape[0],
            "width": output_shape[1],
            "interpolation": interpolation,
        }
    else:
        report["resize"] = None

    report["output_shape"] = list(result.shape)
    report["output_dtype"] = str(result.dtype)
    report["output_min"] = float(np.min(result))
    report["output_max"] = float(np.max(result))
    return result, report
