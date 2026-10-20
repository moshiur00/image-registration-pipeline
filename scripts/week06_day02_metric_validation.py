from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config
from image_registration.reporting import write_report_snapshot
from image_registration.transforms import translation_matrix
from image_registration.unified_metrics import (
    dice_score,
    evaluation_mutual_information,
    landmark_tre,
    model_aware_parameter_errors,
    overlap_aware_descriptive_metrics,
    transform_tre,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Week 6 Day 27 metric implementation validation study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _assert_close(name: str, actual: float, expected: float, tolerance: float) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"{name}: expected {expected}, got {actual}.")


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("Validation rows must not be empty.")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    validation = dict(config["validation"])
    output = dict(config["output"])

    tolerance = float(validation["numeric_tolerance"])
    bins = int(validation["mutual_information_bins"])
    spacing = tuple(float(value) for value in validation["anisotropic_spacing_xy"])

    output_dir = _resolve(str(output["directory"]))
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"Output directory already exists: {output_dir}. Use --overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []

    reference = translation_matrix(0.0, 0.0)
    estimated = translation_matrix(3.0, 4.0)
    parameter_metrics = model_aware_parameter_errors(
        reference,
        estimated,
        transform_model="translation",
        spacing=spacing,
    )
    expected_translation = float(validation["expected_translation_error_px"])
    _assert_close(
        "translation_error_px",
        parameter_metrics["translation_error_px"],
        expected_translation,
        tolerance,
    )
    expected_translation_mm = math.sqrt((3.0 * spacing[0]) ** 2 + (4.0 * spacing[1]) ** 2)
    _assert_close(
        "translation_error_mm",
        parameter_metrics["translation_error_mm"],
        expected_translation_mm,
        tolerance,
    )
    rows.append(
        {
            "case": "known_translation_parameter_error",
            "metric": "translation_error_px",
            "actual": parameter_metrics["translation_error_px"],
            "expected": expected_translation,
            "status": "PASS",
        }
    )
    rows.append(
        {
            "case": "known_translation_parameter_error",
            "metric": "translation_error_mm",
            "actual": parameter_metrics["translation_error_mm"],
            "expected": expected_translation_mm,
            "status": "PASS",
        }
    )

    control_points = np.asarray([[0.0, 0.0], [4.0, 1.0], [8.0, 6.0], [11.0, 9.0]])
    tre = transform_tre(reference, estimated, control_points, spacing=spacing)
    _assert_close("tre_mean_px", tre["px"].mean, 5.0, tolerance)
    _assert_close("tre_std_px", tre["px"].std, 0.0, tolerance)
    _assert_close("tre_mean_mm", tre["mm"].mean, expected_translation_mm, tolerance)
    for metric_name, value, expected_value in (
        ("tre_mean_px", tre["px"].mean, 5.0),
        ("tre_median_px", tre["px"].median, 5.0),
        ("tre_std_px", tre["px"].std, 0.0),
        ("tre_p95_px", tre["px"].p95, 5.0),
        ("tre_mean_mm", tre["mm"].mean, expected_translation_mm),
    ):
        rows.append(
            {
                "case": "known_transform_tre",
                "metric": metric_name,
                "actual": value,
                "expected": expected_value,
                "status": "PASS",
            }
        )

    landmark_reference = np.asarray([[0.0, 0.0], [10.0, 20.0]], dtype=np.float64)
    landmark_estimated = landmark_reference + np.asarray([3.0, 4.0])
    landmark_summary = landmark_tre(
        landmark_reference,
        landmark_estimated,
        spacing=spacing,
    )
    _assert_close("landmark_tre_px", landmark_summary["px"].mean, 5.0, tolerance)
    rows.append(
        {
            "case": "landmark_tre",
            "metric": "tre_mean_px",
            "actual": landmark_summary["px"].mean,
            "expected": 5.0,
            "status": "PASS",
        }
    )

    mask = np.zeros((16, 16), dtype=np.uint8)
    mask[4:12, 4:12] = 1
    disjoint = np.zeros_like(mask)
    disjoint[:4, :4] = 1
    empty = np.zeros_like(mask)
    dice_values = {
        "perfect": dice_score(mask, mask.copy()),
        "disjoint": dice_score(mask, disjoint),
        "both_empty": dice_score(empty, empty),
        "one_empty": dice_score(mask, empty),
    }
    for case, expected_value in {
        "perfect": 1.0,
        "disjoint": 0.0,
        "both_empty": 1.0,
        "one_empty": 0.0,
    }.items():
        _assert_close(f"dice_{case}", dice_values[case], expected_value, tolerance)
        rows.append(
            {
                "case": f"dice_{case}",
                "metric": "dice",
                "actual": dice_values[case],
                "expected": expected_value,
                "status": "PASS",
            }
        )

    binary = np.zeros((16, 16), dtype=np.float64)
    binary[:, 8:] = 1.0
    binary_mi = evaluation_mutual_information(binary, binary.copy(), bins=2)
    expected_binary_mi = float(validation["expected_binary_mi_nats"])
    _assert_close("binary_evaluation_mi", binary_mi, expected_binary_mi, tolerance)
    rows.append(
        {
            "case": "binary_mutual_information",
            "metric": "evaluation_mi",
            "actual": binary_mi,
            "expected": expected_binary_mi,
            "status": "PASS",
        }
    )

    yy, xx = np.indices((32, 32), dtype=np.float64)
    fixed = xx + 2.0 * yy
    registered = fixed.copy()
    registered[:, :8] += 1000.0
    valid = np.ones_like(fixed, dtype=np.uint8)
    valid[:, :8] = 0
    descriptive = overlap_aware_descriptive_metrics(fixed, registered, valid, mi_bins=bins)
    for key, expected_value in {
        "mae": 0.0,
        "mse": 0.0,
        "ncc": 1.0,
        "ssim": 1.0,
        "valid_overlap_fraction": 0.75,
    }.items():
        _assert_close(f"overlap_{key}", descriptive[key], expected_value, tolerance)
        rows.append(
            {
                "case": "overlap_aware_descriptive_metrics",
                "metric": key,
                "actual": descriptive[key],
                "expected": expected_value,
                "status": "PASS",
            }
        )

    no_overlap_rejected = False
    try:
        overlap_aware_descriptive_metrics(
            fixed,
            fixed.copy(),
            np.zeros_like(fixed, dtype=np.uint8),
            mi_bins=bins,
        )
    except ValueError:
        no_overlap_rejected = True
    if not no_overlap_rejected:
        raise AssertionError("No-overlap metric evaluation must be rejected.")

    monomodal = np.linspace(0.0, 1.0, 32 * 32, dtype=np.float64).reshape(32, 32)
    inverted = 1.0 - monomodal
    full = np.ones_like(monomodal, dtype=np.uint8)
    inversion_metrics = overlap_aware_descriptive_metrics(monomodal, inverted, full, mi_bins=bins)

    _write_rows(output_dir / "metric_validation_cases.csv", rows)
    (output_dir / "metric_validation_details.json").write_text(
        json.dumps(
            {
                "parameter_metrics": parameter_metrics,
                "transform_tre_px": tre["px"].to_metrics(),
                "transform_tre_mm": tre["mm"].to_metrics(),
                "landmark_tre_px": landmark_summary["px"].to_metrics(),
                "landmark_tre_mm": landmark_summary["mm"].to_metrics(),
                "dice": dice_values,
                "binary_evaluation_mi": binary_mi,
                "overlap_aware_descriptive": descriptive,
                "no_overlap_rejected": no_overlap_rejected,
                "aligned_intensity_inversion": inversion_metrics,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 6,
        "day": 27,
        "title": "Metric implementation and independent validation",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Implement the metric calculations defined by the Day 26 contract and validate them against hand-constructed cases with independently known answers."
        ),
        "implemented": [
            "model-aware transform parameter error for translation, rigid, similarity, and affine models",
            "TRE mean, median, standard deviation, and 95th percentile for transform and landmark references",
            "pixel and physical-unit TRE when spacing is available",
            "Dice score with explicit empty-mask behavior",
            "overlap-aware MAE, MSE, NCC, SSIM, and evaluation Mutual Information",
            "valid-overlap fraction and explicit no-overlap rejection",
        ],
        "validation_case_count": len(rows),
        "all_hand_constructed_checks_passed": all(row["status"] == "PASS" for row in rows),
        "known_translation": {
            "translation_error_px": parameter_metrics["translation_error_px"],
            "translation_error_mm": parameter_metrics["translation_error_mm"],
            "tre_mean_px": tre["px"].mean,
            "tre_mean_mm": tre["mm"].mean,
        },
        "dice_policy": {
            "perfect": dice_values["perfect"],
            "disjoint": dice_values["disjoint"],
            "both_empty": dice_values["both_empty"],
            "one_empty": dice_values["one_empty"],
        },
        "binary_mutual_information": {
            "actual_nats": binary_mi,
            "expected_nats": expected_binary_mi,
        },
        "valid_overlap_case": descriptive,
        "no_overlap_rejected": no_overlap_rejected,
        "modality_caution_example": {
            "description": "A perfectly corresponding intensity-inverted pair can have poor NCC while evaluation MI remains informative. Descriptive metrics must be interpreted by modality class.",
            "metrics": inversion_metrics,
        },
        "scientific_guards": [
            "Metrics are computed only when the corresponding Day 26 evidence requirements are satisfied by the caller.",
            "Image similarity is descriptive evidence and does not independently establish geometric correctness.",
            "Evaluation Mutual Information is a post-registration metric and is not compared directly with an optimizer objective.",
            "Invalid warp borders must be excluded using an explicit valid-overlap mask.",
            "Both-empty masks have Dice 1.0 by explicit policy; one-empty mask pairs have Dice 0.0.",
        ],
        "artifacts": {
            "local_cases": str((output_dir / "metric_validation_cases.csv").relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "local_details": str((output_dir / "metric_validation_details.json").relative_to(PROJECT_ROOT)).replace("\\", "/"),
        },
        "next_step": (
            "Run target Windows validation. After evidence review, Day 28 builds the deterministic resumable benchmark runner around the frozen evaluation contract and validated metrics."
        ),
    }
    write_report_snapshot(_resolve(str(output["report_snapshot"])), report)

    print("Week 6 Day 27: metric implementation and independent validation")
    print(f"Hand-constructed checks: {len(rows)}/{len(rows)} PASS")
    print(
        "Known translation: "
        f"parameter={parameter_metrics['translation_error_px']:.3f} px, "
        f"TRE={tre['px'].mean:.3f} px"
    )
    print(
        "Physical conversion: "
        f"translation={parameter_metrics['translation_error_mm']:.3f} mm, "
        f"TRE={tre['mm'].mean:.3f} mm"
    )
    print(
        "Dice policy: "
        f"perfect={dice_values['perfect']:.1f}, disjoint={dice_values['disjoint']:.1f}, "
        f"both_empty={dice_values['both_empty']:.1f}, one_empty={dice_values['one_empty']:.1f}"
    )
    print(f"Binary evaluation MI: {binary_mi:.6f} nats (expected ln(2))")
    print(
        "Overlap-aware identity region: "
        f"MAE={descriptive['mae']:.3f}, NCC={descriptive['ncc']:.3f}, "
        f"SSIM={descriptive['ssim']:.3f}, overlap={descriptive['valid_overlap_fraction']:.2f}"
    )
    print(f"No-overlap rejection: {'PASS' if no_overlap_rejected else 'FAIL'}")
    print(
        "Aligned intensity inversion: "
        f"NCC={inversion_metrics['ncc']:.3f}, MI={inversion_metrics['evaluation_mi']:.3f}"
    )
    print(f"Tracked report: {output['report_snapshot']}")
    print("Do not start Day 28 until the target Windows Day 27 evidence is reviewed.")


if __name__ == "__main__":
    main()
