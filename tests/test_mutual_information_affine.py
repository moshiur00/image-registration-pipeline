from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from image_registration.config import load_config
from image_registration.mutual_information import (
    MutualInformationAffineRegistration,
    MutualInformationConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "week05_day03_mi_affine_multiresolution.yaml"


def test_day23_config_reuses_frozen_day22_choices() -> None:
    config = load_config(CONFIG_PATH)
    frozen = config["frozen_mutual_information"]
    preprocessing = config["frozen_preprocessing"]
    assert frozen["histogram_bins"] == 32
    assert frozen["sampling_strategy"] == "none"
    assert frozen["initialization"] == "identity"
    assert frozen["shrink_factors"] == [4, 2, 1]
    assert frozen["smoothing_sigmas"] == [2.0, 1.0, 0.0]
    assert preprocessing == {"type": "gaussian_smooth", "sigma": 1.0}


def test_day23_config_contains_single_and_multiresolution_affine_variants() -> None:
    config = load_config(CONFIG_PATH)
    variants = config["variants"]
    assert set(variants) == {"affine_single_resolution", "affine_multiresolution"}
    assert variants["affine_single_resolution"]["shrink_factors"] == [1]
    assert variants["affine_multiresolution"]["shrink_factors"] == [4, 2, 1]


def test_day23_config_preserves_difficult_and_model_mismatch_cases() -> None:
    config = load_config(CONFIG_PATH)
    cases = {str(item["id"]): item for item in config["cases"]}
    assert "camera_affine_partial_overlap" in cases
    assert cases["camera_affine_partial_overlap"]["postprocess"]["type"] == "restricted_fov"
    assert cases["camera_affine_histogram"]["modality_mapping"]["type"] == "histogram_remap"
    assert cases["moon_affine_edge"]["modality_mapping"]["type"] == "edge_emphasized"
    assert set(config["rigid_comparator"]["case_ids"]).issubset(cases)


def test_affine_mi_returns_project_direction_transform() -> None:
    pytest.importorskip("SimpleITK")
    yy, xx = np.indices((96, 96), dtype=np.float32)
    fixed = np.exp(-((xx - 48.0) ** 2 + (yy - 48.0) ** 2) / (2.0 * 12.0**2))
    fixed += 0.4 * np.exp(-((xx - 30.0) ** 2 + (yy - 65.0) ** 2) / (2.0 * 7.0**2))
    config = MutualInformationConfig(
        histogram_bins=32,
        sampling_strategy="none",
        number_of_iterations=50,
        shrink_factors=(2, 1),
        smoothing_sigmas=(1.0, 0.0),
        initialization="identity",
    )
    result = MutualInformationAffineRegistration(config).register(fixed, fixed.copy())
    assert result.success is True
    fixed_to_moving = np.asarray(
        result.convergence_info["fixed_to_moving_physical_matrix"],
        dtype=np.float64,
    )
    assert result.transform @ fixed_to_moving == pytest.approx(np.eye(3), abs=1e-8)
    assert fixed_to_moving @ result.transform == pytest.approx(np.eye(3), abs=1e-8)
    assert result.registered_image.shape == fixed.shape
    assert result.convergence_info["transform_model"] == "affine"


def test_affine_mi_rejects_non_2d_sitk_input() -> None:
    sitk = pytest.importorskip("SimpleITK")
    image = sitk.GetImageFromArray(np.zeros((4, 16, 16), dtype=np.float32))
    registration = MutualInformationAffineRegistration(MutualInformationConfig())
    with pytest.raises(ValueError, match="2D images only"):
        registration.register_sitk(image, image)
