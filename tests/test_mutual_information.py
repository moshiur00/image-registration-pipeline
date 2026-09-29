from __future__ import annotations

import numpy as np
import pytest

from image_registration.mutual_information import (
    MutualInformationConfig,
    MutualInformationRigidRegistration,
    array_to_sitk_2d,
    sitk_transform_to_homogeneous_2d,
)
from image_registration.transforms import apply_transform


def test_mutual_information_config_rejects_invalid_sampling_strategy() -> None:
    with pytest.raises(ValueError, match="sampling_strategy"):
        MutualInformationConfig(sampling_strategy="unsupported")  # type: ignore[arg-type]


def test_mutual_information_config_requires_matching_pyramid_lengths() -> None:
    with pytest.raises(ValueError, match="equal length"):
        MutualInformationConfig(shrink_factors=(4, 2, 1), smoothing_sigmas=(2.0, 1.0))


def test_array_to_sitk_preserves_explicit_geometry() -> None:
    sitk = pytest.importorskip("SimpleITK")
    image = np.arange(30, dtype=np.float32).reshape(5, 6)
    output = array_to_sitk_2d(
        image,
        spacing_xy=(0.7, 1.3),
        origin_xy=(12.0, -4.0),
        direction=(0.0, -1.0, 1.0, 0.0),
    )
    assert output.GetSize() == (6, 5)
    assert output.GetSpacing() == pytest.approx((0.7, 1.3))
    assert output.GetOrigin() == pytest.approx((12.0, -4.0))
    assert output.GetDirection() == pytest.approx((0.0, -1.0, 1.0, 0.0))
    assert sitk.GetArrayFromImage(output) == pytest.approx(image)


def test_sitk_transform_conversion_matches_transform_point() -> None:
    sitk = pytest.importorskip("SimpleITK")
    transform = sitk.Euler2DTransform()
    transform.SetCenter((20.0, 30.0))
    transform.SetAngle(np.deg2rad(11.0))
    transform.SetTranslation((4.0, -7.0))
    matrix = sitk_transform_to_homogeneous_2d(transform)

    points = np.asarray([[0.0, 0.0], [3.0, 8.0], [40.0, 12.0]], dtype=np.float64)
    expected = np.asarray([transform.TransformPoint(tuple(point)) for point in points])
    actual = apply_transform(points, matrix)
    assert actual == pytest.approx(expected, abs=1e-9)


def test_rigid_mi_identity_case_returns_project_direction_matrix() -> None:
    pytest.importorskip("SimpleITK")
    yy, xx = np.indices((96, 96), dtype=np.float32)
    fixed = np.exp(-((xx - 48.0) ** 2 + (yy - 48.0) ** 2) / (2.0 * 12.0**2))
    fixed += 0.4 * np.exp(-((xx - 30.0) ** 2 + (yy - 65.0) ** 2) / (2.0 * 7.0**2))
    config = MutualInformationConfig(
        sampling_strategy="none",
        number_of_iterations=50,
        shrink_factors=(2, 1),
        smoothing_sigmas=(1.0, 0.0),
        initialization="identity",
    )
    result = MutualInformationRigidRegistration(config).register(fixed, fixed.copy())
    assert result.success is True
    assert result.transform == pytest.approx(np.eye(3), abs=0.25)
    assert result.registered_image.shape == fixed.shape
    assert "fixed_to_moving_physical_matrix" in result.convergence_info
