"""Shared ORB/SIFT matching and RANSAC adapter."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter

from image_registration.affine_ransac import (
    estimate_affine_ransac_from_matches,
    residual_summary as affine_residual_summary,
)
from image_registration.feature_matching import (
    correspondence_grid_coverage,
    match_distance_summary,
    match_feature_knn_ratio,
)
from image_registration.orb import ORBConfig, detect_orb_features
from image_registration.ransac import (
    estimate_similarity_ransac_from_matches,
    residual_summary as similarity_residual_summary,
)
from image_registration.sift import SIFTConfig, detect_sift_features
from image_registration.warping import warp_image

from ui.core.contracts import AdapterResult, RegistrationRequest

from .common import (
    descriptive_metrics,
    failed_result,
    ground_truth_metrics,
    prepare_2d_pair,
    transform_parameters,
    transform_plausibility,
)


class FeatureRegistrationAdapter:
    def run(self, request: RegistrationRequest) -> AdapterResult:
        start = perf_counter()
        try:
            fixed, moving, preparation = prepare_2d_pair(request)
            params = request.registration.parameters
            use_sift = request.registration.method_id.startswith("sift_")
            if use_sift:
                feature_config = SIFTConfig(
                    n_features=int(params.get("n_features", 800)),
                    n_octave_layers=int(params.get("n_octave_layers", 3)),
                    contrast_threshold=float(params.get("contrast_threshold", 0.04)),
                    edge_threshold=float(params.get("edge_threshold", 10.0)),
                    sigma=float(params.get("sigma", 1.6)),
                )
                fixed_features = detect_sift_features(fixed, config=feature_config)
                moving_features = detect_sift_features(moving, config=feature_config)
                metric = "l2"
            else:
                feature_config = ORBConfig(
                    n_features=int(params.get("n_features", 800)),
                    scale_factor=float(params.get("scale_factor", 1.2)),
                    n_levels=int(params.get("n_levels", 8)),
                    edge_threshold=int(params.get("edge_threshold", 31)),
                    fast_threshold=int(params.get("fast_threshold", 20)),
                )
                fixed_features = detect_orb_features(fixed, config=feature_config)
                moving_features = detect_orb_features(moving, config=feature_config)
                metric = "hamming"

            matches = match_feature_knn_ratio(
                fixed_features,
                moving_features,
                metric=metric,
                ratio_threshold=float(params.get("ratio_threshold", 0.75)),
                maximum_distance=params.get("maximum_distance"),
                minimum_matches=int(params.get("minimum_matches", 6 if request.registration.transform_model.value == "affine" else 4)),
            )
            coverage = correspondence_grid_coverage(matches, fixed_features, moving_features)

            ransac_common = {
                "reprojection_threshold": float(params.get("reprojection_threshold", 3.0)),
                "confidence": float(params.get("confidence", 0.99)),
                "max_trials": int(params.get("max_trials", 3000 if request.registration.transform_model.value == "affine" else 2000)),
                "refine_iterations": int(params.get("refine_iterations", 10)),
                "minimum_inliers": int(params.get("minimum_inliers", 6 if request.registration.transform_model.value == "affine" else 4)),
                "minimum_inlier_ratio": float(params.get("minimum_inlier_ratio", 0.0)),
            }
            if request.registration.transform_model.value == "affine":
                ransac = estimate_affine_ransac_from_matches(
                    matches,
                    fixed_features,
                    moving_features,
                    fixed_shape=fixed.shape,
                    moving_shape=moving.shape,
                    minimum_matches=int(params.get("minimum_matches", 6)),
                    minimum_spatial_coverage=float(params.get("minimum_spatial_coverage", 0.125)),
                    random_seed=int(params.get("random_seed", 42)),
                    **ransac_common,
                )
                residuals = affine_residual_summary(ransac)
                affine_diag = asdict(ransac.transform_diagnostics) if ransac.transform_diagnostics else None
                geometry_diag = asdict(ransac.correspondence_geometry) if ransac.correspondence_geometry else None
                plausible = None if ransac.transform_diagnostics is None else bool(ransac.transform_diagnostics.plausible)
                plausibility_reasons = () if ransac.transform_diagnostics is None else tuple(ransac.transform_diagnostics.rejection_reasons)
            else:
                ransac = estimate_similarity_ransac_from_matches(
                    matches,
                    fixed_features,
                    moving_features,
                    minimum_matches=int(params.get("minimum_matches", 4)),
                    **ransac_common,
                )
                residuals = similarity_residual_summary(ransac)
                affine_diag = None
                geometry_diag = None
                plausible = None
                plausibility_reasons = ()

            diagnostics = {
                "feature_type": "sift" if use_sift else "orb",
                "fixed_keypoints": fixed_features.keypoint_count,
                "moving_keypoints": moving_features.keypoint_count,
                "feature_detection_seconds": float(fixed_features.runtime_seconds + moving_features.runtime_seconds),
                "matching_success": bool(matches.success),
                "tentative_matches": matches.tentative_count,
                "accepted_matches": matches.accepted_count,
                "match_acceptance_rate": matches.acceptance_rate,
                "match_distance": match_distance_summary(matches.accepted_matches),
                "fixed_match_coverage": coverage.fixed_coverage,
                "moving_match_coverage": coverage.moving_coverage,
                "minimum_match_coverage": coverage.minimum_coverage,
                "ransac_success": bool(ransac.success),
                "ransac_inliers": ransac.inlier_count,
                "ransac_outliers": ransac.outlier_count,
                "ransac_inlier_ratio": ransac.inlier_ratio,
                "residuals": residuals,
                "affine_transform_diagnostics": affine_diag,
                "correspondence_geometry": geometry_diag,
                "preparation": preparation,
            }
            if not ransac.success or ransac.estimated_transform is None:
                return failed_result(
                    start=start,
                    failure_reason=ransac.failure_reason or matches.failure_reason or "feature_registration_failed",
                    diagnostics=diagnostics,
                )

            transform = ransac.estimated_transform
            registered = warp_image(
                moving,
                transform,
                output_shape=(int(fixed.shape[0]), int(fixed.shape[1])),
                interpolation=str(params.get("interpolation", "linear")),
                border_value=0.0,
            )
            if plausible is None:
                plausible, plausibility_reasons, plausibility_values = transform_plausibility(transform, fixed.shape)
                diagnostics["plausibility"] = plausibility_values
            gt_metrics, within = ground_truth_metrics(request, transform, fixed.shape)
            return AdapterResult(
                method_success=True,
                runtime_seconds=perf_counter() - start,
                transform_matrix=transform,
                registered_array=registered,
                transform_parameters=transform_parameters(transform, request.registration.transform_model.value),
                plausible=plausible,
                plausibility_reasons=plausibility_reasons,
                descriptive_metrics_before=descriptive_metrics(fixed, moving),
                descriptive_metrics_after=descriptive_metrics(fixed, registered),
                ground_truth_metrics=gt_metrics,
                within_tolerance=within,
                diagnostics=diagnostics,
            )
        except (ValueError, RuntimeError, ImportError) as exc:
            return failed_result(start=start, failure_reason=f"{type(exc).__name__}: {exc}")
