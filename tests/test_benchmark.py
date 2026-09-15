from __future__ import annotations

import copy

import numpy as np
import pytest

from image_registration.benchmark import (
    benchmark_manifest_fingerprint,
    build_case_plan,
    sample_benchmark_ground_truth,
    validate_benchmark_records,
    validate_integrated_benchmark_config,
)
from image_registration.synthetic import generate_synthetic_pair, control_point_round_trip_error


def _tier(low: float, high: float) -> dict[str, list[float]]:
    return {
        "translation_abs_px": [low, high],
        "rotation_abs_degrees": [low, high],
        "scale_deviation_abs": [low / 100.0, high / 100.0],
        "affine_shear_abs": [low / 100.0, high / 100.0],
        "noise_base_sigma_fraction": [low / 1000.0, high / 1000.0],
        "noise_signal_sigma_fraction": [low / 500.0, high / 500.0],
    }


def _config() -> dict:
    return {
        "benchmark": {
            "samples_per_tier": 20,
            "transform_families": ["translation", "rigid", "similarity", "affine"],
        },
        "difficulty_tiers": {
            "easy": _tier(1.0, 2.0),
            "moderate": _tier(3.0, 4.0),
            "hard": _tier(5.0, 6.0),
        },
        "degradation_cases": [
            {"id": "noise", "type": "gaussian_noise"},
            {"id": "blur", "type": "gaussian_blur"},
            {"id": "gamma", "type": "gamma"},
            {"id": "illumination", "type": "illumination_gradient"},
        ],
        "multimodal_cases": [{"id": "invert", "type": "intensity_inversion"}],
    }


@pytest.mark.parametrize("family", ["translation", "rigid", "similarity", "affine"])
def test_sample_benchmark_ground_truth_is_invertible(family: str) -> None:
    rng = np.random.default_rng(7)
    transform = sample_benchmark_ground_truth(family, _tier(2.0, 3.0), rng, (128, 128))
    identity = transform.moving_to_fixed @ transform.fixed_to_moving
    assert np.allclose(identity, np.eye(3), atol=1e-10)


def test_sample_benchmark_ground_truth_is_deterministic() -> None:
    first = sample_benchmark_ground_truth("affine", _tier(2.0, 3.0), np.random.default_rng(11), (96, 96))
    second = sample_benchmark_ground_truth("affine", _tier(2.0, 3.0), np.random.default_rng(11), (96, 96))
    assert np.allclose(first.moving_to_fixed, second.moving_to_fixed)
    assert first.parameters == second.parameters


def test_sample_benchmark_ground_truth_round_trip_points() -> None:
    transform = sample_benchmark_ground_truth(
        "similarity", _tier(2.0, 3.0), np.random.default_rng(17), (128, 128)
    )
    fixed = np.zeros((128, 128), dtype=np.uint8)
    fixed[40:88, 45:90] = 180
    pair = generate_synthetic_pair(fixed, transform)
    assert np.max(control_point_round_trip_error(pair)) < 1e-8


def test_build_case_plan_has_expected_total() -> None:
    plan = build_case_plan(
        base_seed=42,
        samples_per_tier=20,
        tiers=("easy", "moderate", "hard"),
        source_ids=("a", "b", "c"),
        transform_families=("translation", "rigid", "similarity", "affine"),
        degradation_ids=("none", "noise", "blur", "gamma"),
        multimodal_ids=("invert", "edge"),
        restricted_fov_every=4,
    )
    assert len(plan) == 60


def test_build_case_plan_is_deterministic() -> None:
    kwargs = dict(
        base_seed=42,
        samples_per_tier=20,
        tiers=("easy", "moderate", "hard"),
        source_ids=("a", "b"),
        transform_families=("translation", "rigid", "similarity", "affine"),
        degradation_ids=("none", "noise", "blur", "gamma"),
        multimodal_ids=("invert", "edge"),
        restricted_fov_every=4,
    )
    first = build_case_plan(**kwargs)
    second = build_case_plan(**kwargs)
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]


def test_build_case_plan_balances_modalities() -> None:
    plan = build_case_plan(
        base_seed=5,
        samples_per_tier=20,
        tiers=("easy",),
        source_ids=("a",),
        transform_families=("translation", "rigid", "similarity", "affine"),
        degradation_ids=("none", "noise", "blur", "gamma"),
        multimodal_ids=("invert", "edge"),
        restricted_fov_every=4,
    )
    counts = {name: sum(item.modality_class == name for item in plan) for name in ("monomodal", "simulated_multimodal")}
    assert counts == {"monomodal": 10, "simulated_multimodal": 10}


