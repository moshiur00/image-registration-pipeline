"""ECC registration for 2D monomodal translation, rigid, and affine motion."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Sequence

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .phase_correlation import estimate_phase_correlation
from .pyramids import build_image_pyramid, rescale_transform_between_shapes, validate_pyramid_scales
from .registration import RegistrationResult
from .transforms import identity_matrix, invert_transform, translation_matrix
from .warping import InterpolationName, warp_image

FloatArray = NDArray[np.float64]
ECCMotionModel = Literal["translation", "rigid", "affine"]
ECCInitialization = Literal["identity", "phase_correlation", "provided"]


@dataclass(frozen=True)
class ECCEstimate:
    """One ECC estimate expressed in the project Moving -> Fixed convention."""

    moving_to_fixed: FloatArray
    fixed_to_moving: FloatArray
    final_ecc: float
    initialization: ECCInitialization
    initial_moving_to_fixed: FloatArray


def _validate_pair(
    fixed: ArrayLike,
    moving: ArrayLike,
) -> tuple[FloatArray, FloatArray]:
    fixed_array = np.asarray(fixed, dtype=np.float64)
    moving_array = np.asarray(moving, dtype=np.float64)

    if fixed_array.ndim != 2 or moving_array.ndim != 2:
        raise ValueError("ECC expects 2D grayscale images.")
    if fixed_array.shape != moving_array.shape:
        raise ValueError("Fixed and moving images must have identical shapes.")
    if fixed_array.size == 0:
        raise ValueError("Fixed and moving images must be non-empty.")
    if not np.all(np.isfinite(fixed_array)) or not np.all(np.isfinite(moving_array)):
        raise ValueError("Fixed and moving images must contain only finite values.")
    if np.isclose(float(np.std(fixed_array)), 0.0):
        raise ValueError("Fixed image has insufficient intensity variation.")
    if np.isclose(float(np.std(moving_array)), 0.0):
        raise ValueError("Moving image has insufficient intensity variation.")

    return fixed_array, moving_array


def _prepare_ecc_inputs(
    fixed: ArrayLike,
    moving: ArrayLike,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Convert an image pair to a shared finite float32 intensity range."""
    fixed_array, moving_array = _validate_pair(fixed, moving)
    low = float(min(np.min(fixed_array), np.min(moving_array)))
    high = float(max(np.max(fixed_array), np.max(moving_array)))
    scale = high - low
    if np.isclose(scale, 0.0):
        raise ValueError("ECC image pair has insufficient joint intensity range.")

    fixed_prepared = ((fixed_array - low) / scale).astype(np.float32)
    moving_prepared = ((moving_array - low) / scale).astype(np.float32)
    return fixed_prepared, moving_prepared


def _opencv_motion_type(motion_model: ECCMotionModel) -> int:
    if motion_model == "translation":
        return cv2.MOTION_TRANSLATION
    if motion_model == "rigid":
        return cv2.MOTION_EUCLIDEAN
    if motion_model == "affine":
        return cv2.MOTION_AFFINE
    raise ValueError("motion_model must be translation, rigid, or affine.")


def _validate_gaussian_filter_size(value: int) -> int:
    size = int(value)
    if size <= 0 or size % 2 == 0:
        raise ValueError("gauss_filt_size must be a positive odd integer.")
    return size


def _initial_moving_to_fixed(
    fixed: NDArray[np.float32],
    moving: NDArray[np.float32],
    initialization: ECCInitialization,
    *,
    phase_use_hanning_window: bool,
    phase_subtract_mean: bool,
    provided_transform: ArrayLike | None = None,
) -> FloatArray:
    if initialization == "identity":
        return identity_matrix()
    if initialization == "phase_correlation":
        estimate = estimate_phase_correlation(
            fixed,
            moving,
            use_hanning_window=phase_use_hanning_window,
            subtract_mean=phase_subtract_mean,
        )
        return translation_matrix(estimate.tx, estimate.ty)
    if initialization == "provided":
        if provided_transform is None:
            raise ValueError("provided initialization requires an initial transform.")
        matrix = np.asarray(provided_transform, dtype=np.float64)
        if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
            raise ValueError("initial transform must be a finite 3x3 matrix.")
        if not np.isclose(matrix[2, 2], 1.0) or not np.allclose(matrix[2, :2], 0.0):
            raise ValueError("initial transform must be a 2D affine-form homogeneous matrix.")
        return matrix.copy()
    raise ValueError("initialization must be identity, phase_correlation, or provided.")


