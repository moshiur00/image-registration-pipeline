from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for value in (str(PROJECT_ROOT), str(SRC_ROOT)):
    if value not in sys.path:
        sys.path.insert(0, value)

from image_registration.automatic_agreement import (
    build_preliminary_consensus,
    robust_numeric_summary,
    summarize_methods,
    summarize_stage_runtimes,
)
from image_registration.automatic_registration import (
    AutoMethodSpec,
    AutoPairProfile,
    AutomaticMultiMethodService,
)
from image_registration.config import load_config
from image_registration.degradations import gaussian_blur, gaussian_noise
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)
from image_registration.io import load_image
from image_registration.multimodal import intensity_inversion
from image_registration.overlap import transformed_support_mask
from image_registration.preprocessing import resize_image
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import (
    GroundTruthTransform,
    generate_synthetic_pair,
    image_center,
)
from image_registration.transforms import affine_matrix, invert_transform
from image_registration.unified_metrics import (
    model_aware_parameter_errors,
    overlap_aware_descriptive_metrics,
    transform_tre,
)
from ui.adapters import build_default_registration_service
from ui.core.contracts import (
    EvaluationContext as UIEvaluationContext,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationSpec,
)
from ui.core.enums import (
    GroundTruthStatus,
    SourceType,
    TransformModel as UITransformModel,
    TransformUnits,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Week 6 Day 30 transform agreement and closure study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _prepare_methods(
    config: dict[str, Any],
) -> tuple[list[AutoMethodSpec], dict[str, dict[str, Any]]]:
    methods: list[AutoMethodSpec] = []
    parameters: dict[str, dict[str, Any]] = {}
    for item in config["methods"]:
        method_id = str(item["method_id"])
        methods.append(
            AutoMethodSpec(
                method_id=method_id,
                display_name=str(item["display_name"]),
                method_family=str(item["method_family"]),
                transform_model=str(item["transform_model"]),
                dimensions=frozenset(int(value) for value in item["dimensions"]),
                supported_modality_classes=frozenset(
                    str(value) for value in item["supported_modality_classes"]
                ),
                requires_same_shape=bool(item.get("requires_same_shape", False)),
                optional=bool(item.get("optional", False)),
                metadata={"parameters": dict(item.get("parameters", {}))},
            )
        )
        parameters[method_id] = dict(item.get("parameters", {}))
    return methods, parameters


def _base_ground_truth(
    fixed: np.ndarray,
    config: dict[str, Any],
) -> GroundTruthTransform:
    gt = dict(config["base_ground_truth"])
    linear = np.asarray(gt["linear"], dtype=np.float64)
    center = image_center(fixed.shape) if bool(gt.get("centered", True)) else None
    moving_to_fixed = affine_matrix(
        linear,
        tx=float(gt["tx"]),
        ty=float(gt["ty"]),
        center=center,
    )
    return GroundTruthTransform(
        transform_type="affine",
        parameters={
            "linear": linear.tolist(),
            "tx": float(gt["tx"]),
            "ty": float(gt["ty"]),
            "center": None if center is None else np.asarray(center).tolist(),
        },
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=invert_transform(moving_to_fixed),
    )


def _apply_condition(
    moving: np.ndarray,
    condition: dict[str, Any],
) -> np.ndarray:
    condition_type = str(condition.get("type", "none")).strip().lower()
    if condition_type == "none":
        return np.asarray(moving).copy()
    if condition_type == "gaussian_blur":
        return gaussian_blur(moving, sigma=float(condition["sigma"]))
    if condition_type == "gaussian_noise":
        rng = np.random.default_rng(int(condition.get("seed", 42)))
        return gaussian_noise(
            moving,
            sigma_fraction=float(condition["sigma_fraction"]),
            rng=rng,
        )
    if condition_type == "intensity_inversion":
        return intensity_inversion(moving)
    raise ValueError(f"Unsupported Day 30 condition: {condition_type}")


def _prepare_case(
    fixed: np.ndarray,
    ground_truth: GroundTruthTransform,
    case_config: dict[str, Any],
) -> tuple[AutoPairProfile, dict[str, Any]]:
    generated = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    moving = _apply_condition(np.asarray(generated.moving), dict(case_config["condition"]))

    pair = AutoPairProfile(
        pair_id=str(case_config["id"]),
        dimensions=2,
        modality_class=str(case_config["modality_class"]),
        candidate_transform_models=tuple(
            str(value) for value in case_config["candidate_transform_models"]
        ),
        same_shape=bool(np.asarray(generated.fixed).shape == moving.shape),
        # Operation deliberately behaves like an unknown real-world pair.
        reference=ReferenceEvidence(),
        metadata={
            "condition": dict(case_config["condition"]),
            "operation_ground_truth": "unavailable",
            "development_ground_truth_not_exposed_to_auto_service": True,
            "image_shape": list(np.asarray(generated.fixed).shape),
        },
    )
    return pair, {
        "fixed": np.asarray(generated.fixed),
        "moving": moving,
        "ground_truth": ground_truth,
        "control_points_moving": np.asarray(
            generated.control_points_moving,
            dtype=np.float64,
        ),
    }


def _ui_transform_model(value: str) -> UITransformModel:
    return UITransformModel(str(value))


def _make_executor(
    config: dict[str, Any],
    prepared: dict[str, Any],
    parameters: dict[str, dict[str, Any]],
):
    registration_service = build_default_registration_service()
    fixed = np.asarray(prepared["fixed"])
    moving = np.asarray(prepared["moving"])
    mi_bins = int(config["runner"]["evaluation_mi_bins"])

    def execute(task) -> UnifiedEvaluationRecord:
        method_parameters = dict(parameters[task.method.method_id])
        initialization = method_parameters.get("initialization")
        request = RegistrationRequest(
            fixed=ImageSource(
                source_type=SourceType.ARRAY,
                display_name=f"{task.pair.pair_id} fixed",
                modality="synthetic",
                array=fixed,
            ),
            moving=ImageSource(
                source_type=SourceType.ARRAY,
                display_name=f"{task.pair.pair_id} moving",
                modality="synthetic",
                array=moving,
            ),
            preprocessing=PreprocessingSpec(
                grayscale=True,
                clipping_percentiles=None,
                normalization=None,
                gaussian_sigma=None,
                resize_policy="none",
            ),
            registration=RegistrationSpec(
                method_id=task.method.method_id,
                transform_model=_ui_transform_model(task.method.transform_model),
                initialization=None if initialization is None else str(initialization),
                parameters=method_parameters,
                interpolation=str(method_parameters.get("interpolation", "bilinear")),
            ),
            evaluation=UIEvaluationContext(
                ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                units=TransformUnits.PIXELS,
            ),
            request_id=task.candidate_id,
        )

        run = registration_service.run(request)
        status = ExecutionStatus(run.run_status.value)
        metrics: dict[str, float] = {}
        timings: dict[str, float] = {
            "total": max(0.0, float(run.runtime_seconds) * 1000.0),
        }
        estimated = (
            None
            if run.transform is None
            else np.asarray(run.transform.matrix, dtype=np.float64)
        )
        overlap_fraction = None

        if (
            run.registered_array is not None
            and estimated is not None
            and status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}
        ):
            support = transformed_support_mask(
                moving.shape,
                estimated,
                destination_shape=(int(fixed.shape[0]), int(fixed.shape[1])),
            )
            descriptive = overlap_aware_descriptive_metrics(
                fixed,
                np.asarray(run.registered_array),
                support,
                mi_bins=mi_bins,
            )
            overlap_fraction = float(descriptive["valid_overlap_fraction"])
            metrics.update(descriptive)

        metrics["total_runtime_ms"] = timings["total"]

        diagnostics = dict(run.diagnostics.values)
        diagnostics["ui_service_request_id"] = run.request_id
        diagnostics["ui_service_provenance"] = {
            "method_id": run.provenance.method_id,
            "transform_direction": run.provenance.transform_direction,
            "ground_truth_status": run.provenance.ground_truth_status.value,
        }

        return UnifiedEvaluationRecord(
            pair_id=task.pair.pair_id,
            method_id=task.method.method_id,
            method_family=task.method.method_family,
            transform_model=task.method.transform_model,
            modality_class=task.pair.modality_class,
            dimensions=task.pair.dimensions,
            execution_status=status,
            reference=task.pair.reference,
            valid_overlap_fraction=overlap_fraction,
            estimated_transform=estimated,
            transform_plausible=None if run.transform is None else run.transform.plausible,
            geometric_within_tolerance=None,
            metrics=metrics,
            timings_ms=timings,
            method_diagnostics=diagnostics,
            warnings=list(run.warnings),
            failure_reason=run.failure_reason,
        )

    return execute


