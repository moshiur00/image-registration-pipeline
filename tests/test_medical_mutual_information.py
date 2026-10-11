from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from image_registration.config import load_config
from image_registration.medical_mutual_information import (
    MedicalMutualInformationConfig,
    geometry_matches_3d,
    physical_domain_overlap_3d,
    rigid_transform_diagnostics_3d,
    sitk_transform_to_homogeneous_3d,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "week05_day04_rire_physical_registration.yaml"


def test_day24_config_uses_prepared_rire_pair_and_disables_unverified_metrics() -> None:
    config = load_config(CONFIG_PATH)
    assert config["dataset"]["manifest"] == "data/manifests/rire_training001.json"
    assert config["dataset"]["pair_id"] == "training001_mr_t1_to_ct"
    assert config["dataset"]["expected_fixed_modality"] == "CT"
    assert config["dataset"]["expected_moving_modality"] == "MR-T1"
    assert config["evaluation"]["landmark_tre_enabled"] is False
    assert config["evaluation"]["dice_enabled"] is False
    assert config["evaluation"]["anatomical_correctness_claim_allowed"] is False


def test_day24_config_preserves_frozen_day22_metric_choices() -> None:
    config = load_config(CONFIG_PATH)
    frozen = config["frozen_mutual_information"]
    assert frozen["histogram_bins"] == 32
    assert frozen["sampling_strategy"] == "none"
    assert frozen["shrink_factors"] == [4, 2, 1]
    assert frozen["smoothing_sigmas"] == [2.0, 1.0, 0.0]
    assert frozen["preprocessing_sigma_mm"] == pytest.approx(1.0)
    assert set(config["variants"]) == {"geometry_multiresolution", "identity_multiresolution"}


def test_medical_mi_config_requires_matching_pyramid_lengths() -> None:
    with pytest.raises(ValueError, match="equal length"):
        MedicalMutualInformationConfig(
            shrink_factors=(4, 2, 1),
            smoothing_sigmas=(2.0, 1.0),
        )


def test_rigid_transform_diagnostics_accepts_identity() -> None:
    diagnostics = rigid_transform_diagnostics_3d(
        np.eye(4),
        fixed_size_xyz=(64, 48, 20),
        fixed_spacing_xyz_mm=(1.0, 1.0, 2.0),
    )
    assert diagnostics["plausible"] is True
    assert diagnostics["determinant"] == pytest.approx(1.0)
    assert diagnostics["rotation_magnitude_degrees"] == pytest.approx(0.0)
    assert diagnostics["translation_norm_mm"] == pytest.approx(0.0)


def test_sitk_3d_transform_conversion_matches_transform_point() -> None:
    sitk = pytest.importorskip("SimpleITK")
    transform = sitk.Euler3DTransform()
    transform.SetCenter((20.0, 30.0, 12.0))
    transform.SetRotation(np.deg2rad(5.0), np.deg2rad(-7.0), np.deg2rad(11.0))
    transform.SetTranslation((4.0, -7.0, 3.0))
    matrix = sitk_transform_to_homogeneous_3d(transform)

    points = np.asarray(
        [[0.0, 0.0, 0.0], [3.0, 8.0, 2.0], [40.0, 12.0, 9.0]],
        dtype=np.float64,
    )
    homogeneous = np.column_stack((points, np.ones(len(points))))
    actual = (matrix @ homogeneous.T).T[:, :3]
    expected = np.asarray([transform.TransformPoint(tuple(point)) for point in points])
    assert actual == pytest.approx(expected, abs=1e-9)


def test_physical_domain_overlap_identity_is_complete_for_same_geometry() -> None:
    sitk = pytest.importorskip("SimpleITK")
    image = sitk.GetImageFromArray(np.zeros((6, 8, 10), dtype=np.float32))
    image.SetSpacing((0.8, 1.2, 2.5))
    identity = sitk.Transform(3, sitk.sitkIdentity)
    overlap = physical_domain_overlap_3d(image, image, identity)
    assert overlap["fixed_domain_covered_by_moving_fraction"] == pytest.approx(1.0)
    assert overlap["moving_domain_covered_by_fixed_fraction"] == pytest.approx(1.0)
    assert geometry_matches_3d(image, image) is True
