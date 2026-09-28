from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config
from image_registration.degradations import gaussian_blur, illumination_gradient
from image_registration.io import load_image
from image_registration.orb import (
    ORBConfig,
    ORBFeatureResult,
    detect_orb_features,
    draw_orb_keypoints,
    keypoint_grid_coverage,
    keypoint_response_summary,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import invert_transform, rigid_matrix, similarity_matrix, translation_matrix


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _orb_config(config: dict[str, Any]) -> ORBConfig:
    orb = config["orb"]
    return ORBConfig(
        n_features=int(orb.get("n_features", 800)),
        scale_factor=float(orb.get("scale_factor", 1.2)),
        n_levels=int(orb.get("n_levels", 8)),
        edge_threshold=int(orb.get("edge_threshold", 31)),
        first_level=int(orb.get("first_level", 0)),
        wta_k=int(orb.get("wta_k", 2)),
        score_type=str(orb.get("score_type", "harris")).strip().lower(),
        patch_size=int(orb.get("patch_size", 31)),
        fast_threshold=int(orb.get("fast_threshold", 20)),
    )


def _make_geometric_pair(fixed: np.ndarray, case: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    operation = str(case["operation"]).strip().lower()
    center = image_center(fixed.shape)

    if operation == "translation":
        matrix = translation_matrix(float(case.get("tx", 0.0)), float(case.get("ty", 0.0)))
        parameters = {"tx": float(case.get("tx", 0.0)), "ty": float(case.get("ty", 0.0))}
    elif operation == "rigid":
        matrix = rigid_matrix(
            float(case.get("angle_degrees", 0.0)),
            tx=float(case.get("tx", 0.0)),
            ty=float(case.get("ty", 0.0)),
            center=center,
        )
        parameters = {
            "angle_degrees": float(case.get("angle_degrees", 0.0)),
            "tx": float(case.get("tx", 0.0)),
            "ty": float(case.get("ty", 0.0)),
            "center": center.tolist(),
        }
    elif operation == "similarity":
        matrix = similarity_matrix(
            float(case.get("scale", 1.0)),
            angle_degrees=float(case.get("angle_degrees", 0.0)),
            tx=float(case.get("tx", 0.0)),
            ty=float(case.get("ty", 0.0)),
            center=center,
        )
        parameters = {
            "scale": float(case.get("scale", 1.0)),
            "angle_degrees": float(case.get("angle_degrees", 0.0)),
            "tx": float(case.get("tx", 0.0)),
            "ty": float(case.get("ty", 0.0)),
            "center": center.tolist(),
        }
    else:
        raise ValueError(f"Unsupported geometric operation: {operation}")

    ground_truth = GroundTruthTransform(
        transform_type=operation,
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )
    pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    metadata = {
        "operation": operation,
        "ground_truth_transform": ground_truth.as_dict(),
    }
    return np.asarray(pair.moving), metadata


def _build_case(fixed: np.ndarray, case: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    operation = str(case["operation"]).strip().lower()
    if operation == "identity":
        return fixed.copy(), {"operation": "identity"}
    if operation in {"translation", "rigid", "similarity"}:
        return _make_geometric_pair(fixed, case)
    if operation == "gaussian_blur":
        sigma = float(case.get("sigma", 1.2))
        return np.asarray(gaussian_blur(fixed, sigma=sigma)), {
            "operation": operation,
            "sigma": sigma,
        }
    if operation == "illumination_gradient":
        strength = float(case.get("strength_fraction", 0.25))
        direction = str(case.get("direction", "horizontal"))
        return np.asarray(
            illumination_gradient(
                fixed,
                strength_fraction=strength,
                direction=direction,
            )
        ), {
            "operation": operation,
            "strength_fraction": strength,
            "direction": direction,
        }
    raise ValueError(f"Unsupported Day 16 operation: {operation}")


def _save_rgb(path: Path, image_rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(np.asarray(image_rgb, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"Could not write image: {path}")


def _save_coverage_plot(
    path: Path,
    image: np.ndarray,
    result: ORBFeatureResult,
    *,
    rows: int,
    columns: int,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 5.4), dpi=140)
    ax.imshow(image, cmap="gray")
    points = result.points_xy
    if points.size:
        ax.scatter(points[:, 0], points[:, 1], s=8, alpha=0.65)
    height, width = image.shape[:2]
    for column in range(1, columns):
        ax.axvline(column * width / columns, linewidth=0.8, alpha=0.55)
    for row in range(1, rows):
        ax.axhline(row * height / rows, linewidth=0.8, alpha=0.55)
    ax.set_title(title)
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _result_metrics(
    result: ORBFeatureResult,
    *,
    rows: int,
    columns: int,
) -> dict[str, Any]:
    response = keypoint_response_summary(result)
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "keypoint_count": int(result.keypoint_count),
        "descriptor_count": int(result.descriptor_count),
        "descriptor_length_bytes": (
            int(result.descriptors.shape[1]) if result.descriptors is not None else None
        ),
        "spatial_coverage": keypoint_grid_coverage(
            result.points_xy,
            result.image_shape,
            rows=rows,
            columns=columns,
        ),
        "response": response,
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _case_record(
    case: dict[str, Any],
    fixed_result: ORBFeatureResult,
    moving_result: ORBFeatureResult,
    metadata: dict[str, Any],
    *,
    rows: int,
    columns: int,
) -> dict[str, Any]:
    fixed_metrics = _result_metrics(fixed_result, rows=rows, columns=columns)
    moving_metrics = _result_metrics(moving_result, rows=rows, columns=columns)
    fixed_count = int(fixed_metrics["keypoint_count"])
    moving_count = int(moving_metrics["keypoint_count"])
    count_ratio = float(moving_count / fixed_count) if fixed_count > 0 else None

    success = bool(fixed_result.success and moving_result.success)
    failure_parts = [
        value
        for value in (fixed_result.failure_reason, moving_result.failure_reason)
        if value is not None
    ]
    return {
        "case_id": str(case["id"]),
        "source_id": str(case["source"]),
        "operation": str(case["operation"]),
        "success": success,
        "failure_reason": "; ".join(failure_parts) if failure_parts else None,
        "condition_metadata": metadata,
        "fixed": fixed_metrics,
        "moving": moving_metrics,
        "moving_to_fixed_keypoint_count_ratio": count_ratio,
        "moving_minus_fixed_keypoints": moving_count - fixed_count,
        "moving_minus_fixed_spatial_coverage": float(
            moving_metrics["spatial_coverage"] - fixed_metrics["spatial_coverage"]
        ),
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in records if record["success"]]
    moving_counts = np.asarray(
        [record["moving"]["keypoint_count"] for record in successful], dtype=np.float64
    )
    moving_coverages = np.asarray(
        [record["moving"]["spatial_coverage"] for record in successful], dtype=np.float64
    )
    moving_runtimes = np.asarray(
        [record["moving"]["runtime_ms"] for record in successful], dtype=np.float64
    )
    ratios = np.asarray(
        [
            record["moving_to_fixed_keypoint_count_ratio"]
            for record in successful
            if record["moving_to_fixed_keypoint_count_ratio"] is not None
        ],
        dtype=np.float64,
    )

    return {
        "case_count": len(records),
        "successful_case_count": len(successful),
        "failed_case_count": len(records) - len(successful),
        "mean_moving_keypoint_count": float(np.mean(moving_counts)) if moving_counts.size else None,
        "median_moving_keypoint_count": float(np.median(moving_counts)) if moving_counts.size else None,
        "mean_moving_spatial_coverage": (
            float(np.mean(moving_coverages)) if moving_coverages.size else None
        ),
        "mean_moving_detection_runtime_ms": (
            float(np.mean(moving_runtimes)) if moving_runtimes.size else None
        ),
        "mean_moving_to_fixed_keypoint_count_ratio": (
            float(np.mean(ratios)) if ratios.size else None
        ),
    }


def _findings(records: list[dict[str, Any]], *, n_features: int) -> dict[str, Any]:
    successful = [record for record in records if record["success"]]
    if not successful:
        return {
            "observations": ["No configured case produced descriptors in both images."],
            "interpretation": [
                "Feature matching should not start until the detection configuration is corrected."
            ],
            "limitations": [
                "This development run did not provide a usable feature-detection baseline."
            ],
            "decision": "Review ORB configuration and source images before Day 17.",
        }

    highest = max(successful, key=lambda item: item["moving"]["keypoint_count"])
    lowest = min(successful, key=lambda item: item["moving"]["keypoint_count"])
    largest_drop = min(
        successful,
        key=lambda item: item["moving_to_fixed_keypoint_count_ratio"]
        if item["moving_to_fixed_keypoint_count_ratio"] is not None
        else float("inf"),
    )
    lowest_coverage = min(successful, key=lambda item: item["moving"]["spatial_coverage"])

    saturated = [
        record["case_id"]
        for record in successful
        if record["moving"]["keypoint_count"] >= n_features
    ]

    observations = [
        (
            f"The largest moving-image keypoint count occurred in {highest['case_id']} "
            f"with {highest['moving']['keypoint_count']} keypoints."
        ),
        (
            f"The smallest moving-image keypoint count occurred in {lowest['case_id']} "
            f"with {lowest['moving']['keypoint_count']} keypoints."
        ),
        (
            f"The strongest keypoint-count reduction relative to its fixed image occurred in "
            f"{largest_drop['case_id']}, with a moving-to-fixed count ratio of "
            f"{largest_drop['moving_to_fixed_keypoint_count_ratio']:.3f}."
        ),
        (
            f"The lowest 4x4 spatial coverage occurred in {lowest_coverage['case_id']} at "
            f"{lowest_coverage['moving']['spatial_coverage']:.3f}."
        ),
    ]

    if saturated:
        observations.append(
            f"The configured n_features cap of {n_features} was reached in "
            + ", ".join(saturated)
            + ". Counts in those cases are capped and should not be interpreted as the total number of detectable features."
        )

    failures = [record for record in records if not record["success"]]
    if failures:
        observations.append(
            "Safe detection failures were recorded for: "
            + ", ".join(record["case_id"] for record in failures)
            + "."
        )
    else:
        observations.append("All configured Day 16 cases produced ORB descriptors in both images.")

    return {
        "observations": observations,
        "interpretation": [
            "ORB feature availability changes with image content and appearance or geometric modification, so later matching quality should be interpreted together with keypoint count and spatial coverage.",
            "A large keypoint count alone is not evidence that a reliable transform can be estimated. Day 17 must test descriptor correspondence quality before any geometric conclusion is made.",
        ],
        "limitations": [
            "Day 16 measures detection and descriptor extraction only. It does not measure keypoint repeatability, correspondence correctness, or registration accuracy because descriptor matching has not been introduced yet.",
            "The observations are specific to the tracked images, configured transformations, OpenCV ORB settings, and the machine used for this run.",
        ],
        "decision": "Proceed to Day 17 with KNN Hamming matching, ratio filtering, cross-check comparison, and match spatial-coverage diagnostics after target-machine validation.",
    }


def _validated_report_exists(path: Path) -> bool:
    """Return True when a tracked report already contains completed target validation."""
    if not path.exists():
        return False
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    local_validation = existing.get("local_validation")
    return bool(
        existing.get("status") == "complete"
        and isinstance(local_validation, dict)
        and local_validation.get("status") == "complete"
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "case_id": record["case_id"],
                "source_id": record["source_id"],
                "operation": record["operation"],
                "success": record["success"],
                "failure_reason": record["failure_reason"],
                "fixed_keypoints": record["fixed"]["keypoint_count"],
                "moving_keypoints": record["moving"]["keypoint_count"],
                "keypoint_count_ratio": record["moving_to_fixed_keypoint_count_ratio"],
                "fixed_spatial_coverage": record["fixed"]["spatial_coverage"],
                "moving_spatial_coverage": record["moving"]["spatial_coverage"],
                "fixed_runtime_ms": record["fixed"]["runtime_ms"],
                "moving_runtime_ms": record["moving"]["runtime_ms"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day 16 ORB feature-detection experiment.")
    parser.add_argument(
        "--config",
        default="configs/week04_day01_orb_features.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    args = parser.parse_args()

    config_path = _resolve(args.config)
    config = load_config(config_path)
    orb_config = _orb_config(config)
    orb_config.validate()

    grid = config["orb"].get("spatial_grid", {})
    rows = int(grid.get("rows", 4))
    columns = int(grid.get("columns", 4))

    output_dir = _resolve(str(config["output"]["directory"]))
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output_dir}. Use --overwrite to replace it."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    sources: dict[str, np.ndarray] = {}
    for source_id, source_path in config["sources"].items():
        sources[str(source_id)] = np.asarray(
            load_image(_resolve(str(source_path)), color_mode="grayscale").array
        )

    records: list[dict[str, Any]] = []
    for index, case_raw in enumerate(config["cases"], start=1):
        case = dict(case_raw)
        source_id = str(case["source"])
        fixed = sources[source_id]
        moving, condition_metadata = _build_case(fixed, case)

        fixed_result = detect_orb_features(fixed, config=orb_config)
        moving_result = detect_orb_features(moving, config=orb_config)
        record = _case_record(
            case,
            fixed_result,
            moving_result,
            condition_metadata,
            rows=rows,
            columns=columns,
        )
        records.append(record)

        case_dir = output_dir / "cases" / str(case["id"])
        _save_rgb(case_dir / "fixed_keypoints.png", draw_orb_keypoints(fixed, fixed_result))
        _save_rgb(case_dir / "moving_keypoints.png", draw_orb_keypoints(moving, moving_result))
        _save_coverage_plot(
            case_dir / "fixed_spatial_coverage.png",
            fixed,
            fixed_result,
            rows=rows,
            columns=columns,
            title=f"{case['id']} - fixed ORB keypoints",
        )
        _save_coverage_plot(
            case_dir / "moving_spatial_coverage.png",
            moving,
            moving_result,
            rows=rows,
            columns=columns,
            title=f"{case['id']} - moving ORB keypoints",
        )

        print(
            f"{index:02d}/{len(config['cases']):02d} {case['id']:<24} "
            f"fixed={fixed_result.keypoint_count:4d}  "
            f"moving={moving_result.keypoint_count:4d}  "
            f"coverage={record['moving']['spatial_coverage']:.3f}  "
            f"{'PASS' if record['success'] else 'FAIL'}"
        )

    summary = _summarize(records)
    findings = _findings(records, n_features=orb_config.n_features)

    with (output_dir / "orb_feature_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "orb_feature_results.csv", records)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "findings": findings}, handle, indent=2)
        handle.write("\n")

    report_payload = {
        "week": 4,
        "global_day": 16,
        "week_day": 1,
        "title": "ORB keypoint detection and binary descriptor extraction",
        "status": "implementation_complete_local_validation_pending",
        "method": "ORB",
        "scope": "feature detection and descriptor extraction only",
        "configuration": {
            "n_features": orb_config.n_features,
            "scale_factor": orb_config.scale_factor,
            "n_levels": orb_config.n_levels,
            "edge_threshold": orb_config.edge_threshold,
            "first_level": orb_config.first_level,
            "wta_k": orb_config.wta_k,
            "score_type": orb_config.score_type,
            "patch_size": orb_config.patch_size,
            "fast_threshold": orb_config.fast_threshold,
            "spatial_grid": {"rows": rows, "columns": columns},
        },
        "development_run": summary,
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "daily_summary": "docs/daily/day_16_summary.md",
        "technical_note": "docs/ORB_FEATURES.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the experiment and full test suite on the target Windows environment before marking Day 16 complete.",
        },
    }
    report_path = PROJECT_ROOT / "reports/week04_day01_orb_features.json"
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print(
            "Tracked Day 16 report already contains completed target validation; "
            "preserving it."
        )
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nDay 16 development run summary")
    print(f"Cases: {summary['case_count']}")
    print(f"Successful cases: {summary['successful_case_count']}")
    print(f"Mean moving keypoints: {summary['mean_moving_keypoint_count']:.1f}")
    print(f"Mean moving spatial coverage: {summary['mean_moving_spatial_coverage']:.3f}")
    print(f"Mean moving detection runtime: {summary['mean_moving_detection_runtime_ms']:.3f} ms")
    print(
        "Tracked report "
        f"({report_action}): reports/week04_day01_orb_features.json"
    )


if __name__ == "__main__":
    main()
