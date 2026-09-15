import numpy as np
import pytest

from image_registration.multimodal import (
    apply_multimodal_mapping,
    edge_emphasized_representation,
    histogram_remap,
    intensity_inversion,
    modality_specific_noise,
    multiplicative_bias_field,
    nonlinear_gamma_mapping,
)


def _image() -> np.ndarray:
    image = np.zeros((48, 64), dtype=np.uint8)
    image[8:40, 10:54] = 70
    image[14:34, 18:46] = 150
    image[20:28, 26:38] = 240
    return image


def test_intensity_inversion_preserves_shape_and_dtype() -> None:
    image = _image()
    result = intensity_inversion(image)
    assert result.shape == image.shape
    assert result.dtype == image.dtype
    assert result[0, 0] == 240
    assert result[24, 32] == 0


def test_gamma_mapping_changes_midrange_but_preserves_extrema() -> None:
    image = _image()
    result = nonlinear_gamma_mapping(image, gamma=2.0)
    assert result.dtype == image.dtype
    assert result.min() == image.min()
    assert result.max() == image.max()
    assert result[10, 12] < image[10, 12]


def test_gamma_mapping_rejects_nonpositive_gamma() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        nonlinear_gamma_mapping(_image(), gamma=0.0)


def test_histogram_remap_is_deterministic_and_preserves_dtype() -> None:
    image = _image()
    result = histogram_remap(
        image,
        input_knots=[0.0, 0.3, 0.6, 1.0],
        output_knots=[0.0, 0.1, 0.8, 1.0],
    )
    repeated = histogram_remap(
        image,
        input_knots=[0.0, 0.3, 0.6, 1.0],
        output_knots=[0.0, 0.1, 0.8, 1.0],
    )
    assert np.array_equal(result, repeated)
    assert result.dtype == image.dtype
    assert not np.array_equal(result, image)


def test_histogram_remap_rejects_nonmonotonic_output() -> None:
    with pytest.raises(ValueError, match="monotonic"):
        histogram_remap(
            _image(),
            input_knots=[0.0, 0.5, 1.0],
            output_knots=[0.0, 0.8, 0.4],
        )


def test_bias_field_changes_spatial_intensity_without_changing_shape() -> None:
    image = np.full((60, 80), 120, dtype=np.uint8)
    result = multiplicative_bias_field(
        image,
        strength_fraction=0.4,
        center_x_fraction=0.25,
        center_y_fraction=0.35,
        sigma_fraction=0.3,
    )
    assert result.shape == image.shape
    assert result.dtype == image.dtype
    assert result[20, 20] != result[-1, -1]


def test_bias_field_rejects_invalid_strength() -> None:
    with pytest.raises(ValueError, match="strength_fraction"):
        multiplicative_bias_field(_image(), strength_fraction=1.2)


def test_edge_emphasized_representation_highlights_edges() -> None:
    image = _image()
    result = edge_emphasized_representation(image, blend=1.0)
    assert result.shape == image.shape
    assert result.dtype == image.dtype
    assert np.max(result) > 0
    assert not np.array_equal(result, image)


def test_edge_emphasized_rejects_invalid_blend() -> None:
    with pytest.raises(ValueError, match="blend"):
        edge_emphasized_representation(_image(), blend=-0.1)


def test_modality_specific_noise_is_seed_deterministic() -> None:
    image = _image()
    first = modality_specific_noise(
        image,
        base_sigma_fraction=0.01,
        signal_sigma_fraction=0.03,
        rng=np.random.default_rng(42),
    )
    second = modality_specific_noise(
        image,
        base_sigma_fraction=0.01,
        signal_sigma_fraction=0.03,
        rng=np.random.default_rng(42),
    )
    assert np.array_equal(first, second)


def test_modality_specific_noise_changes_with_seed() -> None:
    image = _image()
    first = modality_specific_noise(
        image,
        base_sigma_fraction=0.01,
        signal_sigma_fraction=0.03,
        rng=np.random.default_rng(1),
    )
    second = modality_specific_noise(
        image,
        base_sigma_fraction=0.01,
        signal_sigma_fraction=0.03,
        rng=np.random.default_rng(2),
    )
    assert not np.array_equal(first, second)


def test_mapping_dispatch_records_parameters() -> None:
    result = apply_multimodal_mapping(
        _image(),
        {"type": "nonlinear_gamma", "gamma": 1.8},
        rng=np.random.default_rng(4),
    )
    assert result.metadata == {"type": "nonlinear_gamma", "gamma": 1.8}


def test_mapping_dispatch_can_add_modality_noise() -> None:
    result = apply_multimodal_mapping(
        _image(),
        {
            "type": "intensity_inversion",
            "noise_base_sigma_fraction": 0.01,
            "noise_signal_sigma_fraction": 0.02,
        },
        rng=np.random.default_rng(4),
    )
    assert "modality_specific_noise" in result.metadata


def test_unknown_mapping_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported multimodal"):
        apply_multimodal_mapping(
            _image(),
            {"type": "unknown_modality"},
            rng=np.random.default_rng(0),
        )


def test_multimodal_mapping_requires_grayscale() -> None:
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="2D grayscale"):
        intensity_inversion(image)
