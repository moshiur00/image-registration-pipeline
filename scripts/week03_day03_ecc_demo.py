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
from image_registration.degradations import adjust_contrast, illumination_gradient
from image_registration.ecc import ECCRegistration
from image_registration.evaluation import normalized_cross_correlation
from image_registration.io import load_image
from image_registration.registration_metrics import (
    centered_translation_error_pixels,
    centered_translation_parameters,
    mean_tre_pixels,
    rotation_angle_degrees,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import invert_transform, rigid_matrix, translation_matrix
from image_registration.visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
    save_grayscale_image,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Week 3 Day 3 ECC translation and rigid validation."
    )
    parser.add_argument(
        "--config",
        default="configs/week03_day03_ecc_translation_rigid.yaml",
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
    model = str(case["motion_model"])
    tx = float(case.get("tx", 0.0))
    ty = float(case.get("ty", 0.0))
    if model == "translation":
        matrix = translation_matrix(tx, ty)
        parameters = {"tx": tx, "ty": ty}
    elif model == "rigid":
        angle = float(case.get("angle_degrees", 0.0))
        matrix = rigid_matrix(angle, tx=tx, ty=ty, center=center)
        parameters = {
            "angle_degrees": angle,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
        }
    else:
        raise ValueError("Day 3 motion_model must be translation or rigid.")
    return GroundTruthTransform(
        transform_type=model,
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )


def _apply_appearance(image: np.ndarray, spec: dict[str, Any]) -> tuple[np.ndarray, str]:
    name = str(spec.get("type", "clean")).strip().lower()
    if name == "clean":
        return image.copy(), "clean"
    if name == "contrast":
        factor = float(spec.get("factor", 1.0))
        return adjust_contrast(image, factor=factor), f"contrast factor={factor:g}"
    if name == "illumination_gradient":
        strength = float(spec.get("strength_fraction", 0.1))
        direction = str(spec.get("direction", "horizontal"))
        return (
            illumination_gradient(
                image,
                strength_fraction=strength,
                direction=direction,
            ),
            f"illumination strength={strength:g} direction={direction}",
        )
    raise ValueError("Day 3 appearance type must be clean, contrast, or illumination_gradient.")


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _save_case_outputs(
    output_dir: Path,
    case_id: str,
    initialization: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
) -> None:
    case_dir = output_dir / "representative_cases" / f"{case_id}_{initialization}"
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
        title=f"ECC {case_id}, init={initialization}",
    )


