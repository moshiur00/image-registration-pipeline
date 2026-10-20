from __future__ import annotations

import math

import numpy as np
import pytest

from image_registration.transforms import affine_matrix, rigid_matrix, similarity_matrix, translation_matrix
from image_registration.unified_metrics import (
    dice_score,
    evaluation_mutual_information,
    landmark_tre,
    model_aware_parameter_errors,
    overlap_aware_descriptive_metrics,
    transform_tre,
)


def test_translation_parameter_error_matches_3_4_5_triangle() -> None:
    metrics = model_aware_parameter_errors(
        translation_matrix(0.0, 0.0),
        translation_matrix(3.0, 4.0),
        transform_model="translation",
    )
    assert metrics == {"translation_error_px": pytest.approx(5.0)}


def test_translation_parameter_error_converts_anisotropic_spacing() -> None:
    metrics = model_aware_parameter_errors(
        translation_matrix(0.0, 0.0),
        translation_matrix(3.0, 4.0),
        transform_model="translation",
        spacing=(2.0, 0.5),
    )
    assert metrics["translation_error_px"] == pytest.approx(5.0)
    assert metrics["translation_error_mm"] == pytest.approx(math.sqrt(40.0))


def test_rigid_rotation_error_wraps_across_180_degrees() -> None:
    metrics = model_aware_parameter_errors(
        rigid_matrix(179.0),
        rigid_matrix(-179.0),
        transform_model="rigid",
    )
    assert metrics["rotation_error_deg"] == pytest.approx(2.0)


def test_similarity_parameter_error_reports_scale_rotation_and_translation() -> None:
    reference = similarity_matrix(scale=1.2, angle_degrees=10.0, tx=2.0, ty=-1.0)
    estimated = similarity_matrix(scale=1.25, angle_degrees=12.0, tx=5.0, ty=3.0)
    metrics = model_aware_parameter_errors(
        reference,
        estimated,
        transform_model="similarity",
    )
    assert metrics["translation_error_px"] == pytest.approx(5.0)
    assert metrics["rotation_error_deg"] == pytest.approx(2.0)
    assert metrics["scale_error_abs"] == pytest.approx(0.05)


def test_affine_parameter_error_uses_frobenius_linear_error() -> None:
    reference = affine_matrix([[1.0, 0.0], [0.0, 1.0]])
    estimated = affine_matrix([[1.1, 0.2], [0.0, 0.9]], tx=3.0, ty=4.0)
    metrics = model_aware_parameter_errors(reference, estimated, transform_model="affine")
    assert metrics["translation_error_px"] == pytest.approx(5.0)
    assert metrics["affine_linear_error"] == pytest.approx(math.sqrt(0.06))
    assert "rotation_error_deg" not in metrics
    assert "scale_error_abs" not in metrics


def test_transform_tre_known_translation_has_constant_five_pixel_error() -> None:
    points = np.asarray([[0.0, 0.0], [2.0, 1.0], [10.0, 7.0], [4.0, 9.0]])
    summaries = transform_tre(
        translation_matrix(0.0, 0.0),
        translation_matrix(3.0, 4.0),
        points,
    )
    summary = summaries["px"]
    assert summary.mean == pytest.approx(5.0)
    assert summary.median == pytest.approx(5.0)
    assert summary.std == pytest.approx(0.0)
    assert summary.p95 == pytest.approx(5.0)
    assert summary.count == 4


def test_transform_tre_identity_is_exactly_zero() -> None:
    points = np.asarray([[0.0, 0.0], [2.0, 5.0], [7.0, 1.0]])
    summary = transform_tre(np.eye(3), np.eye(3), points)["px"]
    assert summary.mean == pytest.approx(0.0)
    assert summary.p95 == pytest.approx(0.0)


def test_landmark_tre_reports_pixel_and_physical_units() -> None:
    reference = np.asarray([[0.0, 0.0], [10.0, 20.0]])
    estimated = reference + np.asarray([3.0, 4.0])
    summaries = landmark_tre(reference, estimated, spacing=(2.0, 0.5))
    assert summaries["px"].mean == pytest.approx(5.0)
    assert summaries["mm"].mean == pytest.approx(math.sqrt(40.0))


def test_dice_score_handles_perfect_disjoint_and_empty_masks() -> None:
    reference = np.zeros((8, 8), dtype=np.uint8)
    reference[1:4, 1:4] = 1
    same = reference.copy()
    disjoint = np.zeros_like(reference)
    disjoint[5:8, 5:8] = 1
    empty = np.zeros_like(reference)

    assert dice_score(reference, same) == pytest.approx(1.0)
    assert dice_score(reference, disjoint) == pytest.approx(0.0)
    assert dice_score(empty, empty) == pytest.approx(1.0)
    assert dice_score(reference, empty) == pytest.approx(0.0)


def test_evaluation_mutual_information_matches_binary_ln2_case() -> None:
    fixed = np.zeros((8, 8), dtype=np.float64)
    fixed[:, 4:] = 1.0
    moving = fixed.copy()
    value = evaluation_mutual_information(fixed, moving, bins=2)
    assert value == pytest.approx(math.log(2.0), abs=1e-12)


def test_overlap_aware_metrics_are_perfect_for_identical_nonconstant_images() -> None:
    yy, xx = np.indices((16, 16), dtype=np.float64)
    fixed = xx + 2.0 * yy
    mask = np.ones_like(fixed, dtype=np.uint8)
    metrics = overlap_aware_descriptive_metrics(fixed, fixed.copy(), mask, mi_bins=16)
    assert metrics["mae"] == pytest.approx(0.0)
    assert metrics["mse"] == pytest.approx(0.0)
    assert metrics["ncc"] == pytest.approx(1.0)
    assert metrics["ssim"] == pytest.approx(1.0)
    assert metrics["evaluation_mi"] > 0.0
    assert metrics["valid_overlap_fraction"] == pytest.approx(1.0)


def test_overlap_aware_metrics_ignore_invalid_border_changes() -> None:
    yy, xx = np.indices((16, 16), dtype=np.float64)
    fixed = xx + yy
    registered = fixed.copy()
    registered[:, :4] += 1000.0
    valid = np.ones_like(fixed, dtype=np.uint8)
    valid[:, :4] = 0

    metrics = overlap_aware_descriptive_metrics(fixed, registered, valid, mi_bins=16)
    assert metrics["mae"] == pytest.approx(0.0)
    assert metrics["mse"] == pytest.approx(0.0)
    assert metrics["ncc"] == pytest.approx(1.0)
    assert metrics["ssim"] == pytest.approx(1.0)
    assert metrics["valid_overlap_fraction"] == pytest.approx(0.75)


def test_overlap_aware_metrics_reject_empty_overlap() -> None:
    image = np.arange(64, dtype=np.float64).reshape(8, 8)
    empty = np.zeros_like(image, dtype=np.uint8)
    with pytest.raises(ValueError, match="empty"):
        overlap_aware_descriptive_metrics(image, image, empty)


def test_three_dimensional_physical_translation_and_rotation_errors() -> None:
    reference = np.eye(4, dtype=np.float64)
    estimated = np.eye(4, dtype=np.float64)
    estimated[:3, 3] = [1.0, 2.0, 2.0]
    theta = np.deg2rad(10.0)
    estimated[:3, :3] = np.asarray(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    metrics = model_aware_parameter_errors(
        reference,
        estimated,
        transform_model="rigid",
        coordinate_unit="mm",
    )
    assert metrics["translation_error_mm"] == pytest.approx(3.0)
    assert metrics["rotation_error_deg"] == pytest.approx(10.0)
