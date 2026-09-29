from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
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

from image_registration.affine_ransac import (
    RANSACAffineResult,
    estimate_affine_ransac,
    estimate_affine_ransac_from_matches,
    residual_summary as affine_residual_summary,
)
from image_registration.degradations import (
    gaussian_blur,
    illumination_gradient,
    rectangular_occlusion,
)
from image_registration.feature_matching import (
    FeatureMatch,
    FeatureMatchResult,
    draw_feature_matches,
    match_orb_knn_ratio,
)
from image_registration.feature_metrics import texture_diagnostics
from image_registration.io import load_image
from image_registration.orb import ORBConfig, detect_orb_features
from image_registration.overlap import apply_field_of_view, rectangular_field_of_view_mask
from image_registration.ransac import (
    RANSACSimilarityResult,
    estimate_similarity_ransac_from_matches,
)
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    mean_tre_pixels,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import (
    GroundTruthTransform,
    generate_synthetic_pair,
    image_center,
)
from image_registration.transforms import (
    affine_matrix,
    apply_transform,
    invert_transform,
    rotation_matrix,
)
from image_registration.visualization import (
    edge_overlay,
    save_comparison_figure,
    save_grayscale_image,
    save_rgb_image,
)
from image_registration.warping import warp_image


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _orb_config(config: dict[str, Any]) -> ORBConfig:
    section = config["orb"]
    return ORBConfig(
        n_features=int(section.get("n_features", 800)),
        scale_factor=float(section.get("scale_factor", 1.2)),
        n_levels=int(section.get("n_levels", 8)),
        edge_threshold=int(section.get("edge_threshold", 31)),
        first_level=int(section.get("first_level", 0)),
        wta_k=int(section.get("wta_k", 2)),
        score_type=str(section.get("score_type", "harris")).strip().lower(),
        patch_size=int(section.get("patch_size", 31)),
        fast_threshold=int(section.get("fast_threshold", 20)),
    )


