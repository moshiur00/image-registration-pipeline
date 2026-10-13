"""Framework-neutral application core for the image registration UI."""

from .contracts import (
    AdapterResult,
    ArtifactRef,
    DiagnosticSummary,
    EvaluationContext,
    ImageSource,
    MetricSummary,
    PreprocessingSpec,
    ProvenanceSummary,
    RegistrationRequest,
    RegistrationRun,
    RegistrationSpec,
    TransformSummary,
)
from .dataset_catalog import DatasetCatalog, ExampleBundle, ExampleDescriptor
from .export_service import ExportPayload, build_run_exports, comparison_figure, transform_payload
from .enums import (
    GroundTruthStatus,
    IssueSeverity,
    RunStatus,
    SourceType,
    TransformModel,
    TransformUnits,
)
from .method_registry import DEFAULT_METHOD_REGISTRY, MethodDescriptor, MethodRegistry
from .registration_service import RegistrationService, hash_image_source
from .validation import EvidencePolicy, ValidationIssue, ValidationReport, evidence_policy

__all__ = [
    "AdapterResult",
    "ArtifactRef",
    "DatasetCatalog",
    "DiagnosticSummary",
    "EvaluationContext",
    "ExampleBundle",
    "ExampleDescriptor",
    "EvidencePolicy",
    "ExportPayload",
    "GroundTruthStatus",
    "ImageSource",
    "IssueSeverity",
    "MetricSummary",
    "MethodDescriptor",
    "MethodRegistry",
    "PreprocessingSpec",
    "ProvenanceSummary",
    "RegistrationRequest",
    "RegistrationRun",
    "RegistrationService",
    "RegistrationSpec",
    "RunStatus",
    "SourceType",
    "TransformModel",
    "TransformSummary",
    "TransformUnits",
    "ValidationIssue",
    "ValidationReport",
    "DEFAULT_METHOD_REGISTRY",
    "evidence_policy",
    "hash_image_source",
    "build_run_exports",
    "comparison_figure",
    "transform_payload",
]
