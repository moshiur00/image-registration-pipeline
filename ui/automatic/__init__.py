"""Stage 6 automatic comparison application layer."""

from .automatic_service import (
    AutomaticComparisonService,
    build_default_auto_method_catalog,
)
from .models import (
    AgreementComparisonView,
    AutomaticComparisonRequest,
    AutomaticComparisonView,
    CandidateAgreementView,
    CandidateComparisonView,
    CompatibilityPreviewView,
    MethodCompatibilityView,
    PairwiseAgreementView,
)

__all__ = [
    "AgreementComparisonView",
    "AutomaticComparisonRequest",
    "AutomaticComparisonService",
    "AutomaticComparisonView",
    "CandidateAgreementView",
    "CandidateComparisonView",
    "CompatibilityPreviewView",
    "MethodCompatibilityView",
    "PairwiseAgreementView",
    "build_default_auto_method_catalog",
]
