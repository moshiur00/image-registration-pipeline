"""Physical-space 3D Mattes mutual-information registration utilities."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from .registration import RegistrationResult

try:
    import SimpleITK as sitk
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    sitk = None

FloatArray = NDArray[np.float64]
SamplingStrategy = Literal["none", "regular", "random"]
InitializationMode = Literal["identity", "geometry", "moments"]


@dataclass(frozen=True)
class MedicalMutualInformationConfig:
    """Configuration for 3D rigid Mattes mutual-information registration."""

    histogram_bins: int = 32
    sampling_strategy: SamplingStrategy = "none"
    sampling_percentage: float = 0.20
    sampling_seed: int = 42
    learning_rate: float = 2.0
    minimum_step: float = 1e-3
    number_of_iterations: int = 200
    relaxation_factor: float = 0.5
    gradient_magnitude_tolerance: float = 1e-4
    shrink_factors: tuple[int, ...] = (4, 2, 1)
    smoothing_sigmas: tuple[float, ...] = (2.0, 1.0, 0.0)
    initialization: InitializationMode = "geometry"
    preprocessing_sigma_mm: float = 1.0

    def __post_init__(self) -> None:
        if self.histogram_bins < 8:
            raise ValueError("histogram_bins must be at least 8.")
        if self.sampling_strategy not in {"none", "regular", "random"}:
            raise ValueError("sampling_strategy must be none, regular, or random.")
        if not 0.0 < self.sampling_percentage <= 1.0:
            raise ValueError("sampling_percentage must be in the range (0, 1].")
        if self.sampling_seed < 0:
            raise ValueError("sampling_seed must be non-negative.")
        if self.learning_rate <= 0.0 or not np.isfinite(self.learning_rate):
            raise ValueError("learning_rate must be finite and greater than zero.")
        if self.minimum_step <= 0.0 or not np.isfinite(self.minimum_step):
            raise ValueError("minimum_step must be finite and greater than zero.")
        if self.number_of_iterations <= 0:
            raise ValueError("number_of_iterations must be greater than zero.")
        if not 0.0 < self.relaxation_factor < 1.0:
            raise ValueError("relaxation_factor must be in the range (0, 1).")
        if self.gradient_magnitude_tolerance < 0.0 or not np.isfinite(
            self.gradient_magnitude_tolerance
        ):
            raise ValueError("gradient_magnitude_tolerance must be finite and non-negative.")
        if not self.shrink_factors or any(int(value) < 1 for value in self.shrink_factors):
            raise ValueError("shrink_factors must contain positive integers.")
        if len(self.shrink_factors) != len(self.smoothing_sigmas):
            raise ValueError("shrink_factors and smoothing_sigmas must have equal length.")
        if any(float(value) < 0.0 or not np.isfinite(value) for value in self.smoothing_sigmas):
            raise ValueError("smoothing_sigmas must contain finite non-negative values.")
        if self.initialization not in {"identity", "geometry", "moments"}:
            raise ValueError("initialization must be identity, geometry, or moments.")
        if self.preprocessing_sigma_mm < 0.0 or not np.isfinite(self.preprocessing_sigma_mm):
            raise ValueError("preprocessing_sigma_mm must be finite and non-negative.")


def _require_sitk() -> Any:
    if sitk is None:
        raise RuntimeError(
            "SimpleITK is required for 3D medical Mutual Information registration. "
            "Install the project requirements first."
        )
    return sitk


def image_geometry_3d(image: Any) -> dict[str, Any]:
    """Return JSON-friendly 3D image geometry and pixel metadata."""
    _require_sitk()
    if int(image.GetDimension()) != 3:
        raise ValueError("Expected a 3D SimpleITK image.")
    return {
        "dimension": 3,
        "size_xyz": [int(value) for value in image.GetSize()],
        "spacing_xyz_mm": [float(value) for value in image.GetSpacing()],
        "origin_xyz_mm": [float(value) for value in image.GetOrigin()],
        "direction": [float(value) for value in image.GetDirection()],
        "pixel_type": str(image.GetPixelIDTypeAsString()),
        "components_per_pixel": int(image.GetNumberOfComponentsPerPixel()),
    }


def geometry_matches_3d(
    first: Any,
    second: Any,
    *,
    atol: float = 1e-8,
) -> bool:
    """Return whether two 3D images have matching spatial geometry."""
    _require_sitk()
    if int(first.GetDimension()) != 3 or int(second.GetDimension()) != 3:
        return False
    if tuple(first.GetSize()) != tuple(second.GetSize()):
        return False
    return bool(
        np.allclose(first.GetSpacing(), second.GetSpacing(), atol=atol, rtol=0.0)
        and np.allclose(first.GetOrigin(), second.GetOrigin(), atol=atol, rtol=0.0)
        and np.allclose(first.GetDirection(), second.GetDirection(), atol=atol, rtol=0.0)
    )


def sitk_transform_to_homogeneous_3d(transform: Any) -> FloatArray:
    """Convert a linear SimpleITK 3D transform to a homogeneous physical matrix."""
    _require_sitk()
    if int(transform.GetDimension()) != 3:
        raise ValueError("Only 3D SimpleITK transforms are supported by this helper.")

    p0 = np.asarray(transform.TransformPoint((0.0, 0.0, 0.0)), dtype=np.float64)
    px = np.asarray(transform.TransformPoint((1.0, 0.0, 0.0)), dtype=np.float64)
    py = np.asarray(transform.TransformPoint((0.0, 1.0, 0.0)), dtype=np.float64)
    pz = np.asarray(transform.TransformPoint((0.0, 0.0, 1.0)), dtype=np.float64)
    linear = np.column_stack((px - p0, py - p0, pz - p0))
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = linear
    matrix[:3, 3] = p0
    if not np.all(np.isfinite(matrix)):
        raise ValueError("SimpleITK transform produced non-finite coordinates.")
    if np.isclose(np.linalg.det(linear), 0.0):
        raise ValueError("SimpleITK transform is singular.")
    return matrix


def homogeneous_3d_to_sitk_affine(matrix: NDArray[np.generic]) -> Any:
    """Create a SimpleITK affine transform from a global 4 x 4 physical matrix."""
    itk = _require_sitk()
    values = np.asarray(matrix, dtype=np.float64)
    if values.shape != (4, 4):
        raise ValueError("matrix must have shape (4, 4).")
    if not np.all(np.isfinite(values)):
        raise ValueError("matrix must contain only finite values.")
    if not np.allclose(values[3], [0.0, 0.0, 0.0, 1.0], atol=1e-10):
        raise ValueError("matrix must be a homogeneous 3D affine transform.")
    if np.isclose(np.linalg.det(values[:3, :3]), 0.0):
        raise ValueError("matrix must not be singular.")
    transform = itk.AffineTransform(3)
    transform.SetMatrix(tuple(float(value) for value in values[:3, :3].reshape(-1)))
    transform.SetTranslation(tuple(float(value) for value in values[:3, 3]))
    return transform


def _initialize_rigid_3d(fixed: Any, moving: Any, mode: InitializationMode) -> Any:
    itk = _require_sitk()
    if int(fixed.GetDimension()) != 3 or int(moving.GetDimension()) != 3:
        raise ValueError("3D rigid Mutual Information requires 3D images.")

    if mode == "identity":
        transform = itk.Euler3DTransform()
        size = fixed.GetSize()
        center_index = tuple((float(value) - 1.0) / 2.0 for value in size)
        transform.SetCenter(fixed.TransformContinuousIndexToPhysicalPoint(center_index))
        return transform

    initializer = (
        itk.CenteredTransformInitializerFilter.GEOMETRY
        if mode == "geometry"
        else itk.CenteredTransformInitializerFilter.MOMENTS
    )
    return itk.CenteredTransformInitializer(
        fixed,
        moving,
        itk.Euler3DTransform(),
        initializer,
    )


def _configure_sampling(method: Any, config: MedicalMutualInformationConfig) -> None:
    if config.sampling_strategy == "none":
        method.SetMetricSamplingStrategy(method.NONE)
        return
    strategy = method.REGULAR if config.sampling_strategy == "regular" else method.RANDOM
    method.SetMetricSamplingStrategy(strategy)
    method.SetMetricSamplingPercentage(config.sampling_percentage, config.sampling_seed)


def _registration_preprocess(image: Any, sigma_mm: float) -> Any:
    itk = _require_sitk()
    output = itk.Cast(image, itk.sitkFloat32)
    if sigma_mm > 0.0:
        output = itk.SmoothingRecursiveGaussian(output, float(sigma_mm))
    return output


def resample_to_reference_3d(
    source: Any,
    reference: Any,
    reference_to_source: Any,
    *,
    interpolator: int | None = None,
    default_value: float = 0.0,
) -> Any:
    """Resample a 3D source image on the reference grid using reference -> source mapping."""
    itk = _require_sitk()
    if int(source.GetDimension()) != 3 or int(reference.GetDimension()) != 3:
        raise ValueError("3D resampling requires 3D source and reference images.")
    chosen = itk.sitkLinear if interpolator is None else interpolator
    return itk.Resample(
        source,
        reference,
        reference_to_source,
        chosen,
        float(default_value),
        source.GetPixelID(),
    )


def physical_domain_overlap_3d(
    fixed: Any,
    moving: Any,
    fixed_to_moving: Any,
) -> dict[str, float]:
    """Measure mutual field-of-view coverage under one physical transform.

    This is geometry-only overlap. It is not anatomical overlap and does not use
    image intensities, segmentations, or landmarks.
    """
    itk = _require_sitk()
    if int(fixed.GetDimension()) != 3 or int(moving.GetDimension()) != 3:
        raise ValueError("Physical-domain overlap requires 3D images.")

    moving_support = itk.GetImageFromArray(
        np.ones(tuple(reversed(moving.GetSize())), dtype=np.uint8)
    )
    moving_support.CopyInformation(moving)
    support_on_fixed = itk.Resample(
        moving_support,
        fixed,
        fixed_to_moving,
        itk.sitkNearestNeighbor,
        0,
        itk.sitkUInt8,
    )
    fixed_coverage = float(np.mean(itk.GetArrayFromImage(support_on_fixed) > 0))

    fixed_support = itk.GetImageFromArray(
        np.ones(tuple(reversed(fixed.GetSize())), dtype=np.uint8)
    )
    fixed_support.CopyInformation(fixed)
    moving_to_fixed = fixed_to_moving.GetInverse()
    support_on_moving = itk.Resample(
        fixed_support,
        moving,
        moving_to_fixed,
        itk.sitkNearestNeighbor,
        0,
        itk.sitkUInt8,
    )
    moving_coverage = float(np.mean(itk.GetArrayFromImage(support_on_moving) > 0))

    return {
        "fixed_domain_covered_by_moving_fraction": fixed_coverage,
        "moving_domain_covered_by_fixed_fraction": moving_coverage,
        "minimum_bidirectional_coverage_fraction": min(fixed_coverage, moving_coverage),
    }


def rigid_transform_diagnostics_3d(
    moving_to_fixed: NDArray[np.generic],
    *,
    fixed_size_xyz: tuple[int, int, int],
    fixed_spacing_xyz_mm: tuple[float, float, float],
    max_rotation_degrees: float = 90.0,
    max_translation_fraction_of_diagonal: float = 1.0,
    determinant_tolerance: float = 0.02,
    orthogonality_tolerance: float = 1e-5,
) -> dict[str, Any]:
    """Return numerical and broad physical plausibility diagnostics for a 3D rigid transform."""
    matrix = np.asarray(moving_to_fixed, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("moving_to_fixed must have shape (4, 4).")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("moving_to_fixed must contain finite values.")

    linear = matrix[:3, :3]
    translation = matrix[:3, 3]
    determinant = float(np.linalg.det(linear))
    orthogonality_error = float(np.linalg.norm(linear.T @ linear - np.eye(3), ord="fro"))
    trace_value = float(np.trace(linear))
    cosine = float(np.clip((trace_value - 1.0) / 2.0, -1.0, 1.0))
    rotation_degrees = float(np.degrees(np.arccos(cosine)))
    translation_norm_mm = float(np.linalg.norm(translation))

    physical_extent = np.asarray(
        [
            max(int(size) - 1, 0) * float(spacing)
            for size, spacing in zip(fixed_size_xyz, fixed_spacing_xyz_mm, strict=True)
        ],
        dtype=np.float64,
    )
    physical_diagonal_mm = float(np.linalg.norm(physical_extent))
    translation_fraction = (
        float("inf") if np.isclose(physical_diagonal_mm, 0.0) else translation_norm_mm / physical_diagonal_mm
    )

    reasons: list[str] = []
    if abs(determinant - 1.0) > determinant_tolerance:
        reasons.append("rotation_determinant_outside_tolerance")
    if orthogonality_error > orthogonality_tolerance:
        reasons.append("rotation_matrix_not_orthogonal")
    if rotation_degrees > max_rotation_degrees:
        reasons.append("rotation_exceeds_configured_plausibility_limit")
    if translation_fraction > max_translation_fraction_of_diagonal:
        reasons.append("translation_exceeds_configured_physical_diagonal_fraction")

    return {
        "determinant": determinant,
        "orthogonality_error": orthogonality_error,
        "rotation_magnitude_degrees": rotation_degrees,
        "translation_norm_mm": translation_norm_mm,
        "fixed_physical_diagonal_mm": physical_diagonal_mm,
        "translation_fraction_of_fixed_diagonal": float(translation_fraction),
        "plausible": not reasons,
        "rejection_reasons": reasons,
    }


class MutualInformationRigidRegistration3D:
    """3D rigid medical-image registration using Mattes Mutual Information."""

    def __init__(self, config: MedicalMutualInformationConfig | None = None) -> None:
        self.config = MedicalMutualInformationConfig() if config is None else config

    def register_sitk(self, fixed: Any, moving: Any) -> RegistrationResult:
        """Register 3D volumes in physical coordinates and return Moving -> Fixed."""
        itk = _require_sitk()
        if int(fixed.GetDimension()) != 3 or int(moving.GetDimension()) != 3:
            raise ValueError("3D rigid Mutual Information requires 3D images.")
        if int(fixed.GetNumberOfComponentsPerPixel()) != 1:
            raise ValueError("fixed must be a scalar 3D image.")
        if int(moving.GetNumberOfComponentsPerPixel()) != 1:
            raise ValueError("moving must be a scalar 3D image.")

        fixed_original = itk.Cast(fixed, itk.sitkFloat32)
        moving_original = itk.Cast(moving, itk.sitkFloat32)
        fixed_registration = _registration_preprocess(
            fixed_original, self.config.preprocessing_sigma_mm
        )
        moving_registration = _registration_preprocess(
            moving_original, self.config.preprocessing_sigma_mm
        )
        trace: list[dict[str, Any]] = []
        start = perf_counter()

        try:
            initial = _initialize_rigid_3d(
                fixed_registration,
                moving_registration,
                self.config.initialization,
            )
            initial_matrix = sitk_transform_to_homogeneous_3d(initial)

            method = itk.ImageRegistrationMethod()
            method.SetMetricAsMattesMutualInformation(self.config.histogram_bins)
            _configure_sampling(method, self.config)
            method.SetInterpolator(itk.sitkLinear)
            method.SetOptimizerAsRegularStepGradientDescent(
                learningRate=self.config.learning_rate,
                minStep=self.config.minimum_step,
                numberOfIterations=self.config.number_of_iterations,
                relaxationFactor=self.config.relaxation_factor,
                gradientMagnitudeTolerance=self.config.gradient_magnitude_tolerance,
            )
            method.SetOptimizerScalesFromPhysicalShift()
            method.SetShrinkFactorsPerLevel(list(self.config.shrink_factors))
            method.SetSmoothingSigmasPerLevel(list(self.config.smoothing_sigmas))
            method.SetSmoothingSigmasAreSpecifiedInPhysicalUnits(True)
            method.SetInitialTransform(initial, inPlace=False)

            def record_iteration() -> None:
                trace.append(
                    {
                        "level": int(method.GetCurrentLevel()),
                        "iteration": int(method.GetOptimizerIteration()),
                        "metric_value": float(method.GetMetricValue()),
                        "learning_rate": float(method.GetOptimizerLearningRate()),
                    }
                )

            method.AddCommand(itk.sitkIterationEvent, record_iteration)
            fixed_to_moving = method.Execute(fixed_registration, moving_registration)
            runtime = perf_counter() - start
            fixed_to_moving_matrix = sitk_transform_to_homogeneous_3d(fixed_to_moving)
            moving_to_fixed_matrix = np.linalg.inv(fixed_to_moving_matrix)

            registered = itk.Resample(
                moving_original,
                fixed_original,
                fixed_to_moving,
                itk.sitkLinear,
                0.0,
                itk.sitkFloat32,
            )
            registered_array = itk.GetArrayFromImage(registered).astype(np.float32)
            convergence = {
                "metric": "mattes_mutual_information",
                "transform_model": "rigid_3d",
                "coordinate_system": "physical",
                "histogram_bins": self.config.histogram_bins,
                "sampling_strategy": self.config.sampling_strategy,
                "sampling_percentage": (
                    1.0 if self.config.sampling_strategy == "none" else self.config.sampling_percentage
                ),
                "sampling_seed": self.config.sampling_seed,
                "initialization": self.config.initialization,
                "preprocessing_sigma_mm": self.config.preprocessing_sigma_mm,
                "shrink_factors": list(self.config.shrink_factors),
                "smoothing_sigmas": list(self.config.smoothing_sigmas),
                "final_metric_value": float(method.GetMetricValue()),
                "optimizer_iteration": int(method.GetOptimizerIteration()),
                "optimizer_stop_condition": str(method.GetOptimizerStopConditionDescription()),
                "valid_metric_points": int(method.GetMetricNumberOfValidPoints()),
                "initial_fixed_to_moving_physical_matrix": initial_matrix.tolist(),
                "fixed_to_moving_physical_matrix": fixed_to_moving_matrix.tolist(),
                "fixed_geometry": image_geometry_3d(fixed_original),
                "moving_geometry": image_geometry_3d(moving_original),
                "registered_geometry": image_geometry_3d(registered),
                "registered_geometry_matches_fixed": geometry_matches_3d(registered, fixed_original),
                "transform_direction_note": (
                    "SimpleITK registration uses Fixed -> Moving for resampling. "
                    "The returned project transform is its inverse, Moving -> Fixed."
                ),
                "metric_trace": trace,
            }
            return RegistrationResult(
                transform=moving_to_fixed_matrix.astype(np.float64),
                registered_image=registered_array,
                success=True,
                runtime_seconds=float(runtime),
                convergence_info=convergence,
                failure_reason=None,
            )
        except (RuntimeError, ValueError) as exc:
            runtime = perf_counter() - start
            identity = itk.Transform(3, itk.sitkIdentity)
            fallback = itk.Resample(
                moving_original,
                fixed_original,
                identity,
                itk.sitkLinear,
                0.0,
                itk.sitkFloat32,
            )
            return RegistrationResult(
                transform=np.eye(4, dtype=np.float64),
                registered_image=itk.GetArrayFromImage(fallback).astype(np.float32),
                success=False,
                runtime_seconds=float(runtime),
                convergence_info={
                    "metric": "mattes_mutual_information",
                    "transform_model": "rigid_3d",
                    "coordinate_system": "physical",
                    "histogram_bins": self.config.histogram_bins,
                    "sampling_strategy": self.config.sampling_strategy,
                    "sampling_percentage": (
                        1.0 if self.config.sampling_strategy == "none" else self.config.sampling_percentage
                    ),
                    "sampling_seed": self.config.sampling_seed,
                    "initialization": self.config.initialization,
                    "preprocessing_sigma_mm": self.config.preprocessing_sigma_mm,
                    "shrink_factors": list(self.config.shrink_factors),
                    "smoothing_sigmas": list(self.config.smoothing_sigmas),
                    "fixed_geometry": image_geometry_3d(fixed_original),
                    "moving_geometry": image_geometry_3d(moving_original),
                    "metric_trace": trace,
                },
                failure_reason=f"simpleitk_registration_error: {exc}",
            )
