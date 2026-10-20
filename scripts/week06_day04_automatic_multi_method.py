from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for value in (str(PROJECT_ROOT), str(SRC_ROOT)):
    if value not in sys.path:
        sys.path.insert(0, value)

from image_registration.automatic_registration import (
    AutoMethodSpec,
    AutoPairProfile,
    AutomaticMultiMethodService,
)
from image_registration.config import load_config
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)
from image_registration.io import load_image
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
        description="Run the Week 6 Day 29 automatic multi-method foundation study."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _prepare_pair(config: dict[str, Any]) -> tuple[AutoPairProfile, dict[str, Any]]:
    source = np.asarray(
        load_image(_resolve(str(config["source"]["image"])), color_mode="grayscale").array
    )
    resize_shape = tuple(int(value) for value in config["runner"]["resize_shape"])
    fixed = np.asarray(resize_image(source, resize_shape, interpolation="area"))

    gt_config = dict(config["pair"]["development_ground_truth"])
    linear = np.asarray(gt_config["linear"], dtype=np.float64)
    center = image_center(fixed.shape) if bool(gt_config.get("centered", True)) else None
    moving_to_fixed = affine_matrix(
        linear,
        tx=float(gt_config["tx"]),
        ty=float(gt_config["ty"]),
        center=center,
    )
    ground_truth = GroundTruthTransform(
        transform_type="affine",
        parameters={
            "linear": linear.tolist(),
            "tx": float(gt_config["tx"]),
            "ty": float(gt_config["ty"]),
            "center": None if center is None else np.asarray(center).tolist(),
        },
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=invert_transform(moving_to_fixed),
    )
    generated = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")

    pair_profile = AutoPairProfile(
        pair_id=str(config["pair"]["id"]),
        dimensions=2,
        modality_class=str(config["pair"]["modality_class"]),
        candidate_transform_models=tuple(
            str(value) for value in config["pair"]["candidate_transform_models"]
        ),
        same_shape=bool(np.asarray(generated.fixed).shape == np.asarray(generated.moving).shape),
        # Operation deliberately hides the development ground truth.
        reference=ReferenceEvidence(),
        metadata={
            "source": str(config["source"]["image"]),
            "operation_ground_truth": str(config["pair"]["operation_ground_truth"]),
            "development_ground_truth_not_exposed_to_auto_service": True,
        },
    )
    prepared = {
        "fixed": np.asarray(generated.fixed),
        "moving": np.asarray(generated.moving),
        "ground_truth": ground_truth,
        "control_points_moving": np.asarray(generated.control_points_moving, dtype=np.float64),
    }
    return pair_profile, prepared


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
                display_name="Day 29 fixed",
                modality="synthetic",
                array=fixed,
            ),
            moving=ImageSource(
                source_type=SourceType.ARRAY,
                display_name="Day 29 moving",
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
        estimated = None
        overlap_fraction = None

        if run.transform is not None:
            estimated = np.asarray(run.transform.matrix, dtype=np.float64)

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
) -> list[dict[str, Any]]:
    """Evaluate synthetic GT after auto execution without feeding it into selection."""
    ground_truth = prepared["ground_truth"]
    control_points = prepared["control_points_moving"]
    rows: list[dict[str, Any]] = []
    for candidate in auto_result.candidates:
        payload: dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "method_id": candidate.method_id,
            "execution_status": candidate.execution_status.value,
            "used_by_auto_service": False,
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
        rows.append(payload)
    return rows


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    output = dict(config["output"])
    output_dir = _resolve(str(output["directory"]))

    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    elif output_dir.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output directory already exists: {output_dir}. Use --overwrite for the Day 29 study."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    pair, prepared = _prepare_pair(config)
    methods, parameters = _prepare_methods(config)
    executor = _make_executor(config, prepared, parameters)
    service = AutomaticMultiMethodService(
        methods,
        executor,
        include_optional=bool(config["runner"]["include_optional_methods"]),
    )
    result = service.run(pair)

    if len(result.candidates) < 2:
        raise AssertionError("Day 29 requires at least two compatible candidates.")
    if result.to_dict()["recommendation"]["selected_candidate_id"] is not None:
        raise AssertionError("Day 29 must not select a best method.")
    for candidate in result.candidates:
        if candidate.geometric_metrics:
            raise AssertionError(
                "Day 29 operation-time evidence must not contain hidden geometric ground-truth metrics."
            )
        if candidate.geometric_within_tolerance is not None:
            raise AssertionError(
                "Day 29 operation-time evidence must not expose a geometric PASS/CHECK state."
            )

    auto_payload = result.to_dict()
    auto_path = output_dir / "automatic_run.json"
    auto_path.write_text(json.dumps(auto_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation_only = _development_only_validation(result, prepared)
    compatibility = [item.to_dict() for item in result.compatibility]
    compatible = [item for item in compatibility if item["compatible"]]
    excluded = [item for item in compatibility if not item["compatible"]]

    report = {
        "week": 6,
        "day": 29,
        "title": "Automatic multi-method execution foundation",
        "status": "development_run_complete_target_validation_pending",
        "purpose": (
            "Select compatible registration candidates, execute all candidates through the "
            "existing RegistrationService boundary, normalize only common Week 6 evidence, "
            "and preserve method-specific diagnostics, CHECK states, and failures without "
            "selecting a final best method."
        ),
        "schema_version": "week06_auto_run_v1",
        "pair": {
            "pair_id": pair.pair_id,
            "modality_class": pair.modality_class,
            "candidate_transform_models": list(pair.candidate_transform_models),
            "operation_ground_truth": "unavailable",
            "development_ground_truth_available_for_validation_only": True,
        },
        "method_catalog_count": len(methods),
        "compatible_candidate_count": len(compatible),
        "excluded_candidate_count": len(excluded),
        "compatibility": compatibility,
        "status_counts": result.status_counts,
        "recommendation": auto_payload["recommendation"],
        "candidate_summaries": [
            {
                "candidate_id": candidate.candidate_id,
                "method_id": candidate.method_id,
                "method_family": candidate.method_family,
                "transform_model": candidate.transform_model,
                "execution_status": candidate.execution_status.value,
                "transform_plausible": candidate.transform_plausible,
                "common_evidence": candidate.to_dict()["common_evidence"],
                "method_diagnostics_retained": bool(candidate.method_diagnostics),
                "failure_reason": candidate.failure_reason,
            }
            for candidate in result.candidates
        ],
        "development_only_ground_truth_validation": validation_only,
        "scientific_guards": {
            "ground_truth_exposed_to_auto_service": False,
            "geometric_metrics_in_operation_evidence": False,
            "raw_optimizer_objectives_cross_compared": False,
            "final_method_recommendation_implemented": False,
            "failed_and_check_candidates_preserved": True,
        },
        "artifacts": {
            "automatic_run": str(auto_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        },
        "interpretation": [
            "Compatibility is explicit and auditable; methods are excluded for dimensions, transform model, modality class, shape, or optional-method policy.",
            "All compatible candidates are executed rather than stopping after the first successful registration.",
            "Only metrics from the Day 26 common contract are normalized for comparison; method-specific optimizer diagnostics remain opaque evidence.",
            "The operational candidate records behave as if ground truth is unavailable, matching the intended real-world automatic workflow.",
            "Synthetic ground truth is used only after execution as a development validation probe and is not available to the automatic service.",
            "No best-method recommendation or confidence score is produced on Day 29.",
        ],
        "limitations": [
            "Day 29 uses a controlled 2D affine development pair and does not yet characterize arbitrary motion models automatically.",
            "The candidate catalog is configuration driven; learned or heuristic pair characterization is deferred.",
            "Transform-space agreement, consensus, robust summaries, and preliminary comparison are Day 30 work.",
            "Evidence-backed ranking and confidence calibration require Week 7 robustness results.",
            "The 3D RIRE technical path is not part of the Day 29 automatic development run.",
        ],
        "next_step": (
            "Run the target Windows backend suite, frozen UI suite, and Day 29 script. "
            "After evidence review, freeze the automatic execution contract and proceed to "
            "Day 30 transform-space agreement and preliminary consensus work."
        ),
    }
    write_report_snapshot(
        _resolve(str(output["report_snapshot"])),
        report,
    )

    print("Week 6 Day 29: automatic multi-method execution foundation")
    print(f"Method catalog: {len(methods)}")
    print(f"Compatible candidates: {len(compatible)}")
    print(f"Excluded candidates: {len(excluded)}")
    print(
        "Status counts: "
        + ", ".join(f"{key}={value}" for key, value in sorted(result.status_counts.items()))
    )
    print("Recommendation: deferred_until_robustness_calibration")
    print("Ground truth exposed to auto service: no")
    for candidate in result.candidates:
        evidence = candidate.to_dict()["common_evidence"]
        print(
            f"{candidate.method_id}: status={candidate.execution_status.value} "
            f"plausible={candidate.transform_plausible} "
            f"common_descriptive={len(evidence['descriptive'])} "
            f"diagnostics={len(candidate.method_diagnostics)}"
        )
    print(
        "Tracked report: "
        + str(_resolve(str(output["report_snapshot"])).relative_to(PROJECT_ROOT)).replace("\\", "/")
    )
    print("Do not start Day 30 until the target Windows Day 29 evidence is reviewed.")


if __name__ == "__main__":
    main()
