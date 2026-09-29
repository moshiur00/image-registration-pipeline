from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from time import perf_counter
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

from image_registration.affine_ransac import estimate_affine_ransac_from_matches
from image_registration.config import load_config, resolve_project_path
from image_registration.degradations import apply_degradation, gaussian_blur
from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration
from image_registration.evaluation import normalized_cross_correlation, structural_similarity
from image_registration.feature_matching import draw_feature_matches, match_orb_knn_ratio
from image_registration.io import load_image
from image_registration.orb import ORBConfig, detect_orb_features
from image_registration.overlap import (
    apply_field_of_view,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
)
from image_registration.phase_correlation import PhaseCorrelationRegistration
from image_registration.ransac import estimate_similarity_ransac_from_matches, similarity_scale
from image_registration.registration_metrics import (
    affine_linear_error,
    centered_translation_error_pixels,
    mean_tre_pixels,
    rotation_error_degrees,
)
from image_registration.reporting import write_report_snapshot
from image_registration.synthetic import (
    default_control_points,
    generate_synthetic_pair,
    image_center,
    sample_ground_truth_transform,
)
from image_registration.visualization import (
    edge_overlay,
    save_comparison_figure,
    save_grayscale_image,
    save_rgb_image,
)
from image_registration.warping import warp_image
from image_registration.week4_baseline import (
    Week4Thresholds,
    paired_case_comparison,
    summarize_integrated_records,
    within_week4_tolerance,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Day 20 integrated feature-based benchmark and shared-case comparisons."
    )
    parser.add_argument(
        "--config",
        default="configs/week04_day05_integrated_feature_baseline.yaml",
        help="Project-relative or absolute YAML configuration path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing local output directory.",
    )
    return parser.parse_args()


def _resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if width <= 0 or height <= 0:
        raise ValueError("Working dimensions must be positive.")
    return cv2.resize(np.asarray(image), (width, height), interpolation=cv2.INTER_AREA)


