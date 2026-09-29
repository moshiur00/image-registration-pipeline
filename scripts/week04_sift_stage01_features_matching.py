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
from image_registration.degradations import gaussian_blur
from image_registration.feature_matching import (
    FeatureMatchResult,
    correspondence_grid_coverage,
    correspondence_points,
    draw_feature_matches,
    match_distance_summary,
    match_feature_knn_ratio,
)
from image_registration.io import load_image
from image_registration.overlap import apply_field_of_view, rectangular_field_of_view_mask
from image_registration.reporting import write_report_snapshot
from image_registration.sift import (
    SIFTConfig,
    SIFTFeatureResult,
    detect_sift_features,
    draw_sift_keypoints,
    sift_keypoint_response_summary,
    sift_spatial_coverage,
)
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import invert_transform, rigid_matrix, similarity_matrix


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Week 4 SIFT extension Stage 1 experiment.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _sift_config(config: dict[str, Any]) -> SIFTConfig:
    values = config["sift"]
    return SIFTConfig(
        n_features=int(values.get("n_features", 0)),
        n_octave_layers=int(values.get("n_octave_layers", 3)),
        contrast_threshold=float(values.get("contrast_threshold", 0.04)),
        edge_threshold=float(values.get("edge_threshold", 10.0)),
        sigma=float(values.get("sigma", 1.6)),
    )


