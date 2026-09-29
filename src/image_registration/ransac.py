"""Robust similarity-transform estimation from feature correspondences.

This module implements the Day 18 RANSAC stage for the feature-based
registration pipeline. Descriptor matching remains separate from geometric
model estimation so correspondence quality and geometric consistency can be
measured independently.
"""

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
class RANSACSimilarityResult:
    """Similarity estimate with inlier diagnostics and safe failure state."""

    estimated_transform: FloatArray | None
    inlier_mask: BoolArray
    reprojection_residuals: FloatArray
    success: bool
    runtime_seconds: float
    input_match_count: int
    failure_reason: str | None = None
    reprojection_threshold: float = 3.0
    confidence: float = 0.99
    max_trials: int = 2000
    refine_iterations: int = 10
    minimum_inliers: int = 4
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


def _validate_ransac_parameters(
    *,
    reprojection_threshold: float,
    confidence: float,
    max_trials: int,
    refine_iterations: int,
    minimum_matches: int,
    minimum_inliers: int,
    minimum_inlier_ratio: float,
) -> None:
    if not np.isfinite(reprojection_threshold) or reprojection_threshold <= 0.0:
        raise ValueError("reprojection_threshold must be finite and greater than zero.")
    if not np.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be finite and in the range (0, 1).")
    if max_trials <= 0:
        raise ValueError("max_trials must be greater than zero.")
    if refine_iterations < 0:
        raise ValueError("refine_iterations must be non-negative.")
    if minimum_matches < 2:
        raise ValueError("minimum_matches must be at least 2 for a similarity model.")
    if minimum_inliers < 2:
        raise ValueError("minimum_inliers must be at least 2 for a similarity model.")
    if not 0.0 <= minimum_inlier_ratio <= 1.0:
        raise ValueError("minimum_inlier_ratio must be in the range [0, 1].")


def _failure_result(
    *,
    input_match_count: int,
    reason: str,
    runtime_seconds: float = 0.0,
    reprojection_threshold: float,
    confidence: float,
    max_trials: int,
    refine_iterations: int,
    minimum_inliers: int,
    minimum_inlier_ratio: float,
) -> RANSACSimilarityResult:
    return RANSACSimilarityResult(
        estimated_transform=None,
        inlier_mask=np.zeros((max(0, input_match_count),), dtype=bool),
        reprojection_residuals=np.empty((0,), dtype=np.float64),
        success=False,
        runtime_seconds=float(runtime_seconds),
        input_match_count=int(max(0, input_match_count)),
        failure_reason=reason,
        reprojection_threshold=float(reprojection_threshold),
        confidence=float(confidence),
        max_trials=int(max_trials),
        refine_iterations=int(refine_iterations),
        minimum_inliers=int(minimum_inliers),
        minimum_inlier_ratio=float(minimum_inlier_ratio),
    )


