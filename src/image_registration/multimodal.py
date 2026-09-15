"""Synthetic multimodal appearance mappings for controlled benchmark pairs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

NumericArray = NDArray[np.generic]


@dataclass(frozen=True)
class MultimodalResult:
    """Result of one synthetic modality mapping."""

    image: NumericArray
    metadata: dict[str, Any]


def _validate_grayscale(image: ArrayLike) -> NumericArray:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("Synthetic multimodal mappings require a 2D grayscale image.")
    if array.size == 0:
        raise ValueError("Image must be non-empty.")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("Image must contain numeric values.")
    if not np.all(np.isfinite(array.astype(np.float64))):
        raise ValueError("Image must contain only finite values.")
    return array


def _observed_bounds(array: NumericArray) -> tuple[float, float]:
    values = array.astype(np.float64)
    return float(np.min(values)), float(np.max(values))


def _normalize_observed(array: NumericArray) -> tuple[NDArray[np.float64], float, float]:
    low, high = _observed_bounds(array)
    if np.isclose(high, low):
        return np.zeros(array.shape, dtype=np.float64), low, high
    normalized = (array.astype(np.float64) - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0), low, high


def _restore_dtype(
    normalized: ArrayLike,
    reference: NumericArray,
    low: float,
    high: float,
) -> NumericArray:
    values = np.asarray(normalized, dtype=np.float64)
    if np.isclose(high, low):
        restored = np.full(values.shape, low, dtype=np.float64)
    else:
        restored = low + np.clip(values, 0.0, 1.0) * (high - low)

    if np.issubdtype(reference.dtype, np.integer):
        info = np.iinfo(reference.dtype)
        restored = np.rint(np.clip(restored, info.min, info.max))
    return restored.astype(reference.dtype)


def intensity_inversion(image: ArrayLike) -> NumericArray:
    """Invert intensities within the observed image range."""
    array = _validate_grayscale(image)
    low, high = _observed_bounds(array)
    inverted = low + high - array.astype(np.float64)
    if np.issubdtype(array.dtype, np.integer):
        inverted = np.rint(inverted)
    return inverted.astype(array.dtype)


def nonlinear_gamma_mapping(image: ArrayLike, *, gamma: float) -> NumericArray:
    """Apply a nonlinear gamma mapping while preserving shape and dtype."""
    array = _validate_grayscale(image)
    if gamma <= 0.0 or not np.isfinite(gamma):
        raise ValueError("gamma must be a finite value greater than zero.")
    normalized, low, high = _normalize_observed(array)
    mapped = np.power(normalized, gamma)
    return _restore_dtype(mapped, array, low, high)


def histogram_remap(
    image: ArrayLike,
    *,
    input_knots: Sequence[float],
    output_knots: Sequence[float],
) -> NumericArray:
    """Apply a monotonic piecewise-linear intensity remapping in normalized space."""
    array = _validate_grayscale(image)
    x = np.asarray(input_knots, dtype=np.float64)
    y = np.asarray(output_knots, dtype=np.float64)
    if x.ndim != 1 or y.ndim != 1 or x.size < 2 or x.size != y.size:
        raise ValueError("input_knots and output_knots must be equal-length 1D sequences with at least 2 values.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Histogram remap knots must contain finite values.")
    if not np.all(np.diff(x) > 0.0):
        raise ValueError("input_knots must be strictly increasing.")
    if x[0] != 0.0 or x[-1] != 1.0:
        raise ValueError("input_knots must begin at 0 and end at 1.")
    if np.any(y < 0.0) or np.any(y > 1.0):
        raise ValueError("output_knots must stay within [0, 1].")
    if not np.all(np.diff(y) >= 0.0):
        raise ValueError("output_knots must be monotonic non-decreasing.")

    normalized, low, high = _normalize_observed(array)
    mapped = np.interp(normalized, x, y)
    return _restore_dtype(mapped, array, low, high)


def multiplicative_bias_field(
    image: ArrayLike,
    *,
    strength_fraction: float,
    center_x_fraction: float = 0.5,
    center_y_fraction: float = 0.5,
    sigma_fraction: float = 0.35,
) -> NumericArray:
    """Apply a smooth local multiplicative intensity bias field."""
    array = _validate_grayscale(image)
    if not 0.0 <= strength_fraction <= 1.0:
        raise ValueError("strength_fraction must be between 0 and 1.")
    if not 0.0 <= center_x_fraction <= 1.0 or not 0.0 <= center_y_fraction <= 1.0:
        raise ValueError("Bias-field center fractions must be between 0 and 1.")
    if not 0.0 < sigma_fraction <= 1.0:
        raise ValueError("sigma_fraction must be in the range (0, 1].")

    values = array.astype(np.float64)
    height, width = array.shape
    yy, xx = np.indices((height, width), dtype=np.float64)
    center_x = center_x_fraction * max(width - 1, 1)
    center_y = center_y_fraction * max(height - 1, 1)
    sigma = sigma_fraction * max(height, width)
    distance_squared = (xx - center_x) ** 2 + (yy - center_y) ** 2
    gaussian = np.exp(-distance_squared / (2.0 * sigma * sigma))

    field = 1.0 - strength_fraction + 2.0 * strength_fraction * gaussian
    mapped = values * field
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        mapped = np.rint(np.clip(mapped, info.min, info.max))
    return mapped.astype(array.dtype)


def edge_emphasized_representation(image: ArrayLike, *, blend: float = 1.0) -> NumericArray:
    """Create an edge-emphasized representation using Sobel gradient magnitude."""
    array = _validate_grayscale(image)
    if not 0.0 <= blend <= 1.0:
        raise ValueError("blend must be between 0 and 1.")

    normalized, low, high = _normalize_observed(array)
    sobel_x = cv2.Sobel(normalized, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(normalized, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.hypot(sobel_x, sobel_y)
    maximum = float(np.max(magnitude))
    if maximum > 0.0:
        magnitude = magnitude / maximum
    emphasized = np.clip((1.0 - blend) * normalized + blend * magnitude, 0.0, 1.0)
    return _restore_dtype(emphasized, array, low, high)


def modality_specific_noise(
    image: ArrayLike,
    *,
    base_sigma_fraction: float,
    signal_sigma_fraction: float,
    rng: np.random.Generator,
) -> NumericArray:
    """Add deterministic signal-dependent Gaussian noise in normalized intensity space."""
    array = _validate_grayscale(image)
    if base_sigma_fraction < 0.0 or signal_sigma_fraction < 0.0:
        raise ValueError("Noise fractions must be non-negative.")
    if not np.isfinite(base_sigma_fraction) or not np.isfinite(signal_sigma_fraction):
        raise ValueError("Noise fractions must be finite.")

    normalized, low, high = _normalize_observed(array)
    sigma = base_sigma_fraction + signal_sigma_fraction * normalized
    noisy = normalized + rng.normal(0.0, 1.0, size=array.shape) * sigma
    return _restore_dtype(np.clip(noisy, 0.0, 1.0), array, low, high)


def apply_multimodal_mapping(
    image: ArrayLike,
    specification: Mapping[str, Any],
    *,
    rng: np.random.Generator,
) -> MultimodalResult:
    """Apply one configuration-defined synthetic modality mapping."""
    if not isinstance(specification, Mapping):
        raise ValueError("Multimodal mapping specification must be a mapping.")

    array = _validate_grayscale(image)
    name = str(specification.get("type", "")).strip().lower()

    if name == "intensity_inversion":
        mapped = intensity_inversion(array)
        metadata: dict[str, Any] = {"type": name}

    elif name == "nonlinear_gamma":
        gamma = float(specification.get("gamma", 1.6))
        mapped = nonlinear_gamma_mapping(array, gamma=gamma)
        metadata = {"type": name, "gamma": gamma}

    elif name == "histogram_remap":
        input_knots = specification.get("input_knots", [0.0, 0.25, 0.5, 0.75, 1.0])
        output_knots = specification.get("output_knots", [0.0, 0.10, 0.65, 0.88, 1.0])
        mapped = histogram_remap(
            array,
            input_knots=input_knots,
            output_knots=output_knots,
        )
        metadata = {
            "type": name,
            "input_knots": [float(value) for value in input_knots],
            "output_knots": [float(value) for value in output_knots],
        }

    elif name == "bias_field":
        strength_fraction = float(specification.get("strength_fraction", 0.25))
        center_x_fraction = float(specification.get("center_x_fraction", 0.55))
        center_y_fraction = float(specification.get("center_y_fraction", 0.45))
        sigma_fraction = float(specification.get("sigma_fraction", 0.35))
        mapped = multiplicative_bias_field(
            array,
            strength_fraction=strength_fraction,
            center_x_fraction=center_x_fraction,
            center_y_fraction=center_y_fraction,
            sigma_fraction=sigma_fraction,
        )
        metadata = {
            "type": name,
            "strength_fraction": strength_fraction,
            "center_x_fraction": center_x_fraction,
            "center_y_fraction": center_y_fraction,
            "sigma_fraction": sigma_fraction,
        }

    elif name == "edge_emphasized":
        blend = float(specification.get("blend", 0.8))
        mapped = edge_emphasized_representation(array, blend=blend)
        metadata = {"type": name, "blend": blend}

    else:
        raise ValueError(
            "Unsupported multimodal mapping type. Use intensity_inversion, nonlinear_gamma, "
            "histogram_remap, bias_field, or edge_emphasized."
        )

    base_sigma = float(specification.get("noise_base_sigma_fraction", 0.0))
    signal_sigma = float(specification.get("noise_signal_sigma_fraction", 0.0))
    if base_sigma > 0.0 or signal_sigma > 0.0:
        mapped = modality_specific_noise(
            mapped,
            base_sigma_fraction=base_sigma,
            signal_sigma_fraction=signal_sigma,
            rng=rng,
        )
        metadata["modality_specific_noise"] = {
            "base_sigma_fraction": base_sigma,
            "signal_sigma_fraction": signal_sigma,
        }

    return MultimodalResult(image=mapped, metadata=metadata)
