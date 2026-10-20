"""Human-readable diagnostics and issue classification for candidate inspection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import AutomaticComparisonView, CandidateComparisonView


def _is_reference_notice(text: str) -> bool:
    lower = str(text).lower()
    return "ground truth" in lower and ("unavailable" in lower or "not reported" in lower)


def execution_issues(view: AutomaticComparisonView) -> list[dict[str, str]]:
    """Exclude routine unknown-ground-truth notices from execution issues."""
    rows: list[dict[str, str]] = []
    for candidate in view.candidates:
        substantive = [str(w) for w in candidate.warnings if not _is_reference_notice(str(w))]
        if candidate.execution_status == "completed" and candidate.failure_reason is None and not substantive and candidate.transform_plausible is not False:
            continue
        rows.append({"Method": candidate.display_name, "Execution": candidate.execution_status.replace("_", " ").title(),
                     "Failure reason": candidate.failure_reason or "", "Warnings": " | ".join(substantive)})
    return rows


def reference_limitations(view: AutomaticComparisonView) -> tuple[str, ...]:
    """Represent absent reference evidence once at comparison level."""
    if view.ground_truth_status == "unavailable":
        return ("Ground truth unavailable: TRE, parameter error and geometric PASS are not reported.",)
    return ()


def diagnostic_highlights(candidate: CandidateComparisonView, *, limit: int = 8) -> list[dict[str, str]]:
    """Select recorded scalar method diagnostics without inventing unavailable data."""
    terms = {
        "ecc": ("ecc", "converg", "iteration", "objective"),
        "mi": ("optimizer", "metric", "iteration", "valid", "stop", "converg"),
        "orb": ("keypoint", "match", "inlier", "residual", "coverage", "reprojection"),
        "sift": ("keypoint", "match", "inlier", "residual", "coverage", "reprojection"),
    }
    method = candidate.method_id.lower()
    group = next((key for key in terms if method.startswith(key)), "")
    allowed = terms.get(group, ("response", "valid", "objective", "iteration"))
    results: list[dict[str, str]] = []

    def walk(value: Any, path: str, depth: int) -> None:
        if len(results) >= limit or depth > 5:
            return
        if isinstance(value, Mapping):
            for key, sub in value.items():
                walk(sub, f"{path}.{key}" if path else str(key), depth + 1)
            return
        if isinstance(value, (bool, int, float, str)) and any(term in path.lower() for term in allowed):
            results.append({"Diagnostic": path, "Recorded value": str(value)})

    walk(candidate.method_diagnostics, "", 0)
    return results
