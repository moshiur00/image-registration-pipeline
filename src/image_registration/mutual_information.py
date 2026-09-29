"""Mattes mutual-information registration for controlled multimodal experiments."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .registration import RegistrationResult

try:
    import SimpleITK as sitk
except ModuleNotFoundError:  # pragma: no cover - depends on optional runtime dependency
    sitk = None

FloatArray = NDArray[np.float64]
SamplingStrategy = Literal["none", "regular", "random"]
InitializationMode = Literal["identity", "geometry", "moments"]


@dataclass(frozen=True)
class MutualInformationConfig:
    """Configuration for 2D rigid Mattes mutual-information registration."""

    histogram_bins: int = 50
    sampling_strategy: SamplingStrategy = "random"
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


def _require_sitk() -> Any:
    if sitk is None:
        raise RuntimeError(
            "SimpleITK is required for mutual-information registration. "
            "Install the project requirements first."
        )
    return sitk


def _validate_2d_numeric_image(image: ArrayLike, name: str) -> NDArray[np.float32]:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a 2D grayscale image.")
    if array.size == 0:
        raise ValueError(f"{name} must be non-empty.")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must contain numeric values.")
    values = array.astype(np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain only finite values.")
    return values


def array_to_sitk_2d(
    image: ArrayLike,
    *,
    spacing_xy: tuple[float, float] = (1.0, 1.0),
    origin_xy: tuple[float, float] = (0.0, 0.0),
    direction: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 1.0),
) -> Any:
    """Convert a 2D NumPy image to a float SimpleITK image with explicit geometry."""
    itk = _require_sitk()
    values = _validate_2d_numeric_image(image, "image")
    spacing = tuple(float(value) for value in spacing_xy)
    origin = tuple(float(value) for value in origin_xy)
    direction_values = tuple(float(value) for value in direction)
    if len(spacing) != 2 or any(value <= 0.0 or not np.isfinite(value) for value in spacing):
        raise ValueError("spacing_xy must contain two finite positive values.")
    if len(origin) != 2 or any(not np.isfinite(value) for value in origin):
        raise ValueError("origin_xy must contain two finite values.")
    if len(direction_values) != 4 or any(not np.isfinite(value) for value in direction_values):
        raise ValueError("direction must contain four finite values.")

    output = itk.GetImageFromArray(values)
    output.SetSpacing(spacing)
    output.SetOrigin(origin)
    output.SetDirection(direction_values)
    return output


def sitk_transform_to_homogeneous_2d(transform: Any) -> FloatArray:
    """Convert a linear SimpleITK 2D transform to a homogeneous physical matrix.

    SimpleITK registration transforms map fixed-domain physical points into the
    moving-image domain. This helper preserves that direction. The caller must
    invert the matrix to obtain the project's Moving -> Fixed convention.
    """
    _require_sitk()
    if int(transform.GetDimension()) != 2:
        raise ValueError("Only 2D SimpleITK transforms are supported by this helper.")

    p0 = np.asarray(transform.TransformPoint((0.0, 0.0)), dtype=np.float64)
    px = np.asarray(transform.TransformPoint((1.0, 0.0)), dtype=np.float64)
    py = np.asarray(transform.TransformPoint((0.0, 1.0)), dtype=np.float64)
    linear = np.column_stack((px - p0, py - p0))
    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :2] = linear
    matrix[:2, 2] = p0
    if not np.all(np.isfinite(matrix)):
        raise ValueError("SimpleITK transform produced non-finite coordinates.")
    if np.isclose(np.linalg.det(linear), 0.0):
        raise ValueError("SimpleITK transform is singular.")
    return matrix


def _initialize_rigid_2d(fixed: Any, moving: Any, mode: InitializationMode) -> Any:
    itk = _require_sitk()
    if int(fixed.GetDimension()) != 2 or int(moving.GetDimension()) != 2:
        raise ValueError("Rigid Mutual Information registration currently requires 2D images.")

    if mode == "identity":
        transform = itk.Euler2DTransform()
        size = fixed.GetSize()
        center_index = ((size[0] - 1) / 2.0, (size[1] - 1) / 2.0)
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
        itk.Euler2DTransform(),
        initializer,
    )


def _configure_sampling(method: Any, config: MutualInformationConfig) -> None:
    if config.sampling_strategy == "none":
        method.SetMetricSamplingStrategy(method.NONE)
        return
    strategy = method.REGULAR if config.sampling_strategy == "regular" else method.RANDOM
    method.SetMetricSamplingStrategy(strategy)
    method.SetMetricSamplingPercentage(config.sampling_percentage, config.sampling_seed)


class MutualInformationRigidRegistration:
    """2D rigid registration using SimpleITK Mattes mutual information."""

    def __init__(self, config: MutualInformationConfig | None = None) -> None:
        self.config = MutualInformationConfig() if config is None else config

    def register(
        self,
        fixed: NDArray[np.generic],
        moving: NDArray[np.generic],
    ) -> RegistrationResult:
        """Register NumPy arrays using unit spacing and identity physical geometry."""
        fixed_itk = array_to_sitk_2d(fixed)
        moving_itk = array_to_sitk_2d(moving)
        return self.register_sitk(fixed_itk, moving_itk)

    def register_sitk(self, fixed: Any, moving: Any) -> RegistrationResult:
        """Register two 2D SimpleITK images while preserving physical geometry."""
        itk = _require_sitk()
        if int(fixed.GetDimension()) != 2 or int(moving.GetDimension()) != 2:
            raise ValueError("Week 5 Day 21 rigid MI registration currently supports 2D images only.")

        fixed_float = itk.Cast(fixed, itk.sitkFloat32)
        moving_float = itk.Cast(moving, itk.sitkFloat32)
        initial = _initialize_rigid_2d(fixed_float, moving_float, self.config.initialization)

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

        trace: list[dict[str, Any]] = []

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

        start = perf_counter()
        try:
            fixed_to_moving = method.Execute(fixed_float, moving_float)
            runtime = perf_counter() - start
            fixed_to_moving_matrix = sitk_transform_to_homogeneous_2d(fixed_to_moving)
            moving_to_fixed_matrix = np.linalg.inv(fixed_to_moving_matrix)
            registered = itk.Resample(
                moving_float,
                fixed_float,
                fixed_to_moving,
                itk.sitkLinear,
                0.0,
                itk.sitkFloat32,
            )
            registered_array = itk.GetArrayFromImage(registered).astype(np.float32)
            convergence = {
                "metric": "mattes_mutual_information",
                "histogram_bins": self.config.histogram_bins,
                "sampling_strategy": self.config.sampling_strategy,
                "sampling_percentage": (
                    1.0 if self.config.sampling_strategy == "none" else self.config.sampling_percentage
                ),
                "sampling_seed": self.config.sampling_seed,
                "initialization": self.config.initialization,
                "shrink_factors": list(self.config.shrink_factors),
                "smoothing_sigmas": list(self.config.smoothing_sigmas),
                "final_metric_value": float(method.GetMetricValue()),
                "optimizer_iteration": int(method.GetOptimizerIteration()),
                "optimizer_stop_condition": str(method.GetOptimizerStopConditionDescription()),
                "valid_metric_points": int(method.GetMetricNumberOfValidPoints()),
                "fixed_to_moving_physical_matrix": fixed_to_moving_matrix.tolist(),
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
        except RuntimeError as exc:
            runtime = perf_counter() - start
            moving_array = itk.GetArrayFromImage(moving_float).astype(np.float32)
            return RegistrationResult(
                transform=np.eye(3, dtype=np.float64),
                registered_image=moving_array,
                success=False,
                runtime_seconds=float(runtime),
                convergence_info={
                    "metric": "mattes_mutual_information",
                    "histogram_bins": self.config.histogram_bins,
                    "sampling_strategy": self.config.sampling_strategy,
                    "sampling_percentage": self.config.sampling_percentage,
                    "initialization": self.config.initialization,
                    "metric_trace": trace,
                },
                failure_reason=f"simpleitk_registration_error: {exc}",
            )
