"""SIFT keypoint detection and floating-point descriptor extraction.

This module adds the optional SIFT feature front-end used by the Week 4
extension. Matching and robust geometric estimation remain separate so SIFT
can be compared with the validated ORB pipeline under the same conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .orb import keypoint_grid_coverage


@dataclass(frozen=True)
class SIFTKeypoint:
    """Serializable subset of OpenCV SIFT keypoint metadata."""

    x: float
    y: float
    size: float
    angle_degrees: float
    response: float
    octave: int
    class_id: int


@dataclass(frozen=True)
class SIFTFeatureResult:
    """SIFT detection result with diagnostics and safe failure information."""

    keypoints: tuple[SIFTKeypoint, ...]
    descriptors: NDArray[np.float32] | None
    success: bool
    runtime_seconds: float
    image_shape: tuple[int, int]
    failure_reason: str | None = None

    @property
    def keypoint_count(self) -> int:
        return len(self.keypoints)

    @property
    def descriptor_count(self) -> int:
        if self.descriptors is None:
            return 0
        return int(self.descriptors.shape[0])

    @property
    def points_xy(self) -> NDArray[np.float64]:
        if not self.keypoints:
            return np.empty((0, 2), dtype=np.float64)
        return np.asarray([(kp.x, kp.y) for kp in self.keypoints], dtype=np.float64)

    @property
    def responses(self) -> NDArray[np.float64]:
        if not self.keypoints:
            return np.empty((0,), dtype=np.float64)
        return np.asarray([kp.response for kp in self.keypoints], dtype=np.float64)


@dataclass(frozen=True)
class SIFTConfig:
    """Configuration for OpenCV SIFT detection and descriptor extraction."""

    n_features: int = 0
    n_octave_layers: int = 3
    contrast_threshold: float = 0.04
    edge_threshold: float = 10.0
    sigma: float = 1.6

    def validate(self) -> None:
        if self.n_features < 0:
            raise ValueError("n_features must be non-negative.")
        if self.n_octave_layers <= 0:
            raise ValueError("n_octave_layers must be greater than zero.")
        if not np.isfinite(self.contrast_threshold) or self.contrast_threshold < 0.0:
            raise ValueError("contrast_threshold must be finite and non-negative.")
        if not np.isfinite(self.edge_threshold) or self.edge_threshold <= 0.0:
            raise ValueError("edge_threshold must be finite and greater than zero.")
        if not np.isfinite(self.sigma) or self.sigma <= 0.0:
            raise ValueError("sigma must be finite and greater than zero.")


def _to_sift_uint8(image: ArrayLike) -> NDArray[np.uint8]:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("SIFT expects a 2D grayscale image.")
    if array.size == 0:
        raise ValueError("SIFT expects a non-empty image.")
    if not np.all(np.isfinite(array)):
        raise ValueError("SIFT input must contain only finite values.")

    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)

    work = array.astype(np.float64, copy=False)
    minimum = float(np.min(work))
    maximum = float(np.max(work))
    if np.isclose(maximum, minimum):
        return np.zeros(array.shape, dtype=np.uint8)

    normalized = (work - minimum) / (maximum - minimum)
    scaled = np.clip(np.rint(normalized * 255.0), 0.0, 255.0)
    return np.ascontiguousarray(scaled.astype(np.uint8))


def _build_detector(config: SIFTConfig) -> cv2.SIFT:
    config.validate()
    if not hasattr(cv2, "SIFT_create"):
        raise RuntimeError("OpenCV SIFT support is not available in this environment.")
    return cv2.SIFT_create(
        nfeatures=int(config.n_features),
        nOctaveLayers=int(config.n_octave_layers),
        contrastThreshold=float(config.contrast_threshold),
        edgeThreshold=float(config.edge_threshold),
        sigma=float(config.sigma),
    )


def _serialize_keypoints(keypoints: list[cv2.KeyPoint]) -> tuple[SIFTKeypoint, ...]:
    return tuple(
        SIFTKeypoint(
            x=float(keypoint.pt[0]),
            y=float(keypoint.pt[1]),
            size=float(keypoint.size),
            angle_degrees=float(keypoint.angle),
            response=float(keypoint.response),
            octave=int(keypoint.octave),
            class_id=int(keypoint.class_id),
        )
        for keypoint in keypoints
    )


def detect_sift_features(
    image: ArrayLike,
    *,
    config: SIFTConfig | None = None,
    mask: ArrayLike | None = None,
) -> SIFTFeatureResult:
    """Detect SIFT keypoints and 128-dimensional float descriptors."""
    resolved_config = SIFTConfig() if config is None else config
    resolved_config.validate()
    prepared = _to_sift_uint8(image)

    prepared_mask: NDArray[np.uint8] | None = None
    if mask is not None:
        mask_array = np.asarray(mask)
        if mask_array.shape != prepared.shape:
            raise ValueError("SIFT mask must have the same shape as the image.")
        if mask_array.ndim != 2:
            raise ValueError("SIFT mask must be a 2D array.")
        if not np.all(np.isfinite(mask_array)):
            raise ValueError("SIFT mask must contain only finite values.")
        prepared_mask = np.where(mask_array != 0, 255, 0).astype(np.uint8)

    detector = _build_detector(resolved_config)
    start = perf_counter()
    try:
        keypoints, descriptors = detector.detectAndCompute(prepared, prepared_mask)
    except cv2.error as exc:
        return SIFTFeatureResult(
            keypoints=(),
            descriptors=None,
            success=False,
            runtime_seconds=perf_counter() - start,
            image_shape=(int(prepared.shape[0]), int(prepared.shape[1])),
            failure_reason=f"opencv_error: {exc}",
        )

    runtime = perf_counter() - start
    serialized = _serialize_keypoints(keypoints or [])
    if descriptors is None or len(serialized) == 0:
        return SIFTFeatureResult(
            keypoints=serialized,
            descriptors=None,
            success=False,
            runtime_seconds=runtime,
            image_shape=(int(prepared.shape[0]), int(prepared.shape[1])),
            failure_reason="no_keypoints_detected",
        )

    descriptor_array = np.asarray(descriptors, dtype=np.float32)
    if descriptor_array.ndim != 2 or descriptor_array.shape[0] != len(serialized):
        raise RuntimeError("SIFT returned inconsistent keypoint and descriptor counts.")
    if descriptor_array.shape[1] != 128:
        raise RuntimeError("SIFT descriptor length is expected to be 128.")

    return SIFTFeatureResult(
        keypoints=serialized,
        descriptors=np.ascontiguousarray(descriptor_array),
        success=True,
        runtime_seconds=runtime,
        image_shape=(int(prepared.shape[0]), int(prepared.shape[1])),
        failure_reason=None,
    )


def sift_keypoint_response_summary(result: SIFTFeatureResult) -> dict[str, float | None]:
    """Return compact response statistics for one SIFT feature result."""
    responses = result.responses
    if responses.size == 0:
        return {"mean": None, "median": None, "minimum": None, "maximum": None}
    return {
        "mean": float(np.mean(responses)),
        "median": float(np.median(responses)),
        "minimum": float(np.min(responses)),
        "maximum": float(np.max(responses)),
    }


def sift_spatial_coverage(
    result: SIFTFeatureResult,
    *,
    rows: int = 4,
    columns: int = 4,
) -> float:
    """Return grid coverage of detected SIFT keypoints."""
    return keypoint_grid_coverage(
        result.points_xy,
        result.image_shape,
        rows=rows,
        columns=columns,
    )


def draw_sift_keypoints(
    image: ArrayLike,
    result: SIFTFeatureResult,
    *,
    rich: bool = True,
) -> NDArray[np.uint8]:
    """Return an RGB visualization of detected SIFT keypoints."""
    prepared = _to_sift_uint8(image)
    keypoints = [
        cv2.KeyPoint(
            x=float(keypoint.x),
            y=float(keypoint.y),
            size=float(keypoint.size),
            angle=float(keypoint.angle_degrees),
            response=float(keypoint.response),
            octave=int(keypoint.octave),
            class_id=int(keypoint.class_id),
        )
        for keypoint in result.keypoints
    ]
    flags = cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS if rich else cv2.DRAW_MATCHES_FLAGS_DEFAULT
    bgr = cv2.drawKeypoints(prepared, keypoints, None, flags=flags)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
