from __future__ import annotations

import numpy as np
import pytest

from image_registration.automatic_registration import (
    AutoCandidateTask,
    AutoMethodSpec,
    AutoPairProfile,
    AutomaticMultiMethodService,
    normalize_candidate_record,
)
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)


def _pair(**overrides):
    values = {
        "pair_id": "pair-1",
        "dimensions": 2,
        "modality_class": "monomodal",
        "candidate_transform_models": ("affine",),
        "same_shape": True,
        "reference": ReferenceEvidence(),
    }
    values.update(overrides)
    return AutoPairProfile(**values)


def _method(method_id: str = "ecc_affine", **overrides):
    values = {
        "method_id": method_id,
        "display_name": method_id,
        "method_family": "intensity_based",
        "transform_model": "affine",
        "dimensions": frozenset({2}),
        "supported_modality_classes": frozenset({"monomodal"}),
        "requires_same_shape": True,
    }
    values.update(overrides)
    return AutoMethodSpec(**values)


def _record(
    task: AutoCandidateTask,
    *,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    plausible: bool | None = True,
    metrics: dict[str, float] | None = None,
    diagnostics: dict[str, object] | None = None,
    failure_reason: str | None = None,
):
    return UnifiedEvaluationRecord(
        pair_id=task.pair.pair_id,
        method_id=task.method.method_id,
        method_family=task.method.method_family,
        transform_model=task.method.transform_model,
        modality_class=task.pair.modality_class,
        dimensions=task.pair.dimensions,
        execution_status=status,
        reference=task.pair.reference,
        valid_overlap_fraction=0.8 if metrics else None,
        estimated_transform=np.eye(3) if status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK} else None,
        transform_plausible=plausible,
        geometric_within_tolerance=None,
        metrics=metrics or {},
        timings_ms={"total": 12.5},
        method_diagnostics=diagnostics or {},
        warnings=["example_warning"] if status is ExecutionStatus.CHECK else [],
        failure_reason=failure_reason,
    )


def test_candidate_id_is_stable_for_same_scientific_identity() -> None:
    task_a = AutoCandidateTask(pair=_pair(), method=_method())
    task_b = AutoCandidateTask(pair=_pair(), method=_method())
    assert task_a.candidate_id == task_b.candidate_id


def test_candidate_id_changes_when_method_changes() -> None:
    task_a = AutoCandidateTask(pair=_pair(), method=_method("ecc_affine"))
    task_b = AutoCandidateTask(
        pair=_pair(),
        method=_method(
            "orb_affine",
            display_name="ORB",
            method_family="feature_based",
            requires_same_shape=False,
        ),
    )
    assert task_a.candidate_id != task_b.candidate_id


def test_compatibility_filters_transform_model() -> None:
    pair = _pair()
    method = _method(transform_model="rigid")
    reasons = method.compatibility_reasons(pair, include_optional=True)
    assert "transform_model_not_requested" in reasons


def test_compatibility_filters_modality_class() -> None:
    pair = _pair(modality_class="simulated_multimodal")
    method = _method()
    reasons = method.compatibility_reasons(pair, include_optional=True)
    assert "modality_class_not_supported" in reasons


def test_compatibility_filters_shape_requirement() -> None:
    pair = _pair(same_shape=False)
    method = _method(requires_same_shape=True)
    reasons = method.compatibility_reasons(pair, include_optional=True)
    assert "shape_mismatch" in reasons


def test_optional_method_can_be_disabled() -> None:
    pair = _pair()
    method = _method(optional=True)
    reasons = method.compatibility_reasons(pair, include_optional=False)
    assert "optional_method_disabled" in reasons


def test_normalization_groups_common_metrics_by_scientific_role() -> None:
    task = AutoCandidateTask(pair=_pair(), method=_method())
    record = _record(
        task,
        metrics={
            "mae": 1.5,
            "ncc": 0.9,
            "valid_overlap_fraction": 0.8,
            "total_runtime_ms": 12.5,
        },
        diagnostics={"final_ecc": 0.997},
    )
    normalized = normalize_candidate_record(task, record)
    assert normalized.descriptive_metrics == {"mae": 1.5, "ncc": 0.9}
    assert normalized.overlap_metrics == {"valid_overlap_fraction": 0.8}
    assert normalized.runtime_metrics == {"total_runtime_ms": 12.5}
    assert normalized.geometric_metrics == {}
    assert normalized.anatomical_metrics == {}


