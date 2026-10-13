from __future__ import annotations

import json

import numpy as np

from ui.core import (
    DiagnosticSummary,
    EvaluationContext,
    GroundTruthStatus,
    ImageSource,
    MetricSummary,
    PreprocessingSpec,
    ProvenanceSummary,
    RegistrationRequest,
    RegistrationRun,
    RegistrationSpec,
    RunStatus,
    SourceType,
    TransformModel,
    TransformSummary,
)
from ui.core.result_presenter import registration_run_summary, to_json_safe


def test_contracts_are_json_safe() -> None:
    request = RegistrationRequest(
        fixed=ImageSource(SourceType.ARRAY, "fixed", array=np.ones((4, 4), dtype=np.float32)),
        moving=ImageSource(SourceType.ARRAY, "moving", array=np.zeros((4, 4), dtype=np.float32)),
        preprocessing=PreprocessingSpec(gaussian_sigma=1.0),
        registration=RegistrationSpec("phase_translation", TransformModel.TRANSLATION),
        evaluation=EvaluationContext(ground_truth_status=GroundTruthStatus.UNAVAILABLE),
        request_id="req-1",
    )
    payload = to_json_safe(request)
    encoded = json.dumps(payload)
    assert '"method_id": "phase_translation"' in encoded
    assert payload["registration"]["transform_model"] == "translation"


def test_run_summary_excludes_registered_array() -> None:
    run = RegistrationRun(
        request_id="req-1",
        run_status=RunStatus.COMPLETED,
        method_success=True,
        transform=TransformSummary(
            matrix=np.eye(3, dtype=np.float64),
            motion_model=TransformModel.TRANSLATION,
        ),
        metrics=MetricSummary(before={"ncc": 0.1}, after={"ncc": 0.9}),
        diagnostics=DiagnosticSummary(values={"phase_response": 0.95}),
        runtime_seconds=0.01,
        warnings=(),
        provenance=ProvenanceSummary(
            fixed_sha256="a",
            moving_sha256="b",
            method_id="phase_translation",
            normalized_parameters={},
            preprocessing={},
        ),
        registered_array=np.ones((8, 8), dtype=np.float32),
    )
    payload = registration_run_summary(run)
    assert "registered_array" not in payload
    assert payload["transform"]["direction"] == "moving_to_fixed"
