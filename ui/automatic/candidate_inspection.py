"""Stage 6.4 framework-neutral candidate inspection and visual reconstruction.

The visual preview is reconstructed from the reported Moving -> Fixed transform
and the explicitly preprocessed input pair. It is not a rerun of registration,
and it is not used to calculate or replace the recorded evaluation metrics.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from image_registration.warping import warp_image
from image_registration.overlap import transformed_support_mask
from ui.core.image_inputs import prepare_image_source

from .models import AutomaticComparisonRequest, CandidateComparisonView
from .automatic_presenter import execution_status_label, transform_state_label


VISUAL_EXPLANATION = (
    "Visual reconstruction: the preprocessed moving image is resampled into "
    "fixed-image geometry using this candidate's reported Moving -> Fixed "
    "transform. This is an inspection-only preview, not a new registration "
    "run or evidence of geometric correctness. Display rendering may differ "
    "from the original adapter's interpolation settings. The visual support "
    "mask is obtained geometrically from the Moving -> Fixed transform."
)


def candidate_detail(candidate: CandidateComparisonView) -> dict[str, Any]:
    """Preserve failure, transform, method diagnostics, and reference policy."""
    if candidate.geometric_metrics or candidate.anatomical_metrics:
        raise ValueError("Unknown-GT candidate inspection must not reveal reference metrics.")
    return {
        "method": candidate.display_name,
        "family": candidate.method_family.replace("_", " ").title(),
        "transform_model": candidate.transform_model.title(),
        "execution": execution_status_label(candidate.execution_status),
        "plausibility": transform_state_label(candidate.transform_plausible),
        "transform_direction": "Moving -> Fixed",
        "estimated_transform": candidate.estimated_transform,
        "timings_ms": dict(candidate.timings_ms),
        "diagnostics": dict(candidate.method_diagnostics),
        "warnings": tuple(candidate.warnings),
        "failure_reason": candidate.failure_reason,
        "registered_output_available": bool(candidate.registered_output_available),
        "geometric_ground_truth": "unavailable",
    }


def can_inspect_image(candidate: CandidateComparisonView) -> bool:
    """Do not construct inspection images for failed or missing-transform runs."""
    return (
        candidate.execution_status in {"completed", "check"}
        and candidate.estimated_transform is not None
        and candidate.registered_output_available
    )


def reconstruct_visual_preview(
    request: AutomaticComparisonRequest,
    candidate: CandidateComparisonView,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return prepared fixed/moving and a display-only reconstructed registration.

    The project's validated warp_image utility handles inverse sampling for
    the forward Moving -> Fixed transform. The function does not store images;
    the separate export layer explicitly labels reconstructed previews.
    """
    fixed, moving, registered, _mask = reconstruct_visual_inspection(request, candidate)
    return fixed, moving, registered


def reconstruct_visual_inspection(
    request: AutomaticComparisonRequest,
    candidate: CandidateComparisonView,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reconstruct an inspection image and exact geometric source-support mask.

    The mask is a nearest-neighbor warp of a source all-ones image, never
    inferred from darkness or zero-valued pixels in the registered image.
    """
    if not can_inspect_image(candidate):
        raise ValueError("Candidate has no successful registered output for inspection.")
    fixed = prepare_image_source(request.fixed, request.preprocessing, name="Fixed").array
    moving = prepare_image_source(request.moving, request.preprocessing, name="Moving").array
    matrix = np.asarray(candidate.estimated_transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("Candidate transform must be a finite 3x3 matrix.")
    registered = warp_image(
        moving,
        matrix,
        output_shape=(int(fixed.shape[0]), int(fixed.shape[1])),
        interpolation="linear",
    )
    support = transformed_support_mask(
        moving.shape,
        matrix,
        destination_shape=(int(fixed.shape[0]), int(fixed.shape[1])),
    ).astype(bool)
    return fixed, moving, registered, support

