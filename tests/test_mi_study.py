from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from image_registration.mi_study import (
    SUPPORTED_MI_PREPROCESSING,
    apply_mi_preprocessing,
    candidate_rank_key,
    select_best_candidate,
    summarize_mi_records,
)
from image_registration.multimodal import SUPPORTED_MULTIMODAL_MAPPING_TYPES


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_apply_mi_preprocessing_none_preserves_values_as_float32() -> None:
    image = np.arange(16, dtype=np.uint8).reshape(4, 4)
    result = apply_mi_preprocessing(image, {"type": "none"})
    assert result.image.dtype == np.float32
    assert result.image == pytest.approx(image.astype(np.float32))
    assert result.metadata["type"] == "none"


def test_apply_mi_preprocessing_zscore_has_standardized_statistics() -> None:
    image = np.arange(25, dtype=np.float32).reshape(5, 5)
    result = apply_mi_preprocessing(image, {"type": "zscore"})
    assert float(np.mean(result.image)) == pytest.approx(0.0, abs=1e-6)
    assert float(np.std(result.image)) == pytest.approx(1.0, abs=1e-6)


def test_apply_mi_preprocessing_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported MI preprocessing"):
        apply_mi_preprocessing(np.ones((8, 8), dtype=np.float32), {"type": "histogram_match"})


def test_summarize_mi_records_keeps_failures_in_denominator() -> None:
    records = [
        {
            "method_success": True,
            "within_tolerance": True,
            "tre_pixels": 0.2,
            "rotation_error_degrees": 0.1,
            "translation_error_pixels": 0.2,
            "runtime_ms": 10.0,
            "valid_metric_points": 100,
            "optimizer_iteration": 12,
        },
        {
            "method_success": True,
            "within_tolerance": False,
            "tre_pixels": 20.0,
            "rotation_error_degrees": 5.0,
            "translation_error_pixels": 19.0,
            "runtime_ms": 20.0,
            "valid_metric_points": 90,
            "optimizer_iteration": 30,
        },
        {
            "method_success": False,
            "within_tolerance": False,
            "tre_pixels": None,
            "rotation_error_degrees": None,
            "translation_error_pixels": None,
            "runtime_ms": 5.0,
            "valid_metric_points": None,
            "optimizer_iteration": None,
        },
    ]
    summary = summarize_mi_records(records)
    assert summary["case_count"] == 3
    assert summary["method_success_count"] == 2
    assert summary["within_tolerance_count"] == 1
    assert summary["within_tolerance_rate"] == pytest.approx(1.0 / 3.0)
    assert summary["median_tre_pixels"] == pytest.approx(10.1)


def test_candidate_selection_prioritizes_geometric_pass_count() -> None:
    better_accuracy = {
        "candidate_id": "accurate",
        "summary": {
            "within_tolerance_count": 4,
            "method_success_count": 4,
            "median_tre_pixels": 1.0,
            "maximum_tre_pixels": 2.0,
            "mean_runtime_ms": 100.0,
        },
    }
    faster_but_less_accurate = {
        "candidate_id": "fast",
        "summary": {
            "within_tolerance_count": 3,
            "method_success_count": 4,
            "median_tre_pixels": 0.2,
            "maximum_tre_pixels": 0.5,
            "mean_runtime_ms": 10.0,
        },
    }
    selected = select_best_candidate([faster_but_less_accurate, better_accuracy])
    assert selected["candidate_id"] == "accurate"
    assert candidate_rank_key(better_accuracy["summary"]) < candidate_rank_key(
        faster_but_less_accurate["summary"]
    )


def test_week05_day02_config_uses_supported_mapping_and_preprocessing_names() -> None:
    config_path = PROJECT_ROOT / "configs" / "week05_day02_mi_rigid_study.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    for case in config["validation_cases"]:
        mapping = case.get("modality_mapping")
        if mapping is not None:
            assert mapping["type"] in SUPPORTED_MULTIMODAL_MAPPING_TYPES

    for candidate in config["studies"]["preprocessing"]:
        assert candidate["spec"]["type"] in SUPPORTED_MI_PREPROCESSING
