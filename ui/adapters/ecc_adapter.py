"""Adapter for translation, rigid, and affine ECC registration."""

from __future__ import annotations

from time import perf_counter

from image_registration.ecc import ECCRegistration, MultiResolutionECCRegistration

from ui.core.contracts import AdapterResult, RegistrationRequest

from .common import (
    descriptive_metrics,
    failed_result,
    ground_truth_metrics,
    prepare_2d_pair,
    transform_parameters,
    transform_plausibility,
)


class ECCAdapter:
    def run(self, request: RegistrationRequest) -> AdapterResult:
        start = perf_counter()
        try:
            fixed, moving, preparation = prepare_2d_pair(request)
            params = request.registration.parameters
            model = request.registration.transform_model.value
            initialization = request.registration.initialization or str(params.get("initialization", "identity"))
            common = {
                "motion_model": model,
                "initialization": initialization,
                "max_iterations": int(params.get("max_iterations", 150)),
                "epsilon": float(params.get("epsilon", 1e-6)),
                "gauss_filt_size": int(params.get("gauss_filt_size", 5)),
                "interpolation": str(params.get("interpolation", "linear")),
                "phase_use_hanning_window": bool(params.get("phase_use_hanning_window", True)),
                "phase_subtract_mean": bool(params.get("phase_subtract_mean", True)),
                "min_ecc": params.get("min_ecc"),
            }
            if bool(params.get("multiresolution", False)):
                method = MultiResolutionECCRegistration(
                    **common,
                    pyramid_scales=tuple(params.get("pyramid_scales", (0.25, 0.5, 1.0))),
                    pre_smoothing_sigma=float(params.get("pre_smoothing_sigma", 0.8)),
                )
            else:
                method = ECCRegistration(**common)
            result = method.register(fixed, moving)
            diagnostics = dict(result.convergence_info or {})
            diagnostics["preparation"] = preparation
            if not result.success:
                return failed_result(
                    start=start,
                    failure_reason=result.failure_reason or "ecc_failed",
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
                transform_parameters=transform_parameters(result.transform, model),
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
