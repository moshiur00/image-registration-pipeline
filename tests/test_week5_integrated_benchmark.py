from __future__ import annotations

from pathlib import Path

from image_registration.config import load_config
from image_registration.week5_benchmark import (
    compact_seed_variability,
    paired_method_outcomes,
    summarize_benchmark_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "week05_day05_integrated_benchmark.yaml"


def test_day25_config_keeps_frozen_mi_choices() -> None:
    config = load_config(CONFIG_PATH)
    mi = config["frozen_mutual_information"]
    assert mi["histogram_bins"] == 32
    assert mi["sampling_strategy"] == "none"
    assert mi["initialization"] == "identity"
    assert mi["shrink_factors"] == [4, 2, 1]
    assert mi["smoothing_sigmas"] == [2.0, 1.0, 0.0]
    assert config["frozen_mi_preprocessing"] == {"type": "gaussian_smooth", "sigma": 1.0}


def test_day25_config_uses_historical_compatible_ecc_settings() -> None:
    config = load_config(CONFIG_PATH)
    rigid = config["frozen_ecc"]["rigid"]
    affine = config["frozen_ecc"]["affine"]
    assert rigid["motion_model"] == "rigid"
    assert rigid["initialization"] == "phase_correlation"
    assert rigid["max_iterations"] == 140
    assert affine["motion_model"] == "affine"
    assert affine["implementation"] == "multiresolution"
    assert affine["max_iterations"] == 160
    assert affine["pyramid_scales"] == [0.25, 0.5, 1.0]


def test_day25_final_cases_cover_required_conditions_and_models() -> None:
    config = load_config(CONFIG_PATH)
    cases = list(config["cases"])
    models = {str(item["motion_model"]) for item in cases}
    mappings = {
        str(item["modality_mapping"]["type"])
        for item in cases
        if item.get("modality_mapping") is not None
    }
    assert models == {"rigid", "affine"}
    assert {
        "intensity_inversion",
        "nonlinear_gamma",
        "histogram_remap",
        "bias_field",
        "edge_emphasized",
    }.issubset(mappings)
    assert any(item.get("postprocess", {}).get("type") == "restricted_fov" for item in cases)
    assert all(str(item["id"]).endswith("_test") for item in cases)


def test_benchmark_summary_keeps_failed_attempts_in_denominator() -> None:
    records = [
        {
            "method_success": True,
            "within_tolerance": True,
            "tre_pixels": 0.2,
            "parameter_error": 0.1,
            "runtime_ms": 10.0,
        },
        {
            "method_success": True,
            "within_tolerance": False,
            "tre_pixels": 12.0,
            "parameter_error": 3.0,
            "runtime_ms": 20.0,
        },
        {
            "method_success": False,
            "within_tolerance": False,
            "tre_pixels": None,
            "parameter_error": None,
            "runtime_ms": 5.0,
        },
    ]
    summary = summarize_benchmark_records(records)
    assert summary["registration_count"] == 3
    assert summary["method_success_count"] == 2
    assert summary["within_tolerance_count"] == 1
    assert summary["within_tolerance_rate"] == 1.0 / 3.0


def test_paired_outcomes_do_not_drop_check_cases() -> None:
    records = [
        {"case_id": "a", "method": "mutual_information", "within_tolerance": True, "tre_pixels": 0.2},
        {"case_id": "a", "method": "ecc", "within_tolerance": False, "tre_pixels": 10.0},
        {"case_id": "b", "method": "mutual_information", "within_tolerance": False, "tre_pixels": 8.0},
        {"case_id": "b", "method": "ecc", "within_tolerance": False, "tre_pixels": 9.0},
    ]
    summary = paired_method_outcomes(records)
    assert summary["shared_case_count"] == 2
    assert summary["mutual_information_only_pass"] == 1
    assert summary["both_check"] == 1


def test_compact_seed_variability_preserves_diagnostic_only_rule() -> None:
    source = {
        "studies": {
            "random_seed_variability": {
                "sampling_strategy": "random",
                "sampling_percentage": 0.2,
                "selection_rule": "diagnostic_only_seed_is_not_selected_by_accuracy",
                "per_case_variability": [{"case_id": "x", "tre_std_pixels": 0.3}],
            }
        }
    }
    compact = compact_seed_variability(source)
    assert compact["selection_rule"] == "diagnostic_only_seed_is_not_selected_by_accuracy"
    assert compact["per_case_variability"][0]["case_id"] == "x"
