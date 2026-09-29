"""Robust affine-transform estimation with degeneracy and plausibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .feature_matching import FeatureMatchResult, FeatureResult, correspondence_points
from .transforms import apply_transform

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True)
class CorrespondenceGeometryDiagnostics:
    """Geometric support of the correspondences before model fitting."""

    fixed_grid_coverage: float
    moving_grid_coverage: float
    minimum_grid_coverage: float
    fixed_linearity_ratio: float
    moving_linearity_ratio: float


@dataclass(frozen=True)
class AffineTransformDiagnostics:
    """Plausibility measurements for an estimated affine transformation."""

    determinant: float
    principal_scale_min: float
    principal_scale_max: float
    condition_number: float
    shear_cosine: float
    translation_norm_pixels: float
    translation_fraction_of_diagonal: float | None
    plausible: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class RANSACAffineResult:
    """Affine RANSAC result with explicit support, residual, and failure diagnostics."""

    estimated_transform: FloatArray | None
    inlier_mask: BoolArray
    reprojection_residuals: FloatArray
    success: bool
    runtime_seconds: float
    input_match_count: int
    correspondence_geometry: CorrespondenceGeometryDiagnostics | None = None
    transform_diagnostics: AffineTransformDiagnostics | None = None
    failure_reason: str | None = None
    reprojection_threshold: float = 3.0
    confidence: float = 0.99
    max_trials: int = 3000
    refine_iterations: int = 10
    minimum_inliers: int = 6
    minimum_inlier_ratio: float = 0.0

    @property
    def inlier_count(self) -> int:
        return int(np.count_nonzero(self.inlier_mask))

    @property
    def outlier_count(self) -> int:
        return max(0, int(self.input_match_count) - self.inlier_count)

    @property
    def inlier_ratio(self) -> float | None:
        if self.input_match_count <= 0:
            return None
        return float(self.inlier_count / self.input_match_count)

    @property
    def inlier_residuals(self) -> FloatArray:
        if self.reprojection_residuals.size == 0 or self.inlier_mask.size == 0:
            return np.empty((0,), dtype=np.float64)
        return self.reprojection_residuals[self.inlier_mask]


def _validate_points(points: ArrayLike, *, name: str) -> FloatArray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} must have shape (N, 2).")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
    return np.ascontiguousarray(array)


def _validate_shape(image_shape: tuple[int, ...], *, name: str) -> tuple[int, int]:
    if len(image_shape) < 2:
        raise ValueError(f"{name} must include height and width.")
    height, width = int(image_shape[0]), int(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError(f"{name} dimensions must be positive.")
    return height, width


def point_grid_coverage(
    points: ArrayLike,
    image_shape: tuple[int, ...],
    *,
    rows: int = 4,
    cols: int = 4,
) -> float:
    """Return the fraction of grid cells occupied by at least one point."""
    coordinates = _validate_points(points, name="points")
    height, width = _validate_shape(image_shape, name="image_shape")
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be greater than zero.")
    if coordinates.shape[0] == 0:
        return 0.0

    x = np.clip(coordinates[:, 0], 0.0, max(0.0, width - 1.0))
    y = np.clip(coordinates[:, 1], 0.0, max(0.0, height - 1.0))
    col_index = np.minimum((x / max(width, 1) * cols).astype(int), cols - 1)
    row_index = np.minimum((y / max(height, 1) * rows).astype(int), rows - 1)
    occupied = {(int(r), int(c)) for r, c in zip(row_index, col_index, strict=True)}
    return float(len(occupied) / (rows * cols))


def point_linearity_ratio(points: ArrayLike) -> float:
    """Return minor-to-major covariance eigenvalue ratio for 2D point spread."""
    coordinates = _validate_points(points, name="points")
    if coordinates.shape[0] < 3:
        return 0.0
    centered = coordinates - np.mean(coordinates, axis=0, keepdims=True)
    covariance = centered.T @ centered / float(coordinates.shape[0])
    eigenvalues = np.linalg.eigvalsh(covariance)
    major = float(np.max(eigenvalues))
    minor = float(np.min(eigenvalues))
    if major <= np.finfo(np.float64).eps:
        return 0.0
    return float(max(0.0, minor) / major)


def correspondence_geometry_diagnostics(
    fixed_points: ArrayLike,
    moving_points: ArrayLike,
    *,
    fixed_shape: tuple[int, ...],
    moving_shape: tuple[int, ...],
    grid_rows: int = 4,
    grid_cols: int = 4,
) -> CorrespondenceGeometryDiagnostics:
    """Measure point spread in both fixed and moving images."""
    fixed = _validate_points(fixed_points, name="fixed_points")
    moving = _validate_points(moving_points, name="moving_points")
    if fixed.shape[0] != moving.shape[0]:
        raise ValueError("fixed_points and moving_points must contain the same number of points.")
    fixed_coverage = point_grid_coverage(fixed, fixed_shape, rows=grid_rows, cols=grid_cols)
    moving_coverage = point_grid_coverage(moving, moving_shape, rows=grid_rows, cols=grid_cols)
    return CorrespondenceGeometryDiagnostics(
        fixed_grid_coverage=fixed_coverage,
        moving_grid_coverage=moving_coverage,
        minimum_grid_coverage=float(min(fixed_coverage, moving_coverage)),
        fixed_linearity_ratio=point_linearity_ratio(fixed),
        moving_linearity_ratio=point_linearity_ratio(moving),
    )


def affine_transform_diagnostics(
    transform: ArrayLike,
    *,
    image_shape: tuple[int, ...] | None = None,
    min_abs_determinant: float = 0.10,
    min_principal_scale: float = 0.50,
    max_principal_scale: float = 1.80,
    max_condition_number: float = 3.0,
    max_shear_cosine: float = 0.65,
    max_translation_fraction_of_diagonal: float = 1.5,
    allow_reflection: bool = False,
) -> AffineTransformDiagnostics:
    """Measure affine plausibility without assuming the estimate is correct."""
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    linear = matrix[:2, :2]
    determinant = float(np.linalg.det(linear))
    singular_values = np.linalg.svd(linear, compute_uv=False)
    minimum_scale = float(np.min(singular_values))
    maximum_scale = float(np.max(singular_values))
    condition = float(maximum_scale / minimum_scale) if minimum_scale > 0.0 else float("inf")

    col0 = linear[:, 0]
    col1 = linear[:, 1]
    denom = float(np.linalg.norm(col0) * np.linalg.norm(col1))
    shear_cosine = float(abs(np.dot(col0, col1)) / denom) if denom > 0.0 else 1.0
    translation_norm = float(np.linalg.norm(matrix[:2, 2]))

    translation_fraction: float | None = None
    if image_shape is not None:
        height, width = _validate_shape(image_shape, name="image_shape")
        diagonal = float(np.hypot(width, height))
        translation_fraction = float(translation_norm / diagonal) if diagonal > 0.0 else None

    reasons: list[str] = []
    if abs(determinant) < min_abs_determinant:
        reasons.append("near_singular_transform")
    if determinant < 0.0 and not allow_reflection:
        reasons.append("reflection_not_allowed")
    if minimum_scale < min_principal_scale or maximum_scale > max_principal_scale:
        reasons.append("implausible_principal_scale")
    if condition > max_condition_number:
        reasons.append("implausible_condition_number")
    if shear_cosine > max_shear_cosine:
        reasons.append("implausible_shear")
    if (
        translation_fraction is not None
        and translation_fraction > max_translation_fraction_of_diagonal
    ):
        reasons.append("implausible_translation")

    return AffineTransformDiagnostics(
        determinant=determinant,
        principal_scale_min=minimum_scale,
        principal_scale_max=maximum_scale,
        condition_number=condition,
        shear_cosine=shear_cosine,
        translation_norm_pixels=translation_norm,
        translation_fraction_of_diagonal=translation_fraction,
        plausible=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _validate_parameters(
    *,
    reprojection_threshold: float,
    confidence: float,
    max_trials: int,
    refine_iterations: int,
    minimum_matches: int,
    minimum_inliers: int,
    minimum_inlier_ratio: float,
    minimum_spatial_coverage: float,
    minimum_linearity_ratio: float,
) -> None:
    if not np.isfinite(reprojection_threshold) or reprojection_threshold <= 0.0:
        raise ValueError("reprojection_threshold must be finite and greater than zero.")
    if not np.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be finite and in the range (0, 1).")
    if max_trials <= 0:
        raise ValueError("max_trials must be greater than zero.")
    if refine_iterations < 0:
        raise ValueError("refine_iterations must be non-negative.")
    if minimum_matches < 3:
        raise ValueError("minimum_matches must be at least 3 for an affine model.")
    if minimum_inliers < 3:
        raise ValueError("minimum_inliers must be at least 3 for an affine model.")
    if not 0.0 <= minimum_inlier_ratio <= 1.0:
        raise ValueError("minimum_inlier_ratio must be in the range [0, 1].")
    if not 0.0 <= minimum_spatial_coverage <= 1.0:
        raise ValueError("minimum_spatial_coverage must be in the range [0, 1].")
    if not 0.0 <= minimum_linearity_ratio <= 1.0:
        raise ValueError("minimum_linearity_ratio must be in the range [0, 1].")


def _failure_result(
    *,
    input_match_count: int,
    reason: str,
    geometry: CorrespondenceGeometryDiagnostics | None,
    reprojection_threshold: float,
    confidence: float,
    max_trials: int,
    refine_iterations: int,
    minimum_inliers: int,
    minimum_inlier_ratio: float,
    runtime_seconds: float = 0.0,
    transform: FloatArray | None = None,
    inlier_mask: BoolArray | None = None,
    residuals: FloatArray | None = None,
    transform_diagnostics: AffineTransformDiagnostics | None = None,
) -> RANSACAffineResult:
    return RANSACAffineResult(
        estimated_transform=transform,
        inlier_mask=(
            np.zeros((max(0, input_match_count),), dtype=bool)
            if inlier_mask is None
            else inlier_mask
        ),
        reprojection_residuals=(
            np.empty((0,), dtype=np.float64) if residuals is None else residuals
        ),
        success=False,
        runtime_seconds=float(runtime_seconds),
        input_match_count=int(max(0, input_match_count)),
        correspondence_geometry=geometry,
        transform_diagnostics=transform_diagnostics,
        failure_reason=reason,
        reprojection_threshold=float(reprojection_threshold),
        confidence=float(confidence),
        max_trials=int(max_trials),
        refine_iterations=int(refine_iterations),
        minimum_inliers=int(minimum_inliers),
        minimum_inlier_ratio=float(minimum_inlier_ratio),
    )


def estimate_affine_ransac(
    fixed_points: ArrayLike,
    moving_points: ArrayLike,
    *,
    fixed_shape: tuple[int, ...],
    moving_shape: tuple[int, ...],
    reprojection_threshold: float = 3.0,
    confidence: float = 0.99,
    max_trials: int = 3000,
    refine_iterations: int = 10,
    minimum_matches: int = 6,
    minimum_inliers: int = 6,
    minimum_inlier_ratio: float = 0.0,
    grid_rows: int = 4,
    grid_cols: int = 4,
    minimum_spatial_coverage: float = 0.125,
    minimum_linearity_ratio: float = 0.01,
    min_abs_determinant: float = 0.10,
    min_principal_scale: float = 0.50,
    max_principal_scale: float = 1.80,
    max_condition_number: float = 3.0,
    max_shear_cosine: float = 0.65,
    max_translation_fraction_of_diagonal: float = 1.5,
    allow_reflection: bool = False,
    random_seed: int = 42,
) -> RANSACAffineResult:
    """Estimate a Moving -> Fixed affine transform with RANSAC and guardrails."""
    _validate_parameters(
        reprojection_threshold=reprojection_threshold,
        confidence=confidence,
        max_trials=max_trials,
        refine_iterations=refine_iterations,
        minimum_matches=minimum_matches,
        minimum_inliers=minimum_inliers,
        minimum_inlier_ratio=minimum_inlier_ratio,
        minimum_spatial_coverage=minimum_spatial_coverage,
        minimum_linearity_ratio=minimum_linearity_ratio,
    )
    fixed = _validate_points(fixed_points, name="fixed_points")
    moving = _validate_points(moving_points, name="moving_points")
    if fixed.shape[0] != moving.shape[0]:
        raise ValueError("fixed_points and moving_points must contain the same number of points.")
    count = int(fixed.shape[0])
    if count < minimum_matches:
        return _failure_result(
            input_match_count=count,
            reason="insufficient_matches",
            geometry=None,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    geometry = correspondence_geometry_diagnostics(
        fixed,
        moving,
        fixed_shape=fixed_shape,
        moving_shape=moving_shape,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
    )
    if min(geometry.fixed_linearity_ratio, geometry.moving_linearity_ratio) < minimum_linearity_ratio:
        return _failure_result(
            input_match_count=count,
            reason="degenerate_correspondences_collinear",
            geometry=geometry,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )
    if geometry.minimum_grid_coverage < minimum_spatial_coverage:
        return _failure_result(
            input_match_count=count,
            reason="poor_spatial_coverage",
            geometry=geometry,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    cv2.setRNGSeed(int(random_seed))
    start = perf_counter()
    try:
        matrix_2x3, inliers = cv2.estimateAffine2D(
            moving,
            fixed,
            method=cv2.RANSAC,
            ransacReprojThreshold=float(reprojection_threshold),
            maxIters=int(max_trials),
            confidence=float(confidence),
            refineIters=int(refine_iterations),
        )
    except cv2.error as exc:
        return _failure_result(
            input_match_count=count,
            reason=f"opencv_error: {exc}",
            geometry=geometry,
            runtime_seconds=perf_counter() - start,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )
    runtime = perf_counter() - start

    if matrix_2x3 is None or inliers is None:
        return _failure_result(
            input_match_count=count,
            reason="ransac_estimation_failed",
            geometry=geometry,
            runtime_seconds=runtime,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    matrix_2x3 = np.asarray(matrix_2x3, dtype=np.float64)
    if matrix_2x3.shape != (2, 3) or not np.all(np.isfinite(matrix_2x3)):
        return _failure_result(
            input_match_count=count,
            reason="invalid_estimated_transform",
            geometry=geometry,
            runtime_seconds=runtime,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    transform = np.eye(3, dtype=np.float64)
    transform[:2, :] = matrix_2x3
    mask = np.asarray(inliers).reshape(-1).astype(bool)
    if mask.shape != (count,):
        return _failure_result(
            input_match_count=count,
            reason="invalid_inlier_mask",
            geometry=geometry,
            runtime_seconds=runtime,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    predicted = apply_transform(moving, transform)
    residuals = np.linalg.norm(predicted - fixed, axis=1).astype(np.float64)
    diagnostics = affine_transform_diagnostics(
        transform,
        image_shape=fixed_shape,
        min_abs_determinant=min_abs_determinant,
        min_principal_scale=min_principal_scale,
        max_principal_scale=max_principal_scale,
        max_condition_number=max_condition_number,
        max_shear_cosine=max_shear_cosine,
        max_translation_fraction_of_diagonal=max_translation_fraction_of_diagonal,
        allow_reflection=allow_reflection,
    )
    inlier_count = int(np.count_nonzero(mask))
    ratio = float(inlier_count / count) if count else 0.0

    failure_reason: str | None = None
    if inlier_count < minimum_inliers:
        failure_reason = "insufficient_ransac_inliers"
    elif ratio < minimum_inlier_ratio:
        failure_reason = "low_inlier_ratio"
    elif not diagnostics.plausible:
        failure_reason = diagnostics.rejection_reasons[0]

    return RANSACAffineResult(
        estimated_transform=transform,
        inlier_mask=mask,
        reprojection_residuals=residuals,
        success=failure_reason is None,
        runtime_seconds=runtime,
        input_match_count=count,
        correspondence_geometry=geometry,
        transform_diagnostics=diagnostics,
        failure_reason=failure_reason,
        reprojection_threshold=float(reprojection_threshold),
        confidence=float(confidence),
        max_trials=int(max_trials),
        refine_iterations=int(refine_iterations),
        minimum_inliers=int(minimum_inliers),
        minimum_inlier_ratio=float(minimum_inlier_ratio),
    )


def estimate_affine_ransac_from_matches(
    matches: FeatureMatchResult,
    fixed_features: FeatureResult,
    moving_features: FeatureResult,
    *,
    fixed_shape: tuple[int, ...],
    moving_shape: tuple[int, ...],
    **kwargs: object,
) -> RANSACAffineResult:
    """Estimate affine geometry from accepted feature correspondences."""
    if not matches.success:
        minimum_inliers = int(kwargs.get("minimum_inliers", 6))
        minimum_inlier_ratio = float(kwargs.get("minimum_inlier_ratio", 0.0))
        return _failure_result(
            input_match_count=matches.accepted_count,
            reason=matches.failure_reason or "matching_failed",
            geometry=None,
            reprojection_threshold=float(kwargs.get("reprojection_threshold", 3.0)),
            confidence=float(kwargs.get("confidence", 0.99)),
            max_trials=int(kwargs.get("max_trials", 3000)),
            refine_iterations=int(kwargs.get("refine_iterations", 10)),
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )
    fixed_points, moving_points = correspondence_points(matches, fixed_features, moving_features)
    return estimate_affine_ransac(
        fixed_points,
        moving_points,
        fixed_shape=fixed_shape,
        moving_shape=moving_shape,
        **kwargs,
    )


def residual_summary(result: RANSACAffineResult) -> dict[str, float | None]:
    """Return compact all-match and inlier residual statistics."""
    values = result.reprojection_residuals
    inliers = result.inlier_residuals

    def stats(array: FloatArray, prefix: str) -> dict[str, float | None]:
        if array.size == 0:
            return {
                f"{prefix}_mean": None,
                f"{prefix}_median": None,
                f"{prefix}_q95": None,
                f"{prefix}_maximum": None,
            }
        return {
            f"{prefix}_mean": float(np.mean(array)),
            f"{prefix}_median": float(np.median(array)),
            f"{prefix}_q95": float(np.quantile(array, 0.95)),
            f"{prefix}_maximum": float(np.max(array)),
        }

    return {**stats(values, "all"), **stats(inliers, "inlier")}
