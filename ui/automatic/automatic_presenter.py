"""Framework-neutral presentation helpers for automatic candidate comparison.

Stage 6.3 uses these helpers to convert automatic comparison view models into
stable table rows and status summaries. The module has no Streamlit dependency
and deliberately does not expose transform agreement, ranking, or confidence.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .models import (
    AutomaticComparisonView,
    CandidateComparisonView,
    CompatibilityPreviewView,
)


GROUND_TRUTH_EXPLANATION = (
    "Ground truth is unavailable for this image pair. TRE, parameter error, and "
    "geometric correctness are therefore not reported."
)

COMMON_EVIDENCE_EXPLANATION = (
    "MAE, MSE, NCC, SSIM, evaluation Mutual Information, valid overlap, and runtime "
    "are common descriptive evidence. They do not independently establish geometric correctness."
)


_STATUS_LABELS: Mapping[str, str] = {
    "completed": "Completed",
    "check": "CHECK",
    "failed": "Failed",
    "validation_error": "Validation error",
}


def comparison_signature(
    preview: CompatibilityPreviewView, *, include_optional_methods: bool | None = None
) -> str:
    """Return a stable presentation cache key for one compatibility state.

    The backend pair ID already captures images, preprocessing, transform model,
    and modality class. Include the explicit optional-method control when given,
    even if no optional methods are currently compatible. Method IDs also protect
    against a changed catalog or compatibility policy.
    """

    payload = "|".join(
        [
            preview.pair_id,
            f"optional:{include_optional_methods}" if include_optional_methods is not None else "optional:unknown",
            *(f"include:{item.method_id}" for item in preview.compatible),
            *(f"exclude:{item.method_id}" for item in preview.excluded),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def execution_status_label(status: str) -> str:
    normalized = str(status).strip().lower()
    return _STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def transform_state_label(plausible: bool | None) -> str:
    if plausible is True:
        return "Plausible"
    if plausible is False:
        return "Implausible"
    return "Unavailable"


def recommendation_state_label(status: str) -> str:
    normalized = str(status).strip().lower()
    if normalized == "deferred_until_robustness_calibration":
        return "Not calibrated"
    return normalized.replace("_", " ").title()


def _metric(mapping: Mapping[str, float], key: str) -> float | None:
    value = mapping.get(key)
    return None if value is None else float(value)


def _display_number(value: float | None, *, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def candidate_evidence_rows(view: AutomaticComparisonView) -> list[dict[str, Any]]:
    """Build the Stage 6.3 cross-method evidence table.

    Only common evidence is included. Method-specific optimizer diagnostics are
    intentionally excluded and remain available in the view model for Stage 6.4.
    """

    rows: list[dict[str, Any]] = []
    for candidate in view.candidates:
        rows.append(
            {
                "Method": candidate.display_name,
                "Execution": execution_status_label(candidate.execution_status),
                "Transform": transform_state_label(candidate.transform_plausible),
                "MAE": _display_number(_metric(candidate.descriptive_metrics, "mae")),
                "MSE": _display_number(_metric(candidate.descriptive_metrics, "mse")),
                "NCC": _display_number(_metric(candidate.descriptive_metrics, "ncc")),
                "SSIM": _display_number(_metric(candidate.descriptive_metrics, "ssim")),
                "Evaluation MI": _display_number(
                    _metric(candidate.descriptive_metrics, "evaluation_mi")
                ),
                "Valid overlap": _display_number(
                    _metric(candidate.overlap_metrics, "valid_overlap_fraction")
                ),
                "Runtime (ms)": _display_number(
                    _metric(candidate.runtime_metrics, "total_runtime_ms"), digits=2
                ),
            }
        )
    return rows


def execution_summary(view: AutomaticComparisonView) -> dict[str, int]:
    """Return explicit terminal-state counts, including zero-count states."""

    counts = {str(key): int(value) for key, value in view.status_counts.items()}
    return {
        "compatible": int(view.preview.compatible_count),
        "completed": counts.get("completed", 0),
        "check": counts.get("check", 0),
        "failed": counts.get("failed", 0),
        "validation_error": counts.get("validation_error", 0),
    }


def candidate_issue_rows(view: AutomaticComparisonView) -> list[dict[str, str]]:
    """Return CHECK, failure, validation, and warning details without dropping candidates."""

    rows: list[dict[str, str]] = []
    for candidate in view.candidates:
        has_issue = (
            candidate.execution_status != "completed"
            or candidate.failure_reason is not None
            or bool(candidate.warnings)
        )
        if not has_issue:
            continue
        rows.append(
            {
                "Method": candidate.display_name,
                "Execution": execution_status_label(candidate.execution_status),
                "Failure reason": candidate.failure_reason or "",
                "Warnings": " | ".join(str(item) for item in candidate.warnings),
            }
        )
    return rows


def candidate_by_id(
    view: AutomaticComparisonView,
) -> dict[str, CandidateComparisonView]:
    """Return deterministic candidate lookup for later presentation stages."""

    return {candidate.candidate_id: candidate for candidate in view.candidates}
