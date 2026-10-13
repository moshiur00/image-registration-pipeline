from __future__ import annotations

import json
import sys

import numpy as np

from ui.core import (
    AdapterResult,
    EvaluationContext,
    GroundTruthStatus,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationService,
    RegistrationSpec,
    RunStatus,
    SourceType,
    TransformModel,
)


class FakePhaseAdapter:
    def __init__(self, *, success: bool = True, within: bool | None = True) -> None:
        self.success = success
        self.within = within

    def run(self, request: RegistrationRequest) -> AdapterResult:
        return AdapterResult(
            method_success=self.success,
            runtime_seconds=0.012,
            transform_matrix=np.array(
                [[1.0, 0.0, 2.0], [0.0, 1.0, -1.0], [0.0, 0.0, 1.0]],
                dtype=np.float64,
            ),
            registered_array=np.ones((12, 12), dtype=np.float32),
            transform_parameters={"tx": 2.0, "ty": -1.0},
            plausible=True,
            descriptive_metrics_before={"ncc": 0.2},
            descriptive_metrics_after={"ncc": 0.9},
            ground_truth_metrics={"tre_px": 0.1},
            within_tolerance=self.within,
            diagnostics={"phase_response": 0.98},
            failure_reason=None if self.success else "synthetic failure",
        )


def make_request(status: GroundTruthStatus) -> RegistrationRequest:
    ground_truth_transform = (
        np.eye(3, dtype=np.float64) if status is GroundTruthStatus.KNOWN else None
    )
    return RegistrationRequest(
        fixed=ImageSource(SourceType.ARRAY, "fixed", array=np.arange(144, dtype=np.float32).reshape(12, 12)),
        moving=ImageSource(SourceType.ARRAY, "moving", array=np.arange(144, dtype=np.float32).reshape(12, 12)),
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec("phase_translation", TransformModel.TRANSLATION),
        evaluation=EvaluationContext(
            ground_truth_status=status,
            ground_truth_transform=ground_truth_transform,
        ),
        request_id="service-test",
    )


def make_service(adapter: FakePhaseAdapter) -> RegistrationService:
    return RegistrationService(
        adapters={"phase_correlation": adapter},
        version_provider=lambda: "test-version",
    )


def test_service_is_streamlit_independent() -> None:
    assert "streamlit" not in sys.modules
    service = make_service(FakePhaseAdapter())
    assert service.list_methods()
    assert "streamlit" not in sys.modules


def test_unknown_ground_truth_suppresses_tre_and_geometric_status() -> None:
    run = make_service(FakePhaseAdapter(within=True)).run(
        make_request(GroundTruthStatus.UNAVAILABLE)
    )
    assert run.run_status is RunStatus.COMPLETED
    assert run.metrics.ground_truth == {}
    assert run.metrics.within_tolerance is None
    assert any("Ground truth is unavailable" in warning for warning in run.warnings)


def test_known_ground_truth_preserves_tre_and_check_state() -> None:
    run = make_service(FakePhaseAdapter(within=False)).run(make_request(GroundTruthStatus.KNOWN))
    assert run.run_status is RunStatus.CHECK
    assert run.metrics.ground_truth["tre_px"] == 0.1
    assert run.metrics.within_tolerance is False


def test_input_hashes_are_deterministic() -> None:
    request = make_request(GroundTruthStatus.UNAVAILABLE)
    service = make_service(FakePhaseAdapter())
    first = service.run(request)
    second = service.run(request)
    assert first.provenance.fixed_sha256 == second.provenance.fixed_sha256
    assert first.provenance.moving_sha256 == second.provenance.moving_sha256
    assert len(first.provenance.fixed_sha256 or "") == 64


def test_export_summary_is_json_and_excludes_registered_array() -> None:
    run = make_service(FakePhaseAdapter()).run(make_request(GroundTruthStatus.UNAVAILABLE))
    payload = json.loads(make_service(FakePhaseAdapter()).export_summary(run))
    assert payload["provenance"]["transform_direction"] == "moving_to_fixed"
    assert "registered_array" not in payload


def test_missing_adapter_is_explicit_stage3_failure() -> None:
    run = RegistrationService().run(make_request(GroundTruthStatus.UNAVAILABLE))
    assert run.run_status is RunStatus.FAILED
    assert run.failure_reason == "Adapter not registered: phase_correlation"
    assert "Stage 3" in run.warnings[0]
