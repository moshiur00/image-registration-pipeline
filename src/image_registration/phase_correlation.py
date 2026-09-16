"""Translation registration using frequency-domain phase correlation."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .registration import RegistrationResult
from .transforms import identity_matrix, translation_matrix
from .warping import InterpolationName, warp_image

FloatArray = NDArray[np.float64]
WindowName = Literal["hann", "none"]


@dataclass(frozen=True)
class PhaseCorrelationEstimate:
    """Estimated Moving -> Fixed translation and phase-correlation response."""

    tx: float
    ty: float
    response: float

    @property
    def vector(self) -> FloatArray:
        """Return the estimated translation as ``[tx, ty]``."""
        return np.array([self.tx, self.ty], dtype=np.float64)


def _validate_pair(
    fixed: ArrayLike,
    moving: ArrayLike,
) -> tuple[FloatArray, FloatArray]:
    fixed_array = np.asarray(fixed, dtype=np.float64)
    moving_array = np.asarray(moving, dtype=np.float64)

    if fixed_array.ndim != 2 or moving_array.ndim != 2:
        raise ValueError("Phase correlation expects 2D grayscale images.")
    if fixed_array.shape != moving_array.shape:
        raise ValueError("Fixed and moving images must have identical shapes.")
    if fixed_array.size == 0:
        raise ValueError("Fixed and moving images must be non-empty.")
    if not np.all(np.isfinite(fixed_array)) or not np.all(np.isfinite(moving_array)):
        raise ValueError("Fixed and moving images must contain only finite values.")

    return fixed_array, moving_array


def _prepare_inputs(
    fixed: ArrayLike,
    moving: ArrayLike,
    *,
    subtract_mean: bool,
) -> tuple[FloatArray, FloatArray]:
    fixed_array, moving_array = _validate_pair(fixed, moving)
    fixed_prepared = fixed_array.copy()
    moving_prepared = moving_array.copy()

    if subtract_mean:
        fixed_prepared -= float(np.mean(fixed_prepared))
        moving_prepared -= float(np.mean(moving_prepared))

    if np.isclose(float(np.std(fixed_prepared)), 0.0):
        raise ValueError("Fixed image has insufficient intensity variation.")
    if np.isclose(float(np.std(moving_prepared)), 0.0):
        raise ValueError("Moving image has insufficient intensity variation.")

    return fixed_prepared, moving_prepared


def _hann_window(shape: tuple[int, int]) -> FloatArray:
    height, width = int(shape[0]), int(shape[1])
    return cv2.createHanningWindow((width, height), cv2.CV_64F)


def estimate_phase_correlation(
    fixed: ArrayLike,
    moving: ArrayLike,
    *,
    use_hanning_window: bool = True,
    subtract_mean: bool = True,
) -> PhaseCorrelationEstimate:
    """Estimate a Moving -> Fixed translation with OpenCV phase correlation.

    OpenCV returns the displacement from its first source image to its second.
    The project stores transforms as Moving -> Fixed, so ``moving`` is passed as
    the first source and ``fixed`` as the second source.
    """
    fixed_prepared, moving_prepared = _prepare_inputs(
        fixed,
        moving,
        subtract_mean=subtract_mean,
    )
    window = _hann_window(fixed_prepared.shape) if use_hanning_window else None

    shift, response = cv2.phaseCorrelate(
        moving_prepared,
        fixed_prepared,
        window,
    )
    tx, ty = float(shift[0]), float(shift[1])
    response_value = float(response)

    if not np.isfinite(tx) or not np.isfinite(ty) or not np.isfinite(response_value):
        raise RuntimeError("Phase correlation returned a non-finite estimate.")

    return PhaseCorrelationEstimate(tx=tx, ty=ty, response=response_value)


def phase_correlation_surface(
    fixed: ArrayLike,
    moving: ArrayLike,
    *,
    use_hanning_window: bool = True,
    subtract_mean: bool = True,
    epsilon: float = 1e-12,
) -> FloatArray:
    """Return a centered normalized cross-power correlation surface.

    The peak is located at the integer Moving -> Fixed displacement relative to
    the center of the returned array. This function is intended for diagnostics
    and teaching. The production estimate uses OpenCV for its subpixel centroid
    refinement.
    """
    if not np.isfinite(epsilon) or epsilon <= 0.0:
        raise ValueError("epsilon must be finite and greater than zero.")

    fixed_prepared, moving_prepared = _prepare_inputs(
        fixed,
        moving,
        subtract_mean=subtract_mean,
    )
    if use_hanning_window:
        window = _hann_window(fixed_prepared.shape)
        fixed_prepared = fixed_prepared * window
        moving_prepared = moving_prepared * window

    fixed_fft = np.fft.fft2(fixed_prepared)
    moving_fft = np.fft.fft2(moving_prepared)
    cross_power = fixed_fft * np.conj(moving_fft)
    magnitude = np.abs(cross_power)

    normalized = np.zeros_like(cross_power)
    valid = magnitude > float(epsilon)
    normalized[valid] = cross_power[valid] / magnitude[valid]

    correlation = np.abs(np.fft.ifft2(normalized))
    centered = np.fft.fftshift(correlation)
    return centered.astype(np.float64, copy=False)


class PhaseCorrelationRegistration:
    """Register 2D grayscale images using translation-only phase correlation."""

    def __init__(
        self,
        *,
        use_hanning_window: bool = True,
        subtract_mean: bool = True,
        interpolation: InterpolationName = "linear",
        min_response: float | None = None,
    ) -> None:
        if interpolation not in {"nearest", "linear", "cubic"}:
            raise ValueError("interpolation must be nearest, linear, or cubic.")
        if min_response is not None and not np.isfinite(min_response):
            raise ValueError("min_response must be finite when provided.")

        self.use_hanning_window = bool(use_hanning_window)
        self.subtract_mean = bool(subtract_mean)
        self.interpolation = interpolation
        self.min_response = None if min_response is None else float(min_response)

    def register(
        self,
        fixed: NDArray[np.generic],
        moving: NDArray[np.generic],
    ) -> RegistrationResult:
        """Estimate translation and return the standard registration result."""
        total_start = perf_counter()
        estimate_start = perf_counter()

        try:
            estimate = estimate_phase_correlation(
                fixed,
                moving,
                use_hanning_window=self.use_hanning_window,
                subtract_mean=self.subtract_mean,
            )
            estimate_seconds = perf_counter() - estimate_start

            transform = translation_matrix(estimate.tx, estimate.ty)
            warp_start = perf_counter()
            registered = warp_image(
                moving,
                transform,
                output_shape=(int(np.asarray(fixed).shape[0]), int(np.asarray(fixed).shape[1])),
                interpolation=self.interpolation,
                border_value=0.0,
            )
            warp_seconds = perf_counter() - warp_start

            success = True
            failure_reason = None
            if self.min_response is not None and estimate.response < self.min_response:
                success = False
                failure_reason = "phase_response_below_threshold"

            return RegistrationResult(
                transform=transform,
                registered_image=registered,
                success=success,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "phase_correlation",
                    "motion_model": "translation",
                    "tx": estimate.tx,
                    "ty": estimate.ty,
                    "response": estimate.response,
                    "use_hanning_window": self.use_hanning_window,
                    "subtract_mean": self.subtract_mean,
                    "interpolation": self.interpolation,
                    "min_response": self.min_response,
                    "estimation_seconds": estimate_seconds,
                    "warp_seconds": warp_seconds,
                },
                failure_reason=failure_reason,
            )

        except (ValueError, RuntimeError, cv2.error) as exc:
            moving_array = np.asarray(moving)
            fallback_image = moving_array.copy()
            return RegistrationResult(
                transform=identity_matrix(),
                registered_image=fallback_image,
                success=False,
                runtime_seconds=perf_counter() - total_start,
                convergence_info={
                    "method": "phase_correlation",
                    "motion_model": "translation",
                    "use_hanning_window": self.use_hanning_window,
                    "subtract_mean": self.subtract_mean,
                    "interpolation": self.interpolation,
                    "min_response": self.min_response,
                },
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
