from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from ui.adapters import build_default_registration_service
from ui.core import (
    DatasetCatalog,
    EvaluationContext,
    GroundTruthStatus,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationSpec,
    RunStatus,
    SourceType,
    TransformModel,
)
from image_registration.transforms import translation_matrix
from image_registration.warping import warp_image


def _textured_image(size: int = 160) -> np.ndarray:
    yy, xx = np.indices((size, size), dtype=np.float32)
    image = (
        0.8 * np.exp(-((xx - 45.0) ** 2 + (yy - 55.0) ** 2) / (2.0 * 13.0**2))
        + 0.6 * np.exp(-((xx - 112.0) ** 2 + (yy - 105.0) ** 2) / (2.0 * 17.0**2))
    )
    image[25:40, 95:135] += 0.8
    image[105:130, 30:52] += 0.7
    return image.astype(np.float32)


def test_phase_adapter_executes_known_translation() -> None:
    fixed = _textured_image()
    truth = translation_matrix(7.0, -5.0)
    moving = warp_image(fixed, np.linalg.inv(truth), output_shape=fixed.shape)
    request = RegistrationRequest(
        fixed=ImageSource(SourceType.ARRAY, "fixed", array=fixed),
        moving=ImageSource(SourceType.ARRAY, "moving", array=moving),
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec("phase_translation", TransformModel.TRANSLATION),
        evaluation=EvaluationContext(
            ground_truth_status=GroundTruthStatus.KNOWN,
            ground_truth_transform=truth,
        ),
        request_id="phase-stage3",
    )
    run = build_default_registration_service().run(request)
    assert run.method_success is True
    assert run.transform is not None
    assert run.metrics.ground_truth["mean_tre_pixels"] < 1.0


def test_feature_adapter_executes_orb_similarity_catalog_example() -> None:
    catalog = DatasetCatalog()
    bundle = catalog.build("synthetic_similarity")
    request = RegistrationRequest(
        fixed=bundle.fixed,
        moving=bundle.moving,
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec(
            "orb_similarity",
            TransformModel.SIMILARITY,
            parameters={"n_features": 800, "ratio_threshold": 0.75},
        ),
        evaluation=bundle.evaluation,
        request_id="orb-stage3",
    )
    run = build_default_registration_service(example_provider=catalog).run(request)
    assert run.method_success is True
    assert run.transform is not None
    assert run.diagnostics.values["accepted_matches"] >= 4
    assert run.metrics.ground_truth["mean_tre_pixels"] < 2.0


def test_service_lists_catalog_examples() -> None:
    catalog = DatasetCatalog()
    service = build_default_registration_service(example_provider=catalog)
    assert len(service.list_examples()) >= 6


@pytest.mark.skipif(importlib.util.find_spec("SimpleITK") is None, reason="SimpleITK not installed")
def test_mi_adapter_executes_rigid_example_when_simpleitk_available() -> None:
    catalog = DatasetCatalog()
    bundle = catalog.build("synthetic_inversion_rigid")
    request = RegistrationRequest(
        fixed=bundle.fixed,
        moving=bundle.moving,
        preprocessing=PreprocessingSpec(gaussian_sigma=1.0),
        registration=RegistrationSpec(
            "mi_rigid_2d",
            TransformModel.RIGID,
            initialization="identity",
            parameters={
                "histogram_bins": 32,
                "sampling_strategy": "none",
                "sampling_percentage": 1.0,
                "shrink_factors": (4, 2, 1),
                "smoothing_sigmas": (2.0, 1.0, 0.0),
            },
        ),
        evaluation=bundle.evaluation,
        request_id="mi-stage3",
    )
    run = build_default_registration_service().run(request)
    assert run.method_success is True
    assert run.transform is not None


def test_ecc_adapter_executes_rigid_catalog_example() -> None:
    catalog = DatasetCatalog()
    bundle = catalog.build("synthetic_rigid")
    request = RegistrationRequest(
        fixed=bundle.fixed,
        moving=bundle.moving,
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec(
            "ecc_rigid",
            TransformModel.RIGID,
            initialization="identity",
            parameters={"max_iterations": 200},
        ),
        evaluation=bundle.evaluation,
        request_id="ecc-stage3",
    )
    run = build_default_registration_service().run(request)
    assert run.method_success is True
    assert run.transform is not None
    assert run.metrics.ground_truth["mean_tre_pixels"] < 2.0


def test_sift_adapter_executes_similarity_catalog_example() -> None:
    catalog = DatasetCatalog()
    bundle = catalog.build("synthetic_similarity")
    request = RegistrationRequest(
        fixed=bundle.fixed,
        moving=bundle.moving,
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec(
            "sift_similarity",
            TransformModel.SIMILARITY,
            parameters={"n_features": 800, "ratio_threshold": 0.75},
        ),
        evaluation=bundle.evaluation,
        request_id="sift-stage3",
    )
    run = build_default_registration_service().run(request)
    assert run.method_success is True
    assert run.transform is not None
    assert run.metrics.ground_truth["mean_tre_pixels"] < 2.0


def test_uploaded_unknown_image_keeps_ground_truth_metrics_suppressed() -> None:
    import cv2

    fixed = _textured_image()
    truth = translation_matrix(5.0, -3.0)
    moving = warp_image(fixed, np.linalg.inv(truth), output_shape=fixed.shape)
    fixed_u8 = np.clip(np.rint(fixed / max(float(fixed.max()), 1e-6) * 255.0), 0, 255).astype(np.uint8)
    moving_u8 = np.clip(np.rint(moving / max(float(moving.max()), 1e-6) * 255.0), 0, 255).astype(np.uint8)
    ok_fixed, fixed_png = cv2.imencode(".png", fixed_u8)
    ok_moving, moving_png = cv2.imencode(".png", moving_u8)
    assert ok_fixed and ok_moving
    request = RegistrationRequest(
        fixed=ImageSource(SourceType.UPLOADED_BYTES, "fixed.png", content_bytes=fixed_png.tobytes()),
        moving=ImageSource(SourceType.UPLOADED_BYTES, "moving.png", content_bytes=moving_png.tobytes()),
        preprocessing=PreprocessingSpec(),
        registration=RegistrationSpec("phase_translation", TransformModel.TRANSLATION),
        evaluation=EvaluationContext(ground_truth_status=GroundTruthStatus.UNAVAILABLE),
        request_id="upload-stage3",
    )
    run = build_default_registration_service().run(request)
    assert run.method_success is True
    assert run.metrics.ground_truth == {}
    assert run.metrics.within_tolerance is None
    assert run.run_status is RunStatus.COMPLETED