def estimate_similarity_ransac(
    fixed_points: ArrayLike,
    moving_points: ArrayLike,
    *,
    reprojection_threshold: float = 3.0,
    confidence: float = 0.99,
    max_trials: int = 2000,
    refine_iterations: int = 10,
    minimum_matches: int = 4,
    minimum_inliers: int = 4,
    minimum_inlier_ratio: float = 0.0,
    random_seed: int = 42,
) -> RANSACSimilarityResult:
    """Estimate a Moving -> Fixed similarity transform with RANSAC.

    ``moving_points`` are the source coordinates and ``fixed_points`` are the
    destination coordinates. OpenCV ``estimateAffinePartial2D`` is used because
    its model is translation, rotation, and isotropic scale without general
    shear or anisotropic scale.
    """
    _validate_ransac_parameters(
        reprojection_threshold=reprojection_threshold,
        confidence=confidence,
        max_trials=max_trials,
        refine_iterations=refine_iterations,
        minimum_matches=minimum_matches,
        minimum_inliers=minimum_inliers,
        minimum_inlier_ratio=minimum_inlier_ratio,
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
        matrix_2x3, inliers = cv2.estimateAffinePartial2D(
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
    determinant = float(np.linalg.det(transform[:2, :2]))
    if not np.isfinite(determinant) or determinant <= 0.0:
        return _failure_result(
            input_match_count=count,
            reason="invalid_similarity_linear_component",
            runtime_seconds=runtime,
            reprojection_threshold=reprojection_threshold,
            confidence=confidence,
            max_trials=max_trials,
            refine_iterations=refine_iterations,
            minimum_inliers=minimum_inliers,
            minimum_inlier_ratio=minimum_inlier_ratio,
        )

    mask = np.asarray(inliers).reshape(-1).astype(bool)
    if mask.shape != (count,):
        return _failure_result(
            input_match_count=count,
            reason="invalid_inlier_mask",
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
    inlier_count = int(np.count_nonzero(mask))
    ratio = float(inlier_count / count) if count else 0.0

    failure_reason: str | None = None
    if inlier_count < minimum_inliers:
        failure_reason = "insufficient_ransac_inliers"
    elif ratio < minimum_inlier_ratio:
        failure_reason = "low_inlier_ratio"

    return RANSACSimilarityResult(
        estimated_transform=transform,
        inlier_mask=mask,
        reprojection_residuals=residuals,
        success=failure_reason is None,
        runtime_seconds=runtime,
        input_match_count=count,
        failure_reason=failure_reason,
        reprojection_threshold=float(reprojection_threshold),
        confidence=float(confidence),
        max_trials=int(max_trials),
        refine_iterations=int(refine_iterations),
        minimum_inliers=int(minimum_inliers),
        minimum_inlier_ratio=float(minimum_inlier_ratio),
    )


def estimate_similarity_ransac_from_matches(
    matches: FeatureMatchResult,
    fixed_features: FeatureResult,
    moving_features: FeatureResult,
    **kwargs: object,
) -> RANSACSimilarityResult:
    """Estimate similarity directly from accepted descriptor correspondences."""
    if not matches.success:
        return _failure_result(
            input_match_count=matches.accepted_count,
            reason=matches.failure_reason or "matching_failed",
            reprojection_threshold=float(kwargs.get("reprojection_threshold", 3.0)),
            confidence=float(kwargs.get("confidence", 0.99)),
            max_trials=int(kwargs.get("max_trials", 2000)),
            refine_iterations=int(kwargs.get("refine_iterations", 10)),
            minimum_inliers=int(kwargs.get("minimum_inliers", 4)),
            minimum_inlier_ratio=float(kwargs.get("minimum_inlier_ratio", 0.0)),
        )
    fixed_points, moving_points = correspondence_points(
        matches, fixed_features, moving_features, accepted_only=True
    )
    return estimate_similarity_ransac(fixed_points, moving_points, **kwargs)


def similarity_scale(transform: ArrayLike) -> float:
    """Return isotropic scale from a similarity-style 3x3 transform."""
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    linear = matrix[:2, :2]
    determinant = float(np.linalg.det(linear))
    if determinant <= 0.0:
        raise ValueError("Similarity transform must have a positive linear determinant.")
    return float(np.sqrt(determinant))


def residual_summary(result: RANSACSimilarityResult) -> dict[str, float | None]:
    """Return compact reprojection-residual statistics for all and inlier matches."""

    def summarize(values: FloatArray) -> dict[str, float | None]:
        if values.size == 0:
            return {"mean": None, "median": None, "maximum": None, "q95": None}
        return {
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "maximum": float(np.max(values)),
            "q95": float(np.quantile(values, 0.95)),
        }

    return {
        "all_mean": summarize(result.reprojection_residuals)["mean"],
        "all_median": summarize(result.reprojection_residuals)["median"],
        "all_maximum": summarize(result.reprojection_residuals)["maximum"],
        "all_q95": summarize(result.reprojection_residuals)["q95"],
        "inlier_mean": summarize(result.inlier_residuals)["mean"],
        "inlier_median": summarize(result.inlier_residuals)["median"],
        "inlier_maximum": summarize(result.inlier_residuals)["maximum"],
        "inlier_q95": summarize(result.inlier_residuals)["q95"],
    }