def test_build_case_plan_covers_all_transform_families() -> None:
    plan = build_case_plan(
        base_seed=5,
        samples_per_tier=20,
        tiers=("easy",),
        source_ids=("a",),
        transform_families=("translation", "rigid", "similarity", "affine"),
        degradation_ids=("none", "noise", "blur", "gamma"),
        multimodal_ids=("invert",),
        restricted_fov_every=4,
    )
    assert {item.transform_family for item in plan} == {"translation", "rigid", "similarity", "affine"}


def test_build_case_plan_marks_restricted_fov_cases() -> None:
    plan = build_case_plan(
        base_seed=5,
        samples_per_tier=20,
        tiers=("easy",),
        source_ids=("a",),
        transform_families=("translation", "rigid", "similarity"),
        degradation_ids=("none", "noise", "blur", "gamma"),
        multimodal_ids=("invert",),
        restricted_fov_every=4,
    )
    assert sum(item.restricted_fov for item in plan) == 5


def test_manifest_fingerprint_is_order_sensitive_and_repeatable() -> None:
    records = [{"case_id": "a", "value": 1}, {"case_id": "b", "value": 2}]
    assert benchmark_manifest_fingerprint(records) == benchmark_manifest_fingerprint(copy.deepcopy(records))
    assert benchmark_manifest_fingerprint(records) != benchmark_manifest_fingerprint(list(reversed(records)))


def test_validate_integrated_benchmark_config_accepts_valid_config() -> None:
    validate_integrated_benchmark_config(_config())


def test_validate_integrated_benchmark_config_requires_twenty_per_tier() -> None:
    config = _config()
    config["benchmark"]["samples_per_tier"] = 19
    with pytest.raises(ValueError, match="at least 20"):
        validate_integrated_benchmark_config(config)


def test_validate_integrated_benchmark_config_requires_three_transform_families() -> None:
    config = _config()
    config["benchmark"]["transform_families"] = ["translation", "rigid"]
    with pytest.raises(ValueError, match="three transform families"):
        validate_integrated_benchmark_config(config)


def _record(case_id: str, tier: str, modality: str, family: str, degradation: str, restricted: bool = False) -> dict:
    return {
        "case_id": case_id,
        "tier": tier,
        "modality_class": modality,
        "transform_family": family,
        "degradation": {"type": degradation},
        "restricted_fov": restricted,
        "fixed_overlap_fraction": 0.8,
        "control_point_max_error_px": 0.0,
    }


def _valid_records() -> list[dict]:
    records = []
    families = ["translation", "rigid", "similarity", "affine"]
    degradations = ["gaussian_noise", "gaussian_blur", "gamma", "illumination_gradient", "none"]
    for tier in ("easy", "moderate", "hard"):
        for index in range(20):
            records.append(
                _record(
                    f"{tier}_{index:03d}",
                    tier,
                    "monomodal" if index % 2 == 0 else "simulated_multimodal",
                    families[index % len(families)],
                    degradations[index % len(degradations)],
                    restricted=(index % 4 == 0),
                )
            )
    return records


def test_validate_benchmark_records_returns_coverage() -> None:
    summary = validate_benchmark_records(_valid_records(), samples_per_tier=20)
    assert summary["total_records"] == 60
    assert summary["counts_by_tier"] == {"easy": 20, "moderate": 20, "hard": 20}
    assert summary["modality_counts"] == {"monomodal": 30, "simulated_multimodal": 30}
    assert len(summary["transform_families"]) == 4
    assert summary["restricted_fov_cases"] == 15


def test_validate_benchmark_records_rejects_duplicate_ids() -> None:
    records = _valid_records()
    records[1]["case_id"] = records[0]["case_id"]
    with pytest.raises(ValueError, match="unique"):
        validate_benchmark_records(records, samples_per_tier=20)


def test_validate_benchmark_records_rejects_bad_control_error() -> None:
    records = _valid_records()
    records[0]["control_point_max_error_px"] = 0.1
    with pytest.raises(ValueError, match="Control-point"):
        validate_benchmark_records(records, samples_per_tier=20)
