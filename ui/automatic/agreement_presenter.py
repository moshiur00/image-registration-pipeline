"""Framework-neutral Stage 6.4 views of frozen Week 6 transform agreement.

All values come from AgreementComparisonView. This module does not estimate
transforms, compute agreement, rank methods, or apply calibration thresholds.
"""

from __future__ import annotations

from typing import Any
import math

from .models import AutomaticComparisonView


AGREEMENT_EXPLANATION = (
    "Disagreement is measured by applying Moving -> Fixed transforms to the "
    "same image-space control grid. Values are in fixed-image pixels. Agreement "
    "between methods is descriptive and does not prove geometric correctness."
)

ANCHOR_EXPLANATION = (
    "The descriptive consensus anchor is the transform medoid, meaning the "
    "most central eligible transform under the current comparison. It is not "
    "a selected winner, a quality ranking, or a best-method recommendation."
)


def agreement_overview(view: AutomaticComparisonView) -> dict[str, Any]:
    """Summarize eligibility and frozen agreement results without interpretation thresholds."""
    agreement = view.agreement
    available = agreement.status == "available" and agreement.eligible_count >= 2
    anchor_view = descriptive_anchor_interpretation(view)
    anchor = anchor_view["unique_anchor"]
    return {
        "status": agreement.status,
        "eligible": agreement.eligible_count,
        "excluded": len(agreement.excluded_candidates),
        "pairwise_comparisons": agreement.pairwise_count,
        "median_rms_px": agreement.median_pairwise_rms_px if available else None,
        "maximum_rms_px": agreement.max_pairwise_rms_px if available else None,
        "normalized_median_rms": agreement.median_pairwise_normalized_rms if available else None,
        "anchor": anchor,
        "anchor_state": anchor_view["status"],
        "anchor_explanation": anchor_view["explanation"],
        "tied_candidates": anchor_view["tied_candidates"],
    }


def descriptive_anchor_interpretation(view: AutomaticComparisonView) -> dict[str, Any]:
    """Explain backend medoid determinism without claiming unique consensus.

    The backend contract and its tie-breaker remain intact. Equal median
    pairwise RMS values count as tied centrality, even if a secondary backend
    ordering chooses a deterministic medoid. No disagreement cutoff is used.
    """
    agreement = view.agreement
    raw_anchor = agreement.consensus_anchor_candidate_id
    result: dict[str, Any] = {
        "status": "insufficient_candidates",
        "unique_anchor": None,
        "tied_candidates": [],
        "backend_medoid_candidate_id": raw_anchor,
        "backend_medoid_display_name": agreement.consensus_anchor_display_name,
        "explanation": "Insufficient eligible transforms for pairwise agreement. No descriptive consensus anchor is assigned.",
    }
    if agreement.status != "available" or agreement.eligible_count < 2:
        return result
    if agreement.eligible_count == 2:
        result.update(
            status="two_candidate_tie",
            tied_candidates=[item.candidate_id for item in agreement.candidate_summaries],
            explanation=(
                "No unique descriptive consensus anchor. Two eligible transforms "
                "necessarily have equal pairwise centrality; the backend medoid "
                "is a deterministic tie-break, not independent consensus evidence."
            ),
        )
        return result
    # Compute uniqueness using unrounded primary medoid centrality, not UI table values.
    summaries = [
        item for item in agreement.candidate_summaries
        if item.candidate_id in agreement.eligible_candidate_ids
        and math.isfinite(item.median_pairwise_rms_px)
    ]
    if len(summaries) != agreement.eligible_count:
        result.update(
            status="incomplete_centrality",
            explanation="Centrality evidence is incomplete; no unique descriptive anchor can be established.",
        )
        return result
    smallest = min(item.median_pairwise_rms_px for item in summaries)
    tied = [item for item in summaries if math.isclose(item.median_pairwise_rms_px, smallest, rel_tol=1e-12, abs_tol=1e-12)]
    if len(tied) > 1:
        result.update(
            status="centrality_tie",
            tied_candidates=[item.candidate_id for item in tied],
            explanation=(
                "No unique descriptive consensus anchor. Multiple eligible transforms "
                "have equal minimum median pairwise RMS centrality; the backend "
                "medoid reflects a deterministic tie-break only."
            ),
        )
        return result
    unique_id = tied[0].candidate_id
    label = next((c.display_name for c in view.candidates if c.candidate_id == unique_id), unique_id)
    result.update(
        status="unique_descriptive_anchor",
        unique_anchor=label,
        explanation=(
            "Unique minimum median pairwise RMS among eligible transforms. "
            "This descriptive centrality is not a method recommendation or correctness claim."
        ),
    )
    return result


