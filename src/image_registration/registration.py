"""Common registration method interface used by later algorithm modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@dataclass
class RegistrationResult:
    """Standard result returned by a registration method."""

    transform: NDArray[np.float64]
    registered_image: NDArray[np.generic]
    success: bool
    runtime_seconds: float
    convergence_info: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


@runtime_checkable
class RegistrationMethod(Protocol):
    """Interface that registration algorithms will implement."""

    def register(
        self,
        fixed: NDArray[np.generic],
        moving: NDArray[np.generic],
    ) -> RegistrationResult:
        """Estimate a Moving -> Fixed transform and return a standard result."""
        ...
