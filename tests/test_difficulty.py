import numpy as np
import pytest

from image_registration.difficulty import (
    sample_similarity_difficulty,
    validate_difficulty_tiers,
)
from image_registration.transforms import apply_transform


def _tiers() -> dict:
    return {
        "easy": {
            "translation_abs_px": [2.0, 5.0],
            "rotation_abs_degrees": [1.0, 3.0],
            "scale_deviation_abs": [0.01, 0.03],
            "noise_base_sigma_fraction": [0.002, 0.008],
            "noise_signal_sigma_fraction": [0.004, 0.012],
        },
        "moderate": {
            "translation_abs_px": [7.0, 12.0],
            "rotation_abs_degrees": [5.0, 8.0],
            "scale_deviation_abs": [0.05, 0.08],
            "noise_base_sigma_fraction": [0.012, 0.025],
            "noise_signal_sigma_fraction": [0.020, 0.040],
        },
        "hard": {
            "translation_abs_px": [15.0, 22.0],
            "rotation_abs_degrees": [11.0, 16.0],
            "scale_deviation_abs": [0.11, 0.16],
            "noise_base_sigma_fraction": [0.035, 0.055],
            "noise_signal_sigma_fraction": [0.055, 0.085],
        },
    }


def test_valid_non_overlapping_tiers_are_accepted() -> None:
    validate_difficulty_tiers(_tiers())


def test_missing_tier_is_rejected() -> None:
    tiers = _tiers()
    tiers.pop("hard")
    with pytest.raises(ValueError, match="Missing difficulty tier"):
        validate_difficulty_tiers(tiers)


def test_overlapping_intervals_are_rejected() -> None:
    tiers = _tiers()
    tiers["moderate"]["translation_abs_px"] = [4.5, 12.0]
    with pytest.raises(ValueError, match="non-overlapping"):
        validate_difficulty_tiers(tiers)


def test_same_seed_produces_same_difficulty_sample() -> None:
    spec = _tiers()["moderate"]
    first = sample_similarity_difficulty(
        "moderate", spec, np.random.default_rng(42), (100, 140)
    )
    second = sample_similarity_difficulty(
        "moderate", spec, np.random.default_rng(42), (100, 140)
    )
    assert first.severity == second.severity
    assert first.ground_truth.parameters == second.ground_truth.parameters
    assert np.allclose(first.ground_truth.moving_to_fixed, second.ground_truth.moving_to_fixed)


def test_sample_stays_inside_easy_ranges() -> None:
    sample = sample_similarity_difficulty(
        "easy", _tiers()["easy"], np.random.default_rng(8), (100, 140)
    )
    params = sample.ground_truth.parameters
    severity = sample.severity
    assert 2.0 <= abs(params["tx"]) <= 5.0
    assert 2.0 <= abs(params["ty"]) <= 5.0
    assert 1.0 <= abs(params["angle_degrees"]) <= 3.0
    assert 0.01 <= abs(params["scale"] - 1.0) <= 0.03
    assert 0.002 <= severity["noise_base_sigma_fraction"] <= 0.008
    assert 0.004 <= severity["noise_signal_sigma_fraction"] <= 0.012


def test_hard_sample_has_greater_configured_minimum_severity_than_easy() -> None:
    tiers = _tiers()
    easy = sample_similarity_difficulty(
        "easy", tiers["easy"], np.random.default_rng(1), (100, 140)
    )
    hard = sample_similarity_difficulty(
        "hard", tiers["hard"], np.random.default_rng(1), (100, 140)
    )
    assert hard.severity["translation_abs_px"] > easy.severity["translation_abs_px"]
    assert hard.severity["rotation_abs_degrees"] > easy.severity["rotation_abs_degrees"]
    assert hard.severity["scale_deviation_abs"] > easy.severity["scale_deviation_abs"]


def test_sampled_transform_inverse_recovers_points() -> None:
    sample = sample_similarity_difficulty(
        "moderate", _tiers()["moderate"], np.random.default_rng(9), (100, 140)
    )
    points = np.array([[20.0, 30.0], [70.0, 55.0], [110.0, 80.0]])
    moving = apply_transform(points, sample.ground_truth.fixed_to_moving)
    recovered = apply_transform(moving, sample.ground_truth.moving_to_fixed)
    assert np.allclose(recovered, points, atol=1e-10)


def test_invalid_negative_interval_is_rejected() -> None:
    spec = _tiers()["easy"].copy()
    spec["rotation_abs_degrees"] = [-1.0, 3.0]
    with pytest.raises(ValueError, match="0 <= minimum"):
        sample_similarity_difficulty(
            "easy", spec, np.random.default_rng(0), (100, 140)
        )
