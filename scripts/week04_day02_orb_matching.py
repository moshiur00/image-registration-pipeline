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
from image_registration.feature_matching import (
    FeatureMatchResult,
    correspondence_grid_coverage,
    correspondence_points,
    draw_feature_matches,
    match_distance_summary,
    match_orb_cross_check,
    match_orb_knn_ratio,
)
from image_registration.io import load_image
from image_registration.orb import ORBConfig, ORBFeatureResult, detect_orb_features
from image_registration.overlap import apply_field_of_view, rectangular_field_of_view_mask
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
    return np.asarray(pair.moving), {
        "operation": operation,
        "ground_truth_transform": ground_truth.as_dict(),
    }


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
            illumination_gradient(fixed, strength_fraction=strength, direction=direction)
        ), {
            "operation": operation,
            "strength_fraction": strength,
            "direction": direction,
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
    raise ValueError(f"Unsupported Day 17 operation: {operation}")


def _save_rgb(path: Path, image_rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(np.asarray(image_rgb, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"Could not write image: {path}")


def _save_distance_histogram(
    path: Path,
    result: FeatureMatchResult,
    *,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tentative = np.asarray([match.distance for match in result.tentative_matches], dtype=np.float64)
    accepted = np.asarray([match.distance for match in result.accepted_matches], dtype=np.float64)
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=140)
    if tentative.size:
        ax.hist(tentative, bins=30, alpha=0.55, label="tentative")
    if accepted.size:
        ax.hist(accepted, bins=30, alpha=0.65, label="accepted")
    ax.set_title(title)
    ax.set_xlabel("Hamming distance")
    ax.set_ylabel("Match count")
    if tentative.size or accepted.size:
        ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _save_correspondence_coverage(
    path: Path,
    fixed_image: np.ndarray,
    moving_image: np.ndarray,
    fixed_features: ORBFeatureResult,
    moving_features: ORBFeatureResult,
    result: FeatureMatchResult,
    *,
    rows: int,
    columns: int,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fixed_points, moving_points = correspondence_points(result, fixed_features, moving_features)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), dpi=140)
    for ax, image, points, label in (
        (axes[0], moving_image, moving_points, "moving"),
        (axes[1], fixed_image, fixed_points, "fixed"),
    ):
        ax.imshow(image, cmap="gray")
        if points.size:
            ax.scatter(points[:, 0], points[:, 1], s=10, alpha=0.7)
        height, width = image.shape[:2]
        for column in range(1, columns):
            ax.axvline(column * width / columns, linewidth=0.7, alpha=0.5)
        for row in range(1, rows):
            ax.axhline(row * height / rows, linewidth=0.7, alpha=0.5)
        ax.set_title(label)
        ax.set_xlim(0, width)
        ax.set_ylim(height, 0)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _match_metrics(
    result: FeatureMatchResult,
    fixed_features: ORBFeatureResult,
    moving_features: ORBFeatureResult,
    *,
    rows: int,
    columns: int,
) -> dict[str, Any]:
    coverage = correspondence_grid_coverage(
        result,
        fixed_features,
        moving_features,
        rows=rows,
        columns=columns,
    )
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


def _summarize(records: list[dict[str, Any]], strategy: str) -> dict[str, Any]:
    entries = [record[strategy] for record in records]
    successful = [entry for entry in entries if entry["success"]]
    accepted = np.asarray([entry["accepted_match_count"] for entry in entries], dtype=np.float64)
    coverage = np.asarray([entry["minimum_spatial_coverage"] for entry in entries], dtype=np.float64)
    runtimes = np.asarray([entry["runtime_ms"] for entry in entries], dtype=np.float64)
    median_distances = np.asarray(
        [entry["distance"]["median"] for entry in entries if entry["distance"]["median"] is not None],
        dtype=np.float64,
    )
    return {
        "case_count": len(entries),
        "successful_case_count": len(successful),
        "failed_case_count": len(entries) - len(successful),
        "mean_accepted_match_count": float(np.mean(accepted)) if accepted.size else None,
        "median_accepted_match_count": float(np.median(accepted)) if accepted.size else None,
        "mean_minimum_spatial_coverage": float(np.mean(coverage)) if coverage.size else None,
        "mean_matching_runtime_ms": float(np.mean(runtimes)) if runtimes.size else None,
        "mean_case_median_hamming_distance": (
            float(np.mean(median_distances)) if median_distances.size else None
        ),
    }


def _summarize_sweep(sweep_records: list[dict[str, Any]], thresholds: list[float]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for threshold in thresholds:
        selected = [
            record
            for record in sweep_records
            if np.isclose(float(record["ratio_threshold"]), threshold)
        ]
        accepted = np.asarray([record["accepted_match_count"] for record in selected], dtype=np.float64)
        coverage = np.asarray([record["minimum_spatial_coverage"] for record in selected], dtype=np.float64)
        summaries.append(
            {
                "ratio_threshold": threshold,
                "case_count": len(selected),
                "successful_case_count": sum(bool(record["success"]) for record in selected),
                "mean_accepted_match_count": float(np.mean(accepted)) if accepted.size else None,
                "mean_minimum_spatial_coverage": float(np.mean(coverage)) if coverage.size else None,
            }
        )
    return summaries


def _findings(records: list[dict[str, Any]], sweep_summary: list[dict[str, Any]]) -> dict[str, Any]:
    knn_entries = [(record["case_id"], record["knn_ratio"]) for record in records]
    cross_entries = [(record["case_id"], record["cross_check"]) for record in records]
    lowest_knn = min(knn_entries, key=lambda item: item[1]["accepted_match_count"])
    highest_knn = max(knn_entries, key=lambda item: item[1]["accepted_match_count"])
    lowest_coverage = min(knn_entries, key=lambda item: item[1]["minimum_spatial_coverage"])
    strict = sweep_summary[0]
    loose = sweep_summary[-1]

    observations = [
        (
            f"At the default ratio threshold, {highest_knn[0]} produced the largest accepted "
            f"KNN match count with {highest_knn[1]['accepted_match_count']} matches."
        ),
        (
            f"At the default ratio threshold, {lowest_knn[0]} produced the smallest accepted "
            f"KNN match count with {lowest_knn[1]['accepted_match_count']} matches."
        ),
        (
            f"The lowest accepted-correspondence grid coverage occurred in {lowest_coverage[0]} "
            f"with minimum fixed/moving coverage {lowest_coverage[1]['minimum_spatial_coverage']:.3f}."
        ),
        (
            f"Across the configured cases, relaxing the ratio threshold from "
            f"{strict['ratio_threshold']:.2f} to {loose['ratio_threshold']:.2f} changed the mean "
            f"accepted-match count from {strict['mean_accepted_match_count']:.1f} to "
            f"{loose['mean_accepted_match_count']:.1f}."
        ),
    ]
    interpretation = [
        "The ratio threshold controls a trade-off between retaining more correspondences and accepting more ambiguous descriptor matches.",
        "Accepted-match count and spatial coverage should be interpreted together. Many matches concentrated in a small region may still provide weak geometric support.",
        "Cross-check and ratio filtering apply different correspondence rules, so their match counts should not be interpreted as direct quality scores without geometric validation.",
    ]
    limitations = [
        "Day 17 evaluates descriptor correspondence filtering only. No RANSAC model is fitted and no registration transform is estimated.",
        "A descriptor match can pass the current filter and still be geometrically incorrect.",
        "The development findings are specific to the tracked images, ORB settings, matching thresholds, and selected controlled conditions.",
    ]
    return {
        "observations": observations,
        "interpretation": interpretation,
        "limitations": limitations,
        "decision": "Use the Day 17 correspondences as input to Day 18 RANSAC similarity estimation, where geometric inliers and outliers can be measured explicitly.",
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        for strategy in ("knn_ratio", "cross_check"):
            metrics = record[strategy]
            rows.append(
                {
                    "case_id": record["case_id"],
                    "source_id": record["source_id"],
                    "operation": record["operation"],
                    "strategy": strategy,
                    "success": metrics["success"],
                    "failure_reason": metrics["failure_reason"],
                    "fixed_keypoints": record["fixed_keypoints"],
                    "moving_keypoints": record["moving_keypoints"],
                    "tentative_matches": metrics["tentative_match_count"],
                    "accepted_matches": metrics["accepted_match_count"],
                    "acceptance_rate": metrics["acceptance_rate"],
                    "median_hamming_distance": metrics["distance"]["median"],
                    "fixed_match_coverage": metrics["fixed_spatial_coverage"],
                    "moving_match_coverage": metrics["moving_spatial_coverage"],
                    "minimum_match_coverage": metrics["minimum_spatial_coverage"],
                    "runtime_ms": metrics["runtime_ms"],
                }
            )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)



def _save_ratio_sweep_plot(path: Path, summaries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    thresholds = [float(item["ratio_threshold"]) for item in summaries]
    counts = [float(item["mean_accepted_match_count"]) for item in summaries]
    coverage = [float(item["mean_minimum_spatial_coverage"]) for item in summaries]
    fig, ax1 = plt.subplots(figsize=(7.2, 4.8), dpi=140)
    ax1.plot(thresholds, counts, marker="o", label="mean accepted matches")
    ax1.set_xlabel("KNN ratio threshold")
    ax1.set_ylabel("Mean accepted matches")
    ax2 = ax1.twinx()
    ax2.plot(thresholds, coverage, marker="s", linestyle="--", label="mean minimum coverage")
    ax2.set_ylabel("Mean minimum grid coverage")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], loc="upper left")
    ax1.set_title("Ratio threshold sweep")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _save_strategy_comparison_plot(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [record["case_id"] for record in records]
    knn_counts = [record["knn_ratio"]["accepted_match_count"] for record in records]
    cross_counts = [record["cross_check"]["accepted_match_count"] for record in records]
    positions = np.arange(len(labels), dtype=np.float64)
    width = 0.38
    fig, ax = plt.subplots(figsize=(10.5, 5.2), dpi=140)
    ax.bar(positions - width / 2.0, knn_counts, width=width, label="KNN ratio")
    ax.bar(positions + width / 2.0, cross_counts, width=width, label="cross-check")
    ax.set_xticks(positions, labels, rotation=35, ha="right")
    ax.set_ylabel("Accepted matches")
    ax.set_title("Accepted descriptor matches by case")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

def _validated_report_exists(path: Path) -> bool:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day 17 ORB descriptor-matching experiment.")
    parser.add_argument(
        "--config",
        default="configs/week04_day02_orb_matching.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    args = parser.parse_args()

    config = load_config(_resolve(args.config))
    orb_config = _orb_config(config)
    orb_config.validate()
    matching = config["matching"]
    minimum_matches = int(matching.get("minimum_matches", 8))
    ratio_threshold = float(matching.get("knn_ratio_threshold", 0.75))
    ratio_sweep = [float(value) for value in matching.get("ratio_sweep", [ratio_threshold])]
    maximum_distance_value = matching.get("maximum_distance")
    maximum_distance = None if maximum_distance_value is None else float(maximum_distance_value)
    norm = str(matching.get("norm", "hamming")).strip().lower()
    grid = matching.get("spatial_grid", {})
    rows = int(grid.get("rows", 4))
    columns = int(grid.get("columns", 4))
    maximum_drawn = int(matching.get("maximum_drawn_matches", 80))

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
    sweep_records: list[dict[str, Any]] = []
    for index, case_raw in enumerate(config["cases"], start=1):
        case = dict(case_raw)
        fixed = sources[str(case["source"])]
        moving, condition_metadata = _build_case(fixed, case)
        fixed_features = detect_orb_features(fixed, config=orb_config)
        moving_features = detect_orb_features(moving, config=orb_config)

        knn_result = match_orb_knn_ratio(
            fixed_features,
            moving_features,
            ratio_threshold=ratio_threshold,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
            norm=norm,
        )
        cross_result = match_orb_cross_check(
            fixed_features,
            moving_features,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
            norm=norm,
        )
        knn_metrics = _match_metrics(
            knn_result, fixed_features, moving_features, rows=rows, columns=columns
        )
        cross_metrics = _match_metrics(
            cross_result, fixed_features, moving_features, rows=rows, columns=columns
        )
        record = {
            "case_id": str(case["id"]),
            "source_id": str(case["source"]),
            "operation": str(case["operation"]),
            "condition_metadata": condition_metadata,
            "fixed_keypoints": int(fixed_features.keypoint_count),
            "moving_keypoints": int(moving_features.keypoint_count),
            "knn_ratio": knn_metrics,
            "cross_check": cross_metrics,
        }
        records.append(record)

        for threshold in ratio_sweep:
            sweep_result = match_orb_knn_ratio(
                fixed_features,
                moving_features,
                ratio_threshold=threshold,
                maximum_distance=maximum_distance,
                minimum_matches=minimum_matches,
                norm=norm,
            )
            sweep_metrics = _match_metrics(
                sweep_result, fixed_features, moving_features, rows=rows, columns=columns
            )
            sweep_records.append(
                {
                    "case_id": str(case["id"]),
                    "ratio_threshold": threshold,
                    **sweep_metrics,
                }
            )

        case_dir = output_dir / "cases" / str(case["id"])
        _save_rgb(
            case_dir / "knn_tentative_matches.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                knn_result.tentative_matches,
                maximum_drawn=maximum_drawn,
            ),
        )
        _save_rgb(
            case_dir / "knn_ratio_matches.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                knn_result.accepted_matches,
                maximum_drawn=maximum_drawn,
            ),
        )
        _save_rgb(
            case_dir / "cross_check_matches.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                cross_result.accepted_matches,
                maximum_drawn=maximum_drawn,
            ),
        )
        _save_distance_histogram(
            case_dir / "knn_distance_histogram.png",
            knn_result,
            title=f"{case['id']} - KNN ratio matching",
        )
        _save_correspondence_coverage(
            case_dir / "knn_correspondence_coverage.png",
            fixed,
            moving,
            fixed_features,
            moving_features,
            knn_result,
            rows=rows,
            columns=columns,
            title=f"{case['id']} - accepted KNN correspondences",
        )

        status = "PASS" if knn_result.success and cross_result.success else "CHECK"
        print(
            f"{index:02d}/{len(config['cases']):02d} {case['id']:<24} "
            f"KNN={knn_result.accepted_count:4d} cov={knn_metrics['minimum_spatial_coverage']:.3f}  "
            f"cross={cross_result.accepted_count:4d} cov={cross_metrics['minimum_spatial_coverage']:.3f}  "
            f"{status}"
        )

    knn_summary = _summarize(records, "knn_ratio")
    cross_summary = _summarize(records, "cross_check")
    sweep_summary = _summarize_sweep(sweep_records, ratio_sweep)
    findings = _findings(records, sweep_summary)
    _save_ratio_sweep_plot(output_dir / "ratio_threshold_sweep.png", sweep_summary)
    _save_strategy_comparison_plot(output_dir / "strategy_match_count_comparison.png", records)

    with (output_dir / "matching_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    with (output_dir / "ratio_sweep_results.json").open("w", encoding="utf-8") as handle:
        json.dump(sweep_records, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "matching_results.csv", records)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "knn_ratio": knn_summary,
                "cross_check": cross_summary,
                "ratio_sweep": sweep_summary,
                "findings": findings,
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    report_payload = {
        "week": 4,
        "global_day": 17,
        "week_day": 2,
        "title": "ORB descriptor matching and correspondence filtering",
        "status": "implementation_complete_local_validation_pending",
        "scope": "descriptor correspondence filtering only; no RANSAC transform estimation",
        "configuration": {
            "orb": config["orb"],
            "matching": matching,
        },
        "development_run": {
            "knn_ratio": knn_summary,
            "cross_check": cross_summary,
            "ratio_sweep": sweep_summary,
        },
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "daily_summary": "docs/daily/day_17_summary.md",
        "technical_note": "docs/FEATURE_MATCHING.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the full test suite and Day 17 experiment on the target Windows environment before marking Day 17 complete.",
        },
    }
    report_path = PROJECT_ROOT / "reports/week04_day02_orb_matching.json"
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print("Tracked Day 17 report already contains completed target validation; preserving it.")
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nDay 17 development run summary")
    print(
        f"KNN ratio {ratio_threshold:.2f}: "
        f"{knn_summary['successful_case_count']}/{knn_summary['case_count']} cases with at least "
        f"{minimum_matches} accepted matches"
    )
    print(f"Mean KNN accepted matches: {knn_summary['mean_accepted_match_count']:.1f}")
    print(f"Mean KNN minimum spatial coverage: {knn_summary['mean_minimum_spatial_coverage']:.3f}")
    print(
        f"Cross-check: {cross_summary['successful_case_count']}/{cross_summary['case_count']} cases "
        f"with at least {minimum_matches} accepted matches"
    )
    print(f"Mean cross-check accepted matches: {cross_summary['mean_accepted_match_count']:.1f}")
    print(f"Mean cross-check minimum spatial coverage: {cross_summary['mean_minimum_spatial_coverage']:.3f}")
    print(f"Tracked report ({report_action}): reports/week04_day02_orb_matching.json")


if __name__ == "__main__":
    main()