def estimate_ecc(
    fixed: ArrayLike,
    moving: ArrayLike,
    *,
    motion_model: ECCMotionModel = "translation",
    initialization: ECCInitialization = "identity",
    max_iterations: int = 150,
    epsilon: float = 1e-6,
    gauss_filt_size: int = 5,
    phase_use_hanning_window: bool = True,
    phase_subtract_mean: bool = True,
    initial_transform: ArrayLike | None = None,
) -> ECCEstimate:
    """Estimate a Moving -> Fixed transform with OpenCV ECC.

    OpenCV ``findTransformECC`` stores a warp that is conventionally used with
    ``WARP_INVERSE_MAP``. In this project that matrix is treated as Fixed ->
    Moving and inverted before it is returned, preserving the global Moving ->
    Fixed convention.
    """
    if int(max_iterations) <= 0:
        raise ValueError("max_iterations must be greater than zero.")
    if not np.isfinite(epsilon) or float(epsilon) <= 0.0:
        raise ValueError("epsilon must be finite and greater than zero.")

    filter_size = _validate_gaussian_filter_size(gauss_filt_size)
    cv_motion = _opencv_motion_type(motion_model)
    fixed_prepared, moving_prepared = _prepare_ecc_inputs(fixed, moving)

    initial_m2f = _initial_moving_to_fixed(
        fixed_prepared,
        moving_prepared,
        initialization,
        phase_use_hanning_window=phase_use_hanning_window,
        phase_subtract_mean=phase_subtract_mean,
        provided_transform=initial_transform,
    )
    initial_f2m = invert_transform(initial_m2f)
    opencv_warp = initial_f2m[:2, :].astype(np.float32, copy=True)

    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
        int(max_iterations),
        float(epsilon),
    )

    final_ecc, estimated_opencv_warp = cv2.findTransformECC(
        fixed_prepared,
        moving_prepared,
        opencv_warp,
        cv_motion,
        criteria,
        None,
        filter_size,
    )

    fixed_to_moving = identity_matrix()
    fixed_to_moving[:2, :] = np.asarray(estimated_opencv_warp, dtype=np.float64)
    moving_to_fixed = invert_transform(fixed_to_moving)
    final_ecc_value = float(final_ecc)

    if not np.all(np.isfinite(moving_to_fixed)) or not np.isfinite(final_ecc_value):
        raise RuntimeError("ECC returned a non-finite estimate.")

    return ECCEstimate(
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=fixed_to_moving,
        final_ecc=final_ecc_value,
        initialization=initialization,
        initial_moving_to_fixed=initial_m2f,
    )


def rigid_angle_degrees(transform: ArrayLike) -> float:
    """Return the project rotation angle from a rigid 3x3 matrix."""
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("transform must be a finite 3x3 matrix.")
    return float(np.rad2deg(np.arctan2(matrix[0, 1], matrix[0, 0])))


