"""Controlled appearance degradations for synthetic registration benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

NumericArray = NDArray[np.generic]


@dataclass(frozen=True)
class DegradationResult:
    """Image after one controlled degradation plus reproducibility metadata."""

    image: NumericArray
    metadata: dict[str, Any]
    visibility_mask: NDArray[np.uint8]


def _validate_image(image: ArrayLike) -> NumericArray:
    array = np.asarray(image)
    if array.ndim not in (2, 3):
        raise ValueError("Image must have shape (H, W) or (H, W, C).")
    if array.shape[0] <= 0 or array.shape[1] <= 0:
        raise ValueError("Image dimensions must be positive.")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("Image dtype must be numeric.")
    if not np.all(np.isfinite(array)):
        raise ValueError("Image must contain finite values.")
    return array


def _intensity_bounds(array: NumericArray) -> tuple[float, float]:
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return float(info.min), float(info.max)

    lo = float(np.min(array))
    hi = float(np.max(array))
    if 0.0 <= lo and hi <= 1.0:
        return 0.0, 1.0
    if np.isclose(lo, hi):
        return lo, lo + 1.0
    return lo, hi


def _restore_dtype(values: NDArray[np.float64], reference: NumericArray) -> NumericArray:
    low, high = _intensity_bounds(reference)
    clipped = np.clip(values, low, high)
    if np.issubdtype(reference.dtype, np.integer):
        clipped = np.rint(clipped)
    return clipped.astype(reference.dtype)


def _full_visibility_mask(array: NumericArray) -> NDArray[np.uint8]:
    return np.ones(array.shape[:2], dtype=np.uint8)


def gaussian_noise(
    image: ArrayLike,
    *,
    sigma_fraction: float,
    rng: np.random.Generator,
) -> NumericArray:
    """Add zero-mean Gaussian noise scaled to the image intensity range."""
    array = _validate_image(image)
    if sigma_fraction < 0.0 or not np.isfinite(sigma_fraction):
        raise ValueError("sigma_fraction must be a finite non-negative value.")
    if sigma_fraction == 0.0:
        return array.copy()

    low, high = _intensity_bounds(array)
    sigma = sigma_fraction * (high - low)
    noise = rng.normal(0.0, sigma, size=array.shape)
    return _restore_dtype(array.astype(np.float64) + noise, array)


def impulse_noise(
    image: ArrayLike,
    *,
    probability: float,
    rng: np.random.Generator,
    salt_fraction: float = 0.5,
) -> NumericArray:
    """Apply salt-and-pepper impulse noise with a controlled pixel probability."""
    array = _validate_image(image)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1.")
    if not 0.0 <= salt_fraction <= 1.0:
        raise ValueError("salt_fraction must be between 0 and 1.")
    if probability == 0.0:
        return array.copy()

    low, high = _intensity_bounds(array)
    pixel_random = rng.random(array.shape[:2])
    corrupted = pixel_random < probability
    salt_selector = rng.random(array.shape[:2]) < salt_fraction
    result = array.copy()

    if array.ndim == 2:
        result[corrupted & salt_selector] = high
        result[corrupted & ~salt_selector] = low
    else:
        result[corrupted & salt_selector, :] = high
        result[corrupted & ~salt_selector, :] = low
    return result


def gaussian_blur(image: ArrayLike, *, sigma: float) -> NumericArray:
    """Apply Gaussian smoothing with an automatically selected kernel size."""
    array = _validate_image(image)
    if sigma < 0.0 or not np.isfinite(sigma):
        raise ValueError("sigma must be a finite non-negative value.")
    if sigma == 0.0:
        return array.copy()

    radius = max(1, int(np.ceil(3.0 * sigma)))
    kernel_size = 2 * radius + 1
    return cv2.GaussianBlur(
        array,
        (kernel_size, kernel_size),
        sigmaX=float(sigma),
        sigmaY=float(sigma),
        borderType=cv2.BORDER_REFLECT101,
    )


def adjust_contrast(image: ArrayLike, *, factor: float) -> NumericArray:
    """Scale contrast around the image mean while preserving the input dtype."""
    array = _validate_image(image)
    if factor < 0.0 or not np.isfinite(factor):
        raise ValueError("factor must be a finite non-negative value.")
    values = array.astype(np.float64)
    pivot = float(np.mean(values))
    adjusted = pivot + factor * (values - pivot)
    return _restore_dtype(adjusted, array)


def adjust_gamma(image: ArrayLike, *, gamma: float) -> NumericArray:
    """Apply a gamma intensity mapping in the supported intensity range."""
    array = _validate_image(image)
    if gamma <= 0.0 or not np.isfinite(gamma):
        raise ValueError("gamma must be a finite value greater than zero.")
    low, high = _intensity_bounds(array)
    scale = high - low
    if scale <= 0.0:
        return array.copy()
    normalized = np.clip((array.astype(np.float64) - low) / scale, 0.0, 1.0)
    adjusted = low + np.power(normalized, gamma) * scale
    return _restore_dtype(adjusted, array)


def illumination_gradient(
    image: ArrayLike,
    *,
    strength_fraction: float,
    direction: str = "horizontal",
) -> NumericArray:
    """Add a smooth centered illumination gradient without changing geometry."""
    array = _validate_image(image)
    if strength_fraction < 0.0 or not np.isfinite(strength_fraction):
        raise ValueError("strength_fraction must be a finite non-negative value.")

    height, width = array.shape[:2]
    x = np.linspace(-1.0, 1.0, width, dtype=np.float64)
    y = np.linspace(-1.0, 1.0, height, dtype=np.float64)
    xx, yy = np.meshgrid(x, y)

    name = direction.strip().lower()
    if name == "horizontal":
        field = xx
    elif name == "vertical":
        field = yy
    elif name == "diagonal":
        field = (xx + yy) / 2.0
    else:
        raise ValueError("direction must be horizontal, vertical, or diagonal.")

    low, high = _intensity_bounds(array)
    amplitude = strength_fraction * (high - low)
    offset = field * amplitude
    if array.ndim == 3:
        offset = offset[..., np.newaxis]
    return _restore_dtype(array.astype(np.float64) + offset, array)


def rectangular_occlusion(
    image: ArrayLike,
    *,
    area_fraction: float,
    rng: np.random.Generator,
    fill_value: float = 0.0,
) -> tuple[NumericArray, NDArray[np.uint8], dict[str, int]]:
    """Insert one random rectangular occlusion and return its visibility mask."""
    array = _validate_image(image)
    if not 0.0 < area_fraction < 1.0:
        raise ValueError("area_fraction must be between 0 and 1.")

    height, width = array.shape[:2]
    side_fraction = float(np.sqrt(area_fraction))
    rect_h = min(height, max(1, int(round(height * side_fraction))))
    rect_w = min(width, max(1, int(round(width * side_fraction))))
    top = int(rng.integers(0, height - rect_h + 1))
    left = int(rng.integers(0, width - rect_w + 1))
    bottom = top + rect_h
    right = left + rect_w

    result = array.copy()
    result[top:bottom, left:right] = fill_value
    visibility = np.ones((height, width), dtype=np.uint8)
    visibility[top:bottom, left:right] = 0
    box = {"left": left, "top": top, "right": right, "bottom": bottom}
    return result, visibility, box


def apply_degradation(
    image: ArrayLike,
    specification: Mapping[str, Any],
    *,
    rng: np.random.Generator,
) -> DegradationResult:
    """Apply one configuration-defined degradation to an image."""
    if not isinstance(specification, Mapping):
        raise ValueError("Degradation specification must be a mapping.")

    array = _validate_image(image)
    name = str(specification.get("type", "")).strip().lower()
    visibility = _full_visibility_mask(array)

    if name == "gaussian_noise":
        sigma_fraction = float(specification.get("sigma_fraction", 0.03))
        degraded = gaussian_noise(array, sigma_fraction=sigma_fraction, rng=rng)
        metadata = {"type": name, "sigma_fraction": sigma_fraction}

    elif name == "impulse_noise":
        probability = float(specification.get("probability", 0.02))
        salt_fraction = float(specification.get("salt_fraction", 0.5))
        degraded = impulse_noise(
            array,
            probability=probability,
            salt_fraction=salt_fraction,
            rng=rng,
        )
        metadata = {
            "type": name,
            "probability": probability,
            "salt_fraction": salt_fraction,
        }

    elif name == "gaussian_blur":
        sigma = float(specification.get("sigma", 1.2))
        degraded = gaussian_blur(array, sigma=sigma)
        metadata = {"type": name, "sigma": sigma}

    elif name == "contrast":
        factor = float(specification.get("factor", 1.25))
        degraded = adjust_contrast(array, factor=factor)
        metadata = {"type": name, "factor": factor}

    elif name == "gamma":
        gamma = float(specification.get("gamma", 1.4))
        degraded = adjust_gamma(array, gamma=gamma)
        metadata = {"type": name, "gamma": gamma}

    elif name == "illumination_gradient":
        strength_fraction = float(specification.get("strength_fraction", 0.15))
        direction = str(specification.get("direction", "horizontal"))
        degraded = illumination_gradient(
            array,
            strength_fraction=strength_fraction,
            direction=direction,
        )
        metadata = {
            "type": name,
            "strength_fraction": strength_fraction,
            "direction": direction,
        }

    elif name == "rectangular_occlusion":
        area_fraction = float(specification.get("area_fraction", 0.10))
        fill_value = float(specification.get("fill_value", 0.0))
        degraded, visibility, box = rectangular_occlusion(
            array,
            area_fraction=area_fraction,
            fill_value=fill_value,
            rng=rng,
        )
        metadata = {
            "type": name,
            "area_fraction": area_fraction,
            "fill_value": fill_value,
            "box": box,
        }

    else:
        raise ValueError(
            "Unsupported degradation type. Use gaussian_noise, impulse_noise, gaussian_blur, "
            "contrast, gamma, illumination_gradient, or rectangular_occlusion."
        )

    return DegradationResult(
        image=degraded,
        metadata=metadata,
        visibility_mask=visibility,
    )
