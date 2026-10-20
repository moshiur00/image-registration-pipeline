"""Unified Week 6 registration metrics.

The functions in this module implement the metric semantics frozen on Day 26.
They deliberately separate geometric reference metrics from descriptive image
similarity. Descriptive metrics are computed only inside an explicit valid
region and never imply geometric correctness on their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .evaluation import (
    mean_absolute_error,
    mean_squared_error,
    normalized_cross_correlation,
    structural_similarity,
)
from .overlap import overlap_fraction

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
TransformModel = Literal["translation", "rigid", "similarity", "affine"]
CoordinateUnit = Literal["px", "mm"]


@dataclass(frozen=True)
class TRESummary:
    """Summary statistics for target registration error."""

    mean: float
    median: float
    std: float
    p95: float
    count: int
    unit: str

    def to_metrics(self) -> dict[str, float]:
        """Return metric keys compatible with the Week 6 evaluation contract."""
        suffix = "px" if self.unit == "px" else "mm"
        return {
            f"tre_mean_{suffix}": self.mean,
            f"tre_median_{suffix}": self.median,
            f"tre_std_{suffix}": self.std,
            f"tre_p95_{suffix}": self.p95,
        }


def _as_homogeneous_transform(transform: ArrayLike, *, name: str) -> FloatArray:
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape not in {(3, 3), (4, 4)}:
        raise ValueError(f"{name} must be a finite 3x3 or 4x4 homogeneous matrix.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must contain only finite values.")
    dimensions = matrix.shape[0] - 1
    expected_last = np.zeros(dimensions + 1, dtype=np.float64)
    expected_last[-1] = 1.0
    if not np.allclose(matrix[-1], expected_last):
        raise ValueError(f"{name} must be an affine-form homogeneous matrix.")
    return matrix


def _validate_transform_pair(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
) -> tuple[FloatArray, FloatArray, int]:
    reference = _as_homogeneous_transform(reference_transform, name="reference_transform")
    estimated = _as_homogeneous_transform(estimated_transform, name="estimated_transform")
    if reference.shape != estimated.shape:
        raise ValueError("reference_transform and estimated_transform must have identical shapes.")
    return reference, estimated, reference.shape[0] - 1


def _apply_homogeneous(points: ArrayLike, transform: FloatArray) -> FloatArray:
    dimensions = transform.shape[0] - 1
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != dimensions:
        raise ValueError(f"points must have shape (N, {dimensions}).")
    if array.shape[0] == 0:
        raise ValueError("points must contain at least one point.")
    if not np.all(np.isfinite(array)):
        raise ValueError("points must contain only finite values.")
    homogeneous = np.concatenate(
        [array, np.ones((array.shape[0], 1), dtype=np.float64)], axis=1
    )
    mapped = (transform @ homogeneous.T).T
    w = mapped[:, -1]
    if np.any(np.isclose(w, 0.0)):
        raise ValueError("Transform produced a homogeneous point with w=0.")
    return mapped[:, :dimensions] / w[:, None]


def _spacing_vector(spacing: ArrayLike, *, dimensions: int) -> FloatArray:
    values = np.asarray(spacing, dtype=np.float64)
    if values.shape != (dimensions,):
        raise ValueError(f"spacing must have shape ({dimensions},).")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("spacing must contain finite positive values.")
    return values


def _rotation_error_2d(reference: FloatArray, estimated: FloatArray) -> float:
    def angle(matrix: FloatArray) -> float:
        linear = matrix[:2, :2]
        return float(np.rad2deg(np.arctan2(linear[0, 1], linear[0, 0])))

    difference = (angle(estimated) - angle(reference) + 180.0) % 360.0 - 180.0
    return float(abs(difference))


def _rotation_error_3d(reference: FloatArray, estimated: FloatArray) -> float:
    reference_linear = reference[:3, :3]
    estimated_linear = estimated[:3, :3]
    for name, linear in (("reference", reference_linear), ("estimated", estimated_linear)):
        if not np.allclose(linear.T @ linear, np.eye(3), atol=1e-6) or not np.isclose(
            np.linalg.det(linear), 1.0, atol=1e-6
        ):
            raise ValueError(f"{name} 3D rigid transform must contain a proper rotation matrix.")
    relative = estimated_linear @ reference_linear.T
    cosine = float(np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0))
    return float(np.rad2deg(np.arccos(cosine)))


def _similarity_scale(matrix: FloatArray, dimensions: int) -> float:
    determinant = float(np.linalg.det(matrix[:dimensions, :dimensions]))
    if determinant <= 0.0:
        raise ValueError("Similarity transform must have a positive linear determinant.")
    return float(determinant ** (1.0 / dimensions))


def model_aware_parameter_errors(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
    *,
    transform_model: TransformModel,
    coordinate_unit: CoordinateUnit = "px",
    spacing: ArrayLike | None = None,
) -> dict[str, float]:
    """Compute model-aware transform parameter errors.

    Translation error is the Euclidean difference between homogeneous offset
    vectors. For pixel-coordinate transforms, optional spacing also produces a
    physical translation error. Rotation is reported for rigid and similarity
    models. Scale is reported for similarity. Affine uses a Frobenius error on
    the complete linear component.

    For transforms already expressed in physical coordinates, set
    ``coordinate_unit='mm'`` and do not pass spacing.
    """
    reference, estimated, dimensions = _validate_transform_pair(
        reference_transform, estimated_transform
    )
    model = str(transform_model).strip().lower()
    if model not in {"translation", "rigid", "similarity", "affine"}:
        raise ValueError("transform_model must be translation, rigid, similarity, or affine.")
    if coordinate_unit not in {"px", "mm"}:
        raise ValueError("coordinate_unit must be 'px' or 'mm'.")

    offset_delta = estimated[:dimensions, -1] - reference[:dimensions, -1]
    metrics: dict[str, float] = {
        f"translation_error_{coordinate_unit}": float(np.linalg.norm(offset_delta))
    }

    if coordinate_unit == "px" and spacing is not None:
        spacing_values = _spacing_vector(spacing, dimensions=dimensions)
        metrics["translation_error_mm"] = float(np.linalg.norm(offset_delta * spacing_values))
    elif coordinate_unit == "mm" and spacing is not None:
        raise ValueError("spacing must be omitted when transforms already use physical coordinates.")

    if model in {"rigid", "similarity"}:
        if dimensions == 2:
            metrics["rotation_error_deg"] = _rotation_error_2d(reference, estimated)
        else:
            metrics["rotation_error_deg"] = _rotation_error_3d(reference, estimated)

    if model == "similarity":
        metrics["scale_error_abs"] = abs(
            _similarity_scale(estimated, dimensions) - _similarity_scale(reference, dimensions)
        )

    if model == "affine":
        metrics["affine_linear_error"] = float(
            np.linalg.norm(
                estimated[:dimensions, :dimensions] - reference[:dimensions, :dimensions],
                ord="fro",
            )
        )

    return metrics


def summarize_tre_errors(errors: ArrayLike, *, unit: CoordinateUnit) -> TRESummary:
    """Summarize a non-empty vector of non-negative TRE values."""
    values = np.asarray(errors, dtype=np.float64).reshape(-1)
    if values.size == 0:
        raise ValueError("TRE errors must contain at least one value.")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("TRE errors must contain finite non-negative values.")
    if unit not in {"px", "mm"}:
        raise ValueError("unit must be 'px' or 'mm'.")
    return TRESummary(
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values, ddof=0)),
        p95=float(np.quantile(values, 0.95)),
        count=int(values.size),
        unit=unit,
    )


def landmark_tre(
    reference_points: ArrayLike,
    estimated_points: ArrayLike,
    *,
    spacing: ArrayLike | None = None,
) -> dict[str, TRESummary]:
    """Compute TRE from corresponding reference and estimated point locations."""
    reference = np.asarray(reference_points, dtype=np.float64)
    estimated = np.asarray(estimated_points, dtype=np.float64)
    if reference.ndim != 2 or reference.shape[0] == 0:
        raise ValueError("reference_points must have shape (N, D) with N > 0.")
    if estimated.shape != reference.shape:
        raise ValueError("estimated_points must match reference_points shape.")
    if reference.shape[1] not in {2, 3}:
        raise ValueError("Landmark TRE supports 2D or 3D points.")
    if not np.all(np.isfinite(reference)) or not np.all(np.isfinite(estimated)):
        raise ValueError("Landmark points must contain only finite values.")

    delta = estimated - reference
    pixel_errors = np.linalg.norm(delta, axis=1)
    summaries = {"px": summarize_tre_errors(pixel_errors, unit="px")}
    if spacing is not None:
        spacing_values = _spacing_vector(spacing, dimensions=reference.shape[1])
        physical_errors = np.linalg.norm(delta * spacing_values, axis=1)
        summaries["mm"] = summarize_tre_errors(physical_errors, unit="mm")
    return summaries


def transform_tre(
    reference_transform: ArrayLike,
    estimated_transform: ArrayLike,
    source_points: ArrayLike,
    *,
    spacing: ArrayLike | None = None,
) -> dict[str, TRESummary]:
    """Compute TRE by applying reference and estimated transforms to source points."""
    reference, estimated, dimensions = _validate_transform_pair(
        reference_transform, estimated_transform
    )
    points = np.asarray(source_points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != dimensions:
        raise ValueError(f"source_points must have shape (N, {dimensions}).")
    reference_points = _apply_homogeneous(points, reference)
    estimated_points = _apply_homogeneous(points, estimated)
    return landmark_tre(reference_points, estimated_points, spacing=spacing)


def _binary_mask(mask: ArrayLike, *, name: str) -> BoolArray:
    array = np.asarray(mask)
    if array.ndim not in {2, 3} or array.size == 0:
        raise ValueError(f"{name} must be a non-empty 2D or 3D mask.")
    if not np.all(np.isin(array, [0, 1, False, True])):
        raise ValueError(f"{name} must contain only binary values.")
    return array.astype(bool)


def dice_score(
    reference_mask: ArrayLike,
    estimated_mask: ArrayLike,
    *,
    both_empty_value: float = 1.0,
) -> float:
    """Return the Dice score with explicit empty-mask behavior.

    If both masks are empty, ``both_empty_value`` is returned. The default of
    1.0 treats two empty masks as perfect agreement. If exactly one mask is
    empty, the score is 0.0.
    """
    reference = _binary_mask(reference_mask, name="reference_mask")
    estimated = _binary_mask(estimated_mask, name="estimated_mask")
    if reference.shape != estimated.shape:
        raise ValueError("reference_mask and estimated_mask must have identical shapes.")
    empty_value = float(both_empty_value)
    if not np.isfinite(empty_value) or not 0.0 <= empty_value <= 1.0:
        raise ValueError("both_empty_value must be finite and in [0, 1].")

    reference_count = int(np.count_nonzero(reference))
    estimated_count = int(np.count_nonzero(estimated))
    denominator = reference_count + estimated_count
    if denominator == 0:
        return empty_value
    intersection = int(np.count_nonzero(reference & estimated))
    return float(2.0 * intersection / denominator)


def evaluation_mutual_information(
    fixed: ArrayLike,
    registered: ArrayLike,
    *,
    mask: ArrayLike | None = None,
    bins: int = 32,
) -> float:
    """Return histogram mutual information in nats inside the valid region."""
    fixed_array = np.asarray(fixed, dtype=np.float64)
    registered_array = np.asarray(registered, dtype=np.float64)
    if fixed_array.shape != registered_array.shape or fixed_array.ndim != 2:
        raise ValueError("fixed and registered must be same-shape 2D arrays.")
    if not np.all(np.isfinite(fixed_array)) or not np.all(np.isfinite(registered_array)):
        raise ValueError("fixed and registered must contain only finite values.")
    if int(bins) < 2:
        raise ValueError("bins must be at least 2.")

    if mask is None:
        valid = np.ones(fixed_array.shape, dtype=bool)
    else:
        valid = np.asarray(mask, dtype=bool)
        if valid.shape != fixed_array.shape:
            raise ValueError("mask must match image shape.")
    if not np.any(valid):
        raise ValueError("Evaluation mask must select at least one pixel.")

    a = fixed_array[valid]
    b = registered_array[valid]
    histogram, _, _ = np.histogram2d(a, b, bins=int(bins))
    total = float(histogram.sum())
    if total <= 0.0:
        raise ValueError("Mutual-information histogram is empty.")
    joint = histogram / total
    marginal_a = joint.sum(axis=1, keepdims=True)
    marginal_b = joint.sum(axis=0, keepdims=True)
    independent = marginal_a @ marginal_b
    nonzero = joint > 0.0
    return float(np.sum(joint[nonzero] * np.log(joint[nonzero] / independent[nonzero])))


def overlap_aware_descriptive_metrics(
    fixed: ArrayLike,
    registered: ArrayLike,
    valid_overlap_mask: ArrayLike,
    *,
    mi_bins: int = 32,
) -> dict[str, float]:
    """Compute the common descriptive metrics inside one explicit overlap mask."""
    fixed_array = np.asarray(fixed)
    registered_array = np.asarray(registered)
    if fixed_array.shape != registered_array.shape or fixed_array.ndim != 2:
        raise ValueError("fixed and registered must be same-shape 2D arrays.")
    valid = np.asarray(valid_overlap_mask)
    if valid.shape != fixed_array.shape:
        raise ValueError("valid_overlap_mask must match image shape.")
    binary = (valid != 0).astype(np.uint8)
    if not np.any(binary):
        raise ValueError("Valid overlap is empty.")

    ssim_registered = np.asarray(registered_array, dtype=np.float64).copy()
    ssim_fixed = np.asarray(fixed_array, dtype=np.float64)
    ssim_registered[binary == 0] = ssim_fixed[binary == 0]

    return {
        "mae": mean_absolute_error(fixed_array, registered_array, binary),
        "mse": mean_squared_error(fixed_array, registered_array, binary),
        "ncc": normalized_cross_correlation(fixed_array, registered_array, binary),
        "ssim": structural_similarity(ssim_fixed, ssim_registered, binary),
        "evaluation_mi": evaluation_mutual_information(
            fixed_array, registered_array, mask=binary, bins=mi_bins
        ),
        "valid_overlap_fraction": overlap_fraction(binary),
    }
