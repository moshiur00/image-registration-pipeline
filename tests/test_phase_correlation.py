from __future__ import annotations

import cv2
import numpy as np
import pytest

from image_registration.phase_correlation import (
    PhaseCorrelationRegistration,
    estimate_phase_correlation,
    phase_correlation_surface,
)
from image_registration.registration import RegistrationMethod
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair
from image_registration.transforms import invert_transform, translation_matrix
from image_registration.evaluation import normalized_cross_correlation


def _textured_image(height: int = 128, width: int = 144) -> np.ndarray:
    rng = np.random.default_rng(1234)
    image = rng.normal(size=(height, width)).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 1.2)
    image = (image - np.min(image)) / (np.max(image) - np.min(image))
    cv2.rectangle(image, (18, 20), (48, 55), 1.0, thickness=-1)
    cv2.circle(image, (100, 82), 13, 0.1, thickness=-1)
    return image.astype(np.float32)


def _translation_pair(tx: float, ty: float) -> tuple[np.ndarray, np.ndarray]:
    fixed = _textured_image()
    transform = translation_matrix(tx, ty)
    ground_truth = GroundTruthTransform(
        transform_type="translation",
        parameters={"tx": tx, "ty": ty},
        moving_to_fixed=transform,
        fixed_to_moving=invert_transform(transform),
    )
    pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    return pair.fixed, pair.moving


def test_estimate_identity_translation() -> None:
    fixed = _textured_image()
    estimate = estimate_phase_correlation(fixed, fixed)
    assert estimate.tx == pytest.approx(0.0, abs=1e-6)
    assert estimate.ty == pytest.approx(0.0, abs=1e-6)
    assert np.isfinite(estimate.response)


@pytest.mark.parametrize(
    ("tx", "ty"),
    [
        (5.0, -3.0),
        (-8.0, 6.0),
        (14.0, 11.0),
        (-17.0, -9.0),
    ],
)
def test_known_integer_translation_is_recovered(tx: float, ty: float) -> None:
    fixed, moving = _translation_pair(tx, ty)
    estimate = estimate_phase_correlation(fixed, moving)
    assert estimate.tx == pytest.approx(tx, abs=0.12)
    assert estimate.ty == pytest.approx(ty, abs=0.12)


def test_known_subpixel_translation_is_recovered_within_half_pixel() -> None:
    fixed, moving = _translation_pair(8.5, -6.25)
    estimate = estimate_phase_correlation(fixed, moving)
    error = np.linalg.norm(estimate.vector - np.array([8.5, -6.25]))
    assert error <= 0.5


def test_transform_direction_is_moving_to_fixed() -> None:
    fixed, moving = _translation_pair(7.0, -4.0)
    result = PhaseCorrelationRegistration().register(fixed, moving)
    assert result.success
    assert result.transform[0, 2] == pytest.approx(7.0, abs=0.12)
    assert result.transform[1, 2] == pytest.approx(-4.0, abs=0.12)


def test_registration_improves_ncc() -> None:
    fixed, moving = _translation_pair(11.0, -7.0)
    before = normalized_cross_correlation(fixed, moving)
    result = PhaseCorrelationRegistration().register(fixed, moving)
    after = normalized_cross_correlation(fixed, result.registered_image)
    assert result.success
    assert after > before


def test_registration_result_contains_phase_diagnostics() -> None:
    fixed, moving = _translation_pair(6.0, 5.0)
    result = PhaseCorrelationRegistration().register(fixed, moving)
    info = result.convergence_info
    assert result.success
    assert result.runtime_seconds >= 0.0
    assert info["method"] == "phase_correlation"
    assert info["motion_model"] == "translation"
    assert np.isfinite(info["response"])
    assert info["use_hanning_window"] is True
    assert info["estimation_seconds"] >= 0.0
    assert info["warp_seconds"] >= 0.0


def test_phase_correlation_can_run_without_window() -> None:
    fixed, moving = _translation_pair(-5.0, 4.0)
    estimate = estimate_phase_correlation(
        fixed,
        moving,
        use_hanning_window=False,
    )
    assert estimate.tx == pytest.approx(-5.0, abs=0.25)
    assert estimate.ty == pytest.approx(4.0, abs=0.25)


def test_phase_correlation_surface_peak_has_expected_integer_shift() -> None:
    fixed, moving = _translation_pair(6.0, -4.0)
    surface = phase_correlation_surface(
        fixed,
        moving,
        use_hanning_window=False,
    )
    peak_y, peak_x = np.unravel_index(np.argmax(surface), surface.shape)
    estimated_tx = peak_x - surface.shape[1] // 2
    estimated_ty = peak_y - surface.shape[0] // 2
    assert estimated_tx == 6
    assert estimated_ty == -4


def test_mismatched_shapes_return_failure_record() -> None:
    fixed = np.ones((64, 64), dtype=np.float32)
    moving = np.ones((60, 64), dtype=np.float32)
    result = PhaseCorrelationRegistration().register(fixed, moving)
    assert result.success is False
    assert result.failure_reason is not None
    assert "identical shapes" in result.failure_reason


def test_constant_images_return_failure_record() -> None:
    fixed = np.ones((64, 64), dtype=np.float32)
    moving = fixed.copy()
    result = PhaseCorrelationRegistration().register(fixed, moving)
    assert result.success is False
    assert result.failure_reason is not None
    assert "insufficient intensity variation" in result.failure_reason


def test_nonfinite_input_returns_failure_record() -> None:
    fixed = _textured_image()
    moving = fixed.copy()
    moving[0, 0] = np.nan
    result = PhaseCorrelationRegistration().register(fixed, moving)
    assert result.success is False
    assert result.failure_reason is not None
    assert "finite" in result.failure_reason


def test_response_threshold_can_mark_estimate_as_failure() -> None:
    fixed, moving = _translation_pair(4.0, -3.0)
    result = PhaseCorrelationRegistration(min_response=1e6).register(fixed, moving)
    assert result.success is False
    assert result.failure_reason == "phase_response_below_threshold"
    assert result.transform[0, 2] == pytest.approx(4.0, abs=0.12)
    assert result.transform[1, 2] == pytest.approx(-3.0, abs=0.12)


def test_phase_registration_satisfies_common_interface() -> None:
    method = PhaseCorrelationRegistration()
    assert isinstance(method, RegistrationMethod)
