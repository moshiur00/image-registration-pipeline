"""Pure helpers used by the Streamlit presentation layer.

This module intentionally has no Streamlit dependency. It translates UI choices
into the framework-neutral contracts created in Stage 2.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Iterable

import numpy as np

from ui.core.contracts import (
    EvaluationContext,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationSpec,
)
from ui.core.dataset_catalog import ExampleBundle
from ui.core.enums import GroundTruthStatus, SourceType, TransformModel, TransformUnits
from ui.core.method_registry import MethodDescriptor
from ui.core.registration_service import hash_image_source


METHOD_TRE_THRESHOLDS_PIXELS: dict[str, float] = {
    "phase_translation": 0.5,
    "ecc_translation": 1.0,
    "ecc_rigid": 1.0,
    "ecc_affine": 1.0,
    "orb_similarity": 2.0,
    "orb_affine": 3.0,
    "sift_similarity": 2.0,
    "sift_affine": 3.0,
    "mi_rigid_2d": 3.0,
    "mi_affine_2d": 3.0,
}


def method_descriptors_for_example(
    methods: Iterable[MethodDescriptor],
    bundle: ExampleBundle,
) -> list[MethodDescriptor]:
    """Return 2D methods that solve the example's ground-truth motion model."""
    return [
        descriptor
        for descriptor in methods
        if 2 in descriptor.dimensions and bundle.descriptor.transform_model in descriptor.motion_models
    ]


def method_descriptors_for_upload(methods: Iterable[MethodDescriptor]) -> list[MethodDescriptor]:
    """Return all 2D methods available to an unknown-image workflow."""
    return [descriptor for descriptor in methods if 2 in descriptor.dimensions]


def default_preprocessing(method_id: str) -> PreprocessingSpec:
    """Return explicit UI defaults without hiding preprocessing from the user."""
    if method_id.startswith("mi_"):
        return PreprocessingSpec(
            grayscale=True,
            clipping_percentiles=None,
            normalization=None,
            gaussian_sigma=1.0,
            resize_policy="none",
        )
    return PreprocessingSpec(
        grayscale=True,
        clipping_percentiles=None,
        normalization=None,
        gaussian_sigma=0.0,
        resize_policy="none",
    )


def default_method_configuration(method_id: str) -> tuple[str | None, dict[str, Any]]:
    """Return conservative method controls derived from the validated backend defaults."""
    if method_id == "phase_translation":
        return None, {
            "use_hanning_window": True,
            "subtract_mean": True,
            "interpolation": "linear",
        }
    if method_id.startswith("ecc_"):
        return "identity", {
            "max_iterations": 150,
            "epsilon": 1e-6,
            "gauss_filt_size": 5,
            "multiresolution": method_id == "ecc_affine",
            "pyramid_scales": (0.25, 0.5, 1.0),
            "pre_smoothing_sigma": 0.8,
            "interpolation": "linear",
        }
    if method_id.startswith("orb_"):
        return None, {
            "n_features": 800,
            "ratio_threshold": 0.75,
            "reprojection_threshold": 3.0,
            "confidence": 0.99,
            "random_seed": 42,
            "interpolation": "linear",
        }
    if method_id.startswith("sift_"):
        return None, {
            "n_features": 800,
            "ratio_threshold": 0.75,
            "reprojection_threshold": 3.0,
            "confidence": 0.99,
            "random_seed": 42,
            "interpolation": "linear",
        }
    if method_id.startswith("mi_"):
        return "identity", {
            "histogram_bins": 32,
            "sampling_strategy": "none",
            "sampling_percentage": 1.0,
            "sampling_seed": 42,
            "learning_rate": 2.0,
            "minimum_step": 1e-3,
            "number_of_iterations": 200,
            "relaxation_factor": 0.5,
            "gradient_magnitude_tolerance": 1e-4,
            "shrink_factors": (4, 2, 1),
            "smoothing_sigmas": (2.0, 1.0, 0.0),
        }
    return None, {}


def tre_threshold_for_method(method_id: str) -> float | None:
    """Return the frozen development tolerance used by the corresponding research method."""
    return METHOD_TRE_THRESHOLDS_PIXELS.get(method_id)


