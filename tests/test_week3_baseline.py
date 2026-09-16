from __future__ import annotations

import pytest

from image_registration.week3_baseline import (
    BaselineThresholds,
    summarize_by_key,
    within_model_tolerance,
)


def test_translation_tolerance_passes_clean_result() -> None:
    thresholds = BaselineThresholds()
    assert within_model_tolerance(
        "translation",
        optimizer_success=True,
        mean_tre_pixels=0.25,
        translation_error_pixels=0.25,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=thresholds,
    )


def test_translation_tolerance_rejects_large_translation_error() -> None:
    thresholds = BaselineThresholds(translation_error_pixels=0.5)
    assert not within_model_tolerance(
        "translation",
        optimizer_success=True,
        mean_tre_pixels=0.8,
        translation_error_pixels=0.6,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=thresholds,
    )


def test_rigid_tolerance_checks_rotation_and_translation() -> None:
    thresholds = BaselineThresholds()
    assert within_model_tolerance(
        "rigid",
        optimizer_success=True,
        mean_tre_pixels=0.5,
        translation_error_pixels=0.7,
        rotation_error_degrees=0.2,
        affine_linear_error=None,
        thresholds=thresholds,
    )
    assert not within_model_tolerance(
        "rigid",
        optimizer_success=True,
        mean_tre_pixels=0.5,
        translation_error_pixels=0.7,
        rotation_error_degrees=2.0,
        affine_linear_error=None,
        thresholds=thresholds,
    )


def test_affine_tolerance_checks_linear_error() -> None:
    thresholds = BaselineThresholds()
    assert within_model_tolerance(
        "affine",
        optimizer_success=True,
        mean_tre_pixels=0.6,
        translation_error_pixels=0.8,
        rotation_error_degrees=None,
        affine_linear_error=0.01,
        thresholds=thresholds,
    )
    assert not within_model_tolerance(
        "affine",
        optimizer_success=True,
        mean_tre_pixels=0.6,
        translation_error_pixels=0.8,
        rotation_error_degrees=None,
        affine_linear_error=0.03,
        thresholds=thresholds,
    )


def test_failed_optimizer_never_passes_geometric_tolerance() -> None:
    assert not within_model_tolerance(
        "translation",
        optimizer_success=False,
        mean_tre_pixels=0.0,
        translation_error_pixels=0.0,
        rotation_error_degrees=None,
        affine_linear_error=None,
        thresholds=BaselineThresholds(),
    )


def test_invalid_motion_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="motion_model"):
        within_model_tolerance(
            "projective",
            optimizer_success=True,
            mean_tre_pixels=0.0,
            translation_error_pixels=0.0,
            rotation_error_degrees=None,
            affine_linear_error=None,
            thresholds=BaselineThresholds(),
        )


def test_summarize_by_key_aggregates_pass_rate_and_medians() -> None:
    records = [
        {
            "method_id": "a",
            "mean_tre_pixels": 0.2,
            "runtime_ms": 10.0,
            "ncc_before": 0.2,
            "ncc_after": 0.8,
            "ssim_before": 0.3,
            "ssim_after": 0.7,
            "success": True,
            "within_tolerance": True,
        },
        {
            "method_id": "a",
            "mean_tre_pixels": 1.2,
            "runtime_ms": 20.0,
            "ncc_before": 0.1,
            "ncc_after": 0.4,
            "ssim_before": 0.2,
            "ssim_after": 0.3,
            "success": True,
            "within_tolerance": False,
        },
    ]
    summary = summarize_by_key(records, "method_id")["a"]
    assert summary["registration_count"] == 2
    assert summary["within_tolerance_count"] == 1
    assert summary["within_tolerance_rate"] == pytest.approx(0.5)
    assert summary["median_mean_tre_pixels"] == pytest.approx(0.7)
    assert summary["mean_runtime_ms"] == pytest.approx(15.0)


def test_thresholds_reject_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        BaselineThresholds(mean_tre_pixels=-1.0)
