"""Framework-neutral view models for the Stage 6 automatic comparison UI.

The dataclasses in this module contain presentation-ready research evidence but
have no Streamlit dependency. They intentionally preserve the Week 6
scientific boundary: compatibility, candidate evidence, and transform
agreement may be displayed, while final ranking and calibrated confidence stay
deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from ui.core.contracts import ImageSource, PreprocessingSpec
from ui.core.enums import TransformModel


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class AutomaticComparisonRequest:
    """Input contract for one automatic comparison session."""

    fixed: ImageSource
    moving: ImageSource
    transform_model: TransformModel
    modality_class: str
    preprocessing: PreprocessingSpec = field(default_factory=PreprocessingSpec)
    include_optional_methods: bool = True


@dataclass(frozen=True, slots=True)
class MethodCompatibilityView:
    """One explicit method compatibility decision for presentation."""

    method_id: str
    display_name: str
    method_family: str
    transform_model: str
    optional: bool
    compatible: bool
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "display_name": self.display_name,
            "method_family": self.method_family,
            "transform_model": self.transform_model,
            "optional": self.optional,
            "compatible": self.compatible,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class CompatibilityPreviewView:
    """Compatibility preview produced before candidate execution."""

    pair_id: str
    image_shape: tuple[int, int]
    same_shape: bool
    modality_class: str
    transform_model: str
    ground_truth_status: str
    compatible: tuple[MethodCompatibilityView, ...]
    excluded: tuple[MethodCompatibilityView, ...]

    @property
    def compatible_count(self) -> int:
        return len(self.compatible)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "image_shape": list(self.image_shape),
            "same_shape": self.same_shape,
            "modality_class": self.modality_class,
            "transform_model": self.transform_model,
            "ground_truth_status": self.ground_truth_status,
            "compatible_count": self.compatible_count,
            "excluded_count": self.excluded_count,
            "compatible": [item.to_dict() for item in self.compatible],
            "excluded": [item.to_dict() for item in self.excluded],
        }


@dataclass(frozen=True, slots=True)
class CandidateComparisonView:
    """Presentation-ready normalized evidence for one registration candidate."""

    candidate_id: str
    method_id: str
    display_name: str
    method_family: str
    transform_model: str
    execution_status: str
    transform_plausible: bool | None
    estimated_transform: tuple[tuple[float, ...], ...] | None
    geometric_metrics: Mapping[str, float]
    anatomical_metrics: Mapping[str, float]
    descriptive_metrics: Mapping[str, float]
    overlap_metrics: Mapping[str, float]
    runtime_metrics: Mapping[str, float]
    timings_ms: Mapping[str, float]
    method_diagnostics: Mapping[str, Any]
    warnings: tuple[str, ...]
    failure_reason: str | None
    registered_output_available: bool

    @property
    def terminal_success(self) -> bool:
        return self.execution_status in {"completed", "check"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "method_id": self.method_id,
            "display_name": self.display_name,
            "method_family": self.method_family,
            "transform_model": self.transform_model,
            "execution_status": self.execution_status,
            "transform_plausible": self.transform_plausible,
            "estimated_transform": _json_safe(self.estimated_transform),
            "common_evidence": {
                "geometric": dict(self.geometric_metrics),
                "anatomical": dict(self.anatomical_metrics),
                "descriptive": dict(self.descriptive_metrics),
                "overlap": dict(self.overlap_metrics),
                "runtime": dict(self.runtime_metrics),
            },
            "timings_ms": dict(self.timings_ms),
            "method_diagnostics": _json_safe(dict(self.method_diagnostics)),
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
            "registered_output_available": self.registered_output_available,
        }


@dataclass(frozen=True, slots=True)
class PairwiseAgreementView:
    """One pairwise transform-space disagreement record."""

    candidate_a: str
    candidate_b: str
    method_a: str
    method_b: str
    display_name_a: str
    display_name_b: str
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
            "display_name_a": self.display_name_a,
            "display_name_b": self.display_name_b,
            "rms_px": self.rms_px,
            "median_px": self.median_px,
            "p95_px": self.p95_px,
            "max_px": self.max_px,
            "normalized_rms": self.normalized_rms,
        }


@dataclass(frozen=True, slots=True)
class CandidateAgreementView:
    """Per-candidate centrality information used only for descriptive consensus."""

    candidate_id: str
    method_id: str
    display_name: str
    comparisons: int
    median_pairwise_rms_px: float
    max_pairwise_rms_px: float
    median_normalized_rms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "method_id": self.method_id,
            "display_name": self.display_name,
            "comparisons": self.comparisons,
            "median_pairwise_rms_px": self.median_pairwise_rms_px,
            "max_pairwise_rms_px": self.max_pairwise_rms_px,
            "median_normalized_rms": self.median_normalized_rms,
        }


@dataclass(frozen=True, slots=True)
class AgreementComparisonView:
    """Presentation-ready transform agreement without a correctness claim."""

    status: str
    eligible_candidate_ids: tuple[str, ...]
    excluded_candidates: Mapping[str, tuple[str, ...]]
    pairwise: tuple[PairwiseAgreementView, ...]
    candidate_summaries: tuple[CandidateAgreementView, ...]
    consensus_anchor_candidate_id: str | None
    consensus_anchor_method_id: str | None
    consensus_anchor_display_name: str | None
    median_pairwise_rms_px: float | None
    max_pairwise_rms_px: float | None
    median_pairwise_normalized_rms: float | None
    interpretation: str

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_candidate_ids)

    @property
    def pairwise_count(self) -> int:
        return len(self.pairwise)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "eligible_count": self.eligible_count,
            "pairwise_count": self.pairwise_count,
            "eligible_candidate_ids": list(self.eligible_candidate_ids),
            "excluded_candidates": {
                key: list(value) for key, value in self.excluded_candidates.items()
            },
            "pairwise": [item.to_dict() for item in self.pairwise],
            "candidate_summaries": [item.to_dict() for item in self.candidate_summaries],
            "consensus_anchor": {
                "candidate_id": self.consensus_anchor_candidate_id,
                "method_id": self.consensus_anchor_method_id,
                "display_name": self.consensus_anchor_display_name,
                "interpretation": self.interpretation
                if self.consensus_anchor_candidate_id is not None
                else None,
            },
            "overall": {
                "median_pairwise_rms_px": self.median_pairwise_rms_px,
                "max_pairwise_rms_px": self.max_pairwise_rms_px,
                "median_pairwise_normalized_rms": self.median_pairwise_normalized_rms,
            },
            "final_recommendation": None,
        }


@dataclass(frozen=True, slots=True)
class AutomaticComparisonView:
    """Complete serializable Stage 6.1 result for future presentation layers."""

    preview: CompatibilityPreviewView
    candidates: tuple[CandidateComparisonView, ...]
    status_counts: Mapping[str, int]
    agreement: AgreementComparisonView
    recommendation_status: str
    ground_truth_status: str = "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": self.preview.to_dict(),
            "status_counts": dict(self.status_counts),
            "ground_truth_status": self.ground_truth_status,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "agreement": self.agreement.to_dict(),
            "recommendation": {
                "status": self.recommendation_status,
                "selected_candidate_id": None,
            },
        }
