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
from image_registration.degradations import apply_degradation
from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration
from image_registration.evaluation import normalized_cross_correlation, structural_similarity
from image_registration.io import load_image
from image_registration.overlap import (
    apply_field_of_view,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
)
from image_registration.phase_correlation import PhaseCorrelationRegistration
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import default_control_points, generate_synthetic_pair, image_center, sample_ground_truth_transform
from image_registration.visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    edge_overlay,
    save_comparison_figure,
    save_grayscale_image,
    save_rgb_image,
)
from image_registration.week3_baseline import BaselineThresholds, summarize_by_key, within_model_tolerance


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Week 3 Day 5 integrated monomodal baseline benchmark."
    )
    parser.add_argument(
        "--config",
        default="configs/week03_day05_integrated_baselines.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    return parser.parse_args()


def _resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if width <= 0 or height <= 0:
        raise ValueError("Working width and height must be positive.")
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def _load_sources(config: dict[str, Any], width: int, height: int) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for source_id, source_spec in config.items():
        path = resolve_project_path(PROJECT_ROOT, source_spec["image"])
        loaded = load_image(path, color_mode=str(source_spec.get("color_mode", "grayscale")))
        image = np.asarray(loaded.array)
        if image.ndim != 2:
            raise ValueError(f"Source '{source_id}' must be 2D grayscale.")
        result[str(source_id)] = _resize(image, width, height)
    if not result:
        raise ValueError("sources must contain at least one image.")
    return result


def _exact_ground_truth(case: dict[str, Any], image_shape: tuple[int, ...]):
    model = str(case["motion_model"])
    ranges: dict[str, list[float]] = {}
    for name, default in [
        ("tx", 0.0),
        ("ty", 0.0),
        ("angle_degrees", 0.0),
        ("scale_x", 1.0),
        ("scale_y", 1.0),
        ("shear_x", 0.0),
    ]:
        if name in case or name in {"tx", "ty"}:
            value = float(case.get(name, default))
            ranges[name] = [value, value]
    return sample_ground_truth_transform(
        model,
        np.random.default_rng(0),
        image_shape,
        ranges,
    )


def _apply_condition(
    moving: np.ndarray,
    condition: dict[str, Any],
    *,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    name = str(condition.get("type", "clean")).strip().lower()
    valid_mask = np.ones(moving.shape, dtype=np.uint8)
    if name == "clean":
        return moving.copy(), valid_mask, {"type": "clean"}
    if name == "restricted_fov":
        mask = rectangular_field_of_view_mask(
            moving.shape,
            width_fraction=float(condition.get("width_fraction", 0.75)),
            height_fraction=float(condition.get("height_fraction", 0.75)),
            center_x_fraction=float(condition.get("center_x_fraction", 0.5)),
            center_y_fraction=float(condition.get("center_y_fraction", 0.5)),
        )
        result = apply_field_of_view(moving, mask, fill_value=float(condition.get("fill_value", 0.0)))
        return result, mask, {
            "type": "restricted_fov",
            "width_fraction": float(condition.get("width_fraction", 0.75)),
            "height_fraction": float(condition.get("height_fraction", 0.75)),
        }

    degraded = apply_degradation(moving, condition, rng=rng)
    return degraded.image, valid_mask, dict(degraded.metadata)


def _build_method(method_id: str, method_spec: dict[str, Any]):
    common = {
        "interpolation": str(method_spec.get("interpolation", "linear")),
    }
    if method_id == "phase_correlation":
        min_response = method_spec.get("min_response")
        return PhaseCorrelationRegistration(
            use_hanning_window=bool(method_spec.get("use_hanning_window", True)),
            subtract_mean=bool(method_spec.get("subtract_mean", True)),
            min_response=None if min_response is None else float(min_response),
            **common,
        )

    phase_window = bool(method_spec.get("phase_use_hanning_window", True))
    phase_mean = bool(method_spec.get("phase_subtract_mean", True))
    ecc_kwargs = {
        "motion_model": str(method_spec["motion_model"]),
        "initialization": str(method_spec.get("initialization", "phase_correlation")),
        "max_iterations": int(method_spec.get("max_iterations", 140)),
        "epsilon": float(method_spec.get("epsilon", 1e-6)),
        "gauss_filt_size": int(method_spec.get("gauss_filt_size", 5)),
        "interpolation": common["interpolation"],
        "phase_use_hanning_window": phase_window,
        "phase_subtract_mean": phase_mean,
    }
    if method_id == "ecc_affine_multiresolution":
        pyramid = method_spec.get("pyramid", {})
        return MultiResolutionECCRegistration(
            pyramid_scales=[float(value) for value in pyramid.get("scales", [0.25, 0.5, 1.0])],
            pre_smoothing_sigma=float(pyramid.get("pre_smoothing_sigma", 0.5)),
            **ecc_kwargs,
        )
    return ECCRegistration(**ecc_kwargs)


def _save_case_outputs(
    root: Path,
    case_id: str,
    method_id: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
    overlap_mask: np.ndarray,
) -> None:
    folder = root / "representative_cases" / f"{case_id}_{method_id}"
    save_grayscale_image(folder / "fixed.png", fixed)
    save_grayscale_image(folder / "moving.png", moving)
    save_grayscale_image(folder / "registered.png", registered)
    save_grayscale_image(folder / "valid_overlap_fixed.png", overlap_mask, normalize=False)
    save_grayscale_image(folder / "alpha_overlay_before.png", alpha_overlay(fixed, moving))
    save_grayscale_image(folder / "alpha_overlay_after.png", alpha_overlay(fixed, registered))
    save_grayscale_image(folder / "checkerboard_before.png", checkerboard(fixed, moving))
    save_grayscale_image(folder / "checkerboard_after.png", checkerboard(fixed, registered))
    save_grayscale_image(folder / "absolute_difference_before.png", absolute_difference(fixed, moving))
    save_grayscale_image(folder / "absolute_difference_after.png", absolute_difference(fixed, registered))
    save_rgb_image(folder / "edge_overlay_before.png", edge_overlay(fixed, moving))
    save_rgb_image(folder / "edge_overlay_after.png", edge_overlay(fixed, registered))
    save_comparison_figure(
        fixed,
        moving,
        registered,
        folder / "registration_comparison.png",
        title=f"{case_id}, {method_id}",
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError("No records available for CSV output.")
    fields = list(records[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = dict(record)
            for key in ["ground_truth_transform", "estimated_transform", "condition_metadata"]:
                row[key] = json.dumps(row[key], separators=(",", ":"), sort_keys=True)
            writer.writerow(row)


def _write_method_table(path: Path, summary: dict[str, dict[str, Any]], labels: dict[str, str]) -> None:
    fields = [
        "method_id",
        "label",
        "registration_count",
        "optimizer_success_count",
        "optimizer_success_rate",
        "within_tolerance_count",
        "within_tolerance_rate",
        "median_mean_tre_pixels",
        "max_mean_tre_pixels",
        "mean_runtime_ms",
        "median_runtime_ms",
        "mean_ncc_improvement",
        "mean_ssim_improvement",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method_id, values in summary.items():
            writer.writerow({"method_id": method_id, "label": labels[method_id], **values})


def _write_plots(
    records: list[dict[str, Any]],
    method_summary: dict[str, dict[str, Any]],
    method_labels: dict[str, str],
    output_dir: Path,
) -> None:
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    methods = list(method_summary)
    labels = [method_labels[method] for method in methods]

    metrics = [
        ("within_tolerance_rate", "Within-tolerance rate", "within_tolerance_rate_by_method.png", 100.0),
        ("median_mean_tre_pixels", "Median mean TRE (pixels)", "median_tre_by_method.png", 1.0),
        ("mean_runtime_ms", "Mean runtime (ms)", "mean_runtime_by_method.png", 1.0),
        ("mean_ncc_improvement", "Mean NCC improvement", "ncc_improvement_by_method.png", 1.0),
    ]
    for key, ylabel, filename, scale in metrics:
        values = [float(method_summary[method][key]) * scale for method in methods]
        fig = Figure(figsize=(9.5, 5.2))
        FigureCanvasAgg(fig)
        axis = fig.subplots(1, 1)
        x = np.arange(len(methods))
        axis.bar(x, values)
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=28, ha="right")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel + " by supported Week 3 baseline")
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots_dir / filename, dpi=150, bbox_inches="tight")
        fig.clear()

    translation = [record for record in records if record["motion_model"] == "translation"]
    case_ids = sorted({str(record["case_id"]) for record in translation})
    fig = Figure(figsize=(10.5, 5.4))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    x = np.arange(len(case_ids))
    width = 0.36
    for index, method_id in enumerate(["phase_correlation", "ecc_translation"]):
        values = []
        for case_id in case_ids:
            match = [r for r in translation if r["case_id"] == case_id and r["method_id"] == method_id]
            values.append(float(match[0]["mean_tre_pixels"]) if match else np.nan)
        axis.bar(x + (index - 0.5) * width, values, width=width, label=method_labels[method_id])
    axis.set_xticks(x)
    axis.set_xticklabels(case_ids, rotation=35, ha="right")
    axis.set_ylabel("Mean TRE (pixels)")
    axis.set_title("Comparable translation cases: phase correlation vs ECC translation")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "translation_method_comparison.png", dpi=150, bbox_inches="tight")
    fig.clear()


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)

    seed = int(config.get("experiment", {}).get("seed", 42))
    size = config.get("working_size", {})
    width = int(size.get("width", 256))
    height = int(size.get("height", 256))
    sources = _load_sources(config.get("sources", {}), width, height)
    methods = config.get("methods", {})
    cases = config.get("cases", [])
    if not methods or not cases:
        raise ValueError("methods and cases must be non-empty.")

    validation = config.get("validation", {})
    thresholds = BaselineThresholds(
        translation_error_pixels=float(validation.get("translation_error_tolerance_pixels", 0.5)),
        mean_tre_pixels=float(validation.get("mean_tre_tolerance_pixels", 1.0)),
        rigid_translation_error_pixels=float(validation.get("rigid_translation_error_tolerance_pixels", 1.5)),
        rotation_error_degrees=float(validation.get("rotation_error_tolerance_degrees", 1.0)),
        affine_translation_error_pixels=float(validation.get("affine_translation_error_tolerance_pixels", 1.5)),
        affine_linear_error=float(validation.get("affine_linear_tolerance", 0.02)),
    )

    output = config.get("output", {})
    output_dir = resolve_project_path(PROJECT_ROOT, output["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    representative = {tuple(item) for item in config.get("representative_outputs", [])}
    records: list[dict[str, Any]] = []

    planned = sum(len(case.get("methods", [])) for case in cases)
    print("Week 3 Day 5 integrated monomodal baseline benchmark")
    print("---------------------------------------------------")
    print(f"Seed: {seed}")
    print(f"Source images: {len(sources)}")
    print(f"Base cases: {len(cases)}")
    print(f"Planned registrations: {planned}")
    print()

    for case_index, case in enumerate(cases):
        case_id = str(case["id"])
        source_id = str(case["source"])
        if source_id not in sources:
            raise ValueError(f"Unknown source '{source_id}' for case '{case_id}'.")
        fixed = sources[source_id]
        ground_truth = _exact_ground_truth(case, fixed.shape)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        condition_rng = np.random.default_rng(seed + case_index * 1009)
        moving, moving_valid_mask, condition_metadata = _apply_condition(
            np.asarray(pair.moving),
            dict(case.get("condition", {"type": "clean"})),
            rng=condition_rng,
        )
        overlap_mask = overlap_mask_in_fixed_space(
            moving_valid_mask,
            ground_truth.moving_to_fixed,
            fixed_shape=(height, width),
        )
        overlap = overlap_fraction(overlap_mask)
        points = default_control_points(fixed.shape)
        center = image_center(fixed.shape)
        ncc_before = normalized_cross_correlation(fixed, moving)
        ssim_before = structural_similarity(fixed, moving)

        for method_id in case.get("methods", []):
            method_id = str(method_id)
            if method_id not in methods:
                raise ValueError(f"Unknown method '{method_id}' for case '{case_id}'.")
            method_spec = dict(methods[method_id])
            method_model = str(method_spec["motion_model"])
            if method_model != str(case["motion_model"]):
                raise ValueError(
                    f"Method '{method_id}' model '{method_model}' does not match case '{case_id}' model '{case['motion_model']}'."
                )

            registration = _build_method(method_id, method_spec)
            result = registration.register(fixed, moving)
            estimated = np.asarray(result.transform, dtype=np.float64)
            registered = np.asarray(result.registered_image)
            tre = mean_tre_pixels(ground_truth.moving_to_fixed, estimated, points)
            translation_error = centered_translation_error_pixels(
                ground_truth.moving_to_fixed,
                estimated,
                center,
            )
            rotation_error = (
                rotation_error_degrees(ground_truth.moving_to_fixed, estimated)
                if method_model == "rigid"
                else None
            )
            linear_error = (
                affine_linear_error(ground_truth.moving_to_fixed, estimated)
                if method_model == "affine"
                else None
            )
            within = within_model_tolerance(
                method_model,
                optimizer_success=bool(result.success),
                mean_tre_pixels=tre,
                translation_error_pixels=translation_error,
                rotation_error_degrees=rotation_error,
                affine_linear_error=linear_error,
                thresholds=thresholds,
            )
            convergence = dict(result.convergence_info)
            phase_response = convergence.get("response")
            final_ecc = convergence.get("final_ecc")
            levels_completed = convergence.get("levels_completed")
            record = {
                "case_id": case_id,
                "source_id": source_id,
                "condition": str(condition_metadata.get("type", "clean")),
                "motion_model": method_model,
                "method_id": method_id,
                "method_label": str(method_spec.get("label", method_id)),
                "initialization": str(method_spec.get("initialization", "direct")),
                "strategy": "multiresolution" if method_id.endswith("multiresolution") else "single_resolution",
                "success": bool(result.success),
                "within_tolerance": bool(within),
                "failure_reason": result.failure_reason,
                "mean_tre_pixels": float(tre),
                "translation_error_pixels": float(translation_error),
                "rotation_error_degrees": None if rotation_error is None else float(rotation_error),
                "affine_linear_error": None if linear_error is None else float(linear_error),
                "overlap_fraction": float(overlap),
                "ncc_before": float(ncc_before),
                "ncc_after": float(normalized_cross_correlation(fixed, registered)),
                "ssim_before": float(ssim_before),
                "ssim_after": float(structural_similarity(fixed, registered)),
                "phase_response": None if phase_response is None else float(phase_response),
                "final_ecc": None if final_ecc is None else float(final_ecc),
                "levels_completed": None if levels_completed is None else int(levels_completed),
                "runtime_ms": float(result.runtime_seconds * 1000.0),
                "ground_truth_transform": ground_truth.moving_to_fixed.tolist(),
                "estimated_transform": estimated.tolist(),
                "condition_metadata": condition_metadata,
            }
            records.append(record)

            status = "PASS" if within else "FAIL"
            diagnostic = (
                f"response={float(phase_response):.3f}"
                if phase_response is not None
                else f"ECC={float(final_ecc):.4f}" if final_ecc is not None else "score=n/a"
            )
            print(
                f"{case_id:<36} {method_id:<31} "
                f"TRE={tre:7.3f} px  runtime={record['runtime_ms']:7.2f} ms  {diagnostic:<15} {status}"
            )

            if (case_id, method_id) in representative:
                _save_case_outputs(
                    output_dir,
                    case_id,
                    method_id,
                    fixed,
                    moving,
                    registered,
                    overlap_mask,
                )

    with (output_dir / "baseline_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, sort_keys=True)
        handle.write("\n")
    _write_csv(output_dir / "baseline_results.csv", records)

    method_summary = summarize_by_key(records, "method_id")
    condition_summary = summarize_by_key(records, "condition")
    motion_summary = summarize_by_key(records, "motion_model")
    labels = {str(key): str(value.get("label", key)) for key, value in methods.items()}
    _write_method_table(output_dir / "baseline_method_table.csv", method_summary, labels)
    _write_plots(records, method_summary, labels, output_dir)

    summary = {
        "case_count": len(cases),
        "registration_count": len(records),
        "optimizer_success_count": sum(bool(r["success"]) for r in records),
        "within_tolerance_count": sum(bool(r["within_tolerance"]) for r in records),
        "method_summary": method_summary,
        "condition_summary": condition_summary,
        "motion_model_summary": motion_summary,
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    report_path = resolve_project_path(PROJECT_ROOT, output["report_snapshot"])
    write_report_snapshot(
        report_path,
        {
            "week": 3,
            "week_day": 5,
            "global_day": 15,
            "title": "Integrated monomodal frequency and intensity baselines",
            "status": "experiment_completed",
            "seed": seed,
            "source_images": sorted(sources),
            "working_shape": [height, width],
            "base_case_count": len(cases),
            "registration_count": len(records),
            "optimizer_success_count": summary["optimizer_success_count"],
            "within_tolerance_count": summary["within_tolerance_count"],
            "within_tolerance_rate": summary["within_tolerance_count"] / len(records),
            "method_summary": method_summary,
            "condition_summary": condition_summary,
            "motion_model_summary": motion_summary,
            "tolerances": {
                "translation_error_pixels": thresholds.translation_error_pixels,
                "mean_tre_pixels": thresholds.mean_tre_pixels,
                "rigid_translation_error_pixels": thresholds.rigid_translation_error_pixels,
                "rotation_error_degrees": thresholds.rotation_error_degrees,
                "affine_translation_error_pixels": thresholds.affine_translation_error_pixels,
                "affine_linear_error": thresholds.affine_linear_error,
            },
            "raw_output_directory": Path(output["directory"]).as_posix(),
            "daily_summary": "docs/daily/day_15_summary.md",
            "weekly_summary": "docs/weekly/week_03_summary.md",
            "technical_note": "docs/WEEK03_BASELINE_COMPARISON.md",
        },
    )

    print()
    print("Summary")
    print("-------")
    print(f"Optimizer successes: {summary['optimizer_success_count']}/{len(records)}")
    print(f"Within tolerance:    {summary['within_tolerance_count']}/{len(records)}")
    for method_id, values in method_summary.items():
        print(
            f"{method_id:<31} pass={values['within_tolerance_count']}/{values['registration_count']} "
            f"median TRE={values['median_mean_tre_pixels']:.3f} px  "
            f"mean runtime={values['mean_runtime_ms']:.2f} ms"
        )
    print(f"Results: {output['directory']}")
    print(f"Report snapshot: {output['report_snapshot']}")
    print("Week 3 Day 5 complete: integrated monomodal baseline results generated and summarized.")


if __name__ == "__main__":
    main()
