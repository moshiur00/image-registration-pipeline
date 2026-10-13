"""Framework-neutral request and result contracts for the UI service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from image_registration.conventions import STORED_TRANSFORM_DIRECTION

from .enums import GroundTruthStatus, RunStatus, SourceType, TransformModel, TransformUnits

Array = NDArray[np.generic]
FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class ImageSource:
    """One fixed or moving image reference supplied to the service."""

    source_type: SourceType
    display_name: str
    modality: str | None = None
    path: Path | None = None
    content_bytes: bytes | None = None
    array: Array | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PreprocessingSpec:
    """Explicit preprocessing requested by the UI."""

    grayscale: bool = True
    clipping_percentiles: tuple[float, float] | None = None
    normalization: str | None = None
    gaussian_sigma: float | None = None
    resize_policy: str = "none"


@dataclass(slots=True)
class RegistrationSpec:
    """Method selection and normalized method parameters."""

    method_id: str
    transform_model: TransformModel
    initialization: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    interpolation: str = "bilinear"


@dataclass(slots=True)
class EvaluationContext:
    """Evidence that is available for evaluating a registration run."""

    ground_truth_status: GroundTruthStatus = GroundTruthStatus.UNAVAILABLE
    ground_truth_transform: FloatArray | None = None
    fixed_landmarks: FloatArray | None = None
    moving_landmarks: FloatArray | None = None
    fixed_mask: Array | None = None
    moving_mask: Array | None = None
    units: TransformUnits = TransformUnits.UNSPECIFIED
    thresholds: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RegistrationRequest:
    """Complete normalized registration request."""

    fixed: ImageSource
    moving: ImageSource
    preprocessing: PreprocessingSpec
    registration: RegistrationSpec
    evaluation: EvaluationContext = field(default_factory=EvaluationContext)
    request_id: str = ""


@dataclass(slots=True)
class TransformSummary:
    """Project-direction transform and interpretable plausibility information."""

    matrix: FloatArray
    motion_model: TransformModel
    direction: str = STORED_TRANSFORM_DIRECTION
    parameters: dict[str, Any] = field(default_factory=dict)
    plausible: bool | None = None
    plausibility_reasons: tuple[str, ...] = ()


@dataclass(slots=True)
class MetricSummary:
    """Descriptive and optional ground-truth metrics."""

    before: dict[str, float] = field(default_factory=dict)
    after: dict[str, float] = field(default_factory=dict)
    ground_truth: dict[str, float] = field(default_factory=dict)
    within_tolerance: bool | None = None
    units: TransformUnits = TransformUnits.UNSPECIFIED


@dataclass(slots=True)
class DiagnosticSummary:
    """Method-specific diagnostics kept separate from evaluation metrics."""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProvenanceSummary:
    """Minimal reproducibility information for one UI run."""

    fixed_sha256: str | None
    moving_sha256: str | None
    method_id: str
    normalized_parameters: dict[str, Any]
    preprocessing: dict[str, Any]
    transform_direction: str = STORED_TRANSFORM_DIRECTION
    package_version: str = "unknown"
    ground_truth_status: GroundTruthStatus = GroundTruthStatus.UNAVAILABLE


@dataclass(slots=True)
class ArtifactRef:
    """Reference to a temporary UI artifact."""

    name: str
    media_type: str
    location: str | None = None


@dataclass(slots=True)
class RegistrationRun:
    """Normalized result returned to any presentation layer."""

    request_id: str
    run_status: RunStatus
    method_success: bool
    transform: TransformSummary | None
    metrics: MetricSummary
    diagnostics: DiagnosticSummary
    runtime_seconds: float
    warnings: tuple[str, ...]
    provenance: ProvenanceSummary
    registered_array: Array | None = None
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    failure_reason: str | None = None


@dataclass(slots=True)
class AdapterResult:
    """Framework-neutral output expected from a Stage 3 registration adapter."""

    method_success: bool
    runtime_seconds: float
    transform_matrix: FloatArray | None = None
    registered_array: Array | None = None
    transform_parameters: dict[str, Any] = field(default_factory=dict)
    plausible: bool | None = None
    plausibility_reasons: tuple[str, ...] = ()
    descriptive_metrics_before: dict[str, float] = field(default_factory=dict)
    descriptive_metrics_after: dict[str, float] = field(default_factory=dict)
    ground_truth_metrics: dict[str, float] = field(default_factory=dict)
    within_tolerance: bool | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None
