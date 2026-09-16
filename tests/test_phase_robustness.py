from __future__ import annotations

import cv2
import numpy as np

from image_registration.degradations import gaussian_blur, gaussian_noise
from image_registration.overlap import (
    apply_field_of_view,
    combine_valid_masks,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
    transformed_support_mask,
)
from image_registration.phase_correlation import PhaseCorrelationRegistration
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair
from image_registration.transforms import invert_transform, translation_matrix


def _textured_image(height: int = 160, width: int = 176) -> np.ndarray:
    rng = np.random.default_rng(90210)
    image = rng.normal(size=(height, width)).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 1.1)
    image = (image - np.min(image)) / (np.max(image) - np.min(image))
    cv2.rectangle(image, (20, 24), (58, 70), 1.0, thickness=-1)
    cv2.circle(image, (126, 105), 16, 0.05, thickness=-1)
    return image.astype(np.float32)


def _translation_pair(tx: float = 16.0, ty: float = -11.0):
    fixed = _textured_image()
    transform = translation_matrix(tx, ty)
    ground_truth = GroundTruthTransform(
        transform_type="translation",
        parameters={"tx": tx, "ty": ty},
        moving_to_fixed=transform,
        fixed_to_moving=invert_transform(transform),
    )
    return generate_synthetic_pair(fixed, ground_truth, interpolation="linear")


def _translation_error(result, tx: float, ty: float) -> float:
    return float(
        np.hypot(
            float(result.transform[0, 2]) - tx,
            float(result.transform[1, 2]) - ty,
        )
    )


def test_gaussian_noise_with_same_seed_is_deterministic() -> None:
    pair = _translation_pair()
    first = gaussian_noise(
        pair.moving,
        sigma_fraction=0.3,
        rng=np.random.default_rng(42),
    )
    second = gaussian_noise(
        pair.moving,
        sigma_fraction=0.3,
        rng=np.random.default_rng(42),
    )
    assert np.array_equal(first, second)


def test_phase_correlation_handles_moderate_gaussian_noise() -> None:
    pair = _translation_pair()
    moving = gaussian_noise(
        pair.moving,
        sigma_fraction=0.3,
        rng=np.random.default_rng(42),
    )
    result = PhaseCorrelationRegistration().register(pair.fixed, moving)
    assert result.success
    assert _translation_error(result, 16.0, -11.0) <= 0.5


def test_phase_correlation_handles_moderate_gaussian_blur() -> None:
    pair = _translation_pair()
    moving = gaussian_blur(pair.moving, sigma=2.5)
    result = PhaseCorrelationRegistration().register(pair.fixed, moving)
    assert result.success
    assert _translation_error(result, 16.0, -11.0) <= 0.5


def test_severe_blur_returns_finite_diagnostics() -> None:
    pair = _translation_pair()
    moving = gaussian_blur(pair.moving, sigma=8.0)
    result = PhaseCorrelationRegistration().register(pair.fixed, moving)
    assert result.success
    assert np.all(np.isfinite(result.transform))
    assert np.isfinite(float(result.convergence_info["response"]))
    assert result.runtime_seconds >= 0.0


def test_restricted_field_of_view_reduces_valid_overlap() -> None:
    pair = _translation_pair()
    natural_valid = transformed_support_mask(
        pair.fixed.shape,
        pair.ground_truth.fixed_to_moving,
        destination_shape=pair.moving.shape,
    )
    natural_overlap_mask = overlap_mask_in_fixed_space(
        natural_valid,
        pair.ground_truth.moving_to_fixed,
        fixed_shape=pair.fixed.shape,
    )

    fov = rectangular_field_of_view_mask(
        pair.moving.shape,
        width_fraction=0.45,
        height_fraction=0.45,
    )
    restricted_valid = combine_valid_masks(natural_valid, fov)
    restricted_overlap_mask = overlap_mask_in_fixed_space(
        restricted_valid,
        pair.ground_truth.moving_to_fixed,
        fixed_shape=pair.fixed.shape,
    )

    assert overlap_fraction(restricted_overlap_mask) < overlap_fraction(natural_overlap_mask)


def test_phase_correlation_handles_restricted_field_of_view_safely() -> None:
    pair = _translation_pair()
    fov = rectangular_field_of_view_mask(
        pair.moving.shape,
        width_fraction=0.25,
        height_fraction=0.25,
    )
    moving = apply_field_of_view(pair.moving, fov, fill_value=0.0)
    result = PhaseCorrelationRegistration().register(pair.fixed, moving)
    assert result.failure_reason is None
    assert result.success
    assert np.all(np.isfinite(result.transform))
    assert np.isfinite(float(result.convergence_info["response"]))


def test_windowed_and_unwindowed_estimates_are_finite() -> None:
    pair = _translation_pair(tx=48.0, ty=-32.0)
    for use_hanning_window in (False, True):
        result = PhaseCorrelationRegistration(
            use_hanning_window=use_hanning_window
        ).register(pair.fixed, pair.moving)
        assert result.success
        assert np.all(np.isfinite(result.transform))
        assert np.isfinite(float(result.convergence_info["response"]))
