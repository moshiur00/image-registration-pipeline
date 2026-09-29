from __future__ import annotations

import math

import pytest

from image_registration.week4_baseline import (
    Week4Thresholds,
    paired_case_comparison,
    summarize_integrated_records,
    within_week4_tolerance,
)


def test_thresholds_reject_negative_values() -> None:
    with pytest.raises(ValueError):
        Week4Thresholds(translation_tre_pixels=-1.0)


def test_translation_tolerance_requires_success_and_geometry() -> None:
    thresholds = Week4Thresholds()
    assert within_week4_tolerance(
        "translation",
        success=True,
        mean_tre_pixels=0.4,
        translation_error_pixels=0.5,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=thresholds,
    )
    assert not within_week4_tolerance(
        "translation",
        success=False,
        mean_tre_pixels=0.1,
        translation_error_pixels=0.1,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=thresholds,
    )


def test_rigid_tolerance_checks_rotation() -> None:
    thresholds = Week4Thresholds()
    assert within_week4_tolerance(
        "rigid",
        success=True,
        mean_tre_pixels=1.0,
        translation_error_pixels=1.0,
        rotation_error_degrees=0.5,
        affine_linear_error=None,
        thresholds=thresholds,
    )
    assert not within_week4_tolerance(
        "rigid",
        success=True,
        mean_tre_pixels=1.0,
        translation_error_pixels=1.0,
        rotation_error_degrees=2.0,
        affine_linear_error=None,
        thresholds=thresholds,
    )


def test_affine_tolerance_checks_linear_error() -> None:
    thresholds = Week4Thresholds()
    assert within_week4_tolerance(
        "affine",
        success=True,
        mean_tre_pixels=1.0,
        translation_error_pixels=1.0,
        rotation_error_degrees=None,
        affine_linear_error=0.02,
        thresholds=thresholds,
    )
    assert not within_week4_tolerance(
        "affine",
        success=True,
        mean_tre_pixels=1.0,
        translation_error_pixels=1.0,
        rotation_error_degrees=None,
        affine_linear_error=0.08,
        thresholds=thresholds,
    )


def test_unknown_model_rejected() -> None:
    with pytest.raises(ValueError):
        within_week4_tolerance(
            "similarity",
            success=True,
            mean_tre_pixels=0.1,
            translation_error_pixels=0.1,
            rotation_error_degrees=0.1,
            affine_linear_error=None,
            thresholds=Week4Thresholds(),
        )


def test_nonfinite_geometry_fails() -> None:
    assert not within_week4_tolerance(
        "translation",
        success=True,
        mean_tre_pixels=math.nan,
        translation_error_pixels=0.1,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=Week4Thresholds(),
    )


def test_summary_keeps_failed_records_in_denominator() -> None:
    records = [
        {"method_id": "a", "success": True, "within_tolerance": True, "mean_tre_pixels": 0.2, "runtime_ms": 1.0},
        {"method_id": "a", "success": False, "within_tolerance": False, "mean_tre_pixels": 5.0, "runtime_ms": 2.0},
    ]
    summary = summarize_integrated_records(records, "method_id")["a"]
    assert summary["registration_count"] == 2
    assert summary["success_count"] == 1
    assert summary["within_tolerance_count"] == 1
    assert summary["within_tolerance_rate"] == 0.5
    assert summary["median_tre_pixels"] == pytest.approx(2.6)


def test_summary_handles_missing_tre() -> None:
    records = [
        {"method_id": "a", "success": False, "within_tolerance": False, "mean_tre_pixels": None, "runtime_ms": 1.0}
    ]
    summary = summarize_integrated_records(records, "method_id")["a"]
    assert summary["median_tre_pixels"] is None
    assert summary["maximum_tre_pixels"] is None


def test_paired_case_comparison_requires_one_record_per_method() -> None:
    records = [
        {"comparison_group": "translation", "case_id": "c1", "method_id": "a", "success": True, "within_tolerance": True, "mean_tre_pixels": 0.1, "runtime_ms": 1.0},
        {"comparison_group": "translation", "case_id": "c1", "method_id": "b", "success": True, "within_tolerance": True, "mean_tre_pixels": 0.2, "runtime_ms": 2.0},
    ]
    result = paired_case_comparison(records, method_ids=("a", "b"), group="translation")
    assert result["case_count"] == 1
    assert result["complete_case_count"] == 1
    assert result["cases"][0]["a"]["mean_tre_pixels"] == pytest.approx(0.1)


def test_paired_case_comparison_marks_incomplete_case() -> None:
    records = [
        {"comparison_group": "translation", "case_id": "c1", "method_id": "a", "success": True, "within_tolerance": True, "mean_tre_pixels": 0.1, "runtime_ms": 1.0},
    ]
    result = paired_case_comparison(records, method_ids=("a", "b"), group="translation")
    assert result["complete_case_count"] == 0
    assert result["cases"][0]["b"] is None