def build_upload_source(
    *,
    display_name: str,
    content_bytes: bytes,
    decoded_array: np.ndarray,
    modality: str | None = None,
) -> ImageSource:
    """Build an uploaded source while keeping original bytes for provenance hashing."""
    spatial_shape = tuple(int(v) for v in np.asarray(decoded_array).shape[:2])
    return ImageSource(
        source_type=SourceType.UPLOADED_BYTES,
        display_name=display_name,
        modality=modality,
        content_bytes=content_bytes,
        metadata={
            "ndim": 2,
            "shape": list(spatial_shape),
            "decoded_shape": list(np.asarray(decoded_array).shape),
            "dtype": str(np.asarray(decoded_array).dtype),
        },
    )


def _request_id(
    fixed: ImageSource,
    moving: ImageSource,
    preprocessing: PreprocessingSpec,
    registration: RegistrationSpec,
) -> str:
    payload = {
        "fixed": hash_image_source(fixed),
        "moving": hash_image_source(moving),
        "preprocessing": {
            "grayscale": preprocessing.grayscale,
            "clipping_percentiles": preprocessing.clipping_percentiles,
            "normalization": preprocessing.normalization,
            "gaussian_sigma": preprocessing.gaussian_sigma,
            "resize_policy": preprocessing.resize_policy,
        },
        "registration": {
            "method_id": registration.method_id,
            "transform_model": registration.transform_model.value,
            "initialization": registration.initialization,
            "parameters": registration.parameters,
            "interpolation": registration.interpolation,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
    return "ui-" + hashlib.sha256(encoded).hexdigest()[:16]


def build_example_request(
    *,
    bundle: ExampleBundle,
    method: MethodDescriptor,
    preprocessing: PreprocessingSpec,
    initialization: str | None,
    parameters: dict[str, Any],
) -> RegistrationRequest:
    """Build a known-ground-truth request for one curated example."""
    threshold = tre_threshold_for_method(method.id)
    evaluation = replace(
        bundle.evaluation,
        thresholds={"mean_tre_pixels": threshold} if threshold is not None else {},
    )
    transform_model = next(iter(method.motion_models))
    registration = RegistrationSpec(
        method_id=method.id,
        transform_model=transform_model,
        initialization=initialization,
        parameters=dict(parameters),
        interpolation=str(parameters.get("interpolation", "linear")),
    )
    return RegistrationRequest(
        fixed=bundle.fixed,
        moving=bundle.moving,
        preprocessing=preprocessing,
        registration=registration,
        evaluation=evaluation,
        request_id=_request_id(bundle.fixed, bundle.moving, preprocessing, registration),
    )


def build_upload_request(
    *,
    fixed: ImageSource,
    moving: ImageSource,
    method: MethodDescriptor,
    preprocessing: PreprocessingSpec,
    initialization: str | None,
    parameters: dict[str, Any],
) -> RegistrationRequest:
    """Build an unknown-ground-truth request for user-supplied 2D images."""
    transform_model = next(iter(method.motion_models))
    registration = RegistrationSpec(
        method_id=method.id,
        transform_model=transform_model,
        initialization=initialization,
        parameters=dict(parameters),
        interpolation=str(parameters.get("interpolation", "linear")),
    )
    evaluation = EvaluationContext(
        ground_truth_status=GroundTruthStatus.UNAVAILABLE,
        units=TransformUnits.PIXELS,
    )
    return RegistrationRequest(
        fixed=fixed,
        moving=moving,
        preprocessing=preprocessing,
        registration=registration,
        evaluation=evaluation,
        request_id=_request_id(fixed, moving, preprocessing, registration),
    )


def evidence_status_label(*, ground_truth_known: bool, run_status: str, within_tolerance: bool | None) -> str:
    """Map service state to evidence-aware language for the workbench."""
    if run_status == "failed" or run_status == "validation_error":
        return "Failed"
    if ground_truth_known:
        if within_tolerance is True:
            return "PASS"
        if run_status == "check" or within_tolerance is False:
            return "CHECK"
        return "Completed"
    if run_status == "check":
        return "Warning"
    return "Completed"
