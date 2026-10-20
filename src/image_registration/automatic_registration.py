"""Framework-neutral automatic multi-method execution foundation.

Day 29 introduces candidate compatibility filtering and common evidence
normalization without implementing a final recommendation policy. The module
does not compare raw optimizer objectives across method families. Method-
specific diagnostics remain available for inspection, while comparable evidence
is restricted to the unified Week 6 metric contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .evaluation_contracts import (
    METRIC_DEFINITIONS,
    ExecutionStatus,
    MetricRole,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)

AUTO_RUN_SCHEMA_VERSION = "week06_auto_run_v1"
AUTO_CANDIDATE_IDENTITY_VERSION = "week06_auto_candidate_v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True)
class AutoPairProfile:
    """Method-selection information available before candidate execution."""

    pair_id: str
    dimensions: int
    modality_class: str
    candidate_transform_models: tuple[str, ...]
    same_shape: bool = True
    reference: ReferenceEvidence = field(default_factory=ReferenceEvidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        pair_id = str(self.pair_id).strip()
        modality = str(self.modality_class).strip().lower()
        models = tuple(str(value).strip().lower() for value in self.candidate_transform_models)
        if not pair_id:
            raise ValueError("pair_id must be non-empty.")
        if int(self.dimensions) not in {2, 3}:
            raise ValueError("dimensions must be 2 or 3.")
        if not modality:
            raise ValueError("modality_class must be non-empty.")
        if not models or any(not value for value in models):
            raise ValueError("candidate_transform_models must contain non-empty values.")
        object.__setattr__(self, "pair_id", pair_id)
        object.__setattr__(self, "dimensions", int(self.dimensions))
        object.__setattr__(self, "modality_class", modality)
        object.__setattr__(self, "candidate_transform_models", models)
        object.__setattr__(self, "same_shape", bool(self.same_shape))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class AutoMethodSpec:
    """One registration configuration eligible for automatic orchestration."""

    method_id: str
    display_name: str
    method_family: str
    transform_model: str
    dimensions: frozenset[int]
    supported_modality_classes: frozenset[str] | None = None
    requires_same_shape: bool = False
    optional: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("method_id", "display_name", "method_family", "transform_model"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty.")
            object.__setattr__(self, name, value)
        dimensions = frozenset(int(value) for value in self.dimensions)
        if not dimensions or not dimensions.issubset({2, 3}):
            raise ValueError("dimensions must be a non-empty subset of {2, 3}.")
        object.__setattr__(self, "dimensions", dimensions)
        if self.supported_modality_classes is not None:
            modalities = frozenset(
                str(value).strip().lower() for value in self.supported_modality_classes
            )
            if not modalities or any(not value for value in modalities):
                raise ValueError(
                    "supported_modality_classes must contain non-empty values when supplied."
                )
            object.__setattr__(self, "supported_modality_classes", modalities)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def compatibility_reasons(
        self,
        pair: AutoPairProfile,
        *,
        include_optional: bool,
    ) -> tuple[str, ...]:
        """Return explicit exclusion reasons, or an empty tuple when compatible."""
        reasons: list[str] = []
        if pair.dimensions not in self.dimensions:
            reasons.append("dimension_mismatch")
        if self.transform_model.lower() not in pair.candidate_transform_models:
            reasons.append("transform_model_not_requested")
        if (
            self.supported_modality_classes is not None
            and pair.modality_class not in self.supported_modality_classes
        ):
            reasons.append("modality_class_not_supported")
        if self.requires_same_shape and not pair.same_shape:
            reasons.append("shape_mismatch")
        if self.optional and not include_optional:
            reasons.append("optional_method_disabled")
        return tuple(reasons)


@dataclass(frozen=True)
class CandidateCompatibility:
    """Compatibility decision retained for auditability."""

    method_id: str
    compatible: bool
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "compatible": self.compatible,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class AutoCandidateTask:
    """One compatible candidate execution request."""

    pair: AutoPairProfile
    method: AutoMethodSpec

    @property
    def candidate_id(self) -> str:
        payload = {
            "identity_version": AUTO_CANDIDATE_IDENTITY_VERSION,
            "pair_id": self.pair.pair_id,
            "dimensions": self.pair.dimensions,
            "modality_class": self.pair.modality_class,
            "candidate_transform_models": list(self.pair.candidate_transform_models),
            "same_shape": self.pair.same_shape,
            "method_id": self.method.method_id,
            "method_family": self.method.method_family,
            "transform_model": self.method.transform_model,
            "method_metadata": dict(self.method.metadata),
        }
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        return f"auto-{digest[:20]}"


@dataclass(frozen=True)
class NormalizedCandidateEvidence:
    """Comparable evidence plus opaque method-specific diagnostics."""

    candidate_id: str
    pair_id: str
    method_id: str
    display_name: str
    method_family: str
    transform_model: str
    execution_status: ExecutionStatus
    transform_plausible: bool | None
    geometric_within_tolerance: bool | None
    estimated_transform: np.ndarray | None
    geometric_metrics: Mapping[str, float]
    anatomical_metrics: Mapping[str, float]
    descriptive_metrics: Mapping[str, float]
    overlap_metrics: Mapping[str, float]
    runtime_metrics: Mapping[str, float]
    timings_ms: Mapping[str, float]
    method_diagnostics: Mapping[str, Any]
    warnings: tuple[str, ...]
    failure_reason: str | None

    @property
    def terminal_success(self) -> bool:
        return self.execution_status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "pair_id": self.pair_id,
            "method_id": self.method_id,
            "display_name": self.display_name,
            "method_family": self.method_family,
            "transform_model": self.transform_model,
            "execution_status": self.execution_status.value,
            "transform_plausible": self.transform_plausible,
            "geometric_within_tolerance": self.geometric_within_tolerance,
            "estimated_transform": (
                None
                if self.estimated_transform is None
                else np.asarray(self.estimated_transform, dtype=np.float64).tolist()
            ),
            "common_evidence": {
                "geometric": dict(self.geometric_metrics),
                "anatomical": dict(self.anatomical_metrics),
                "descriptive": dict(self.descriptive_metrics),
                "overlap": dict(self.overlap_metrics),
                "runtime": dict(self.runtime_metrics),
            },
            "timings_ms": dict(self.timings_ms),
            "method_diagnostics": _jsonable(dict(self.method_diagnostics)),
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
        }


def normalize_candidate_record(
    task: AutoCandidateTask,
    record: UnifiedEvaluationRecord,
) -> NormalizedCandidateEvidence:
    """Normalize one candidate using only the common Week 6 metric catalog."""
    if record.pair_id != task.pair.pair_id:
        raise ValueError("Candidate record pair_id does not match the automatic task.")
    if record.method_id != task.method.method_id:
        raise ValueError("Candidate record method_id does not match the automatic task.")
    if record.method_family != task.method.method_family:
        raise ValueError("Candidate record method_family does not match the automatic task.")
    if record.transform_model != task.method.transform_model:
        raise ValueError("Candidate record transform_model does not match the automatic task.")
    if record.modality_class != task.pair.modality_class:
        raise ValueError("Candidate record modality_class does not match the automatic task.")
    if record.dimensions != task.pair.dimensions:
        raise ValueError("Candidate record dimensionality does not match the automatic task.")
    if record.reference != task.pair.reference:
        raise ValueError(
            "Candidate record reference evidence does not match the automatic task. "
            "Automatic execution must not gain hidden ground-truth evidence."
        )

    grouped: dict[MetricRole, dict[str, float]] = {
        role: {} for role in MetricRole
    }
    for key, value in record.metrics.items():
        definition = METRIC_DEFINITIONS[key]
        grouped[definition.role][key] = float(value)

    return NormalizedCandidateEvidence(
        candidate_id=task.candidate_id,
        pair_id=record.pair_id,
        method_id=record.method_id,
        display_name=task.method.display_name,
        method_family=record.method_family,
        transform_model=record.transform_model,
        execution_status=record.execution_status,
        transform_plausible=record.transform_plausible,
        geometric_within_tolerance=record.geometric_within_tolerance,
        estimated_transform=(
            None
            if record.estimated_transform is None
            else np.asarray(record.estimated_transform, dtype=np.float64).copy()
        ),
        geometric_metrics=grouped[MetricRole.GEOMETRIC_ERROR],
        anatomical_metrics=grouped[MetricRole.ANATOMICAL_OVERLAP],
        descriptive_metrics=grouped[MetricRole.DESCRIPTIVE_SIMILARITY],
        overlap_metrics=grouped[MetricRole.VALID_OVERLAP],
        runtime_metrics=grouped[MetricRole.RUNTIME],
        timings_ms=dict(record.timings_ms),
        method_diagnostics=dict(record.method_diagnostics),
        warnings=tuple(record.warnings),
        failure_reason=record.failure_reason,
    )


@dataclass(frozen=True)
class AutomaticRunResult:
    """All automatic-run evidence without a final recommendation."""

    pair: AutoPairProfile
    candidates: tuple[NormalizedCandidateEvidence, ...]
    compatibility: tuple[CandidateCompatibility, ...]
    recommendation_status: str = "deferred_until_robustness_calibration"

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ExecutionStatus}
        for candidate in self.candidates:
            counts[candidate.execution_status.value] += 1
        return counts

    @property
    def compatible_method_ids(self) -> tuple[str, ...]:
        return tuple(candidate.method_id for candidate in self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AUTO_RUN_SCHEMA_VERSION,
            "pair": {
                "pair_id": self.pair.pair_id,
                "dimensions": self.pair.dimensions,
                "modality_class": self.pair.modality_class,
                "candidate_transform_models": list(self.pair.candidate_transform_models),
                "same_shape": self.pair.same_shape,
                "reference": {
                    "exact_transform": self.pair.reference.exact_transform,
                    "landmarks": self.pair.reference.landmarks,
                    "masks": self.pair.reference.masks,
                    "physical_spacing": self.pair.reference.physical_spacing,
                    "label": self.pair.reference.label,
                },
                "metadata": _jsonable(dict(self.pair.metadata)),
            },
            "compatibility": [item.to_dict() for item in self.compatibility],
            "candidate_count": len(self.candidates),
            "status_counts": self.status_counts,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "recommendation": {
                "status": self.recommendation_status,
                "selected_candidate_id": None,
                "reason": (
                    "Day 29 executes and normalizes compatible candidates only. "
                    "Evidence-backed ranking is deferred until robustness calibration."
                ),
            },
        }


CandidateExecutor = Callable[[AutoCandidateTask], UnifiedEvaluationRecord]


class AutomaticMultiMethodService:
    """Select compatible candidates, execute all of them, and preserve evidence."""

    def __init__(
        self,
        methods: Sequence[AutoMethodSpec],
        executor: CandidateExecutor,
        *,
        include_optional: bool = True,
    ) -> None:
        if not methods:
            raise ValueError("methods must not be empty.")
        ids = [method.method_id for method in methods]
        if len(ids) != len(set(ids)):
            raise ValueError("Automatic method catalog contains duplicate method IDs.")
        self._methods = tuple(sorted(methods, key=lambda item: item.method_id))
        self._executor = executor
        self._include_optional = bool(include_optional)

    def compatibility(self, pair: AutoPairProfile) -> tuple[CandidateCompatibility, ...]:
        decisions: list[CandidateCompatibility] = []
        for method in self._methods:
            reasons = method.compatibility_reasons(
                pair,
                include_optional=self._include_optional,
            )
            decisions.append(
                CandidateCompatibility(
                    method_id=method.method_id,
                    compatible=not reasons,
                    reasons=reasons,
                )
            )
        return tuple(decisions)

    @staticmethod
    def _failure_record(
        task: AutoCandidateTask,
        *,
        status: ExecutionStatus,
        reason: str,
    ) -> UnifiedEvaluationRecord:
        return UnifiedEvaluationRecord(
            pair_id=task.pair.pair_id,
            method_id=task.method.method_id,
            method_family=task.method.method_family,
            transform_model=task.method.transform_model,
            modality_class=task.pair.modality_class,
            dimensions=task.pair.dimensions,
            execution_status=status,
            reference=task.pair.reference,
            valid_overlap_fraction=None,
            estimated_transform=None,
            transform_plausible=None,
            geometric_within_tolerance=None,
            metrics={},
            timings_ms={},
            method_diagnostics={},
            warnings=[],
            failure_reason=reason,
        )

    def run(self, pair: AutoPairProfile) -> AutomaticRunResult:
        decisions = self.compatibility(pair)
        compatible_ids = {
            item.method_id for item in decisions if item.compatible
        }
        if not compatible_ids:
            raise ValueError(
                f"Pair '{pair.pair_id}' has no compatible automatic registration candidates."
            )

        candidates: list[NormalizedCandidateEvidence] = []
        for method in self._methods:
            if method.method_id not in compatible_ids:
                continue
            task = AutoCandidateTask(pair=pair, method=method)
            try:
                record = self._executor(task)
                if not isinstance(record, UnifiedEvaluationRecord):
                    raise TypeError(
                        "Automatic candidate executor must return UnifiedEvaluationRecord."
                    )
                normalized = normalize_candidate_record(task, record)
            except (TypeError, ValueError) as exc:
                record = self._failure_record(
                    task,
                    status=ExecutionStatus.VALIDATION_ERROR,
                    reason=f"auto_validation_error: {type(exc).__name__}: {exc}",
                )
                normalized = normalize_candidate_record(task, record)
            except Exception as exc:
                record = self._failure_record(
                    task,
                    status=ExecutionStatus.FAILED,
                    reason=f"auto_executor_exception: {type(exc).__name__}: {exc}",
                )
                normalized = normalize_candidate_record(task, record)
            candidates.append(normalized)

        return AutomaticRunResult(
            pair=pair,
            candidates=tuple(candidates),
            compatibility=decisions,
        )
