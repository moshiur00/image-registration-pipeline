from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config, resolve_project_path
from image_registration.evaluation import normalized_cross_correlation
from image_registration.io import load_image
from image_registration.reporting import write_report_snapshot
from image_registration.phase_correlation import (
    PhaseCorrelationRegistration,
    phase_correlation_surface,
)
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair
from image_registration.transforms import invert_transform, translation_matrix
from image_registration.visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
    save_grayscale_image,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Week 3 Day 1 phase-correlation validation cases."
    )
    parser.add_argument(
        "--config",
        default="configs/week03_day01_phase_correlation.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    return parser.parse_args()


def _save_surface_figure(surface: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = surface.shape
    center_y, center_x = height // 2, width // 2
    peak_y, peak_x = np.unravel_index(np.argmax(surface), surface.shape)
    peak_tx = int(peak_x - center_x)
    peak_ty = int(peak_y - center_y)

    radius = int(min(64, center_x, center_y, width - center_x - 1, height - center_y - 1))
    cropped = surface[
        center_y - radius : center_y + radius + 1,
        center_x - radius : center_x + radius + 1,
    ]

    fig = Figure(figsize=(7.2, 5.6))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    image = axis.imshow(
        cropped,
        cmap="viridis",
        extent=[-radius, radius, radius, -radius],
        aspect="equal",
    )
    if -radius <= peak_tx <= radius and -radius <= peak_ty <= radius:
        axis.scatter([peak_tx], [peak_ty], marker="x", s=65, linewidths=1.8)
    axis.set_title(f"Centered phase-correlation surface, integer peak=({peak_tx}, {peak_ty})")
    axis.set_xlabel("Moving to Fixed x shift (pixels)")
    axis.set_ylabel("Moving to Fixed y shift (pixels)")
    fig.colorbar(image, ax=axis, label="Normalized correlation magnitude")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.clear()


def _save_representative_outputs(
    output_dir: Path,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
    surface: np.ndarray,
) -> None:
    rep = output_dir / "representative_case"
    save_grayscale_image(rep / "fixed.png", fixed)
    save_grayscale_image(rep / "moving.png", moving)
    save_grayscale_image(rep / "registered.png", registered)
    save_grayscale_image(rep / "alpha_overlay_before.png", alpha_overlay(fixed, moving))
    save_grayscale_image(rep / "alpha_overlay_after.png", alpha_overlay(fixed, registered))
    save_grayscale_image(rep / "checkerboard_before.png", checkerboard(fixed, moving))
    save_grayscale_image(rep / "checkerboard_after.png", checkerboard(fixed, registered))
    save_grayscale_image(rep / "absolute_difference_before.png", absolute_difference(fixed, moving))
    save_grayscale_image(
        rep / "absolute_difference_after.png",
        absolute_difference(fixed, registered),
    )
    save_comparison_figure(
        fixed,
        moving,
        registered,
        rep / "registration_comparison.png",
        title="Week 3 Day 1 phase correlation",
    )
    _save_surface_figure(surface, rep / "phase_correlation_surface.png")


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)

    source = config.get("source", {})
    method_config = config.get("phase_correlation", {})
    validation = config.get("validation", {})
    output_config = config.get("output", {})

    source_path = resolve_project_path(PROJECT_ROOT, source["image"])
    loaded = load_image(source_path, color_mode=str(source.get("color_mode", "grayscale")))
    fixed = np.asarray(loaded.array)
    if fixed.ndim != 2:
        raise ValueError("Week 3 Day 1 source image must be 2D grayscale.")

    output_dir = resolve_project_path(PROJECT_ROOT, output_config["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    method = PhaseCorrelationRegistration(
        use_hanning_window=bool(method_config.get("use_hanning_window", True)),
        subtract_mean=bool(method_config.get("subtract_mean", True)),
        interpolation=str(method_config.get("interpolation", "linear")),
        min_response=(
            None
            if method_config.get("min_response") is None
            else float(method_config["min_response"])
        ),
    )

    tolerance = float(validation.get("translation_tolerance_pixels", 0.5))
    cases = validation.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("validation.cases must contain at least one translation case.")

    records: list[dict[str, object]] = []
    representative_saved = False

    print()
    print("Week 3 Day 1 phase-correlation validation")
    print("-------------------------------------------")
    print(f"Source image: {source_path.relative_to(PROJECT_ROOT)}")
    print(f"Cases: {len(cases)}")
    print(f"Tolerance: {tolerance:.3f} pixels")
    print(f"Hanning window: {method.use_hanning_window}")
    print()

    for index, case in enumerate(cases, start=1):
        case_id = str(case["id"])
        true_tx = float(case["tx"])
        true_ty = float(case["ty"])
        moving_to_fixed = translation_matrix(true_tx, true_ty)
        ground_truth = GroundTruthTransform(
            transform_type="translation",
            parameters={"tx": true_tx, "ty": true_ty},
            moving_to_fixed=moving_to_fixed,
            fixed_to_moving=invert_transform(moving_to_fixed),
        )
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")

        ncc_before = normalized_cross_correlation(pair.fixed, pair.moving)
        result = method.register(pair.fixed, pair.moving)
        estimated_tx = float(result.transform[0, 2])
        estimated_ty = float(result.transform[1, 2])
        translation_error = float(
            np.linalg.norm(
                np.array([estimated_tx - true_tx, estimated_ty - true_ty], dtype=np.float64)
            )
        )
        ncc_after = normalized_cross_correlation(pair.fixed, result.registered_image)
        within_tolerance = bool(result.success and translation_error <= tolerance)

        info = result.convergence_info
        record = {
            "case_id": case_id,
            "true_tx": true_tx,
            "true_ty": true_ty,
            "estimated_tx": estimated_tx,
            "estimated_ty": estimated_ty,
            "translation_error_pixels": translation_error,
            "phase_response": float(info.get("response", float("nan"))),
            "ncc_before": ncc_before,
            "ncc_after": ncc_after,
            "runtime_ms": result.runtime_seconds * 1000.0,
            "success": bool(result.success),
            "within_tolerance": within_tolerance,
            "failure_reason": result.failure_reason,
        }
        records.append(record)

        print(
            f"{index:02d}/{len(cases):02d} {case_id:<28} "
            f"true=({true_tx:+7.2f}, {true_ty:+7.2f})  "
            f"est=({estimated_tx:+7.2f}, {estimated_ty:+7.2f})  "
            f"error={translation_error:.3f}  "
            f"response={record['phase_response']:.3f}  "
            f"{'PASS' if within_tolerance else 'FAIL'}"
        )

        if not representative_saved and (abs(true_tx) + abs(true_ty)) > 10.0:
            surface = phase_correlation_surface(
                pair.fixed,
                pair.moving,
                use_hanning_window=method.use_hanning_window,
                subtract_mean=method.subtract_mean,
            )
            _save_representative_outputs(
                output_dir,
                pair.fixed,
                pair.moving,
                result.registered_image,
                surface,
            )
            representative_saved = True

    passed = sum(bool(record["within_tolerance"]) for record in records)
    success_rate = passed / len(records)
    errors = np.array([float(record["translation_error_pixels"]) for record in records])
    runtimes = np.array([float(record["runtime_ms"]) for record in records])
    responses = np.array([float(record["phase_response"]) for record in records])

    summary = {
        "method": "phase_correlation",
        "motion_model": "translation",
        "case_count": len(records),
        "passed_within_tolerance": passed,
        "success_rate": success_rate,
        "translation_tolerance_pixels": tolerance,
        "mean_translation_error_pixels": float(np.mean(errors)),
        "median_translation_error_pixels": float(np.median(errors)),
        "max_translation_error_pixels": float(np.max(errors)),
        "mean_phase_response": float(np.mean(responses)),
        "mean_runtime_ms": float(np.mean(runtimes)),
    }

    fieldnames = list(records[0].keys())
    with (output_dir / "phase_correlation_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    with (output_dir / "phase_correlation_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    report_summary = {
        "week": 3,
        "global_day": 11,
        "week_day": 1,
        "title": "Phase correlation for translation estimation",
        "status": "complete",
        **summary,
        "raw_output_directory": output_config["directory"],
        "daily_summary": "docs/daily/day_11_summary.md",
        "technical_note": "docs/PHASE_CORRELATION.md",
    }
    write_report_snapshot(
        PROJECT_ROOT / "reports/week03_day01_phase_correlation.json",
        report_summary,
    )

    print()
    print("Summary")
    print("-------")
    print(f"Passed within tolerance: {passed}/{len(records)}")
    print(f"Success rate: {100.0 * success_rate:.1f}%")
    print(f"Mean translation error: {summary['mean_translation_error_pixels']:.4f} px")
    print(f"Median translation error: {summary['median_translation_error_pixels']:.4f} px")
    print(f"Maximum translation error: {summary['max_translation_error_pixels']:.4f} px")
    print(f"Mean phase response: {summary['mean_phase_response']:.4f}")
    print(f"Mean runtime: {summary['mean_runtime_ms']:.3f} ms")
    print(f"Results: {output_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