class ECCRegistration:
    """Register 2D grayscale images with OpenCV ECC."""

    def __init__(
        self,
        *,
        motion_model: ECCMotionModel = "translation",
        initialization: ECCInitialization = "identity",
        max_iterations: int = 150,
        epsilon: float = 1e-6,
        gauss_filt_size: int = 5,
        interpolation: InterpolationName = "linear",
        phase_use_hanning_window: bool = True,
        phase_subtract_mean: bool = True,
        min_ecc: float | None = None,
        initial_transform: ArrayLike | None = None,
    ) -> None:
        _opencv_motion_type(motion_model)
        if initialization not in {"identity", "phase_correlation", "provided"}:
            raise ValueError("initialization must be identity, phase_correlation, or provided.")
        if int(max_iterations) <= 0:
            raise ValueError("max_iterations must be greater than zero.")
        if not np.isfinite(epsilon) or float(epsilon) <= 0.0:
            raise ValueError("epsilon must be finite and greater than zero.")
        _validate_gaussian_filter_size(gauss_filt_size)
        if interpolation not in {"nearest", "linear", "cubic"}:
            raise ValueError("interpolation must be nearest, linear, or cubic.")
        if min_ecc is not None and not np.isfinite(min_ecc):
            raise ValueError("min_ecc must be finite when provided.")
        if initialization == "provided" and initial_transform is None:
            raise ValueError("provided initialization requires initial_transform.")
        if initialization != "provided" and initial_transform is not None:
            raise ValueError("initial_transform can only be used with provided initialization.")

        self.motion_model = motion_model
        self.initialization = initialization
        self.max_iterations = int(max_iterations)
        self.epsilon = float(epsilon)
        self.gauss_filt_size = int(gauss_filt_size)
        self.interpolation = interpolation
        self.phase_use_hanning_window = bool(phase_use_hanning_window)
        self.phase_subtract_mean = bool(phase_subtract_mean)
        self.min_ecc = None if min_ecc is None else float(min_ecc)
        self.initial_transform = None if initial_transform is None else np.asarray(initial_transform, dtype=np.float64).copy()

    def register(
        self,
        fixed: NDArray[np.generic],
        moving: NDArray[np.generic],
    ) -> RegistrationResult:
        """Estimate translation, rigid, or affine motion and return a standard result."""
        total_start = perf_counter()
        estimate_start = perf_counter()

        try:
            estimate = estimate_ecc(
                fixed,
                moving,
                motion_model=self.motion_model,
                initialization=self.initialization,
                max_iterations=self.max_iterations,
                epsilon=self.epsilon,
                gauss_filt_size=self.gauss_filt_size,
                phase_use_hanning_window=self.phase_use_hanning_window,
                phase_subtract_mean=self.phase_subtract_mean,
                initial_transform=self.initial_transform,
            )
            estimate_seconds = perf_counter() - estimate_start

            warp_start = perf_counter()
            registered = warp_image(
                moving,
                estimate.moving_to_fixed,
                output_shape=(int(np.asarray(fixed).shape[0]), int(np.asarray(fixed).shape[1])),
                interpolation=self.interpolation,
                border_value=0.0,
            )
            warp_seconds = perf_counter() - warp_start

            success = True
            failure_reason = None
            if self.min_ecc is not None and estimate.final_ecc < self.min_ecc:
                success = False
                failure_reason = "ecc_below_threshold"

            convergence_info = {
                "method": "ecc",
                "motion_model": self.motion_model,
                "initialization": self.initialization,
                "final_ecc": estimate.final_ecc,
                "max_iterations": self.max_iterations,
                "epsilon": self.epsilon,
                "gauss_filt_size": self.gauss_filt_size,
                "interpolation": self.interpolation,
                "min_ecc": self.min_ecc,
                "phase_use_hanning_window": self.phase_use_hanning_window,
                "phase_subtract_mean": self.phase_subtract_mean,
                "initial_moving_to_fixed": estimate.initial_moving_to_fixed.tolist(),
                "estimated_fixed_to_moving": estimate.fixed_to_moving.tolist(),
                "estimation_seconds": estimate_seconds,
                "warp_seconds": warp_seconds,
            }
            if self.motion_model == "rigid":
                convergence_info["estimated_angle_degrees"] = rigid_angle_degrees(
                    estimate.moving_to_fixed
                )

            return RegistrationResult(
                transform=estimate.moving_to_fixed,
                registered_image=registered,
                success=success,
                runtime_seconds=perf_counter() - total_start,
                convergence_info=convergence_info,
                failure_reason=failure_reason,
            )

        except ValueError as exc:
            return RegistrationResult(
                transform=identity_matrix(),
                registered_image=np.asarray(moving).copy(),
                success=False,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "ecc",
                    "motion_model": self.motion_model,
                    "initialization": self.initialization,
                    "error_message": str(exc),
                },
                failure_reason="invalid_input",
            )
        except cv2.error as exc:
            return RegistrationResult(
                transform=identity_matrix(),
                registered_image=np.asarray(moving).copy(),
                success=False,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "ecc",
                    "motion_model": self.motion_model,
                    "initialization": self.initialization,
                    "error_message": str(exc).splitlines()[0] if str(exc) else "OpenCV ECC error",
                },
                failure_reason="ecc_optimization_failed",
            )
        except RuntimeError as exc:
            return RegistrationResult(
                transform=identity_matrix(),
                registered_image=np.asarray(moving).copy(),
                success=False,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "ecc",
                    "motion_model": self.motion_model,
                    "initialization": self.initialization,
                    "error_message": str(exc),
                },
                failure_reason="ecc_runtime_failure",
            )


