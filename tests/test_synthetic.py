import numpy as np
import pytest

from image_registration.synthetic import (
    control_point_round_trip_error,
    default_control_points,
    generate_synthetic_pair,
    image_center,
    sample_ground_truth_transform,
)
from image_registration.transforms import apply_transform, invert_transform


def _test_image() -> np.ndarray:
    image = np.zeros((80, 120), dtype=np.uint8)
    image[20:60, 30:90] = 180
    image[32:48, 46:74] = 255
    return image


def test_image_center_uses_xy_coordinates() -> None:
    assert np.allclose(image_center((80, 120)), [59.5, 39.5])


def test_same_seed_produces_same_rigid_transform() -> None:
    ranges = {
        "tx": [-12.0, 12.0],
        "ty": [-8.0, 8.0],
        "angle_degrees": [-10.0, 10.0],
    }
    first = sample_ground_truth_transform(
        "rigid", np.random.default_rng(42), (80, 120), ranges
    )
    second = sample_ground_truth_transform(
        "rigid", np.random.default_rng(42), (80, 120), ranges
    )
    assert first.parameters == second.parameters
    assert np.allclose(first.moving_to_fixed, second.moving_to_fixed)


def test_different_seed_changes_sampled_transform() -> None:
    ranges = {"tx": [-20.0, 20.0], "ty": [-20.0, 20.0]}
    first = sample_ground_truth_transform(
        "translation", np.random.default_rng(1), (80, 120), ranges
    )
    second = sample_ground_truth_transform(
        "translation", np.random.default_rng(2), (80, 120), ranges
    )
    assert not np.allclose(first.moving_to_fixed, second.moving_to_fixed)


def test_translation_parameters_stay_inside_ranges() -> None:
    ranges = {"tx": [-4.0, 7.0], "ty": [3.0, 9.0]}
    sample = sample_ground_truth_transform(
        "translation", np.random.default_rng(10), (80, 120), ranges
    )
    assert -4.0 <= sample.parameters["tx"] <= 7.0
    assert 3.0 <= sample.parameters["ty"] <= 9.0


def test_similarity_parameters_stay_inside_ranges() -> None:
    ranges = {
        "tx": [-5.0, 5.0],
        "ty": [-5.0, 5.0],
        "angle_degrees": [-8.0, 8.0],
        "scale": [0.9, 1.1],
    }
    sample = sample_ground_truth_transform(
        "similarity", np.random.default_rng(5), (80, 120), ranges
    )
    assert 0.9 <= sample.parameters["scale"] <= 1.1
    assert -8.0 <= sample.parameters["angle_degrees"] <= 8.0


def test_affine_sample_is_non_singular() -> None:
    ranges = {
        "tx": [-5.0, 5.0],
        "ty": [-5.0, 5.0],
        "angle_degrees": [-12.0, 12.0],
        "scale_x": [0.85, 1.15],
        "scale_y": [0.85, 1.15],
        "shear_x": [-0.12, 0.12],
    }
    sample = sample_ground_truth_transform(
        "affine", np.random.default_rng(7), (80, 120), ranges
    )
    determinant = np.linalg.det(sample.moving_to_fixed[:2, :2])
    assert not np.isclose(determinant, 0.0)


def test_fixed_to_moving_is_exact_inverse() -> None:
    sample = sample_ground_truth_transform(
        "rigid",
        np.random.default_rng(42),
        (80, 120),
        {"tx": [7.0, 7.0], "ty": [-4.0, -4.0], "angle_degrees": [6.0, 6.0]},
    )
    assert np.allclose(
        sample.fixed_to_moving,
        invert_transform(sample.moving_to_fixed),
        atol=1e-12,
    )
    assert np.allclose(sample.moving_to_fixed @ sample.fixed_to_moving, np.eye(3), atol=1e-12)


def test_control_points_are_inside_source_image() -> None:
    points = default_control_points((80, 120))
    assert np.all(points[:, 0] >= 0.0)
    assert np.all(points[:, 0] <= 119.0)
    assert np.all(points[:, 1] >= 0.0)
    assert np.all(points[:, 1] <= 79.0)


