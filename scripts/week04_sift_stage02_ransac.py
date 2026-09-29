from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from image_registration.config import load_config
from image_registration.affine_ransac import (
    RANSACAffineResult,
    estimate_affine_ransac_from_matches,
    residual_summary as affine_residual_summary,
)
from image_registration.degradations import gaussian_blur
from image_registration.feature_matching import (
    FeatureMatch,
    FeatureMatchResult,
    correspondence_grid_coverage,
    draw_feature_matches,
    match_feature_knn_ratio,
)
from image_registration.io import load_image
from image_registration.overlap import apply_field_of_view, rectangular_field_of_view_mask
from image_registration.ransac import (
    RANSACSimilarityResult,
    estimate_similarity_ransac_from_matches,
    residual_summary as similarity_residual_summary,
    similarity_scale,
)
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.sift import SIFTConfig, SIFTFeatureResult, detect_sift_features
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import affine_matrix, invert_transform, rotation_matrix, similarity_matrix
from image_registration.visualization import edge_overlay, save_comparison_figure, save_rgb_image
from image_registration.warping import warp_image


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Week 4 SIFT extension Stage 2.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _sift_config(config: dict[str, Any]) -> SIFTConfig:
    values = config["sift"]
    return SIFTConfig(
        n_features=int(values.get("n_features", 800)),
        n_octave_layers=int(values.get("n_octave_layers", 3)),
        contrast_threshold=float(values.get("contrast_threshold", 0.04)),
        edge_threshold=float(values.get("edge_threshold", 10.0)),
        sigma=float(values.get("sigma", 1.6)),
    )