def _candidate_labels(view: AutomaticComparisonView) -> dict[str, str]:
    """Disambiguate method labels without relying on their candidate IDs as names."""
    eligible = set(view.agreement.eligible_candidate_ids)
    candidates = [candidate for candidate in view.candidates if candidate.candidate_id in eligible]
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.display_name] = counts.get(candidate.display_name, 0) + 1
    return {
        candidate.candidate_id: (
            candidate.display_name
            if counts[candidate.display_name] == 1
            else f"{candidate.display_name} ({candidate.method_id})"
        )
        for candidate in candidates
    }


def disagreement_matrix_rows(view: AutomaticComparisonView) -> list[dict[str, Any]]:
    """Build a symmetric RMS-pixel matrix for eligible candidates in service order.

    Missing pairwise records remain None instead of being represented as zero.
    An insufficient-candidates result returns no matrix.
    """
    agreement = view.agreement
    if agreement.status != "available" or agreement.eligible_count < 2:
        return []
    labels = _candidate_labels(view)
    eligible_ids = tuple(agreement.eligible_candidate_ids)
    pair_values: dict[tuple[str, str], float] = {}
    for pair in agreement.pairwise:
        if pair.candidate_a in labels and pair.candidate_b in labels:
            pair_values[(pair.candidate_a, pair.candidate_b)] = float(pair.rms_px)
            pair_values[(pair.candidate_b, pair.candidate_a)] = float(pair.rms_px)
    rows: list[dict[str, Any]] = []
    for source_id in eligible_ids:
        row: dict[str, Any] = {"Candidate": labels[source_id]}
        for destination_id in eligible_ids:
            if destination_id == source_id:
                row[labels[destination_id]] = 0.0
            else:
                value = pair_values.get((source_id, destination_id))
                row[labels[destination_id]] = None if value is None else round(value, 3)
        rows.append(row)
    return rows


def pairwise_disagreement_rows(view: AutomaticComparisonView) -> list[dict[str, Any]]:
    """Show all available backend metrics without converting them to scores."""
    if view.agreement.status != "available":
        return []
    return [
        {
            "Candidate A": item.display_name_a,
            "Candidate B": item.display_name_b,
            "RMS (px)": round(float(item.rms_px), 4),
            "Median (px)": round(float(item.median_px), 4),
            "p95 (px)": round(float(item.p95_px), 4),
            "Maximum (px)": round(float(item.max_px), 4),
            "Normalized RMS": round(float(item.normalized_rms), 6),
        }
        for item in view.agreement.pairwise
    ]


def candidate_agreement_rows(view: AutomaticComparisonView) -> list[dict[str, Any]]:
    """Return unranked, backend-ordered candidate centrality evidence."""
    summaries = {
        summary.candidate_id: summary for summary in view.agreement.candidate_summaries
    }
    rows: list[dict[str, Any]] = []
    for candidate in view.candidates:
        summary = summaries.get(candidate.candidate_id)
        if summary is None:
            continue
        rows.append(
            {
                "Method": candidate.display_name,
                "Comparisons": int(summary.comparisons),
                "Median pairwise RMS (px)": round(float(summary.median_pairwise_rms_px), 4),
                "Maximum pairwise RMS (px)": round(float(summary.max_pairwise_rms_px), 4),
            }
        )
    return rows


def agreement_exclusion_rows(view: AutomaticComparisonView) -> list[dict[str, str]]:
    """Preserve explicit exclusion reasons for failed and implausible candidates."""
    candidates = {candidate.candidate_id: candidate for candidate in view.candidates}
    return [
        {
            "Method": candidates[candidate_id].display_name
            if candidate_id in candidates else candidate_id,
            "Reason": "; ".join(str(reason) for reason in reasons),
        }
        for candidate_id, reasons in view.agreement.excluded_candidates.items()
    ]