def _write_plots(records: list[dict[str, Any]], output_dir: Path) -> None:
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    labels = sorted({str(record["case_id"]) for record in records})
    x = np.arange(len(labels), dtype=np.float64)
    width = 0.36
    for metric, ylabel, filename in [
        ("mean_tre_pixels", "Mean TRE (pixels)", "tre_by_case_and_initialization.png"),
        ("runtime_ms", "Runtime (ms)", "runtime_by_case_and_initialization.png"),
    ]:
        fig = Figure(figsize=(12.5, 5.5))
        FigureCanvasAgg(fig)
        axis = fig.subplots(1, 1)
        for offset_index, init in enumerate(["identity", "phase_correlation"]):
            values = []
            for label in labels:
                matches = [
                    r for r in records if r["case_id"] == label and r["initialization"] == init
                ]
                values.append(float(matches[0][metric]) if matches else np.nan)
            offset = (-0.5 + offset_index) * width
            axis.bar(x + offset, values, width=width, label=init)
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=45, ha="right")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel + " by ECC initialization")
        axis.legend()
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots_dir / filename, dpi=150, bbox_inches="tight")
        fig.clear()

    fig = Figure(figsize=(8.5, 5.5))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    before = np.array([float(record["ncc_before"]) for record in records])
    after = np.array([float(record["ncc_after"]) for record in records])
    axis.scatter(before, after, s=32)
    low = float(min(np.min(before), np.min(after)))
    high = float(max(np.max(before), np.max(after)))
    axis.plot([low, high], [low, high], linestyle="--", linewidth=1.0)
    axis.set_xlabel("NCC before")
    axis.set_ylabel("NCC after")
    axis.set_title("ECC alignment similarity improvement")
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "ncc_before_vs_after.png", dpi=150, bbox_inches="tight")
    fig.clear()


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for model in ["translation", "rigid"]:
        for init in ["identity", "phase_correlation"]:
            group = [
                record
                for record in records
                if record["motion_model"] == model and record["initialization"] == init
            ]
            if not group:
                continue
            key = f"{model}_{init}"
            tre = np.array([float(record["mean_tre_pixels"]) for record in group])
            runtimes = np.array([float(record["runtime_ms"]) for record in group])
            ecc_values = np.array(
                [
                    float(record["final_ecc"])
                    for record in group
                    if record["final_ecc"] is not None
                ],
                dtype=np.float64,
            )
            passes = sum(bool(record["within_tolerance"]) for record in group)
            optimizer_successes = sum(bool(record["success"]) for record in group)
            result[key] = {
                "case_count": len(group),
                "optimizer_success_count": optimizer_successes,
                "within_tolerance_count": passes,
                "within_tolerance_rate": passes / len(group),
                "median_mean_tre_pixels": float(np.median(tre)),
                "max_mean_tre_pixels": float(np.max(tre)),
                "mean_runtime_ms": float(np.mean(runtimes)),
                "median_final_ecc": float(np.median(ecc_values)) if ecc_values.size else None,
                "mean_ncc_improvement": float(
                    np.mean(
                        [float(record["ncc_after"]) - float(record["ncc_before"]) for record in group]
                    )
                ),
            }
    return result


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)

    source_config = config.get("source", {})
    ecc_config = config.get("ecc", {})
    validation = config.get("validation", {})
    output_config = config.get("output", {})

    source_path = resolve_project_path(PROJECT_ROOT, source_config["image"])
    loaded = load_image(source_path, color_mode=str(source_config.get("color_mode", "grayscale")))
    fixed = np.asarray(loaded.array)
    if fixed.ndim != 2:
        raise ValueError("Week 3 Day 3 source image must be 2D grayscale.")
    fixed = _resize_source(fixed, source_config)
    center = image_center(fixed.shape)

    output_dir = resolve_project_path(PROJECT_ROOT, output_config["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    tre_tolerance = float(validation.get("mean_tre_tolerance_pixels", 1.0))
    translation_tolerance = float(
        validation.get("translation_parameter_tolerance_pixels", 1.5)
    )
    rotation_tolerance = float(validation.get("rotation_tolerance_degrees", 1.0))
    cases = validation.get("cases", [])
    initializations = [str(value) for value in ecc_config.get("initializations", [])]
    if not cases:
        raise ValueError("validation.cases must contain at least one case.")
    if not initializations:
        raise ValueError("ecc.initializations must contain at least one initialization.")

    phase_config = ecc_config.get("phase_initialization", {})
    records: list[dict[str, Any]] = []

    print()
    print("Week 3 Day 3 ECC translation and rigid validation")
    print("---------------------------------------------------")
    print(f"Source image: {source_path.relative_to(PROJECT_ROOT)}")
    print(f"Working size: {fixed.shape[1]} x {fixed.shape[0]}")
    print(f"Base cases: {len(cases)}")
    print(f"Initializations: {', '.join(initializations)}")
    print(f"Planned registrations: {len(cases) * len(initializations)}")
    print()

    for case in cases:
        case_id = str(case["id"])
        motion_model = str(case["motion_model"])
        appearance = dict(case.get("appearance", {"type": "clean"}))
        ground_truth = _build_ground_truth(case, center)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving, appearance_label = _apply_appearance(pair.moving, appearance)
        ncc_before = normalized_cross_correlation(pair.fixed, moving)

        for initialization in initializations:
            method = ECCRegistration(
                motion_model=motion_model,
                initialization=initialization,
                max_iterations=int(ecc_config.get("max_iterations", 120)),
                epsilon=float(ecc_config.get("epsilon", 1e-6)),
                gauss_filt_size=int(ecc_config.get("gauss_filt_size", 5)),
                interpolation=str(ecc_config.get("interpolation", "linear")),
                min_ecc=(
                    None if ecc_config.get("min_ecc") is None else float(ecc_config["min_ecc"])
                ),
                phase_use_hanning_window=bool(
                    phase_config.get("use_hanning_window", True)
                ),
                phase_subtract_mean=bool(phase_config.get("subtract_mean", True)),
            )
            result = method.register(pair.fixed, moving)
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
            rotation_error = rotation_error_degrees(
                ground_truth.moving_to_fixed,
                estimated,
            )
            estimated_translation = centered_translation_parameters(estimated, center)
            estimated_angle = rotation_angle_degrees(estimated)
            ncc_after = normalized_cross_correlation(pair.fixed, result.registered_image)
            final_ecc = _safe_float(result.convergence_info.get("final_ecc"))

            within_tolerance = bool(
                result.success
                and tre <= tre_tolerance
                and translation_error <= translation_tolerance
                and (motion_model != "rigid" or rotation_error <= rotation_tolerance)
            )

            record = {
                "case_id": case_id,
                "motion_model": motion_model,
                "appearance": appearance_label,
                "initialization": initialization,
                "true_angle_degrees": float(case.get("angle_degrees", 0.0)),
                "estimated_angle_degrees": estimated_angle,
                "rotation_error_degrees": rotation_error,
                "true_tx": float(case.get("tx", 0.0)),
                "true_ty": float(case.get("ty", 0.0)),
                "estimated_tx": float(estimated_translation[0]),
                "estimated_ty": float(estimated_translation[1]),
                "translation_parameter_error_pixels": translation_error,
                "mean_tre_pixels": tre,
                "ncc_before": ncc_before,
                "ncc_after": ncc_after,
                "ncc_improvement": ncc_after - ncc_before,
                "final_ecc": final_ecc,
                "runtime_ms": result.runtime_seconds * 1000.0,
                "success": bool(result.success),
                "within_tolerance": within_tolerance,
                "failure_reason": result.failure_reason,
            }
            records.append(record)

            ecc_text = "n/a" if final_ecc is None else f"{final_ecc:.4f}"
            print(
                f"{case_id:<35} init={initialization:<17} "
                f"TRE={tre:>6.3f} px  rot_err={rotation_error:>5.2f} deg  "
                f"trans_err={translation_error:>6.3f} px  ECC={ecc_text:<7} "
                f"{'PASS' if within_tolerance else 'FAIL'}"
            )

            if case_id in {
                "rigid_challenging_initialization",
                "rigid_illumination",
                "translation_contrast",
            }:
                _save_case_outputs(
                    output_dir,
                    case_id,
                    initialization,
                    pair.fixed,
                    moving,
                    result.registered_image,
                )

    fieldnames = list(records[0].keys())
    with (output_dir / "ecc_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    with (output_dir / "ecc_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")

    grouped = _group_summary(records)
    total_passed = sum(bool(record["within_tolerance"]) for record in records)
    total_optimizer_success = sum(bool(record["success"]) for record in records)
    challenging = [
        record for record in records if record["case_id"] == "rigid_challenging_initialization"
    ]
    summary = {
        "week": 3,
        "global_day": 13,
        "week_day": 3,
        "title": "ECC translation and rigid registration",
        "status": "implementation_complete",
        "source_image": source_path.relative_to(PROJECT_ROOT).as_posix(),
        "working_shape": [int(fixed.shape[0]), int(fixed.shape[1])],
        "base_case_count": len(cases),
        "registration_count": len(records),
        "optimizer_success_count": total_optimizer_success,
        "within_tolerance_count": total_passed,
        "within_tolerance_rate": total_passed / len(records),
        "tolerances": {
            "mean_tre_pixels": tre_tolerance,
            "translation_parameter_error_pixels": translation_tolerance,
            "rotation_error_degrees": rotation_tolerance,
        },
        "groups": grouped,
        "challenging_initialization_case": challenging,
        "raw_output_directory": output_config["directory"],
        "daily_summary": "docs/daily/day_13_summary.md",
        "technical_note": "docs/ECC_REGISTRATION.md",
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
    for key, group in grouped.items():
        print(
            f"{key:<30} pass={group['within_tolerance_count']}/{group['case_count']}  "
            f"median TRE={group['median_mean_tre_pixels']:.3f} px  "
            f"mean runtime={group['mean_runtime_ms']:.2f} ms"
        )
    print(f"Results: {output_dir.relative_to(PROJECT_ROOT)}")
    print(f"Report snapshot: {report_path.relative_to(PROJECT_ROOT)}")
    print("Week 3 Day 3 complete: ECC translation and rigid validation generated and summarized.")


if __name__ == "__main__":
    main()
