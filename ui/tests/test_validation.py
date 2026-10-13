from __future__ import annotations

import numpy as np

from ui.core import (
    EvaluationContext,
    GroundTruthStatus,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationService,
    RegistrationSpec,
    SourceType,
    TransformModel,
)


def make_request(
    *,
    method_id: str = "phase_translation",
    model: TransformModel = TransformModel.TRANSLATION,
    gt_status: GroundTruthStatus = GroundTruthStatus.UNAVAILABLE,
    gt_transform: np.ndarray | None = None,
) -> RegistrationRequest:
    return RegistrationRequest(
        fixed=ImageSource(SourceType.ARRAY, "fixed", array=np.ones((16, 16), dtype=np.float32)),
        moving=ImageSource(SourceType.ARRAY, "moving", array=np.ones((16, 16), dtype=np.float32)),
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec(method_id, model),
        evaluation=EvaluationContext(
            ground_truth_status=gt_status,
            ground_truth_transform=gt_transform,
        ),
        request_id="validation-test",
    )


def test_invalid_transform_is_rejected_before_execution() -> None:
    request = make_request(model=TransformModel.AFFINE)
    report = RegistrationService().validate(request)
    assert report.valid is False
    assert "unsupported_transform_model" in {issue.code for issue in report.errors}


def test_known_ground_truth_requires_evidence() -> None:
    request = make_request(gt_status=GroundTruthStatus.KNOWN)
    report = RegistrationService().validate(request)
    assert report.valid is False
    assert "known_ground_truth_missing_evidence" in {issue.code for issue in report.errors}


def test_known_ground_truth_transform_is_valid() -> None:
    request = make_request(
        gt_status=GroundTruthStatus.KNOWN,
        gt_transform=np.eye(3, dtype=np.float64),
    )
    assert RegistrationService().validate(request).valid is True
