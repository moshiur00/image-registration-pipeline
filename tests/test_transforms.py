import numpy as np
import pytest

from image_registration.transforms import (
    apply_transform,
    compose_transforms,
    from_homogeneous,
    identity_matrix,
    invert_transform,
    to_homogeneous,
    translation_matrix,
)


def test_identity_transform_preserves_point() -> None:
    point = np.array([17.25, 9.5])
    result = apply_transform(point, identity_matrix())
    assert np.allclose(result, point, atol=1e-12)


def test_known_translation_moves_point_in_xy_order() -> None:
    point_moving = np.array([100.0, 100.0])
    transform_mf = translation_matrix(tx=30.0, ty=20.0)
    point_fixed = apply_transform(point_moving, transform_mf)
    assert np.allclose(point_fixed, [130.0, 120.0], atol=1e-12)


def test_inverse_translation_recovers_original_point() -> None:
    original = np.array([100.0, 100.0])
    transform = translation_matrix(tx=30.0, ty=-15.0)
    transformed = apply_transform(original, transform)
    recovered = apply_transform(transformed, invert_transform(transform))
    assert np.allclose(recovered, original, atol=1e-12)


def test_transform_composition_uses_application_order() -> None:
    point = np.array([10.0, 20.0])
    first = translation_matrix(5.0, 0.0)
    second = translation_matrix(0.0, 7.0)

    sequential = apply_transform(apply_transform(point, first), second)
    composed = apply_transform(point, compose_transforms(first, second))

    assert np.allclose(sequential, [15.0, 27.0], atol=1e-12)
    assert np.allclose(composed, sequential, atol=1e-12)


def test_multiple_points_are_transformed_vectorially() -> None:
    points = np.array([[0.0, 0.0], [10.0, 20.0], [-5.0, 2.0]])
    result = apply_transform(points, translation_matrix(3.0, -4.0))
    expected = np.array([[3.0, -4.0], [13.0, 16.0], [-2.0, -2.0]])
    assert np.allclose(result, expected, atol=1e-12)


def test_homogeneous_round_trip_single_and_multiple_points() -> None:
    single = np.array([4.0, 8.0])
    multiple = np.array([[1.0, 2.0], [3.0, 4.0]])

    assert np.allclose(from_homogeneous(to_homogeneous(single)), single)
    assert np.allclose(from_homogeneous(to_homogeneous(multiple)), multiple)


def test_invalid_point_shape_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_homogeneous([1.0, 2.0, 3.0])


def test_singular_transform_is_rejected_on_inversion() -> None:
    singular = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    with pytest.raises(ValueError, match="singular"):
        invert_transform(singular)


def test_positive_90_degree_rotation_is_counterclockwise_in_display() -> None:
    from image_registration.transforms import rotation_matrix

    point_to_right = np.array([1.0, 0.0])
    rotated = apply_transform(point_to_right, rotation_matrix(90.0))
    # Image y grows downward, so visually "up" is negative y.
    assert np.allclose(rotated, [0.0, -1.0], atol=1e-12)


def test_zero_degree_rotation_is_identity() -> None:
    from image_registration.transforms import rotation_matrix

    assert np.allclose(rotation_matrix(0.0), identity_matrix(), atol=1e-12)


def test_known_centered_rigid_transform() -> None:
    from image_registration.transforms import rigid_matrix

    point = np.array([120.0, 100.0])
    transform = rigid_matrix(
        angle_degrees=90.0,
        tx=10.0,
        ty=5.0,
        center=[100.0, 100.0],
    )
    result = apply_transform(point, transform)
    assert np.allclose(result, [110.0, 85.0], atol=1e-12)


def test_rotation_center_is_fixed_without_translation() -> None:
    from image_registration.transforms import rigid_matrix

    center = np.array([73.5, 41.25])
    transform = rigid_matrix(37.0, center=center)
    result = apply_transform(center, transform)
    assert np.allclose(result, center, atol=1e-12)


def test_rigid_transform_preserves_pairwise_distance() -> None:
    from image_registration.transforms import rigid_matrix

    points = np.array([[10.0, 20.0], [42.0, -3.0]])
    original_distance = np.linalg.norm(points[1] - points[0])

    transform = rigid_matrix(31.0, tx=17.0, ty=-8.0, center=[5.0, 7.0])
    transformed = apply_transform(points, transform)
    transformed_distance = np.linalg.norm(transformed[1] - transformed[0])

    assert np.isclose(transformed_distance, original_distance, atol=1e-12)


