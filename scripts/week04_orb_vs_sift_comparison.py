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

from image_registration.affine_ransac import (
    RANSACAffineResult,
    estimate_affine_ransac_from_matches,
    residual_summary as affine_residual_summary,
)
from image_registration.config import load_config
from image_registration.degradations import gaussian_blur
from image_registration.feature_comparison import (
    build_paired_case_summary,
    summarize_frontend,
    summarize_paired_outcomes,
)
from image_registration.feature_matching import (
    FeatureMatch,
    FeatureMatchResult,
    correspondence_grid_coverage,
    draw_feature_matches,
    match_feature_knn_ratio,
)
from image_registration.io import load_image
from image_registration.orb import ORBConfig, ORBFeatureResult, detect_orb_features, keypoint_grid_coverage
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

FeatureResult = ORBFeatureResult | SIFTFeatureResult


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen Week 4 ORB versus SIFT comparison.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _orb_config(config: dict[str, Any]) -> ORBConfig:
    values = config["orb"]
    return ORBConfig(
        n_features=int(values.get("n_features", 800)),
        scale_factor=float(values.get("scale_factor", 1.2)),
        n_levels=int(values.get("n_levels", 8)),
        edge_threshold=int(values.get("edge_threshold", 31)),
        first_level=int(values.get("first_level", 0)),
        wta_k=int(values.get("wta_k", 2)),
        score_type=str(values.get("score_type", "harris")),
        patch_size=int(values.get("patch_size", 31)),
        fast_threshold=int(values.get("fast_threshold", 20)),
    )


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
    raise ValueError(f"Unsupported Stage 3 postprocess type: {kind}")


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
        raise ValueError("Stage 3 model must be similarity or affine.")

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


def _feature_record(result: FeatureResult, *, rows: int, columns: int) -> dict[str, Any]:
    area = int(result.image_shape[0] * result.image_shape[1])
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "keypoint_count": int(result.keypoint_count),
        "keypoint_density_per_1000_pixels": 0.0 if area == 0 else float(result.keypoint_count * 1000.0 / area),
        "spatial_coverage": float(
            keypoint_grid_coverage(result.points_xy, result.image_shape, rows=rows, columns=columns)
        ),
        "runtime_ms": float(result.runtime_seconds * 1000.0),
    }


def _matching_record(
    result: FeatureMatchResult,
    fixed_features: FeatureResult,
    moving_features: FeatureResult,
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
    fixed_features: FeatureResult,
    moving_features: FeatureResult,
    matching: FeatureMatchResult,
    estimated: np.ndarray | None,
    inlier_mask: np.ndarray,
    *,
    maximum_drawn: int,
) -> None:
    save_rgb_image(
        case_dir / "filtered_matches.png",
        draw_feature_matches(
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching.accepted_matches,
            maximum_drawn=maximum_drawn,
        ).astype(np.float32)
        / 255.0,
    )
    inliers, outliers = _split_matches(matching.accepted_matches, inlier_mask)
    if inliers:
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
    if estimated is not None:
        registered = warp_image(moving, estimated, output_shape=fixed.shape, interpolation="linear")
        save_comparison_figure(fixed, moving, registered, case_dir / "registration.png")
        save_rgb_image(case_dir / "edge_overlay.png", edge_overlay(fixed, registered))


