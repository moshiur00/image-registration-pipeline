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

from image_registration.config import load_config
from image_registration.io import load_image
from image_registration.mi_study import (
    SUPPORTED_MI_PREPROCESSING,
    apply_mi_preprocessing,
    candidate_rank_key,
    select_best_candidate,
    summarize_mi_records,
)
from image_registration.multimodal import (
    SUPPORTED_MULTIMODAL_MAPPING_TYPES,
    apply_multimodal_mapping,
)
from image_registration.mutual_information import (
    MutualInformationConfig,
    MutualInformationRigidRegistration,
)
from image_registration.registration_metrics import (
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import invert_transform, rigid_matrix
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
        description="Run Week 5 Day 22 controlled rigid Mutual Information study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _mi_config(values: dict[str, Any]) -> MutualInformationConfig:
    return MutualInformationConfig(
        histogram_bins=int(values.get("histogram_bins", 50)),
        sampling_strategy=str(values.get("sampling_strategy", "random")),
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
        initialization=str(values.get("initialization", "geometry")),
    )


def _validate_config(config: dict[str, Any]) -> None:
    required = {
        "experiment",
        "baseline_mutual_information",
        "baseline_preprocessing",
        "validation",
        "sources",
        "validation_cases",
        "studies",
        "selection",
        "output",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Missing Day 22 configuration sections: {', '.join(missing)}")

    _mi_config(dict(config["baseline_mutual_information"]))
    baseline_preprocessing = dict(config["baseline_preprocessing"])
    if str(baseline_preprocessing.get("type", "none")) not in SUPPORTED_MI_PREPROCESSING:
        raise ValueError("baseline_preprocessing.type is not supported.")

    cases = list(config["validation_cases"])
    if not cases:
        raise ValueError("validation_cases must contain at least one case.")
    case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError("Every Day 22 validation case requires an id.")
        if case_id in case_ids:
            raise ValueError(f"Duplicate Day 22 validation case id: {case_id}")
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

    studies = config["studies"]
    for required_study in (
        "initialization",
        "histogram_bins",
        "sampling_strategy",
        "sampling_percentage",
        "random_seed_variability",
        "preprocessing",
    ):
        if required_study not in studies:
            raise ValueError(f"Missing Day 22 study: {required_study}")

    for candidate in studies["preprocessing"]:
        spec = candidate.get("spec", {})
        mode = str(spec.get("type", "none")).strip().lower()
        if mode not in SUPPORTED_MI_PREPROCESSING:
            raise ValueError(f"Unsupported preprocessing candidate: {mode}")


def _ground_truth(fixed: np.ndarray, case: dict[str, Any]) -> GroundTruthTransform:
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


def _evaluate(
    ground_truth: GroundTruthTransform,
    estimated: np.ndarray,
    control_points_moving: np.ndarray,
    center: np.ndarray,
    validation: dict[str, Any],
    method_success: bool,
) -> dict[str, Any]:
    if not method_success:
        return {
            "tre_pixels": None,
            "rotation_error_degrees": None,
            "translation_error_pixels": None,
            "within_tolerance": False,
        }
    tre = mean_tre_pixels(ground_truth.moving_to_fixed, estimated, control_points_moving)
    rotation = rotation_error_degrees(ground_truth.moving_to_fixed, estimated)
    translation = centered_translation_error_pixels(ground_truth.moving_to_fixed, estimated, center)
    within = (
        tre <= float(validation["tre_threshold_pixels"])
        and rotation <= float(validation["rotation_error_threshold_degrees"])
        and translation <= float(validation["translation_error_threshold_pixels"])
    )
    return {
        "tre_pixels": float(tre),
        "rotation_error_degrees": float(rotation),
        "translation_error_pixels": float(translation),
        "within_tolerance": bool(within),
    }


def _prepare_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {
        source_id: np.asarray(load_image(_resolve(path), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }
    base_seed = int(config["experiment"].get("seed", 42))
    prepared: list[dict[str, Any]] = []

    for index, case in enumerate(config["validation_cases"]):
        fixed = sources[str(case["source"])]
        ground_truth = _ground_truth(fixed, case)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving = np.asarray(pair.moving)
        mapping_name = "none"
        mapping_metadata: dict[str, Any] | None = None
        mapping_spec = case.get("modality_mapping")
        if isinstance(mapping_spec, dict):
            case_rng = np.random.default_rng(base_seed + index * 1009)
            mapped = apply_multimodal_mapping(moving, mapping_spec, rng=case_rng)
            moving = np.asarray(mapped.image)
            mapping_metadata = mapped.metadata
            mapping_name = str(mapping_metadata["type"])

        prepared.append(
            {
                "case_id": str(case["id"]),
                "scope": str(case.get("scope", "simulated_multimodal_validation")),
                "source": str(case["source"]),
                "fixed": fixed,
                "moving": moving,
                "ground_truth": ground_truth,
                "control_points_moving": np.asarray(pair.control_points_moving, dtype=np.float64),
                "center": image_center(fixed.shape),
                "modality_mapping": mapping_name,
                "modality_mapping_metadata": mapping_metadata,
            }
        )
    return prepared


def _run_candidate(
    *,
    stage: str,
    candidate_id: str,
    mi_values: dict[str, Any],
    preprocessing_spec: dict[str, Any],
    prepared_cases: list[dict[str, Any]],
    validation: dict[str, Any],
    visual_root: Path | None = None,
    joint_histogram_bins: int = 64,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registration = MutualInformationRigidRegistration(_mi_config(mi_values))
    records: list[dict[str, Any]] = []

    for case in prepared_cases:
        fixed_preprocessed = apply_mi_preprocessing(case["fixed"], preprocessing_spec)
        moving_preprocessed = apply_mi_preprocessing(case["moving"], preprocessing_spec)
        result = registration.register(fixed_preprocessed.image, moving_preprocessed.image)
        evaluation = _evaluate(
            case["ground_truth"],
            np.asarray(result.transform, dtype=np.float64),
            case["control_points_moving"],
            case["center"],
            validation,
            result.success,
        )
        convergence = result.convergence_info
        record = {
            "stage": stage,
            "candidate_id": candidate_id,
            "case_id": case["case_id"],
            "scope": case["scope"],
            "source": case["source"],
            "modality_mapping": case["modality_mapping"],
            "modality_mapping_metadata": case["modality_mapping_metadata"],
            "mutual_information_configuration": deepcopy(mi_values),
            "preprocessing": deepcopy(preprocessing_spec),
            "preprocessing_fixed_metadata": fixed_preprocessed.metadata,
            "preprocessing_moving_metadata": moving_preprocessed.metadata,
            "ground_truth": case["ground_truth"].as_dict(),
            "estimated_moving_to_fixed": np.asarray(result.transform).tolist(),
            "method_success": bool(result.success),
            "within_tolerance": bool(evaluation["within_tolerance"]),
            "tre_pixels": evaluation["tre_pixels"],
            "rotation_error_degrees": evaluation["rotation_error_degrees"],
            "translation_error_pixels": evaluation["translation_error_pixels"],
            "runtime_ms": float(result.runtime_seconds * 1000.0),
            "final_metric_value": convergence.get("final_metric_value"),
            "optimizer_iteration": convergence.get("optimizer_iteration"),
            "optimizer_stop_condition": convergence.get("optimizer_stop_condition"),
            "valid_metric_points": convergence.get("valid_metric_points"),
            "metric_trace": convergence.get("metric_trace", []),
            "failure_reason": result.failure_reason,
        }
        records.append(record)

        if visual_root is not None:
            case_dir = visual_root / case["case_id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            save_comparison_figure(
                fixed_preprocessed.image,
                moving_preprocessed.image,
                result.registered_image,
                case_dir / "comparison.png",
                title=f"{case['case_id']}: frozen rigid MI configuration",
            )
            save_joint_histogram(
                fixed_preprocessed.image,
                moving_preprocessed.image,
                case_dir / "joint_histogram_before.png",
                bins=joint_histogram_bins,
                title=f"{case['case_id']}: before registration",
            )
            save_joint_histogram(
                fixed_preprocessed.image,
                result.registered_image,
                case_dir / "joint_histogram_after.png",
                bins=joint_histogram_bins,
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

    return records, summarize_mi_records(records)


def _candidate_summary(
    stage: str,
    candidate_id: str,
    candidate_value: Any,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "candidate_id": candidate_id,
        "candidate_value": candidate_value,
        "summary": summary,
        "case_results": [
            {
                "case_id": item["case_id"],
                "method_success": item["method_success"],
                "within_tolerance": item["within_tolerance"],
                "tre_pixels": item["tre_pixels"],
                "rotation_error_degrees": item["rotation_error_degrees"],
                "translation_error_pixels": item["translation_error_pixels"],
                "runtime_ms": item["runtime_ms"],
                "optimizer_iteration": item["optimizer_iteration"],
                "optimizer_stop_condition": item["optimizer_stop_condition"],
                "valid_metric_points": item["valid_metric_points"],
                "failure_reason": item["failure_reason"],
            }
            for item in records
        ],
    }


def _run_parameter_candidates(
    *,
    stage: str,
    candidates: list[dict[str, Any]],
    current_mi: dict[str, Any],
    current_preprocessing: dict[str, Any],
    parameter_name: str,
    prepared_cases: list[dict[str, Any]],
    validation: dict[str, Any],
    all_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        candidate_value = candidate["value"]
        values = deepcopy(current_mi)
        values[parameter_name] = candidate_value
        records, summary = _run_candidate(
            stage=stage,
            candidate_id=candidate_id,
            mi_values=values,
            preprocessing_spec=current_preprocessing,
            prepared_cases=prepared_cases,
            validation=validation,
        )
        all_records.extend(records)
        summaries.append(
            _candidate_summary(stage, candidate_id, candidate_value, records, summary)
        )
        print(
            f"  {candidate_id:<24} within={summary['within_tolerance_count']}/"
            f"{summary['case_count']} median_TRE={summary['median_tre_pixels']} "
            f"mean_runtime_ms={summary['mean_runtime_ms']}"
        )
    selected = dict(select_best_candidate(summaries))
    return summaries, selected


def _run_preprocessing_candidates(
    *,
    candidates: list[dict[str, Any]],
    current_mi: dict[str, Any],
    prepared_cases: list[dict[str, Any]],
    validation: dict[str, Any],
    all_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        spec = deepcopy(dict(candidate["spec"]))
        records, summary = _run_candidate(
            stage="preprocessing",
            candidate_id=candidate_id,
            mi_values=current_mi,
            preprocessing_spec=spec,
            prepared_cases=prepared_cases,
            validation=validation,
        )
        all_records.extend(records)
        summaries.append(_candidate_summary("preprocessing", candidate_id, spec, records, summary))
        print(
            f"  {candidate_id:<24} within={summary['within_tolerance_count']}/"
            f"{summary['case_count']} median_TRE={summary['median_tre_pixels']} "
            f"mean_runtime_ms={summary['mean_runtime_ms']}"
        )
    selected = dict(select_best_candidate(summaries))
    return summaries, selected


def _compact_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excluded = {
        "metric_trace",
        "preprocessing_fixed_metadata",
        "preprocessing_moving_metadata",
        "estimated_moving_to_fixed",
        "ground_truth",
        "modality_mapping_metadata",
        "mutual_information_configuration",
        "preprocessing",
    }
    return [{key: value for key, value in item.items() if key not in excluded} for item in records]


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "stage",
        "candidate_id",
        "case_id",
        "scope",
        "source",
        "modality_mapping",
        "method_success",
        "within_tolerance",
        "tre_pixels",
        "rotation_error_degrees",
        "translation_error_pixels",
        "runtime_ms",
        "final_metric_value",
        "optimizer_iteration",
        "valid_metric_points",
        "optimizer_stop_condition",
        "failure_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field) for field in fields})


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
    validation = dict(config["validation"])
    baseline_mi = deepcopy(dict(config["baseline_mutual_information"]))
    baseline_preprocessing = deepcopy(dict(config["baseline_preprocessing"]))
    current_mi = deepcopy(baseline_mi)
    current_preprocessing = deepcopy(baseline_preprocessing)
    studies = config["studies"]
    all_records: list[dict[str, Any]] = []
    stage_reports: dict[str, Any] = {}
    selected_values: dict[str, Any] = {}

    print("Week 5 Day 22: rigid MI controlled validation study")
    print(f"Validation cases: {len(prepared_cases)}")
    print("Selection is sequential one-factor-at-a-time, not a grid search.")

    print("\nBaseline")
    baseline_records, baseline_summary = _run_candidate(
        stage="baseline",
        candidate_id="day21_baseline",
        mi_values=baseline_mi,
        preprocessing_spec=baseline_preprocessing,
        prepared_cases=prepared_cases,
        validation=validation,
    )
    all_records.extend(baseline_records)
    stage_reports["baseline"] = {
        "configuration": deepcopy(baseline_mi),
        "preprocessing": deepcopy(baseline_preprocessing),
        "summary": baseline_summary,
        "case_results": _compact_records(baseline_records),
    }
    print(
        f"  within={baseline_summary['within_tolerance_count']}/{baseline_summary['case_count']} "
        f"median_TRE={baseline_summary['median_tre_pixels']} "
        f"mean_runtime_ms={baseline_summary['mean_runtime_ms']}"
    )

    print("\nInitialization study")
    summaries, selected = _run_parameter_candidates(
        stage="initialization",
        candidates=list(studies["initialization"]),
        current_mi=current_mi,
        current_preprocessing=current_preprocessing,
        parameter_name="initialization",
        prepared_cases=prepared_cases,
        validation=validation,
        all_records=all_records,
    )
    stage_reports["initialization"] = {"candidates": summaries, "selected": selected}
    current_mi["initialization"] = selected["candidate_value"]
    selected_values["initialization"] = selected["candidate_value"]

    print("\nHistogram-bin study")
    summaries, selected = _run_parameter_candidates(
        stage="histogram_bins",
        candidates=list(studies["histogram_bins"]),
        current_mi=current_mi,
        current_preprocessing=current_preprocessing,
        parameter_name="histogram_bins",
        prepared_cases=prepared_cases,
        validation=validation,
        all_records=all_records,
    )
    stage_reports["histogram_bins"] = {"candidates": summaries, "selected": selected}
    current_mi["histogram_bins"] = int(selected["candidate_value"])
    selected_values["histogram_bins"] = int(selected["candidate_value"])

    print("\nSampling-strategy study")
    summaries, selected = _run_parameter_candidates(
        stage="sampling_strategy",
        candidates=list(studies["sampling_strategy"]),
        current_mi=current_mi,
        current_preprocessing=current_preprocessing,
        parameter_name="sampling_strategy",
        prepared_cases=prepared_cases,
        validation=validation,
        all_records=all_records,
    )
    stage_reports["sampling_strategy"] = {"candidates": summaries, "selected": selected}
    current_mi["sampling_strategy"] = str(selected["candidate_value"])
    selected_values["sampling_strategy"] = str(selected["candidate_value"])

    print("\nSampling-percentage study")
    percentage_strategy = str(current_mi["sampling_strategy"])
    percentage_applies_to_frozen = percentage_strategy in {"regular", "random"}
    if not percentage_applies_to_frozen:
        percentage_strategy = "random"
        print("  Frozen strategy is full sampling; percentage sweep is diagnostic with random sampling.")
    percentage_candidates = [
        {"id": f"{percentage_strategy}_{int(round(float(value) * 100)):02d}pct", "value": float(value)}
        for value in studies["sampling_percentage"]["values"]
    ]
    percentage_base = deepcopy(current_mi)
    percentage_base["sampling_strategy"] = percentage_strategy
    summaries, selected = _run_parameter_candidates(
        stage="sampling_percentage",
        candidates=percentage_candidates,
        current_mi=percentage_base,
        current_preprocessing=current_preprocessing,
        parameter_name="sampling_percentage",
        prepared_cases=prepared_cases,
        validation=validation,
        all_records=all_records,
    )
    stage_reports["sampling_percentage"] = {
        "sampling_strategy": percentage_strategy,
        "applies_to_frozen_configuration": percentage_applies_to_frozen,
        "candidates": summaries,
        "selected": selected,
    }
    if percentage_applies_to_frozen:
        current_mi["sampling_percentage"] = float(selected["candidate_value"])
        selected_values["sampling_percentage"] = float(selected["candidate_value"])
    else:
        selected_values["sampling_percentage"] = "not_applicable_full_sampling"

    print("\nPreprocessing study")
    summaries, selected = _run_preprocessing_candidates(
        candidates=list(studies["preprocessing"]),
        current_mi=current_mi,
        prepared_cases=prepared_cases,
        validation=validation,
        all_records=all_records,
    )
    stage_reports["preprocessing"] = {"candidates": summaries, "selected": selected}
    current_preprocessing = deepcopy(dict(selected["candidate_value"]))
    selected_values["preprocessing"] = deepcopy(current_preprocessing)

    fixed_seed = int(config["selection"].get("fixed_sampling_seed", 42))
    current_mi["sampling_seed"] = fixed_seed

    print("\nRandom-sampling seed variability")
    seed_strategy_values = deepcopy(current_mi)
    seed_strategy_values["sampling_strategy"] = "random"
    if current_mi["sampling_strategy"] == "none":
        seed_strategy_values["sampling_percentage"] = float(
            baseline_mi.get("sampling_percentage", 0.20)
        )
    seed_candidates: list[dict[str, Any]] = []
    seed_records_all: list[dict[str, Any]] = []
    for seed in studies["random_seed_variability"]["seeds"]:
        seed_values = deepcopy(seed_strategy_values)
        seed_values["sampling_seed"] = int(seed)
        candidate_id = f"seed_{int(seed)}"
        records, summary = _run_candidate(
            stage="random_seed_variability",
            candidate_id=candidate_id,
            mi_values=seed_values,
            preprocessing_spec=current_preprocessing,
            prepared_cases=prepared_cases,
            validation=validation,
        )
        all_records.extend(records)
        seed_records_all.extend(records)
        seed_candidates.append(_candidate_summary("random_seed_variability", candidate_id, int(seed), records, summary))
        print(
            f"  {candidate_id:<24} within={summary['within_tolerance_count']}/"
            f"{summary['case_count']} median_TRE={summary['median_tre_pixels']}"
        )
    seed_case_variability: list[dict[str, Any]] = []
    for case in prepared_cases:
        case_records = [item for item in seed_records_all if item["case_id"] == case["case_id"]]
        tre_values = [
            float(item["tre_pixels"])
            for item in case_records
            if item["tre_pixels"] is not None and np.isfinite(float(item["tre_pixels"]))
        ]
        seed_case_variability.append(
            {
                "case_id": case["case_id"],
                "attempt_count": len(case_records),
                "within_tolerance_count": sum(bool(item["within_tolerance"]) for item in case_records),
                "tre_median_pixels": None if not tre_values else float(np.median(tre_values)),
                "tre_std_pixels": None if not tre_values else float(np.std(tre_values)),
                "tre_min_pixels": None if not tre_values else float(np.min(tre_values)),
                "tre_max_pixels": None if not tre_values else float(np.max(tre_values)),
            }
        )
    stage_reports["random_seed_variability"] = {
        "selection_rule": "diagnostic_only_seed_is_not_selected_by_accuracy",
        "sampling_strategy": "random",
        "sampling_percentage": seed_strategy_values["sampling_percentage"],
        "candidates": seed_candidates,
        "per_case_variability": seed_case_variability,
    }

    print("\nSequential composite candidate")
    sequential_records, sequential_summary = _run_candidate(
        stage="sequential_composite",
        candidate_id="selected_ofat_values",
        mi_values=current_mi,
        preprocessing_spec=current_preprocessing,
        prepared_cases=prepared_cases,
        validation=validation,
    )
    all_records.extend(sequential_records)
    stage_reports["sequential_composite"] = {
        "configuration": deepcopy(current_mi),
        "preprocessing": deepcopy(current_preprocessing),
        "summary": sequential_summary,
        "case_results": _compact_records(sequential_records),
    }
    print(
        f"  within={sequential_summary['within_tolerance_count']}/{sequential_summary['case_count']} "
        f"median_TRE={sequential_summary['median_tre_pixels']}"
    )

    baseline_choice = {
        "candidate_id": "day21_baseline",
        "summary": baseline_summary,
        "configuration": deepcopy(baseline_mi),
        "preprocessing": deepcopy(baseline_preprocessing),
    }
    sequential_choice = {
        "candidate_id": "selected_ofat_values",
        "summary": sequential_summary,
        "configuration": deepcopy(current_mi),
        "preprocessing": deepcopy(current_preprocessing),
    }
    final_choice = min(
        [baseline_choice, sequential_choice],
        key=lambda item: candidate_rank_key(item["summary"]),
    )
    frozen_mi = deepcopy(final_choice["configuration"])
    frozen_preprocessing = deepcopy(final_choice["preprocessing"])
    frozen_mi["sampling_seed"] = fixed_seed

    print("\nFrozen-candidate confirmation")
    visual_root = output_dir / "frozen_confirmation"
    confirmation_records, confirmation_summary = _run_candidate(
        stage="frozen_confirmation",
        candidate_id=str(final_choice["candidate_id"]),
        mi_values=frozen_mi,
        preprocessing_spec=frozen_preprocessing,
        prepared_cases=prepared_cases,
        validation=validation,
        visual_root=visual_root,
        joint_histogram_bins=int(config.get("visualization", {}).get("joint_histogram_bins", 64)),
    )
    all_records.extend(confirmation_records)
    print(
        f"  choice={final_choice['candidate_id']} "
        f"within={confirmation_summary['within_tolerance_count']}/{confirmation_summary['case_count']} "
        f"median_TRE={confirmation_summary['median_tre_pixels']}"
    )

    frozen_payload = {
        "selection_source": str(final_choice["candidate_id"]),
        "mutual_information": frozen_mi,
        "preprocessing": frozen_preprocessing,
        "validation_subset": [case["case_id"] for case in prepared_cases],
        "validation_thresholds": validation,
        "note": (
            "This configuration is frozen from the Day 22 validation subset for later Week 5 work. "
            "It is not selected from the final Day 25 benchmark."
        ),
    }
    (output_dir / "frozen_rigid_mi_candidate.json").write_text(
        json.dumps(frozen_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output_dir / "all_runs.csv", all_records)
    (output_dir / "all_runs.json").write_text(
        json.dumps(all_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 5,
        "day": 22,
        "title": "Rigid Mutual Information initialization, sampling, and parameter study",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Select a rigid Mattes Mutual Information configuration on a limited multimodal validation subset "
            "using sequential one-factor-at-a-time studies before affine and final Week 5 evaluation."
        ),
        "transform_convention": "Moving -> Fixed",
        "experimental_design": {
            "type": "sequential_one_factor_at_a_time",
            "not_grid_search": True,
            "validation_case_ids": [case["case_id"] for case in prepared_cases],
            "selection_priority": list(config["selection"]["priority"]),
            "seed_rule": str(config["selection"]["note"]),
        },
        "baseline": stage_reports["baseline"],
        "studies": {
            key: value
            for key, value in stage_reports.items()
            if key not in {"baseline", "sequential_composite"}
        },
        "selected_values_before_composite_confirmation": selected_values,
        "sequential_composite": stage_reports["sequential_composite"],
        "freeze_decision": {
            "candidate": str(final_choice["candidate_id"]),
            "baseline_rank_key": list(candidate_rank_key(baseline_summary)),
            "sequential_rank_key": list(candidate_rank_key(sequential_summary)),
            "frozen_configuration": frozen_payload,
        },
        "confirmation": {
            "summary": confirmation_summary,
            "case_results": _compact_records(confirmation_records),
            "visual_evidence_directory": "outputs/week05_day02_mi_rigid_study/frozen_confirmation",
        },
        "limitations": [
            "Configuration selection uses five controlled simulated multimodal validation cases and is not final test evidence.",
            "The histogram-remap and edge-emphasized cases are retained even when they fail geometric thresholds.",
            "Optimizer success and geometric correctness are separate result fields.",
            "Random seed repetitions measure stochastic variability; the seed is not tuned for best accuracy.",
            "Joint histograms are descriptive visual diagnostics and do not prove geometric correctness.",
            "Real RIRE CT/MR-T1 physical-space validation is reserved for Day 24.",
        ],
        "evidence": {
            "full_local_records": "outputs/week05_day02_mi_rigid_study/all_runs.json",
            "full_local_table": "outputs/week05_day02_mi_rigid_study/all_runs.csv",
            "frozen_candidate": "outputs/week05_day02_mi_rigid_study/frozen_rigid_mi_candidate.json",
            "confirmation_visuals": "outputs/week05_day02_mi_rigid_study/frozen_confirmation",
        },
        "next_step": (
            "Validate the full test suite and Day 22 study on the target Windows environment. "
            "Review the frozen-candidate evidence before starting Day 23 affine Mutual Information."
        ),
    }
    write_report_snapshot(_resolve(str(config["output"]["report_snapshot"])), report)

    print("\nDay 22 development run summary")
    print(f"Baseline within tolerance: {baseline_summary['within_tolerance_count']}/{baseline_summary['case_count']}")
    print(
        f"Sequential candidate within tolerance: "
        f"{sequential_summary['within_tolerance_count']}/{sequential_summary['case_count']}"
    )
    print(f"Frozen choice: {final_choice['candidate_id']}")
    print(
        f"Frozen confirmation: {confirmation_summary['within_tolerance_count']}/"
        f"{confirmation_summary['case_count']} within tolerance"
    )
    print(f"Tracked report: {config['output']['report_snapshot']}")
    print("Do not start Day 23 until the target Windows Day 22 evidence is reviewed.")


if __name__ == "__main__":
    main()
