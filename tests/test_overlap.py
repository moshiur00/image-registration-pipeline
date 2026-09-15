import numpy as np
import pytest

from image_registration.overlap import (
    apply_field_of_view,
    combine_valid_masks,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
    transformed_support_mask,
)
from image_registration.transforms import identity_matrix, translation_matrix


def test_identity_transform_has_full_support() -> None:
    mask = transformed_support_mask((10, 12), identity_matrix())
    assert np.all(mask == 1)
    assert overlap_fraction(mask) == pytest.approx(1.0)


def test_horizontal_translation_reduces_overlap_as_expected() -> None:
    support = transformed_support_mask((10, 10), translation_matrix(2.0, 0.0))
    assert overlap_fraction(support) == pytest.approx(0.8)


def test_rectangular_fov_mask_has_requested_size() -> None:
    mask = rectangular_field_of_view_mask(
        (100, 200),
        width_fraction=0.5,
        height_fraction=0.6,
    )
    assert int(mask.sum()) == 100 * 60


def test_shifted_fov_mask_stays_inside_image() -> None:
    mask = rectangular_field_of_view_mask(
        (40, 60),
        width_fraction=0.7,
        height_fraction=0.8,
        center_x_fraction=0.2,
        center_y_fraction=0.75,
    )
    assert mask.shape == (40, 60)
    assert set(np.unique(mask)).issubset({0, 1})
    assert np.any(mask == 1)


def test_apply_field_of_view_zeros_hidden_pixels() -> None:
    image = np.full((10, 12), 90, dtype=np.uint8)
    mask = rectangular_field_of_view_mask(
        image.shape,
        width_fraction=0.5,
        height_fraction=0.5,
    )
    restricted = apply_field_of_view(image, mask)
    assert np.all(restricted[mask == 0] == 0)
    assert np.all(restricted[mask == 1] == 90)


def test_combine_valid_masks_uses_intersection() -> None:
    a = np.ones((6, 8), dtype=np.uint8)
    b = np.ones((6, 8), dtype=np.uint8)
    b[:, :3] = 0
    combined = combine_valid_masks(a, b)
    assert np.array_equal(combined, b)


def test_overlap_mask_maps_moving_validity_to_fixed_space() -> None:
    moving_valid = np.ones((10, 10), dtype=np.uint8)
    fixed_overlap = overlap_mask_in_fixed_space(
        moving_valid,
        translation_matrix(2.0, 0.0),
        fixed_shape=(10, 10),
    )
    assert overlap_fraction(fixed_overlap) == pytest.approx(0.8)


def test_restricted_fov_reduces_fixed_overlap() -> None:
    shape = (40, 60)
    moving_support = np.ones(shape, dtype=np.uint8)
    fov = rectangular_field_of_view_mask(
        shape,
        width_fraction=0.6,
        height_fraction=0.8,
    )
    moving_valid = combine_valid_masks(moving_support, fov)
    overlap = overlap_mask_in_fixed_space(
        moving_valid,
        identity_matrix(),
        fixed_shape=shape,
    )
    assert overlap_fraction(overlap) == pytest.approx(0.48)


def test_overlap_fraction_rejects_non_binary_mask() -> None:
    with pytest.raises(ValueError, match="only 0 and 1"):
        overlap_fraction(np.array([[0, 2]], dtype=np.uint8))


def test_combine_valid_masks_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="same shape"):
        combine_valid_masks(np.ones((3, 3), dtype=np.uint8), np.ones((4, 3), dtype=np.uint8))
