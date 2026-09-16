from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.ecc import (
    ECCRegistration,
    estimate_ecc,
    rigid_angle_degrees,
)
from image_registration.registration import RegistrationMethod
from image_registration.registration_metrics import (
    centered_translation_error_pixels,
    centered_translation_parameters,
    mean_tre_pixels,
    rotation_error_degrees,
    transform_point_errors,
)
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import invert_transform, rigid_matrix, translation_matrix


def _textured_image() -> np.ndarray:
    image = np.zeros((128, 128), dtype=np.uint8)
    cv2.rectangle(image, (12, 18), (48, 70), 90, -1)
    cv2.circle(image, (88, 38), 18, 210, -1)
    cv2.line(image, (20, 105), (112, 82), 160, 5)
    cv2.putText(image, "R", (70, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 245, 2)
    return cv2.GaussianBlur(image, (3, 3), 0.6)


def _translation_pair(tx: float = 7.0, ty: float = -5.0):
    fixed = _textured_image()
    transform = translation_matrix(tx, ty)
    gt = GroundTruthTransform(
        transform_type="translation",
        parameters={"tx": tx, "ty": ty},
        moving_to_fixed=transform,
        fixed_to_moving=invert_transform(transform),
    )
    return generate_synthetic_pair(fixed, gt)


def _rigid_pair(angle: float = 4.0, tx: float = 5.0, ty: float = -4.0):
    fixed = _textured_image()
    center = image_center(fixed.shape)
    transform = rigid_matrix(angle, tx=tx, ty=ty, center=center)
    gt = GroundTruthTransform(
        transform_type="rigid",
        parameters={"angle_degrees": angle, "tx": tx, "ty": ty, "center": center.tolist()},
        moving_to_fixed=transform,
        fixed_to_moving=invert_transform(transform),
    )
    return generate_synthetic_pair(fixed, gt), center


def test_ecc_registration_implements_common_protocol() -> None:
    method = ECCRegistration()
    assert isinstance(method, RegistrationMethod)


@pytest.mark.parametrize("initialization", ["identity", "phase_correlation"])
def test_ecc_translation_recovers_known_shift(initialization: str) -> None:
    pair = _translation_pair()
    result = ECCRegistration(
        motion_model="translation",
        initialization=initialization,
        max_iterations=120,
    ).register(pair.fixed, pair.moving)
    assert result.success
    assert result.failure_reason is None
    assert mean_tre_pixels(
        pair.ground_truth.moving_to_fixed,
        result.transform,
        pair.control_points_moving,
    ) < 0.8


@pytest.mark.parametrize("initialization", ["identity", "phase_correlation"])
def test_ecc_rigid_recovers_known_motion(initialization: str) -> None:
    pair, center = _rigid_pair()
    result = ECCRegistration(
        motion_model="rigid",
        initialization=initialization,
        max_iterations=150,
    ).register(pair.fixed, pair.moving)
    assert result.success
    assert rotation_error_degrees(pair.ground_truth.moving_to_fixed, result.transform) < 0.8
    assert centered_translation_error_pixels(
        pair.ground_truth.moving_to_fixed,
        result.transform,
        center,
    ) < 1.5


def test_estimate_ecc_returns_project_moving_to_fixed_direction() -> None:
    pair = _translation_pair(tx=9.0, ty=-6.0)
    estimate = estimate_ecc(pair.fixed, pair.moving, motion_model="translation")
    assert estimate.moving_to_fixed[0, 2] == pytest.approx(9.0, abs=0.8)
    assert estimate.moving_to_fixed[1, 2] == pytest.approx(-6.0, abs=0.8)
    identity = estimate.fixed_to_moving @ estimate.moving_to_fixed
    assert np.allclose(identity, np.eye(3), atol=1e-5)


def test_ecc_records_optimizer_diagnostics() -> None:
    pair = _translation_pair()
    result = ECCRegistration(
        motion_model="translation",
        initialization="phase_correlation",
        max_iterations=77,
        epsilon=1e-5,
        gauss_filt_size=5,
    ).register(pair.fixed, pair.moving)
    info = result.convergence_info
    assert info["method"] == "ecc"
    assert info["motion_model"] == "translation"
    assert info["initialization"] == "phase_correlation"
    assert info["max_iterations"] == 77
    assert info["epsilon"] == pytest.approx(1e-5)
    assert np.isfinite(info["final_ecc"])
    assert info["estimation_seconds"] >= 0.0
    assert info["warp_seconds"] >= 0.0


def test_ecc_constant_image_fails_safely() -> None:
    image = np.ones((64, 64), dtype=np.uint8) * 120
    result = ECCRegistration().register(image, image)
    assert not result.success
    assert result.failure_reason == "invalid_input"
    assert np.allclose(result.transform, np.eye(3))


def test_ecc_shape_mismatch_fails_safely() -> None:
    fixed = np.zeros((64, 64), dtype=np.uint8)
    moving = np.zeros((60, 64), dtype=np.uint8)
    result = ECCRegistration().register(fixed, moving)
    assert not result.success
    assert result.failure_reason == "invalid_input"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"motion_model": "perspective"},
        {"initialization": "unknown"},
        {"max_iterations": 0},
        {"epsilon": 0.0},
        {"gauss_filt_size": 4},
    ],
)
def test_ecc_invalid_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ECCRegistration(**kwargs)  # type: ignore[arg-type]


def test_minimum_ecc_threshold_can_mark_result_unsuccessful() -> None:
    pair = _translation_pair()
    result = ECCRegistration(min_ecc=1.1).register(pair.fixed, pair.moving)
    assert not result.success
    assert result.failure_reason == "ecc_below_threshold"


def test_rigid_angle_helper_matches_project_convention() -> None:
    fixed = _textured_image()
    center = image_center(fixed.shape)
    matrix = rigid_matrix(13.5, tx=4.0, ty=-2.0, center=center)
    assert rigid_angle_degrees(matrix) == pytest.approx(13.5, abs=1e-9)


def test_registration_metrics_return_zero_for_identical_transforms() -> None:
    fixed = _textured_image()
    center = image_center(fixed.shape)
    transform = rigid_matrix(7.0, tx=3.0, ty=-5.0, center=center)
    points = np.array([[10.0, 12.0], [80.0, 20.0], [60.0, 90.0]])
    errors = transform_point_errors(transform, transform, points)
    assert np.allclose(errors, 0.0)
    assert mean_tre_pixels(transform, transform, points) == pytest.approx(0.0)
    assert rotation_error_degrees(transform, transform) == pytest.approx(0.0)
    assert centered_translation_error_pixels(transform, transform, center) == pytest.approx(0.0)


def test_centered_translation_parameters_recover_rigid_parameters() -> None:
    fixed = _textured_image()
    center = image_center(fixed.shape)
    matrix = rigid_matrix(-11.0, tx=8.0, ty=6.0, center=center)
    translation = centered_translation_parameters(matrix, center)
    assert translation[0] == pytest.approx(8.0, abs=1e-9)
    assert translation[1] == pytest.approx(6.0, abs=1e-9)
