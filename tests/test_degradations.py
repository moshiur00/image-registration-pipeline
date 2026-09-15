import numpy as np
import pytest

from image_registration.degradations import (
    adjust_contrast,
    adjust_gamma,
    apply_degradation,
    gaussian_blur,
    gaussian_noise,
    illumination_gradient,
    impulse_noise,
    rectangular_occlusion,
)


def _image() -> np.ndarray:
    image = np.zeros((40, 60), dtype=np.uint8)
    image[8:32, 12:48] = 180
    image[16:24, 24:36] = 255
    return image


def test_gaussian_noise_is_deterministic_for_same_seed() -> None:
    image = _image()
    first = gaussian_noise(image, sigma_fraction=0.04, rng=np.random.default_rng(7))
    second = gaussian_noise(image, sigma_fraction=0.04, rng=np.random.default_rng(7))
    assert np.array_equal(first, second)


def test_zero_gaussian_noise_preserves_image() -> None:
    image = _image()
    result = gaussian_noise(image, sigma_fraction=0.0, rng=np.random.default_rng(1))
    assert np.array_equal(result, image)


def test_impulse_noise_is_deterministic_and_bounded() -> None:
    image = _image()
    first = impulse_noise(image, probability=0.08, rng=np.random.default_rng(9))
    second = impulse_noise(image, probability=0.08, rng=np.random.default_rng(9))
    assert np.array_equal(first, second)
    assert first.dtype == image.dtype
    assert int(first.min()) >= 0
    assert int(first.max()) <= 255


def test_zero_impulse_noise_preserves_image() -> None:
    image = _image()
    result = impulse_noise(image, probability=0.0, rng=np.random.default_rng(2))
    assert np.array_equal(result, image)


def test_gaussian_blur_preserves_shape_and_dtype() -> None:
    image = _image()
    result = gaussian_blur(image, sigma=1.4)
    assert result.shape == image.shape
    assert result.dtype == image.dtype
    assert np.var(result.astype(np.float64)) < np.var(image.astype(np.float64))


def test_zero_blur_preserves_image() -> None:
    image = _image()
    assert np.array_equal(gaussian_blur(image, sigma=0.0), image)


def test_contrast_factor_one_preserves_image() -> None:
    image = _image()
    assert np.array_equal(adjust_contrast(image, factor=1.0), image)


def test_gamma_one_preserves_image() -> None:
    image = _image()
    assert np.array_equal(adjust_gamma(image, gamma=1.0), image)


def test_zero_illumination_gradient_preserves_image() -> None:
    image = _image()
    result = illumination_gradient(image, strength_fraction=0.0, direction="diagonal")
    assert np.array_equal(result, image)


def test_illumination_gradient_changes_brightness_across_image() -> None:
    image = np.full((20, 30), 128, dtype=np.uint8)
    result = illumination_gradient(image, strength_fraction=0.20, direction="horizontal")
    assert float(np.mean(result[:, -3:])) > float(np.mean(result[:, :3]))


def test_rectangular_occlusion_returns_binary_visibility_mask() -> None:
    image = _image()
    result, visibility, box = rectangular_occlusion(
        image,
        area_fraction=0.16,
        rng=np.random.default_rng(4),
    )
    assert result.shape == image.shape
    assert visibility.shape == image.shape
    assert set(np.unique(visibility)).issubset({0, 1})
    assert np.any(visibility == 0)
    assert box["right"] > box["left"]
    assert box["bottom"] > box["top"]


def test_apply_degradation_records_parameters() -> None:
    result = apply_degradation(
        _image(),
        {"type": "gaussian_noise", "sigma_fraction": 0.05},
        rng=np.random.default_rng(3),
    )
    assert result.metadata == {"type": "gaussian_noise", "sigma_fraction": 0.05}
    assert np.all(result.visibility_mask == 1)


def test_occlusion_dispatch_records_box_and_visibility() -> None:
    result = apply_degradation(
        _image(),
        {"type": "rectangular_occlusion", "area_fraction": 0.10},
        rng=np.random.default_rng(3),
    )
    assert result.metadata["type"] == "rectangular_occlusion"
    assert "box" in result.metadata
    assert np.any(result.visibility_mask == 0)


def test_unknown_degradation_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported degradation"):
        apply_degradation(_image(), {"type": "jpeg_artifact"}, rng=np.random.default_rng(1))


def test_invalid_probability_is_rejected() -> None:
    with pytest.raises(ValueError, match="probability"):
        impulse_noise(_image(), probability=1.2, rng=np.random.default_rng(1))


def test_invalid_gamma_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        adjust_gamma(_image(), gamma=0.0)


def test_invalid_illumination_direction_is_rejected() -> None:
    with pytest.raises(ValueError, match="direction"):
        illumination_gradient(_image(), strength_fraction=0.1, direction="radial")
