"""Utilities for controlled rigid Mutual Information parameter studies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .preprocessing import clip_percentiles, gaussian_smooth, robust_normalize

FloatImage = NDArray[np.float32]
PreprocessingMode = Literal[
    "none",
    "robust_clip",
    "robust_normalize",
    "zscore",
    "gaussian_smooth",
]
SUPPORTED_MI_PREPROCESSING = frozenset(
    {
        "none",
        "robust_clip",
        "robust_normalize",
        "zscore",
        "gaussian_smooth",
    }
)


@dataclass(frozen=True)
class MIPreprocessingResult:
    """One preprocessed image plus the operation metadata used to create it."""

    image: FloatImage
    metadata: dict[str, Any]


def _as_float32_image(image: ArrayLike) -> FloatImage:
    values = np.asarray(image)
    if values.ndim != 2:
        raise ValueError("Mutual Information preprocessing requires a 2D grayscale image.")
    if values.size == 0:
        raise ValueError("Mutual Information preprocessing requires a non-empty image.")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError("Mutual Information preprocessing requires numeric image values.")
    output = values.astype(np.float32)
    if not np.all(np.isfinite(output)):
        raise ValueError("Mutual Information preprocessing requires finite image values.")
    return output


def apply_mi_preprocessing(
    image: ArrayLike,
    spec: Mapping[str, Any] | None,
) -> MIPreprocessingResult:
    """Apply one modality-safe preprocessing option without histogram matching.

    Each image is processed independently. None of the supported options uses the
    other modality's intensity distribution, so the operation does not force the
    fixed and moving histograms to become identical.
    """
    values = _as_float32_image(image)
    config = {} if spec is None else dict(spec)
    mode = str(config.get("type", "none")).strip().lower()
    if mode not in SUPPORTED_MI_PREPROCESSING:
        supported = ", ".join(sorted(SUPPORTED_MI_PREPROCESSING))
        raise ValueError(f"Unsupported MI preprocessing type '{mode}'. Supported types: {supported}.")

    metadata: dict[str, Any] = {"type": mode}

    if mode == "none":
        output = values.copy()

    elif mode == "robust_clip":
        lower = float(config.get("lower_percentile", 1.0))
        upper = float(config.get("upper_percentile", 99.0))
        output = clip_percentiles(values, lower=lower, upper=upper).astype(np.float32)
        metadata.update({"lower_percentile": lower, "upper_percentile": upper})

    elif mode == "robust_normalize":
        lower = float(config.get("lower_percentile", 1.0))
        upper = float(config.get("upper_percentile", 99.0))
        output = robust_normalize(values, lower=lower, upper=upper).astype(np.float32)
        metadata.update({"lower_percentile": lower, "upper_percentile": upper})

    elif mode == "zscore":
        mean = float(np.mean(values, dtype=np.float64))
        std = float(np.std(values, dtype=np.float64))
        if not np.isfinite(std) or np.isclose(std, 0.0):
            output = np.zeros_like(values, dtype=np.float32)
        else:
            output = ((values - mean) / std).astype(np.float32)
        metadata.update({"input_mean": mean, "input_std": std})

    else:
        sigma = float(config.get("sigma", 1.0))
        output = gaussian_smooth(values, sigma=sigma).astype(np.float32)
        metadata.update({"sigma": sigma})

    metadata.update(
        {
            "output_min": float(np.min(output)),
            "output_max": float(np.max(output)),
            "output_mean": float(np.mean(output, dtype=np.float64)),
            "output_std": float(np.std(output, dtype=np.float64)),
        }
    )
    return MIPreprocessingResult(image=output, metadata=metadata)


def summarize_mi_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate method success, geometric accuracy, runtime, and optimizer evidence."""
    record_list = list(records)
    method_success_count = sum(bool(item.get("method_success", False)) for item in record_list)
    within_tolerance_count = sum(bool(item.get("within_tolerance", False)) for item in record_list)

    tre_values = [
        float(item["tre_pixels"])
        for item in record_list
        if item.get("tre_pixels") is not None and np.isfinite(float(item["tre_pixels"]))
    ]
    rotation_values = [
        float(item["rotation_error_degrees"])
        for item in record_list
        if item.get("rotation_error_degrees") is not None
        and np.isfinite(float(item["rotation_error_degrees"]))
    ]
    translation_values = [
        float(item["translation_error_pixels"])
        for item in record_list
        if item.get("translation_error_pixels") is not None
        and np.isfinite(float(item["translation_error_pixels"]))
    ]
    runtimes = [
        float(item["runtime_ms"])
        for item in record_list
        if item.get("runtime_ms") is not None and np.isfinite(float(item["runtime_ms"]))
    ]
    valid_points = [
        int(item["valid_metric_points"])
        for item in record_list
        if item.get("valid_metric_points") is not None
    ]
    iteration_counts = [
        int(item["optimizer_iteration"])
        for item in record_list
        if item.get("optimizer_iteration") is not None
    ]

    return {
        "case_count": len(record_list),
        "method_success_count": int(method_success_count),
        "within_tolerance_count": int(within_tolerance_count),
        "within_tolerance_rate": (
            0.0 if not record_list else float(within_tolerance_count / len(record_list))
        ),
        "median_tre_pixels": None if not tre_values else float(np.median(tre_values)),
        "maximum_tre_pixels": None if not tre_values else float(np.max(tre_values)),
        "median_rotation_error_degrees": (
            None if not rotation_values else float(np.median(rotation_values))
        ),
        "median_translation_error_pixels": (
            None if not translation_values else float(np.median(translation_values))
        ),
        "mean_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
        "median_runtime_ms": None if not runtimes else float(np.median(runtimes)),
        "median_valid_metric_points": (
            None if not valid_points else float(np.median(valid_points))
        ),
        "median_optimizer_iteration": (
            None if not iteration_counts else float(np.median(iteration_counts))
        ),
    }


def candidate_rank_key(summary: Mapping[str, Any]) -> tuple[float, ...]:
    """Return the deterministic ranking key used for one-factor selection.

    Higher geometric pass count is preferred first. Method execution success is
    next. Median and maximum TRE break remaining ties, followed by runtime. This
    ranking is only for candidates of the same rigid MI method on the same cases.
    """

    def finite_or_inf(value: Any) -> float:
        if value is None:
            return float("inf")
        numeric = float(value)
        return numeric if np.isfinite(numeric) else float("inf")

    return (
        -float(summary.get("within_tolerance_count", 0)),
        -float(summary.get("method_success_count", 0)),
        finite_or_inf(summary.get("median_tre_pixels")),
        finite_or_inf(summary.get("maximum_tre_pixels")),
        finite_or_inf(summary.get("mean_runtime_ms")),
    )


def select_best_candidate(
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Select one controlled candidate using the documented ranking rule."""
    candidate_list = list(candidates)
    if not candidate_list:
        raise ValueError("At least one candidate summary is required.")
    return min(candidate_list, key=lambda item: candidate_rank_key(item["summary"]))
