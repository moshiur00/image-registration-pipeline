"""Unified Week 6 evaluation semantics and result contracts.

This module defines how registration evidence is represented across methods.
It deliberately separates optimization diagnostics from evaluation metrics and
prevents geometric correctness claims when reference evidence is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .overlap import combine_valid_masks, overlap_fraction

SCHEMA_VERSION = "week06_evaluation_v1"
TRANSFORM_DIRECTION = "moving_to_fixed"
COORDINATE_ORDER_2D = "xy"
COORDINATE_ORDER_3D = "xyz"

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


class MetricRole(str, Enum):
    """Scientific role of one value in the evaluation system."""

    GEOMETRIC_ERROR = "geometric_error"
    ANATOMICAL_OVERLAP = "anatomical_overlap"
    DESCRIPTIVE_SIMILARITY = "descriptive_similarity"
    VALID_OVERLAP = "valid_overlap"
    RUNTIME = "runtime"


class MetricDirection(str, Enum):
    """Direction used only for within-metric interpretation."""

    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"
    NONE = "none"


class ExecutionStatus(str, Enum):
    """Common execution state for one registration candidate."""

    COMPLETED = "completed"
    CHECK = "check"
    FAILED = "failed"
    VALIDATION_ERROR = "validation_error"


@dataclass(frozen=True)
class MetricDefinition:
    """Definition and scientific requirements for one comparable metric."""

    key: str
    display_name: str
    role: MetricRole
    unit: str
    direction: MetricDirection
    requires_exact_transform: bool = False
    requires_geometric_reference: bool = False
    requires_reference_masks: bool = False
    requires_physical_spacing: bool = False
    requires_valid_overlap: bool = False
    note: str = ""


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "translation_error_px": MetricDefinition(
        key="translation_error_px",
        display_name="Translation error",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="px",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_exact_transform=True,
    ),
    "translation_error_mm": MetricDefinition(
        key="translation_error_mm",
        display_name="Translation error",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="mm",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_exact_transform=True,
        requires_physical_spacing=True,
    ),
    "rotation_error_deg": MetricDefinition(
        key="rotation_error_deg",
        display_name="Rotation error",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="deg",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_exact_transform=True,
    ),
    "scale_error_abs": MetricDefinition(
        key="scale_error_abs",
        display_name="Absolute scale error",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="dimensionless",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_exact_transform=True,
    ),
    "affine_linear_error": MetricDefinition(
        key="affine_linear_error",
        display_name="Affine linear error",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="frobenius",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_exact_transform=True,
    ),
    "tre_mean_px": MetricDefinition(
        key="tre_mean_px",
        display_name="Mean TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="px",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
    ),
    "tre_median_px": MetricDefinition(
        key="tre_median_px",
        display_name="Median TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="px",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
    ),
    "tre_std_px": MetricDefinition(
        key="tre_std_px",
        display_name="TRE standard deviation",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="px",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
    ),
    "tre_p95_px": MetricDefinition(
        key="tre_p95_px",
        display_name="95th percentile TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="px",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
    ),
    "tre_mean_mm": MetricDefinition(
        key="tre_mean_mm",
        display_name="Mean TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="mm",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
        requires_physical_spacing=True,
    ),
    "tre_median_mm": MetricDefinition(
        key="tre_median_mm",
        display_name="Median TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="mm",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
        requires_physical_spacing=True,
    ),
    "tre_std_mm": MetricDefinition(
        key="tre_std_mm",
        display_name="TRE standard deviation",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="mm",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
        requires_physical_spacing=True,
    ),
    "tre_p95_mm": MetricDefinition(
        key="tre_p95_mm",
        display_name="95th percentile TRE",
        role=MetricRole.GEOMETRIC_ERROR,
        unit="mm",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_geometric_reference=True,
        requires_physical_spacing=True,
    ),
    "dice": MetricDefinition(
        key="dice",
        display_name="Dice score",
        role=MetricRole.ANATOMICAL_OVERLAP,
        unit="score",
        direction=MetricDirection.HIGHER_IS_BETTER,
        requires_reference_masks=True,
    ),
    "mae": MetricDefinition(
        key="mae",
        display_name="Mean absolute error",
        role=MetricRole.DESCRIPTIVE_SIMILARITY,
        unit="intensity",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_valid_overlap=True,
        note="Descriptive only. Do not use alone as evidence of geometric correctness.",
    ),
    "mse": MetricDefinition(
        key="mse",
        display_name="Mean squared error",
        role=MetricRole.DESCRIPTIVE_SIMILARITY,
        unit="intensity_squared",
        direction=MetricDirection.LOWER_IS_BETTER,
        requires_valid_overlap=True,
        note="Descriptive only. Do not use alone as evidence of geometric correctness.",
    ),
    "ncc": MetricDefinition(
        key="ncc",
        display_name="Normalized cross correlation",
        role=MetricRole.DESCRIPTIVE_SIMILARITY,
        unit="score",
        direction=MetricDirection.HIGHER_IS_BETTER,
        requires_valid_overlap=True,
        note="Most interpretable for monomodal intensity relationships.",
    ),
    "ssim": MetricDefinition(
        key="ssim",
        display_name="Structural similarity",
        role=MetricRole.DESCRIPTIVE_SIMILARITY,
        unit="score",
        direction=MetricDirection.HIGHER_IS_BETTER,
        requires_valid_overlap=True,
        note="Descriptive only and modality-sensitive.",
    ),
    "evaluation_mi": MetricDefinition(
        key="evaluation_mi",
        display_name="Evaluation mutual information",
        role=MetricRole.DESCRIPTIVE_SIMILARITY,
        unit="score",
        direction=MetricDirection.HIGHER_IS_BETTER,
        requires_valid_overlap=True,
        note="Independent evaluation value. It is not a cross-method optimizer score.",
    ),
    "valid_overlap_fraction": MetricDefinition(
        key="valid_overlap_fraction",
        display_name="Valid overlap",
        role=MetricRole.VALID_OVERLAP,
        unit="fraction",
        direction=MetricDirection.HIGHER_IS_BETTER,
        requires_valid_overlap=True,
    ),
    "preprocessing_runtime_ms": MetricDefinition(
        key="preprocessing_runtime_ms",
        display_name="Preprocessing runtime",
        role=MetricRole.RUNTIME,
        unit="ms",
        direction=MetricDirection.NONE,
    ),
    "registration_runtime_ms": MetricDefinition(
        key="registration_runtime_ms",
        display_name="Registration runtime",
        role=MetricRole.RUNTIME,
        unit="ms",
        direction=MetricDirection.NONE,
    ),
    "warping_runtime_ms": MetricDefinition(
        key="warping_runtime_ms",
        display_name="Warping runtime",
        role=MetricRole.RUNTIME,
        unit="ms",
        direction=MetricDirection.NONE,
    ),
    "evaluation_runtime_ms": MetricDefinition(
        key="evaluation_runtime_ms",
        display_name="Evaluation runtime",
        role=MetricRole.RUNTIME,
        unit="ms",
        direction=MetricDirection.NONE,
    ),
    "total_runtime_ms": MetricDefinition(
        key="total_runtime_ms",
        display_name="Total runtime",
        role=MetricRole.RUNTIME,
        unit="ms",
        direction=MetricDirection.NONE,
    ),
}


@dataclass(frozen=True)
class ReferenceEvidence:
    """Reference information available for one image pair."""

    exact_transform: bool = False
    landmarks: bool = False
    masks: bool = False
    physical_spacing: bool = False

    @property
    def geometric_reference_available(self) -> bool:
        """Return whether geometric error can be evaluated."""
        return self.exact_transform or self.landmarks

    @property
    def any_ground_truth_available(self) -> bool:
        """Return whether any reference evidence is available."""
        return self.geometric_reference_available or self.masks

    @property
    def label(self) -> str:
        """Return a stable human-readable reference label."""
        labels: list[str] = []
        if self.exact_transform:
            labels.append("exact_transform")
        if self.landmarks:
            labels.append("landmarks")
        if self.masks:
            labels.append("masks")
        return "+".join(labels) if labels else "unavailable"


@dataclass(frozen=True)
class EvaluationContext:
    """Scientific context controlling which evaluation claims are allowed."""

    modality_class: str
    reference: ReferenceEvidence
    valid_overlap_available: bool
    valid_overlap_fraction: float | None = None

    def __post_init__(self) -> None:
        modality = self.modality_class.strip().lower()
        if not modality:
            raise ValueError("modality_class must be non-empty.")
        object.__setattr__(self, "modality_class", modality)
        if self.valid_overlap_fraction is not None:
            value = float(self.valid_overlap_fraction)
            if not np.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError("valid_overlap_fraction must be in the range (0, 1].")
            if not self.valid_overlap_available:
                raise ValueError("valid_overlap_fraction requires valid_overlap_available=True.")
            object.__setattr__(self, "valid_overlap_fraction", value)

    @property
    def geometric_pass_allowed(self) -> bool:
        """Return whether a geometric PASS/CHECK statement is scientifically allowed."""
        return self.reference.geometric_reference_available


@dataclass(frozen=True)
class MetricAvailability:
    """Availability decision for one metric in one evaluation context."""

    metric_key: str
    available: bool
    reason: str | None = None


def metric_availability(metric_key: str, context: EvaluationContext) -> MetricAvailability:
    """Return whether one metric may be reported for the supplied context."""
    if metric_key not in METRIC_DEFINITIONS:
        raise KeyError(f"Unknown metric definition: {metric_key}")
    definition = METRIC_DEFINITIONS[metric_key]
    reference = context.reference

    if definition.requires_exact_transform and not reference.exact_transform:
        return MetricAvailability(metric_key, False, "exact_transform_unavailable")
    if definition.requires_geometric_reference and not reference.geometric_reference_available:
        return MetricAvailability(metric_key, False, "geometric_reference_unavailable")
    if definition.requires_reference_masks and not reference.masks:
        return MetricAvailability(metric_key, False, "reference_masks_unavailable")
    if definition.requires_physical_spacing and not reference.physical_spacing:
        return MetricAvailability(metric_key, False, "physical_spacing_unavailable")
    if definition.requires_valid_overlap and not context.valid_overlap_available:
        return MetricAvailability(metric_key, False, "valid_overlap_unavailable")
    return MetricAvailability(metric_key, True, None)


def available_metric_keys(context: EvaluationContext) -> list[str]:
    """Return metric keys that are scientifically available for one context."""
    return [
        key
        for key in METRIC_DEFINITIONS
        if metric_availability(key, context).available
    ]


@dataclass(frozen=True)
class ValidOverlap:
    """Resolved valid-overlap mask and summary."""

    mask: BoolArray
    pixel_count: int
    total_pixels: int
    fraction: float


def resolve_valid_overlap(
    image_shape: tuple[int, int],
    *masks: ArrayLike,
) -> ValidOverlap:
    """Resolve the evaluation region as the intersection of supplied valid masks.

    If no masks are supplied, the full image is treated as valid. Callers should
    include transformed moving-image support when warp borders are invalid.
    """
    if len(image_shape) != 2 or any(int(value) <= 0 for value in image_shape):
        raise ValueError("image_shape must contain positive height and width.")
    height, width = (int(image_shape[0]), int(image_shape[1]))

    if masks:
        binary_masks = []
        for index, mask in enumerate(masks):
            array = np.asarray(mask)
            if array.shape != (height, width):
                raise ValueError(f"mask[{index}] must match image_shape.")
            binary_masks.append((array != 0).astype(np.uint8))
        resolved = combine_valid_masks(*binary_masks).astype(bool)
    else:
        resolved = np.ones((height, width), dtype=bool)

    pixel_count = int(np.count_nonzero(resolved))
    if pixel_count == 0:
        raise ValueError("Valid overlap is empty.")
    total_pixels = int(height * width)
    fraction = overlap_fraction(resolved.astype(np.uint8))
    return ValidOverlap(
        mask=resolved,
        pixel_count=pixel_count,
        total_pixels=total_pixels,
        fraction=fraction,
    )


def _coordinate_order(dimensions: int) -> str:
    if dimensions == 2:
        return COORDINATE_ORDER_2D
    if dimensions == 3:
        return COORDINATE_ORDER_3D
    raise ValueError("dimensions must be 2 or 3.")


def _validate_transform(transform: ArrayLike | None, *, dimensions: int) -> FloatArray | None:
    if transform is None:
        return None
    matrix = np.asarray(transform, dtype=np.float64)
    expected_shape = (dimensions + 1, dimensions + 1)
    if matrix.shape != expected_shape:
        raise ValueError(f"estimated_transform must have shape {expected_shape}.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("estimated_transform must contain only finite values.")
    expected_last_row = np.zeros(dimensions + 1, dtype=np.float64)
    expected_last_row[-1] = 1.0
    if not np.allclose(matrix[-1], expected_last_row):
        raise ValueError("estimated_transform must be an affine-form homogeneous matrix.")
    return matrix


@dataclass
class UnifiedEvaluationRecord:
    """Method-independent record for one registration candidate."""

    pair_id: str
    method_id: str
    method_family: str
    transform_model: str
    modality_class: str
    dimensions: int
    execution_status: ExecutionStatus
    reference: ReferenceEvidence
    valid_overlap_fraction: float | None
    seed: int | None = None
    estimated_transform: ArrayLike | None = None
    transform_plausible: bool | None = None
    geometric_within_tolerance: bool | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)
    method_diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("pair_id", "method_id", "method_family", "transform_model", "modality_class"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty.")
            setattr(self, name, value)

        self.dimensions = int(self.dimensions)
        _coordinate_order(self.dimensions)

        if not isinstance(self.execution_status, ExecutionStatus):
            self.execution_status = ExecutionStatus(str(self.execution_status))

        self.estimated_transform = _validate_transform(
            self.estimated_transform, dimensions=self.dimensions
        )

        if self.valid_overlap_fraction is not None:
            overlap = float(self.valid_overlap_fraction)
            if not np.isfinite(overlap) or not 0.0 < overlap <= 1.0:
                raise ValueError("valid_overlap_fraction must be in the range (0, 1].")
            self.valid_overlap_fraction = overlap

        context = EvaluationContext(
            modality_class=self.modality_class,
            reference=self.reference,
            valid_overlap_available=self.valid_overlap_fraction is not None,
            valid_overlap_fraction=self.valid_overlap_fraction,
        )
        if self.geometric_within_tolerance is not None and not context.geometric_pass_allowed:
            raise ValueError("Geometric PASS/CHECK requires geometric reference evidence.")

        if self.execution_status in {ExecutionStatus.FAILED, ExecutionStatus.VALIDATION_ERROR}:
            if not self.failure_reason:
                raise ValueError("Failed and validation-error records require failure_reason.")

        normalized_metrics: dict[str, float] = {}
        for key, value in self.metrics.items():
            if key not in METRIC_DEFINITIONS:
                raise KeyError(f"Unknown comparable metric: {key}")
            decision = metric_availability(key, context)
            if not decision.available:
                raise ValueError(f"Metric '{key}' is unavailable: {decision.reason}.")
            numeric = float(value)
            if not np.isfinite(numeric):
                raise ValueError(f"Metric '{key}' must be finite.")
            normalized_metrics[key] = numeric
        self.metrics = normalized_metrics

        normalized_timings: dict[str, float] = {}
        for key, value in self.timings_ms.items():
            numeric = float(value)
            if not np.isfinite(numeric) or numeric < 0.0:
                raise ValueError(f"Timing '{key}' must be finite and non-negative.")
            normalized_timings[str(key)] = numeric
        self.timings_ms = normalized_timings

    @property
    def transform_direction(self) -> str:
        return TRANSFORM_DIRECTION

    @property
    def schema_version(self) -> str:
        return SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible representation."""
        return {
            "schema_version": self.schema_version,
            "pair_id": self.pair_id,
            "method_id": self.method_id,
            "method_family": self.method_family,
            "transform_model": self.transform_model,
            "modality_class": self.modality_class,
            "dimensions": self.dimensions,
            "seed": self.seed,
            "execution_status": self.execution_status.value,
            "failure_reason": self.failure_reason,
            "transform_direction": self.transform_direction,
            "coordinate_order": _coordinate_order(self.dimensions),
            "estimated_transform": (
                self.estimated_transform.tolist() if self.estimated_transform is not None else None
            ),
            "transform_plausible": self.transform_plausible,
            "geometric_within_tolerance": self.geometric_within_tolerance,
            "reference": {
                "label": self.reference.label,
                "exact_transform": self.reference.exact_transform,
                "landmarks": self.reference.landmarks,
                "masks": self.reference.masks,
                "physical_spacing": self.reference.physical_spacing,
            },
            "valid_overlap_fraction": self.valid_overlap_fraction,
            "metrics": dict(sorted(self.metrics.items())),
            "timings_ms": dict(sorted(self.timings_ms.items())),
            "method_diagnostics": self.method_diagnostics,
            "warnings": list(self.warnings),
        }


def metric_catalog() -> list[dict[str, Any]]:
    """Return the common metric catalog as JSON-compatible records."""
    catalog: list[dict[str, Any]] = []
    for key in sorted(METRIC_DEFINITIONS):
        definition = METRIC_DEFINITIONS[key]
        catalog.append(
            {
                "key": definition.key,
                "display_name": definition.display_name,
                "role": definition.role.value,
                "unit": definition.unit,
                "direction": definition.direction.value,
                "requires_exact_transform": definition.requires_exact_transform,
                "requires_geometric_reference": definition.requires_geometric_reference,
                "requires_reference_masks": definition.requires_reference_masks,
                "requires_physical_spacing": definition.requires_physical_spacing,
                "requires_valid_overlap": definition.requires_valid_overlap,
                "note": definition.note,
            }
        )
    return catalog


def summarize_metric_availability(context: EvaluationContext) -> dict[str, Mapping[str, Any]]:
    """Return availability decisions for every common metric."""
    summary: dict[str, Mapping[str, Any]] = {}
    for key in sorted(METRIC_DEFINITIONS):
        decision = metric_availability(key, context)
        summary[key] = {
            "available": decision.available,
            "reason": decision.reason,
        }
    return summary
