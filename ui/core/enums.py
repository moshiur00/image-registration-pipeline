"""Framework-neutral enumerations for the UI application core."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """How an image source is supplied to the UI service."""

    FILE_PATH = "file_path"
    UPLOADED_BYTES = "uploaded_bytes"
    ARRAY = "array"
    EXAMPLE = "example"
    SYNTHETIC_PRESET = "synthetic_preset"
    RIRE = "rire"


class GroundTruthStatus(StrEnum):
    """Ground-truth availability for evidence-aware result handling."""

    KNOWN = "known"
    UNAVAILABLE = "unavailable"
    LANDMARKS_MISSING = "landmarks_missing"


class RunStatus(StrEnum):
    """High-level UI execution state."""

    COMPLETED = "completed"
    CHECK = "check"
    FAILED = "failed"
    VALIDATION_ERROR = "validation_error"


class TransformModel(StrEnum):
    """Supported geometric motion models."""

    TRANSLATION = "translation"
    RIGID = "rigid"
    SIMILARITY = "similarity"
    AFFINE = "affine"


class TransformUnits(StrEnum):
    """Units used for transform and ground-truth evidence."""

    PIXELS = "pixels"
    PHYSICAL_MM = "mm"
    UNSPECIFIED = "unspecified"


class IssueSeverity(StrEnum):
    """Validation issue severity."""

    ERROR = "error"
    WARNING = "warning"
