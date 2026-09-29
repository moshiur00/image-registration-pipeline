from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config
from image_registration.io import load_image
from image_registration.multimodal import apply_multimodal_mapping
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
from image_registration.visualization import save_comparison_figure


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Week 5 Day 1 rigid Mutual Information experiment.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _mi_config(config: dict[str, Any]) -> MutualInformationConfig:
    values = config["mutual_information"]
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
        smoothing_sigmas=tuple(float(value) for value in values.get("smoothing_sigmas", [2.0, 1.0, 0.0])),
        initialization=str(values.get("initialization", "geometry")),
    )


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


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "scope",
        "modality_mapping",
        "method_success",
        "within_tolerance",
        "tre_pixels",
        "rotation_error_degrees",
        "translation_error_pixels",
        "runtime_ms",
        "final_metric_value",
        "optimizer_iteration",
        "failure_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in records:
            writer.writerow({field: item.get(field) for field in fields})


def main() -> None:
    args = _parse_args()
    config_path = _resolve(args.config)
    config = load_config(config_path)
    output_dir = _resolve(str(config["output"]["directory"]))
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output directory already exists: {output_dir}. Use --overwrite.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(int(config["experiment"].get("seed", 42)))
    registration = MutualInformationRigidRegistration(_mi_config(config))
    sources = {
        source_id: np.asarray(load_image(_resolve(path), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }

    records: list[dict[str, Any]] = []
    cases = list(config["cases"])
    print("Week 5 Day 1: rigid Mattes Mutual Information")
    print(f"Cases: {len(cases)}")

    for index, case in enumerate(cases, start=1):
        case_id = str(case["id"])
        fixed = sources[str(case["source"])]
        ground_truth = _ground_truth(fixed, case)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving = np.asarray(pair.moving)
        mapping_spec = case.get("modality_mapping")
        mapping_name = "none"
        mapping_metadata: dict[str, Any] | None = None
        if isinstance(mapping_spec, dict):
            mapped = apply_multimodal_mapping(moving, mapping_spec, rng=rng)
            moving = np.asarray(mapped.image)
            mapping_metadata = mapped.metadata
            mapping_name = str(mapping_metadata["type"])

        result = registration.register(fixed, moving)
        evaluation = _evaluate(
            ground_truth,
            np.asarray(result.transform, dtype=np.float64),
            np.asarray(pair.control_points_moving, dtype=np.float64),
            image_center(fixed.shape),
            config["validation"],
            result.success,
        )
        convergence = result.convergence_info
        record = {
            "case_id": case_id,
            "scope": str(case.get("scope", "simulated_multimodal")),
            "source": str(case["source"]),
            "modality_mapping": mapping_name,
            "modality_mapping_metadata": mapping_metadata,
            "ground_truth": ground_truth.as_dict(),
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

        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        save_comparison_figure(
            fixed,
            moving,
            result.registered_image,
            case_dir / "comparison.png",
            title=f"{case_id}: Mutual Information rigid registration",
        )
        (case_dir / "result.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        tre_text = "n/a" if evaluation["tre_pixels"] is None else f"{evaluation['tre_pixels']:.3f}"
        status = "PASS" if evaluation["within_tolerance"] else "CHECK"
        print(
            f"{index:02d}/{len(cases):02d} {case_id:<27} "
            f"mapping={mapping_name:<19} TRE={tre_text:>7} "
            f"runtime={record['runtime_ms']:8.2f} ms {status}"
        )

    method_successes = sum(item["method_success"] for item in records)
    within = sum(item["within_tolerance"] for item in records)
    numeric_tre = [float(item["tre_pixels"]) for item in records if item["tre_pixels"] is not None]
    runtimes = [float(item["runtime_ms"]) for item in records]
    summary = {
        "case_count": len(records),
        "method_success_count": int(method_successes),
        "within_tolerance_count": int(within),
        "median_tre_pixels": None if not numeric_tre else float(np.median(numeric_tre)),
        "maximum_tre_pixels": None if not numeric_tre else float(np.max(numeric_tre)),
        "mean_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
    }

    _write_csv(output_dir / "results.csv", records)
    (output_dir / "results.json").write_text(
        json.dumps({"summary": summary, "records": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 5,
        "day": 21,
        "title": "Rigid Mattes Mutual Information registration foundation",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Validate the initial 2D rigid Mutual Information path on a monomodal reference and "
            "controlled simulated multimodal pairs before affine and real-data experiments."
        ),
        "transform_convention": "Moving -> Fixed",
        "simpleitk_direction_note": (
            "SimpleITK optimizes a Fixed -> Moving physical transform for resampling. "
            "The module inverts it before returning the project Moving -> Fixed transform."
        ),
        "configuration": config["mutual_information"],
        "validation_thresholds": config["validation"],
        "development_run": summary,
        "records": records,
        "limitations": [
            "This Day 21 experiment uses 2D unit-spacing synthetic geometry; real RIRE physical-space validation is not part of this run.",
            "The thresholds are development criteria and are not final benchmark thresholds.",
            "Optimizer completion and geometric correctness are reported separately.",
            "Simulated multimodal mappings do not replace validation on real multimodal data.",
        ],
        "next_step": (
            "Validate on the target Windows environment, then use the observed convergence and failure evidence "
            "to proceed to rigid/affine Mutual Information initialization and parameter studies."
        ),
    }
    write_report_snapshot(_resolve(str(config["output"]["report_snapshot"])), report)

    print("\nWeek 5 Day 1 development run summary")
    print(f"Method success: {method_successes}/{len(records)}")
    print(f"Within tolerance: {within}/{len(records)}")
    if numeric_tre:
        print(f"Median TRE: {np.median(numeric_tre):.3f} px")
    print(f"Tracked report: {config['output']['report_snapshot']}")


if __name__ == "__main__":
    main()
