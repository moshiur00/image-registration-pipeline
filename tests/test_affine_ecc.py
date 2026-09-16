from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration, estimate_ecc
from image_registration.registration import RegistrationMethod
from image_registration.registration_metrics import affine_linear_error, mean_tre_pixels
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import affine_matrix, invert_transform, rotation_matrix


def _textured_image() -> np.ndarray:
    image = np.zeros((128, 128), dtype=np.uint8)
    cv2.rectangle(image, (12, 18), (48, 70), 90, -1)
    cv2.circle(image, (88, 38), 18, 210, -1)
    cv2.line(image, (20, 105), (112, 82), 160, 5)
    cv2.putText(image, "R", (70, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 245, 2)
    return cv2.GaussianBlur(image, (3, 3), 0.6)


def _affine_ground_truth() -> tuple[np.ndarray, GroundTruthTransform]:
    image = _textured_image()
    center = image_center(image.shape)
    rotation = rotation_matrix(5.0)[:2, :2]
    linear = rotation @ np.array([[1.04, 0.04], [0.0, 0.96]], dtype=np.float64)
    transform = affine_matrix(linear, tx=8.0, ty=-6.0, center=center)
    ground_truth = GroundTruthTransform(
        transform_type="affine",
        parameters={},
        moving_to_fixed=transform,
        fixed_to_moving=invert_transform(transform),
    )
    return image, ground_truth


def test_estimate_ecc_supports_affine_motion() -> None:
    image, ground_truth = _affine_ground_truth()
    pair = generate_synthetic_pair(image, ground_truth)
    estimate = estimate_ecc(
        pair.fixed,
        pair.moving,
        motion_model="affine",
        initialization="phase_correlation",
        max_iterations=180,
    )
    assert mean_tre_pixels(
        ground_truth.moving_to_fixed,
        estimate.moving_to_fixed,
        pair.control_points_moving,
    ) < 1.0


def test_ecc_registration_affine_returns_standard_result() -> None:
    image, ground_truth = _affine_ground_truth()
    pair = generate_synthetic_pair(image, ground_truth)
    method = ECCRegistration(
        motion_model="affine",
        initialization="phase_correlation",
        max_iterations=180,
    )
    assert isinstance(method, RegistrationMethod)
    result = method.register(pair.fixed, pair.moving)
    assert result.success
    assert result.transform.shape == (3, 3)
    assert result.convergence_info["motion_model"] == "affine"
    assert affine_linear_error(ground_truth.moving_to_fixed, result.transform) < 0.03


def test_ecc_supports_provided_initial_transform() -> None:
    image, ground_truth = _affine_ground_truth()
    pair = generate_synthetic_pair(image, ground_truth)
    result = ECCRegistration(
        motion_model="affine",
        initialization="provided",
        initial_transform=ground_truth.moving_to_fixed,
        max_iterations=80,
    ).register(pair.fixed, pair.moving)
    assert result.success
    assert result.convergence_info["initialization"] == "provided"


def test_provided_initialization_requires_transform() -> None:
    with pytest.raises(ValueError, match="requires initial_transform"):
        ECCRegistration(motion_model="affine", initialization="provided")


def test_initial_transform_rejected_for_nonprovided_initialization() -> None:
    with pytest.raises(ValueError, match="only be used"):
        ECCRegistration(
            motion_model="affine",
            initialization="identity",
            initial_transform=np.eye(3),
        )


def test_multiresolution_affine_ecc_completes_all_levels() -> None:
    image, ground_truth = _affine_ground_truth()
    pair = generate_synthetic_pair(image, ground_truth)
    result = MultiResolutionECCRegistration(
        motion_model="affine",
        initialization="phase_correlation",
        pyramid_scales=(0.5, 1.0),
        pre_smoothing_sigma=0.5,
        max_iterations=120,
    ).register(pair.fixed, pair.moving)
    assert result.success
    assert result.convergence_info["levels_completed"] == 2
    assert len(result.convergence_info["level_records"]) == 2
    assert mean_tre_pixels(
        ground_truth.moving_to_fixed,
        result.transform,
        pair.control_points_moving,
    ) < 1.0


def test_multiresolution_invalid_scales_fail_at_construction() -> None:
    with pytest.raises(ValueError):
        MultiResolutionECCRegistration(pyramid_scales=(0.5, 0.25, 1.0))