def _checkerboard(height: int, width: int, block_size: int) -> np.ndarray:
    if height <= 0 or width <= 0 or block_size <= 0:
        raise ValueError("Checkerboard dimensions and block size must be positive.")
    yy, xx = np.indices((height, width))
    pattern = ((yy // block_size + xx // block_size) % 2) * 255
    return pattern.astype(np.uint8)


def _load_sources(config: dict[str, Any], width: int, height: int) -> dict[str, np.ndarray]:
    sources: dict[str, np.ndarray] = {}
    for source_id, specification in config.get("sources", {}).items():
        path = resolve_project_path(PROJECT_ROOT, specification["image"])
        loaded = load_image(path, color_mode=str(specification.get("color_mode", "grayscale")))
        image = np.asarray(loaded.array)
        if image.ndim != 2:
            raise ValueError(f"Source '{source_id}' must be a 2D grayscale image.")
        sources[str(source_id)] = _resize(image, width, height)

    for source_id, specification in config.get("generated_sources", {}).items():
        kind = str(specification.get("type", "")).strip().lower()
        if kind == "gaussian_blur":
            base = str(specification["base_source"])
            if base not in sources:
                raise ValueError(f"Generated source '{source_id}' references unknown source '{base}'.")
            sources[str(source_id)] = np.asarray(
                gaussian_blur(sources[base], sigma=float(specification.get("sigma", 8.0)))
            )
        elif kind == "checkerboard":
            sources[str(source_id)] = _checkerboard(
                int(specification.get("height", height)),
                int(specification.get("width", width)),
                int(specification.get("block_size", 24)),
            )
        else:
            raise ValueError(f"Unsupported generated source type: {kind}")
    if not sources:
        raise ValueError("At least one source image is required.")
    return sources


def _exact_ground_truth(case: dict[str, Any], image_shape: tuple[int, ...]):
    model = str(case["ground_truth_model"]).strip().lower()
    ranges: dict[str, list[float]] = {}
    names = ["tx", "ty", "angle_degrees", "scale", "scale_x", "scale_y", "shear_x"]
    defaults = {
        "tx": 0.0,
        "ty": 0.0,
        "angle_degrees": 0.0,
        "scale": 1.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "shear_x": 0.0,
    }
    for name in names:
        if name in case or name in {"tx", "ty"}:
            value = float(case.get(name, defaults[name]))
            ranges[name] = [value, value]
    return sample_ground_truth_transform(
        model,
        np.random.default_rng(0),
        image_shape,
        ranges,
    )


def _apply_condition(
    moving: np.ndarray,
    condition: dict[str, Any],
    *,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    kind = str(condition.get("type", "clean")).strip().lower()
    valid_mask = np.ones(moving.shape, dtype=np.uint8)
    if kind == "clean":
        return np.asarray(moving).copy(), valid_mask, {"type": "clean"}
    if kind == "restricted_fov":
        mask = rectangular_field_of_view_mask(
            moving.shape,
            width_fraction=float(condition.get("width_fraction", 0.75)),
            height_fraction=float(condition.get("height_fraction", 0.75)),
            center_x_fraction=float(condition.get("center_x_fraction", 0.50)),
            center_y_fraction=float(condition.get("center_y_fraction", 0.50)),
        )
        result = apply_field_of_view(moving, mask, fill_value=float(condition.get("fill_value", 0.0)))
        return result, mask, {
            "type": kind,
            "width_fraction": float(condition.get("width_fraction", 0.75)),
            "height_fraction": float(condition.get("height_fraction", 0.75)),
        }

    degraded = apply_degradation(moving, condition, rng=rng)
    return np.asarray(degraded.image), valid_mask, dict(degraded.metadata)


def _orb_config(config: dict[str, Any]) -> ORBConfig:
    section = config["orb"]
    return ORBConfig(
        n_features=int(section.get("n_features", 800)),
        scale_factor=float(section.get("scale_factor", 1.2)),
        n_levels=int(section.get("n_levels", 8)),
        edge_threshold=int(section.get("edge_threshold", 31)),
        first_level=int(section.get("first_level", 0)),
        wta_k=int(section.get("wta_k", 2)),
        score_type=str(section.get("score_type", "harris")),
        patch_size=int(section.get("patch_size", 31)),
        fast_threshold=int(section.get("fast_threshold", 20)),
    )


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


def _build_direct_method(method_id: str, config: dict[str, Any]):
    if method_id == "phase_correlation":
        section = config["phase_correlation"]
        return PhaseCorrelationRegistration(
            use_hanning_window=bool(section.get("use_hanning_window", True)),
            subtract_mean=bool(section.get("subtract_mean", True)),
            min_response=section.get("min_response"),
            interpolation=str(section.get("interpolation", "linear")),
        )

    if method_id in {"ecc_translation", "ecc_rigid", "ecc_affine_single"}:
        section = config[method_id]
        return ECCRegistration(
            motion_model=str(section["motion_model"]),
            initialization=str(section.get("initialization", "phase_correlation")),
            max_iterations=int(section.get("max_iterations", 150)),
            epsilon=float(section.get("epsilon", 1e-6)),
            gauss_filt_size=int(section.get("gauss_filt_size", 5)),
            interpolation=str(section.get("interpolation", "linear")),
        )

    if method_id == "ecc_affine_multiresolution":
        section = config[method_id]
        return MultiResolutionECCRegistration(
            motion_model=str(section["motion_model"]),
            initialization=str(section.get("initialization", "phase_correlation")),
            pyramid_scales=[float(value) for value in section.get("pyramid_scales", [0.25, 0.5, 1.0])],
            pre_smoothing_sigma=float(section.get("pre_smoothing_sigma", 0.8)),
            max_iterations=int(section.get("max_iterations", 140)),
            epsilon=float(section.get("epsilon", 1e-6)),
            gauss_filt_size=int(section.get("gauss_filt_size", 5)),
            interpolation=str(section.get("interpolation", "linear")),
        )

    raise ValueError(f"Unknown direct method: {method_id}")


def _run_feature_method(
    method_id: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    config: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    start = perf_counter()
    orb_config = _orb_config(config)
    fixed_features = detect_orb_features(fixed, config=orb_config)
    moving_features = detect_orb_features(moving, config=orb_config)
    matching = match_orb_knn_ratio(
        fixed_features,
        moving_features,
        ratio_threshold=float(config["matching"].get("ratio_threshold", 0.75)),
        maximum_distance=config["matching"].get("maximum_distance"),
        minimum_matches=int(config["matching"].get("minimum_matches", 8)),
        norm=str(config["matching"].get("norm", "hamming")),
    )

    if method_id == "orb_similarity":
        estimate = estimate_similarity_ransac_from_matches(
            matching,
            fixed_features,
            moving_features,
            **_similarity_kwargs(config, seed),
        )
    elif method_id == "orb_affine":
        estimate = estimate_affine_ransac_from_matches(
            matching,
            fixed_features,
            moving_features,
            fixed_shape=fixed.shape,
            moving_shape=moving.shape,
            **_affine_kwargs(config, seed),
        )
    else:
        raise ValueError(f"Unknown feature method: {method_id}")

    estimated_transform = estimate.estimated_transform
    if estimated_transform is None:
        registered = np.asarray(moving).copy()
    else:
        registered = warp_image(
            moving,
            estimated_transform,
            output_shape=fixed.shape[:2],
            interpolation="linear",
            border_value=0.0,
        )

    diagnostics: dict[str, Any] = {
        "fixed_keypoints": fixed_features.keypoint_count,
        "moving_keypoints": moving_features.keypoint_count,
        "accepted_matches": matching.accepted_count,
        "matching_success": bool(matching.success),
        "matching_failure_reason": matching.failure_reason,
        "inlier_count": estimate.inlier_count,
        "inlier_ratio": estimate.inlier_ratio,
        "ransac_failure_reason": estimate.failure_reason,
    }
    if method_id == "orb_similarity" and estimated_transform is not None:
        diagnostics["estimated_similarity_scale"] = similarity_scale(estimated_transform)
    if method_id == "orb_affine" and estimate.correspondence_geometry is not None:
        diagnostics["minimum_correspondence_coverage"] = (
            estimate.correspondence_geometry.minimum_grid_coverage
        )
    if method_id == "orb_affine" and estimate.transform_diagnostics is not None:
        diagnostics["affine_plausible"] = estimate.transform_diagnostics.plausible
        diagnostics["affine_rejection_reasons"] = list(
            estimate.transform_diagnostics.rejection_reasons
        )

    return {
        "success": bool(estimate.success),
        "failure_reason": estimate.failure_reason,
        "transform": None if estimated_transform is None else np.asarray(estimated_transform, dtype=np.float64),
        "registered": np.asarray(registered),
        "runtime_seconds": perf_counter() - start,
        "diagnostics": diagnostics,
        "fixed_features": fixed_features,
        "moving_features": moving_features,
        "matching": matching,
        "estimate": estimate,
    }


def _method_family(method_id: str) -> str:
    if method_id == "phase_correlation":
        return "frequency"
    if method_id.startswith("ecc_"):
        return "intensity"
    if method_id.startswith("orb_"):
        return "feature"
    raise ValueError(f"Unknown method family for {method_id}")


def _method_label(method_id: str) -> str:
    labels = {
        "phase_correlation": "Phase Correlation",
        "ecc_translation": "ECC Translation",
        "ecc_rigid": "ECC Rigid",
        "ecc_affine_single": "ECC Affine Single",
        "ecc_affine_multiresolution": "ECC Affine Multiresolution",
        "orb_similarity": "ORB + RANSAC Similarity",
        "orb_affine": "ORB + RANSAC Affine",
    }
    return labels[method_id]


def _method_model(method_id: str) -> str:
    mapping = {
        "phase_correlation": "translation",
        "ecc_translation": "translation",
        "ecc_rigid": "rigid",
        "ecc_affine_single": "affine",
        "ecc_affine_multiresolution": "affine",
        "orb_similarity": "similarity",
        "orb_affine": "affine",
    }
    return mapping[method_id]


def _safe_similarity_metric(function, fixed: np.ndarray, registered: np.ndarray, mask: np.ndarray) -> float | None:
    try:
        return float(function(fixed, registered, mask=mask.astype(bool)))
    except ValueError:
        return None


def _save_representative(
    output_dir: Path,
    case_id: str,
    method_id: str,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray,
    feature_payload: dict[str, Any] | None,
) -> None:
    folder = output_dir / "representative_cases" / f"{case_id}_{method_id}"
    folder.mkdir(parents=True, exist_ok=True)
    save_grayscale_image(folder / "fixed.png", fixed)
    save_grayscale_image(folder / "moving.png", moving)
    save_grayscale_image(folder / "registered.png", registered)
    save_rgb_image(folder / "edge_overlay_after.png", edge_overlay(fixed, registered))
    save_comparison_figure(
        fixed,
        moving,
        registered,
        folder / "registration_comparison.png",
        title=f"{case_id} - {_method_label(method_id)}",
    )

    if feature_payload is not None:
        fixed_features = feature_payload["fixed_features"]
        moving_features = feature_payload["moving_features"]
        matching = feature_payload["matching"]
        estimate = feature_payload["estimate"]
        save_rgb_image(
            folder / "accepted_matches.png",
            draw_feature_matches(
                fixed,
                moving,
                fixed_features,
                moving_features,
                matching.accepted_matches,
                maximum_drawn=80,
            ),
        )
        if estimate.inlier_mask.size == len(matching.accepted_matches):
            inliers = tuple(
                match
                for match, keep in zip(matching.accepted_matches, estimate.inlier_mask, strict=True)
                if bool(keep)
            )
            save_rgb_image(
                folder / "ransac_inliers.png",
                draw_feature_matches(
                    fixed,
                    moving,
                    fixed_features,
                    moving_features,
                    inliers,
                    maximum_drawn=80,
                ),
            )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "source_id",
        "scope",
        "comparison_group",
        "condition",
        "ground_truth_model",
        "method_id",
        "method_label",
        "method_family",
        "method_model",
        "success",
        "within_tolerance",
        "failure_reason",
        "mean_tre_pixels",
        "translation_error_pixels",
        "rotation_error_degrees",
        "affine_linear_error",
        "overlap_fraction",
        "ncc_after",
        "ssim_after",
        "runtime_ms",
        "feature_fixed_keypoints",
        "feature_moving_keypoints",
        "feature_accepted_matches",
        "feature_inlier_count",
        "feature_inlier_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            diagnostics = record.get("diagnostics", {})
            writer.writerow(
                {
                    **{field: record.get(field) for field in fields if not field.startswith("feature_")},
                    "feature_fixed_keypoints": diagnostics.get("fixed_keypoints"),
                    "feature_moving_keypoints": diagnostics.get("moving_keypoints"),
                    "feature_accepted_matches": diagnostics.get("accepted_matches"),
                    "feature_inlier_count": diagnostics.get("inlier_count"),
                    "feature_inlier_ratio": diagnostics.get("inlier_ratio"),
                }
            )


def _save_group_plot(
    output_dir: Path,
    records: list[dict[str, Any]],
    group: str,
    method_ids: list[str],
) -> None:
    selected = [record for record in records if record["comparison_group"] == group]
    case_ids = sorted({str(record["case_id"]) for record in selected})
    if not case_ids:
        return
    fig, axis = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(case_ids), dtype=float)
    width = 0.8 / len(method_ids)
    for index, method_id in enumerate(method_ids):
        values: list[float] = []
        for case_id in case_ids:
            matches = [
                record
                for record in selected
                if record["case_id"] == case_id and record["method_id"] == method_id
            ]
            value = matches[0]["mean_tre_pixels"] if matches else None
            values.append(np.nan if value is None else float(value))
        offset = (index - (len(method_ids) - 1) / 2.0) * width
        axis.bar(x + offset, values, width=width, label=_method_label(method_id))
    axis.set_xticks(x)
    axis.set_xticklabels(case_ids, rotation=30, ha="right")
    axis.set_ylabel("Mean TRE (pixels)")
    axis.set_title(f"Shared {group} cases")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "plots" / f"{group}_shared_case_tre.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _save_feature_diagnostic_plot(output_dir: Path, records: list[dict[str, Any]]) -> None:
    selected = [
        record
        for record in records
        if record["scope"] == "feature_diagnostic" and record["method_id"] == "orb_affine"
    ]
    if not selected:
        return
    labels = [record["case_id"] for record in selected]
    matches = [float(record["diagnostics"].get("accepted_matches", 0)) for record in selected]
    inliers = [float(record["diagnostics"].get("inlier_count", 0)) for record in selected]
    x = np.arange(len(labels), dtype=float)
    fig, axis = plt.subplots(figsize=(7.5, 4.8))
    axis.bar(x - 0.18, matches, width=0.36, label="Filtered matches")
    axis.bar(x + 0.18, inliers, width=0.36, label="RANSAC inliers")
    axis.set_xticks(x)
    axis.set_xticklabels(labels, rotation=20, ha="right")
    axis.set_ylabel("Count")
    axis.set_title("Feature diagnostic cases")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "plots" / "feature_diagnostic_support.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


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


def _findings(
    records: list[dict[str, Any]],
    group_summaries: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    feature_failures = [
        {"case_id": record["case_id"], "failure_reason": record["failure_reason"]}
        for record in records
        if record["scope"] == "feature_diagnostic" and not record["within_tolerance"]
    ]
    observations: list[str] = []
    for group in ["translation", "rigid", "affine"]:
        summary = group_summaries[group]
        for method_id, values in summary.items():
            median = values.get("median_tre_pixels")
            if median is not None:
                observations.append(
                    f"{_method_label(method_id)} recorded median TRE {median:.3f} px across the shared {group} cases assigned to that comparison."
                )
    for failure in feature_failures:
        observations.append(
            f"Feature diagnostic case {failure['case_id']} did not meet the development criterion; recorded reason: {failure['failure_reason']}."
        )

    return {
        "observations": observations,
        "interpretation": [
            "The integrated benchmark keeps comparison groups separate so methods are compared only on shared cases with compatible geometric intent.",
            "Translation, rigid, and affine results are not combined into one universal ranking because the supported motion models and model flexibility differ.",
            "Feature matching success, RANSAC estimation success, and ground-truth geometric success remain separate recorded states.",
            "The low-texture and repeated-pattern cases are diagnostic failure probes and are reported separately from the shared comparison groups.",
        ],
        "limitations": [
            "The current thresholds are development thresholds and are not frozen final benchmark criteria.",
            "The integrated comparison uses a compact controlled subset and does not establish general method superiority.",
            "ORB similarity has one scale degree of freedom beyond ECC rigid on the rigid comparison group, so that comparison is a shared-case behavior comparison rather than an equal-complexity model comparison.",
            "The current comparison remains monomodal. Real and simulated multimodal method comparison is reserved for the mutual-information stage.",
        ],
        "failure_cases": feature_failures,
        "decision": "Carry the shared-case comparison policy, explicit feature failure records, and integrated result schema into the later unified evaluation framework.",
    }


def main() -> None:
    args = _parse_args()
    config_path = resolve_project_path(PROJECT_ROOT, args.config)
    config = load_config(config_path)
    seed = int(config.get("experiment", {}).get("seed", 42))

    size = config.get("working_size", {})
    width = int(size.get("width", 256))
    height = int(size.get("height", 256))
    sources = _load_sources(config, width, height)
    cases = list(config.get("cases", []))
    if not cases:
        raise ValueError("cases must not be empty.")

    thresholds = Week4Thresholds(**{key: float(value) for key, value in config["validation"].items()})

    output_dir = resolve_project_path(PROJECT_ROOT, config["output"]["directory"])
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory already exists and is not empty: {output_dir}. Use --overwrite to replace it."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "plots").mkdir(parents=True, exist_ok=True)
    with (output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    representative = {tuple(item) for item in config.get("representative_outputs", [])}
    records: list[dict[str, Any]] = []
    total_runs = sum(len(case.get("methods", [])) for case in cases)

    print("Day 20 integrated feature-based benchmark")
    print(f"Cases: {len(cases)}")
    print(f"Planned registrations: {total_runs}")

    run_index = 0
    for case_index, case in enumerate(cases):
        case_id = str(case["id"])
        source_id = str(case["source"])
        if source_id not in sources:
            raise ValueError(f"Unknown source '{source_id}' for case '{case_id}'.")
        fixed = np.asarray(sources[source_id])
        ground_truth = _exact_ground_truth(case, fixed.shape)
        pair = generate_synthetic_pair(fixed, ground_truth, interpolation="linear")
        moving, moving_valid_mask, condition_metadata = _apply_condition(
            np.asarray(pair.moving),
            dict(case.get("condition", {"type": "clean"})),
            rng=np.random.default_rng(seed + case_index * 1009),
        )
        overlap_mask = overlap_mask_in_fixed_space(
            moving_valid_mask,
            ground_truth.moving_to_fixed,
            fixed_shape=fixed.shape,
        )
        overlap = overlap_fraction(overlap_mask)
        points = default_control_points(fixed.shape)
        center = image_center(fixed.shape)

        for method_offset, method_id_raw in enumerate(case.get("methods", [])):
            run_index += 1
            method_id = str(method_id_raw)
            method_seed = seed + case_index * 1009 + method_offset * 31
            feature_payload: dict[str, Any] | None = None

            if method_id.startswith("orb_"):
                feature_payload = _run_feature_method(method_id, fixed, moving, config, method_seed)
                success = bool(feature_payload["success"])
                failure_reason = feature_payload["failure_reason"]
                estimated = feature_payload["transform"]
                registered = np.asarray(feature_payload["registered"])
                runtime_seconds = float(feature_payload["runtime_seconds"])
                diagnostics = dict(feature_payload["diagnostics"])
            else:
                registration = _build_direct_method(method_id, config)
                result = registration.register(fixed, moving)
                success = bool(result.success)
                failure_reason = result.failure_reason
                estimated = np.asarray(result.transform, dtype=np.float64)
                registered = np.asarray(result.registered_image)
                runtime_seconds = float(result.runtime_seconds)
                diagnostics = dict(result.convergence_info)

            if estimated is None:
                tre = None
                translation_error = None
                rotation_error = None
                linear_error = None
                within = False
                estimated_json = None
            else:
                estimated_array = np.asarray(estimated, dtype=np.float64)
                tre = mean_tre_pixels(ground_truth.moving_to_fixed, estimated_array, points)
                translation_error = centered_translation_error_pixels(
                    ground_truth.moving_to_fixed,
                    estimated_array,
                    center,
                )
                rotation_error = (
                    rotation_error_degrees(ground_truth.moving_to_fixed, estimated_array)
                    if str(case["ground_truth_model"]) == "rigid"
                    else None
                )
                linear_error = (
                    affine_linear_error(ground_truth.moving_to_fixed, estimated_array)
                    if str(case["ground_truth_model"]) == "affine"
                    else None
                )
                within = within_week4_tolerance(
                    str(case["ground_truth_model"]),
                    success=success,
                    mean_tre_pixels=tre,
                    translation_error_pixels=translation_error,
                    rotation_error_degrees=rotation_error,
                    affine_linear_error=linear_error,
                    thresholds=thresholds,
                )
                estimated_json = estimated_array.tolist()

            record = {
                "case_id": case_id,
                "source_id": source_id,
                "scope": str(case.get("scope", "shared_comparison")),
                "comparison_group": str(case.get("comparison_group", "unassigned")),
                "condition": str(condition_metadata.get("type", "clean")),
                "condition_metadata": condition_metadata,
                "ground_truth_model": str(case["ground_truth_model"]),
                "method_id": method_id,
                "method_label": _method_label(method_id),
                "method_family": _method_family(method_id),
                "method_model": _method_model(method_id),
                "success": success,
                "within_tolerance": bool(within),
                "failure_reason": failure_reason,
                "mean_tre_pixels": None if tre is None else float(tre),
                "translation_error_pixels": None if translation_error is None else float(translation_error),
                "rotation_error_degrees": None if rotation_error is None else float(rotation_error),
                "affine_linear_error": None if linear_error is None else float(linear_error),
                "overlap_fraction": float(overlap),
                "ncc_after": _safe_similarity_metric(
                    normalized_cross_correlation, fixed, registered, overlap_mask
                ),
                "ssim_after": _safe_similarity_metric(
                    structural_similarity, fixed, registered, overlap_mask
                ),
                "runtime_ms": runtime_seconds * 1000.0,
                "ground_truth_transform": ground_truth.moving_to_fixed.tolist(),
                "estimated_transform": estimated_json,
                "diagnostics": diagnostics,
            }
            records.append(record)

            if (case_id, method_id) in representative:
                _save_representative(
                    output_dir,
                    case_id,
                    method_id,
                    fixed,
                    moving,
                    registered,
                    feature_payload,
                )

            tre_text = "n/a" if tre is None else f"{tre:.3f}"
            state = "PASS" if within else "CHECK"
            print(
                f"{run_index:02d}/{total_runs:02d} {case_id:<36} {method_id:<30} "
                f"TRE={tre_text:>7} runtime={runtime_seconds * 1000.0:7.2f} ms {state}"
            )

    with (output_dir / "integrated_results.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, sort_keys=True)
        handle.write("\n")
    _write_csv(output_dir / "integrated_results.csv", records)

    shared_records = [record for record in records if record["scope"] == "shared_comparison"]
    feature_diagnostic_records = [record for record in records if record["scope"] == "feature_diagnostic"]
    method_summary = summarize_integrated_records(records, "method_id")
    group_summaries = {
        group: summarize_integrated_records(
            [record for record in shared_records if record["comparison_group"] == group],
            "method_id",
        )
        for group in ["translation", "rigid", "affine"]
    }
    paired = {
        "translation": paired_case_comparison(
            shared_records,
            method_ids=("phase_correlation", "ecc_translation", "orb_similarity"),
            group="translation",
        ),
        "rigid": paired_case_comparison(
            shared_records,
            method_ids=("ecc_rigid", "orb_similarity"),
            group="rigid",
        ),
        "affine": paired_case_comparison(
            shared_records,
            method_ids=("ecc_affine_single", "ecc_affine_multiresolution", "orb_affine"),
            group="affine",
        ),
    }
    findings = _findings(records, group_summaries)

    _save_group_plot(
        output_dir,
        records,
        "translation",
        ["phase_correlation", "ecc_translation", "orb_similarity"],
    )
    _save_group_plot(output_dir, records, "rigid", ["ecc_rigid", "orb_similarity"])
    _save_group_plot(
        output_dir,
        records,
        "affine",
        ["ecc_affine_single", "ecc_affine_multiresolution", "orb_affine"],
    )
    _save_feature_diagnostic_plot(output_dir, records)

    summary = {
        "case_count": len(cases),
        "registration_count": len(records),
        "shared_case_count": len({record["case_id"] for record in shared_records}),
        "feature_diagnostic_case_count": len({record["case_id"] for record in feature_diagnostic_records}),
        "success_count": sum(bool(record["success"]) for record in records),
        "within_tolerance_count": sum(bool(record["within_tolerance"]) for record in records),
        "method_summary": method_summary,
        "shared_group_summaries": group_summaries,
        "paired_shared_case_comparisons": paired,
        "feature_diagnostic_results": feature_diagnostic_records,
        "findings": findings,
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    report_payload = {
        "week": 4,
        "week_day": 5,
        "global_day": 20,
        "title": "Integrated feature-based benchmark and shared-case comparison",
        "status": "implementation_complete_local_validation_pending",
        "scope": "Integrated monomodal comparison of frequency, intensity, and feature-based registration on explicitly shared case groups",
        "development_run": summary,
        "tolerances": config["validation"],
        "fair_comparison_policy": {
            "translation": "Phase Correlation, ECC Translation, and ORB + RANSAC Similarity are compared on the same four translation cases.",
            "rigid": "ECC Rigid and ORB + RANSAC Similarity are compared on the same three rigid cases. ORB Similarity has one additional scale degree of freedom, so this is a shared-case behavior comparison rather than an equal-complexity model comparison.",
            "affine": "ECC Affine Single, ECC Affine Multiresolution, and ORB + RANSAC Affine are compared on the same four affine cases with the same affine target geometry.",
            "feature_diagnostics": "Low-texture and repeated-pattern cases are reported separately and are not included in cross-family method rankings.",
        },
        "raw_output_directory": str(config["output"]["directory"]),
        "daily_summary": "docs/daily/day_20_summary.md",
        "weekly_summary": "docs/weekly/week_04_summary.md",
        "technical_note": "docs/WEEK04_FEATURE_BASELINE_COMPARISON.md",
        "local_validation": {
            "status": "pending",
            "note": "Run the full test suite and Day 20 experiment on the target Windows environment before marking Day 20 and Week 4 complete.",
        },
    }
    report_path = resolve_project_path(PROJECT_ROOT, config["output"]["report_snapshot"])
    if _validated_report_exists(report_path):
        report_action = "preserved"
        print("Tracked Day 20 report already contains completed target validation; preserving it.")
    else:
        write_report_snapshot(report_path, report_payload)
        report_action = "refreshed"

    print("\nDay 20 development run summary")
    print(f"Cases: {summary['case_count']}")
    print(f"Registrations: {summary['registration_count']}")
    print(f"Method successes: {summary['success_count']}/{summary['registration_count']}")
    print(
        f"Within development tolerances: {summary['within_tolerance_count']}/{summary['registration_count']}"
    )
    for group in ["translation", "rigid", "affine"]:
        print(f"{group.capitalize()} shared cases:")
        for method_id, values in group_summaries[group].items():
            median = values["median_tre_pixels"]
            median_text = "n/a" if median is None else f"{median:.3f} px"
            print(
                f"  {method_id:<31} pass={values['within_tolerance_count']}/{values['registration_count']} "
                f"median TRE={median_text}"
            )
    print(f"Feature diagnostic cases: {summary['feature_diagnostic_case_count']}")
    print(f"Tracked report ({report_action}): {config['output']['report_snapshot']}")


if __name__ == "__main__":
    main()
