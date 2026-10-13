"""JSON-safe presentation helpers for framework-neutral UI contracts."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import PurePath
from typing import Any

import numpy as np

from .contracts import RegistrationRun


def to_json_safe(value: Any) -> Any:
    """Convert common contract values into JSON-safe Python values."""
    if is_dataclass(value):
        return {key: to_json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_safe(item) for item in value]
    return value


def registration_run_summary(run: RegistrationRun) -> dict[str, Any]:
    """Return an export-friendly run summary without embedding image arrays."""
    payload = to_json_safe(run)
    payload.pop("registered_array", None)
    return payload
