"""Descriptive image-similarity metrics for registration pipeline checks."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray
from skimage.metrics import structural_similarity as skimage_ssim

FloatArray = NDArray[np.float64]


def _prepare_pair(
    fixed: ArrayLike,
    moving: ArrayLike,
    mask: ArrayLike | None = None,
) -> tuple[FloatArray, FloatArray, NDArray[np.bool_] | None]:
    fixed_array = np.asarray(fixed, dtype=np.float64)
    moving_array = np.asarray(moving, dtype=np.float64)
    if fixed_array.shape != moving_array.shape:
        raise ValueError("Fixed and moving arrays must have identical shapes.")
    if fixed_array.ndim != 2:
        raise ValueError("Evaluation currently expects 2D grayscale images.")
    if not np.all(np.isfinite(fixed_array)) or not np.all(np.isfinite(moving_array)):
        raise ValueError("Evaluation arrays must contain only finite values.")

    if mask is None:
        return fixed_array, moving_array, None

    mask_array = np.asarray(mask, dtype=bool)
    if mask_array.shape != fixed_array.shape:
        raise ValueError("Evaluation mask must match image shape.")
    if not np.any(mask_array):
        raise ValueError("Evaluation mask must select at least one pixel.")
    return fixed_array, moving_array, mask_array


def mean_absolute_error(fixed: ArrayLike, moving: ArrayLike, mask: ArrayLike | None = None) -> float:
    """Return the mean absolute intensity error."""
    a, b, m = _prepare_pair(fixed, moving, mask)
    diff = np.abs(a - b)
    return float(np.mean(diff[m])) if m is not None else float(np.mean(diff))


def mean_squared_error(fixed: ArrayLike, moving: ArrayLike, mask: ArrayLike | None = None) -> float:
    """Return the mean squared intensity error."""
    a, b, m = _prepare_pair(fixed, moving, mask)
    diff2 = (a - b) ** 2
    return float(np.mean(diff2[m])) if m is not None else float(np.mean(diff2))


def normalized_cross_correlation(
    fixed: ArrayLike,
    moving: ArrayLike,
    mask: ArrayLike | None = None,
) -> float:
    """Return zero-mean normalized cross correlation in approximately [-1, 1]."""
    a, b, m = _prepare_pair(fixed, moving, mask)
    if m is not None:
        a = a[m]
        b = b[m]
    else:
        a = a.reshape(-1)
        b = b.reshape(-1)

    a_centered = a - np.mean(a)
    b_centered = b - np.mean(b)
    denominator = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if np.isclose(denominator, 0.0):
        return 1.0 if np.allclose(a, b) else 0.0
    return float(np.dot(a_centered, b_centered) / denominator)


def structural_similarity(
    fixed: ArrayLike,
    moving: ArrayLike,
    mask: ArrayLike | None = None,
) -> float:
    """Return SSIM, optionally averaged only inside a supplied mask."""
    a, b, m = _prepare_pair(fixed, moving, mask)
    combined_min = float(min(np.min(a), np.min(b)))
    combined_max = float(max(np.max(a), np.max(b)))
    data_range = combined_max - combined_min
    if np.isclose(data_range, 0.0):
        return 1.0 if np.allclose(a, b) else 0.0

    if m is None:
        return float(skimage_ssim(a, b, data_range=data_range))

    score, similarity_map = skimage_ssim(a, b, data_range=data_range, full=True)
    del score
    return float(np.mean(similarity_map[m]))


def evaluate_pair(
    fixed: ArrayLike,
    moving: ArrayLike,
    mask: ArrayLike | None = None,
) -> dict[str, float]:
    """Compute the common descriptive metric set."""
    return {
        "mae": mean_absolute_error(fixed, moving, mask),
        "mse": mean_squared_error(fixed, moving, mask),
        "ncc": normalized_cross_correlation(fixed, moving, mask),
        "ssim": structural_similarity(fixed, moving, mask),
    }
