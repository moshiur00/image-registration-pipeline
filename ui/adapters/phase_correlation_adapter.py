"""Adapter for the validated Phase Correlation backend."""

from __future__ import annotations

from time import perf_counter

from image_registration.phase_correlation import PhaseCorrelationRegistration

from ui.core.contracts import AdapterResult, RegistrationRequest

from .common import (
    descriptive_metrics,
    failed_result,
    ground_truth_metrics,
    prepare_2d_pair,
    transform_parameters,
    transform_plausibility,
)


class PhaseCorrelationAdapter:
    def run(self, request: RegistrationRequest) -> AdapterResult:
        start = perf_counter()
        try:
            fixed, moving, preparation = prepare_2d_pair(request)
            params = request.registration.parameters
            method = PhaseCorrelationRegistration(
                use_hanning_window=bool(params.get("use_hanning_window", True)),
                subtract_mean=bool(params.get("subtract_mean", True)),
                interpolation=str(params.get("interpolation", "linear")),
                min_response=params.get("min_response"),
            )
            result = method.register(fixed, moving)
            diagnostics = dict(result.convergence_info or {})
            diagnostics["preparation"] = preparation
            if not result.success:
                return failed_result(
                    start=start,
                    failure_reason=result.failure_reason or "phase_correlation_failed",
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
                transform_parameters=transform_parameters(result.transform, "translation"),
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
