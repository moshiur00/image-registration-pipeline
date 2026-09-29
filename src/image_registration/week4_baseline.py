"""Helpers for the integrated Week 4 feature-based benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class Week4Thresholds:
    """Development tolerances for the integrated feature-based benchmark."""

    translation_tre_pixels: float = 1.0
    translation_error_pixels: float = 1.0
    rigid_tre_pixels: float = 2.0
    rigid_translation_error_pixels: float = 2.0
    rigid_rotation_error_degrees: float = 1.5
    affine_tre_pixels: float = 3.0
    affine_translation_error_pixels: float = 4.0
    affine_linear_error: float = 0.05

    def __post_init__(self) -> None:
        values = [
            self.translation_tre_pixels,
            self.translation_error_pixels,
            self.rigid_tre_pixels,
            self.rigid_translation_error_pixels,
            self.rigid_rotation_error_degrees,
            self.affine_tre_pixels,
            self.affine_translation_error_pixels,
            self.affine_linear_error,
        ]
        if any(not np.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("All Week 4 thresholds must be finite and non-negative.")


def within_week4_tolerance(
    ground_truth_model: str,
    *,
    success: bool,
    mean_tre_pixels: float,
    translation_error_pixels: float,
    rotation_error_degrees: float | None,
    affine_linear_error: float | None,
    thresholds: Week4Thresholds,
) -> bool:
    """Return whether one integrated result meets its model-aware tolerance."""
    if not success:
        return False
    if not np.isfinite(mean_tre_pixels) or not np.isfinite(translation_error_pixels):
        return False

    model = str(ground_truth_model).strip().lower()
    if model == "translation":
        return (
            mean_tre_pixels <= thresholds.translation_tre_pixels
            and translation_error_pixels <= thresholds.translation_error_pixels
        )
    if model == "rigid":
        return (
            rotation_error_degrees is not None
            and np.isfinite(rotation_error_degrees)
            and mean_tre_pixels <= thresholds.rigid_tre_pixels
            and translation_error_pixels <= thresholds.rigid_translation_error_pixels
            and rotation_error_degrees <= thresholds.rigid_rotation_error_degrees
        )
    if model == "affine":
        return (
            affine_linear_error is not None
            and np.isfinite(affine_linear_error)
            and mean_tre_pixels <= thresholds.affine_tre_pixels
            and translation_error_pixels <= thresholds.affine_translation_error_pixels
            and affine_linear_error <= thresholds.affine_linear_error
        )
    raise ValueError("ground_truth_model must be translation, rigid, or affine.")


def summarize_integrated_records(
    records: Iterable[Mapping[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    """Summarize integrated records by a categorical key without hiding failures."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record[key]), []).append(record)

    summary: dict[str, dict[str, Any]] = {}
    for value, group in sorted(groups.items()):
        numeric_tre = [
            float(item["mean_tre_pixels"])
            for item in group
            if item.get("mean_tre_pixels") is not None
            and np.isfinite(float(item["mean_tre_pixels"]))
        ]
        runtimes = [float(item["runtime_ms"]) for item in group]
        success_count = sum(bool(item["success"]) for item in group)
        pass_count = sum(bool(item["within_tolerance"]) for item in group)
        summary[value] = {
            "registration_count": len(group),
            "success_count": success_count,
            "success_rate": success_count / len(group),
            "within_tolerance_count": pass_count,
            "within_tolerance_rate": pass_count / len(group),
            "median_tre_pixels": None if not numeric_tre else float(np.median(numeric_tre)),
            "maximum_tre_pixels": None if not numeric_tre else float(np.max(numeric_tre)),
            "mean_runtime_ms": float(np.mean(runtimes)),
            "median_runtime_ms": float(np.median(runtimes)),
        }
    return summary


def paired_case_comparison(
    records: Iterable[Mapping[str, Any]],
    *,
    method_ids: tuple[str, ...],
    group: str,
) -> dict[str, Any]:
    """Return a fair shared-case comparison for an explicitly defined method group."""
    selected = [record for record in records if str(record.get("comparison_group")) == group]
    case_ids = sorted({str(record["case_id"]) for record in selected})
    rows: list[dict[str, Any]] = []
    complete_case_count = 0

    for case_id in case_ids:
        row: dict[str, Any] = {"case_id": case_id}
        complete = True
        for method_id in method_ids:
            matches = [
                record
                for record in selected
                if str(record["case_id"]) == case_id and str(record["method_id"]) == method_id
            ]
            if len(matches) != 1:
                complete = False
                row[method_id] = None
            else:
                record = matches[0]
                row[method_id] = {
                    "success": bool(record["success"]),
                    "within_tolerance": bool(record["within_tolerance"]),
                    "mean_tre_pixels": record.get("mean_tre_pixels"),
                    "runtime_ms": float(record["runtime_ms"]),
                }
        if complete:
            complete_case_count += 1
        rows.append(row)

    return {
        "comparison_group": group,
        "methods": list(method_ids),
        "case_count": len(case_ids),
        "complete_case_count": complete_case_count,
        "cases": rows,
    }
