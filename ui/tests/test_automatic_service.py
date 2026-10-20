from __future__ import annotations

import json

import numpy as np
import pytest

from image_registration.automatic_registration import AutoMethodSpec
from ui.automatic import AutomaticComparisonRequest, AutomaticComparisonService
from ui.core.contracts import (
    DiagnosticSummary,
    ImageSource,
    MetricSummary,
    PreprocessingSpec,
    ProvenanceSummary,
    RegistrationRun,
    TransformSummary,
)
from ui.core.enums import GroundTruthStatus, RunStatus, SourceType, TransformModel, TransformUnits


class FakeRegistrationService:
    def __init__(self, runs: dict[str, RegistrationRun]) -> None:
        self.runs = runs
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.runs[request.registration.method_id]

    def list_methods(self):
        return []


def _source(name: str, array: np.ndarray) -> ImageSource:
    return ImageSource(
        source_type=SourceType.ARRAY,
        display_name=name,
        array=np.asarray(array),
    )


def _request(
    *,
    fixed_shape: tuple[int, int] = (32, 32),
    moving_shape: tuple[int, int] = (32, 32),
    transform_model: TransformModel = TransformModel.AFFINE,
    modality_class: str = "monomodal",
    include_optional_methods: bool = True,
) -> AutomaticComparisonRequest:
    fixed = np.arange(np.prod(fixed_shape), dtype=np.float32).reshape(fixed_shape)
    moving = np.arange(np.prod(moving_shape), dtype=np.float32).reshape(moving_shape)
    return AutomaticComparisonRequest(
        fixed=_source("fixed", fixed),
        moving=_source("moving", moving),
        transform_model=transform_model,
        modality_class=modality_class,
        preprocessing=PreprocessingSpec(grayscale=True, resize_policy="none"),
        include_optional_methods=include_optional_methods,
    )


def _method(
    method_id: str,
    *,
    transform_model: str = "affine",
    modality_classes: frozenset[str] = frozenset({"monomodal", "unknown"}),
    requires_same_shape: bool = False,
    optional: bool = False,
) -> AutoMethodSpec:
    return AutoMethodSpec(
        method_id=method_id,
        display_name=method_id.replace("_", " ").title(),
        method_family="test_family",
        transform_model=transform_model,
        dimensions=frozenset({2}),
        supported_modality_classes=modality_classes,
        requires_same_shape=requires_same_shape,
        optional=optional,
        metadata={"initialization": "identity", "parameters": {}},
    )


def _run(
    method_id: str,
    *,
    status: RunStatus = RunStatus.COMPLETED,
    tx: float = 0.0,
    ty: float = 0.0,
    plausible: bool | None = True,
    registered: bool = True,
    failure_reason: str | None = None,
) -> RegistrationRun:
    matrix = None
    transform = None
    if status in {RunStatus.COMPLETED, RunStatus.CHECK}:
        matrix = np.array(
            [[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        transform = TransformSummary(
            matrix=matrix,
            motion_model=TransformModel.AFFINE,
            plausible=plausible,
        )
    registered_array = (
        np.arange(32 * 32, dtype=np.float32).reshape(32, 32)
        if registered and transform is not None
        else None
    )
    return RegistrationRun(
        request_id=f"fake-{method_id}",
        run_status=status,
        method_success=status in {RunStatus.COMPLETED, RunStatus.CHECK},
        transform=transform,
        metrics=MetricSummary(units=TransformUnits.PIXELS),
        diagnostics=DiagnosticSummary(values={"raw_objective": float(len(method_id))}),
        runtime_seconds=0.012,
        warnings=(),
        provenance=ProvenanceSummary(
            fixed_sha256="fixed",
            moving_sha256="moving",
            method_id=method_id,
            normalized_parameters={},
            preprocessing={},
            ground_truth_status=GroundTruthStatus.UNAVAILABLE,
        ),
        registered_array=registered_array,
        failure_reason=failure_reason,
    )


def test_preview_is_stable_and_keeps_ground_truth_unavailable() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(_method("ecc_affine"),),
    )
    request = _request()
    first = service.preview(request)
    second = service.preview(request)
    assert first.pair_id == second.pair_id
    assert first.ground_truth_status == "unavailable"
    assert first.compatible_count == 1
    assert first.excluded_count == 0


def test_preview_preserves_explicit_exclusion_reasons() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(
            _method("phase_translation", transform_model="translation"),
            _method("ecc_affine"),
            _method("sift_affine", optional=True),
        ),
    )
    preview = service.preview(_request(include_optional_methods=False))
    assert [item.method_id for item in preview.compatible] == ["ecc_affine"]
    reasons = {item.method_id: item.reasons for item in preview.excluded}
    assert "transform_model_not_requested" in reasons["phase_translation"]
    assert "optional_method_disabled" in reasons["sift_affine"]


def test_shape_mismatch_only_excludes_methods_that_require_same_shape() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(
            _method("ecc_affine", requires_same_shape=True),
            _method("orb_affine", requires_same_shape=False),
        ),
    )
    preview = service.preview(_request(moving_shape=(28, 32)))
    assert [item.method_id for item in preview.compatible] == ["orb_affine"]
    assert preview.excluded[0].method_id == "ecc_affine"
    assert preview.excluded[0].reasons == ("shape_mismatch",)


