from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config, resolve_project_path
from image_registration.degradations import gaussian_blur, gaussian_noise
from image_registration.evaluation import normalized_cross_correlation
from image_registration.io import load_image
from image_registration.reporting import write_report_snapshot
from image_registration.overlap import (
    apply_field_of_view,
    combine_valid_masks,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
    transformed_support_mask,
)
from image_registration.phase_correlation import PhaseCorrelationRegistration
from image_registration.synthetic import GroundTruthTransform, SyntheticPair, generate_synthetic_pair
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
        description="Run Week 3 Day 2 phase-correlation robustness sweeps."
    )
    parser.add_argument(
        "--config",
        default="configs/week03_day02_phase_robustness.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    return parser.parse_args()


def _make_pair(fixed: np.ndarray, tx: float, ty: float) -> SyntheticPair:
    moving_to_fixed = translation_matrix(tx, ty)
    ground_truth = GroundTruthTransform(
        transform_type="translation",
        parameters={"tx": tx, "ty": ty},
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=invert_transform(moving_to_fixed),
    )
    return generate_synthetic_pair(fixed, ground_truth, interpolation="linear")


def _natural_moving_valid_mask(pair: SyntheticPair) -> np.ndarray:
    return transformed_support_mask(
        pair.fixed.shape,
        pair.ground_truth.fixed_to_moving,
        destination_shape=pair.moving.shape[:2],
    )


def _fixed_overlap_fraction(pair: SyntheticPair, moving_valid_mask: np.ndarray) -> float:
    mask = overlap_mask_in_fixed_space(
        moving_valid_mask,
        pair.ground_truth.moving_to_fixed,
        fixed_shape=pair.fixed.shape[:2],
    )
    return overlap_fraction(mask)


def _evaluate_case(
    pair: SyntheticPair,
    moving_input: np.ndarray,
    *,
    method: PhaseCorrelationRegistration,
    tolerance: float,
    sweep: str,
    case_id: str,
    severity_value: float,
    severity_label: str,
    overlap_value: float,
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    true_tx = float(pair.ground_truth.parameters["tx"])
    true_ty = float(pair.ground_truth.parameters["ty"])

    ncc_before = normalized_cross_correlation(pair.fixed, moving_input)
    result = method.register(pair.fixed, moving_input)
    estimated_tx = float(result.transform[0, 2])
    estimated_ty = float(result.transform[1, 2])
    translation_error = float(
        np.hypot(estimated_tx - true_tx, estimated_ty - true_ty)
    )
    ncc_after = normalized_cross_correlation(pair.fixed, result.registered_image)
    within_tolerance = bool(result.success and translation_error <= tolerance)

    info = result.convergence_info
    record: dict[str, Any] = {
        "sweep": sweep,
        "case_id": case_id,
        "severity_value": float(severity_value),
        "severity_label": severity_label,
        "true_tx": true_tx,
        "true_ty": true_ty,
        "translation_magnitude_pixels": float(np.hypot(true_tx, true_ty)),
        "estimated_tx": estimated_tx,
        "estimated_ty": estimated_ty,
        "translation_error_pixels": translation_error,
        "phase_response": float(info.get("response", float("nan"))),
        "overlap_fraction": float(overlap_value),
        "use_hanning_window": bool(method.use_hanning_window),
        "ncc_before": float(ncc_before),
        "ncc_after": float(ncc_after),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "method_success": bool(result.success),
        "within_tolerance": within_tolerance,
        "failure_reason": result.failure_reason,
    }
    if extra:
        record.update(extra)
    return record, np.asarray(result.registered_image)


def _summary_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "case_count": 0,
            "passed_within_tolerance": 0,
            "success_rate": 0.0,
        }

    errors = np.array([float(row["translation_error_pixels"]) for row in records])
    responses = np.array([float(row["phase_response"]) for row in records])
    runtimes = np.array([float(row["runtime_ms"]) for row in records])
    passed = sum(bool(row["within_tolerance"]) for row in records)
    return {
        "case_count": len(records),
        "passed_within_tolerance": passed,
        "success_rate": passed / len(records),
        "mean_translation_error_pixels": float(np.mean(errors)),
        "median_translation_error_pixels": float(np.median(errors)),
        "max_translation_error_pixels": float(np.max(errors)),
        "mean_phase_response": float(np.mean(responses)),
        "mean_runtime_ms": float(np.mean(runtimes)),
    }


def _plot_single_sweep(
    records: list[dict[str, Any]],
    *,
    x_key: str,
    x_label: str,
    title: str,
    output_path: Path,
    tolerance: float,
    invert_x: bool = False,
) -> None:
    x = np.array([float(row[x_key]) for row in records], dtype=np.float64)
    y = np.array([float(row["translation_error_pixels"]) for row in records], dtype=np.float64)

    fig = Figure(figsize=(7.3, 4.8))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    axis.plot(x, y, marker="o", label="translation error")
    axis.axhline(tolerance, linestyle="--", label=f"tolerance {tolerance:.2f} px")
    axis.set_xlabel(x_label)
    axis.set_ylabel("Translation-vector error (pixels)")
    axis.set_title(title)
    axis.grid(True, alpha=0.25)
    axis.legend()
    if invert_x:
        axis.invert_xaxis()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.clear()


def _plot_response_sweep(
    records: list[dict[str, Any]],
    *,
    x_key: str,
    x_label: str,
    title: str,
    output_path: Path,
    invert_x: bool = False,
) -> None:
    x = np.array([float(row[x_key]) for row in records], dtype=np.float64)
    y = np.array([float(row["phase_response"]) for row in records], dtype=np.float64)

    fig = Figure(figsize=(7.3, 4.8))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    axis.plot(x, y, marker="o")
    axis.set_xlabel(x_label)
    axis.set_ylabel("Phase-correlation response")
    axis.set_title(title)
    axis.grid(True, alpha=0.25)
    if invert_x:
        axis.invert_xaxis()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.clear()


def _plot_window_comparison(
    records: list[dict[str, Any]],
    *,
    output_path: Path,
    tolerance: float,
) -> None:
    condition_order: list[str] = []
    for row in records:
        condition = str(row["condition"])
        if condition not in condition_order:
            condition_order.append(condition)

    positions = np.arange(len(condition_order), dtype=np.float64)
    fig = Figure(figsize=(8.0, 4.9))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)

    for enabled, label in [(False, "window off"), (True, "Hanning window")]:
        values = []
        for condition in condition_order:
            match = next(
                row
                for row in records
                if str(row["condition"]) == condition
                and bool(row["use_hanning_window"]) is enabled
            )
            values.append(float(match["translation_error_pixels"]))
        axis.plot(positions, values, marker="o", label=label)

    axis.axhline(tolerance, linestyle="--", label=f"tolerance {tolerance:.2f} px")
    axis.set_xticks(positions)
    axis.set_xticklabels(condition_order, rotation=20, ha="right")
    axis.set_ylabel("Translation-vector error (pixels)")
    axis.set_title("Hanning-window comparison under selected conditions")
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.clear()