def _load_sources(config: dict[str, Any]) -> dict[str, np.ndarray]:
    sources = {
        str(source_id): np.asarray(load_image(_resolve(str(path)), color_mode="grayscale").array)
        for source_id, path in config["sources"].items()
    }
    for source_id, specification in config.get("generated_sources", {}).items():
        spec = dict(specification)
        kind = str(spec.get("type", "")).strip().lower()
        if kind == "gaussian_blur":
            base = sources[str(spec["base_source"])]
            sources[str(source_id)] = np.asarray(
                gaussian_blur(base, sigma=float(spec.get("sigma", 8.0)))
            )
        elif kind == "checkerboard":
            height = int(spec.get("height", 512))
            width = int(spec.get("width", 512))
            block = int(spec.get("block_size", 32))
            yy, xx = np.indices((height, width))
            sources[str(source_id)] = (((xx // block + yy // block) % 2) * 255).astype(np.uint8)
        else:
            raise ValueError(f"Unsupported generated source type: {kind}")
    return sources


def _apply_postprocess(moving: np.ndarray, postprocess: Any) -> tuple[np.ndarray, dict[str, Any] | None]:
    if not isinstance(postprocess, dict):
        return moving, None
    kind = str(postprocess.get("type", "")).strip().lower()
    if kind == "gaussian_blur":
        sigma = float(postprocess.get("sigma", 2.0))
        return np.asarray(gaussian_blur(moving, sigma=sigma)), {"type": kind, "sigma": sigma}
    if kind == "restricted_fov":
        mask = rectangular_field_of_view_mask(
            moving.shape,
            width_fraction=float(postprocess.get("width_fraction", 0.70)),
            height_fraction=float(postprocess.get("height_fraction", 0.75)),
            center_x_fraction=float(postprocess.get("center_x_fraction", 0.50)),
            center_y_fraction=float(postprocess.get("center_y_fraction", 0.50)),
        )
        result = apply_field_of_view(moving, mask, fill_value=float(postprocess.get("fill_value", 0.0)))
        return np.asarray(result), {
            "type": kind,
            "width_fraction": float(postprocess.get("width_fraction", 0.70)),
            "height_fraction": float(postprocess.get("height_fraction", 0.75)),
            "center_x_fraction": float(postprocess.get("center_x_fraction", 0.50)),
            "center_y_fraction": float(postprocess.get("center_y_fraction", 0.50)),
            "visible_fraction": float(np.mean(mask)),
        }
    raise ValueError(f"Unsupported Stage 2 postprocess type: {kind}")


def _build_pair(
    fixed: np.ndarray,
    case: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    model = str(case["model"]).strip().lower()
    center = image_center(fixed.shape)
    if model == "similarity":
        scale = float(case.get("scale", 1.0))
        angle = float(case.get("angle_degrees", 0.0))
        tx = float(case.get("tx", 0.0))
        ty = float(case.get("ty", 0.0))
        matrix = similarity_matrix(scale, angle, tx=tx, ty=ty, center=center)
        parameters = {
            "scale": scale,
            "angle_degrees": angle,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
        }
    elif model == "affine":
        angle = float(case.get("angle_degrees", 0.0))
        scale_x = float(case.get("scale_x", 1.0))
        scale_y = float(case.get("scale_y", 1.0))
        shear_x = float(case.get("shear_x", 0.0))
        tx = float(case.get("tx", 0.0))
        ty = float(case.get("ty", 0.0))
        rotation = rotation_matrix(angle)[:2, :2]
        shear = np.asarray([[1.0, shear_x], [0.0, 1.0]], dtype=np.float64)
        scale = np.asarray([[scale_x, 0.0], [0.0, scale_y]], dtype=np.float64)
        linear = rotation @ shear @ scale
        matrix = affine_matrix(linear, tx=tx, ty=ty, center=center)
        parameters = {
            "angle_degrees": angle,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "shear_x": shear_x,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
            "linear": linear.tolist(),
        }
    else:
        raise ValueError("Stage 2 model must be similarity or affine.")

    ground_truth = GroundTruthTransform(
        transform_type=model,
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )
    pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    moving, postprocess = _apply_postprocess(np.asarray(pair.moving), case.get("postprocess"))
    metadata = ground_truth.as_dict()
    metadata["postprocess"] = postprocess
    return moving, matrix, np.asarray(pair.control_points_moving), center, metadata


def _similarity_kwargs(config: dict[str, Any], seed: int) -> dict[str, Any]:
    section = config["ransac_similarity"]
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


def _affine_kwargs(config: dict[str, Any], seed: int) -> dict[str, Any]:
    section = config["ransac_affine"]
    plausibility = section.get("plausibility", {})
    return {
        "reprojection_threshold": float(section.get("reprojection_threshold", 3.0)),
        "confidence": float(section.get("confidence", 0.99)),
        "max_trials": int(section.get("max_trials", 3000)),
        "refine_iterations": int(section.get("refine_iterations", 10)),
        "minimum_matches": int(config["matching"].get("minimum_matches", 8)),
        "minimum_inliers": int(section.get("minimum_inliers", 8)),
        "minimum_inlier_ratio": float(section.get("minimum_inlier_ratio", 0.25)),
        "grid_rows": int(section.get("grid_rows", 4)),
        "grid_cols": int(section.get("grid_cols", 4)),
        "minimum_spatial_coverage": float(section.get("minimum_spatial_coverage", 0.125)),
        "minimum_linearity_ratio": float(section.get("minimum_linearity_ratio", 0.01)),
        "min_abs_determinant": float(plausibility.get("min_abs_determinant", 0.10)),
        "min_principal_scale": float(plausibility.get("min_principal_scale", 0.50)),
        "max_principal_scale": float(plausibility.get("max_principal_scale", 1.80)),
        "max_condition_number": float(plausibility.get("max_condition_number", 3.0)),
        "max_shear_cosine": float(plausibility.get("max_shear_cosine", 0.65)),
        "max_translation_fraction_of_diagonal": float(
            plausibility.get("max_translation_fraction_of_diagonal", 1.50)
        ),
        "allow_reflection": bool(plausibility.get("allow_reflection", False)),
        "random_seed": int(seed),
    }


def _evaluation(
    model: str,
    estimated: np.ndarray | None,
    ground_truth: np.ndarray,
    control_points: np.ndarray,
    center: np.ndarray,
    validation: dict[str, Any],
    *,
    estimator_success: bool,
) -> dict[str, Any]:
    empty = {
        "tre_pixels": None,
        "translation_error_pixels": None,
        "rotation_error_degrees": None,
        "scale_error": None,
        "affine_linear_error": None,
        "within_tolerance": False,
    }
    if estimated is None:
        return empty

    tre = mean_tre_pixels(ground_truth, estimated, control_points)
    translation_error = centered_translation_error_pixels(ground_truth, estimated, center)
    if model == "similarity":
        rotation_error = rotation_error_degrees(ground_truth, estimated)
        scale_error = abs(similarity_scale(estimated) - similarity_scale(ground_truth))
        limits = validation["similarity"]
        within = bool(
            estimator_success
            and tre <= float(limits["tre_threshold_pixels"])
            and translation_error <= float(limits["translation_error_threshold_pixels"])
            and rotation_error <= float(limits["rotation_error_threshold_degrees"])
            and scale_error <= float(limits["scale_error_threshold"])
        )
        return {
            "tre_pixels": float(tre),
            "translation_error_pixels": float(translation_error),
            "rotation_error_degrees": float(rotation_error),
            "scale_error": float(scale_error),
            "affine_linear_error": None,
            "within_tolerance": within,
        }

    linear_error = affine_linear_error(ground_truth, estimated)
    limits = validation["affine"]
    within = bool(
        estimator_success
        and tre <= float(limits["tre_threshold_pixels"])
        and translation_error <= float(limits["translation_error_threshold_pixels"])
        and linear_error <= float(limits["affine_linear_error_threshold"])
    )
    return {
        "tre_pixels": float(tre),
        "translation_error_pixels": float(translation_error),
        "rotation_error_degrees": None,
        "scale_error": None,
        "affine_linear_error": float(linear_error),
        "within_tolerance": within,
    }


def _feature_record(result: SIFTFeatureResult) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "keypoint_count": int(result.keypoint_count),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _matching_record(
    result: FeatureMatchResult,
    fixed_features: SIFTFeatureResult,
    moving_features: SIFTFeatureResult,
    *,
    rows: int,
    columns: int,
) -> dict[str, Any]:
    coverage = correspondence_grid_coverage(
        result, fixed_features, moving_features, rows=rows, columns=columns
    )
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "tentative_match_count": int(result.tentative_count),
        "filtered_match_count": int(result.accepted_count),
        "rejected_match_count": int(result.rejected_count),
        "acceptance_rate": result.acceptance_rate,
        "fixed_spatial_coverage": float(coverage.fixed_coverage),
        "moving_spatial_coverage": float(coverage.moving_coverage),
        "minimum_spatial_coverage": float(coverage.minimum_coverage),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _similarity_record(result: RANSACSimilarityResult) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "inlier_count": int(result.inlier_count),
        "outlier_count": int(result.outlier_count),
        "inlier_ratio": result.inlier_ratio,
        "reprojection_residuals": similarity_residual_summary(result),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "estimated_transform": result.estimated_transform.tolist() if result.estimated_transform is not None else None,
    }


def _affine_record(result: RANSACAffineResult) -> dict[str, Any]:
    geometry = result.correspondence_geometry
    diagnostics = result.transform_diagnostics
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "inlier_count": int(result.inlier_count),
        "outlier_count": int(result.outlier_count),
        "inlier_ratio": result.inlier_ratio,
        "reprojection_residuals": affine_residual_summary(result),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "estimated_transform": result.estimated_transform.tolist() if result.estimated_transform is not None else None,
        "correspondence_geometry": None if geometry is None else {
            "fixed_grid_coverage": geometry.fixed_grid_coverage,
            "moving_grid_coverage": geometry.moving_grid_coverage,
            "minimum_grid_coverage": geometry.minimum_grid_coverage,
            "fixed_linearity_ratio": geometry.fixed_linearity_ratio,
            "moving_linearity_ratio": geometry.moving_linearity_ratio,
        },
        "transform_diagnostics": None if diagnostics is None else {
            "determinant": diagnostics.determinant,
            "principal_scale_min": diagnostics.principal_scale_min,
            "principal_scale_max": diagnostics.principal_scale_max,
            "condition_number": diagnostics.condition_number,
            "shear_cosine": diagnostics.shear_cosine,
            "translation_norm_pixels": diagnostics.translation_norm_pixels,
            "translation_fraction_of_diagonal": diagnostics.translation_fraction_of_diagonal,
            "plausible": diagnostics.plausible,
            "rejection_reasons": list(diagnostics.rejection_reasons),
        },
    }


def _split_matches(
    matches: tuple[FeatureMatch, ...], mask: np.ndarray
) -> tuple[tuple[FeatureMatch, ...], tuple[FeatureMatch, ...]]:
    if len(matches) != int(mask.size):
        return (), ()
    inliers = tuple(match for match, keep in zip(matches, mask, strict=True) if bool(keep))
    outliers = tuple(match for match, keep in zip(matches, mask, strict=True) if not bool(keep))
    return inliers, outliers


def _save_case_figures(
    case_dir: Path,
    fixed: np.ndarray,
    moving: np.ndarray,
    fixed_features: SIFTFeatureResult,
    moving_features: SIFTFeatureResult,
    matching: FeatureMatchResult,
    estimated: np.ndarray | None,
    inlier_mask: np.ndarray,
    *,
    maximum_drawn: int,
) -> None:
    save_rgb_image(
        case_dir / "filtered_matches.png",
        draw_feature_matches(
            fixed, moving, fixed_features, moving_features, matching.accepted_matches, maximum_drawn=maximum_drawn
        ).astype(np.float32) / 255.0,
    )
    inliers, outliers = _split_matches(matching.accepted_matches, inlier_mask)
    if inliers:
        save_rgb_image(
            case_dir / "ransac_inliers.png",
            draw_feature_matches(
                fixed, moving, fixed_features, moving_features, inliers, maximum_drawn=maximum_drawn
            ).astype(np.float32) / 255.0,
        )
    if outliers:
        save_rgb_image(
            case_dir / "ransac_outliers.png",
            draw_feature_matches(
                fixed, moving, fixed_features, moving_features, outliers, maximum_drawn=maximum_drawn
            ).astype(np.float32) / 255.0,
        )
    if estimated is not None:
        registered = warp_image(moving, estimated, output_shape=fixed.shape, interpolation="linear")
        save_comparison_figure(fixed, moving, registered, case_dir / "registration.png")
        save_rgb_image(case_dir / "edge_overlay.png", edge_overlay(fixed, registered))


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    def group_summary(model: str) -> dict[str, Any]:
        selected = [item for item in records if item["model"] == model]
        numeric_tre = [item["evaluation"]["tre_pixels"] for item in selected if item["evaluation"]["tre_pixels"] is not None]
        ratios = [item["ransac"]["inlier_ratio"] for item in selected if item["ransac"]["inlier_ratio"] is not None]
        runtimes = [item["total_runtime_ms"] for item in selected]
        return {
            "case_count": len(selected),
            "ransac_success_count": sum(bool(item["ransac"]["success"]) for item in selected),
            "within_tolerance_count": sum(bool(item["evaluation"]["within_tolerance"]) for item in selected),
            "median_tre_pixels": None if not numeric_tre else float(np.median(numeric_tre)),
            "maximum_tre_pixels": None if not numeric_tre else float(np.max(numeric_tre)),
            "mean_inlier_ratio": None if not ratios else float(np.mean(ratios)),
            "mean_total_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
        }

    return {
        "case_count": len(records),
        "matching_success_count": sum(bool(item["matching"]["success"]) for item in records),
        "ransac_success_count": sum(bool(item["ransac"]["success"]) for item in records),
        "within_tolerance_count": sum(bool(item["evaluation"]["within_tolerance"]) for item in records),
        "similarity": group_summary("similarity"),
        "affine": group_summary("affine"),
    }


def _findings(records: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [item for item in records if not item["evaluation"]["within_tolerance"]]
    best = [item for item in records if item["evaluation"]["tre_pixels"] is not None]
    observations: list[str] = []
    if best:
        lowest = min(best, key=lambda item: float(item["evaluation"]["tre_pixels"]))
        highest = max(best, key=lambda item: float(item["evaluation"]["tre_pixels"]))
        observations.append(
            f"Lowest development-run TRE was {lowest['evaluation']['tre_pixels']:.3f} px for {lowest['case_id']}."
        )
        observations.append(
            f"Largest returned development-run TRE was {highest['evaluation']['tre_pixels']:.3f} px for {highest['case_id']}."
        )
    if failures:
        descriptions = ", ".join(
            f"{item['case_id']} ({item['ransac']['failure_reason'] or 'geometric threshold failure'})"
            for item in failures
        )
        observations.append(f"Cases outside development tolerance: {descriptions}.")
    else:
        observations.append("All configured cases were inside the Stage 2 development tolerances in this run.")
    return {
        "observations": observations,
        "interpretation": [
            "Stage 2 separates SIFT descriptor filtering, RANSAC execution success, and geometric correctness against known ground truth.",
            "The same similarity and affine RANSAC implementations used by the ORB pipeline are reused here; only the feature front-end and descriptor metric differ.",
            "Development results are not the final ORB versus SIFT decision because Stage 3 must run both front-ends on the same frozen cases and settings.",
        ],
        "limitations": [
            "This tracked Stage 2 snapshot records a development-machine run until target Windows validation is supplied.",
            "The case set is controlled and small, so observations are case-specific.",
            "Runtime values depend on machine, OpenCV build, and thread scheduling.",
        ],
        "decision": "Validate Stage 2 on the target Windows environment, then freeze the common cases and thresholds for Stage 3 ORB versus SIFT comparison.",
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for item in records:
        rows.append({
            "case_id": item["case_id"],
            "model": item["model"],
            "scope": item["scope"],
            "filtered_matches": item["matching"]["filtered_match_count"],
            "inlier_count": item["ransac"]["inlier_count"],
            "inlier_ratio": item["ransac"]["inlier_ratio"],
            "tre_pixels": item["evaluation"]["tre_pixels"],
            "translation_error_pixels": item["evaluation"]["translation_error_pixels"],
            "rotation_error_degrees": item["evaluation"]["rotation_error_degrees"],
            "scale_error": item["evaluation"]["scale_error"],
            "affine_linear_error": item["evaluation"]["affine_linear_error"],
            "total_runtime_ms": item["total_runtime_ms"],
            "ransac_success": item["ransac"]["success"],
            "within_tolerance": item["evaluation"]["within_tolerance"],
            "failure_reason": item["ransac"]["failure_reason"],
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = _parse_args()
    config = load_config(_resolve(args.config))
    sift_config = _sift_config(config)
    seed = int(config["experiment"].get("seed", 42))
    matching_config = config["matching"]
    ratio_threshold = float(matching_config.get("ratio_threshold", 0.75))
    minimum_matches = int(matching_config.get("minimum_matches", 8))
    maximum_distance = matching_config.get("maximum_distance")
    maximum_distance = None if maximum_distance is None else float(maximum_distance)
    maximum_drawn = int(matching_config.get("maximum_drawn_matches", 100))
    rows = int(config["sift"].get("spatial_grid", {}).get("rows", 4))
    columns = int(config["sift"].get("spatial_grid", {}).get("columns", 4))

    output_dir = _resolve(config["output"]["directory"])
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory already exists and is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    sources = _load_sources(config)
    records: list[dict[str, Any]] = []
    print("Week 4 extension Stage 2: SIFT + shared RANSAC")
    print(f"Cases: {len(config['cases'])}")

    for index, case in enumerate(config["cases"], start=1):
        case_id = str(case["id"])
        source_id = str(case["source"])
        model = str(case["model"]).strip().lower()
        scope = str(case.get("scope", "controlled"))
        fixed = sources[source_id]
        moving, ground_truth, control_points, center, metadata = _build_pair(fixed, case)

        fixed_features = detect_sift_features(fixed, config=sift_config)
        moving_features = detect_sift_features(moving, config=sift_config)
        matching = match_feature_knn_ratio(
            fixed_features,
            moving_features,
            metric="l2",
            ratio_threshold=ratio_threshold,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )

        if model == "similarity":
            ransac = estimate_similarity_ransac_from_matches(
                matching, fixed_features, moving_features, **_similarity_kwargs(config, seed)
            )
            ransac_record = _similarity_record(ransac)
        else:
            ransac = estimate_affine_ransac_from_matches(
                matching,
                fixed_features,
                moving_features,
                fixed_shape=fixed.shape,
                moving_shape=moving.shape,
                **_affine_kwargs(config, seed),
            )
            ransac_record = _affine_record(ransac)

        evaluation = _evaluation(
            model,
            ransac.estimated_transform,
            ground_truth,
            control_points,
            center,
            config["validation"],
            estimator_success=bool(ransac.success),
        )
        matching_record = _matching_record(
            matching, fixed_features, moving_features, rows=rows, columns=columns
        )
        total_runtime_ms = float(
            (fixed_features.runtime_seconds + moving_features.runtime_seconds + matching.runtime_seconds + ransac.runtime_seconds)
            * 1000.0
        )
        record = {
            "case_id": case_id,
            "source_id": source_id,
            "model": model,
            "scope": scope,
            "ground_truth": metadata,
            "fixed_features": _feature_record(fixed_features),
            "moving_features": _feature_record(moving_features),
            "matching": matching_record,
            "ransac": ransac_record,
            "evaluation": evaluation,
            "total_runtime_ms": total_runtime_ms,
        }
        records.append(record)

        _save_case_figures(
            output_dir / "cases" / case_id,
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching,
            ransac.estimated_transform,
            ransac.inlier_mask,
            maximum_drawn=maximum_drawn,
        )

        tre = evaluation["tre_pixels"]
        tre_text = "n/a" if tre is None else f"{tre:.3f}"
        state = "PASS" if evaluation["within_tolerance"] else "CHECK"
        print(
            f"{index:02d}/{len(config['cases']):02d} {case_id:<26} {model:<10} "
            f"matches={matching.accepted_count:4d} inliers={ransac.inlier_count:4d} TRE={tre_text:>7} {state}"
        )

    summary = _summarize(records)
    findings = _findings(records)
    with (output_dir / "stage02_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "findings": findings}, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "stage02_results.csv", records)

    report_payload = {
        "week": 4,
        "extension": "SIFT optional feature comparison",
        "stage": 2,
        "title": "SIFT + RANSAC similarity and affine registration",
        "status": "implementation_complete_target_validation_pending",
        "purpose": "Test whether Stage 1 SIFT correspondences recover correct Moving -> Fixed geometry under the existing similarity and affine RANSAC estimators.",
        "setup": {
            "case_count": len(records),
            "similarity_case_count": sum(item["model"] == "similarity" for item in records),
            "affine_case_count": sum(item["model"] == "affine" for item in records),
            "failure_probe_count": sum(item["scope"] == "failure_probe" for item in records),
            "seed": seed,
        },
        "variables_changed": [
            "controlled transform model and parameters by case",
            "blur or restricted field of view on the named robustness cases",
            "image texture structure on the two failure probes",
        ],
        "factors_kept_fixed": [
            "SIFT configuration from validated Stage 1",
            "L2 KNN matching with ratio threshold 0.75",
            "shared RANSAC implementations and development thresholds from the validated ORB stage",
            "Moving -> Fixed transform convention",
        ],
        "metrics_and_thresholds": {
            "validation": config["validation"],
            "matching": config["matching"],
            "ransac_similarity": config["ransac_similarity"],
            "ransac_affine": config["ransac_affine"],
        },
        "development_run": summary,
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "technical_note": "docs/SIFT_FEATURES.md",
        "experiment_summary": "docs/experiments/sift_stage02_summary.md",
        "target_windows_validation": {
            "status": "pending",
            "note": "Run the full pytest suite and Stage 2 experiment on the target Windows environment before marking Stage 2 complete.",
        },
    }
    write_report_snapshot(_resolve(config["output"]["report_snapshot"]), report_payload)

    print("\nSIFT Stage 2 development run summary")
    print(f"Matching success: {summary['matching_success_count']}/{summary['case_count']}")
    print(f"RANSAC success: {summary['ransac_success_count']}/{summary['case_count']}")
    print(f"Within tolerance: {summary['within_tolerance_count']}/{summary['case_count']}")
    print(f"Tracked report: {config['output']['report_snapshot']}")


if __name__ == "__main__":
    main()
