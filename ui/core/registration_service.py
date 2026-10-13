"""Framework-neutral orchestration service used by current and future clients."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping, Protocol

import numpy as np

from image_registration.conventions import STORED_TRANSFORM_DIRECTION

from .contracts import (
    AdapterResult,
    DiagnosticSummary,
    ImageSource,
    MetricSummary,
    ProvenanceSummary,
    RegistrationRequest,
    RegistrationRun,
    TransformSummary,
)
from .enums import GroundTruthStatus, RunStatus
from .method_registry import DEFAULT_METHOD_REGISTRY, MethodDescriptor, MethodRegistry
from .result_presenter import registration_run_summary, to_json_safe
from .validation import ValidationReport, evidence_policy, validate_request


class RegistrationAdapter(Protocol):
    """Stage 3 adapter contract consumed by RegistrationService."""

    def run(self, request: RegistrationRequest) -> AdapterResult:
        """Execute one normalized request."""
        ...


class ExampleProvider(Protocol):
    """Optional source of curated examples, implemented in Stage 3."""

    def list_examples(self) -> list[object]:
        ...


def _package_version() -> str:
    try:
        return importlib.metadata.version("image-registration-pipeline")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0-dev"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_image_source(source: ImageSource) -> str | None:
    """Compute a content hash when source bytes are available without decoding."""
    if source.content_bytes is not None:
        return _sha256_bytes(source.content_bytes)

    if source.array is not None:
        array = np.ascontiguousarray(source.array)
        digest = hashlib.sha256()
        digest.update(str(array.dtype).encode("utf-8"))
        digest.update(repr(tuple(array.shape)).encode("utf-8"))
        digest.update(array.tobytes(order="C"))
        return digest.hexdigest()

    if source.path is not None:
        path = Path(source.path)
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()

    return None


def _request_parameter_summary(request: RegistrationRequest) -> dict[str, object]:
    return {
        "transform_model": request.registration.transform_model.value,
        "initialization": request.registration.initialization,
        "parameters": to_json_safe(request.registration.parameters),
        "interpolation": request.registration.interpolation,
    }


def _preprocessing_summary(request: RegistrationRequest) -> dict[str, object]:
    return to_json_safe(asdict(request.preprocessing))


class RegistrationService:
    """Validate, dispatch, normalize, and export registration results."""

    def __init__(
        self,
        *,
        method_registry: MethodRegistry = DEFAULT_METHOD_REGISTRY,
        adapters: Mapping[str, RegistrationAdapter] | None = None,
        example_provider: ExampleProvider | None = None,
        version_provider: Callable[[], str] = _package_version,
    ) -> None:
        self._method_registry = method_registry
        self._adapters = dict(adapters or {})
        self._example_provider = example_provider
        self._version_provider = version_provider

    def list_methods(self) -> list[MethodDescriptor]:
        """List transport-independent method descriptors."""
        return self._method_registry.list()

    def list_examples(self) -> list[object]:
        """List curated examples when a Stage 3 provider is configured."""
        if self._example_provider is None:
            return []
        return list(self._example_provider.list_examples())

    def validate(self, request: RegistrationRequest) -> ValidationReport:
        """Validate a request without executing a registration method."""
        return validate_request(request, self._method_registry)

    def _provenance(self, request: RegistrationRequest) -> ProvenanceSummary:
        return ProvenanceSummary(
            fixed_sha256=hash_image_source(request.fixed),
            moving_sha256=hash_image_source(request.moving),
            method_id=request.registration.method_id,
            normalized_parameters=_request_parameter_summary(request),
            preprocessing=_preprocessing_summary(request),
            transform_direction=STORED_TRANSFORM_DIRECTION,
            package_version=self._version_provider(),
            ground_truth_status=request.evaluation.ground_truth_status,
        )

    def _validation_error_run(
        self,
        request: RegistrationRequest,
        report: ValidationReport,
    ) -> RegistrationRun:
        warnings = tuple(issue.message for issue in report.issues)
        return RegistrationRun(
            request_id=request.request_id,
            run_status=RunStatus.VALIDATION_ERROR,
            method_success=False,
            transform=None,
            metrics=MetricSummary(units=request.evaluation.units),
            diagnostics=DiagnosticSummary(
                values={"validation_codes": [issue.code for issue in report.issues]}
            ),
            runtime_seconds=0.0,
            warnings=warnings,
            provenance=self._provenance(request),
            failure_reason="Request validation failed.",
        )

    def _adapter_missing_run(self, request: RegistrationRequest, adapter_id: str) -> RegistrationRun:
        return RegistrationRun(
            request_id=request.request_id,
            run_status=RunStatus.FAILED,
            method_success=False,
            transform=None,
            metrics=MetricSummary(units=request.evaluation.units),
            diagnostics=DiagnosticSummary(values={"adapter_id": adapter_id}),
            runtime_seconds=0.0,
            warnings=("Registration adapters are implemented in UI Stage 3.",),
            provenance=self._provenance(request),
            failure_reason=f"Adapter not registered: {adapter_id}",
        )

    def run(self, request: RegistrationRequest) -> RegistrationRun:
        """Run a validated request through a registered adapter and normalize evidence."""
        report = self.validate(request)
        if not report.valid:
            return self._validation_error_run(request, report)

        descriptor = self._method_registry.require(request.registration.method_id)
        adapter = self._adapters.get(descriptor.adapter_id)
        if adapter is None:
            return self._adapter_missing_run(request, descriptor.adapter_id)

        adapter_result = adapter.run(request)
        policy = evidence_policy(request)

        ground_truth = (
            dict(adapter_result.ground_truth_metrics) if policy.allow_ground_truth_metrics else {}
        )
        within_tolerance = (
            adapter_result.within_tolerance if policy.allow_geometric_status else None
        )

        transform = None
        if adapter_result.transform_matrix is not None:
            transform = TransformSummary(
                matrix=np.asarray(adapter_result.transform_matrix, dtype=np.float64),
                motion_model=request.registration.transform_model,
                direction=STORED_TRANSFORM_DIRECTION,
                parameters=dict(adapter_result.transform_parameters),
                plausible=adapter_result.plausible,
                plausibility_reasons=tuple(adapter_result.plausibility_reasons),
            )

        if not adapter_result.method_success:
            status = RunStatus.FAILED
        elif adapter_result.plausible is False:
            status = RunStatus.CHECK
        elif policy.allow_geometric_status and within_tolerance is False:
            status = RunStatus.CHECK
        else:
            status = RunStatus.COMPLETED

        warnings = list(report.warnings)
        warning_messages = [issue.message for issue in warnings]
        warning_messages.extend(adapter_result.warnings)
        if request.evaluation.ground_truth_status is not GroundTruthStatus.KNOWN:
            warning_messages.append(
                "Ground truth is unavailable; TRE and geometric PASS are not reported."
            )

        return RegistrationRun(
            request_id=request.request_id,
            run_status=status,
            method_success=adapter_result.method_success,
            transform=transform,
            metrics=MetricSummary(
                before=dict(adapter_result.descriptive_metrics_before),
                after=dict(adapter_result.descriptive_metrics_after),
                ground_truth=ground_truth,
                within_tolerance=within_tolerance,
                units=request.evaluation.units,
            ),
            diagnostics=DiagnosticSummary(values=dict(adapter_result.diagnostics)),
            runtime_seconds=float(adapter_result.runtime_seconds),
            warnings=tuple(warning_messages),
            provenance=self._provenance(request),
            registered_array=adapter_result.registered_array,
            failure_reason=adapter_result.failure_reason,
        )

    def export_summary(self, run: RegistrationRun) -> bytes:
        """Serialize a compact run summary for download or future API transport."""
        payload = registration_run_summary(run)
        return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