def _load_sources(config: dict[str, Any]) -> dict[str, np.ndarray]:
    sources: dict[str, np.ndarray] = {}
    for source_id, source_path in config["sources"].items():
        sources[str(source_id)] = np.asarray(
            load_image(_resolve(str(source_path)), color_mode="grayscale").array
        )

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
            if height <= 0 or width <= 0 or block <= 1:
                raise ValueError("Checkerboard dimensions and block_size must be positive.")
            yy, xx = np.indices((height, width))
            checker = ((xx // block + yy // block) % 2) * 255
            sources[str(source_id)] = checker.astype(np.uint8)
        else:
            raise ValueError(f"Unsupported generated source type: {kind}")
    return sources


def _build_affine_pair(
    fixed: np.ndarray,
    case: dict[str, Any],
    *,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    center = image_center(fixed.shape)
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
    model = str(case.get("ground_truth_model", "affine")).strip().lower()
    ground_truth = GroundTruthTransform(
        transform_type=model,
        parameters={
            "angle_degrees": angle,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "shear_x": shear_x,
            "tx": tx,
            "ty": ty,
            "center": center.tolist(),
            "linear": linear.tolist(),
        },
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )
    pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
    moving = np.asarray(pair.moving)

    postprocess_record: dict[str, Any] | None = None
    postprocess = case.get("postprocess")
    if isinstance(postprocess, dict):
        kind = str(postprocess.get("type", "")).strip().lower()
        if kind == "rectangular_occlusion":
            moving, _visibility, box = rectangular_occlusion(
                moving,
                area_fraction=float(postprocess.get("area_fraction", 0.15)),
                fill_value=float(postprocess.get("fill_value", 0.0)),
                rng=rng,
            )
            postprocess_record = {
                "type": kind,
                "area_fraction": float(postprocess.get("area_fraction", 0.15)),
                "box": box,
            }
        elif kind == "restricted_fov":
            mask = rectangular_field_of_view_mask(
                moving.shape,
                width_fraction=float(postprocess.get("width_fraction", 0.70)),
                height_fraction=float(postprocess.get("height_fraction", 0.75)),
                center_x_fraction=float(postprocess.get("center_x_fraction", 0.50)),
                center_y_fraction=float(postprocess.get("center_y_fraction", 0.50)),
            )
            moving = apply_field_of_view(
                moving,
                mask,
                fill_value=float(postprocess.get("fill_value", 0.0)),
            )
            postprocess_record = {
                "type": kind,
                "width_fraction": float(postprocess.get("width_fraction", 0.70)),
                "height_fraction": float(postprocess.get("height_fraction", 0.75)),
            }
        elif kind == "gaussian_blur":
            sigma = float(postprocess.get("sigma", 2.0))
            moving = np.asarray(gaussian_blur(moving, sigma=sigma))
            postprocess_record = {"type": kind, "sigma": sigma}
        elif kind == "illumination_gradient":
            strength = float(postprocess.get("strength_fraction", 0.25))
            direction = str(postprocess.get("direction", "diagonal"))
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
            raise ValueError(f"Unsupported Day 19 postprocess type: {kind}")

    metadata = ground_truth.as_dict()
    metadata["ground_truth_model"] = model
    metadata["postprocess"] = postprocess_record
    return moving, matrix, np.asarray(pair.control_points_moving), metadata


def _affine_kwargs(
    config: dict[str, Any],
    seed: int,
    *,
    reprojection_threshold: float | None = None,
) -> dict[str, Any]:
    section = config["ransac_affine"]
    plausibility = section.get("plausibility", {})
    return {
        "reprojection_threshold": float(
            section.get("reprojection_threshold", 3.0)
            if reprojection_threshold is None
            else reprojection_threshold
        ),
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


def _geometry_metrics(
    estimated: np.ndarray | None,
    ground_truth: np.ndarray,
    control_points_moving: np.ndarray,
    center: np.ndarray,
    validation: dict[str, Any],
    *,
    estimator_success: bool,
) -> dict[str, Any]:
    if estimated is None:
        return {
            "tre_pixels": None,
            "affine_linear_error": None,
            "translation_error_pixels": None,
            "within_tolerance": False,
        }
    tre = mean_tre_pixels(ground_truth, estimated, control_points_moving)
    linear_error = affine_linear_error(ground_truth, estimated)
    translation_error = centered_translation_error_pixels(ground_truth, estimated, center)
    within = bool(
        estimator_success
        and tre <= float(validation["tre_threshold_pixels"])
        and linear_error <= float(validation["affine_linear_error_threshold"])
        and translation_error <= float(validation["translation_error_threshold_pixels"])
    )
    return {
        "tre_pixels": float(tre),
        "affine_linear_error": float(linear_error),
        "translation_error_pixels": float(translation_error),
        "within_tolerance": within,
    }


def _affine_record(result: RANSACAffineResult) -> dict[str, Any]:
    geometry = result.correspondence_geometry
    transform = result.transform_diagnostics
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "input_match_count": int(result.input_match_count),
        "inlier_count": int(result.inlier_count),
        "outlier_count": int(result.outlier_count),
        "inlier_ratio": result.inlier_ratio,
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "reprojection_residuals": affine_residual_summary(result),
        "correspondence_geometry": (
            {
                "fixed_grid_coverage": geometry.fixed_grid_coverage,
                "moving_grid_coverage": geometry.moving_grid_coverage,
                "minimum_grid_coverage": geometry.minimum_grid_coverage,
                "fixed_linearity_ratio": geometry.fixed_linearity_ratio,
                "moving_linearity_ratio": geometry.moving_linearity_ratio,
            }
            if geometry is not None
            else None
        ),
        "transform_diagnostics": (
            {
                "determinant": transform.determinant,
                "principal_scale_min": transform.principal_scale_min,
                "principal_scale_max": transform.principal_scale_max,
                "condition_number": transform.condition_number,
                "shear_cosine": transform.shear_cosine,
                "translation_norm_pixels": transform.translation_norm_pixels,
                "translation_fraction_of_diagonal": transform.translation_fraction_of_diagonal,
                "plausible": transform.plausible,
                "rejection_reasons": list(transform.rejection_reasons),
            }
            if transform is not None
            else None
        ),
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
    ransac: RANSACAffineResult,
    maximum_drawn: int,
) -> None:
    if ransac.inlier_mask.size != matching.accepted_count:
        return
    inliers, outliers = _split_matches(matching.accepted_matches, ransac.inlier_mask)
    if inliers:
        save_rgb_image(
            case_dir / "affine_ransac_inliers.png",
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
            case_dir / "affine_ransac_outliers.png",
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


def _save_residual_plot(path: Path, result: RANSACAffineResult, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7.0, 4.6), dpi=140)
    positions = np.arange(result.input_match_count)
    if result.reprojection_residuals.size and result.inlier_mask.size == result.input_match_count:
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


def _texture_record(
    fixed: np.ndarray,
    moving: np.ndarray,
    fixed_features: Any,
    moving_features: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    section = config["texture"]
    kwargs = {
        "low_threshold": float(section["low_gradient_energy_threshold"]),
        "high_threshold": float(section["high_gradient_energy_threshold"]),
    }
    fixed_diag = texture_diagnostics(fixed, fixed_features, **kwargs)
    moving_diag = texture_diagnostics(moving, moving_features, **kwargs)
    order = {"low": 0, "medium": 1, "high": 2}
    combined_label = (
        fixed_diag.label
        if order[fixed_diag.label] <= order[moving_diag.label]
        else moving_diag.label
    )
    return {
        "fixed_gradient_energy": fixed_diag.gradient_energy,
        "moving_gradient_energy": moving_diag.gradient_energy,
        "fixed_keypoint_density_per_megapixel": fixed_diag.keypoint_density_per_megapixel,
        "moving_keypoint_density_per_megapixel": moving_diag.keypoint_density_per_megapixel,
        "fixed_label": fixed_diag.label,
        "moving_label": moving_diag.label,
        "minimum_label": combined_label,
    }


def _similarity_result_record(
    result: RANSACSimilarityResult,
    ground_truth: np.ndarray,
    control_points_moving: np.ndarray,
    center: np.ndarray,
    validation: dict[str, Any],
) -> dict[str, Any]:
    geometry = _geometry_metrics(
        result.estimated_transform,
        ground_truth,
        control_points_moving,
        center,
        validation,
        estimator_success=result.success,
    )
    return {
        "success": bool(result.success),
        "failure_reason": result.failure_reason,
        "inlier_count": int(result.inlier_count),
        "inlier_ratio": result.inlier_ratio,
        "runtime_ms": float(result.runtime_seconds * 1000.0),
        "geometry": geometry,
    }


def _run_degeneracy_probes(config: dict[str, Any], seed: int) -> list[dict[str, Any]]:
    base_kwargs = _affine_kwargs(config, seed)
    probes: list[dict[str, Any]] = []

    x = np.linspace(20.0, 220.0, 16)
    moving = np.column_stack([x, 0.45 * x + 7.0])
    transform = affine_matrix(np.asarray([[1.05, 0.06], [0.02, 0.94]]), tx=12.0, ty=-8.0)
    fixed = apply_transform(moving, transform)
    kwargs = dict(base_kwargs)
    kwargs["minimum_spatial_coverage"] = 0.0
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(256, 256),
        moving_shape=(256, 256),
        **kwargs,
    )
    probes.append(
        {
            "probe": "collinear_correspondences",
            "expected_failure": "degenerate_correspondences_collinear",
            "observed_success": bool(result.success),
            "observed_failure": result.failure_reason,
            "passed": result.failure_reason == "degenerate_correspondences_collinear",
        }
    )

    moving = np.asarray(
        [[10, 10], [15, 13], [22, 16], [12, 24], [19, 28], [27, 21], [31, 29], [35, 17]],
        dtype=np.float64,
    )
    fixed = apply_transform(moving, transform)
    kwargs = dict(base_kwargs)
    kwargs["minimum_linearity_ratio"] = 0.001
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(512, 512),
        moving_shape=(512, 512),
        **kwargs,
    )
    probes.append(
        {
            "probe": "clustered_correspondences",
            "expected_failure": "poor_spatial_coverage",
            "observed_success": bool(result.success),
            "observed_failure": result.failure_reason,
            "passed": result.failure_reason == "poor_spatial_coverage",
        }
    )

    yy, xx = np.meshgrid(np.linspace(40.0, 180.0, 4), np.linspace(40.0, 180.0, 4))
    moving = np.column_stack([xx.ravel(), yy.ravel()])
    implausible = affine_matrix(np.diag([2.2, 2.1]), tx=4.0, ty=-6.0)
    fixed = apply_transform(moving, implausible)
    kwargs = dict(base_kwargs)
    kwargs["minimum_spatial_coverage"] = 0.05
    result = estimate_affine_ransac(
        fixed,
        moving,
        fixed_shape=(700, 700),
        moving_shape=(256, 256),
        **kwargs,
    )
    probes.append(
        {
            "probe": "implausible_scale",
            "expected_failure": "implausible_principal_scale",
            "observed_success": bool(result.success),
            "observed_failure": result.failure_reason,
            "passed": result.failure_reason == "implausible_principal_scale",
        }
    )
    return probes


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [r for r in records if r["affine_ransac"]["success"]]
    correct = [r for r in records if r["affine_geometry"]["within_tolerance"]]
    tres = np.asarray(
        [r["affine_geometry"]["tre_pixels"] for r in records if r["affine_geometry"]["tre_pixels"] is not None],
        dtype=np.float64,
    )
    ratios = np.asarray(
        [r["affine_ransac"]["inlier_ratio"] for r in successes if r["affine_ransac"]["inlier_ratio"] is not None],
        dtype=np.float64,
    )
    runtimes = np.asarray([r["affine_ransac"]["runtime_ms"] for r in records], dtype=np.float64)
    by_texture: dict[str, dict[str, Any]] = {}
    for label in ("low", "medium", "high"):
        subset = [r for r in records if r["texture"]["minimum_label"] == label]
        if not subset:
            continue
        subset_tre = [
            r["affine_geometry"]["tre_pixels"]
            for r in subset
            if r["affine_geometry"]["tre_pixels"] is not None
        ]
        by_texture[label] = {
            "case_count": len(subset),
            "success_count": sum(bool(r["affine_ransac"]["success"]) for r in subset),
            "within_tolerance_count": sum(bool(r["affine_geometry"]["within_tolerance"]) for r in subset),
            "median_tre_pixels": float(np.median(subset_tre)) if subset_tre else None,
        }
    return {
        "case_count": len(records),
        "ransac_success_count": len(successes),
        "within_tolerance_count": len(correct),
        "failed_count": len(records) - len(successes),
        "mean_inlier_ratio": float(np.mean(ratios)) if ratios.size else None,
        "median_tre_pixels": float(np.median(tres)) if tres.size else None,
        "maximum_tre_pixels": float(np.max(tres)) if tres.size else None,
        "mean_affine_ransac_runtime_ms": float(np.mean(runtimes)) if runtimes.size else None,
        "by_texture": by_texture,
    }


def _threshold_sweep(
    config: dict[str, Any],
    contexts: dict[str, dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    section = config["threshold_sweep"]
    rows: list[dict[str, Any]] = []
    matching_cfg = config["matching"]
    maximum_distance_value = matching_cfg.get("maximum_distance")
    maximum_distance = None if maximum_distance_value is None else float(maximum_distance_value)
    minimum_matches = int(matching_cfg.get("minimum_matches", 8))
    norm = str(matching_cfg.get("norm", "hamming")).strip().lower()
    validation = config["validation"]

    for case_id in section["case_ids"]:
        context = contexts[str(case_id)]
        for ratio_threshold in section["ratio_thresholds"]:
            matching = match_orb_knn_ratio(
                context["fixed_features"],
                context["moving_features"],
                ratio_threshold=float(ratio_threshold),
                maximum_distance=maximum_distance,
                minimum_matches=minimum_matches,
                norm=norm,
            )
            for reprojection_threshold in section["reprojection_thresholds"]:
                result = estimate_affine_ransac_from_matches(
                    matching,
                    context["fixed_features"],
                    context["moving_features"],
                    fixed_shape=context["fixed"].shape,
                    moving_shape=context["moving"].shape,
                    **_affine_kwargs(
                        config,
                        seed,
                        reprojection_threshold=float(reprojection_threshold),
                    ),
                )
                geometry = _geometry_metrics(
                    result.estimated_transform,
                    context["ground_truth"],
                    context["control_points_moving"],
                    image_center(context["fixed"].shape),
                    validation,
                    estimator_success=result.success,
                )
                rows.append(
                    {
                        "case_id": str(case_id),
                        "ratio_threshold": float(ratio_threshold),
                        "reprojection_threshold": float(reprojection_threshold),
                        "accepted_match_count": int(matching.accepted_count),
                        "ransac_success": bool(result.success),
                        "failure_reason": result.failure_reason,
                        "inlier_count": int(result.inlier_count),
                        "inlier_ratio": result.inlier_ratio,
                        "tre_pixels": geometry["tre_pixels"],
                        "within_tolerance": geometry["within_tolerance"],
                    }
                )
    return rows


def _save_threshold_plot(path: Path, rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.0), dpi=140)
    ratios = sorted({row["ratio_threshold"] for row in rows})
    reproj = sorted({row["reprojection_threshold"] for row in rows})
    for ratio in ratios:
        medians = []
        for threshold in reproj:
            values = [
                row["tre_pixels"]
                for row in rows
                if row["ratio_threshold"] == ratio
                and row["reprojection_threshold"] == threshold
                and row["tre_pixels"] is not None
            ]
            medians.append(float(np.median(values)) if values else np.nan)
        ax.plot(reproj, medians, marker="o", label=f"ratio {ratio:.2f}")
    ax.set_xlabel("RANSAC reprojection threshold (px)")
    ax.set_ylabel("Median TRE across sweep subset (px)")
    ax.set_title("Day 19 threshold sweep")
    ax.legend(ncol=2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _save_texture_plot(path: Path, records: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=140)
    for record in records:
        tre = record["affine_geometry"]["tre_pixels"]
        if tre is None:
            continue
        energy = min(
            record["texture"]["fixed_gradient_energy"],
            record["texture"]["moving_gradient_energy"],
        )
        ax.scatter(energy, tre, s=45)
        ax.annotate(record["case_id"], (energy, tre), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Minimum normalized gradient energy")
    ax.set_ylabel("Affine TRE (px)")
    ax.set_title("Texture diagnostic versus affine registration error")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _save_model_plot(path: Path, records: list[dict[str, Any]]) -> None:
    labels = [r["case_id"] for r in records]
    affine_values = [r["affine_geometry"]["tre_pixels"] or np.nan for r in records]
    similarity_values = [r["similarity_baseline"]["geometry"]["tre_pixels"] or np.nan for r in records]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10.0, 5.2), dpi=140)
    ax.plot(x, similarity_values, marker="o", label="Similarity RANSAC")
    ax.plot(x, affine_values, marker="o", label="Affine RANSAC")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("TRE (px)")
    ax.set_title("Similarity versus affine model on shared correspondences")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "case_id": record["case_id"],
                "source_id": record["source_id"],
                "ground_truth_model": record["condition_metadata"]["ground_truth_model"],
                "texture_label": record["texture"]["minimum_label"],
                "accepted_matches": record["matching"]["accepted_match_count"],
                "affine_success": record["affine_ransac"]["success"],
                "affine_failure_reason": record["affine_ransac"]["failure_reason"],
                "affine_inlier_count": record["affine_ransac"]["inlier_count"],
                "affine_inlier_ratio": record["affine_ransac"]["inlier_ratio"],
                "affine_tre_pixels": record["affine_geometry"]["tre_pixels"],
                "affine_linear_error": record["affine_geometry"]["affine_linear_error"],
                "affine_translation_error_pixels": record["affine_geometry"]["translation_error_pixels"],
                "affine_within_tolerance": record["affine_geometry"]["within_tolerance"],
                "similarity_success": record["similarity_baseline"]["success"],
                "similarity_tre_pixels": record["similarity_baseline"]["geometry"]["tre_pixels"],
                "affine_runtime_ms": record["affine_ransac"]["runtime_ms"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _findings(
    records: list[dict[str, Any]],
    degeneracy_probes: list[dict[str, Any]],
    sweep: list[dict[str, Any]],
) -> dict[str, Any]:
    valid = [
        (r["case_id"], r["affine_geometry"]["tre_pixels"])
        for r in records
        if r["affine_geometry"]["tre_pixels"] is not None
    ]
    best = min(valid, key=lambda item: item[1]) if valid else None
    worst = max(valid, key=lambda item: item[1]) if valid else None
    lowest_ratio = min(
        (
            (r["case_id"], r["affine_ransac"]["inlier_ratio"])
            for r in records
            if r["affine_ransac"]["inlier_ratio"] is not None
        ),
        key=lambda item: item[1],
        default=None,
    )
    affine_true = [r for r in records if r["condition_metadata"]["ground_truth_model"] == "affine"]
    similarity_losses = [
        r for r in affine_true
        if r["similarity_baseline"]["geometry"]["tre_pixels"] is not None
        and r["affine_geometry"]["tre_pixels"] is not None
        and r["similarity_baseline"]["geometry"]["tre_pixels"] > r["affine_geometry"]["tre_pixels"]
    ]
    failed_cases = [
        {"case_id": r["case_id"], "reason": r["affine_ransac"]["failure_reason"]}
        for r in records
        if not r["affine_ransac"]["success"]
    ]
    observations: list[str] = []
    if best:
        observations.append(f"The smallest affine TRE occurred in {best[0]} at {best[1]:.3f} px.")
    if worst:
        observations.append(f"The largest affine TRE occurred in {worst[0]} at {worst[1]:.3f} px.")
    if lowest_ratio:
        observations.append(
            f"The lowest affine RANSAC inlier ratio occurred in {lowest_ratio[0]} at {lowest_ratio[1]:.3f}."
        )
    observations.append(
        f"Affine RANSAC produced lower TRE than the similarity model on {len(similarity_losses)} of {len(affine_true)} true-affine cases in this development run."
    )
    observations.append(
        f"The three controlled degeneracy and plausibility probes produced their expected failure labels in {sum(p['passed'] for p in degeneracy_probes)} of {len(degeneracy_probes)} probes."
    )
    sweep_success = sum(bool(row["within_tolerance"]) for row in sweep)
    observations.append(
        f"The threshold sweep produced {sweep_success} within-tolerance results across {len(sweep)} case and threshold combinations."
    )
    return {
        "observations": observations,
        "interpretation": [
            "The affine model can represent anisotropic scale and shear that a similarity model cannot, but the additional freedom requires stronger geometric guardrails.",
            "Feature count alone is not sufficient for reliable affine estimation. Spatial coverage, collinearity, RANSAC inlier consistency, and transform plausibility are recorded separately.",
            "Ratio filtering and RANSAC reprojection thresholds interact. A threshold that retains more correspondences is not automatically the setting with the lowest geometric error.",
            "Texture diagnostics are descriptive stratification variables. They help explain feature availability but do not by themselves determine registration success.",
        ],
        "failure_cases": failed_cases,
        "limitations": [
            "The Day 19 thresholds are development settings and are not frozen final benchmark settings.",
            "Texture labels use configured gradient-energy thresholds and a capped ORB detector, so the categories are specific to this experiment setup.",
            "The procedural repeated-pattern case is a controlled ambiguity probe and is not a substitute for diverse real repeated structures.",
            "Similarity and affine model comparisons are limited to the shared Day 19 cases and should not be generalized beyond the current benchmark.",
        ],
        "decision": "Carry the affine model, explicit failure rules, texture diagnostics, and evidence-supported threshold settings into the Day 20 integrated feature-based benchmark.",
    }


def _validated_report_exists(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    validation = payload.get("local_validation")
    return bool(
        payload.get("status") == "complete"
        and isinstance(validation, dict)
        and validation.get("status") == "complete"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Day 19 affine RANSAC, degeneracy, texture, and threshold experiments."
    )
    parser.add_argument(
        "--config",
        default="configs/week04_day04_ransac_affine_robustness.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output directory.")
    args = parser.parse_args()

    from image_registration.config import load_config

    config = load_config(_resolve(args.config))
    seed = int(config["experiment"].get("seed", 42))
    rng = np.random.default_rng(seed)
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

    sources = _load_sources(config)
    records: list[dict[str, Any]] = []
    contexts: dict[str, dict[str, Any]] = {}

    for index, case_raw in enumerate(config["cases"], start=1):
        case = dict(case_raw)
        fixed = sources[str(case["source"])]
        moving, ground_truth, control_points_moving, metadata = _build_affine_pair(
            fixed,
            case,
            rng=np.random.default_rng(seed + index),
        )
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
        affine_result = estimate_affine_ransac_from_matches(
            matching,
            fixed_features,
            moving_features,
            fixed_shape=fixed.shape,
            moving_shape=moving.shape,
            **_affine_kwargs(config, seed),
        )
        similarity_result = estimate_similarity_ransac_from_matches(
            matching,
            fixed_features,
            moving_features,
            **_similarity_kwargs(config, seed),
        )
        center = image_center(fixed.shape)
        affine_geometry = _geometry_metrics(
            affine_result.estimated_transform,
            ground_truth,
            control_points_moving,
            center,
            validation,
            estimator_success=affine_result.success,
        )
        similarity_record = _similarity_result_record(
            similarity_result,
            ground_truth,
            control_points_moving,
            center,
            validation,
        )
        texture = _texture_record(
            fixed,
            moving,
            fixed_features,
            moving_features,
            config,
        )
        record = {
            "case_id": str(case["id"]),
            "source_id": str(case["source"]),
            "condition_metadata": metadata,
            "texture": texture,
            "matching": {
                "success": bool(matching.success),
                "failure_reason": matching.failure_reason,
                "tentative_match_count": int(matching.tentative_count),
                "accepted_match_count": int(matching.accepted_count),
                "ratio_threshold": matching.ratio_threshold,
            },
            "affine_ransac": _affine_record(affine_result),
            "affine_geometry": affine_geometry,
            "similarity_baseline": similarity_record,
            "ground_truth_transform": ground_truth.tolist(),
        }
        records.append(record)
        contexts[str(case["id"])] = {
            "fixed": fixed,
            "moving": moving,
            "fixed_features": fixed_features,
            "moving_features": moving_features,
            "ground_truth": ground_truth,
            "control_points_moving": control_points_moving,
        }

        case_dir = output_dir / "cases" / str(case["id"])
        case_dir.mkdir(parents=True, exist_ok=True)
        save_grayscale_image(case_dir / "fixed.png", fixed)
        save_grayscale_image(case_dir / "moving.png", moving)
        _save_match_views(
            case_dir,
            fixed,
            moving,
            fixed_features,
            moving_features,
            matching,
            affine_result,
            maximum_drawn,
        )
        _save_residual_plot(
            case_dir / "affine_reprojection_residuals.png",
            affine_result,
            str(case["id"]),
        )
        if affine_result.estimated_transform is not None:
            registered = warp_image(
                moving,
                affine_result.estimated_transform,
                output_shape=fixed.shape[:2],
                interpolation="linear",
            )
            save_comparison_figure(
                fixed,
                moving,
                registered,
                case_dir / "affine_registration_comparison.png",
                title=f"{case['id']} - ORB + RANSAC affine",
            )
            save_rgb_image(case_dir / "affine_edge_overlay.png", edge_overlay(fixed, registered))

        status = "PASS" if affine_result.success and affine_geometry["within_tolerance"] else "CHECK"
        tre_text = "n/a" if affine_geometry["tre_pixels"] is None else f"{affine_geometry['tre_pixels']:.3f}"
        similarity_tre = similarity_record["geometry"]["tre_pixels"]
        similarity_text = "n/a" if similarity_tre is None else f"{similarity_tre:.3f}"
        ratio_text = "n/a" if affine_result.inlier_ratio is None else f"{affine_result.inlier_ratio:.3f}"
        print(
            f"{index:02d}/{len(config['cases']):02d} {case['id']:<31} "
            f"matches={matching.accepted_count:4d} inliers={affine_result.inlier_count:4d} "
            f"ratio={ratio_text:>5} affineTRE={tre_text:>7} simTRE={similarity_text:>7} {status}"
        )

    degeneracy_probes = _run_degeneracy_probes(config, seed)
    sweep = _threshold_sweep(config, contexts, seed)
    summary = _summarize(records)
    findings = _findings(records, degeneracy_probes, sweep)

    with (output_dir / "affine_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    _write_csv(output_dir / "affine_results.csv", records)
    with (output_dir / "degeneracy_probes.json").open("w", encoding="utf-8") as handle:
        json.dump(degeneracy_probes, handle, indent=2)
        handle.write("\n")
    with (output_dir / "threshold_sweep.json").open("w", encoding="utf-8") as handle:
        json.dump(sweep, handle, indent=2)
        handle.write("\n")
    if sweep:
        with (output_dir / "threshold_sweep.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(sweep[0].keys()))
            writer.writeheader()
            writer.writerows(sweep)
    _save_threshold_plot(output_dir / "threshold_sweep.png", sweep)
    _save_texture_plot(output_dir / "texture_vs_tre.png", records)
    _save_model_plot(output_dir / "similarity_vs_affine_tre.png", records)

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": summary,
                "degeneracy_probes": degeneracy_probes,
                "findings": findings,
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    report_payload = {
        "week": 4,
        "global_day": 19,
        "week_day": 4,
        "title": "Affine RANSAC, degeneracy checks, texture diagnostics, and threshold sweeps",
        "status": "implementation_complete_local_validation_pending",
        "scope": "feature-based affine estimation with robust failure rules and controlled robustness diagnostics",
        "configuration": {
            "orb": config["orb"],
            "matching": config["matching"],
            "ransac_affine": config["ransac_affine"],
            "ransac_similarity": config["ransac_similarity"],
            "validation": config["validation"],
            "texture": config["texture"],
            "threshold_sweep": config["threshold_sweep"],
        },
        "development_run": summary,
        "degeneracy_probes": degeneracy_probes,
        "case_results": records,
        "findings": findings,
        "raw_output_directory": str(config["output"]["directory"]),
        "daily_summary": "docs/daily/day_19_summary.md",
        "technical_note": "docs/RANSAC_AFFINE_ROBUSTNESS.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the full test suite and Day 19 experiment on the target Windows environment before marking Day 19 complete.",
        },
    }
    report_path = PROJECT_ROOT / "reports/week04_day04_ransac_affine_robustness.json"
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print("Tracked Day 19 report already contains completed target validation; preserving it.")
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nDay 19 development run summary")
    print(f"Affine RANSAC success: {summary['ransac_success_count']}/{summary['case_count']} cases")
    print(
        f"Within development tolerances: {summary['within_tolerance_count']}/{summary['case_count']} cases"
    )
    if summary["mean_inlier_ratio"] is not None:
        print(f"Mean inlier ratio: {summary['mean_inlier_ratio']:.3f}")
    if summary["median_tre_pixels"] is not None:
        print(f"Median affine TRE: {summary['median_tre_pixels']:.3f} px")
    if summary["maximum_tre_pixels"] is not None:
        print(f"Maximum affine TRE: {summary['maximum_tre_pixels']:.3f} px")
    print(
        "Degeneracy/plausibility probes: "
        f"{sum(p['passed'] for p in degeneracy_probes)}/{len(degeneracy_probes)} expected failures recorded"
    )
    print(f"Threshold sweep combinations: {len(sweep)}")
    print(f"Tracked report ({report_action}): reports/week04_day04_ransac_affine_robustness.json")


if __name__ == "__main__":
    main()
