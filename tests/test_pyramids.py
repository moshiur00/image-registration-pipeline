from __future__ import annotations

import numpy as np
import pytest

from image_registration.pyramids import (
    build_image_pyramid,
    rescale_transform_between_shapes,
    validate_pyramid_scales,
)
from image_registration.transforms import affine_matrix, apply_transform, translation_matrix


def test_validate_pyramid_scales_accepts_coarse_to_full() -> None:
    assert validate_pyramid_scales([0.25, 0.5, 1.0]) == (0.25, 0.5, 1.0)


def test_validate_pyramid_scales_rejects_unsorted_values() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_pyramid_scales([0.5, 0.25, 1.0])


def test_validate_pyramid_scales_requires_full_resolution_last() -> None:
    with pytest.raises(ValueError, match="final pyramid scale"):
        validate_pyramid_scales([0.25, 0.5])


def test_build_image_pyramid_has_expected_shapes() -> None:
    image = np.arange(128 * 96, dtype=np.float32).reshape(128, 96)
    levels = build_image_pyramid(image, [0.25, 0.5, 1.0], pre_smoothing_sigma=0.0)
    assert [level.shape for level in levels] == [(32, 24), (64, 48), (128, 96)]


def test_build_image_pyramid_preserves_full_resolution_values() -> None:
    image = np.arange(64, dtype=np.float32).reshape(8, 8)
    levels = build_image_pyramid(image, [0.5, 1.0])
    assert np.array_equal(levels[-1].image, image)


def test_rescale_translation_between_shapes() -> None:
    transform = translation_matrix(20.0, -12.0)
    scaled = rescale_transform_between_shapes(transform, (200, 100), (100, 50))
    assert np.allclose(scaled[:2, 2], [10.0, -6.0])


def test_transform_rescaling_round_trip_recovers_original() -> None:
    transform = affine_matrix([[1.05, 0.08], [-0.03, 0.96]], tx=18.0, ty=-11.0)
    coarse = rescale_transform_between_shapes(transform, (256, 256), (64, 64))
    recovered = rescale_transform_between_shapes(coarse, (64, 64), (256, 256))
    assert np.allclose(recovered, transform)


def test_affine_rescaling_preserves_point_mapping_in_scaled_coordinates() -> None:
    transform = affine_matrix([[1.1, 0.05], [-0.02, 0.9]], tx=12.0, ty=-8.0)
    coarse = rescale_transform_between_shapes(transform, (200, 100), (100, 50))
    full_point = np.array([40.0, 60.0])
    coarse_point = np.array([20.0, 30.0])
    full_mapped = apply_transform(full_point, transform)
    coarse_mapped = apply_transform(coarse_point, coarse)
    assert np.allclose(coarse_mapped, full_mapped * 0.5)
