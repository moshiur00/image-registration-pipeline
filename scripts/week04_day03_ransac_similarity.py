from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.degradations import gaussian_blur, illumination_gradient
from image_registration.feature_matching import (
    FeatureMatch,
    FeatureMatchResult,
    draw_feature_matches,
    match_orb_knn_ratio,
)
from image_registration.io import load_image
from image_registration.orb import ORBConfig, detect_orb_features
from image_registration.ransac import (
    RANSACSimilarityResult,
    estimate_similarity_ransac_from_matches,
    residual_summary,
    similarity_scale,
)
from image_registration.registration_metrics import (
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import (
    GroundTruthTransform,
    default_control_points,
    generate_synthetic_pair,
    image_center,
)
from image_registration.transforms import invert_transform, similarity_matrix
from image_registration.visualization import edge_overlay, save_comparison_figure, save_rgb_image
from image_registration.warping import warp_image


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


def _build_similarity_pair(
    fixed: np.ndarray,
    case: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    center = image_center(fixed.shape)
    scale = float(case.get("scale", 1.0))
    angle = float(case.get("angle_degrees", 0.0))
    tx = float(case.get("tx", 0.0))
    ty = float(case.get("ty", 0.0))
    matrix = similarity_matrix(scale, angle, tx=tx, ty=ty, center=center)
    ground_truth = GroundTruthTransform(
        transform_type="similarity",
        parameters={
            "scale": scale,
            "angle_degrees": angle,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
        },
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )
    pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    moving = np.asarray(pair.moving)

    postprocess = case.get("postprocess")
    postprocess_record: dict[str, Any] | None = None
    if isinstance(postprocess, dict):
        kind = str(postprocess.get("type", "")).strip().lower()
        if kind == "gaussian_blur":
            sigma = float(postprocess.get("sigma", 1.0))
            moving = np.asarray(gaussian_blur(moving, sigma=sigma))
            postprocess_record = {"type": kind, "sigma": sigma}
        elif kind == "illumination_gradient":
            strength = float(postprocess.get("strength_fraction", 0.25))
            direction = str(postprocess.get("direction", "horizontal"))
            moving = np.asarray(
                illumination_gradient(
                    moving,
                    strength_fraction=strength,
                    direction=direction,
                )
            )
            postprocess_record = {
                "type": kind,
                "strength_fraction": strength,
                "direction": direction,
            }
        else:
            raise ValueError(f"Unsupported Day 18 postprocess type: {kind}")

    metadata = ground_truth.as_dict()
    metadata["postprocess"] = postprocess_record
    return moving, matrix, np.asarray(pair.control_points_moving), metadata


def _ransac_kwargs(config: dict[str, Any], seed: int) -> dict[str, Any]:
    section = config["ransac"]
    return {
        "reprojection_threshold": float(section.get("reprojection_threshold", 3.0)),
        "confidence": float(section.get("confidence", 0.99)),
        "max_trials": int(section.get("max_trials", 2000)),
        "refine_iterations": int(section.get("refine_iterations", 10)),
        "minimum_matches": int(config["matching"].get("minimum_matches", 8)),
        "minimum_inliers": int(section.get("minimum_inliers", 8)),
        "minimum_inlier_ratio": float(section.get("minimum_inlier_ratio", 0.25)),
        "random_seed": int(seed),
    }


def _geometric_metrics(
    result: RANSACSimilarityResult,
    ground_truth: np.ndarray,
    control_points_moving: np.ndarray,
    center: np.ndarray,
    validation: dict[str, Any],
) -> dict[str, Any]:
    if result.estimated_transform is None:
        return {
            "tre_pixels": None,
            "rotation_error_degrees": None,
            "scale_error": None,
            "translation_error_pixels": None,
            "within_tolerance": False,
        }

    estimated = result.estimated_transform
    tre = mean_tre_pixels(ground_truth, estimated, control_points_moving)
    rotation_error = rotation_error_degrees(ground_truth, estimated)
    scale_error = abs(similarity_scale(estimated) - similarity_scale(ground_truth))
    translation_error = centered_translation_error_pixels(ground_truth, estimated, center)
    within = bool(
        tre <= float(validation["tre_threshold_pixels"])
        and rotation_error <= float(validation["rotation_error_threshold_degrees"])
        and scale_error <= float(validation["scale_error_threshold"])
        and translation_error <= float(validation["translation_error_threshold_pixels"])
    )
    return {
        "tre_pixels": float(tre),
        "rotation_error_degrees": float(rotation_error),
        "scale_error": float(scale_error),
        "translation_error_pixels": float(translation_error),
        "within_tolerance": within,
    }


def _ransac_record(result: RANSACSimilarityResult) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "input_match_count": int(result.input_match_count),
        "inlier_count": int(result.inlier_count),
        "outlier_count": int(result.outlier_count),
        "inlier_ratio": result.inlier_ratio,
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "reprojection_residuals": residual_summary(result),
        "estimated_transform": (
            result.estimated_transform.tolist() if result.estimated_transform is not None else None
        ),
    }


def _split_matches(
    matches: tuple[FeatureMatch, ...], mask: np.ndarray
) -> tuple[tuple[FeatureMatch, ...], tuple[FeatureMatch, ...]]:
    inliers = tuple(match for match, keep in zip(matches, mask, strict=True) if bool(keep))
    outliers = tuple(match for match, keep in zip(matches, mask, strict=True) if not bool(keep))
    return inliers, outliers


def _save_match_views(
    case_dir: Path,
    fixed: np.ndarray,
    moving: np.ndarray,
    fixed_features: Any,
    moving_features: Any,
    matching: FeatureMatchResult,
    ransac: RANSACSimilarityResult,
    maximum_drawn: int,
) -> None:
    if ransac.inlier_mask.size != matching.accepted_count:
        return
    inliers, outliers = _split_matches(matching.accepted_matches, ransac.inlier_mask)
    save_rgb_image(
        case_dir / "ransac_inliers.png",
        draw_feature_matches(
            fixed,
            moving,
            fixed_features,
            moving_features,
            inliers,
            maximum_drawn=maximum_drawn,
        ).astype(np.float32)
        / 255.0,
    )
    if outliers:
        save_rgb_image(
            case_dir / "ransac_outliers.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                outliers,
                maximum_drawn=maximum_drawn,
            ).astype(np.float32)
            / 255.0,
        )