def test_control_point_correspondence_matches_manual_translation() -> None:
    sample = sample_ground_truth_transform(
        "translation",
        np.random.default_rng(0),
        (80, 120),
        {"tx": [8.0, 8.0], "ty": [-3.0, -3.0]},
    )
    fixed_points = np.array([[20.0, 30.0], [70.0, 50.0]])
    moving_points = apply_transform(fixed_points, sample.fixed_to_moving)
    expected_moving = fixed_points - np.array([8.0, -3.0])
    assert np.allclose(moving_points, expected_moving, atol=1e-12)
    recovered = apply_transform(moving_points, sample.moving_to_fixed)
    assert np.allclose(recovered, fixed_points, atol=1e-12)


def test_generated_pair_has_exact_control_point_round_trip() -> None:
    sample = sample_ground_truth_transform(
        "similarity",
        np.random.default_rng(21),
        (80, 120),
        {
            "tx": [-6.0, 6.0],
            "ty": [-6.0, 6.0],
            "angle_degrees": [-5.0, 5.0],
            "scale": [0.95, 1.05],
        },
    )
    pair = generate_synthetic_pair(_test_image(), sample)
    errors = control_point_round_trip_error(pair)
    assert np.max(errors) < 1e-10


def test_generated_pair_preserves_shape_and_dtype() -> None:
    fixed = _test_image()
    sample = sample_ground_truth_transform(
        "translation",
        np.random.default_rng(1),
        fixed.shape,
        {"tx": [4.0, 4.0], "ty": [3.0, 3.0]},
    )
    pair = generate_synthetic_pair(fixed, sample)
    assert pair.fixed.shape == fixed.shape
    assert pair.moving.shape == fixed.shape
    assert pair.moving.dtype == fixed.dtype


def test_invalid_transform_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="transform_type"):
        sample_ground_truth_transform("projective", np.random.default_rng(0), (80, 120), {})


def test_invalid_range_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum"):
        sample_ground_truth_transform(
            "translation",
            np.random.default_rng(0),
            (80, 120),
            {"tx": [5.0, -5.0]},
        )


def test_sampled_rigid_matrix_matches_stored_parameters() -> None:
    from image_registration.transforms import rigid_matrix

    sample = sample_ground_truth_transform(
        "rigid",
        np.random.default_rng(11),
        (80, 120),
        {"tx": [-8.0, 8.0], "ty": [-6.0, 6.0], "angle_degrees": [-9.0, 9.0]},
    )
    params = sample.parameters
    expected = rigid_matrix(
        params["angle_degrees"],
        tx=params["tx"],
        ty=params["ty"],
        center=params["center"],
    )
    assert np.allclose(sample.moving_to_fixed, expected, atol=1e-12)


def test_sampled_similarity_matrix_matches_stored_parameters() -> None:
    from image_registration.transforms import similarity_matrix

    sample = sample_ground_truth_transform(
        "similarity",
        np.random.default_rng(12),
        (80, 120),
        {
            "tx": [-8.0, 8.0],
            "ty": [-6.0, 6.0],
            "angle_degrees": [-9.0, 9.0],
            "scale": [0.9, 1.1],
        },
    )
    params = sample.parameters
    expected = similarity_matrix(
        params["scale"],
        params["angle_degrees"],
        tx=params["tx"],
        ty=params["ty"],
        center=params["center"],
    )
    assert np.allclose(sample.moving_to_fixed, expected, atol=1e-12)


def test_sampled_affine_matrix_matches_stored_linear_component() -> None:
    from image_registration.transforms import affine_matrix

    sample = sample_ground_truth_transform(
        "affine",
        np.random.default_rng(13),
        (80, 120),
        {
            "tx": [-8.0, 8.0],
            "ty": [-6.0, 6.0],
            "angle_degrees": [-9.0, 9.0],
            "scale_x": [0.9, 1.1],
            "scale_y": [0.9, 1.1],
            "shear_x": [-0.1, 0.1],
        },
    )
    params = sample.parameters
    expected = affine_matrix(
        params["linear"],
        tx=params["tx"],
        ty=params["ty"],
        center=params["center"],
    )
    assert np.allclose(sample.moving_to_fixed, expected, atol=1e-12)


def test_zero_translation_generates_identical_pair() -> None:
    fixed = _test_image()
    sample = sample_ground_truth_transform(
        "translation",
        np.random.default_rng(0),
        fixed.shape,
        {"tx": [0.0, 0.0], "ty": [0.0, 0.0]},
    )
    pair = generate_synthetic_pair(fixed, sample, interpolation="nearest")
    assert np.array_equal(pair.moving, fixed)