def _development_only_validation(
    auto_result,
    prepared: dict[str, Any],
    *,
    tolerance_px: float,
) -> list[dict[str, Any]]:
    """Evaluate hidden synthetic GT after automatic execution."""
    ground_truth = prepared["ground_truth"]
    control_points = prepared["control_points_moving"]
    rows: list[dict[str, Any]] = []
    for candidate in auto_result.candidates:
        payload: dict[str, Any] = {
            "pair_id": auto_result.pair.pair_id,
            "modality_class": auto_result.pair.modality_class,
            "candidate_id": candidate.candidate_id,
            "method_id": candidate.method_id,
            "execution_status": candidate.execution_status.value,
            "used_by_auto_service": False,
            "within_development_tolerance": None,
        }
        if candidate.estimated_transform is not None:
            parameter = model_aware_parameter_errors(
                ground_truth.moving_to_fixed,
                candidate.estimated_transform,
                transform_model="affine",
            )
            tre = transform_tre(
                ground_truth.moving_to_fixed,
                candidate.estimated_transform,
                control_points,
            )["px"]
            payload.update(parameter)
            payload.update(tre.to_metrics())
            payload["within_development_tolerance"] = bool(
                tre.mean <= float(tolerance_px)
            )
        rows.append(payload)
    return rows


