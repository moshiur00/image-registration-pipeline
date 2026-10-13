"""Request validation and evidence-policy rules for the UI application core."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import RegistrationRequest
from .enums import GroundTruthStatus, IssueSeverity
from .method_registry import MethodDescriptor, MethodRegistry


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One request validation issue."""

    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Validation result returned before method execution."""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        """Return True when the report contains no errors."""
        return not any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.WARNING)


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    """What evidence may be shown for the current request."""

    allow_ground_truth_metrics: bool
    allow_geometric_status: bool


def evidence_policy(request: RegistrationRequest) -> EvidencePolicy:
    """Return evidence permissions without inferring unavailable ground truth."""
    known = request.evaluation.ground_truth_status is GroundTruthStatus.KNOWN
    return EvidencePolicy(
        allow_ground_truth_metrics=known,
        allow_geometric_status=known,
    )


def _known_ndim(request: RegistrationRequest) -> int | None:
    dimensions: list[int] = []
    for source in (request.fixed, request.moving):
        if source.array is not None:
            dimensions.append(int(np.asarray(source.array).ndim))
        elif "ndim" in source.metadata:
            dimensions.append(int(source.metadata["ndim"]))
    if not dimensions:
        return None
    return dimensions[0] if len(set(dimensions)) == 1 else -1


def _known_shape(source: object) -> tuple[int, ...] | None:
    array = getattr(source, "array", None)
    if array is not None:
        return tuple(int(value) for value in np.asarray(array).shape)
    metadata = getattr(source, "metadata", {})
    shape = metadata.get("shape") if isinstance(metadata, dict) else None
    if shape is not None:
        return tuple(int(value) for value in shape)
    return None


def _validate_descriptor(request: RegistrationRequest, descriptor: MethodDescriptor) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if request.registration.transform_model not in descriptor.motion_models:
        supported = ", ".join(sorted(model.value for model in descriptor.motion_models))
        issues.append(
            ValidationIssue(
                code="unsupported_transform_model",
                message=(
                    f"{descriptor.display_name} does not support "
                    f"{request.registration.transform_model.value}. Supported: {supported}."
                ),
            )
        )

    ndim = _known_ndim(request)
    if ndim == -1:
        issues.append(
            ValidationIssue(
                code="dimension_mismatch",
                message="Fixed and moving sources report different dimensionality.",
            )
        )
    elif ndim is not None and ndim not in descriptor.dimensions:
        supported_dims = ", ".join(str(value) for value in sorted(descriptor.dimensions))
        issues.append(
            ValidationIssue(
                code="unsupported_dimension",
                message=f"{descriptor.display_name} supports dimensions: {supported_dims}.",
            )
        )

    fixed_shape = _known_shape(request.fixed)
    moving_shape = _known_shape(request.moving)
    if descriptor.requires_same_shape and fixed_shape and moving_shape and fixed_shape != moving_shape:
        issues.append(
            ValidationIssue(
                code="shape_mismatch",
                message=(
                    f"{descriptor.display_name} requires matching fixed and moving shapes; "
                    f"received {fixed_shape} and {moving_shape}."
                ),
            )
        )
    return issues


def validate_request(request: RegistrationRequest, registry: MethodRegistry) -> ValidationReport:
    """Validate a normalized request before any adapter executes."""
    issues: list[ValidationIssue] = []

    if not request.fixed.display_name.strip() or not request.moving.display_name.strip():
        issues.append(
            ValidationIssue(
                code="missing_display_name",
                message="Fixed and moving sources require non-empty display names.",
            )
        )

    descriptor = registry.get(request.registration.method_id)
    if descriptor is None:
        issues.append(
            ValidationIssue(
                code="unknown_method",
                message=f"Unknown registration method: {request.registration.method_id}",
            )
        )
    else:
        issues.extend(_validate_descriptor(request, descriptor))

    clip = request.preprocessing.clipping_percentiles
    if clip is not None:
        low, high = clip
        if not (0.0 <= low < high <= 100.0):
            issues.append(
                ValidationIssue(
                    code="invalid_clipping_percentiles",
                    message="Clipping percentiles must satisfy 0 <= low < high <= 100.",
                )
            )

    sigma = request.preprocessing.gaussian_sigma
    if sigma is not None and sigma < 0.0:
        issues.append(
            ValidationIssue(
                code="invalid_gaussian_sigma",
                message="Gaussian sigma must be non-negative.",
            )
        )

    if request.preprocessing.resize_policy != "none":
        issues.append(
            ValidationIssue(
                code="resize_not_available_v01",
                message="UI v0.1 does not silently resize inputs; resize_policy must be 'none'.",
            )
        )

    context = request.evaluation
    if context.ground_truth_status is GroundTruthStatus.KNOWN:
        has_transform = context.ground_truth_transform is not None
        has_landmarks = context.fixed_landmarks is not None and context.moving_landmarks is not None
        has_masks = context.fixed_mask is not None and context.moving_mask is not None
        if not (has_transform or has_landmarks or has_masks):
            issues.append(
                ValidationIssue(
                    code="known_ground_truth_missing_evidence",
                    message=(
                        "Ground truth is marked known but no transform, paired landmarks, "
                        "or paired masks were supplied."
                    ),
                )
            )

    if context.fixed_landmarks is not None or context.moving_landmarks is not None:
        if context.fixed_landmarks is None or context.moving_landmarks is None:
            issues.append(
                ValidationIssue(
                    code="incomplete_landmark_pair",
                    message="Fixed and moving landmarks must be supplied together.",
                )
            )

    return ValidationReport(tuple(issues))