def test_rigid_linear_block_is_orthonormal_with_unit_determinant() -> None:
    from image_registration.transforms import rigid_matrix

    linear = rigid_matrix(-23.0, tx=4.0, ty=9.0)[:2, :2]
    assert np.allclose(linear.T @ linear, np.eye(2), atol=1e-12)
    assert np.isclose(np.linalg.det(linear), 1.0, atol=1e-12)


def test_rigid_inverse_recovers_multiple_points() -> None:
    from image_registration.transforms import rigid_matrix

    points = np.array([[0.0, 0.0], [20.0, 10.0], [-8.0, 4.0]])
    transform = rigid_matrix(64.0, tx=13.0, ty=-11.0, center=[3.0, 2.0])
    transformed = apply_transform(points, transform)
    recovered = apply_transform(transformed, invert_transform(transform))
    assert np.allclose(recovered, points, atol=1e-11)


def test_known_similarity_transform_about_center() -> None:
    from image_registration.transforms import similarity_matrix

    point = np.array([11.0, 10.0])
    transform = similarity_matrix(
        scale=2.0,
        angle_degrees=90.0,
        tx=3.0,
        ty=-1.0,
        center=[10.0, 10.0],
    )
    result = apply_transform(point, transform)
    assert np.allclose(result, [13.0, 7.0], atol=1e-12)


def test_similarity_scales_all_distances_uniformly() -> None:
    from image_registration.transforms import similarity_matrix

    points = np.array([[2.0, 3.0], [12.0, 8.0]])
    scale = 1.7
    original_distance = np.linalg.norm(points[1] - points[0])
    transformed = apply_transform(
        points,
        similarity_matrix(scale, 23.0, tx=5.0, ty=-9.0, center=[4.0, 6.0]),
    )
    transformed_distance = np.linalg.norm(transformed[1] - transformed[0])
    assert np.isclose(transformed_distance, scale * original_distance, atol=1e-11)


def test_similarity_linear_block_has_expected_metric_properties() -> None:
    from image_registration.transforms import similarity_matrix

    scale = 1.25
    linear = similarity_matrix(scale, -31.0)[:2, :2]
    assert np.allclose(linear.T @ linear, (scale**2) * np.eye(2), atol=1e-12)
    assert np.isclose(np.linalg.det(linear), scale**2, atol=1e-12)


def test_similarity_rejects_non_positive_scale() -> None:
    from image_registration.transforms import similarity_matrix

    with pytest.raises(ValueError, match="greater than zero"):
        similarity_matrix(0.0)


def test_known_affine_transform() -> None:
    from image_registration.transforms import affine_matrix

    linear = np.array([[2.0, 0.5], [-0.25, 1.5]])
    transform = affine_matrix(linear, tx=4.0, ty=-3.0)
    point = np.array([10.0, 8.0])
    expected = linear @ point + np.array([4.0, -3.0])
    result = apply_transform(point, transform)
    assert np.allclose(result, expected, atol=1e-12)


def test_affine_center_remains_fixed_without_translation() -> None:
    from image_registration.transforms import affine_matrix

    center = np.array([25.0, 40.0])
    linear = np.array([[1.2, 0.15], [-0.1, 0.9]])
    transform = affine_matrix(linear, center=center)
    result = apply_transform(center, transform)
    assert np.allclose(result, center, atol=1e-12)


def test_affine_inverse_recovers_points() -> None:
    from image_registration.transforms import affine_matrix

    points = np.array([[0.0, 1.0], [10.0, 20.0], [-5.0, 7.0]])
    transform = affine_matrix(
        [[1.1, 0.2], [-0.05, 0.85]],
        tx=9.0,
        ty=-4.0,
        center=[3.0, 2.0],
    )
    transformed = apply_transform(points, transform)
    recovered = apply_transform(transformed, invert_transform(transform))
    assert np.allclose(recovered, points, atol=1e-11)


def test_affine_rejects_singular_linear_component() -> None:
    from image_registration.transforms import affine_matrix

    with pytest.raises(ValueError, match="non-singular"):
        affine_matrix([[1.0, 2.0], [2.0, 4.0]])
