from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config
from image_registration.evaluation_contracts import (
    COORDINATE_ORDER_2D,
    COORDINATE_ORDER_3D,
    METRIC_DEFINITIONS,
    SCHEMA_VERSION,
    TRANSFORM_DIRECTION,
    EvaluationContext,
    ReferenceEvidence,
    metric_catalog,
    summarize_metric_availability,
)
from image_registration.reporting import write_report_snapshot


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and snapshot the Week 6 Day 26 unified evaluation contract."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _validate_config(config: dict[str, Any]) -> None:
    required = {"experiment", "contract", "metric_groups", "scenarios", "output"}
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Missing Day 26 configuration sections: {', '.join(missing)}")

    contract = dict(config["contract"])
    expected = {
        "schema_version": SCHEMA_VERSION,
        "transform_direction": TRANSFORM_DIRECTION,
        "coordinate_order_by_dimension": {2: COORDINATE_ORDER_2D, 3: COORDINATE_ORDER_3D},
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise ValueError(f"contract.{key} must be '{value}'.")
    coordinate_orders = dict(contract.get("coordinate_order_by_dimension", {}))
    if str(coordinate_orders.get(2, coordinate_orders.get("2", ""))) != COORDINATE_ORDER_2D:
        raise ValueError("contract.coordinate_order_by_dimension.2 must be 'xy'.")
    if str(coordinate_orders.get(3, coordinate_orders.get("3", ""))) != COORDINATE_ORDER_3D:
        raise ValueError("contract.coordinate_order_by_dimension.3 must be 'xyz'.")

    configured_metrics: list[str] = []
    for group_name, metric_keys in dict(config["metric_groups"]).items():
        if not isinstance(metric_keys, list) or not metric_keys:
            raise ValueError(f"metric_groups.{group_name} must be a non-empty list.")
        configured_metrics.extend(str(item) for item in metric_keys)
    unknown = sorted(set(configured_metrics).difference(METRIC_DEFINITIONS))
    if unknown:
        raise ValueError(f"Unknown configured metrics: {', '.join(unknown)}")
    missing_metrics = sorted(set(METRIC_DEFINITIONS).difference(configured_metrics))
    if missing_metrics:
        raise ValueError(f"Metric catalog entries missing from configuration: {', '.join(missing_metrics)}")
    if len(configured_metrics) != len(set(configured_metrics)):
        raise ValueError("Each metric must appear in exactly one metric group.")

    scenarios = dict(config["scenarios"])
    if not scenarios:
        raise ValueError("scenarios must not be empty.")
    for scenario_id, values in scenarios.items():
        required_scenario = {
            "modality_class",
            "exact_transform",
            "landmarks",
            "masks",
            "physical_spacing",
            "valid_overlap_fraction",
        }
        missing_scenario = required_scenario.difference(values)
        if missing_scenario:
            raise ValueError(
                f"Scenario '{scenario_id}' is missing: {', '.join(sorted(missing_scenario))}"
            )


def _scenario_context(values: dict[str, Any]) -> EvaluationContext:
    return EvaluationContext(
        modality_class=str(values["modality_class"]),
        reference=ReferenceEvidence(
            exact_transform=bool(values["exact_transform"]),
            landmarks=bool(values["landmarks"]),
            masks=bool(values["masks"]),
            physical_spacing=bool(values["physical_spacing"]),
        ),
        valid_overlap_available=True,
        valid_overlap_fraction=float(values["valid_overlap_fraction"]),
    )


def _write_metric_catalog_csv(path: Path) -> None:
    rows = metric_catalog()
    if not rows:
        raise ValueError("Metric catalog is empty.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    _validate_config(config)

    output_dir = _resolve(str(config["output"]["directory"]))
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"Output directory already exists: {output_dir}. Use --overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog = metric_catalog()
    scenario_summaries: dict[str, Any] = {}
    for scenario_id, values in dict(config["scenarios"]).items():
        context = _scenario_context(dict(values))
        availability = summarize_metric_availability(context)
        scenario_summaries[str(scenario_id)] = {
            "modality_class": context.modality_class,
            "reference_label": context.reference.label,
            "geometric_pass_allowed": context.geometric_pass_allowed,
            "valid_overlap_fraction": context.valid_overlap_fraction,
            "available_metrics": [
                key for key, item in availability.items() if bool(item["available"])
            ],
            "unavailable_metrics": {
                key: item["reason"]
                for key, item in availability.items()
                if not bool(item["available"])
            },
        }

    _write_metric_catalog_csv(output_dir / "metric_catalog.csv")
    (output_dir / "evaluation_contract.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "transform_direction": TRANSFORM_DIRECTION,
                "coordinate_order_by_dimension": {2: COORDINATE_ORDER_2D, 3: COORDINATE_ORDER_3D},
                "principles": list(config["contract"]["principles"]),
                "metric_catalog": catalog,
                "scenario_availability": scenario_summaries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "week": 6,
        "day": 26,
        "title": "Unified evaluation semantics and result contract",
        "status": "development_run_complete_target_validation_pending",
        "schema_version": SCHEMA_VERSION,
        "transform_convention": "Moving -> Fixed",
        "coordinate_order_by_dimension": {2: COORDINATE_ORDER_2D, 3: COORDINATE_ORDER_3D},
        "purpose": (
            "Freeze the method-independent evaluation vocabulary, reference-evidence policy, "
            "valid-overlap rule, metric units, and result contract before implementing the full Week 6 metrics and benchmark runner."
        ),
        "principles": list(config["contract"]["principles"]),
        "metric_count": len(catalog),
        "metric_groups": config["metric_groups"],
        "scenario_availability": scenario_summaries,
        "scientific_guards": [
            "Unknown image pairs cannot report TRE, transform parameter error, Dice without reference masks, or geometric PASS/CHECK.",
            "NCC, SSIM, MAE, MSE, and evaluation MI are descriptive evidence computed within valid overlap and do not independently prove geometric correctness.",
            "Optimization objectives remain method-specific diagnostics and are not directly compared across methods.",
            "Every comparable transform uses the project Moving -> Fixed direction and x,y coordinate order.",
            "Failed runs remain first-class records and require an explicit failure reason.",
        ],
        "artifacts": {
            "local_contract": str((output_dir / "evaluation_contract.json").relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "local_metric_catalog": str((output_dir / "metric_catalog.csv").relative_to(PROJECT_ROOT)).replace("\\", "/"),
        },
        "next_step": (
            "Run target Windows validation. After review, Day 27 implements and independently tests the actual metric calculations under this frozen contract."
        ),
    }
    write_report_snapshot(_resolve(str(config["output"]["report_snapshot"])), report)

    print("Week 6 Day 26: unified evaluation contract")
    print(f"Schema: {SCHEMA_VERSION}")
    print(
        "Transform convention: Moving -> Fixed "
        f"(2D {COORDINATE_ORDER_2D}, 3D {COORDINATE_ORDER_3D})"
    )
    print(f"Common metric definitions: {len(catalog)}")
    for scenario_id, summary in scenario_summaries.items():
        print(
            f"{scenario_id:<28} reference={summary['reference_label']:<18} "
            f"geometric_pass={str(summary['geometric_pass_allowed']):<5} "
            f"metrics={len(summary['available_metrics'])}"
        )
    print(f"Tracked report: {config['output']['report_snapshot']}")
    print("Do not start Day 27 until the target Windows Day 26 evidence is reviewed.")


if __name__ == "__main__":
    main()
