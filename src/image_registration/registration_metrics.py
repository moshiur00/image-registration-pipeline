"""Ground-truth transform metrics used during method development."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .transforms import apply_transform

FloatArray = NDArray[np.float64]


def transform_point_errors(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
    points: ArrayLike,
) -> FloatArray:
    """Return per-point geometric error between two transforms in pixels."""
    reference_points = apply_transform(points, reference_transform)
    estimated_points = apply_transform(points, estimated_transform)
    return np.linalg.norm(reference_points - estimated_points, axis=1)


def mean_tre_pixels(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
    points: ArrayLike,
) -> float:
    """Return mean target registration error for supplied points."""
    errors = transform_point_errors(reference_transform, estimated_transform, points)
    if errors.size == 0:
        raise ValueError("points must contain at least one point.")
    return float(np.mean(errors))


def rotation_angle_degrees(transform: ArrayLike) -> float:
    """Extract the project rotation angle from a rigid-style transform."""
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    return float(np.rad2deg(np.arctan2(matrix[0, 1], matrix[0, 0])))


def rotation_error_degrees(reference_transform: ArrayLike, estimated_transform: ArrayLike) -> float:
    """Return the smallest absolute 2D rotation difference in degrees."""
    reference = rotation_angle_degrees(reference_transform)
    estimated = rotation_angle_degrees(estimated_transform)
    difference = (estimated - reference + 180.0) % 360.0 - 180.0
    return float(abs(difference))


def centered_translation_parameters(
    transform: ArrayLike,
    center_xy: ArrayLike,
) -> FloatArray:
    """Recover post-rotation translation parameters for a known rotation center."""
    matrix = np.asarray(transform, dtype=np.float64)
    center = np.asarray(center_xy, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    if center.shape != (2,) or not np.all(np.isfinite(center)):
        raise ValueError("center_xy must be a finite length-2 vector.")
    linear = matrix[:2, :2]
    offset = matrix[:2, 2]
    return offset - (center - linear @ center)


def centered_translation_error_pixels(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
    center_xy: ArrayLike,
) -> float:
    """Return translation-parameter error for transforms defined about one center."""
    reference = centered_translation_parameters(reference_transform, center_xy)
    estimated = centered_translation_parameters(estimated_transform, center_xy)
    return float(np.linalg.norm(estimated - reference))


def affine_linear_error(reference_transform: ArrayLike, estimated_transform: ArrayLike) -> float:
    """Return Frobenius error between the 2x2 affine linear components."""
    reference = np.asarray(reference_transform, dtype=np.float64)
    estimated = np.asarray(estimated_transform, dtype=np.float64)
    if reference.shape != (3, 3) or estimated.shape != (3, 3):
        raise ValueError("Transforms must have shape (3, 3).")
    if not np.all(np.isfinite(reference)) or not np.all(np.isfinite(estimated)):
        raise ValueError("Transforms must contain only finite values.")
    return float(np.linalg.norm(estimated[:2, :2] - reference[:2, :2], ord="fro"))
