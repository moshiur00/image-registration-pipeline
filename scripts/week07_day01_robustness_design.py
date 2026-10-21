"""Week 7 Day 31: design preflight, task manifest, and small registration pilot.

Usage:
  python scripts/week07_day01_robustness_design.py --config configs/week07_day01_robustness_grid.yaml
  python scripts/week07_day01_robustness_design.py --config configs/week07_day01_robustness_grid.yaml --pilot

The full severity grid is never executed by this script. --pilot runs only
explicit pilot cases through the frozen UI RegistrationService.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for location in (str(ROOT), str(ROOT / "src")):
    if location not in sys.path:
        sys.path.insert(0, location)

from image_registration.benchmark_runner import (  # noqa: E402
    BenchmarkPairSpec, ResumableBenchmarkRunner, enumerate_benchmark_tasks,
)
from image_registration.config import load_config  # noqa: E402
from image_registration.evaluation_contracts import (  # noqa: E402
    ExecutionStatus, ReferenceEvidence, UnifiedEvaluationRecord,
)
from image_registration.io import load_image  # noqa: E402
from image_registration.multimodal import intensity_inversion  # noqa: E402
from image_registration.overlap import transformed_support_mask  # noqa: E402
from image_registration.preprocessing import resize_image  # noqa: E402
from image_registration.reporting import write_report_snapshot  # noqa: E402
from image_registration.synthetic import (  # noqa: E402
    sample_ground_truth_transform, generate_synthetic_pair,
)
from image_registration.unified_metrics import (  # noqa: E402
    transform_tre, overlap_aware_descriptive_metrics,
)
from image_registration.week7_robustness import (  # noqa: E402
    SCHEMA_VERSION, content_hash, make_manifest, method_specs, validate_design,
)
from ui.adapters import build_default_registration_service  # noqa: E402
from ui.core.contracts import (  # noqa: E402
    ImageSource, PreprocessingSpec, RegistrationRequest, RegistrationSpec,
    EvaluationContext as UIEvaluationContext,
)
from ui.core.enums import (  # noqa: E402
    SourceType, GroundTruthStatus, TransformModel, TransformUnits,
)


def _path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pilot_pairs(config: dict[str, Any], fixed: np.ndarray):
    specs = []
    prepared = {}
    for case in config["pilot"]:
        model = str(case["transform_model"])
        # Seed only samples from fixed single-point ranges: deterministic and explicit.
        ranges = {key: (float(value), float(value)) for key, value in case["geometry"].items()}
        gt = sample_ground_truth_transform(model, np.random.default_rng(42), fixed.shape, ranges)
        pair = generate_synthetic_pair(fixed, gt)
        moving = np.asarray(pair.moving)
        if case["condition"] == "intensity_inversion":
            moving = np.asarray(intensity_inversion(moving))
        elif case["condition"] != "none":
            raise ValueError("Day 31 pilot requires explicitly implemented conditions only.")
        pair_id = str(case["id"])
        specs.append(BenchmarkPairSpec(
            pair_id=pair_id,
            modality_class=str(case["modality_class"]),
            transform_model=model,
            degradation=str(case["condition"]),
            reference=ReferenceEvidence(exact_transform=True),
            metadata={
                "pilot": True,
                "geometry": dict(case["geometry"]),
                "condition": case["condition"],
                "source_sha256": config["_day31_source_hash"],
                "resize_shape": list(config["runner"]["resize_shape"]),
                "interpolation": "linear",
            },
        ))
        prepared[pair_id] = (fixed, moving, gt, pair.control_points_moving)
    return specs, prepared


def _pilot_executor(config: dict[str, Any], methods, prepared):
    service = build_default_registration_service()
    by_config = {method.config_id: method for method in methods}
    tolerance = float(config["runner"]["pilot_tre_threshold_px"])
    mi_bins = int(config["runner"]["pilot_mi_bins"])

    def execute(task):
        fixed, moving, gt, points = prepared[task.pair_id]
        parameters = dict(by_config[task.config_id].metadata["parameters"])
        start = perf_counter()
        request = RegistrationRequest(
            fixed=ImageSource(SourceType.ARRAY, "Day31 fixed", array=fixed),
            moving=ImageSource(SourceType.ARRAY, "Day31 moving", array=moving),
            preprocessing=PreprocessingSpec(grayscale=True, resize_policy="none"),
            registration=RegistrationSpec(
                method_id=task.method_id,
                transform_model=TransformModel(task.transform_model),
                initialization=parameters.get("initialization"),
                parameters=parameters,
                interpolation=str(parameters.get("interpolation", "bilinear")),
            ),
            # Firewall: the run has no access to GT or landmark data.
            evaluation=UIEvaluationContext(
                ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                units=TransformUnits.PIXELS,
            ),
            request_id=task.experiment_id,
        )
        run = service.run(request)
        elapsed_ms = (perf_counter() - start) * 1000.0
        estimated = None if run.transform is None else np.asarray(run.transform.matrix, dtype=np.float64)
        metrics: dict[str, float] = {"total_runtime_ms": elapsed_ms}
        overlap = None
        within = None
        if estimated is not None and run.registered_array is not None:
            support = transformed_support_mask(moving.shape, estimated, destination_shape=fixed.shape)
            if bool(np.any(support)):
                descriptive = overlap_aware_descriptive_metrics(
                    fixed, run.registered_array, support, mi_bins=mi_bins,
                )
                metrics.update(descriptive)
                overlap = float(descriptive["valid_overlap_fraction"])
                tre = transform_tre(gt.moving_to_fixed, estimated, points)["px"]
                metrics.update(tre.to_metrics())
                within = bool(tre.mean <= tolerance)
        status = ExecutionStatus(run.run_status.value)
        if status in {ExecutionStatus.FAILED, ExecutionStatus.VALIDATION_ERROR}:
            reason = run.failure_reason or "registration_failed"
        else:
            reason = None
        return UnifiedEvaluationRecord(
            pair_id=task.pair_id,
            method_id=task.method_id,
            method_family=task.method_family,
            transform_model=task.transform_model,
            modality_class=task.modality_class,
            dimensions=2,
            execution_status=status,
            reference=task.reference,
            seed=task.seed,
            valid_overlap_fraction=overlap,
            estimated_transform=estimated,
            transform_plausible=None if run.transform is None else run.transform.plausible,
            geometric_within_tolerance=within,
            metrics=metrics,
            timings_ms={"total": elapsed_ms},
            method_diagnostics={"pilot": True, "raw": run.diagnostics.values},
            warnings=list(run.warnings),
            failure_reason=reason,
        )

    return execute


def execute_pilot(config: dict[str, Any], methods):
    source = np.asarray(load_image(_path(config["sources"]["development"]), color_mode="grayscale").array)
    fixed = np.asarray(resize_image(source, tuple(config["runner"]["resize_shape"]), interpolation="area"))
    pair_specs, prepared = _pilot_pairs(config, fixed)
    tasks = enumerate_benchmark_tasks(pair_specs, methods, [None])
    runner = ResumableBenchmarkRunner(_path(config["runner"]["pilot_output"]))
    first = runner.run(tasks, _pilot_executor(config, methods, prepared), resume=True)
    second = runner.run(tasks, _pilot_executor(config, methods, prepared), resume=True)
    if second.executed_count != 0:
        raise AssertionError("Pilot resume check reran a completed attempt.")
    with runner.long_form_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(tasks) or len({row["experiment_id"] for row in rows}) != len(rows):
        raise AssertionError("Pilot long-form results have missing or duplicate records.")
    time_ms = [float(row["timing_total_ms"]) for row in rows if row["timing_total_ms"]]
    by_method: dict[str, list[float]] = {}
    for row in rows:
        if row["timing_total_ms"]:
            by_method.setdefault(row["method_id"], []).append(float(row["timing_total_ms"]))
    journal_size = runner.journal_path.stat().st_size
    missing_dependencies = [row["method_id"] for row in rows if "required for mutual-information" in row["failure_reason"]]
    # A pilot missing an entire method family cannot yield a credible full-grid cost estimate.
    estimate = (
        round((sum(time_ms) / len(time_ms)) * config["_design_attempt_count"] / 3_600_000, 3)
        if time_ms and not missing_dependencies else None
    )
    return {
        "state": "pilot_executed_local_dependency_caveats_apply",
        "runner_summary": first.to_dict(),
        "resume_probe": second.to_dict(),
        "method_attempts": len(rows),
        "method_family_count": len({task.method_family for task in tasks}),
        "timing_total_ms": round(sum(time_ms), 3),
        "missing_dependency_methods": sorted(set(missing_dependencies)),
        "observed_serial_method_times_ms": {
            method: round(float(np.median(times)), 3) for method, times in sorted(by_method.items())
        },
        "journal_bytes": journal_size,
        "projected_full_grid_journal_mb_unverified": round(
            journal_size / len(rows) * config["_design_attempt_count"] / (1024 * 1024), 3
        ),
        "estimated_full_grid_serial_runtime_hours": estimate,
        "estimate_warning": "Unreliable pilot extrapolation, excludes actual severity-dependent runtime and failures.",
        "pilot_output": str(config["runner"]["pilot_output"]),
        "limitations": ["Failed attempts caused by missing optional dependencies remain in the journal.",
                        "TRE is computed strictly after registration, not supplied to the registration service."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan Week 7 Day 31 robustness grid and run a tiny pilot.")
    parser.add_argument("--config", default="configs/week07_day01_robustness_grid.yaml")
    parser.add_argument("--pilot", action="store_true", help="Execute only the explicit small pilot matrix.")
    args = parser.parse_args()
    config_path = _path(args.config)
    config = load_config(config_path)
    validate_design(config)
    source_paths = {key: _path(str(value)) for key, value in config["sources"].items() if key in {"development", "final_holdout"}}
    for key, path in source_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{key} source not found: {path}")
    source_hashes = {key: content_hash(path) for key, path in source_paths.items()}
    if source_hashes["development"] == source_hashes["final_holdout"]:
        raise ValueError("Development and held-out source bytes must differ.")
    method_path = _path(str(config["frozen_method_catalog"]))
    catalog_hash = content_hash(method_path)
    methods = method_specs(load_config(method_path), catalog_hash)
    manifest, tasks = make_manifest(config, methods, source_hashes)
    manifest.update({
        "config_sha256": content_hash(config_path),
        "method_catalog_sha256": catalog_hash,
        "pilot_cases": [case["id"] for case in config["pilot"]],
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    })
    directory = _path(config["runner"]["design_output"])
    _json_write(directory / "manifest.json", manifest)
    # Full task manifest can be large; the Week 6 identity implementation remains authoritative.
    _json_write(directory / "tasks.json", [task.to_dict() for task in tasks])
    config["_day31_source_hash"] = source_hashes["development"]
    config["_design_attempt_count"] = len(tasks)
    pilot = execute_pilot(config, methods) if args.pilot else {"state": "not_executed", "note": "Pass --pilot to run the small cost estimation matrix."}
    report = {
        "week": 7, "day": 31,
        "title": "Robustness design preflight and pilot",
        "status": "local_design_ready_target_validation_pending",
        "frozen_ui_version": "v0.2",
        "grid": manifest,
        "pilot": pilot,
        "day32_readiness": "candidate_grid_requires_target_review_before_full_sweeps",
        "scientific_boundaries": [
            "Day31 does not execute the full severity grid.",
            "No final method recommendation, calibrated confidence, or outlier threshold is added.",
            "Ground truth is available only for post-run offline evaluation.",
            "Week 8 final_holdout source is not used for pilot or calibration.",
        ],
    }
    report_path = _path(config["runner"]["report_snapshot"])
    write_report_snapshot(report_path, report)
    print(f"Day31 robustness design: {manifest['pair_count']} pairs, {len(tasks)} compatible method tasks")
    print(f"Plan fingerprint: {manifest['plan_fingerprint']}")
    print(f"Pilot: {pilot['state']}")
    if args.pilot:
        print(f"Pilot attempts: {pilot['method_attempts']} | estimated full-grid hours: {pilot['estimated_full_grid_serial_runtime_hours']}")
    print(f"Manifest: {directory / 'manifest.json'}")
    print(f"Tracked report: {report_path}")


if __name__ == "__main__":
    main()