def test_multimodal_preview_excludes_monomodal_only_method() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(
            _method("ecc_affine", modality_classes=frozenset({"monomodal", "unknown"})),
            _method(
                "mi_affine_2d",
                modality_classes=frozenset(
                    {"monomodal", "multimodal", "simulated_multimodal", "unknown"}
                ),
            ),
        ),
    )
    preview = service.preview(_request(modality_class="multimodal"))
    assert [item.method_id for item in preview.compatible] == ["mi_affine_2d"]
    assert preview.excluded[0].method_id == "ecc_affine"
    assert "modality_class_not_supported" in preview.excluded[0].reasons


def test_unknown_modality_is_permissive_for_candidate_discovery() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(
            _method("ecc_affine"),
            _method(
                "mi_affine_2d",
                modality_classes=frozenset({"multimodal", "unknown"}),
            ),
        ),
    )
    preview = service.preview(_request(modality_class="unknown"))
    assert {item.method_id for item in preview.compatible} == {
        "ecc_affine",
        "mi_affine_2d",
    }


def test_invalid_modality_class_is_rejected_before_execution() -> None:
    service = AutomaticComparisonService(
        registration_service=FakeRegistrationService({}),
        methods=(_method("ecc_affine"),),
    )
    with pytest.raises(ValueError, match="modality_class"):
        service.preview(_request(modality_class="not-a-modality"))


def test_run_executes_all_compatible_candidates_and_keeps_gt_hidden() -> None:
    fake = FakeRegistrationService(
        {
            "ecc_affine": _run("ecc_affine", tx=1.0),
            "orb_affine": _run("orb_affine", tx=2.0),
        }
    )
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"), _method("orb_affine")),
    )
    result = service.run(_request())
    assert len(fake.requests) == 2
    assert len(result.candidates) == 2
    assert result.status_counts["completed"] == 2
    assert result.ground_truth_status == "unavailable"
    assert result.recommendation_status == "deferred_until_robustness_calibration"
    assert all(
        request.evaluation.ground_truth_status is GroundTruthStatus.UNAVAILABLE
        for request in fake.requests
    )
    assert all(candidate.geometric_metrics == {} for candidate in result.candidates)
    assert all(candidate.anatomical_metrics == {} for candidate in result.candidates)


def test_run_normalizes_common_evidence_and_keeps_raw_diagnostics_separate() -> None:
    fake = FakeRegistrationService({"ecc_affine": _run("ecc_affine")})
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"),),
    )
    result = service.run(_request())
    candidate = result.candidates[0]
    assert set(candidate.descriptive_metrics) >= {"mae", "mse", "ncc", "ssim", "evaluation_mi"}
    assert "valid_overlap_fraction" in candidate.overlap_metrics
    assert "total_runtime_ms" in candidate.runtime_metrics
    assert candidate.method_diagnostics["raw_objective"] == pytest.approx(10.0)
    assert "raw_objective" not in candidate.descriptive_metrics
    assert candidate.registered_output_available is True