def test_raw_optimizer_diagnostics_are_preserved_but_not_promoted_to_common_metrics() -> None:
    task = AutoCandidateTask(pair=_pair(), method=_method())
    record = _record(
        task,
        metrics={"ncc": 0.9, "valid_overlap_fraction": 0.8},
        diagnostics={"final_ecc": 0.999, "iterations": 18},
    )
    normalized = normalize_candidate_record(task, record)
    assert normalized.method_diagnostics["final_ecc"] == 0.999
    assert "final_ecc" not in normalized.descriptive_metrics
    assert "final_ecc" not in normalized.runtime_metrics


def test_service_executes_all_compatible_candidates_and_preserves_check() -> None:
    methods = (
        _method("ecc_affine"),
        _method(
            "orb_affine",
            display_name="ORB",
            method_family="feature_based",
            requires_same_shape=False,
        ),
    )

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        status = (
            ExecutionStatus.CHECK
            if task.method.method_id == "orb_affine"
            else ExecutionStatus.COMPLETED
        )
        return _record(
            task,
            status=status,
            plausible=(status is ExecutionStatus.COMPLETED),
            metrics={"ncc": 0.8, "valid_overlap_fraction": 0.8},
        )

    result = AutomaticMultiMethodService(methods, executor).run(_pair())
    assert len(result.candidates) == 2
    assert result.status_counts["completed"] == 1
    assert result.status_counts["check"] == 1
    assert result.recommendation_status == "deferred_until_robustness_calibration"
    assert result.to_dict()["recommendation"]["selected_candidate_id"] is None


def test_service_preserves_executor_failure_as_candidate_evidence() -> None:
    method = _method()

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        raise RuntimeError("synthetic failure")

    result = AutomaticMultiMethodService((method,), executor).run(_pair())
    candidate = result.candidates[0]
    assert candidate.execution_status is ExecutionStatus.FAILED
    assert "synthetic failure" in (candidate.failure_reason or "")


def test_service_converts_identity_mismatch_to_validation_error() -> None:
    method = _method()

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        record = _record(task)
        record.method_id = "wrong_method"
        return record

    result = AutomaticMultiMethodService((method,), executor).run(_pair())
    candidate = result.candidates[0]
    assert candidate.execution_status is ExecutionStatus.VALIDATION_ERROR
    assert "method_id" in (candidate.failure_reason or "")


def test_incompatible_methods_are_retained_in_compatibility_audit() -> None:
    methods = (
        _method("ecc_affine"),
        _method("ecc_rigid", transform_model="rigid"),
    )

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        return _record(task)

    result = AutomaticMultiMethodService(methods, executor).run(_pair())
    assert len(result.candidates) == 1
    decisions = {item.method_id: item for item in result.compatibility}
    assert decisions["ecc_affine"].compatible is True
    assert decisions["ecc_rigid"].compatible is False
    assert "transform_model_not_requested" in decisions["ecc_rigid"].reasons


def test_service_rejects_pair_with_no_compatible_candidate() -> None:
    methods = (_method(transform_model="rigid"),)

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        raise AssertionError("must not execute")

    service = AutomaticMultiMethodService(methods, executor)
    with pytest.raises(ValueError, match="no compatible"):
        service.run(_pair())


def test_unknown_reference_candidate_cannot_invent_geometric_pass() -> None:
    task = AutoCandidateTask(pair=_pair(), method=_method())
    with pytest.raises(ValueError, match="Geometric PASS/CHECK"):
        UnifiedEvaluationRecord(
            pair_id=task.pair.pair_id,
            method_id=task.method.method_id,
            method_family=task.method.method_family,
            transform_model=task.method.transform_model,
            modality_class=task.pair.modality_class,
            dimensions=task.pair.dimensions,
            execution_status=ExecutionStatus.COMPLETED,
            reference=ReferenceEvidence(),
            valid_overlap_fraction=None,
            estimated_transform=np.eye(3),
            transform_plausible=True,
            geometric_within_tolerance=True,
        )


def test_service_blocks_hidden_ground_truth_reference_leakage() -> None:
    method = _method()

    def executor(task: AutoCandidateTask) -> UnifiedEvaluationRecord:
        return UnifiedEvaluationRecord(
            pair_id=task.pair.pair_id,
            method_id=task.method.method_id,
            method_family=task.method.method_family,
            transform_model=task.method.transform_model,
            modality_class=task.pair.modality_class,
            dimensions=task.pair.dimensions,
            execution_status=ExecutionStatus.COMPLETED,
            reference=ReferenceEvidence(exact_transform=True),
            valid_overlap_fraction=None,
            estimated_transform=np.eye(3),
            transform_plausible=True,
            geometric_within_tolerance=True,
        )

    result = AutomaticMultiMethodService((method,), executor).run(_pair())
    candidate = result.candidates[0]
    assert candidate.execution_status is ExecutionStatus.VALIDATION_ERROR
    assert "hidden ground-truth" in (candidate.failure_reason or "")
