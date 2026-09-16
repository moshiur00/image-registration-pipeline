"""Image-pyramid utilities for coarse-to-fine registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class PyramidLevel:
    """One image-pyramid level derived from the original image."""

    scale: float
    image: NDArray[np.generic]

    @property
    def shape(self) -> tuple[int, int]:
        return int(self.image.shape[0]), int(self.image.shape[1])


def validate_pyramid_scales(scales: Sequence[float]) -> tuple[float, ...]:
    """Validate ascending pyramid scales ending at full resolution."""
    values = tuple(float(value) for value in scales)
    if not values:
        raise ValueError("Pyramid scales must contain at least one value.")
    if any(not np.isfinite(value) or value <= 0.0 or value > 1.0 for value in values):
        raise ValueError("Pyramid scales must be finite values in the range (0, 1].")
    if any(right <= left for left, right in zip(values, values[1:], strict=False)):
        raise ValueError("Pyramid scales must be strictly increasing.")
    if not np.isclose(values[-1], 1.0):
        raise ValueError("The final pyramid scale must be 1.0.")
    return values


def build_image_pyramid(
    image: ArrayLike,
    scales: Sequence[float],
    *,
    pre_smoothing_sigma: float = 0.8,
) -> list[PyramidLevel]:
    """Build coarse-to-fine levels directly from the original 2D image."""
    array = np.asarray(image)
    if array.ndim != 2 or array.size == 0:
        raise ValueError("Image pyramid expects a non-empty 2D image.")
    if not np.all(np.isfinite(array)):
        raise ValueError("Image pyramid expects only finite values.")
    if not np.isfinite(pre_smoothing_sigma) or pre_smoothing_sigma < 0.0:
        raise ValueError("pre_smoothing_sigma must be finite and non-negative.")

    validated = validate_pyramid_scales(scales)
    height, width = int(array.shape[0]), int(array.shape[1])
    levels: list[PyramidLevel] = []

    for scale in validated:
        if np.isclose(scale, 1.0):
            resized = array.copy()
        else:
            source = array
            if pre_smoothing_sigma > 0.0:
                source = cv2.GaussianBlur(
                    array,
                    ksize=(0, 0),
                    sigmaX=float(pre_smoothing_sigma),
                    sigmaY=float(pre_smoothing_sigma),
                )
            target_width = max(2, int(round(width * scale)))
            target_height = max(2, int(round(height * scale)))
            resized = cv2.resize(
                source,
                (target_width, target_height),
                interpolation=cv2.INTER_AREA,
            )
        levels.append(PyramidLevel(scale=scale, image=resized))

    return levels


def _shape_scale_matrix(
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> FloatArray:
    source_height, source_width = int(source_shape[0]), int(source_shape[1])
    target_height, target_width = int(target_shape[0]), int(target_shape[1])
    if min(source_height, source_width, target_height, target_width) <= 0:
        raise ValueError("Image shapes must contain positive height and width.")

    scale_x = target_width / source_width
    scale_y = target_height / source_height
    return np.array(
        [[scale_x, 0.0, 0.0], [0.0, scale_y, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def rescale_transform_between_shapes(
    transform: ArrayLike,
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> FloatArray:
    """Convert one Moving -> Fixed transform between image coordinate scales.

    Both moving and fixed images are assumed to share the same source shape and
    the same target shape. Coordinate conversion uses homogeneous conjugation,
    so translation and affine linear terms remain correct even when rounding
    causes slightly different x and y scale factors.
    """
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    if not np.isclose(matrix[2, 2], 1.0) or not np.allclose(matrix[2, :2], 0.0):
        raise ValueError("transform must be a 2D affine-form homogeneous matrix.")

    scale = _shape_scale_matrix(source_shape, target_shape)
    return scale @ matrix @ np.linalg.inv(scale)