def _save_representative_case(
    output_dir: Path,
    name: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
    overlap_mask: np.ndarray | None = None,
) -> None:
    case_dir = output_dir / "representative_cases" / name
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
        title=f"Week 3 Day 2: {name}",
    )
    if valid_mask is not None:
        save_grayscale_image(case_dir / "moving_valid_mask.png", valid_mask * 255)
    if overlap_mask is not None:
        save_grayscale_image(case_dir / "valid_overlap_fixed.png", overlap_mask * 255)


def _print_sweep_summary(name: str, summary: dict[str, Any]) -> None:
    print(
        f"{name:<24} "
        f"pass={summary['passed_within_tolerance']:>2}/{summary['case_count']:<2}  "
        f"rate={100.0 * float(summary['success_rate']):>6.1f}%  "
        f"median_error={float(summary.get('median_translation_error_pixels', float('nan'))):>7.3f} px  "
        f"max_error={float(summary.get('max_translation_error_pixels', float('nan'))):>7.3f} px"
    )


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)

    seed = int(config.get("experiment", {}).get("seed", 42))
    source = config.get("source", {})
    method_config = config.get("phase_correlation", {})
    validation = config.get("validation", {})
    sweeps = config.get("sweeps", {})
    output_config = config.get("output", {})

    source_path = resolve_project_path(PROJECT_ROOT, source["image"])
    loaded = load_image(source_path, color_mode=str(source.get("color_mode", "grayscale")))
    fixed = np.asarray(loaded.array)
    if fixed.ndim != 2:
        raise ValueError("Week 3 Day 2 source image must be 2D grayscale.")

    output_dir = resolve_project_path(PROJECT_ROOT, output_config["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = output_dir / "plots"

    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    tolerance = float(validation.get("translation_tolerance_pixels", 0.5))
    base_translation = validation.get("base_translation", {})
    base_tx = float(base_translation.get("tx", 16.0))
    base_ty = float(base_translation.get("ty", -11.0))

    default_method = PhaseCorrelationRegistration(
        use_hanning_window=bool(method_config.get("use_hanning_window", True)),
        subtract_mean=bool(method_config.get("subtract_mean", True)),
        interpolation=str(method_config.get("interpolation", "linear")),
        min_response=(
            None
            if method_config.get("min_response") is None
            else float(method_config["min_response"])
        ),
    )

    base_pair = _make_pair(fixed, base_tx, base_ty)
    base_valid = _natural_moving_valid_mask(base_pair)
    base_overlap = _fixed_overlap_fraction(base_pair, base_valid)

    all_records: list[dict[str, Any]] = []
    grouped_records: dict[str, list[dict[str, Any]]] = {}

    print()
    print("Week 3 Day 2 phase-correlation robustness")
    print("-------------------------------------------")
    print(f"Source image: {source_path.relative_to(PROJECT_ROOT)}")
    print(f"Seed: {seed}")
    print(f"Tolerance: {tolerance:.3f} pixels")
    print(f"Base translation: ({base_tx:+.2f}, {base_ty:+.2f})")
    print(f"Base geometric overlap: {base_overlap:.3f}")
    print()

    # Gaussian-noise severity sweep. The RNG is reset at each level so the same
    # standardized noise realization is scaled by the configured severity.
    noise_records: list[dict[str, Any]] = []
    for index, sigma_fraction in enumerate(
        sweeps.get("gaussian_noise", {}).get("sigma_fractions", []), start=1
    ):
        sigma = float(sigma_fraction)
        if sigma == 0.0:
            moving = base_pair.moving.copy()
        else:
            moving = gaussian_noise(
                base_pair.moving,
                sigma_fraction=sigma,
                rng=np.random.default_rng(seed),
            )
        record, registered = _evaluate_case(
            base_pair,
            moving,
            method=default_method,
            tolerance=tolerance,
            sweep="gaussian_noise",
            case_id=f"noise_{index:02d}",
            severity_value=sigma,
            severity_label=f"sigma_fraction={sigma:g}",
            overlap_value=base_overlap,
            extra={"noise_sigma_fraction": sigma},
        )
        noise_records.append(record)
        all_records.append(record)
        print(
            f"noise {sigma:>5.2f}  error={record['translation_error_pixels']:>7.3f} px  "
            f"response={record['phase_response']:>6.3f}  "
            f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
        )
        if np.isclose(sigma, 1.50):
            _save_representative_case(
                output_dir,
                "severe_gaussian_noise",
                base_pair.fixed,
                moving,
                registered,
            )
    grouped_records["gaussian_noise"] = noise_records

    print()

    blur_records: list[dict[str, Any]] = []
    for index, sigma_value in enumerate(
        sweeps.get("gaussian_blur", {}).get("sigmas", []), start=1
    ):
        sigma = float(sigma_value)
        moving = base_pair.moving.copy() if sigma == 0.0 else gaussian_blur(base_pair.moving, sigma=sigma)
        record, registered = _evaluate_case(
            base_pair,
            moving,
            method=default_method,
            tolerance=tolerance,
            sweep="gaussian_blur",
            case_id=f"blur_{index:02d}",
            severity_value=sigma,
            severity_label=f"sigma={sigma:g}",
            overlap_value=base_overlap,
            extra={"blur_sigma": sigma},
        )
        blur_records.append(record)
        all_records.append(record)
        print(
            f"blur  {sigma:>5.2f}  error={record['translation_error_pixels']:>7.3f} px  "
            f"response={record['phase_response']:>6.3f}  "
            f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
        )
        if np.isclose(sigma, 8.0):
            _save_representative_case(
                output_dir,
                "severe_gaussian_blur",
                base_pair.fixed,
                moving,
                registered,
            )
    grouped_records["gaussian_blur"] = blur_records

    print()

    overlap_records: list[dict[str, Any]] = []
    for index, fraction_value in enumerate(
        sweeps.get("partial_overlap", {}).get("field_of_view_fractions", []), start=1
    ):
        fraction = float(fraction_value)
        fov_mask = rectangular_field_of_view_mask(
            base_pair.moving.shape,
            width_fraction=fraction,
            height_fraction=fraction,
        )
        valid_mask = combine_valid_masks(base_valid, fov_mask)
        moving = apply_field_of_view(base_pair.moving, fov_mask, fill_value=0.0)
        fixed_overlap_mask = overlap_mask_in_fixed_space(
            valid_mask,
            base_pair.ground_truth.moving_to_fixed,
            fixed_shape=base_pair.fixed.shape[:2],
        )
        actual_overlap = overlap_fraction(fixed_overlap_mask)
        record, registered = _evaluate_case(
            base_pair,
            moving,
            method=default_method,
            tolerance=tolerance,
            sweep="partial_overlap",
            case_id=f"overlap_{index:02d}",
            severity_value=actual_overlap,
            severity_label=f"overlap={100.0 * actual_overlap:.2f}%",
            overlap_value=actual_overlap,
            extra={"field_of_view_fraction": fraction},
        )
        overlap_records.append(record)
        all_records.append(record)
        print(
            f"overlap FOV={fraction:>4.2f}  actual={100.0 * actual_overlap:>6.2f}%  "
            f"error={record['translation_error_pixels']:>7.3f} px  "
            f"response={record['phase_response']:>6.3f}  "
            f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
        )
        if np.isclose(fraction, 0.05):
            _save_representative_case(
                output_dir,
                "extreme_partial_overlap",
                base_pair.fixed,
                moving,
                registered,
                valid_mask=valid_mask,
                overlap_mask=fixed_overlap_mask,
            )
    grouped_records["partial_overlap"] = overlap_records

    print()

    magnitude_records: list[dict[str, Any]] = []
    vectors = sweeps.get("translation_magnitude", {}).get("vectors", [])
    for index, vector in enumerate(vectors, start=1):
        tx, ty = float(vector[0]), float(vector[1])
        pair = _make_pair(fixed, tx, ty)
        valid = _natural_moving_valid_mask(pair)
        actual_overlap = _fixed_overlap_fraction(pair, valid)
        magnitude = float(np.hypot(tx, ty))
        record, _ = _evaluate_case(
            pair,
            pair.moving,
            method=default_method,
            tolerance=tolerance,
            sweep="translation_magnitude",
            case_id=f"magnitude_{index:02d}",
            severity_value=magnitude,
            severity_label=f"magnitude={magnitude:.2f}px",
            overlap_value=actual_overlap,
        )
        magnitude_records.append(record)
        all_records.append(record)
        print(
            f"magnitude {magnitude:>7.2f} px  overlap={100.0 * actual_overlap:>6.2f}%  "
            f"error={record['translation_error_pixels']:>7.3f} px  "
            f"response={record['phase_response']:>6.3f}  "
            f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
        )
    grouped_records["translation_magnitude"] = magnitude_records

    print()

    subpixel_records: list[dict[str, Any]] = []
    subpixel_vectors = sweeps.get("subpixel", {}).get("vectors", [])
    for index, vector in enumerate(subpixel_vectors, start=1):
        tx, ty = float(vector[0]), float(vector[1])
        pair = _make_pair(fixed, tx, ty)
        valid = _natural_moving_valid_mask(pair)
        actual_overlap = _fixed_overlap_fraction(pair, valid)
        fractional_offset = float(np.hypot(tx - np.rint(tx), ty - np.rint(ty)))
        record, _ = _evaluate_case(
            pair,
            pair.moving,
            method=default_method,
            tolerance=tolerance,
            sweep="subpixel",
            case_id=f"subpixel_{index:02d}",
            severity_value=fractional_offset,
            severity_label=f"fractional_offset={fractional_offset:.3f}",
            overlap_value=actual_overlap,
            extra={"fractional_offset_pixels": fractional_offset},
        )
        subpixel_records.append(record)
        all_records.append(record)
        print(
            f"subpixel true=({tx:+6.2f}, {ty:+6.2f})  "
            f"error={record['translation_error_pixels']:>7.3f} px  "
            f"response={record['phase_response']:>6.3f}  "
            f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
        )
    grouped_records["subpixel"] = subpixel_records

    print()

    window_records: list[dict[str, Any]] = []
    window_config = sweeps.get("windowing_comparison", {})
    window_tx, window_ty = [float(value) for value in window_config.get("translation", [96.0, -72.0])]
    window_pair = _make_pair(fixed, window_tx, window_ty)
    window_natural_valid = _natural_moving_valid_mask(window_pair)
    window_natural_overlap = _fixed_overlap_fraction(window_pair, window_natural_valid)

    for condition_index, condition in enumerate(window_config.get("conditions", []), start=1):
        condition_id = str(condition["id"])
        condition_type = str(condition.get("type", "clean"))
        moving = window_pair.moving.copy()
        actual_overlap = window_natural_overlap

        if condition_type == "gaussian_blur":
            moving = gaussian_blur(moving, sigma=float(condition["sigma"]))
        elif condition_type == "gaussian_noise":
            moving = gaussian_noise(
                moving,
                sigma_fraction=float(condition["sigma_fraction"]),
                rng=np.random.default_rng(seed),
            )
        elif condition_type == "restricted_fov":
            fov_fraction = float(condition["field_of_view_fraction"])
            fov_mask = rectangular_field_of_view_mask(
                moving.shape,
                width_fraction=fov_fraction,
                height_fraction=fov_fraction,
            )
            moving = apply_field_of_view(moving, fov_mask, fill_value=0.0)
            valid_mask = combine_valid_masks(window_natural_valid, fov_mask)
            actual_overlap = _fixed_overlap_fraction(window_pair, valid_mask)
        elif condition_type != "clean":
            raise ValueError(f"Unsupported windowing comparison condition: {condition_type}")

        for use_hanning in (False, True):
            method = PhaseCorrelationRegistration(
                use_hanning_window=use_hanning,
                subtract_mean=bool(method_config.get("subtract_mean", True)),
                interpolation=str(method_config.get("interpolation", "linear")),
                min_response=(
                    None
                    if method_config.get("min_response") is None
                    else float(method_config["min_response"])
                ),
            )
            record, _ = _evaluate_case(
                window_pair,
                moving,
                method=method,
                tolerance=tolerance,
                sweep="windowing_comparison",
                case_id=f"window_{condition_index:02d}_{'on' if use_hanning else 'off'}",
                severity_value=float(condition_index),
                severity_label=condition_id,
                overlap_value=actual_overlap,
                extra={
                    "condition": condition_id,
                    "condition_type": condition_type,
                },
            )
            window_records.append(record)
            all_records.append(record)
            print(
                f"window {'ON ' if use_hanning else 'OFF'} {condition_id:<16}  "
                f"error={record['translation_error_pixels']:>8.3f} px  "
                f"response={record['phase_response']:>6.3f}  "
                f"{'PASS' if record['within_tolerance'] else 'FAIL'}"
            )
    grouped_records["windowing_comparison"] = window_records

    # Store machine-readable outputs.
    csv_fields = [
        "sweep",
        "case_id",
        "severity_value",
        "severity_label",
        "true_tx",
        "true_ty",
        "translation_magnitude_pixels",
        "estimated_tx",
        "estimated_ty",
        "translation_error_pixels",
        "phase_response",
        "overlap_fraction",
        "use_hanning_window",
        "ncc_before",
        "ncc_after",
        "runtime_ms",
        "method_success",
        "within_tolerance",
        "failure_reason",
        "noise_sigma_fraction",
        "blur_sigma",
        "field_of_view_fraction",
        "fractional_offset_pixels",
        "condition",
        "condition_type",
    ]
    with (output_dir / "phase_robustness_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_records)

    with (output_dir / "phase_robustness_results.json").open("w", encoding="utf-8") as handle:
        json.dump(all_records, handle, indent=2)
        handle.write("\n")

    summaries = {
        name: _summary_for_records(records)
        for name, records in grouped_records.items()
    }
    summary = {
        "method": "phase_correlation",
        "motion_model": "translation",
        "seed": seed,
        "translation_tolerance_pixels": tolerance,
        "base_translation": {"tx": base_tx, "ty": base_ty},
        "base_geometric_overlap_fraction": base_overlap,
        "total_case_count": len(all_records),
        "sweeps": summaries,
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    report_summary = {
        "week": 3,
        "global_day": 12,
        "week_day": 2,
        "title": "Phase-correlation robustness",
        "status": "complete",
        **summary,
        "raw_output_directory": output_config["directory"],
        "daily_summary": "docs/daily/day_12_summary.md",
        "technical_note": "docs/PHASE_CORRELATION_ROBUSTNESS.md",
    }
    write_report_snapshot(
        PROJECT_ROOT / "reports/week03_day02_phase_robustness.json",
        report_summary,
    )

    # Figures are derived directly from the saved records.
    _plot_single_sweep(
        noise_records,
        x_key="noise_sigma_fraction",
        x_label="Gaussian noise sigma fraction",
        title="Phase correlation under Gaussian noise",
        output_path=plots_dir / "translation_error_vs_noise.png",
        tolerance=tolerance,
    )
    _plot_response_sweep(
        noise_records,
        x_key="noise_sigma_fraction",
        x_label="Gaussian noise sigma fraction",
        title="Phase response under Gaussian noise",
        output_path=plots_dir / "phase_response_vs_noise.png",
    )
    _plot_single_sweep(
        blur_records,
        x_key="blur_sigma",
        x_label="Gaussian blur sigma",
        title="Phase correlation under Gaussian blur",
        output_path=plots_dir / "translation_error_vs_blur.png",
        tolerance=tolerance,
    )
    _plot_response_sweep(
        blur_records,
        x_key="blur_sigma",
        x_label="Gaussian blur sigma",
        title="Phase response under Gaussian blur",
        output_path=plots_dir / "phase_response_vs_blur.png",
    )
    _plot_single_sweep(
        overlap_records,
        x_key="overlap_fraction",
        x_label="Valid geometric overlap fraction",
        title="Phase correlation under decreasing overlap",
        output_path=plots_dir / "translation_error_vs_overlap.png",
        tolerance=tolerance,
        invert_x=True,
    )
    _plot_response_sweep(
        overlap_records,
        x_key="overlap_fraction",
        x_label="Valid geometric overlap fraction",
        title="Phase response under decreasing overlap",
        output_path=plots_dir / "phase_response_vs_overlap.png",
        invert_x=True,
    )
    _plot_single_sweep(
        magnitude_records,
        x_key="translation_magnitude_pixels",
        x_label="True translation magnitude (pixels)",
        title="Phase correlation across translation magnitude",
        output_path=plots_dir / "translation_error_vs_magnitude.png",
        tolerance=tolerance,
    )
    _plot_single_sweep(
        subpixel_records,
        x_key="fractional_offset_pixels",
        x_label="Fractional distance from nearest integer shift (pixels)",
        title="Subpixel phase-correlation error",
        output_path=plots_dir / "subpixel_error.png",
        tolerance=tolerance,
    )
    _plot_window_comparison(
        window_records,
        output_path=plots_dir / "windowing_comparison.png",
        tolerance=tolerance,
    )

    print()
    print("Summary by sweep")
    print("----------------")
    for name in [
        "gaussian_noise",
        "gaussian_blur",
        "partial_overlap",
        "translation_magnitude",
        "subpixel",
        "windowing_comparison",
    ]:
        _print_sweep_summary(name, summaries[name])

    print()
    print(f"Total evaluated registrations: {len(all_records)}")
    print(f"Results: {output_dir.relative_to(PROJECT_ROOT)}")
    print("Week 3 Day 2 complete: controlled robustness sweeps generated and summarized.")


if __name__ == "__main__":
    main()
