"""Shared adapter helpers that keep UI logic outside the research backend."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import Any

import numpy as np
from numpy.typing import NDArray

from image_registration.evaluation import evaluate_pair
from image_registration.registration_metrics import (
    affine_linear_error,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.synthetic import default_control_points
from image_registration.transforms import apply_transform

from ui.core.contracts import AdapterResult, RegistrationRequest
from ui.core.image_inputs import prepare_image_source

FloatArray = NDArray[np.float64]


def prepare_2d_pair(request: RegistrationRequest) -> tuple[NDArray[np.float32], NDArray[np.float32], dict[str, Any]]:
    fixed = prepare_image_source(request.fixed, request.preprocessing, name="Fixed")
    moving = prepare_image_source(request.moving, request.preprocessing, name="Moving")
    if fixed.array.ndim != 2 or moving.array.ndim != 2:
        raise ValueError("The Stage 3 2D adapters require grayscale 2D images.")
    return fixed.array, moving.array, {
        "fixed_source": fixed.source_metadata,
        "moving_source": moving.source_metadata,
        "fixed_preprocessing": fixed.preprocessing_report,
        "moving_preprocessing": moving.preprocessing_report,
    }


def descriptive_metrics(fixed: NDArray[np.generic], other: NDArray[np.generic]) -> dict[str, float]:
    if np.asarray(fixed).shape != np.asarray(other).shape:
        return {}
    try:
        return evaluate_pair(fixed, other)
    except ValueError:
        return {}


def transform_parameters(matrix: NDArray[np.generic], motion_model: str) -> dict[str, Any]:
    transform = np.asarray(matrix, dtype=np.float64)
    linear = transform[:2, :2]
    result: dict[str, Any] = {
        "matrix_offset_tx": float(transform[0, 2]),
        "matrix_offset_ty": float(transform[1, 2]),
        "determinant": float(np.linalg.det(linear)),
    }
    if motion_model in {"rigid", "similarity"}:
        result["rotation_degrees"] = float(np.rad2deg(np.arctan2(linear[0, 1], linear[0, 0])))
    if motion_model == "similarity":
        determinant = float(np.linalg.det(linear))
        result["scale"] = float(np.sqrt(determinant)) if determinant > 0.0 else None
    return result


def transform_plausibility(matrix: NDArray[np.generic], fixed_shape: tuple[int, ...]) -> tuple[bool, tuple[str, ...], dict[str, float]]:
    transform = np.asarray(matrix, dtype=np.float64)
    reasons: list[str] = []
    if transform.shape != (3, 3) or not np.all(np.isfinite(transform)):
        return False, ("invalid_transform",), {}
    linear = transform[:2, :2]
    determinant = float(np.linalg.det(linear))
    singular_values = np.linalg.svd(linear, compute_uv=False)
    min_scale = float(np.min(singular_values))
    max_scale = float(np.max(singular_values))
    translation_norm = float(np.linalg.norm(transform[:2, 2]))
    diagonal = float(np.hypot(fixed_shape[0], fixed_shape[1]))
    translation_fraction = translation_norm / diagonal if diagonal > 0.0 else float("inf")
    if determinant <= 0.0:
        reasons.append("reflection_or_singular_transform")
    if min_scale < 0.10 or max_scale > 10.0:
        reasons.append("extreme_scale")
    if translation_fraction > 2.0:
        reasons.append("extreme_translation")
    return not reasons, tuple(reasons), {
        "determinant": determinant,
        "principal_scale_min": min_scale,
        "principal_scale_max": max_scale,
        "translation_norm_pixels": translation_norm,
        "translation_fraction_of_diagonal": translation_fraction,
    }


def ground_truth_metrics(
    request: RegistrationRequest,
    estimated_transform: NDArray[np.generic],
    fixed_shape: tuple[int, ...],
) -> tuple[dict[str, float], bool | None]:
    context = request.evaluation
    reference = context.ground_truth_transform
    if reference is None:
        return {}, None

    reference_array = np.asarray(reference, dtype=np.float64)
    estimated = np.asarray(estimated_transform, dtype=np.float64)
    if reference_array.shape != (3, 3) or estimated.shape != (3, 3):
        return {}, None

    if context.moving_landmarks is not None and context.fixed_landmarks is not None:
        predicted = apply_transform(context.moving_landmarks, estimated)
        residuals = np.linalg.norm(predicted - np.asarray(context.fixed_landmarks), axis=1)
        tre = float(np.mean(residuals))
    else:
        points = default_control_points(fixed_shape)
        tre = mean_tre_pixels(reference_array, estimated, points)

    metrics: dict[str, float] = {
        "mean_tre_pixels": tre,
        "matrix_offset_error_pixels": float(
            np.linalg.norm(reference_array[:2, 2] - estimated[:2, 2])
        ),
    }
    model = request.registration.transform_model.value
    if model in {"rigid", "similarity"}:
        metrics["rotation_error_degrees"] = rotation_error_degrees(reference_array, estimated)
    if model == "affine":
        metrics["affine_linear_error"] = affine_linear_error(reference_array, estimated)

    threshold = context.thresholds.get("mean_tre_pixels")
    within = None if threshold is None else bool(tre <= float(threshold))
    return metrics, within


def failed_result(
    *,
    start: float,
    failure_reason: str,
    diagnostics: dict[str, Any] | None = None,
    warnings: tuple[str, ...] = (),
    registered_array: NDArray[np.generic] | None = None,
) -> AdapterResult:
    return AdapterResult(
        method_success=False,
        runtime_seconds=perf_counter() - start,
        transform_matrix=None,
        registered_array=registered_array,
        diagnostics=diagnostics or {},
        warnings=warnings,
        failure_reason=failure_reason,
    )
