from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import cv2
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config, resolve_project_path
from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration
from image_registration.evaluation import normalized_cross_correlation
from image_registration.io import load_image
from image_registration.pyramids import build_image_pyramid
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    centered_translation_parameters,
    mean_tre_pixels,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import affine_matrix, invert_transform, rotation_matrix
from image_registration.visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
    save_grayscale_image,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Week 3 Day 4 affine ECC and multiresolution validation."
    )
    parser.add_argument(
        "--config",
        default="configs/week03_day04_ecc_affine_multiresolution.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    return parser.parse_args()


def _resize_source(image: np.ndarray, source_config: dict[str, Any]) -> np.ndarray:
    resize = source_config.get("resize")
    if not resize:
        return image
    width = int(resize["width"])
    height = int(resize["height"])
    if width <= 0 or height <= 0:
        raise ValueError("source.resize width and height must be positive.")
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def _build_ground_truth(case: dict[str, Any], center: np.ndarray) -> GroundTruthTransform:
    angle = float(case.get("angle_degrees", 0.0))
    scale_x = float(case.get("scale_x", 1.0))
    scale_y = float(case.get("scale_y", 1.0))
    shear_x = float(case.get("shear_x", 0.0))
    tx = float(case.get("tx", 0.0))
    ty = float(case.get("ty", 0.0))
    if scale_x <= 0.0 or scale_y <= 0.0:
        raise ValueError("Affine scales must be greater than zero.")

    rotation = rotation_matrix(angle)[:2, :2]
    scale = np.array([[scale_x, 0.0], [0.0, scale_y]], dtype=np.float64)
    shear = np.array([[1.0, shear_x], [0.0, 1.0]], dtype=np.float64)
    linear = rotation @ shear @ scale
    matrix = affine_matrix(linear, tx=tx, ty=ty, center=center)
    parameters = {
        "angle_degrees": angle,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "shear_x": shear_x,
        "tx": tx,
        "ty": ty,
        "center": center.tolist(),
        "linear": linear.tolist(),
    }
    return GroundTruthTransform(
        transform_type="affine",
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _save_case_outputs(
    output_dir: Path,
    case_id: str,
    strategy: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
) -> None:
    case_dir = output_dir / "representative_cases" / f"{case_id}_{strategy}"
    save_grayscale_image(case_dir / "fixed.png", fixed)
    save_grayscale_image(case_dir / "moving.png", moving)
    save_grayscale_image(case_dir / "registered.png", registered)
    save_grayscale_image(case_dir / "alpha_overlay_before.png", alpha_overlay(fixed, moving))
    save_grayscale_image(case_dir / "alpha_overlay_after.png", alpha_overlay(fixed, registered))
    save_grayscale_image(case_dir / "checkerboard_before.png", checkerboard(fixed, moving))
    save_grayscale_image(case_dir / "checkerboard_after.png", checkerboard(fixed, registered))
    save_grayscale_image(
        case_dir / "absolute_difference_before.png",
        absolute_difference(fixed, moving),
    )
    save_grayscale_image(
        case_dir / "absolute_difference_after.png",
        absolute_difference(fixed, registered),
    )
    save_comparison_figure(
        fixed,
        moving,
        registered,
        case_dir / "registration_comparison.png",
        title=f"Affine ECC {case_id}, {strategy}",
    )


def _save_pyramid_figure(
    output_dir: Path,
    fixed: np.ndarray,
    moving: np.ndarray,
    scales: list[float],
    pre_smoothing_sigma: float,
) -> None:
    fixed_levels = build_image_pyramid(
        fixed,
        scales,
        pre_smoothing_sigma=pre_smoothing_sigma,
    )
    moving_levels = build_image_pyramid(
        moving,
        scales,
        pre_smoothing_sigma=pre_smoothing_sigma,
    )
    fig = Figure(figsize=(10.5, 3.1 * len(scales)))
    FigureCanvasAgg(fig)
    axes = fig.subplots(len(scales), 2, squeeze=False)
    for row, (fixed_level, moving_level) in enumerate(
        zip(fixed_levels, moving_levels, strict=True)
    ):
        axes[row, 0].imshow(fixed_level.image, cmap="gray")
        axes[row, 0].set_title(
            f"Fixed scale={fixed_level.scale:g}, {fixed_level.shape[1]}x{fixed_level.shape[0]}"
        )
        axes[row, 1].imshow(moving_level.image, cmap="gray")
        axes[row, 1].set_title(
            f"Moving scale={moving_level.scale:g}, {moving_level.shape[1]}x{moving_level.shape[0]}"
        )
        axes[row, 0].axis("off")
        axes[row, 1].axis("off")
    fig.suptitle("Coarse-to-fine ECC image pyramid")
    fig.tight_layout()
    path = output_dir / "representative_cases" / "pyramid_levels.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    fig.clear()


def _write_plots(records: list[dict[str, Any]], output_dir: Path) -> None:
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    labels = [str(value) for value in dict.fromkeys(record["case_id"] for record in records)]
    strategies = ["single_resolution", "multiresolution"]
    x = np.arange(len(labels), dtype=np.float64)
    width = 0.36

    for metric, ylabel, filename in [
        ("mean_tre_pixels", "Mean TRE (pixels)", "tre_single_vs_multiresolution.png"),
        ("affine_linear_error", "Affine linear error", "affine_linear_error_comparison.png"),
        ("runtime_ms", "Runtime (ms)", "runtime_single_vs_multiresolution.png"),
    ]:
        fig = Figure(figsize=(12.5, 5.5))
        FigureCanvasAgg(fig)
        axis = fig.subplots(1, 1)
        for offset_index, strategy in enumerate(strategies):
            values = []
            for label in labels:
                match = next(
                    record
                    for record in records
                    if record["case_id"] == label and record["strategy"] == strategy
                )
                values.append(float(match[metric]))
            offset = (-0.5 + offset_index) * width
            axis.bar(x + offset, values, width=width, label=strategy)
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=45, ha="right")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel + ": single-resolution vs multiresolution ECC")
        axis.legend()
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots_dir / filename, dpi=150, bbox_inches="tight")
        fig.clear()

    fig = Figure(figsize=(8.5, 5.5))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    for strategy in strategies:
        group = [record for record in records if record["strategy"] == strategy]
        axis.scatter(
            [float(record["ncc_before"]) for record in group],
            [float(record["ncc_after"]) for record in group],
            s=36,
            label=strategy,
        )
    all_values = [float(record["ncc_before"]) for record in records] + [
        float(record["ncc_after"]) for record in records
    ]
    low, high = min(all_values), max(all_values)
    axis.plot([low, high], [low, high], linestyle="--", linewidth=1.0)
    axis.set_xlabel("NCC before")
    axis.set_ylabel("NCC after")
    axis.set_title("Affine ECC similarity before and after registration")
    axis.legend()
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "ncc_before_vs_after.png", dpi=150, bbox_inches="tight")
    fig.clear()


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for strategy in ["single_resolution", "multiresolution"]:
        group = [record for record in records if record["strategy"] == strategy]
        tre = np.array([float(record["mean_tre_pixels"]) for record in group])
        linear = np.array([float(record["affine_linear_error"]) for record in group])
        runtime = np.array([float(record["runtime_ms"]) for record in group])
        passes = sum(bool(record["within_tolerance"]) for record in group)
        optimizer_successes = sum(bool(record["success"]) for record in group)
        ecc_values = np.array(
            [float(record["final_ecc"]) for record in group if record["final_ecc"] is not None],
            dtype=np.float64,
        )
        summary[strategy] = {
            "case_count": len(group),
            "optimizer_success_count": optimizer_successes,
            "within_tolerance_count": passes,
            "within_tolerance_rate": passes / len(group),
            "median_mean_tre_pixels": float(np.median(tre)),
            "max_mean_tre_pixels": float(np.max(tre)),
            "median_affine_linear_error": float(np.median(linear)),
            "mean_runtime_ms": float(np.mean(runtime)),
            "median_final_ecc": float(np.median(ecc_values)) if ecc_values.size else None,
        }
    return summary


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)

    source_config = config.get("source", {})
    ecc_config = config.get("ecc", {})
    pyramid_config = ecc_config.get("pyramid", {})
    phase_config = ecc_config.get("phase_initialization", {})
    validation = config.get("validation", {})
    output_config = config.get("output", {})

    source_path = resolve_project_path(PROJECT_ROOT, source_config["image"])
    loaded = load_image(source_path, color_mode=str(source_config.get("color_mode", "grayscale")))
    fixed = np.asarray(loaded.array)
    if fixed.ndim != 2:
        raise ValueError("Week 3 Day 4 source image must be 2D grayscale.")
    fixed = _resize_source(fixed, source_config)
    center = image_center(fixed.shape)

    output_dir = resolve_project_path(PROJECT_ROOT, output_config["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    cases = validation.get("cases", [])
    if not cases:
        raise ValueError("validation.cases must contain at least one case.")
    tre_tolerance = float(validation.get("mean_tre_tolerance_pixels", 1.0))
    translation_tolerance = float(
        validation.get("translation_parameter_tolerance_pixels", 1.5)
    )
    linear_tolerance = float(validation.get("affine_linear_tolerance", 0.02))
    initialization = str(ecc_config.get("initialization", "phase_correlation"))
    scales = [float(value) for value in pyramid_config.get("scales", [0.25, 0.5, 1.0])]
    pre_smoothing_sigma = float(pyramid_config.get("pre_smoothing_sigma", 0.5))

    common = {
        "motion_model": "affine",
        "initialization": initialization,
        "max_iterations": int(ecc_config.get("max_iterations", 160)),
        "epsilon": float(ecc_config.get("epsilon", 1e-6)),
        "gauss_filt_size": int(ecc_config.get("gauss_filt_size", 5)),
        "interpolation": str(ecc_config.get("interpolation", "linear")),
        "min_ecc": None if ecc_config.get("min_ecc") is None else float(ecc_config["min_ecc"]),
        "phase_use_hanning_window": bool(phase_config.get("use_hanning_window", True)),
        "phase_subtract_mean": bool(phase_config.get("subtract_mean", True)),
    }

    records: list[dict[str, Any]] = []
    print()
    print("Week 3 Day 4 affine ECC and multiresolution validation")
    print("--------------------------------------------------------")
    print(f"Source image: {source_path.relative_to(PROJECT_ROOT)}")
    print(f"Working size: {fixed.shape[1]} x {fixed.shape[0]}")
    print(f"Affine cases: {len(cases)}")
    print(f"Initialization: {initialization}")
    print(f"Pyramid scales: {', '.join(f'{value:g}' for value in scales)}")
    print(f"Planned registrations: {len(cases) * 2}")
    print()

    pyramid_saved = False
    for case in cases:
        case_id = str(case["id"])
        ground_truth = _build_ground_truth(case, center)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        ncc_before = normalized_cross_correlation(pair.fixed, pair.moving)

        methods = {
            "single_resolution": ECCRegistration(**common),
            "multiresolution": MultiResolutionECCRegistration(
                **common,
                pyramid_scales=scales,
                pre_smoothing_sigma=pre_smoothing_sigma,
            ),
        }

        for strategy, method in methods.items():
            result = method.register(pair.fixed, pair.moving)
            estimated = result.transform
            tre = mean_tre_pixels(
                ground_truth.moving_to_fixed,
                estimated,
                pair.control_points_moving,
            )
            translation_error = centered_translation_error_pixels(
                ground_truth.moving_to_fixed,
                estimated,
                center,
            )
            linear_error = affine_linear_error(
                ground_truth.moving_to_fixed,
                estimated,
            )
            estimated_translation = centered_translation_parameters(estimated, center)
            ncc_after = normalized_cross_correlation(pair.fixed, result.registered_image)
            final_ecc = _safe_float(result.convergence_info.get("final_ecc"))
            levels_completed = int(result.convergence_info.get("levels_completed", 1))

            within_tolerance = bool(
                result.success
                and tre <= tre_tolerance
                and translation_error <= translation_tolerance
                and linear_error <= linear_tolerance
            )
            record = {
                "case_id": case_id,
                "strategy": strategy,
                "initialization": initialization,
                "true_angle_degrees": float(case.get("angle_degrees", 0.0)),
                "true_scale_x": float(case.get("scale_x", 1.0)),
                "true_scale_y": float(case.get("scale_y", 1.0)),
                "true_shear_x": float(case.get("shear_x", 0.0)),
                "true_tx": float(case.get("tx", 0.0)),
                "true_ty": float(case.get("ty", 0.0)),
                "estimated_tx": float(estimated_translation[0]),
                "estimated_ty": float(estimated_translation[1]),
                "translation_parameter_error_pixels": translation_error,
                "affine_linear_error": linear_error,
                "mean_tre_pixels": tre,
                "ncc_before": ncc_before,
                "ncc_after": ncc_after,
                "ncc_improvement": ncc_after - ncc_before,
                "final_ecc": final_ecc,
                "levels_completed": levels_completed,
                "runtime_ms": result.runtime_seconds * 1000.0,
                "success": bool(result.success),
                "within_tolerance": within_tolerance,
                "failure_reason": result.failure_reason,
                "estimated_transform": estimated.tolist(),
            }
            records.append(record)

            ecc_text = "n/a" if final_ecc is None else f"{final_ecc:.4f}"
            print(
                f"{case_id:<29} {strategy:<18} "
                f"TRE={tre:>7.3f} px  linear={linear_error:>6.4f}  "
                f"trans={translation_error:>7.3f} px  ECC={ecc_text:<7} "
                f"{'PASS' if within_tolerance else 'FAIL'}"
            )

            if case_id in {
                "affine_large",
                "affine_capture_range",
                "affine_strong_capture_range",
                "affine_strong_shape_change",
            }:
                _save_case_outputs(
                    output_dir,
                    case_id,
                    strategy,
                    pair.fixed,
                    pair.moving,
                    result.registered_image,
                )

        if not pyramid_saved and case_id == "affine_capture_range":
            _save_pyramid_figure(
                output_dir,
                pair.fixed,
                pair.moving,
                scales,
                pre_smoothing_sigma,
            )
            pyramid_saved = True

    fieldnames = list(records[0].keys())
    with (output_dir / "affine_ecc_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    with (output_dir / "affine_ecc_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")

    grouped = _group_summary(records)
    capture_cases = [
        record
        for record in records
        if record["case_id"] in {
            "affine_capture_range",
            "affine_strong_capture_range",
            "affine_strong_shape_change",
        }
    ]
    total_passed = sum(bool(record["within_tolerance"]) for record in records)
    total_optimizer_success = sum(bool(record["success"]) for record in records)
    summary = {
        "week": 3,
        "global_day": 14,
        "week_day": 4,
        "title": "ECC affine and multiresolution pyramids",
        "status": "implementation_complete",
        "source_image": source_path.relative_to(PROJECT_ROOT).as_posix(),
        "working_shape": [int(fixed.shape[0]), int(fixed.shape[1])],
        "affine_case_count": len(cases),
        "registration_count": len(records),
        "optimizer_success_count": total_optimizer_success,
        "within_tolerance_count": total_passed,
        "within_tolerance_rate": total_passed / len(records),
        "initialization": initialization,
        "pyramid": {
            "scales": scales,
            "pre_smoothing_sigma": pre_smoothing_sigma,
        },
        "tolerances": {
            "mean_tre_pixels": tre_tolerance,
            "translation_parameter_error_pixels": translation_tolerance,
            "affine_linear_error": linear_tolerance,
        },
        "groups": grouped,
        "capture_range_cases": capture_cases,
        "raw_output_directory": output_config["directory"],
        "daily_summary": "docs/daily/day_14_summary.md",
        "technical_note": "docs/MULTIRESOLUTION_ECC.md",
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    report_path = resolve_project_path(PROJECT_ROOT, output_config["report_snapshot"])
    write_report_snapshot(report_path, summary)
    _write_plots(records, output_dir)

    print()
    print("Summary")
    print("-------")
    print(f"Optimizer successes: {total_optimizer_success}/{len(records)}")
    print(f"Within tolerance:    {total_passed}/{len(records)}")
    for strategy, group in grouped.items():
        print(
            f"{strategy:<20} pass={group['within_tolerance_count']}/{group['case_count']}  "
            f"median TRE={group['median_mean_tre_pixels']:.3f} px  "
            f"mean runtime={group['mean_runtime_ms']:.2f} ms"
        )
    print(f"Results: {output_dir.relative_to(PROJECT_ROOT)}")
    print(f"Report snapshot: {report_path.relative_to(PROJECT_ROOT)}")
    print("Week 3 Day 4 complete: affine ECC and coarse-to-fine validation generated and summarized.")


if __name__ == "__main__":
    main()
