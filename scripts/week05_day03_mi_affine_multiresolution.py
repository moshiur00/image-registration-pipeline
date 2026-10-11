from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.affine_ransac import affine_transform_diagnostics
from image_registration.config import load_config
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
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import affine_matrix, invert_transform, rotation_matrix
from image_registration.visualization import (
    save_comparison_figure,
    save_joint_histogram,
    save_metric_trace,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Week 5 Day 23 affine Mutual Information and multiresolution study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _mi_config(values: dict[str, Any]) -> MutualInformationConfig:
    return MutualInformationConfig(
        histogram_bins=int(values.get("histogram_bins", 32)),
        sampling_strategy=str(values.get("sampling_strategy", "none")),
        sampling_percentage=float(values.get("sampling_percentage", 0.20)),
        sampling_seed=int(values.get("sampling_seed", 42)),
        learning_rate=float(values.get("learning_rate", 2.0)),
        minimum_step=float(values.get("minimum_step", 0.001)),
        number_of_iterations=int(values.get("number_of_iterations", 200)),
        relaxation_factor=float(values.get("relaxation_factor", 0.5)),
        gradient_magnitude_tolerance=float(values.get("gradient_magnitude_tolerance", 1e-4)),
        shrink_factors=tuple(int(value) for value in values.get("shrink_factors", [4, 2, 1])),
        smoothing_sigmas=tuple(
            float(value) for value in values.get("smoothing_sigmas", [2.0, 1.0, 0.0])
        ),
        initialization=str(values.get("initialization", "identity")),
    )


def _validate_config(config: dict[str, Any]) -> None:
    required = {
        "experiment",
        "frozen_mutual_information",
        "frozen_preprocessing",
        "variants",
        "rigid_comparator",
        "validation",
        "plausibility",
        "sources",
        "cases",
        "output",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Missing Day 23 configuration sections: {', '.join(missing)}")

    frozen = dict(config["frozen_mutual_information"])
    _mi_config(frozen)
    if str(frozen.get("sampling_strategy")) != "none":
        raise ValueError("Day 23 must reuse the Day 22 frozen full-sampling strategy.")
    if int(frozen.get("histogram_bins", -1)) != 32:
        raise ValueError("Day 23 must reuse the Day 22 frozen 32-bin MI setting.")
    if str(frozen.get("initialization")) != "identity":
        raise ValueError("Day 23 must reuse the Day 22 frozen identity initialization.")

    preprocessing = dict(config["frozen_preprocessing"])
    preprocessing_mode = str(preprocessing.get("type", "")).strip().lower()
    if preprocessing_mode not in SUPPORTED_MI_PREPROCESSING:
        raise ValueError(f"Unsupported frozen preprocessing type: {preprocessing_mode}")
    if preprocessing_mode != "gaussian_smooth" or float(preprocessing.get("sigma", -1.0)) != 1.0:
        raise ValueError("Day 23 must reuse Day 22 Gaussian smoothing with sigma 1.0.")

    variants = dict(config["variants"])
    expected_variants = {"affine_single_resolution", "affine_multiresolution"}
    if set(variants) != expected_variants:
        raise ValueError("Day 23 requires affine_single_resolution and affine_multiresolution variants.")
    for variant_id, variant in variants.items():
        if str(variant.get("model")) != "affine":
            raise ValueError(f"Variant {variant_id} must use the affine model.")
        shrink = list(variant.get("shrink_factors", []))
        smooth = list(variant.get("smoothing_sigmas", []))
        if not shrink or len(shrink) != len(smooth):
            raise ValueError(f"Variant {variant_id} has an invalid multiresolution schedule.")

    cases = list(config["cases"])
    if not cases:
        raise ValueError("Day 23 cases must not be empty.")
    case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError("Every Day 23 case requires an id.")
        if case_id in case_ids:
            raise ValueError(f"Duplicate Day 23 case id: {case_id}")
        case_ids.add(case_id)
        source = str(case.get("source", "")).strip()
        if source not in config["sources"]:
            raise ValueError(f"Case {case_id} references unknown source '{source}'.")
        mapping = case.get("modality_mapping")
        if mapping is not None:
            if not isinstance(mapping, dict):
                raise ValueError(f"Case {case_id} modality_mapping must be a mapping.")
            mapping_name = str(mapping.get("type", "")).strip().lower()
            if mapping_name not in SUPPORTED_MULTIMODAL_MAPPING_TYPES:
                supported = ", ".join(sorted(SUPPORTED_MULTIMODAL_MAPPING_TYPES))
                raise ValueError(
                    f"Case {case_id} uses unsupported mapping '{mapping_name}'. "
                    f"Supported types: {supported}."
                )
        postprocess = case.get("postprocess")
        if postprocess is not None:
            if not isinstance(postprocess, dict):
                raise ValueError(f"Case {case_id} postprocess must be a mapping.")
            if str(postprocess.get("type", "")).strip().lower() != "restricted_fov":
                raise ValueError(f"Case {case_id} uses an unsupported Day 23 postprocess.")

    comparator_ids = set(str(item) for item in config["rigid_comparator"].get("case_ids", []))
    unknown = sorted(comparator_ids.difference(case_ids))
    if unknown:
        raise ValueError(f"Rigid comparator references unknown case ids: {', '.join(unknown)}")


def _ground_truth(fixed: np.ndarray, case: dict[str, Any]) -> GroundTruthTransform:
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


def _apply_postprocess(image: np.ndarray, spec: dict[str, Any] | None) -> tuple[np.ndarray, dict[str, Any] | None]:
    if spec is None:
        return image, None
    kind = str(spec.get("type", "")).strip().lower()
    if kind != "restricted_fov":
        raise ValueError(f"Unsupported Day 23 postprocess type: {kind}")
    mask = rectangular_field_of_view_mask(
        image.shape,
        width_fraction=float(spec.get("width_fraction", 0.72)),
        height_fraction=float(spec.get("height_fraction", 0.78)),
        center_x_fraction=float(spec.get("center_x_fraction", 0.50)),
        center_y_fraction=float(spec.get("center_y_fraction", 0.50)),
    )
    output = apply_field_of_view(
        image,
        mask,
        fill_value=float(spec.get("fill_value", 0.0)),
    )
    return np.asarray(output), {
        "type": "restricted_fov",
        "width_fraction": float(spec.get("width_fraction", 0.72)),
        "height_fraction": float(spec.get("height_fraction", 0.78)),
        "center_x_fraction": float(spec.get("center_x_fraction", 0.50)),
        "center_y_fraction": float(spec.get("center_y_fraction", 0.50)),
        "visible_fraction": float(np.mean(mask)),
    }


def _prepare_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {
        str(source_id): np.asarray(load_image(_resolve(str(path)), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }
    base_seed = int(config["experiment"].get("seed", 42))
    prepared: list[dict[str, Any]] = []
    for index, case in enumerate(config["cases"]):
        fixed = sources[str(case["source"])]
        ground_truth = _ground_truth(fixed, case)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving = np.asarray(pair.moving)
        mapping_name = "none"
        mapping_metadata: dict[str, Any] | None = None
        mapping_spec = case.get("modality_mapping")
        if isinstance(mapping_spec, dict):
            rng = np.random.default_rng(base_seed + (index + 1) * 1009)
            mapped = apply_multimodal_mapping(moving, mapping_spec, rng=rng)
            moving = np.asarray(mapped.image)
            mapping_metadata = mapped.metadata
            mapping_name = str(mapping_metadata["type"])

        moving, postprocess_metadata = _apply_postprocess(moving, case.get("postprocess"))
        preprocessing = dict(config["frozen_preprocessing"])
        fixed_preprocessed = apply_mi_preprocessing(fixed, preprocessing)
        moving_preprocessed = apply_mi_preprocessing(moving, preprocessing)

        prepared.append(
            {
                "case_id": str(case["id"]),
                "scope": str(case.get("scope", "affine_validation")),
                "source": str(case["source"]),
                "fixed_raw": fixed,
                "moving_raw": moving,
                "fixed": fixed_preprocessed.image,
                "moving": moving_preprocessed.image,
                "preprocessing_fixed_metadata": fixed_preprocessed.metadata,
                "preprocessing_moving_metadata": moving_preprocessed.metadata,
                "ground_truth": ground_truth,
                "control_points_moving": np.asarray(pair.control_points_moving, dtype=np.float64),
                "center": image_center(fixed.shape),
                "modality_mapping": mapping_name,
                "modality_mapping_metadata": mapping_metadata,
                "postprocess": postprocess_metadata,
            }
        )
    return prepared


def _plausibility_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    values = config["plausibility"]
    return {
        "min_abs_determinant": float(values.get("min_abs_determinant", 0.20)),
        "min_principal_scale": float(values.get("min_principal_scale", 0.55)),
        "max_principal_scale": float(values.get("max_principal_scale", 1.60)),
        "max_condition_number": float(values.get("max_condition_number", 2.75)),
        "max_shear_cosine": float(values.get("max_shear_cosine", 0.70)),
        "max_translation_fraction_of_diagonal": float(
            values.get("max_translation_fraction_of_diagonal", 1.50)
        ),
        "allow_reflection": bool(values.get("allow_reflection", False)),
    }


def _evaluate(
    *,
    ground_truth: GroundTruthTransform,
    estimated: np.ndarray,
    control_points_moving: np.ndarray,
    center: np.ndarray,
    image_shape: tuple[int, ...],
    validation: dict[str, Any],
    plausibility: dict[str, Any],
    method_success: bool,
) -> dict[str, Any]:
    if not method_success:
        return {
            "tre_pixels": None,
            "affine_linear_error": None,
            "translation_error_pixels": None,
            "plausible_transform": False,
            "plausibility_diagnostics": None,
            "within_tolerance": False,
        }

    tre = mean_tre_pixels(ground_truth.moving_to_fixed, estimated, control_points_moving)
    linear_error = affine_linear_error(ground_truth.moving_to_fixed, estimated)
    translation_error = centered_translation_error_pixels(
        ground_truth.moving_to_fixed,
        estimated,
        center,
    )
    diagnostics = affine_transform_diagnostics(
        estimated,
        image_shape=image_shape,
        **plausibility,
    )
    diagnostics_dict = {
        "determinant": diagnostics.determinant,
        "principal_scale_min": diagnostics.principal_scale_min,
        "principal_scale_max": diagnostics.principal_scale_max,
        "condition_number": diagnostics.condition_number,
        "shear_cosine": diagnostics.shear_cosine,
        "translation_norm_pixels": diagnostics.translation_norm_pixels,
        "translation_fraction_of_diagonal": diagnostics.translation_fraction_of_diagonal,
        "plausible": diagnostics.plausible,
        "rejection_reasons": list(diagnostics.rejection_reasons),
    }
    within = (
        diagnostics.plausible
        and tre <= float(validation["tre_threshold_pixels"])
        and linear_error <= float(validation["affine_linear_error_threshold"])
        and translation_error <= float(validation["translation_error_threshold_pixels"])
    )
    return {
        "tre_pixels": float(tre),
        "affine_linear_error": float(linear_error),
        "translation_error_pixels": float(translation_error),
        "plausible_transform": bool(diagnostics.plausible),
        "plausibility_diagnostics": diagnostics_dict,
        "within_tolerance": bool(within),
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    tre = [float(item["tre_pixels"]) for item in records if item.get("tre_pixels") is not None]
    linear = [
        float(item["affine_linear_error"])
        for item in records
        if item.get("affine_linear_error") is not None
    ]
    translation = [
        float(item["translation_error_pixels"])
        for item in records
        if item.get("translation_error_pixels") is not None
    ]
    runtimes = [float(item["runtime_ms"]) for item in records]
    return {
        "registration_count": len(records),
        "method_success_count": sum(bool(item["method_success"]) for item in records),
        "plausible_transform_count": sum(bool(item["plausible_transform"]) for item in records),
        "within_tolerance_count": sum(bool(item["within_tolerance"]) for item in records),
        "median_tre_pixels": None if not tre else float(np.median(tre)),
        "maximum_tre_pixels": None if not tre else float(np.max(tre)),
        "median_affine_linear_error": None if not linear else float(np.median(linear)),
        "median_translation_error_pixels": None if not translation else float(np.median(translation)),
        "mean_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
        "median_runtime_ms": None if not runtimes else float(np.median(runtimes)),
    }


def _run_variant(
    *,
    variant_id: str,
    model: str,
    mi_values: dict[str, Any],
    prepared_cases: list[dict[str, Any]],
    selected_case_ids: set[str] | None,
    config: dict[str, Any],
    output_dir: Path,
) -> list[dict[str, Any]]:
    registration = (
        MutualInformationAffineRegistration(_mi_config(mi_values))
        if model == "affine"
        else MutualInformationRigidRegistration(_mi_config(mi_values))
    )
    records: list[dict[str, Any]] = []
    joint_bins = int(config.get("visualization", {}).get("joint_histogram_bins", 64))
    selected_cases = [
        case
        for case in prepared_cases
        if selected_case_ids is None or case["case_id"] in selected_case_ids
    ]

    for index, case in enumerate(selected_cases, start=1):
        result = registration.register(case["fixed"], case["moving"])
        estimated = np.asarray(result.transform, dtype=np.float64)
        evaluation = _evaluate(
            ground_truth=case["ground_truth"],
            estimated=estimated,
            control_points_moving=case["control_points_moving"],
            center=case["center"],
            image_shape=case["fixed"].shape,
            validation=config["validation"],
            plausibility=_plausibility_kwargs(config),
            method_success=result.success,
        )
        convergence = result.convergence_info
        record = {
            "variant": variant_id,
            "registration_model": model,
            "case_id": case["case_id"],
            "scope": case["scope"],
            "source": case["source"],
            "modality_mapping": case["modality_mapping"],
            "modality_mapping_metadata": case["modality_mapping_metadata"],
            "postprocess": case["postprocess"],
            "ground_truth": case["ground_truth"].as_dict(),
            "estimated_moving_to_fixed": estimated.tolist(),
            "method_success": bool(result.success),
            "plausible_transform": bool(evaluation["plausible_transform"]),
            "within_tolerance": bool(evaluation["within_tolerance"]),
            "tre_pixels": evaluation["tre_pixels"],
            "affine_linear_error": evaluation["affine_linear_error"],
            "translation_error_pixels": evaluation["translation_error_pixels"],
            "plausibility_diagnostics": evaluation["plausibility_diagnostics"],
            "runtime_ms": float(result.runtime_seconds * 1000.0),
            "final_metric_value": convergence.get("final_metric_value"),
            "optimizer_iteration": convergence.get("optimizer_iteration"),
            "optimizer_stop_condition": convergence.get("optimizer_stop_condition"),
            "valid_metric_points": convergence.get("valid_metric_points"),
            "metric_trace": convergence.get("metric_trace", []),
            "mutual_information_configuration": deepcopy(mi_values),
            "preprocessing": deepcopy(config["frozen_preprocessing"]),
            "failure_reason": result.failure_reason,
        }
        records.append(record)

        case_dir = output_dir / variant_id / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        save_comparison_figure(
            case["fixed"],
            case["moving"],
            result.registered_image,
            case_dir / "comparison.png",
            title=f"{case['case_id']}: {variant_id}",
        )
        save_joint_histogram(
            case["fixed"],
            case["moving"],
            case_dir / "joint_histogram_before.png",
            bins=joint_bins,
            title=f"{case['case_id']}: before registration",
        )
        save_joint_histogram(
            case["fixed"],
            result.registered_image,
            case_dir / "joint_histogram_after.png",
            bins=joint_bins,
            title=f"{case['case_id']}: after registration",
        )
        save_metric_trace(
            list(convergence.get("metric_trace", [])),
            case_dir / "metric_trace.png",
            title=f"{case['case_id']}: Mattes MI convergence",
        )
        (case_dir / "result.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        tre_text = "n/a" if record["tre_pixels"] is None else f"{record['tre_pixels']:.3f}"
        affine_text = (
            "n/a" if record["affine_linear_error"] is None else f"{record['affine_linear_error']:.4f}"
        )
        status = "PASS" if record["within_tolerance"] else "CHECK"
        print(
            f"  {index:02d}/{len(selected_cases):02d} {case['case_id']:<33} "
            f"TRE={tre_text:>7} affine_err={affine_text:>7} "
            f"runtime={record['runtime_ms']:8.2f} ms {status}"
        )
    return records


def _capture_range_comparison(
    single_records: list[dict[str, Any]],
    multi_records: list[dict[str, Any]],
) -> dict[str, Any]:
    single = {item["case_id"]: item for item in single_records}
    multi = {item["case_id"]: item for item in multi_records}
    shared = sorted(set(single).intersection(multi))
    paired: list[dict[str, Any]] = []
    for case_id in shared:
        single_item = single[case_id]
        multi_item = multi[case_id]
        paired.append(
            {
                "case_id": case_id,
                "single_within_tolerance": bool(single_item["within_tolerance"]),
                "multiresolution_within_tolerance": bool(multi_item["within_tolerance"]),
                "single_tre_pixels": single_item["tre_pixels"],
                "multiresolution_tre_pixels": multi_item["tre_pixels"],
            }
        )
    return {
        "shared_case_count": len(shared),
        "both_pass": sum(
            item["single_within_tolerance"] and item["multiresolution_within_tolerance"]
            for item in paired
        ),
        "multiresolution_only_pass": sum(
            (not item["single_within_tolerance"]) and item["multiresolution_within_tolerance"]
            for item in paired
        ),
        "single_only_pass": sum(
            item["single_within_tolerance"] and (not item["multiresolution_within_tolerance"])
            for item in paired
        ),
        "both_check": sum(
            (not item["single_within_tolerance"]) and (not item["multiresolution_within_tolerance"])
            for item in paired
        ),
        "paired_cases": paired,
    }


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "metric_trace",
        "estimated_moving_to_fixed",
        "ground_truth",
        "modality_mapping_metadata",
        "mutual_information_configuration",
        "preprocessing",
    }
    return {key: value for key, value in record.items() if key not in excluded}


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "variant",
        "registration_model",
        "case_id",
        "scope",
        "modality_mapping",
        "method_success",
        "plausible_transform",
        "within_tolerance",
        "tre_pixels",
        "affine_linear_error",
        "translation_error_pixels",
        "runtime_ms",
        "final_metric_value",
        "optimizer_iteration",
        "valid_metric_points",
        "failure_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in records:
            writer.writerow({field: item.get(field) for field in fields})


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

    prepared_cases = _prepare_cases(config)
    frozen = deepcopy(dict(config["frozen_mutual_information"]))
    all_records: list[dict[str, Any]] = []
    variant_records: dict[str, list[dict[str, Any]]] = {}

    print("Week 5 Day 23: affine Mutual Information and multiresolution capture range")
    print(f"Cases: {len(prepared_cases)}")
    print("Day 22 MI metric, optimizer, initialization, sampling, and preprocessing choices are frozen.")

    for variant_id, variant in config["variants"].items():
        values = deepcopy(frozen)
        values["shrink_factors"] = list(variant["shrink_factors"])
        values["smoothing_sigmas"] = list(variant["smoothing_sigmas"])
        print(f"\n{variant_id}")
        records = _run_variant(
            variant_id=str(variant_id),
            model="affine",
            mi_values=values,
            prepared_cases=prepared_cases,
            selected_case_ids=None,
            config=config,
            output_dir=output_dir,
        )
        variant_records[str(variant_id)] = records
        all_records.extend(records)
        summary = _summary(records)
        print(
            f"  summary method_success={summary['method_success_count']}/{summary['registration_count']} "
            f"plausible={summary['plausible_transform_count']}/{summary['registration_count']} "
            f"within={summary['within_tolerance_count']}/{summary['registration_count']} "
            f"median_TRE={summary['median_tre_pixels']}"
        )

    comparator_records: list[dict[str, Any]] = []
    comparator = dict(config["rigid_comparator"])
    if bool(comparator.get("enabled", False)):
        values = deepcopy(frozen)
        values["shrink_factors"] = list(comparator["shrink_factors"])
        values["smoothing_sigmas"] = list(comparator["smoothing_sigmas"])
        selected = set(str(item) for item in comparator.get("case_ids", []))
        print("\nrigid_multiresolution_model_mismatch_comparator")
        comparator_records = _run_variant(
            variant_id="rigid_multiresolution_model_mismatch_comparator",
            model="rigid",
            mi_values=values,
            prepared_cases=prepared_cases,
            selected_case_ids=selected,
            config=config,
            output_dir=output_dir,
        )
        all_records.extend(comparator_records)
        comparator_summary = _summary(comparator_records)
        print(
            f"  summary method_success={comparator_summary['method_success_count']}/"
            f"{comparator_summary['registration_count']} "
            f"within={comparator_summary['within_tolerance_count']}/"
            f"{comparator_summary['registration_count']} "
            f"median_TRE={comparator_summary['median_tre_pixels']}"
        )

    single_records = variant_records["affine_single_resolution"]
    multi_records = variant_records["affine_multiresolution"]
    capture = _capture_range_comparison(single_records, multi_records)
    variant_summaries = {key: _summary(value) for key, value in variant_records.items()}
    comparator_summary = _summary(comparator_records) if comparator_records else None

    _write_csv(output_dir / "results.csv", all_records)
    (output_dir / "results.json").write_text(
        json.dumps(
            {
                "variant_summaries": variant_summaries,
                "capture_range_comparison": capture,
                "rigid_comparator_summary": comparator_summary,
                "records": all_records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 5,
        "day": 23,
        "title": "Affine Mutual Information and multiresolution capture-range validation",
        "status": "development_run_complete_target_validation_pending",
        "transform_convention": "Moving -> Fixed",
        "purpose": (
            "Extend the validated rigid MI path to affine transforms, compare single-resolution and "
            "multiresolution capture range on controlled affine ground truth, and preserve a limited "
            "rigid comparator as transform-model mismatch evidence."
        ),
        "frozen_day22_configuration": {
            "mutual_information": config["frozen_mutual_information"],
            "preprocessing": config["frozen_preprocessing"],
        },
        "variants": config["variants"],
        "validation_thresholds": config["validation"],
        "plausibility_thresholds": config["plausibility"],
        "case_count": len(prepared_cases),
        "variant_summaries": variant_summaries,
        "capture_range_comparison": capture,
        "rigid_comparator_summary": comparator_summary,
        "records": [_compact_record(record) for record in all_records],
        "limitations": [
            "Day 23 uses controlled 2D synthetic affine ground truth and simulated multimodal appearance mappings.",
            "The Day 22 MI settings remain frozen; Day 23 does not retune them on these cases.",
            "The rigid comparator is restricted to selected true-affine cases and is evidence of model mismatch, not a universal method ranking.",
            "Optimizer completion, transform plausibility, and geometric correctness are separate result fields.",
            "Real CT/MR physical-space evidence is reserved for Day 24.",
        ],
        "next_step": (
            "Review and validate these results on the target Windows environment before starting "
            "Day 24 real RIRE CT/MR-T1 physical-space registration."
        ),
    }
    write_report_snapshot(_resolve(str(config["output"]["report_snapshot"])), report)

    print("\nDay 23 development run summary")
    for variant_id, summary in variant_summaries.items():
        print(
            f"{variant_id}: method_success={summary['method_success_count']}/"
            f"{summary['registration_count']}, within={summary['within_tolerance_count']}/"
            f"{summary['registration_count']}, median_TRE={summary['median_tre_pixels']}"
        )
    print(
        "Capture-range paired outcomes: "
        f"both_pass={capture['both_pass']}, "
        f"multiresolution_only_pass={capture['multiresolution_only_pass']}, "
        f"single_only_pass={capture['single_only_pass']}, both_check={capture['both_check']}"
    )
    if comparator_summary is not None:
        print(
            "Rigid model-mismatch comparator: "
            f"within={comparator_summary['within_tolerance_count']}/"
            f"{comparator_summary['registration_count']}"
        )
    print(f"Tracked report: {config['output']['report_snapshot']}")
    print("Do not start Day 24 until the target Windows Day 23 evidence is reviewed.")


if __name__ == "__main__":
    main()