def _run_frontend(
    frontend: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    model: str,
    ground_truth: np.ndarray,
    control_points: np.ndarray,
    center: np.ndarray,
    config: dict[str, Any],
    seed: int,
) -> tuple[dict[str, Any], FeatureResult, FeatureResult, FeatureMatchResult, Any]:
    if frontend == "orb":
        fixed_features = detect_orb_features(fixed, config=_orb_config(config))
        moving_features = detect_orb_features(moving, config=_orb_config(config))
        metric = str(config["matching"].get("orb_metric", "hamming"))
        grid_config = config["orb"].get("spatial_grid", {})
    elif frontend == "sift":
        fixed_features = detect_sift_features(fixed, config=_sift_config(config))
        moving_features = detect_sift_features(moving, config=_sift_config(config))
        metric = str(config["matching"].get("sift_metric", "l2"))
        grid_config = config["sift"].get("spatial_grid", {})
    else:
        raise ValueError("frontend must be orb or sift.")

    ratio_threshold = float(config["matching"].get("ratio_threshold", 0.75))
    minimum_matches = int(config["matching"].get("minimum_matches", 8))
    maximum_distance = config["matching"].get("maximum_distance")
    maximum_distance = None if maximum_distance is None else float(maximum_distance)
    rows = int(grid_config.get("rows", 4))
    columns = int(grid_config.get("columns", 4))

    matching = match_feature_knn_ratio(
        fixed_features,
        moving_features,
        metric=metric,
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
    feature_fixed_record = _feature_record(fixed_features, rows=rows, columns=columns)
    feature_moving_record = _feature_record(moving_features, rows=rows, columns=columns)
    matching_record = _matching_record(
        matching, fixed_features, moving_features, rows=rows, columns=columns
    )
    total_runtime_ms = float(
        (
            fixed_features.runtime_seconds
            + moving_features.runtime_seconds
            + matching.runtime_seconds
            + ransac.runtime_seconds
        )
        * 1000.0
    )
    record = {
        "frontend": frontend,
        "descriptor_type": "binary" if frontend == "orb" else "float32",
        "descriptor_metric": metric,
        "fixed_features": feature_fixed_record,
        "moving_features": feature_moving_record,
        "matching": matching_record,
        "ransac": ransac_record,
        "evaluation": evaluation,
        "total_runtime_ms": total_runtime_ms,
    }
    return record, fixed_features, moving_features, matching, ransac


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for item in records:
        rows.append(
            {
                "case_id": item["case_id"],
                "frontend": item["frontend"],
                "model": item["model"],
                "scope": item["scope"],
                "fixed_keypoints": item["fixed_features"]["keypoint_count"],
                "moving_keypoints": item["moving_features"]["keypoint_count"],
                "moving_feature_coverage": item["moving_features"]["spatial_coverage"],
                "feature_runtime_ms": item["fixed_features"]["runtime_ms"] + item["moving_features"]["runtime_ms"],
                "filtered_matches": item["matching"]["filtered_match_count"],
                "match_coverage": item["matching"]["minimum_spatial_coverage"],
                "matching_runtime_ms": item["matching"]["runtime_ms"],
                "inlier_count": item["ransac"]["inlier_count"],
                "inlier_ratio": item["ransac"]["inlier_ratio"],
                "tre_pixels": item["evaluation"]["tre_pixels"],
                "translation_error_pixels": item["evaluation"]["translation_error_pixels"],
                "rotation_error_degrees": item["evaluation"]["rotation_error_degrees"],
                "scale_error": item["evaluation"]["scale_error"],
                "affine_linear_error": item["evaluation"]["affine_linear_error"],
                "ransac_runtime_ms": item["ransac"]["runtime_ms"],
                "total_runtime_ms": item["total_runtime_ms"],
                "matching_success": item["matching"]["success"],
                "ransac_success": item["ransac"]["success"],
                "within_tolerance": item["evaluation"]["within_tolerance"],
                "failure_reason": item["ransac"]["failure_reason"],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _development_observations(
    summaries: dict[str, dict[str, Any]],
    paired: list[dict[str, Any]],
) -> list[str]:
    outcomes = summarize_paired_outcomes(paired)
    observations = [
        f"ORB was inside tolerance on {summaries['orb']['within_tolerance_count']} / {summaries['orb']['case_count']} cases in this development run.",
        f"SIFT was inside tolerance on {summaries['sift']['within_tolerance_count']} / {summaries['sift']['case_count']} cases in this development run.",
        f"Paired outcomes: {outcomes['both_within_tolerance']} both passed, {outcomes['orb_only_within_tolerance']} ORB-only passes, {outcomes['sift_only_within_tolerance']} SIFT-only passes, {outcomes['neither_within_tolerance']} neither passed.",
    ]
    for item in paired:
        if item["outcome"] in {"orb_only_within_tolerance", "sift_only_within_tolerance", "neither_within_tolerance"}:
            observations.append(f"{item['case_id']}: {item['outcome']}.")
    return observations


def main() -> None:
    args = _parse_args()
    config = load_config(_resolve(args.config))
    seed = int(config["experiment"].get("seed", 42))
    maximum_drawn = int(config["matching"].get("maximum_drawn_matches", 100))

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
    print("Week 4 SIFT extension Stage 3: frozen ORB versus SIFT comparison")
    print(f"Cases: {len(config['cases'])}; registrations: {len(config['cases']) * 2}")

    for index, case in enumerate(config["cases"], start=1):
        case_id = str(case["id"])
        source_id = str(case["source"])
        model = str(case["model"]).strip().lower()
        scope = str(case.get("scope", "normal"))
        fixed = sources[source_id]
        moving, ground_truth, control_points, center, metadata = _build_pair(fixed, case)

        print(f"\n{index:02d}/{len(config['cases']):02d} {case_id} [{model}, {scope}]")
        for frontend in ("orb", "sift"):
            frontend_record, fixed_features, moving_features, matching, ransac = _run_frontend(
                frontend,
                fixed,
                moving,
                model,
                ground_truth,
                control_points,
                center,
                config,
                seed,
            )
            record = {
                "case_id": case_id,
                "source_id": source_id,
                "model": model,
                "scope": scope,
                "ground_truth": metadata,
                **frontend_record,
            }
            records.append(record)
            _save_case_figures(
                output_dir / "cases" / case_id / frontend,
                fixed,
                moving,
                fixed_features,
                moving_features,
                matching,
                ransac.estimated_transform,
                ransac.inlier_mask,
                maximum_drawn=maximum_drawn,
            )
            tre = record["evaluation"]["tre_pixels"]
            tre_text = "n/a" if tre is None else f"{tre:.3f}"
            state = "PASS" if record["evaluation"]["within_tolerance"] else "CHECK"
            print(
                f"  {frontend.upper():<4} kp={record['moving_features']['keypoint_count']:4d} "
                f"matches={record['matching']['filtered_match_count']:4d} "
                f"inliers={record['ransac']['inlier_count']:4d} TRE={tre_text:>7} "
                f"runtime={record['total_runtime_ms']:8.2f} ms {state}"
            )

    summaries = {
        "orb": summarize_frontend(records, "orb"),
        "sift": summarize_frontend(records, "sift"),
    }
    paired = build_paired_case_summary(records)
    paired_outcomes = summarize_paired_outcomes(paired)
    observations = _development_observations(summaries, paired)

    with (output_dir / "stage03_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    with (output_dir / "paired_case_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(paired, handle, indent=2)
        handle.write("\n")
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "frontends": summaries,
                "paired_outcomes": paired_outcomes,
                "observations": observations,
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    _write_csv(output_dir / "stage03_results.csv", records)

    report_payload = {
        "week": 4,
        "extension": "SIFT optional feature comparison",
        "stage": 3,
        "title": "Frozen ORB versus SIFT controlled comparison",
        "status": "implementation_complete_target_validation_pending",
        "purpose": "Compare ORB and SIFT feature front-ends under identical image pairs, ground truth, transform models, RANSAC settings, evaluation points, success criteria, and result schema.",
        "setup": {
            "case_count": len(config["cases"]),
            "registration_count": len(records),
            "normal_case_count": sum(str(case.get("scope", "normal")) == "normal" for case in config["cases"]),
            "challenging_case_count": sum(str(case.get("scope", "normal")) == "challenging" for case in config["cases"]),
            "failure_probe_count": sum(str(case.get("scope", "normal")) == "failure_probe" for case in config["cases"]),
            "seed": seed,
        },
        "frozen_factors": [
            "same fixed and moving image pair for both front-ends",
            "same known Moving -> Fixed ground-truth transform",
            "same transform model per case",
            "same KNN ratio threshold 0.75 and minimum-match rule",
            "same similarity or affine RANSAC settings",
            "same control points and geometric evaluation thresholds",
            "same output result schema",
        ],
        "frontend_difference": {
            "orb": "binary descriptor with Hamming distance",
            "sift": "128-dimensional float descriptor with L2 distance",
        },
        "metrics_and_thresholds": {
            "matching": config["matching"],
            "ransac_similarity": config["ransac_similarity"],
            "ransac_affine": config["ransac_affine"],
            "validation": config["validation"],
        },
        "development_run": {
            "frontends": summaries,
            "paired_outcomes": paired_outcomes,
        },
        "paired_case_results": paired,
        "observations": observations,
        "interpretation": [
            "Feature count and raw match count are diagnostics, not the deciding criteria.",
            "Registration success and geometric correctness are evaluated before difficult-case recovery, RANSAC consistency, and runtime.",
            "A final SIFT retention decision is intentionally deferred until the same Stage 3 experiment is validated on the target Windows environment.",
        ],
        "limitations": [
            "This tracked Stage 3 snapshot records a development-machine run until target Windows validation is supplied.",
            "The comparison is a small controlled subset and does not establish universal superiority of either feature method.",
            "Runtime depends on machine, OpenCV build, and thread scheduling.",
        ],
        "final_sift_decision": {
            "status": "pending_target_windows_validation",
            "allowed_outcomes": [
                "retain_as_core_feature_baseline",
                "retain_as_optional_complement",
                "document_only",
            ],
            "priority": [
                "success rate",
                "TRE and geometric correctness",
                "difficult-case recovery",
                "RANSAC consistency",
                "runtime",
            ],
        },
        "raw_output_directory": str(config["output"]["directory"]),
        "technical_note": "docs/ORB_VS_SIFT_COMPARISON.md",
        "target_windows_validation": {
            "status": "pending",
            "note": "Run the full pytest suite and this frozen Stage 3 experiment on the target Windows environment before making the final SIFT retention decision.",
        },
    }
    write_report_snapshot(_resolve(config["output"]["report_snapshot"]), report_payload)

    print("\nStage 3 development comparison summary")
    for frontend in ("orb", "sift"):
        summary = summaries[frontend]
        print(
            f"{frontend.upper()}: matching {summary['matching_success_count']}/{summary['case_count']}, "
            f"RANSAC {summary['ransac_success_count']}/{summary['case_count']}, "
            f"within tolerance {summary['within_tolerance_count']}/{summary['case_count']}, "
            f"median TRE {summary['median_tre_pixels'] if summary['median_tre_pixels'] is not None else 'n/a'}"
        )
    print(
        "Paired outcomes: "
        f"both={paired_outcomes['both_within_tolerance']}, "
        f"ORB-only={paired_outcomes['orb_only_within_tolerance']}, "
        f"SIFT-only={paired_outcomes['sift_only_within_tolerance']}, "
        f"neither={paired_outcomes['neither_within_tolerance']}"
    )
    print(f"Tracked report: {config['output']['report_snapshot']}")


if __name__ == "__main__":
    main()