def test_failed_candidate_is_preserved_in_view() -> None:
    fake = FakeRegistrationService(
        {
            "ecc_affine": _run(
                "ecc_affine",
                status=RunStatus.FAILED,
                registered=False,
                failure_reason="optimizer_failed",
            )
        }
    )
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"),),
    )
    result = service.run(_request())
    candidate = result.candidates[0]
    assert candidate.execution_status == "failed"
    assert candidate.failure_reason == "optimizer_failed"
    assert candidate.registered_output_available is False
    assert result.status_counts["failed"] == 1


def test_check_candidate_is_preserved_and_implausible_transform_is_excluded_from_agreement() -> None:
    fake = FakeRegistrationService(
        {
            "ecc_affine": _run(
                "ecc_affine",
                status=RunStatus.CHECK,
                plausible=False,
            ),
            "orb_affine": _run("orb_affine", tx=1.0),
        }
    )
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"), _method("orb_affine")),
    )
    result = service.run(_request())
    by_method = {candidate.method_id: candidate for candidate in result.candidates}
    assert by_method["ecc_affine"].execution_status == "check"
    assert result.status_counts["check"] == 1
    assert result.agreement.status == "insufficient_candidates"
    excluded = result.agreement.excluded_candidates[by_method["ecc_affine"].candidate_id]
    assert "implausible_transform" in excluded


def test_two_valid_candidates_produce_descriptive_agreement_not_recommendation() -> None:
    fake = FakeRegistrationService(
        {
            "ecc_affine": _run("ecc_affine", tx=0.0),
            "orb_affine": _run("orb_affine", tx=3.0, ty=4.0),
        }
    )
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"), _method("orb_affine")),
        agreement_grid_rows=3,
        agreement_grid_cols=3,
        agreement_margin_fraction=0.0,
    )
    result = service.run(_request())
    assert result.agreement.status == "available"
    assert result.agreement.pairwise_count == 1
    assert result.agreement.pairwise[0].rms_px == pytest.approx(5.0)
    assert "not a validated best-method recommendation" in result.agreement.interpretation
    assert result.to_dict()["agreement"]["final_recommendation"] is None
    assert result.to_dict()["recommendation"]["selected_candidate_id"] is None


def test_single_candidate_does_not_invent_consensus() -> None:
    fake = FakeRegistrationService({"ecc_affine": _run("ecc_affine")})
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"),),
    )
    result = service.run(_request())
    assert result.agreement.status == "insufficient_candidates"
    assert result.agreement.consensus_anchor_candidate_id is None
    assert result.agreement.pairwise_count == 0


def test_result_view_is_json_serializable() -> None:
    fake = FakeRegistrationService({"ecc_affine": _run("ecc_affine")})
    service = AutomaticComparisonService(
        registration_service=fake,
        methods=(_method("ecc_affine"),),
    )
    result = service.run(_request())
    encoded = json.dumps(result.to_dict(), sort_keys=True)
    assert "deferred_until_robustness_calibration" in encoded
    assert "raw_objective" in encoded


def test_stage61_service_module_has_no_streamlit_dependency() -> None:
    import ui.automatic.automatic_service as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "import streamlit" not in source
    assert "from streamlit" not in source


def test_default_catalog_is_derived_from_existing_2d_registry() -> None:
    from ui.adapters import build_default_registration_service
    from ui.automatic.automatic_service import build_default_auto_method_catalog

    registration_service = build_default_registration_service()
    catalog = build_default_auto_method_catalog(registration_service)
    method_ids = {method.method_id for method in catalog}
    assert method_ids == {
        "phase_translation",
        "ecc_translation",
        "ecc_rigid",
        "ecc_affine",
        "orb_similarity",
        "orb_affine",
        "sift_similarity",
        "sift_affine",
        "mi_rigid_2d",
        "mi_affine_2d",
    }
    assert all(2 in method.dimensions for method in catalog)
    assert "mi_rigid_3d_rire" not in method_ids
    assert next(method for method in catalog if method.method_id == "sift_affine").optional is True