def _save_residual_plot(path: Path, result: RANSACSimilarityResult, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.0, 4.6), dpi=140)
    positions = np.arange(result.input_match_count)
    if result.reprojection_residuals.size:
        ax.scatter(
            positions[result.inlier_mask],
            result.reprojection_residuals[result.inlier_mask],
            s=18,
            label="RANSAC inlier",
        )
        ax.scatter(
            positions[~result.inlier_mask],
            result.reprojection_residuals[~result.inlier_mask],
            s=18,
            label="RANSAC outlier",
        )
    ax.axhline(result.reprojection_threshold, linestyle="--", label="configured threshold")
    ax.set_xlabel("Accepted descriptor match index")
    ax.set_ylabel("Reprojection residual (px)")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _inject_outlier_matches(
    result: FeatureMatchResult,
    *,
    fixed_keypoint_count: int,
    fraction: float,
    seed: int,
) -> tuple[FeatureMatchResult, list[int]]:
    if not 0.0 < fraction < 1.0:
        raise ValueError("Outlier injection fraction must be in the range (0, 1).")
    if result.accepted_count == 0:
        return result, []
    rng = np.random.default_rng(seed)
    count = max(1, int(round(result.accepted_count * fraction)))
    selected = sorted(rng.choice(result.accepted_count, size=count, replace=False).tolist())
    selected_set = set(selected)
    modified: list[FeatureMatch] = []
    for index, match in enumerate(result.accepted_matches):
        if index not in selected_set:
            modified.append(match)
            continue
        candidate = int(rng.integers(0, fixed_keypoint_count))
        if fixed_keypoint_count > 1 and candidate == match.fixed_index:
            candidate = (candidate + 1) % fixed_keypoint_count
        modified.append(replace(match, fixed_index=candidate))

    injected = FeatureMatchResult(
        strategy=result.strategy,
        tentative_matches=result.tentative_matches,
        accepted_matches=tuple(modified),
        success=result.success,
        runtime_seconds=result.runtime_seconds,
        failure_reason=result.failure_reason,
        ratio_threshold=result.ratio_threshold,
        maximum_distance=result.maximum_distance,
        minimum_matches=result.minimum_matches,
    )
    return injected, selected


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in records if record["ransac"]["success"]]
    correct = [record for record in records if record["geometry"]["within_tolerance"]]
    inlier_ratios = np.asarray(
        [record["ransac"]["inlier_ratio"] for record in successful], dtype=np.float64
    )
    tres = np.asarray(
        [record["geometry"]["tre_pixels"] for record in records if record["geometry"]["tre_pixels"] is not None],
        dtype=np.float64,
    )
    runtimes = np.asarray(
        [record["ransac"]["runtime_ms"] for record in records], dtype=np.float64
    )
    return {
        "case_count": len(records),
        "ransac_success_count": len(successful),
        "within_tolerance_count": len(correct),
        "failed_count": len(records) - len(successful),
        "mean_inlier_ratio": float(np.mean(inlier_ratios)) if inlier_ratios.size else None,
        "median_tre_pixels": float(np.median(tres)) if tres.size else None,
        "maximum_tre_pixels": float(np.max(tres)) if tres.size else None,
        "mean_ransac_runtime_ms": float(np.mean(runtimes)) if runtimes.size else None,
    }