def _make_geometric_pair(fixed: np.ndarray, case: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    operation = str(case["operation"]).strip().lower()
    center = image_center(fixed.shape)
    if operation == "rigid":
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
    return np.asarray(pair.moving), {
        "operation": operation,
        "ground_truth_transform": ground_truth.as_dict(),
    }


def _build_case(fixed: np.ndarray, case: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    operation = str(case["operation"]).strip().lower()
    if operation == "identity":
        return fixed.copy(), {"operation": operation}
    if operation in {"rigid", "similarity"}:
        return _make_geometric_pair(fixed, case)
    if operation == "gaussian_blur":
        sigma = float(case.get("sigma", 1.2))
        return np.asarray(gaussian_blur(fixed, sigma=sigma)), {
            "operation": operation,
            "sigma": sigma,
        }
    if operation == "restricted_fov":
        width_fraction = float(case.get("width_fraction", 0.6))
        height_fraction = float(case.get("height_fraction", 0.75))
        center_x_fraction = float(case.get("center_x_fraction", 0.5))
        center_y_fraction = float(case.get("center_y_fraction", 0.5))
        mask = rectangular_field_of_view_mask(
            fixed.shape,
            width_fraction=width_fraction,
            height_fraction=height_fraction,
            center_x_fraction=center_x_fraction,
            center_y_fraction=center_y_fraction,
        )
        moving = apply_field_of_view(fixed, mask, fill_value=0.0)
        return np.asarray(moving), {
            "operation": operation,
            "width_fraction": width_fraction,
            "height_fraction": height_fraction,
            "center_x_fraction": center_x_fraction,
            "center_y_fraction": center_y_fraction,
            "visible_fraction": float(np.mean(mask)),
        }
    raise ValueError(f"Unsupported SIFT Stage 1 operation: {operation}")


def _save_rgb(path: Path, image_rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(np.asarray(image_rgb, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"Could not write image: {path}")


def _feature_metrics(result: SIFTFeatureResult, *, rows: int, columns: int) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "keypoint_count": int(result.keypoint_count),
        "descriptor_count": int(result.descriptor_count),
        "descriptor_length": int(result.descriptors.shape[1]) if result.descriptors is not None else None,
        "descriptor_dtype": str(result.descriptors.dtype) if result.descriptors is not None else None,
        "spatial_coverage": sift_spatial_coverage(result, rows=rows, columns=columns),
        "response": sift_keypoint_response_summary(result),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _match_metrics(
    result: FeatureMatchResult,
    fixed: SIFTFeatureResult,
    moving: SIFTFeatureResult,
    *,
    rows: int,
    columns: int,
) -> dict[str, Any]:
    coverage = correspondence_grid_coverage(result, fixed, moving, rows=rows, columns=columns)
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "tentative_match_count": int(result.tentative_count),
        "accepted_match_count": int(result.accepted_count),
        "rejected_match_count": int(result.rejected_count),
        "acceptance_rate": result.acceptance_rate,
        "distance": match_distance_summary(result.accepted_matches),
        "fixed_spatial_coverage": float(coverage.fixed_coverage),
        "moving_spatial_coverage": float(coverage.moving_coverage),
        "minimum_spatial_coverage": float(coverage.minimum_coverage),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _save_distance_histogram(path: Path, result: FeatureMatchResult, *, title: str) -> None:
    tentative = np.asarray([item.distance for item in result.tentative_matches], dtype=np.float64)
    accepted = np.asarray([item.distance for item in result.accepted_matches], dtype=np.float64)
    fig, axis = plt.subplots(figsize=(7.2, 4.8), dpi=140)
    if tentative.size:
        axis.hist(tentative, bins=30, alpha=0.5, label="tentative")
    if accepted.size:
        axis.hist(accepted, bins=30, alpha=0.65, label="accepted")
    axis.set_title(title)
    axis.set_xlabel("L2 descriptor distance")
    axis.set_ylabel("Match count")
    if tentative.size or accepted.size:
        axis.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _save_coverage_plot(
    path: Path,
    fixed_image: np.ndarray,
    moving_image: np.ndarray,
    fixed: SIFTFeatureResult,
    moving: SIFTFeatureResult,
    result: FeatureMatchResult,
    *,
    rows: int,
    columns: int,
    title: str,
) -> None:
    fixed_points, moving_points = correspondence_points(result, fixed, moving)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), dpi=140)
    for axis, image, points, label in (
        (axes[0], moving_image, moving_points, "moving"),
        (axes[1], fixed_image, fixed_points, "fixed"),
    ):
        axis.imshow(image, cmap="gray")
        if points.size:
            axis.scatter(points[:, 0], points[:, 1], s=10, alpha=0.7)
        height, width = image.shape[:2]
        for column in range(1, columns):
            axis.axvline(column * width / columns, linewidth=0.7, alpha=0.5)
        for row in range(1, rows):
            axis.axhline(row * height / rows, linewidth=0.7, alpha=0.5)
        axis.set_xlim(0, width)
        axis.set_ylim(height, 0)
        axis.set_title(label)
    fig.suptitle(title)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _save_ratio_sweep_plot(path: Path, summaries: list[dict[str, Any]]) -> None:
    thresholds = [float(item["ratio_threshold"]) for item in summaries]
    matches = [float(item["mean_accepted_match_count"]) for item in summaries]
    coverage = [float(item["mean_minimum_spatial_coverage"]) for item in summaries]
    fig, axis = plt.subplots(figsize=(7.4, 4.8), dpi=140)
    axis.plot(thresholds, matches, marker="o", label="mean accepted matches")
    axis.set_xlabel("SIFT ratio threshold")
    axis.set_ylabel("Mean accepted matches")
    second = axis.twinx()
    second.plot(thresholds, coverage, marker="s", label="mean minimum coverage")
    second.set_ylabel("Mean minimum spatial coverage")
    axis.set_title("SIFT ratio-threshold sweep")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = np.asarray([record["matching"]["accepted_match_count"] for record in records], dtype=float)
    coverage = np.asarray([record["matching"]["minimum_spatial_coverage"] for record in records], dtype=float)
    detection = np.asarray(
        [record["fixed_features"]["runtime_ms"] + record["moving_features"]["runtime_ms"] for record in records],
        dtype=float,
    )
    matching = np.asarray([record["matching"]["runtime_ms"] for record in records], dtype=float)
    return {
        "case_count": len(records),
        "successful_case_count": sum(bool(record["matching"]["success"]) for record in records),
        "mean_accepted_match_count": float(np.mean(accepted)) if accepted.size else None,
        "median_accepted_match_count": float(np.median(accepted)) if accepted.size else None,
        "mean_minimum_spatial_coverage": float(np.mean(coverage)) if coverage.size else None,
        "mean_total_detection_runtime_ms": float(np.mean(detection)) if detection.size else None,
        "mean_matching_runtime_ms": float(np.mean(matching)) if matching.size else None,
    }


def _summarize_sweep(records: list[dict[str, Any]], thresholds: list[float]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for threshold in thresholds:
        selected = [item for item in records if np.isclose(item["ratio_threshold"], threshold)]
        accepted = np.asarray([item["accepted_match_count"] for item in selected], dtype=float)
        coverage = np.asarray([item["minimum_spatial_coverage"] for item in selected], dtype=float)
        output.append(
            {
                "ratio_threshold": threshold,
                "case_count": len(selected),
                "successful_case_count": sum(bool(item["success"]) for item in selected),
                "mean_accepted_match_count": float(np.mean(accepted)) if accepted.size else None,
                "mean_minimum_spatial_coverage": float(np.mean(coverage)) if coverage.size else None,
            }
        )
    return output


def _findings(records: list[dict[str, Any]], sweep: list[dict[str, Any]]) -> dict[str, Any]:
    by_matches = sorted(records, key=lambda item: item["matching"]["accepted_match_count"])
    by_coverage = sorted(records, key=lambda item: item["matching"]["minimum_spatial_coverage"])
    strict = sweep[0]
    loose = sweep[-1]
    observations = [
        f"{by_matches[0]['case_id']} produced the fewest accepted SIFT matches at the provisional threshold with {by_matches[0]['matching']['accepted_match_count']} matches.",
        f"{by_matches[-1]['case_id']} produced the most accepted SIFT matches at the provisional threshold with {by_matches[-1]['matching']['accepted_match_count']} matches.",
        f"{by_coverage[0]['case_id']} had the lowest accepted-correspondence spatial coverage at {by_coverage[0]['matching']['minimum_spatial_coverage']:.3f}.",
        f"Relaxing the ratio threshold from {strict['ratio_threshold']:.2f} to {loose['ratio_threshold']:.2f} increased the mean accepted-match count from {strict['mean_accepted_match_count']:.1f} to {loose['mean_accepted_match_count']:.1f} in this development run.",
    ]
    return {
        "observations": observations,
        "interpretation": [
            "SIFT uses 128-dimensional floating-point descriptors and L2 distance, so its descriptor distances are not directly comparable with ORB Hamming distances.",
            "Accepted-match count and spatial coverage are descriptive inputs to later geometric estimation. They are not registration-accuracy metrics.",
            "The ratio threshold remains provisional because Stage 1 does not test geometric inliers or ground-truth registration error.",
        ],
        "limitations": [
            "Stage 1 evaluates SIFT detection, description, and correspondence filtering only. No RANSAC transform is estimated.",
            "The development subset is small and uses tracked monomodal images with controlled transformations and degradations.",
            "Runtime measurements are machine-dependent and should be replaced by target Windows measurements before final reporting.",
        ],
        "decision": "Carry ratio threshold 0.75 provisionally into SIFT Stage 2, where similarity and affine RANSAC will determine whether the retained correspondences are geometrically consistent.",
    }


def _validated_report_exists(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    validation = payload.get("local_validation")
    return bool(
        payload.get("status") == "complete"
        and isinstance(validation, dict)
        and validation.get("status") == "complete"
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for record in records:
        rows.append(
            {
                "case_id": record["case_id"],
                "source_id": record["source_id"],
                "operation": record["operation"],
                "fixed_keypoints": record["fixed_features"]["keypoint_count"],
                "moving_keypoints": record["moving_features"]["keypoint_count"],
                "accepted_matches": record["matching"]["accepted_match_count"],
                "minimum_spatial_coverage": record["matching"]["minimum_spatial_coverage"],
                "matching_runtime_ms": record["matching"]["runtime_ms"],
                "success": record["matching"]["success"],
                "failure_reason": record["matching"]["failure_reason"],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = _parse_args()
    config = load_config(_resolve(args.config))
    sift_config = _sift_config(config)
    matching = config["matching"]
    ratio_threshold = float(matching.get("ratio_threshold", 0.75))
    ratio_sweep = [float(value) for value in matching.get("ratio_sweep", [ratio_threshold])]
    minimum_matches = int(matching.get("minimum_matches", 8))
    maximum_distance = matching.get("maximum_distance")
    maximum_distance = None if maximum_distance is None else float(maximum_distance)
    maximum_drawn = int(matching.get("maximum_drawn_matches", 80))
    rows = int(config["sift"].get("spatial_grid", {}).get("rows", 4))
    columns = int(config["sift"].get("spatial_grid", {}).get("columns", 4))

    output_dir = _resolve(config["output"]["directory"])
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory already exists and is not empty: {output_dir}. Use --overwrite to replace it."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    sources = {
        source_id: np.asarray(load_image(_resolve(str(path)), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }

    records: list[dict[str, Any]] = []
    sweep_records: list[dict[str, Any]] = []
    print("Week 4 extension Stage 1: SIFT detection and L2 matching")
    print(f"Cases: {len(config['cases'])}")

    for index, case in enumerate(config["cases"], start=1):
        source_id = str(case["source"])
        fixed = sources[source_id]
        moving, metadata = _build_case(fixed, case)
        fixed_features = detect_sift_features(fixed, config=sift_config)
        moving_features = detect_sift_features(moving, config=sift_config)
        result = match_feature_knn_ratio(
            fixed_features,
            moving_features,
            metric="l2",
            ratio_threshold=ratio_threshold,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )

        fixed_metrics = _feature_metrics(fixed_features, rows=rows, columns=columns)
        moving_metrics = _feature_metrics(moving_features, rows=rows, columns=columns)
        match_metrics = _match_metrics(
            result, fixed_features, moving_features, rows=rows, columns=columns
        )
        record = {
            "case_id": str(case["id"]),
            "source_id": source_id,
            "operation": str(case["operation"]),
            "condition_metadata": metadata,
            "fixed_features": fixed_metrics,
            "moving_features": moving_metrics,
            "matching": match_metrics,
        }
        records.append(record)

        for threshold in ratio_sweep:
            sweep_result = match_feature_knn_ratio(
                fixed_features,
                moving_features,
                metric="l2",
                ratio_threshold=threshold,
                maximum_distance=maximum_distance,
                minimum_matches=minimum_matches,
            )
            metrics = _match_metrics(
                sweep_result, fixed_features, moving_features, rows=rows, columns=columns
            )
            sweep_records.append({"case_id": str(case["id"]), "ratio_threshold": threshold, **metrics})

        case_dir = output_dir / "cases" / str(case["id"])
        _save_rgb(case_dir / "fixed_keypoints.png", draw_sift_keypoints(fixed, fixed_features))
        _save_rgb(case_dir / "moving_keypoints.png", draw_sift_keypoints(moving, moving_features))
        _save_rgb(
            case_dir / "sift_ratio_matches.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                result.accepted_matches,
                maximum_drawn=maximum_drawn,
            ),
        )
        _save_distance_histogram(
            case_dir / "l2_distance_histogram.png",
            result,
            title=f"{case['id']} - SIFT L2 matching",
        )
        _save_coverage_plot(
            case_dir / "correspondence_coverage.png",
            fixed,
            moving,
            fixed_features,
            moving_features,
            result,
            rows=rows,
            columns=columns,
            title=f"{case['id']} - accepted SIFT correspondences",
        )

        state = "PASS" if result.success else "CHECK"
        print(
            f"{index:02d}/{len(config['cases']):02d} {case['id']:<24} "
            f"fixed={fixed_features.keypoint_count:4d} moving={moving_features.keypoint_count:4d} "
            f"matches={result.accepted_count:4d} cov={match_metrics['minimum_spatial_coverage']:.3f} {state}"
        )

    summary = _summarize(records)
    sweep_summary = _summarize_sweep(sweep_records, ratio_sweep)
    findings = _findings(records, sweep_summary)
    _save_ratio_sweep_plot(output_dir / "ratio_threshold_sweep.png", sweep_summary)

    with (output_dir / "stage01_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    with (output_dir / "ratio_sweep_results.json").open("w", encoding="utf-8") as handle:
        json.dump(sweep_records, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "stage01_results.csv", records)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "ratio_sweep": sweep_summary, "findings": findings}, handle, indent=2)
        handle.write("\n")

    report_payload = {
        "week": 4,
        "extension": "SIFT optional feature comparison",
        "stage": 1,
        "title": "SIFT detection, description, and L2 matching",
        "status": "implementation_complete_target_validation_pending",
        "scope": "SIFT feature extraction and descriptor filtering only; no RANSAC transform estimation",
        "configuration": {"sift": config["sift"], "matching": matching},
        "development_run": summary,
        "ratio_sweep": sweep_summary,
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "technical_note": "docs/SIFT_FEATURES.md",
        "experiment_summary": "docs/experiments/sift_stage01_summary.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the full test suite and SIFT Stage 1 experiment on the target Windows environment before marking this extension stage complete.",
        },
    }
    report_path = _resolve(config["output"]["report_snapshot"])
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print("Tracked SIFT Stage 1 report already contains completed target validation; preserving it.")
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nSIFT Stage 1 development run summary")
    print(f"Cases: {summary['case_count']}")
    print(f"Successful matching cases: {summary['successful_case_count']}/{summary['case_count']}")
    print(f"Mean accepted matches: {summary['mean_accepted_match_count']:.1f}")
    print(f"Mean minimum spatial coverage: {summary['mean_minimum_spatial_coverage']:.3f}")
    print(f"Mean total SIFT detection runtime: {summary['mean_total_detection_runtime_ms']:.3f} ms")
    print(f"Mean L2 matching runtime: {summary['mean_matching_runtime_ms']:.3f} ms")
    print(f"Tracked report ({report_action}): {config['output']['report_snapshot']}")


if __name__ == "__main__":
    main()
