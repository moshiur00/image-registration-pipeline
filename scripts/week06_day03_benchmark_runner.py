from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.benchmark_runner import (
    BenchmarkMethodSpec,
    BenchmarkPairSpec,
    BenchmarkTask,
    ResumableBenchmarkRunner,
    enumerate_benchmark_tasks,
)
from image_registration.config import load_config
from image_registration.degradations import gaussian_blur
from image_registration.ecc import ECCRegistration
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)
from image_registration.io import load_image
from image_registration.multimodal import intensity_inversion
from image_registration.overlap import transformed_support_mask
from image_registration.phase_correlation import PhaseCorrelationRegistration
from image_registration.preprocessing import resize_image
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair
from image_registration.transforms import invert_transform, translation_matrix
from image_registration.unified_metrics import (
    model_aware_parameter_errors,
    overlap_aware_descriptive_metrics,
    transform_tre,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Week 6 Day 28 deterministic resumable benchmark-runner study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _prepare_pairs(config: dict[str, Any]) -> tuple[list[BenchmarkPairSpec], dict[str, dict[str, Any]]]:
    source_path = _resolve(str(config["source"]["image"]))
    source = np.asarray(load_image(source_path, color_mode="grayscale").array)
    resize_shape = tuple(int(value) for value in config["runner"]["resize_shape"])
    fixed_base = np.asarray(resize_image(source, resize_shape, interpolation="area"))

    specs: list[BenchmarkPairSpec] = []
    prepared: dict[str, dict[str, Any]] = {}
    for pair_config in config["pairs"]:
        pair_id = str(pair_config["id"])
        tx = float(pair_config["tx"])
        ty = float(pair_config["ty"])
        moving_to_fixed = translation_matrix(tx, ty)
        ground_truth = GroundTruthTransform(
            transform_type="translation",
            parameters={"tx": tx, "ty": ty},
            moving_to_fixed=moving_to_fixed,
            fixed_to_moving=invert_transform(moving_to_fixed),
        )
        generated = generate_synthetic_pair(fixed_base, ground_truth, interpolation="linear")
        moving = np.asarray(generated.moving)
        degradation = str(pair_config.get("degradation", "none"))
        degradation_parameters = dict(pair_config.get("degradation_parameters", {}))
        if degradation == "gaussian_blur":
            moving = np.asarray(
                gaussian_blur(moving, sigma=float(degradation_parameters["sigma"]))
            )
        elif degradation == "intensity_inversion":
            moving = np.asarray(intensity_inversion(moving))
        elif degradation != "none":
            raise ValueError(f"Unsupported Day 28 degradation: {degradation}")

        modality_class = str(pair_config["modality_class"])
        specs.append(
            BenchmarkPairSpec(
                pair_id=pair_id,
                modality_class=modality_class,
                transform_model="translation",
                degradation=degradation,
                dimensions=2,
                reference=ReferenceEvidence(exact_transform=True),
                metadata={
                    "source": str(config["source"]["image"]),
                    "tx": tx,
                    "ty": ty,
                    "degradation_parameters": degradation_parameters,
                },
            )
        )
        prepared[pair_id] = {
            "fixed": fixed_base,
            "moving": moving,
            "ground_truth": ground_truth,
            "control_points_moving": np.asarray(generated.control_points_moving, dtype=np.float64),
        }
    return specs, prepared


def _prepare_methods(
    config: dict[str, Any],
) -> tuple[list[BenchmarkMethodSpec], dict[str, dict[str, Any]]]:
    specs: list[BenchmarkMethodSpec] = []
    parameters: dict[str, dict[str, Any]] = {}
    for method_config in config["methods"]:
        method_id = str(method_config["method_id"])
        config_id = str(method_config["config_id"])
        method_parameters = dict(method_config["parameters"])
        specs.append(
            BenchmarkMethodSpec(
                method_id=method_id,
                config_id=config_id,
                method_family=str(method_config["method_family"]),
                supported_transform_models=tuple(
                    str(value) for value in method_config["supported_transform_models"]
                ),
                metadata={"parameters": method_parameters},
            )
        )
        parameters[config_id] = method_parameters
    return specs, parameters


def _build_method(task: BenchmarkTask, parameters: dict[str, dict[str, Any]]):
    spec = dict(parameters[task.config_id])
    if task.method_id == "phase_translation":
        return PhaseCorrelationRegistration(**spec)
    if task.method_id == "ecc_translation":
        return ECCRegistration(**spec)
    raise ValueError(f"Unsupported Day 28 method: {task.method_id}")


def _make_executor(
    config: dict[str, Any],
    prepared_pairs: dict[str, dict[str, Any]],
    parameters: dict[str, dict[str, Any]],
):
    mi_bins = int(config["runner"]["evaluation_mi_bins"])
    parameter_threshold = float(config["runner"]["translation_error_threshold_px"])
    tre_threshold = float(config["runner"]["tre_threshold_px"])
    translation_fraction = float(config["runner"]["max_translation_fraction_of_diagonal"])

    def execute(task: BenchmarkTask) -> UnifiedEvaluationRecord:
        pair = prepared_pairs[task.pair_id]
        fixed = np.asarray(pair["fixed"])
        moving = np.asarray(pair["moving"])
        method = _build_method(task, parameters)
        result = method.register(fixed, moving)

        evaluation_start = perf_counter()
        estimated = np.asarray(result.transform, dtype=np.float64)
        support = transformed_support_mask(
            moving.shape,
            estimated,
            destination_shape=(int(fixed.shape[0]), int(fixed.shape[1])),
        )
        descriptive = overlap_aware_descriptive_metrics(
            fixed,
            result.registered_image,
            support,
            mi_bins=mi_bins,
        )
        parameter_metrics = model_aware_parameter_errors(
            pair["ground_truth"].moving_to_fixed,
            estimated,
            transform_model="translation",
        )
        tre_summary = transform_tre(
            pair["ground_truth"].moving_to_fixed,
            estimated,
            pair["control_points_moving"],
        )["px"]
        geometric_within = (
            parameter_metrics["translation_error_px"] <= parameter_threshold
            and tre_summary.mean <= tre_threshold
        )

        translation = estimated[:2, 2]
        image_diagonal = float(np.hypot(fixed.shape[1], fixed.shape[0]))
        transform_plausible = bool(
            np.all(np.isfinite(estimated))
            and float(np.linalg.norm(translation))
            <= translation_fraction * image_diagonal
        )

        evaluation_ms = (perf_counter() - evaluation_start) * 1000.0
        convergence = dict(result.convergence_info)
        registration_ms = float(convergence.get("estimation_seconds", 0.0)) * 1000.0
        warping_ms = float(convergence.get("warp_seconds", 0.0)) * 1000.0
        if registration_ms <= 0.0:
            registration_ms = max(0.0, result.runtime_seconds * 1000.0 - warping_ms)
        total_ms = result.runtime_seconds * 1000.0 + evaluation_ms

        metrics: dict[str, float] = {}
        metrics.update(parameter_metrics)
        metrics.update(tre_summary.to_metrics())
        metrics.update(descriptive)
        metrics.update(
            {
                "preprocessing_runtime_ms": 0.0,
                "registration_runtime_ms": registration_ms,
                "warping_runtime_ms": warping_ms,
                "evaluation_runtime_ms": evaluation_ms,
                "total_runtime_ms": total_ms,
            }
        )

        warnings: list[str] = []
        if result.success and not geometric_within:
            warnings.append("geometric_threshold_not_met")
        if not transform_plausible:
            warnings.append("transform_outside_day28_plausibility_bound")

        status = ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED
        failure_reason = result.failure_reason if not result.success else None
        return UnifiedEvaluationRecord(
            pair_id=task.pair_id,
            method_id=task.method_id,
            method_family=task.method_family,
            transform_model=task.transform_model,
            modality_class=task.modality_class,
            dimensions=task.dimensions,
            execution_status=status,
            reference=task.reference,
            valid_overlap_fraction=float(descriptive["valid_overlap_fraction"]),
            seed=task.seed,
            estimated_transform=estimated,
            transform_plausible=transform_plausible,
            geometric_within_tolerance=geometric_within,
            metrics=metrics,
            timings_ms={
                "preprocessing": 0.0,
                "registration": registration_ms,
                "warping": warping_ms,
                "evaluation": evaluation_ms,
                "total": total_ms,
            },
            method_diagnostics=convergence,
            warnings=warnings,
            failure_reason=failure_reason,
        )

    return execute


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summarize_rows(rows: list[dict[str, str]], key: str) -> list[dict[str, Any]]:
    values = sorted({row[key] for row in rows})
    summaries: list[dict[str, Any]] = []
    for value in values:
        group = [row for row in rows if row[key] == value]
        tre = [float(row["tre_mean_px"]) for row in group if row["tre_mean_px"]]
        summaries.append(
            {
                key: value,
                "attempt_count": len(group),
                "completed_count": sum(row["execution_status"] == "completed" for row in group),
                "failed_count": sum(row["execution_status"] == "failed" for row in group),
                "geometric_within_tolerance_count": sum(
                    row["geometric_within_tolerance"] == "True" for row in group
                ),
                "median_tre_px": None if not tre else float(np.median(tre)),
            }
        )
    return summaries


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    output = dict(config["output"])
    output_dir = _resolve(str(output["directory"]))
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    elif output_dir.exists() and not args.overwrite:
        # Existing output is allowed because Day 28 explicitly tests resume.
        pass

    pair_specs, prepared_pairs = _prepare_pairs(config)
    method_specs, method_parameters = _prepare_methods(config)
    seeds = [int(value) for value in config["runner"]["seeds"]]
    tasks = enumerate_benchmark_tasks(pair_specs, method_specs, seeds)

    runner = ResumableBenchmarkRunner(output_dir)
    executor = _make_executor(config, prepared_pairs, method_parameters)
    first = runner.run(tasks, executor, resume=True)
    resumed = runner.run(tasks, executor, resume=True)

    rows = _read_csv(runner.long_form_path)
    experiment_ids = [row["experiment_id"] for row in rows]
    if len(experiment_ids) != len(set(experiment_ids)):
        raise AssertionError("Day 28 long-form table contains duplicate experiment IDs.")
    if resumed.executed_count != 0 or resumed.skipped_count != len(tasks):
        raise AssertionError("Day 28 resume probe must skip every persisted task.")

    report = {
        "week": 6,
        "day": 28,
        "title": "Deterministic resumable benchmark runner",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Add deterministic experiment identities, durable resume/skip-completed behavior, "
            "explicit terminal failure records, and a standardized long-form result table around "
            "the frozen Day 26 evaluation contract and validated Day 27 metrics."
        ),
        "runner_schema_version": "week06_benchmark_runner_v1",
        "plan_fingerprint": first.plan_fingerprint,
        "planned_attempts": len(tasks),
        "pair_count": len(pair_specs),
        "method_configuration_count": len(method_specs),
        "seed_count": len(seeds),
        "first_run": first.to_dict(),
        "resume_probe": resumed.to_dict(),
        "unique_experiment_ids": len(set(experiment_ids)),
        "method_summaries": _summarize_rows(rows, "method_id"),
        "modality_summaries": _summarize_rows(rows, "modality_class"),
        "degradation_summaries": _summarize_rows(rows, "degradation"),
        "artifacts": {
            "plan": str(runner.plan_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "journal": str(runner.journal_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "long_form_csv": str(runner.long_form_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "runner_summary": str(runner.summary_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        },
        "interpretation": [
            "The same frozen experiment matrix receives stable identifiers derived from scientific task identity.",
            "A second invocation performs zero registrations and skips every existing terminal record.",
            "Monomodal and simulated-multimodal labels remain explicit in the long-form result table.",
            "Execution status and geometric correctness remain separate fields.",
            "Algorithm and executor failures are retained as terminal evidence rather than removed from later summaries.",
        ],
        "limitations": [
            "Day 28 validates orchestration with translation Phase Correlation and ECC only; the complete multi-method matrix is deferred.",
            "The two seeds are runner-level reproducibility probes for deterministic methods, not independent stochastic accuracy trials.",
            "Final dataset-specific success thresholds and robust aggregate statistics remain later Week 6 work.",
            "Automatic method recommendation is not implemented on Day 28.",
        ],
        "next_step": (
            "Review target Windows Day 28 evidence before Day 29 automatic multi-method execution work."
        ),
    }
    report_path = _resolve(str(output["report_snapshot"]))
    write_report_snapshot(report_path, report)

    print("Week 6 Day 28: deterministic resumable benchmark runner")
    print(f"Planned attempts: {len(tasks)} ({len(pair_specs)} pairs x {len(method_specs)} methods x {len(seeds)} seeds)")
    print(f"Plan fingerprint: {first.plan_fingerprint[:16]}...")
    print(
        "First run: "
        f"executed={first.executed_count}, skipped={first.skipped_count}, "
        f"completed={first.completed_count}, failed={first.failed_count}, "
        f"validation_error={first.validation_error_count}"
    )
    print(
        "Resume probe: "
        f"executed={resumed.executed_count}, skipped={resumed.skipped_count}, "
        f"records={resumed.terminal_count}"
    )
    print(f"Unique long-form records: {len(set(experiment_ids))}/{len(rows)}")
    for summary in _summarize_rows(rows, "method_id"):
        print(
            f"{summary['method_id']}: attempts={summary['attempt_count']} "
            f"completed={summary['completed_count']} failed={summary['failed_count']} "
            f"within={summary['geometric_within_tolerance_count']} "
            f"median_TRE={summary['median_tre_px']}"
        )
    print(f"Tracked report: {report_path.relative_to(PROJECT_ROOT).as_posix()}")
    print("Do not start Day 29 until the target Windows Day 28 evidence is reviewed.")


if __name__ == "__main__":
    main()