def _findings(records: list[dict[str, Any]], outlier_experiment: dict[str, Any] | None) -> dict[str, Any]:
    valid_tre = [
        (record["case_id"], record["geometry"]["tre_pixels"])
        for record in records
        if record["geometry"]["tre_pixels"] is not None
    ]
    best = min(valid_tre, key=lambda item: item[1]) if valid_tre else None
    worst = max(valid_tre, key=lambda item: item[1]) if valid_tre else None
    lowest_ratio = min(
        (
            (record["case_id"], record["ransac"]["inlier_ratio"])
            for record in records
            if record["ransac"]["inlier_ratio"] is not None
        ),
        key=lambda item: item[1],
        default=None,
    )

    observations: list[str] = []
    if best is not None:
        observations.append(f"The smallest geometric error occurred in {best[0]} with TRE {best[1]:.3f} px.")
    if worst is not None:
        observations.append(f"The largest geometric error occurred in {worst[0]} with TRE {worst[1]:.3f} px.")
    if lowest_ratio is not None:
        observations.append(
            f"The lowest RANSAC inlier ratio occurred in {lowest_ratio[0]} at {lowest_ratio[1]:.3f}."
        )
    if outlier_experiment is not None:
        observations.append(
            f"The controlled outlier experiment injected {outlier_experiment['injected_count']} incorrect correspondences; "
            f"RANSAC rejected {outlier_experiment['injected_rejected_count']} of those injected correspondences."
        )

    return {
        "observations": observations,
        "interpretation": [
            "RANSAC adds a geometric consistency test after descriptor filtering. Accepted ORB matches are not automatically treated as correct correspondences.",
            "Inlier ratio, reprojection residuals, and ground-truth TRE describe different parts of the result and should be reported together.",
            "A successful RANSAC call is not sufficient evidence of correct registration. Geometric correctness is evaluated separately against the known transform.",
        ],
        "limitations": [
            "Day 18 evaluates only the similarity model. General affine estimation and degeneracy checks are reserved for Day 19.",
            "The current development thresholds are working thresholds for controlled experiments and are not final benchmark thresholds.",
            "The findings are specific to the tracked images, ORB configuration, ratio filter, RANSAC settings, and selected controlled transformations.",
        ],
        "decision": "Proceed to Day 19 with affine RANSAC, degeneracy checks, texture stratification, and threshold sweeps while retaining the Day 18 similarity baseline.",
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "case_id": record["case_id"],
                "source_id": record["source_id"],
                "accepted_matches": record["matching"]["accepted_match_count"],
                "ransac_success": record["ransac"]["success"],
                "inlier_count": record["ransac"]["inlier_count"],
                "outlier_count": record["ransac"]["outlier_count"],
                "inlier_ratio": record["ransac"]["inlier_ratio"],
                "inlier_median_reprojection_px": record["ransac"]["reprojection_residuals"]["inlier_median"],
                "tre_pixels": record["geometry"]["tre_pixels"],
                "rotation_error_degrees": record["geometry"]["rotation_error_degrees"],
                "scale_error": record["geometry"]["scale_error"],
                "translation_error_pixels": record["geometry"]["translation_error_pixels"],
                "within_tolerance": record["geometry"]["within_tolerance"],
                "ransac_runtime_ms": record["ransac"]["runtime_ms"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _validated_report_exists(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    local_validation = payload.get("local_validation")
    return bool(
        payload.get("status") == "complete"
        and isinstance(local_validation, dict)
        and local_validation.get("status") == "complete"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day 18 ORB + RANSAC similarity experiment.")
    parser.add_argument(
        "--config",
        default="configs/week04_day03_ransac_similarity.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output directory.")
    args = parser.parse_args()

    from image_registration.config import load_config

    config = load_config(_resolve(args.config))
    seed = int(config["experiment"].get("seed", 42))
    orb_config = _orb_config(config)
    orb_config.validate()
    matching_cfg = config["matching"]
    ratio_threshold = float(matching_cfg.get("knn_ratio_threshold", 0.75))
    maximum_distance_value = matching_cfg.get("maximum_distance")
    maximum_distance = None if maximum_distance_value is None else float(maximum_distance_value)
    minimum_matches = int(matching_cfg.get("minimum_matches", 8))
    norm = str(matching_cfg.get("norm", "hamming")).strip().lower()
    maximum_drawn = int(matching_cfg.get("maximum_drawn_matches", 100))
    validation = config["validation"]
    ransac_kwargs = _ransac_kwargs(config, seed)

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
    context_by_case: dict[str, tuple[Any, ...]] = {}
    for index, case_raw in enumerate(config["cases"], start=1):
        case = dict(case_raw)
        fixed = sources[str(case["source"])]
        moving, ground_truth, control_points_moving, metadata = _build_similarity_pair(fixed, case)
        fixed_features = detect_orb_features(fixed, config=orb_config)
        moving_features = detect_orb_features(moving, config=orb_config)
        matching = match_orb_knn_ratio(
            fixed_features,
            moving_features,
            ratio_threshold=ratio_threshold,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
            norm=norm,
        )
        ransac = estimate_similarity_ransac_from_matches(
            matching, fixed_features, moving_features, **ransac_kwargs
        )
        center = image_center(fixed.shape)
        geometry = _geometric_metrics(
            ransac, ground_truth, control_points_moving, center, validation
        )
        ransac_metrics = _ransac_record(ransac)
        record = {
            "case_id": str(case["id"]),
            "source_id": str(case["source"]),
            "condition_metadata": metadata,
            "matching": {
                "success": bool(matching.success),
                "failure_reason": matching.failure_reason,
                "accepted_match_count": int(matching.accepted_count),
                "tentative_match_count": int(matching.tentative_count),
                "ratio_threshold": matching.ratio_threshold,
            },
            "ransac": ransac_metrics,
            "geometry": geometry,
            "ground_truth_transform": ground_truth.tolist(),
        }
        records.append(record)
        context_by_case[str(case["id"])] = (
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching,
            ransac,
            ground_truth,
            control_points_moving,
        )

        case_dir = output_dir / "cases" / str(case["id"])
        case_dir.mkdir(parents=True, exist_ok=True)
        _save_match_views(
            case_dir,
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching,
            ransac,
            maximum_drawn,
        )
        _save_residual_plot(case_dir / "reprojection_residuals.png", ransac, str(case["id"]))
        if ransac.estimated_transform is not None:
            registered = warp_image(
                moving,
                ransac.estimated_transform,
                output_shape=fixed.shape[:2],
                interpolation="linear",
            )
            save_comparison_figure(
                fixed,
                moving,
                registered,
                case_dir / "registration_comparison.png",
                title=f"{case['id']} - ORB + RANSAC similarity",
            )
            save_rgb_image(
                case_dir / "edge_overlay.png",
                edge_overlay(fixed, registered),
            )

        status = "PASS" if ransac.success and geometry["within_tolerance"] else "CHECK"
        tre_text = "n/a" if geometry["tre_pixels"] is None else f"{geometry['tre_pixels']:.3f}"
        ratio_text = "n/a" if ransac.inlier_ratio is None else f"{ransac.inlier_ratio:.3f}"
        print(
            f"{index:02d}/{len(config['cases']):02d} {case['id']:<32} "
            f"matches={matching.accepted_count:4d} inliers={ransac.inlier_count:4d} "
            f"ratio={ratio_text:>5} TRE={tre_text:>7}  {status}"
        )

    outlier_experiment: dict[str, Any] | None = None
    injection = config.get("outlier_injection", {})
    if isinstance(injection, dict) and bool(injection.get("enabled", False)):
        target_id = str(injection["case_id"])
        if target_id not in context_by_case:
            raise ValueError(f"Outlier injection case not found: {target_id}")
        (
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching,
            _clean_ransac,
            ground_truth,
            control_points_moving,
        ) = context_by_case[target_id]
        injected_matching, injected_indices = _inject_outlier_matches(
            matching,
            fixed_keypoint_count=fixed_features.keypoint_count,
            fraction=float(injection.get("fraction", 0.30)),
            seed=int(injection.get("random_seed", seed)),
        )
        injected_ransac = estimate_similarity_ransac_from_matches(
            injected_matching,
            fixed_features,
            moving_features,
            **ransac_kwargs,
        )
        geometry = _geometric_metrics(
            injected_ransac,
            ground_truth,
            control_points_moving,
            image_center(fixed.shape),
            validation,
        )
        rejected_injected = sum(
            not bool(injected_ransac.inlier_mask[index])
            for index in injected_indices
            if index < injected_ransac.inlier_mask.size
        )
        outlier_experiment = {
            "case_id": target_id,
            "injected_fraction": float(injection.get("fraction", 0.30)),
            "injected_count": len(injected_indices),
            "injected_rejected_count": int(rejected_injected),
            "injected_rejection_rate": (
                float(rejected_injected / len(injected_indices)) if injected_indices else None
            ),
            "ransac": _ransac_record(injected_ransac),
            "geometry": geometry,
        }
        injection_dir = output_dir / "outlier_injection"
        injection_dir.mkdir(parents=True, exist_ok=True)
        _save_match_views(
            injection_dir,
            fixed,
            moving,
            fixed_features,
            moving_features,
            injected_matching,
            injected_ransac,
            maximum_drawn,
        )
        _save_residual_plot(
            injection_dir / "reprojection_residuals.png",
            injected_ransac,
            f"{target_id} - injected correspondence outliers",
        )

    summary = _summarize(records)
    findings = _findings(records, outlier_experiment)
    with (output_dir / "ransac_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "ransac_results.csv", records)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": summary,
                "outlier_injection": outlier_experiment,
                "findings": findings,
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    report_payload = {
        "week": 4,
        "global_day": 18,
        "week_day": 3,
        "title": "ORB + RANSAC similarity estimation and outlier rejection",
        "status": "implementation_complete_local_validation_pending",
        "scope": "similarity transform estimation from ORB correspondences with RANSAC",
        "configuration": {
            "orb": config["orb"],
            "matching": matching_cfg,
            "ransac": config["ransac"],
            "validation": validation,
        },
        "development_run": summary,
        "outlier_injection": outlier_experiment,
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "daily_summary": "docs/daily/day_18_summary.md",
        "technical_note": "docs/RANSAC_SIMILARITY.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the full test suite and Day 18 experiment on the target Windows environment before marking Day 18 complete.",
        },
    }
    report_path = PROJECT_ROOT / "reports/week04_day03_ransac_similarity.json"
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print("Tracked Day 18 report already contains completed target validation; preserving it.")
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nDay 18 development run summary")
    print(
        f"RANSAC success: {summary['ransac_success_count']}/{summary['case_count']} cases"
    )
    print(
        f"Within development tolerances: {summary['within_tolerance_count']}/{summary['case_count']} cases"
    )
    print(f"Mean inlier ratio: {summary['mean_inlier_ratio']:.3f}")
    print(f"Median TRE: {summary['median_tre_pixels']:.3f} px")
    print(f"Maximum TRE: {summary['maximum_tre_pixels']:.3f} px")
    if outlier_experiment is not None:
        print(
            "Injected outliers rejected: "
            f"{outlier_experiment['injected_rejected_count']}/{outlier_experiment['injected_count']}"
        )
        if outlier_experiment["geometry"]["tre_pixels"] is not None:
            print(
                "Outlier-injection TRE: "
                f"{outlier_experiment['geometry']['tre_pixels']:.3f} px"
            )
    print(f"Tracked report ({report_action}): reports/week04_day03_ransac_similarity.json")


if __name__ == "__main__":
    main()
