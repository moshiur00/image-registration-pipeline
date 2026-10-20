from __future__ import annotations

import numpy as np
import pytest

from image_registration.evaluation_contracts import (
    COORDINATE_ORDER_2D,
    COORDINATE_ORDER_3D,
    METRIC_DEFINITIONS,
    SCHEMA_VERSION,
    TRANSFORM_DIRECTION,
    EvaluationContext,
    ExecutionStatus,
    MetricRole,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
    available_metric_keys,
    metric_availability,
    resolve_valid_overlap,
)


def test_metric_catalog_separates_descriptive_and_geometric_evidence() -> None:
    assert METRIC_DEFINITIONS["tre_mean_px"].role is MetricRole.GEOMETRIC_ERROR
    assert METRIC_DEFINITIONS["ncc"].role is MetricRole.DESCRIPTIVE_SIMILARITY
    assert METRIC_DEFINITIONS["total_runtime_ms"].role is MetricRole.RUNTIME


def test_unknown_pair_disables_ground_truth_metrics_but_keeps_descriptive_metrics() -> None:
    context = EvaluationContext(
        modality_class="unknown",
        reference=ReferenceEvidence(),
        valid_overlap_available=True,
        valid_overlap_fraction=0.8,
    )
    assert metric_availability("tre_mean_px", context).available is False
    assert metric_availability("translation_error_px", context).available is False
    assert metric_availability("dice", context).available is False
    assert metric_availability("ncc", context).available is True
    assert metric_availability("ssim", context).available is True
    assert context.geometric_pass_allowed is False


def test_exact_transform_enables_parameter_error_and_tre() -> None:
    context = EvaluationContext(
        modality_class="monomodal",
        reference=ReferenceEvidence(exact_transform=True),
        valid_overlap_available=True,
        valid_overlap_fraction=1.0,
    )
    keys = available_metric_keys(context)
    assert "translation_error_px" in keys
    assert "rotation_error_deg" in keys
    assert "tre_mean_px" in keys
    assert "dice" not in keys
    assert context.geometric_pass_allowed is True


def test_mask_reference_enables_dice_without_enabling_tre() -> None:
    context = EvaluationContext(
        modality_class="medical",
        reference=ReferenceEvidence(masks=True),
        valid_overlap_available=True,
        valid_overlap_fraction=0.9,
    )
    assert metric_availability("dice", context).available is True
    assert metric_availability("tre_mean_px", context).available is False
    assert context.geometric_pass_allowed is False


def test_physical_metrics_require_physical_spacing() -> None:
    without_spacing = EvaluationContext(
        modality_class="medical",
        reference=ReferenceEvidence(exact_transform=True, physical_spacing=False),
        valid_overlap_available=True,
        valid_overlap_fraction=0.9,
    )
    with_spacing = EvaluationContext(
        modality_class="medical",
        reference=ReferenceEvidence(exact_transform=True, physical_spacing=True),
        valid_overlap_available=True,
        valid_overlap_fraction=0.9,
    )
    assert metric_availability("translation_error_mm", without_spacing).available is False
    assert metric_availability("translation_error_mm", with_spacing).available is True
    assert metric_availability("tre_mean_mm", with_spacing).available is True
    assert metric_availability("tre_median_mm", with_spacing).available is True
    assert metric_availability("tre_std_mm", with_spacing).available is True
    assert metric_availability("tre_p95_mm", with_spacing).available is True


def test_resolve_valid_overlap_intersects_masks() -> None:
    first = np.ones((4, 5), dtype=np.uint8)
    first[:, 0] = 0
    second = np.ones((4, 5), dtype=np.uint8)
    second[0, :] = 0
    overlap = resolve_valid_overlap((4, 5), first, second)
    assert overlap.pixel_count == 12
    assert overlap.total_pixels == 20
    assert overlap.fraction == pytest.approx(0.6)
    assert overlap.mask.dtype == np.bool_


def test_resolve_valid_overlap_rejects_empty_region() -> None:
    empty = np.zeros((4, 5), dtype=np.uint8)
    with pytest.raises(ValueError, match="empty"):
        resolve_valid_overlap((4, 5), empty)


def test_unknown_record_cannot_claim_geometric_pass() -> None:
    with pytest.raises(ValueError, match="Geometric PASS/CHECK"):
        UnifiedEvaluationRecord(
            pair_id="upload_pair",
            method_id="ecc_affine",
            method_family="ecc",
            transform_model="affine",
            modality_class="unknown",
            dimensions=2,
            execution_status=ExecutionStatus.COMPLETED,
            reference=ReferenceEvidence(),
            valid_overlap_fraction=0.8,
            estimated_transform=np.eye(3),
            transform_plausible=True,
            geometric_within_tolerance=True,
        )


def test_record_rejects_unavailable_metric() -> None:
    with pytest.raises(ValueError, match="tre_mean_px"):
        UnifiedEvaluationRecord(
            pair_id="upload_pair",
            method_id="ecc_affine",
            method_family="ecc",
            transform_model="affine",
            modality_class="unknown",
            dimensions=2,
            execution_status=ExecutionStatus.COMPLETED,
            reference=ReferenceEvidence(),
            valid_overlap_fraction=0.8,
            estimated_transform=np.eye(3),
            metrics={"tre_mean_px": 1.0},
        )


def test_known_record_serializes_stable_contract() -> None:
    record = UnifiedEvaluationRecord(
        pair_id="synthetic_affine",
        method_id="ecc_affine",
        method_family="ecc",
        transform_model="affine",
        modality_class="monomodal",
        dimensions=2,
        execution_status=ExecutionStatus.COMPLETED,
        reference=ReferenceEvidence(exact_transform=True),
        valid_overlap_fraction=0.75,
        seed=42,
        estimated_transform=np.eye(3),
        transform_plausible=True,
        geometric_within_tolerance=True,
        metrics={"tre_mean_px": 0.1, "ncc": 0.95},
        timings_ms={"registration": 12.5, "total": 16.0},
        method_diagnostics={"final_ecc": 0.99},
    )
    payload = record.to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["transform_direction"] == TRANSFORM_DIRECTION
    assert payload["coordinate_order"] == COORDINATE_ORDER_2D
    assert payload["reference"]["label"] == "exact_transform"
    assert payload["estimated_transform"] == np.eye(3).tolist()
    assert payload["metrics"] == {"ncc": 0.95, "tre_mean_px": 0.1}



def test_three_dimensional_record_accepts_4x4_physical_transform() -> None:
    record = UnifiedEvaluationRecord(
        pair_id="rire_pair",
        method_id="mi_rigid_3d",
        method_family="mutual_information",
        transform_model="rigid",
        modality_class="real_multimodal",
        dimensions=3,
        execution_status=ExecutionStatus.COMPLETED,
        reference=ReferenceEvidence(physical_spacing=True),
        valid_overlap_fraction=0.66,
        estimated_transform=np.eye(4),
        transform_plausible=True,
    )
    payload = record.to_dict()
    assert payload["dimensions"] == 3
    assert payload["coordinate_order"] == COORDINATE_ORDER_3D
    assert payload["estimated_transform"] == np.eye(4).tolist()


def test_failed_record_requires_failure_reason() -> None:
    with pytest.raises(ValueError, match="failure_reason"):
        UnifiedEvaluationRecord(
            pair_id="case",
            method_id="orb_affine",
            method_family="feature",
            transform_model="affine",
            modality_class="monomodal",
            dimensions=2,
            execution_status=ExecutionStatus.FAILED,
            reference=ReferenceEvidence(exact_transform=True),
            valid_overlap_fraction=0.7,
        )
