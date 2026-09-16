"""Helpers for the integrated Week 3 monomodal baseline benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class BaselineThresholds:
    """Development tolerances used for Week 3 geometric validation."""

    translation_error_pixels: float = 0.5
    mean_tre_pixels: float = 1.0
    rigid_translation_error_pixels: float = 1.5
    rotation_error_degrees: float = 1.0
    affine_translation_error_pixels: float = 1.5
    affine_linear_error: float = 0.02

    def __post_init__(self) -> None:
        values = [
            self.translation_error_pixels,
            self.mean_tre_pixels,
            self.rigid_translation_error_pixels,
            self.rotation_error_degrees,
            self.affine_translation_error_pixels,
            self.affine_linear_error,
        ]
        if any(not np.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("All baseline thresholds must be finite and non-negative.")


def within_model_tolerance(
    motion_model: str,
    *,
    optimizer_success: bool,
    mean_tre_pixels: float,
    translation_error_pixels: float,
    rotation_error_degrees: float | None,
    affine_linear_error: float | None,
    thresholds: BaselineThresholds,
) -> bool:
    """Return whether one supported registration result meets Week 3 tolerances."""
    if not optimizer_success:
        return False
    if not np.isfinite(mean_tre_pixels) or not np.isfinite(translation_error_pixels):
        return False

    model = str(motion_model).strip().lower()
    if model == "translation":
        return (
            mean_tre_pixels <= thresholds.mean_tre_pixels
            and translation_error_pixels <= thresholds.translation_error_pixels
        )
    if model == "rigid":
        return (
            rotation_error_degrees is not None
            and np.isfinite(rotation_error_degrees)
            and mean_tre_pixels <= thresholds.mean_tre_pixels
            and translation_error_pixels <= thresholds.rigid_translation_error_pixels
            and rotation_error_degrees <= thresholds.rotation_error_degrees
        )
    if model == "affine":
        return (
            affine_linear_error is not None
            and np.isfinite(affine_linear_error)
            and mean_tre_pixels <= thresholds.mean_tre_pixels
            and translation_error_pixels <= thresholds.affine_translation_error_pixels
            and affine_linear_error <= thresholds.affine_linear_error
        )
    raise ValueError("motion_model must be translation, rigid, or affine.")


def summarize_by_key(
    records: Iterable[Mapping[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    """Aggregate comparable Week 3 records by one categorical field."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        value = str(record[key])
        grouped.setdefault(value, []).append(record)

    summary: dict[str, dict[str, Any]] = {}
    for value, group in sorted(grouped.items()):
        tre = np.asarray([float(item["mean_tre_pixels"]) for item in group], dtype=np.float64)
        runtime = np.asarray([float(item["runtime_ms"]) for item in group], dtype=np.float64)
        ncc_gain = np.asarray(
            [float(item["ncc_after"]) - float(item["ncc_before"]) for item in group],
            dtype=np.float64,
        )
        ssim_gain = np.asarray(
            [float(item["ssim_after"]) - float(item["ssim_before"]) for item in group],
            dtype=np.float64,
        )
        optimizer_successes = sum(bool(item["success"]) for item in group)
        passes = sum(bool(item["within_tolerance"]) for item in group)
        summary[value] = {
            "registration_count": len(group),
            "optimizer_success_count": optimizer_successes,
            "optimizer_success_rate": optimizer_successes / len(group),
            "within_tolerance_count": passes,
            "within_tolerance_rate": passes / len(group),
            "median_mean_tre_pixels": float(np.median(tre)),
            "max_mean_tre_pixels": float(np.max(tre)),
            "mean_runtime_ms": float(np.mean(runtime)),
            "median_runtime_ms": float(np.median(runtime)),
            "mean_ncc_improvement": float(np.mean(ncc_gain)),
            "mean_ssim_improvement": float(np.mean(ssim_gain)),
        }
    return summary
