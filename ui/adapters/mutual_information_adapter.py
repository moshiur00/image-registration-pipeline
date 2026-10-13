"""Adapter for the validated 2D Mattes Mutual Information backend."""

from __future__ import annotations

from time import perf_counter

from image_registration.mutual_information import (
    MutualInformationAffineRegistration,
    MutualInformationConfig,
    MutualInformationRigidRegistration,
)

from ui.core.contracts import AdapterResult, RegistrationRequest

from .common import (
    descriptive_metrics,
    failed_result,
    ground_truth_metrics,
    prepare_2d_pair,
    transform_parameters,
    transform_plausibility,
)


class MutualInformationAdapter:
    def run(self, request: RegistrationRequest) -> AdapterResult:
        start = perf_counter()
        try:
            fixed, moving, preparation = prepare_2d_pair(request)
            params = request.registration.parameters
            config = MutualInformationConfig(
                histogram_bins=int(params.get("histogram_bins", 50)),
                sampling_strategy=str(params.get("sampling_strategy", "random")),
                sampling_percentage=float(params.get("sampling_percentage", 0.20)),
                sampling_seed=int(params.get("sampling_seed", 42)),
                learning_rate=float(params.get("learning_rate", 2.0)),
                minimum_step=float(params.get("minimum_step", 1e-3)),
                number_of_iterations=int(params.get("number_of_iterations", 200)),
                relaxation_factor=float(params.get("relaxation_factor", 0.5)),
                gradient_magnitude_tolerance=float(params.get("gradient_magnitude_tolerance", 1e-4)),
                shrink_factors=tuple(int(v) for v in params.get("shrink_factors", (4, 2, 1))),
                smoothing_sigmas=tuple(float(v) for v in params.get("smoothing_sigmas", (2.0, 1.0, 0.0))),
                initialization=request.registration.initialization or str(params.get("initialization", "geometry")),
            )
            method = (
                MutualInformationAffineRegistration(config)
                if request.registration.transform_model.value == "affine"
                else MutualInformationRigidRegistration(config)
            )
            result = method.register(fixed, moving)
            diagnostics = dict(result.convergence_info or {})
            diagnostics["preparation"] = preparation
            diagnostics["resolved_config"] = {
                "histogram_bins": config.histogram_bins,
                "sampling_strategy": config.sampling_strategy,
                "sampling_percentage": config.sampling_percentage,
                "sampling_seed": config.sampling_seed,
                "learning_rate": config.learning_rate,
                "minimum_step": config.minimum_step,
                "number_of_iterations": config.number_of_iterations,
                "relaxation_factor": config.relaxation_factor,
                "gradient_magnitude_tolerance": config.gradient_magnitude_tolerance,
                "shrink_factors": list(config.shrink_factors),
                "smoothing_sigmas": list(config.smoothing_sigmas),
                "initialization": config.initialization,
            }
            if not result.success:
                return failed_result(
                    start=start,
                    failure_reason=result.failure_reason or "mutual_information_failed",
                    diagnostics=diagnostics,
                    registered_array=result.registered_image,
                )
            plausible, reasons, plausibility_values = transform_plausibility(result.transform, fixed.shape)
            diagnostics["plausibility"] = plausibility_values
            gt_metrics, within = ground_truth_metrics(request, result.transform, fixed.shape)
            return AdapterResult(
                method_success=True,
                runtime_seconds=perf_counter() - start,
                transform_matrix=result.transform,
                registered_array=result.registered_image,
                transform_parameters=transform_parameters(result.transform, request.registration.transform_model.value),
                plausible=plausible,
                plausibility_reasons=reasons,
                descriptive_metrics_before=descriptive_metrics(fixed, moving),
                descriptive_metrics_after=descriptive_metrics(fixed, result.registered_image),
                ground_truth_metrics=gt_metrics,
                within_tolerance=within,
                diagnostics=diagnostics,
            )
        except (ValueError, RuntimeError, ImportError) as exc:
            return failed_result(start=start, failure_reason=f"{type(exc).__name__}: {exc}")
