"""Registration adapters for the UI application layer."""

from __future__ import annotations

from ui.core.registration_service import RegistrationService

from .ecc_adapter import ECCAdapter
from .feature_adapter import FeatureRegistrationAdapter
from .mutual_information_adapter import MutualInformationAdapter
from .phase_correlation_adapter import PhaseCorrelationAdapter


def build_default_registration_service(*, example_provider=None) -> RegistrationService:
    """Build the Stage 3 service with all supported 2D adapter families."""
    return RegistrationService(
        adapters={
            "phase_correlation": PhaseCorrelationAdapter(),
            "ecc": ECCAdapter(),
            "feature": FeatureRegistrationAdapter(),
            "mutual_information": MutualInformationAdapter(),
        },
        example_provider=example_provider,
    )


__all__ = [
    "ECCAdapter",
    "FeatureRegistrationAdapter",
    "MutualInformationAdapter",
    "PhaseCorrelationAdapter",
    "build_default_registration_service",
]
