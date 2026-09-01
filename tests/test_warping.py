"""Tests for Day 3 image resampling utilities."""

import numpy as np
import pytest

from image_registration.transforms import identity_matrix, translation_matrix
from image_registration.warping import warp_image, warp_mask


def test_identity_warp_with_nearest_is_exact() -> None:
    image = np.arange(30, dtype=np.uint8).reshape(5, 6)
    warped = warp_image(image, identity_matrix(), interpolation="nearest")
    assert np.array_equal(warped, image)


def test_forward_translation_moves_pixel_to_expected_destination() -> None:
    image = np.zeros((8, 9), dtype=np.uint8)
    image[2, 2] = 255

    warped = warp_image(
        image,
        translation_matrix(tx=1.0, ty=2.0),
        output_shape=(8, 9),
        interpolation="nearest",
    )

    assert warped[4, 3] == 255
    assert np.count_nonzero(warped) == 1


def test_output_shape_is_height_width() -> None:
    image = np.ones((4, 5), dtype=np.uint8)
    warped = warp_image(image, identity_matrix(), output_shape=(7, 9))
    assert warped.shape == (7, 9)


def test_mask_warp_preserves_discrete_labels() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[4:10, 5:12] = 2
    mask[12:16, 3:9] = 7

    warped = warp_mask(mask, translation_matrix(2.0, -1.0), output_shape=mask.shape)

    assert set(np.unique(warped)).issubset({0, 2, 7})


def test_linear_interpolation_can_create_intermediate_values() -> None:
    image = np.zeros((6, 8), dtype=np.float32)
    image[:, 3:] = 100.0

    warped = warp_image(
        image,
        translation_matrix(0.5, 0.0),
        interpolation="linear",
    )

    assert np.any((warped > 0.0) & (warped < 100.0))


def test_unknown_interpolation_is_rejected() -> None:
    image = np.zeros((4, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="Unsupported interpolation"):
        warp_image(image, identity_matrix(), interpolation="lanczos")  # type: ignore[arg-type]


def test_invalid_output_shape_is_rejected() -> None:
    image = np.zeros((4, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="positive"):
        warp_image(image, identity_matrix(), output_shape=(0, 10))


def test_mask_must_be_two_dimensional() -> None:
    mask = np.zeros((5, 5, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="2D"):
        warp_mask(mask, identity_matrix())
