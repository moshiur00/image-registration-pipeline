"""Texture diagnostics for feature-based registration experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import ArrayLike

from .orb import ORBFeatureResult

TextureLabel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class TextureDiagnostics:
    """Compact texture measurements used to stratify feature experiments."""

    gradient_energy: float
    keypoint_density_per_megapixel: float
    label: TextureLabel


def _normalized_grayscale(image: ArrayLike) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 3:
        if array.shape[2] == 3:
            array = cv2.cvtColor(array.astype(np.float32), cv2.COLOR_RGB2GRAY)
        elif array.shape[2] == 4:
            array = cv2.cvtColor(array.astype(np.float32), cv2.COLOR_RGBA2GRAY)
        else:
            raise ValueError("Color images must have 3 or 4 channels.")
    if array.ndim != 2 or array.size == 0:
        raise ValueError("image must be a non-empty 2D grayscale image or RGB/RGBA image.")
    values = array.astype(np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("image must contain only finite values.")
    low = float(np.min(values))
    high = float(np.max(values))
    if np.isclose(low, high):
        return np.zeros_like(values, dtype=np.float64)
    return (values - low) / (high - low)


def gradient_energy(image: ArrayLike) -> float:
    """Return mean squared Sobel-gradient magnitude on a normalized image."""
    normalized = _normalized_grayscale(image)
    dx = cv2.Sobel(normalized, cv2.CV_64F, 1, 0, ksize=3, borderType=cv2.BORDER_REFLECT101)
    dy = cv2.Sobel(normalized, cv2.CV_64F, 0, 1, ksize=3, borderType=cv2.BORDER_REFLECT101)
    return float(np.mean(dx * dx + dy * dy, dtype=np.float64))


def keypoint_density_per_megapixel(
    features: ORBFeatureResult,
    image_shape: tuple[int, ...],
) -> float:
    """Return detected keypoints per megapixel of image area."""
    if len(image_shape) < 2:
        raise ValueError("image_shape must include height and width.")
    height, width = int(image_shape[0]), int(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive.")
    megapixels = (height * width) / 1_000_000.0
    return float(features.keypoint_count / megapixels)


def classify_texture(
    energy: float,
    *,
    low_threshold: float,
    high_threshold: float,
) -> TextureLabel:
    """Classify normalized gradient energy using explicit experiment thresholds."""
    if not np.isfinite(energy) or energy < 0.0:
        raise ValueError("energy must be finite and non-negative.")
    if not np.isfinite(low_threshold) or low_threshold < 0.0:
        raise ValueError("low_threshold must be finite and non-negative.")
    if not np.isfinite(high_threshold) or high_threshold <= low_threshold:
        raise ValueError("high_threshold must be finite and greater than low_threshold.")
    if energy < low_threshold:
        return "low"
    if energy < high_threshold:
        return "medium"
    return "high"


def texture_diagnostics(
    image: ArrayLike,
    features: ORBFeatureResult,
    *,
    low_threshold: float,
    high_threshold: float,
) -> TextureDiagnostics:
    """Measure gradient energy, keypoint density, and configured texture label."""
    energy = gradient_energy(image)
    return TextureDiagnostics(
        gradient_energy=energy,
        keypoint_density_per_megapixel=keypoint_density_per_megapixel(features, np.asarray(image).shape),
        label=classify_texture(
            energy,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
        ),
    )