class MultiResolutionECCRegistration:
    """Run ECC from coarse to fine while preserving Moving -> Fixed geometry."""

    def __init__(
        self,
        *,
        motion_model: ECCMotionModel = "affine",
        initialization: Literal["identity", "phase_correlation"] = "identity",
        pyramid_scales: Sequence[float] = (0.25, 0.5, 1.0),
        pre_smoothing_sigma: float = 0.8,
        max_iterations: int = 120,
        epsilon: float = 1e-6,
        gauss_filt_size: int = 5,
        interpolation: InterpolationName = "linear",
        phase_use_hanning_window: bool = True,
        phase_subtract_mean: bool = True,
        min_ecc: float | None = None,
    ) -> None:
        _opencv_motion_type(motion_model)
        if initialization not in {"identity", "phase_correlation"}:
            raise ValueError("initialization must be identity or phase_correlation.")
        self.pyramid_scales = validate_pyramid_scales(pyramid_scales)
        if not np.isfinite(pre_smoothing_sigma) or pre_smoothing_sigma < 0.0:
            raise ValueError("pre_smoothing_sigma must be finite and non-negative.")
        if int(max_iterations) <= 0:
            raise ValueError("max_iterations must be greater than zero.")
        if not np.isfinite(epsilon) or float(epsilon) <= 0.0:
            raise ValueError("epsilon must be finite and greater than zero.")
        _validate_gaussian_filter_size(gauss_filt_size)
        if interpolation not in {"nearest", "linear", "cubic"}:
            raise ValueError("interpolation must be nearest, linear, or cubic.")
        if min_ecc is not None and not np.isfinite(min_ecc):
            raise ValueError("min_ecc must be finite when provided.")

        self.motion_model = motion_model
        self.initialization = initialization
        self.pre_smoothing_sigma = float(pre_smoothing_sigma)
        self.max_iterations = int(max_iterations)
        self.epsilon = float(epsilon)
        self.gauss_filt_size = int(gauss_filt_size)
        self.interpolation = interpolation
        self.phase_use_hanning_window = bool(phase_use_hanning_window)
        self.phase_subtract_mean = bool(phase_subtract_mean)
        self.min_ecc = None if min_ecc is None else float(min_ecc)

    def register(
        self,
        fixed: NDArray[np.generic],
        moving: NDArray[np.generic],
    ) -> RegistrationResult:
        total_start = perf_counter()
        try:
            fixed_array, moving_array = _validate_pair(fixed, moving)
            fixed_levels = build_image_pyramid(
                fixed_array,
                self.pyramid_scales,
                pre_smoothing_sigma=self.pre_smoothing_sigma,
            )
            moving_levels = build_image_pyramid(
                moving_array,
                self.pyramid_scales,
                pre_smoothing_sigma=self.pre_smoothing_sigma,
            )

            current_transform: FloatArray | None = None
            previous_shape: tuple[int, int] | None = None
            level_records: list[dict[str, object]] = []
            final_ecc: float | None = None
            failure_reason: str | None = None

            for index, (fixed_level, moving_level) in enumerate(
                zip(fixed_levels, moving_levels, strict=True)
            ):
                level_shape = fixed_level.shape
                if current_transform is None:
                    level_initialization: ECCInitialization = self.initialization
                    supplied = None
                else:
                    if previous_shape is None:
                        raise RuntimeError("Missing previous pyramid shape.")
                    current_transform = rescale_transform_between_shapes(
                        current_transform,
                        previous_shape,
                        level_shape,
                    )
                    level_initialization = "provided"
                    supplied = current_transform

                level_start = perf_counter()
                try:
                    estimate = estimate_ecc(
                        fixed_level.image,
                        moving_level.image,
                        motion_model=self.motion_model,
                        initialization=level_initialization,
                        max_iterations=self.max_iterations,
                        epsilon=self.epsilon,
                        gauss_filt_size=self.gauss_filt_size,
                        phase_use_hanning_window=self.phase_use_hanning_window,
                        phase_subtract_mean=self.phase_subtract_mean,
                        initial_transform=supplied,
                    )
                except (cv2.error, RuntimeError) as exc:
                    failure_reason = "ecc_pyramid_level_failed"
                    level_records.append(
                        {
                            "level_index": index,
                            "scale": fixed_level.scale,
                            "shape": list(level_shape),
                            "success": False,
                            "runtime_seconds": perf_counter() - level_start,
                            "error_message": str(exc).splitlines()[0] if str(exc) else "OpenCV ECC error",
                        }
                    )
                    break

                current_transform = estimate.moving_to_fixed
                previous_shape = level_shape
                final_ecc = estimate.final_ecc
                level_records.append(
                    {
                        "level_index": index,
                        "scale": fixed_level.scale,
                        "shape": list(level_shape),
                        "success": True,
                        "runtime_seconds": perf_counter() - level_start,
                        "final_ecc": final_ecc,
                        "moving_to_fixed": current_transform.tolist(),
                    }
                )

            if current_transform is None:
                final_transform = identity_matrix()
            else:
                final_transform = current_transform
                if previous_shape is not None and previous_shape != fixed_array.shape:
                    final_transform = rescale_transform_between_shapes(
                        final_transform,
                        previous_shape,
                        (int(fixed_array.shape[0]), int(fixed_array.shape[1])),
                    )

            warp_start = perf_counter()
            registered = warp_image(
                moving,
                final_transform,
                output_shape=(int(fixed_array.shape[0]), int(fixed_array.shape[1])),
                interpolation=self.interpolation,
                border_value=0.0,
            )
            warp_seconds = perf_counter() - warp_start

            success = failure_reason is None and len(level_records) == len(self.pyramid_scales)
            if success and self.min_ecc is not None and final_ecc is not None and final_ecc < self.min_ecc:
                success = False
                failure_reason = "ecc_below_threshold"

            return RegistrationResult(
                transform=final_transform,
                registered_image=registered,
                success=success,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "ecc_multiresolution",
                    "motion_model": self.motion_model,
                    "initialization": self.initialization,
                    "pyramid_scales": list(self.pyramid_scales),
                    "pre_smoothing_sigma": self.pre_smoothing_sigma,
                    "max_iterations_per_level": self.max_iterations,
                    "epsilon": self.epsilon,
                    "gauss_filt_size": self.gauss_filt_size,
                    "final_ecc": final_ecc,
                    "levels_completed": sum(bool(record.get("success")) for record in level_records),
                    "level_records": level_records,
                    "warp_seconds": warp_seconds,
                },
                failure_reason=failure_reason,
            )

        except ValueError as exc:
            return RegistrationResult(
                transform=identity_matrix(),
                registered_image=np.asarray(moving).copy(),
                success=False,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "ecc_multiresolution",
                    "motion_model": self.motion_model,
                    "initialization": self.initialization,
                    "error_message": str(exc),
                },
                failure_reason="invalid_input",
            )
