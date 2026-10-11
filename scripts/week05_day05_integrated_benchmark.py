from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from copy import deepcopy
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

from image_registration.affine_ransac import affine_transform_diagnostics
from image_registration.config import load_config
from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration
from image_registration.io import load_image
from image_registration.mi_study import SUPPORTED_MI_PREPROCESSING, apply_mi_preprocessing
from image_registration.multimodal import (
    SUPPORTED_MULTIMODAL_MAPPING_TYPES,
    apply_multimodal_mapping,
)
from image_registration.mutual_information import (
    MutualInformationAffineRegistration,
    MutualInformationConfig,
    MutualInformationRigidRegistration,
)
from image_registration.overlap import apply_field_of_view, rectangular_field_of_view_mask
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import affine_matrix, invert_transform, rigid_matrix, rotation_matrix
from image_registration.visualization import (
    alpha_overlay,
    edge_overlay,
    save_comparison_figure,
    save_grayscale_image,
    save_joint_histogram,
    save_metric_trace,
    save_rgb_image,
)
from image_registration.week5_benchmark import (
    compact_seed_variability,
    group_summaries,
    paired_method_outcomes,
    summarize_benchmark_records,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Week 5 Day 25 frozen integrated multimodal benchmark."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _mi_config(values: dict[str, Any]) -> MutualInformationConfig:
    return MutualInformationConfig(
        histogram_bins=int(values["histogram_bins"]),
        sampling_strategy=str(values["sampling_strategy"]),
        sampling_percentage=float(values["sampling_percentage"]),
        sampling_seed=int(values["sampling_seed"]),
        learning_rate=float(values["learning_rate"]),
        minimum_step=float(values["minimum_step"]),
        number_of_iterations=int(values["number_of_iterations"]),
        relaxation_factor=float(values["relaxation_factor"]),
        gradient_magnitude_tolerance=float(values["gradient_magnitude_tolerance"]),
        shrink_factors=tuple(int(value) for value in values["shrink_factors"]),
        smoothing_sigmas=tuple(float(value) for value in values["smoothing_sigmas"]),
        initialization=str(values["initialization"]),
    )


def _validate_config(config: dict[str, Any]) -> None:
    required = {
        "experiment",
        "frozen_mutual_information",
        "frozen_mi_preprocessing",
        "frozen_ecc",
        "validation",
        "plausibility",
        "sources",
        "cases",
        "carried_evidence",
        "output",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Missing Day 25 configuration sections: {', '.join(missing)}")

    mi = dict(config["frozen_mutual_information"])
    _mi_config(mi)
    if int(mi["histogram_bins"]) != 32:
        raise ValueError("Day 25 must keep the frozen 32-bin MI setting.")
    if str(mi["sampling_strategy"]) != "none":
        raise ValueError("Day 25 must keep the frozen full-sampling MI setting.")
    if str(mi["initialization"]) != "identity":
        raise ValueError("Day 25 must keep the frozen identity MI initialization.")

    preprocessing = dict(config["frozen_mi_preprocessing"])
    preprocessing_type = str(preprocessing.get("type", "")).strip().lower()
    if preprocessing_type not in SUPPORTED_MI_PREPROCESSING:
        raise ValueError(f"Unsupported Day 25 MI preprocessing: {preprocessing_type}")
    if preprocessing_type != "gaussian_smooth" or float(preprocessing.get("sigma", -1.0)) != 1.0:
        raise ValueError("Day 25 must keep Day 22 Gaussian smoothing with sigma 1.0.")

    ecc = dict(config["frozen_ecc"])
    if set(ecc) != {"rigid", "affine"}:
        raise ValueError("Day 25 requires frozen rigid and affine ECC baselines.")
    if str(ecc["rigid"].get("motion_model")) != "rigid":
        raise ValueError("The Day 25 rigid ECC baseline must use the rigid model.")
    if str(ecc["affine"].get("motion_model")) != "affine":
        raise ValueError("The Day 25 affine ECC baseline must use the affine model.")

    seen: set[str] = set()
    cases = list(config["cases"])
    if not cases:
        raise ValueError("Day 25 final test cases must not be empty.")
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError(f"Missing or duplicate Day 25 case id: {case_id}")
        seen.add(case_id)
        if not case_id.endswith("_test"):
            raise ValueError(f"Day 25 case '{case_id}' must be explicitly marked as a final test case.")
        if str(case.get("motion_model")) not in {"rigid", "affine"}:
            raise ValueError(f"Case {case_id} must use rigid or affine geometry.")
        if str(case.get("source")) not in config["sources"]:
            raise ValueError(f"Case {case_id} references an unknown source.")
        mapping = case.get("modality_mapping")
        if mapping is not None:
            mapping_type = str(mapping.get("type", "")).strip().lower()
            if mapping_type not in SUPPORTED_MULTIMODAL_MAPPING_TYPES:
                raise ValueError(f"Case {case_id} uses unsupported mapping '{mapping_type}'.")
        postprocess = case.get("postprocess")
        if postprocess is not None and str(postprocess.get("type", "")).strip().lower() != "restricted_fov":
            raise ValueError(f"Case {case_id} uses unsupported postprocess.")

    for key in ["day22_seed_variability_report", "day24_rire_report"]:
        path = _resolve(str(config["carried_evidence"][key]))
        if not path.exists():
            raise FileNotFoundError(f"Required carried evidence is missing: {path}")


def _rigid_ground_truth(fixed: np.ndarray, case: dict[str, Any]) -> GroundTruthTransform:
    center = image_center(fixed.shape)
    angle = float(case.get("angle_degrees", 0.0))
    tx = float(case.get("tx", 0.0))
    ty = float(case.get("ty", 0.0))
    moving_to_fixed = rigid_matrix(angle, tx=tx, ty=ty, center=center)
    return GroundTruthTransform(
        transform_type="rigid",
        parameters={
            "angle_degrees": angle,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
        },
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=invert_transform(moving_to_fixed),
    )


def _affine_ground_truth(fixed: np.ndarray, case: dict[str, Any]) -> GroundTruthTransform:
    center = image_center(fixed.shape)
    angle = float(case.get("angle_degrees", 0.0))
    scale_x = float(case.get("scale_x", 1.0))
    scale_y = float(case.get("scale_y", 1.0))
    shear_x = float(case.get("shear_x", 0.0))
    tx = float(case.get("tx", 0.0))
    ty = float(case.get("ty", 0.0))
    rotation = rotation_matrix(angle)[:2, :2]
    shear = np.asarray([[1.0, shear_x], [0.0, 1.0]], dtype=np.float64)
    scale = np.asarray([[scale_x, 0.0], [0.0, scale_y]], dtype=np.float64)
    linear = rotation @ shear @ scale
    moving_to_fixed = affine_matrix(linear, tx=tx, ty=ty, center=center)
    return GroundTruthTransform(
        transform_type="affine",
        parameters={
            "angle_degrees": angle,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "shear_x": shear_x,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
            "linear": linear.tolist(),
        },
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=invert_transform(moving_to_fixed),
    )


def _apply_postprocess(
    image: np.ndarray,
    spec: dict[str, Any] | None,
) -> tuple[np.ndarray, dict[str, Any] | None]:
    if spec is None:
        return image, None
    mask = rectangular_field_of_view_mask(
        image.shape,
        width_fraction=float(spec.get("width_fraction", 0.74)),
        height_fraction=float(spec.get("height_fraction", 0.80)),
        center_x_fraction=float(spec.get("center_x_fraction", 0.50)),
        center_y_fraction=float(spec.get("center_y_fraction", 0.50)),
    )
    output = apply_field_of_view(image, mask, fill_value=float(spec.get("fill_value", 0.0)))
    return np.asarray(output), {
        "type": "restricted_fov",
        "visible_fraction": float(np.mean(mask)),
        "width_fraction": float(spec.get("width_fraction", 0.74)),
        "height_fraction": float(spec.get("height_fraction", 0.80)),
    }


def _prepare_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {
        str(source_id): np.asarray(load_image(_resolve(str(path)), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }
    base_seed = int(config["experiment"].get("seed", 42))
    prepared: list[dict[str, Any]] = []
    for index, case in enumerate(config["cases"]):
        case_id = str(case["id"])
        fixed = sources[str(case["source"])]
        motion_model = str(case["motion_model"])
        ground_truth = (
            _rigid_ground_truth(fixed, case)
            if motion_model == "rigid"
            else _affine_ground_truth(fixed, case)
        )
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving = np.asarray(pair.moving)
        mapping_spec = case.get("modality_mapping")
        mapping_name = "none"
        mapping_metadata: dict[str, Any] | None = None
        if isinstance(mapping_spec, dict):
            mapped = apply_multimodal_mapping(
                moving,
                mapping_spec,
                rng=np.random.default_rng(base_seed + index * 1009),
            )
            moving = np.asarray(mapped.image)
            mapping_metadata = dict(mapped.metadata)
            mapping_name = str(mapping_metadata["type"])
        moving, postprocess_metadata = _apply_postprocess(moving, case.get("postprocess"))

        prepared.append(
            {
                "case_id": case_id,
                "motion_model": motion_model,
                "scope": str(case["scope"]),
                "condition": mapping_name if mapping_name != "none" else "monomodal_reference",
                "source": str(case["source"]),
                "fixed": np.asarray(fixed),
                "moving": np.asarray(moving),
                "ground_truth": ground_truth,
                "control_points_moving": np.asarray(pair.control_points_moving, dtype=np.float64),
                "center": image_center(fixed.shape),
                "mapping_metadata": mapping_metadata,
                "postprocess": postprocess_metadata,
            }
        )
    return prepared


def _build_ecc(spec: dict[str, Any]) -> ECCRegistration | MultiResolutionECCRegistration:
    common = {
        "motion_model": str(spec["motion_model"]),
        "initialization": str(spec["initialization"]),
        "max_iterations": int(spec["max_iterations"]),
        "epsilon": float(spec["epsilon"]),
        "gauss_filt_size": int(spec["gauss_filt_size"]),
        "interpolation": str(spec["interpolation"]),
        "phase_use_hanning_window": bool(spec.get("phase_use_hanning_window", True)),
        "phase_subtract_mean": bool(spec.get("phase_subtract_mean", True)),
        "min_ecc": spec.get("min_ecc"),
    }
    if str(spec["implementation"]) == "multiresolution":
        return MultiResolutionECCRegistration(
            **common,
            pyramid_scales=tuple(float(value) for value in spec["pyramid_scales"]),
            pre_smoothing_sigma=float(spec["pre_smoothing_sigma"]),
        )
    return ECCRegistration(**common)


def _affine_plausibility(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "min_abs_determinant": float(config["min_abs_determinant"]),
        "min_principal_scale": float(config["min_principal_scale"]),
        "max_principal_scale": float(config["max_principal_scale"]),
        "max_condition_number": float(config["max_condition_number"]),
        "max_shear_cosine": float(config["max_shear_cosine"]),
        "max_translation_fraction_of_diagonal": float(
            config["max_translation_fraction_of_diagonal"]
        ),
        "allow_reflection": bool(config["allow_reflection"]),
    }


def _evaluate(
    case: dict[str, Any],
    estimated: np.ndarray,
    *,
    method_success: bool,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not method_success:
        return {
            "within_tolerance": False,
            "plausible_transform": False,
            "tre_pixels": None,
            "rotation_error_degrees": None,
            "affine_linear_error": None,
            "translation_error_pixels": None,
            "parameter_error": None,
            "plausibility_diagnostics": None,
        }

    ground_truth = case["ground_truth"]
    tre = mean_tre_pixels(
        ground_truth.moving_to_fixed,
        estimated,
        case["control_points_moving"],
    )
    translation = centered_translation_error_pixels(
        ground_truth.moving_to_fixed,
        estimated,
        case["center"],
    )
    if case["motion_model"] == "rigid":
        rotation = rotation_error_degrees(ground_truth.moving_to_fixed, estimated)
        thresholds = config["validation"]["rigid"]
        within = (
            tre <= float(thresholds["tre_threshold_pixels"])
            and rotation <= float(thresholds["rotation_error_threshold_degrees"])
            and translation <= float(thresholds["translation_error_threshold_pixels"])
        )
        return {
            "within_tolerance": bool(within),
            "plausible_transform": True,
            "tre_pixels": float(tre),
            "rotation_error_degrees": float(rotation),
            "affine_linear_error": None,
            "translation_error_pixels": float(translation),
            "parameter_error": float(rotation),
            "plausibility_diagnostics": None,
        }

    linear_error = affine_linear_error(ground_truth.moving_to_fixed, estimated)
    diagnostics = affine_transform_diagnostics(
        estimated,
        image_shape=case["fixed"].shape,
        **_affine_plausibility(config["plausibility"]),
    )
    thresholds = config["validation"]["affine"]
    within = (
        diagnostics.plausible
        and tre <= float(thresholds["tre_threshold_pixels"])
        and linear_error <= float(thresholds["affine_linear_error_threshold"])
        and translation <= float(thresholds["translation_error_threshold_pixels"])
    )
    return {
        "within_tolerance": bool(within),
        "plausible_transform": bool(diagnostics.plausible),
        "tre_pixels": float(tre),
        "rotation_error_degrees": None,
        "affine_linear_error": float(linear_error),
        "translation_error_pixels": float(translation),
        "parameter_error": float(linear_error),
        "plausibility_diagnostics": {
            "determinant": diagnostics.determinant,
            "principal_scale_min": diagnostics.principal_scale_min,
            "principal_scale_max": diagnostics.principal_scale_max,
            "condition_number": diagnostics.condition_number,
            "shear_cosine": diagnostics.shear_cosine,
            "translation_norm_pixels": diagnostics.translation_norm_pixels,
            "translation_fraction_of_diagonal": diagnostics.translation_fraction_of_diagonal,
            "plausible": diagnostics.plausible,
            "rejection_reasons": list(diagnostics.rejection_reasons),
        },
    }


def _save_method_evidence(
    *,
    output_dir: Path,
    case: dict[str, Any],
    method: str,
    fixed_input: np.ndarray,
    moving_input: np.ndarray,
    registered: np.ndarray,
    metric_trace: list[dict[str, Any]],
    joint_bins: int,
) -> dict[str, str]:
    method_dir = output_dir / "cases" / case["case_id"] / method
    method_dir.mkdir(parents=True, exist_ok=True)
    comparison = save_comparison_figure(
        fixed_input,
        moving_input,
        registered,
        method_dir / "comparison.png",
        title=f"{case['case_id']}: {method}",
    )
    alpha_before = save_grayscale_image(
        method_dir / "alpha_overlay_before.png",
        alpha_overlay(fixed_input, moving_input),
    )
    alpha_after = save_grayscale_image(
        method_dir / "alpha_overlay_after.png",
        alpha_overlay(fixed_input, registered),
    )
    edge_after = save_rgb_image(
        method_dir / "edge_overlay_after.png",
        edge_overlay(fixed_input, registered),
    )
    joint_before = save_joint_histogram(
        fixed_input,
        moving_input,
        method_dir / "joint_histogram_before.png",
        bins=joint_bins,
        title=f"{case['case_id']}: {method} before",
    )
    joint_after = save_joint_histogram(
        fixed_input,
        registered,
        method_dir / "joint_histogram_after.png",
        bins=joint_bins,
        title=f"{case['case_id']}: {method} after",
    )
    paths = {
        "comparison": comparison.relative_to(output_dir).as_posix(),
        "alpha_before": alpha_before.relative_to(output_dir).as_posix(),
        "alpha_after": alpha_after.relative_to(output_dir).as_posix(),
        "edge_after": edge_after.relative_to(output_dir).as_posix(),
        "joint_histogram_before": joint_before.relative_to(output_dir).as_posix(),
        "joint_histogram_after": joint_after.relative_to(output_dir).as_posix(),
    }
    if metric_trace:
        trace_path = save_metric_trace(
            metric_trace,
            method_dir / "metric_trace.png",
            title=f"{case['case_id']}: Mattes MI convergence",
        )
        paths["metric_trace"] = trace_path.relative_to(output_dir).as_posix()
    return paths


def _run_registration(
    *,
    case: dict[str, Any],
    method: str,
    config: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    if method == "mutual_information":
        fixed_preprocessed = apply_mi_preprocessing(
            case["fixed"], config["frozen_mi_preprocessing"]
        )
        moving_preprocessed = apply_mi_preprocessing(
            case["moving"], config["frozen_mi_preprocessing"]
        )
        registration = (
            MutualInformationRigidRegistration(_mi_config(config["frozen_mutual_information"]))
            if case["motion_model"] == "rigid"
            else MutualInformationAffineRegistration(_mi_config(config["frozen_mutual_information"]))
        )
        fixed_input = np.asarray(fixed_preprocessed.image)
        moving_input = np.asarray(moving_preprocessed.image)
        result = registration.register(fixed_input, moving_input)
        convergence = result.convergence_info
        objective_name = "mattes_mutual_information"
        objective_value = convergence.get("final_metric_value")
        metric_trace = list(convergence.get("metric_trace", []))
        method_config = {
            "mutual_information": deepcopy(config["frozen_mutual_information"]),
            "preprocessing": deepcopy(config["frozen_mi_preprocessing"]),
        }
    else:
        fixed_input = np.asarray(case["fixed"])
        moving_input = np.asarray(case["moving"])
        ecc_spec = deepcopy(dict(config["frozen_ecc"][case["motion_model"]]))
        result = _build_ecc(ecc_spec).register(fixed_input, moving_input)
        convergence = result.convergence_info
        objective_name = "enhanced_correlation_coefficient"
        objective_value = convergence.get("final_ecc")
        metric_trace = []
        method_config = {"ecc": ecc_spec}

    estimated = np.asarray(result.transform, dtype=np.float64)
    evaluation = _evaluate(
        case,
        estimated,
        method_success=bool(result.success),
        config=config,
    )
    evidence = _save_method_evidence(
        output_dir=output_dir,
        case=case,
        method=method,
        fixed_input=fixed_input,
        moving_input=moving_input,
        registered=np.asarray(result.registered_image),
        metric_trace=metric_trace,
        joint_bins=int(config.get("visualization", {}).get("joint_histogram_bins", 64)),
    )
    record = {
        "case_id": case["case_id"],
        "motion_model": case["motion_model"],
        "scope": case["scope"],
        "condition": case["condition"],
        "source": case["source"],
        "method": method,
        "method_success": bool(result.success),
        "within_tolerance": bool(evaluation["within_tolerance"]),
        "plausible_transform": bool(evaluation["plausible_transform"]),
        "tre_pixels": evaluation["tre_pixels"],
        "rotation_error_degrees": evaluation["rotation_error_degrees"],
        "affine_linear_error": evaluation["affine_linear_error"],
        "translation_error_pixels": evaluation["translation_error_pixels"],
        "parameter_error": evaluation["parameter_error"],
        "plausibility_diagnostics": evaluation["plausibility_diagnostics"],
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "objective_name": objective_name,
        "objective_value": objective_value,
        "optimizer_iteration": convergence.get("optimizer_iteration"),
        "optimizer_stop_condition": convergence.get("optimizer_stop_condition"),
        "valid_metric_points": convergence.get("valid_metric_points"),
        "failure_reason": result.failure_reason,
        "estimated_moving_to_fixed": estimated.tolist(),
        "ground_truth": case["ground_truth"].as_dict(),
        "mapping_metadata": case["mapping_metadata"],
        "postprocess": case["postprocess"],
        "method_configuration": method_config,
        "evidence_paths": evidence,
    }
    result_path = output_dir / "cases" / case["case_id"] / method / "result.json"
    result_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "motion_model",
        "scope",
        "condition",
        "method",
        "method_success",
        "plausible_transform",
        "within_tolerance",
        "tre_pixels",
        "rotation_error_degrees",
        "affine_linear_error",
        "translation_error_pixels",
        "runtime_ms",
        "objective_name",
        "objective_value",
        "failure_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field) for field in fields})


def _save_summary_plots(
    output_dir: Path,
    grouped: list[dict[str, Any]],
) -> None:
    plots_dir = output_dir / "summary_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    models = ["rigid", "affine"]
    methods = ["mutual_information", "ecc"]
    x = np.arange(len(models), dtype=np.float64)
    width = 0.36

    lookup = {(item["motion_model"], item["method"]): item for item in grouped}

    fig = Figure(figsize=(7.5, 4.8))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    for index, method in enumerate(methods):
        values = [
            float(lookup[(model, method)]["within_tolerance_rate"]) for model in models
        ]
        axis.bar(x + (index - 0.5) * width, values, width=width, label=method)
    axis.set_xticks(x)
    axis.set_xticklabels(models)
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("Within-tolerance rate")
    axis.set_title("Day 25 geometric success by motion model")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "success_rate_by_model.png", dpi=150, bbox_inches="tight")
    fig.clear()

    fig = Figure(figsize=(7.5, 4.8))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    for index, method in enumerate(methods):
        values = [
            float(lookup[(model, method)]["median_tre_pixels"]) for model in models
        ]
        axis.bar(x + (index - 0.5) * width, values, width=width, label=method)
    axis.set_xticks(x)
    axis.set_xticklabels(models)
    axis.set_ylabel("Median TRE (pixels)")
    axis.set_title("Day 25 median geometric error by motion model")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "median_tre_by_model.png", dpi=150, bbox_inches="tight")
    fig.clear()

    fig = Figure(figsize=(7.5, 4.8))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    for index, method in enumerate(methods):
        values = [float(lookup[(model, method)]["mean_runtime_ms"]) for model in models]
        axis.bar(x + (index - 0.5) * width, values, width=width, label=method)
    axis.set_xticks(x)
    axis.set_xticklabels(models)
    axis.set_ylabel("Mean runtime (ms)")
    axis.set_title("Day 25 runtime by motion model")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots_dir / "runtime_by_model.png", dpi=150, bbox_inches="tight")
    fig.clear()


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "estimated_moving_to_fixed",
        "ground_truth",
        "mapping_metadata",
        "method_configuration",
        "plausibility_diagnostics",
    }
    return {key: value for key, value in record.items() if key not in excluded}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_rire_evidence(report: dict[str, Any]) -> dict[str, Any]:
    dataset = dict(report.get("dataset", {}))
    evaluation_policy = dict(report.get("evaluation_policy", {}))
    records = list(report.get("records", []))
    first_record = records[0] if records else {}
    return {
        "source_report": "reports/week05_day04_rire_physical_registration.json",
        "status": report.get("status"),
        "pair_id": dataset.get("pair_id"),
        "fixed_modality": dataset.get("fixed_modality"),
        "moving_modality": dataset.get("moving_modality"),
        "transform_model": first_record.get("transform_model"),
        "coordinate_system": "physical",
        "summary": report.get("summary"),
        "target_windows_validation": report.get("target_windows_validation"),
        "observations": report.get("observations", []),
        "interpretation": report.get("interpretation"),
        "ground_truth_status": dataset.get("ground_truth_status"),
        "evaluation_policy": evaluation_policy,
        "note": (
            "Real RIRE evidence remains descriptive and technically validated. It is not mixed into "
            "the synthetic TRE-based method comparison because verified landmarks or masks are not integrated."
        ),
    }


def main() -> None:
    args = _parse_args()
    config = load_config(_resolve(args.config))
    _validate_config(config)

    output_dir = _resolve(str(config["output"]["directory"]))
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output directory already exists: {output_dir}. Use --overwrite.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    prepared = _prepare_cases(config)
    records: list[dict[str, Any]] = []

    print("Week 5 Day 25: frozen integrated multimodal benchmark")
    print(f"Final synthetic test cases: {len(prepared)}")
    print(f"Planned registrations: {len(prepared) * 2}")
    print("MI and ECC configurations are frozen before this final test run.")
    print("Rigid and affine results are summarized separately.")

    for index, case in enumerate(prepared, start=1):
        print(f"\n{index:02d}/{len(prepared):02d} {case['case_id']} [{case['motion_model']}, {case['condition']}]")
        for method in ["mutual_information", "ecc"]:
            record = _run_registration(
                case=case,
                method=method,
                config=config,
                output_dir=output_dir,
            )
            records.append(record)
            tre_text = "n/a" if record["tre_pixels"] is None else f"{record['tre_pixels']:.3f}"
            status = "PASS" if record["within_tolerance"] else "CHECK"
            print(
                f"  {method:<20} success={str(record['method_success']):<5} "
                f"TRE={tre_text:>8} runtime={record['runtime_ms']:9.2f} ms {status}"
            )

    method_model_summaries = group_summaries(records, ("motion_model", "method"))
    condition_summaries = group_summaries(records, ("motion_model", "condition", "method"))
    paired_all = paired_method_outcomes(records)
    paired_by_model = {
        model: paired_method_outcomes([item for item in records if item["motion_model"] == model])
        for model in ["rigid", "affine"]
    }

    seed_report_path = _resolve(str(config["carried_evidence"]["day22_seed_variability_report"]))
    rire_report_path = _resolve(str(config["carried_evidence"]["day24_rire_report"]))
    stochastic_evidence = compact_seed_variability(_read_json(seed_report_path))
    rire_evidence = _compact_rire_evidence(_read_json(rire_report_path))

    failures = [
        {
            "case_id": item["case_id"],
            "motion_model": item["motion_model"],
            "condition": item["condition"],
            "method": item["method"],
            "method_success": item["method_success"],
            "within_tolerance": item["within_tolerance"],
            "tre_pixels": item["tre_pixels"],
            "failure_reason": item["failure_reason"],
            "evidence_paths": item["evidence_paths"],
        }
        for item in records
        if not bool(item["within_tolerance"])
    ]

    _write_csv(output_dir / "results.csv", records)
    (output_dir / "results.json").write_text(
        json.dumps(
            {
                "method_model_summaries": method_model_summaries,
                "condition_summaries": condition_summaries,
                "paired_outcomes": paired_all,
                "paired_outcomes_by_model": paired_by_model,
                "failure_cases": failures,
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "failure_gallery.json").write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _save_summary_plots(output_dir, method_model_summaries)

    report = {
        "week": 5,
        "day": 25,
        "title": "Integrated Week 5 multimodal benchmark and closure evidence",
        "status": "development_run_complete_target_validation_pending",
        "transform_convention": "Moving -> Fixed",
        "purpose": (
            "Run a frozen final synthetic multimodal benchmark for rigid and affine MI, compare "
            "against compatible historical ECC baselines on the same test cases, carry forward "
            "the Day 22 stochastic evidence, and keep real RIRE evidence separate."
        ),
        "final_test_case_count": len(prepared),
        "registration_count": len(records),
        "frozen_configurations": {
            "mutual_information": config["frozen_mutual_information"],
            "mi_preprocessing": config["frozen_mi_preprocessing"],
            "ecc": config["frozen_ecc"],
        },
        "validation_thresholds": config["validation"],
        "method_model_summaries": method_model_summaries,
        "condition_summaries": condition_summaries,
        "paired_outcomes": paired_all,
        "paired_outcomes_by_model": paired_by_model,
        "failure_case_count": len(failures),
        "failure_cases": failures,
        "stochastic_variability_evidence": stochastic_evidence,
        "real_rire_evidence": rire_evidence,
        "records": [_compact_record(item) for item in records],
        "limitations": [
            "Day 25 final synthetic test cases use known transforms and simulated modality mappings; they do not replace real multimodal validation.",
            "MI and ECC use their own previously frozen preprocessing and optimizer configurations. The image geometry and appearance condition are shared, but method-specific preprocessing is part of each frozen method pipeline.",
            "Rigid and affine results must be interpreted separately because the motion models solve different geometric problems.",
            "Optimizer execution success and within-tolerance geometric correctness remain separate fields.",
            "The frozen MI configuration uses full sampling, so Day 25 does not select or rerun a random seed for final-test accuracy. Day 22 stochastic evidence is carried forward separately.",
            "RIRE evidence is not included in the synthetic TRE ranking because verified landmarks or masks are not integrated.",
        ],
        "decision_rule": (
            "Report condition-specific evidence only. Do not convert the final results into a universal "
            "method ranking and do not retune frozen settings on Day 25 test cases."
        ),
        "next_step": (
            "Review the complete target Windows Day 25 results. If the full test suite and benchmark "
            "are reproducible, promote this report to target-validated status and close Week 5 before Week 6."
        ),
    }
    write_report_snapshot(_resolve(str(config["output"]["report_snapshot"])), report)

    print("\nDay 25 development run summary")
    for summary in method_model_summaries:
        print(
            f"{summary['motion_model']:<6} {summary['method']:<20} "
            f"success={summary['method_success_count']}/{summary['registration_count']} "
            f"within={summary['within_tolerance_count']}/{summary['registration_count']} "
            f"median_TRE={summary['median_tre_pixels']} "
            f"mean_runtime_ms={summary['mean_runtime_ms']}"
        )
    print(
        "Paired outcomes: "
        f"both_pass={paired_all['both_pass']}, "
        f"MI_only_pass={paired_all['mutual_information_only_pass']}, "
        f"ECC_only_pass={paired_all['ecc_only_pass']}, "
        f"both_check={paired_all['both_check']}"
    )
    print(f"Failure/CHECK records retained: {len(failures)}")
    print(f"Tracked report: {config['output']['report_snapshot']}")
    print("Do not close Week 5 until the target Windows Day 25 evidence is reviewed.")


if __name__ == "__main__":
    main()
