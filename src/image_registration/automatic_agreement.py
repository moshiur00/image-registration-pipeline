"""Transform-space agreement and robust Week 6 comparison summaries.

Day 30 adds a ground-truth-free comparison layer over the normalized automatic
candidate evidence introduced on Day 29. Candidate transforms are compared on a
shared control grid in image space. The resulting medoid is a descriptive
consensus anchor only; it is not a best-method recommendation.

Raw optimizer objectives remain method-specific diagnostics and are never used
as cross-method agreement scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .automatic_registration import (
    AutomaticRunResult,
    NormalizedCandidateEvidence,
)
from .evaluation_contracts import ExecutionStatus

AGREEMENT_SCHEMA_VERSION = "week06_transform_agreement_v1"


def _finite(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=np.float64).reshape(-1)
    return array[np.isfinite(array)]


def robust_numeric_summary(values: Iterable[float]) -> dict[str, float | int] | None:
    """Return count, median, MAD, and p95 for finite values.

    The MAD is the unscaled median absolute deviation. Returning ``None`` for an
    empty input keeps missing evidence explicit instead of inventing zeros.
    """
    array = _finite(values)
    if array.size == 0:
        return None
    median = float(np.median(array))
    return {
        "count": int(array.size),
        "median": median,
        "mad": float(np.median(np.abs(array - median))),
        "p95": float(np.percentile(array, 95.0)),
    }


def control_grid_2d(
    image_shape: Sequence[int],
    *,
    rows: int = 5,
    cols: int = 5,
    margin_fraction: float = 0.10,
) -> np.ndarray:
    """Create deterministic XY control points inside a 2D image.

    ``image_shape`` follows NumPy order ``(height, width)`` while points use the
    project coordinate convention ``(x, y)``.
    """
    if len(image_shape) < 2:
        raise ValueError("image_shape must provide height and width.")
    height = int(image_shape[0])
    width = int(image_shape[1])
    if height < 2 or width < 2:
        raise ValueError("image dimensions must be at least 2.")
    if rows < 2 or cols < 2:
        raise ValueError("rows and cols must each be at least 2.")
    if not 0.0 <= float(margin_fraction) < 0.5:
        raise ValueError("margin_fraction must be in [0, 0.5).")

    margin = float(margin_fraction)
    x0 = margin * (width - 1)
    x1 = (1.0 - margin) * (width - 1)
    y0 = margin * (height - 1)
    y1 = (1.0 - margin) * (height - 1)

    xs = np.linspace(x0, x1, int(cols), dtype=np.float64)
    ys = np.linspace(y0, y1, int(rows), dtype=np.float64)
    xx, yy = np.meshgrid(xs, ys)
    return np.column_stack([xx.reshape(-1), yy.reshape(-1)])


def _apply_homogeneous_2d(transform: np.ndarray, points_xy: np.ndarray) -> np.ndarray:
    matrix = np.asarray(transform, dtype=np.float64)
    points = np.asarray(points_xy, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError("Day 30 image-space disagreement currently requires a 3x3 2D transform.")
    if points.ndim != 2 or points.shape[1] != 2 or points.shape[0] == 0:
        raise ValueError("points_xy must have shape (N, 2) with N > 0.")
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(points)):
        raise ValueError("Transforms and control points must contain finite values.")

    homogeneous = np.column_stack([points, np.ones(points.shape[0], dtype=np.float64)])
    mapped_h = (matrix @ homogeneous.T).T
    denom = mapped_h[:, 2]
    if np.any(np.isclose(denom, 0.0)):
        raise ValueError("Transform maps at least one control point to infinity.")
    return mapped_h[:, :2] / denom[:, None]


@dataclass(frozen=True)
class PairwiseTransformDisagreement:
    """Image-space disagreement between two candidate transforms."""

    candidate_a: str
    candidate_b: str
    method_a: str
    method_b: str
    rms_px: float
    median_px: float
    p95_px: float
    max_px: float
    normalized_rms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_a": self.candidate_a,
            "candidate_b": self.candidate_b,
            "method_a": self.method_a,
            "method_b": self.method_b,
            "rms_px": self.rms_px,
            "median_px": self.median_px,
            "p95_px": self.p95_px,
            "max_px": self.max_px,
            "normalized_rms": self.normalized_rms,
        }


def transform_disagreement_2d(
    candidate_a: NormalizedCandidateEvidence,
    candidate_b: NormalizedCandidateEvidence,
    *,
    control_points_xy: np.ndarray,
    image_shape: Sequence[int],
) -> PairwiseTransformDisagreement:
    """Compare two Moving-to-Fixed transforms on the same control points."""
    if candidate_a.estimated_transform is None or candidate_b.estimated_transform is None:
        raise ValueError("Both candidates must provide an estimated transform.")
    if candidate_a.transform_model != candidate_b.transform_model:
        raise ValueError("Candidates must use the same transform model for direct disagreement.")
    if candidate_a.pair_id != candidate_b.pair_id:
        raise ValueError("Candidates must belong to the same image pair.")

    mapped_a = _apply_homogeneous_2d(candidate_a.estimated_transform, control_points_xy)
    mapped_b = _apply_homogeneous_2d(candidate_b.estimated_transform, control_points_xy)
    distances = np.linalg.norm(mapped_a - mapped_b, axis=1)

    height = int(image_shape[0])
    width = int(image_shape[1])
    diagonal = hypot(max(1, width - 1), max(1, height - 1))
    rms = float(np.sqrt(np.mean(np.square(distances))))
    return PairwiseTransformDisagreement(
        candidate_a=candidate_a.candidate_id,
        candidate_b=candidate_b.candidate_id,
        method_a=candidate_a.method_id,
        method_b=candidate_b.method_id,
        rms_px=rms,
        median_px=float(np.median(distances)),
        p95_px=float(np.percentile(distances, 95.0)),
        max_px=float(np.max(distances)),
        normalized_rms=float(rms / diagonal),
    )


@dataclass(frozen=True)
class CandidateAgreementSummary:
    candidate_id: str
    method_id: str
    comparisons: int
    median_pairwise_rms_px: float
    max_pairwise_rms_px: float
    median_normalized_rms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "method_id": self.method_id,
            "comparisons": self.comparisons,
            "median_pairwise_rms_px": self.median_pairwise_rms_px,
            "max_pairwise_rms_px": self.max_pairwise_rms_px,
            "median_normalized_rms": self.median_normalized_rms,
        }


@dataclass(frozen=True)
class PreliminaryConsensusView:
    """Ground-truth-free transform agreement view.

    The consensus anchor is the transform medoid, meaning the candidate with the
    smallest median pairwise RMS displacement. It is a geometric reference for
    inspecting agreement, not an evidence-backed method recommendation.
    """

    pair_id: str
    eligible_candidate_ids: tuple[str, ...]
    excluded_candidates: Mapping[str, tuple[str, ...]]
    pairwise: tuple[PairwiseTransformDisagreement, ...]
    candidate_summaries: tuple[CandidateAgreementSummary, ...]
    consensus_anchor_candidate_id: str | None
    consensus_anchor_method_id: str | None
    median_pairwise_rms_px: float | None
    max_pairwise_rms_px: float | None
    median_pairwise_normalized_rms: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AGREEMENT_SCHEMA_VERSION,
            "pair_id": self.pair_id,
            "status": self.status,
            "eligible_candidate_ids": list(self.eligible_candidate_ids),
            "excluded_candidates": {
                candidate_id: list(reasons)
                for candidate_id, reasons in self.excluded_candidates.items()
            },
            "pairwise": [item.to_dict() for item in self.pairwise],
            "candidate_summaries": [item.to_dict() for item in self.candidate_summaries],
            "consensus_anchor": {
                "candidate_id": self.consensus_anchor_candidate_id,
                "method_id": self.consensus_anchor_method_id,
                "interpretation": (
                    "Transform medoid for descriptive agreement only. "
                    "This is not a best-method recommendation."
                    if self.consensus_anchor_candidate_id is not None
                    else None
                ),
            },
            "overall": {
                "median_pairwise_rms_px": self.median_pairwise_rms_px,
                "max_pairwise_rms_px": self.max_pairwise_rms_px,
                "median_pairwise_normalized_rms": self.median_pairwise_normalized_rms,
            },
            "final_recommendation": None,
        }


def _candidate_exclusion_reasons(candidate: NormalizedCandidateEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.execution_status not in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}:
        reasons.append(f"terminal_status_{candidate.execution_status.value}")
    if candidate.estimated_transform is None:
        reasons.append("missing_transform")
    if candidate.transform_plausible is False:
        reasons.append("implausible_transform")
    return tuple(reasons)


def build_preliminary_consensus(
    run: AutomaticRunResult,
    *,
    image_shape: Sequence[int],
    grid_rows: int = 5,
    grid_cols: int = 5,
    margin_fraction: float = 0.10,
) -> PreliminaryConsensusView:
    """Build pairwise transform agreement without using ground truth."""
    eligible: list[NormalizedCandidateEvidence] = []
    excluded: dict[str, tuple[str, ...]] = {}
    for candidate in run.candidates:
        reasons = _candidate_exclusion_reasons(candidate)
        if reasons:
            excluded[candidate.candidate_id] = reasons
        else:
            eligible.append(candidate)

    eligible.sort(key=lambda item: item.candidate_id)
    if len(eligible) < 2:
        return PreliminaryConsensusView(
            pair_id=run.pair.pair_id,
            eligible_candidate_ids=tuple(item.candidate_id for item in eligible),
            excluded_candidates=excluded,
            pairwise=(),
            candidate_summaries=(),
            consensus_anchor_candidate_id=None,
            consensus_anchor_method_id=None,
            median_pairwise_rms_px=None,
            max_pairwise_rms_px=None,
            median_pairwise_normalized_rms=None,
            status="insufficient_candidates",
        )

    models = {item.transform_model for item in eligible}
    if len(models) != 1:
        raise ValueError(
            "Preliminary consensus requires candidates using one common transform model."
        )

    points = control_grid_2d(
        image_shape,
        rows=grid_rows,
        cols=grid_cols,
        margin_fraction=margin_fraction,
    )

    pairwise: list[PairwiseTransformDisagreement] = []
    by_candidate: dict[str, list[PairwiseTransformDisagreement]] = {
        item.candidate_id: [] for item in eligible
    }
    for index, candidate_a in enumerate(eligible):
        for candidate_b in eligible[index + 1 :]:
            item = transform_disagreement_2d(
                candidate_a,
                candidate_b,
                control_points_xy=points,
                image_shape=image_shape,
            )
            pairwise.append(item)
            by_candidate[candidate_a.candidate_id].append(item)
            by_candidate[candidate_b.candidate_id].append(item)

    summaries: list[CandidateAgreementSummary] = []
    method_by_id = {item.candidate_id: item.method_id for item in eligible}
    for candidate in eligible:
        rows = by_candidate[candidate.candidate_id]
        rms_values = np.asarray([item.rms_px for item in rows], dtype=np.float64)
        normalized_values = np.asarray(
            [item.normalized_rms for item in rows],
            dtype=np.float64,
        )
        summaries.append(
            CandidateAgreementSummary(
                candidate_id=candidate.candidate_id,
                method_id=candidate.method_id,
                comparisons=len(rows),
                median_pairwise_rms_px=float(np.median(rms_values)),
                max_pairwise_rms_px=float(np.max(rms_values)),
                median_normalized_rms=float(np.median(normalized_values)),
            )
        )

    summaries.sort(
        key=lambda item: (
            item.median_pairwise_rms_px,
            item.max_pairwise_rms_px,
            item.candidate_id,
        )
    )
    anchor = summaries[0]
    rms_all = np.asarray([item.rms_px for item in pairwise], dtype=np.float64)
    normalized_all = np.asarray(
        [item.normalized_rms for item in pairwise],
        dtype=np.float64,
    )

    return PreliminaryConsensusView(
        pair_id=run.pair.pair_id,
        eligible_candidate_ids=tuple(item.candidate_id for item in eligible),
        excluded_candidates=excluded,
        pairwise=tuple(pairwise),
        candidate_summaries=tuple(summaries),
        consensus_anchor_candidate_id=anchor.candidate_id,
        consensus_anchor_method_id=method_by_id[anchor.candidate_id],
        median_pairwise_rms_px=float(np.median(rms_all)),
        max_pairwise_rms_px=float(np.max(rms_all)),
        median_pairwise_normalized_rms=float(np.median(normalized_all)),
        status="available",
    )


def summarize_methods(
    runs: Sequence[AutomaticRunResult],
) -> list[dict[str, Any]]:
    """Create robust operation-time summaries by modality and method.

    Only normalized common evidence is aggregated. Method-specific diagnostics
    are deliberately excluded from cross-method summaries.
    """
    grouped: dict[tuple[str, str, str], list[NormalizedCandidateEvidence]] = {}
    for run in runs:
        for candidate in run.candidates:
            key = (run.pair.modality_class, candidate.method_id, candidate.method_family)
            grouped.setdefault(key, []).append(candidate)

    rows: list[dict[str, Any]] = []
    for (modality_class, method_id, method_family), candidates in sorted(grouped.items()):
        status_counts = {status.value: 0 for status in ExecutionStatus}
        for candidate in candidates:
            status_counts[candidate.execution_status.value] += 1

        terminal = [candidate for candidate in candidates if candidate.terminal_success]
        plausible = [candidate for candidate in terminal if candidate.transform_plausible is True]

        metric_values: dict[str, list[float]] = {}
        for candidate in candidates:
            common_groups = (
                candidate.geometric_metrics,
                candidate.anatomical_metrics,
                candidate.descriptive_metrics,
                candidate.overlap_metrics,
                candidate.runtime_metrics,
            )
            for group in common_groups:
                for name, value in group.items():
                    metric_values.setdefault(name, []).append(float(value))

        common_summaries = {
            name: summary
            for name, values in sorted(metric_values.items())
            if (summary := robust_numeric_summary(values)) is not None
        }

        attempts = len(candidates)
        terminal_count = len(terminal)
        rows.append(
            {
                "modality_class": modality_class,
                "method_id": method_id,
                "method_family": method_family,
                "attempts": attempts,
                "status_counts": status_counts,
                "terminal_success_rate": terminal_count / attempts if attempts else 0.0,
                "plausible_rate_among_terminal": (
                    len(plausible) / terminal_count if terminal_count else None
                ),
                "common_metric_summaries": common_summaries,
                "raw_optimizer_objectives_aggregated": False,
            }
        )
    return rows


def summarize_stage_runtimes(
    runs: Sequence[AutomaticRunResult],
) -> dict[str, dict[str, float | int]]:
    """Summarize available stage timing fields across all candidates."""
    values: dict[str, list[float]] = {}
    for run in runs:
        for candidate in run.candidates:
            for name, value in candidate.timings_ms.items():
                values.setdefault(str(name), []).append(float(value))

    summaries: dict[str, dict[str, float | int]] = {}
    for name, rows in sorted(values.items()):
        summary = robust_numeric_summary(rows)
        if summary is not None:
            summaries[name] = summary
    return summaries