def _summarize_hidden_validation(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["modality_class"]), str(row["method_id"]))
        grouped.setdefault(key, []).append(row)

    output: list[dict[str, Any]] = []
    for (modality_class, method_id), items in sorted(grouped.items()):
        tre_values = [
            float(item["tre_mean_px"])
            for item in items
            if item.get("tre_mean_px") is not None
        ]
        evaluated = [
            item for item in items
            if item.get("within_development_tolerance") is not None
        ]
        within = [
            item for item in evaluated
            if bool(item["within_development_tolerance"])
        ]
        output.append(
            {
                "modality_class": modality_class,
                "method_id": method_id,
                "attempts": len(items),
                "ground_truth_evaluated": len(evaluated),
                "within_development_tolerance": len(within),
                "development_geometric_success_rate": (
                    len(within) / len(evaluated) if evaluated else None
                ),
                "tre_mean_px_summary": robust_numeric_summary(tre_values),
                "used_by_auto_service": False,
            }
        )
    return output


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    output = dict(config["output"])
    output_dir = _resolve(str(output["directory"]))

    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    elif output_dir.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output directory already exists: {output_dir}. "
            "Use --overwrite for the Day 30 study."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    source = np.asarray(
        load_image(
            _resolve(str(config["source"]["image"])),
            color_mode="grayscale",
        ).array
    )
    resize_shape = tuple(int(value) for value in config["runner"]["resize_shape"])
    fixed = np.asarray(resize_image(source, resize_shape, interpolation="area"))
    ground_truth = _base_ground_truth(fixed, config)
    methods, parameters = _prepare_methods(config)

    agreement_config = dict(config["runner"]["agreement_grid"])
    tolerance_px = float(config["runner"]["development_tre_tolerance_px"])

    runs = []
    agreement_views = []
    validation_rows: list[dict[str, Any]] = []
    case_summaries = []

    for case_config in config["cases"]:
        pair, prepared = _prepare_case(fixed, ground_truth, dict(case_config))
        executor = _make_executor(config, prepared, parameters)
        service = AutomaticMultiMethodService(
            methods,
            executor,
            include_optional=bool(config["runner"]["include_optional_methods"]),
        )

        started = time.perf_counter()
        result = service.run(pair)
        orchestration_ms = (time.perf_counter() - started) * 1000.0

        if result.to_dict()["recommendation"]["selected_candidate_id"] is not None:
            raise AssertionError("Day 30 must not select a final best method.")
        for candidate in result.candidates:
            if candidate.geometric_metrics:
                raise AssertionError(
                    "Day 30 operation-time evidence must not contain hidden GT metrics."
                )
            if candidate.geometric_within_tolerance is not None:
                raise AssertionError(
                    "Day 30 operation-time evidence must not expose geometric PASS/CHECK."
                )

        agreement = build_preliminary_consensus(
            result,
            image_shape=fixed.shape,
            grid_rows=int(agreement_config["rows"]),
            grid_cols=int(agreement_config["cols"]),
            margin_fraction=float(agreement_config["margin_fraction"]),
        )
        if agreement.to_dict()["final_recommendation"] is not None:
            raise AssertionError("Preliminary consensus must not become a recommendation.")

        hidden_validation = _development_only_validation(
            result,
            prepared,
            tolerance_px=tolerance_px,
        )

        runs.append(result)
        agreement_views.append(agreement)
        validation_rows.extend(hidden_validation)
        case_summaries.append(
            {
                "pair_id": pair.pair_id,
                "modality_class": pair.modality_class,
                "condition": dict(case_config["condition"]),
                "compatible_candidates": len(result.candidates),
                "status_counts": result.status_counts,
                "orchestration_runtime_ms": orchestration_ms,
                "agreement_status": agreement.status,
                "eligible_for_agreement": len(agreement.eligible_candidate_ids),
                "consensus_anchor_candidate_id": agreement.consensus_anchor_candidate_id,
                "consensus_anchor_method_id": agreement.consensus_anchor_method_id,
                "median_pairwise_rms_px": agreement.median_pairwise_rms_px,
                "max_pairwise_rms_px": agreement.max_pairwise_rms_px,
                "final_recommendation": None,
            }
        )

    method_summaries = summarize_methods(runs)
    stage_runtime = summarize_stage_runtimes(runs)
    hidden_summary = _summarize_hidden_validation(validation_rows)
    orchestration_runtime_summary = robust_numeric_summary(
        row["orchestration_runtime_ms"] for row in case_summaries
    )

    automatic_runs_path = output_dir / "automatic_runs.json"
    agreements_path = output_dir / "agreement_views.json"
    method_summaries_path = output_dir / "method_summaries.json"
    validation_path = output_dir / "development_only_ground_truth_validation.json"

    automatic_runs_path.write_text(
        json.dumps([run.to_dict() for run in runs], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    agreements_path.write_text(
        json.dumps([view.to_dict() for view in agreement_views], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    method_summaries_path.write_text(
        json.dumps(method_summaries, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(
            {
                "tolerance_px": tolerance_px,
                "rows": validation_rows,
                "summaries": hidden_summary,
                "used_by_auto_service": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 6,
        "day": 30,
        "title": "Transform agreement, preliminary consensus, and Week 6 closure",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Compare compatible candidate transforms in a common image-space representation, "
            "build a ground-truth-free preliminary consensus view, summarize common evidence "
            "robustly by method and modality, retain runtime evidence, and close Week 6 without "
            "freezing a final best-method recommendation."
        ),
        "schema_version": "week06_transform_agreement_v1",
        "matrix": {
            "case_count": len(config["cases"]),
            "method_catalog_count": len(methods),
            "case_summaries": case_summaries,
        },
        "agreement_views": [view.to_dict() for view in agreement_views],
        "method_summaries": method_summaries,
        "stage_runtime_summary_ms": stage_runtime,
        "orchestration_runtime_summary_ms": orchestration_runtime_summary,
        "development_only_ground_truth_validation": {
            "tolerance_px": tolerance_px,
            "summaries": hidden_summary,
            "used_by_auto_service": False,
        },
        "scientific_guards": {
            "ground_truth_exposed_to_auto_service": False,
            "ground_truth_used_for_consensus": False,
            "raw_optimizer_objectives_cross_compared": False,
            "consensus_anchor_is_final_recommendation": False,
            "final_method_recommendation_implemented": False,
            "method_and_modality_summaries_kept_separate": True,
        },
        "artifacts": {
            "automatic_runs": str(automatic_runs_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "agreement_views": str(agreements_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "method_summaries": str(method_summaries_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "development_only_ground_truth_validation": str(
                validation_path.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
        },
        "week_6_completion_criteria": {
            "independently_tested_metrics": True,
            "common_result_schema": True,
            "unknown_images_free_of_unsupported_geometric_claims": True,
            "resumable_benchmark_without_duplicates": True,
            "modality_summaries_separate": True,
            "optimizer_objectives_separate_from_evaluation": True,
            "automatic_multi_method_execution": True,
            "transform_agreement_without_ground_truth": True,
            "final_ranking_deferred": True,
        },
        "interpretation": [
            "Transform disagreement is measured by mapping a common image-space control grid through each Moving-to-Fixed candidate transform and comparing the resulting point locations.",
            "The consensus anchor is the transform medoid with the smallest median pairwise RMS disagreement. It is a descriptive geometric reference, not a best-method recommendation.",
            "Only normalized common evidence is aggregated across methods. Raw ECC, RANSAC, and MI optimizer objectives remain method-specific diagnostics.",
            "Operation-time comparison does not use synthetic ground truth. Hidden ground truth is applied only after automatic execution for development validation.",
            "Monomodal and simulated multimodal summaries remain separate because metric behavior and method compatibility differ by modality class.",
            "Week 7 is required to calibrate robustness, ranking, confidence, and abstention policies."
        ],
        "limitations": [
            "The Day 30 comparison matrix is intentionally small and is not a substitute for Week 7 condition sweeps.",
            "The preliminary consensus view currently operates on 2D transforms in image coordinates.",
            "A single compatible candidate cannot produce cross-method agreement and is reported as insufficient_candidates.",
            "The transform medoid is not evidence that the anchor method is geometrically correct.",
            "The 3D RIRE technical path remains outside the automatic consensus development matrix."
        ],
        "next_step": (
            "Run the target Windows backend suite, frozen UI suite, and Day 30 script. "
            "After evidence review, freeze Week 6 and proceed to Week 7 robustness sweeps "
            "for condition-aware calibration, ranking, confidence, and abstention."
        ),
    }
    write_report_snapshot(
        _resolve(str(output["report_snapshot"])),
        report,
    )

    total_candidates = sum(len(run.candidates) for run in runs)
    status_totals = {status.value: 0 for status in ExecutionStatus}
    for run in runs:
        for key, value in run.status_counts.items():
            status_totals[key] += value

    print("Week 6 Day 30: transform agreement, preliminary consensus, and closure")
    print(f"Cases: {len(runs)}")
    print(f"Method catalog: {len(methods)}")
    print(f"Automatic candidate executions: {total_candidates}")
    print(
        "Status totals: "
        + ", ".join(f"{key}={value}" for key, value in sorted(status_totals.items()))
    )
    print("Ground truth exposed to auto service: no")
    print("Final method recommendation: deferred")
    for row in case_summaries:
        median = row["median_pairwise_rms_px"]
        median_text = "n/a" if median is None else f"{median:.3f} px"
        print(
            f"{row['pair_id']}: candidates={row['compatible_candidates']} "
            f"agreement={row['agreement_status']} "
            f"eligible={row['eligible_for_agreement']} "
            f"median_pairwise_rms={median_text} "
            f"anchor={row['consensus_anchor_method_id']}"
        )

    print(f"Method/modality summaries: {len(method_summaries)}")
    print(
        "Tracked report: "
        + str(_resolve(str(output["report_snapshot"])).relative_to(PROJECT_ROOT)).replace("\\", "/")
    )
    print("Do not start Week 7 until the target Windows Day 30 evidence is reviewed.")


if __name__ == "__main__":
    main()
