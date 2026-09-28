"""ORB keypoint detection and binary descriptor extraction.

This module provides the feature-detection layer used by the Week 4
feature-based registration work. Matching and robust model estimation are kept
separate so detection behavior can be measured independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

ScoreType = Literal["harris", "fast"]


@dataclass(frozen=True)
class ORBKeypoint:
    """Serializable subset of OpenCV keypoint metadata."""

    x: float
    y: float
    size: float
    angle_degrees: float
    response: float
    octave: int
    class_id: int


@dataclass(frozen=True)
class ORBFeatureResult:
    """ORB detection result with diagnostics and safe failure information."""

    keypoints: tuple[ORBKeypoint, ...]
    descriptors: NDArray[np.uint8] | None
    success: bool
    runtime_seconds: float
    image_shape: tuple[int, int]
    failure_reason: str | None = None

    @property
    def keypoint_count(self) -> int:
        """Return the number of detected keypoints."""
        return len(self.keypoints)

    @property
    def descriptor_count(self) -> int:
        """Return the number of binary descriptors."""
        if self.descriptors is None:
            return 0
        return int(self.descriptors.shape[0])

    @property
    def points_xy(self) -> NDArray[np.float64]:
        """Return keypoint coordinates as an ``(N, 2)`` array in ``(x, y)`` order."""
        if not self.keypoints:
            return np.empty((0, 2), dtype=np.float64)
        return np.asarray([(kp.x, kp.y) for kp in self.keypoints], dtype=np.float64)

    @property
    def responses(self) -> NDArray[np.float64]:
        """Return keypoint response values."""
        if not self.keypoints:
            return np.empty((0,), dtype=np.float64)
        return np.asarray([kp.response for kp in self.keypoints], dtype=np.float64)


@dataclass(frozen=True)
class ORBConfig:
    """Configuration for OpenCV ORB detection and descriptor extraction."""

    n_features: int = 800
    scale_factor: float = 1.2
    n_levels: int = 8
    edge_threshold: int = 31
    first_level: int = 0
    wta_k: int = 2
    score_type: ScoreType = "harris"
    patch_size: int = 31
    fast_threshold: int = 20

    def validate(self) -> None:
        """Validate values before constructing the OpenCV detector."""
        if self.n_features <= 0:
            raise ValueError("n_features must be greater than zero.")
        if not np.isfinite(self.scale_factor) or self.scale_factor <= 1.0:
            raise ValueError("scale_factor must be finite and greater than 1.0.")
        if self.n_levels <= 0:
            raise ValueError("n_levels must be greater than zero.")
        if self.edge_threshold < 0:
            raise ValueError("edge_threshold must be non-negative.")
        if self.first_level < 0 or self.first_level >= self.n_levels:
            raise ValueError("first_level must be in the range [0, n_levels).")
        if self.wta_k not in {2, 3, 4}:
            raise ValueError("wta_k must be one of 2, 3, or 4.")
        if self.score_type not in {"harris", "fast"}:
            raise ValueError("score_type must be harris or fast.")
        if self.patch_size <= 1:
            raise ValueError("patch_size must be greater than one.")
        if self.fast_threshold < 0:
            raise ValueError("fast_threshold must be non-negative.")


def _to_orb_uint8(image: ArrayLike) -> NDArray[np.uint8]:
    """Convert one 2D intensity image to the uint8 representation ORB expects."""
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("ORB expects a 2D grayscale image.")
    if array.size == 0:
        raise ValueError("ORB expects a non-empty image.")
    if not np.all(np.isfinite(array)):
        raise ValueError("ORB input must contain only finite values.")

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


def _score_flag(score_type: ScoreType) -> int:
    return cv2.ORB_HARRIS_SCORE if score_type == "harris" else cv2.ORB_FAST_SCORE


def _build_detector(config: ORBConfig) -> cv2.ORB:
    config.validate()
    return cv2.ORB_create(
        nfeatures=int(config.n_features),
        scaleFactor=float(config.scale_factor),
        nlevels=int(config.n_levels),
        edgeThreshold=int(config.edge_threshold),
        firstLevel=int(config.first_level),
        WTA_K=int(config.wta_k),
        scoreType=_score_flag(config.score_type),
        patchSize=int(config.patch_size),
        fastThreshold=int(config.fast_threshold),
    )


def _serialize_keypoints(keypoints: list[cv2.KeyPoint]) -> tuple[ORBKeypoint, ...]:
    return tuple(
        ORBKeypoint(
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


def detect_orb_features(
    image: ArrayLike,
    *,
    config: ORBConfig | None = None,
    mask: ArrayLike | None = None,
) -> ORBFeatureResult:
    """Detect ORB keypoints and binary descriptors on one grayscale image.

    An image with no detectable features returns a safe failure result rather
    than raising an exception. Invalid inputs and invalid configuration values
    still raise ``ValueError`` because they indicate caller or configuration
    errors rather than an expected image-content limitation.
    """
    resolved_config = ORBConfig() if config is None else config
    resolved_config.validate()
    prepared = _to_orb_uint8(image)

    prepared_mask: NDArray[np.uint8] | None = None
    if mask is not None:
        mask_array = np.asarray(mask)
        if mask_array.shape != prepared.shape:
            raise ValueError("ORB mask must have the same shape as the image.")
        if mask_array.ndim != 2:
            raise ValueError("ORB mask must be a 2D array.")
        if not np.all(np.isfinite(mask_array)):
            raise ValueError("ORB mask must contain only finite values.")
        prepared_mask = np.where(mask_array != 0, 255, 0).astype(np.uint8)

    detector = _build_detector(resolved_config)
    start = perf_counter()
    try:
        keypoints, descriptors = detector.detectAndCompute(prepared, prepared_mask)
    except cv2.error as exc:
        return ORBFeatureResult(
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
        return ORBFeatureResult(
            keypoints=serialized,
            descriptors=None,
            success=False,
            runtime_seconds=runtime,
            image_shape=(int(prepared.shape[0]), int(prepared.shape[1])),
            failure_reason="no_keypoints_detected",
        )

    descriptor_array = np.asarray(descriptors, dtype=np.uint8)
    if descriptor_array.ndim != 2 or descriptor_array.shape[0] != len(serialized):
        raise RuntimeError("ORB returned inconsistent keypoint and descriptor counts.")

    return ORBFeatureResult(
        keypoints=serialized,
        descriptors=np.ascontiguousarray(descriptor_array),
        success=True,
        runtime_seconds=runtime,
        image_shape=(int(prepared.shape[0]), int(prepared.shape[1])),
        failure_reason=None,
    )


def keypoint_grid_coverage(
    keypoints: ArrayLike,
    image_shape: tuple[int, int],
    *,
    rows: int = 4,
    columns: int = 4,
) -> float:
    """Return the fraction of grid cells containing at least one keypoint."""
    if rows <= 0 or columns <= 0:
        raise ValueError("rows and columns must be greater than zero.")
    height, width = int(image_shape[0]), int(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("image_shape values must be greater than zero.")

    points = np.asarray(keypoints, dtype=np.float64)
    if points.size == 0:
        return 0.0
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("keypoints must have shape (N, 2).")
    if not np.all(np.isfinite(points)):
        raise ValueError("keypoints must contain only finite values.")

    valid = (
        (points[:, 0] >= 0.0)
        & (points[:, 0] < float(width))
        & (points[:, 1] >= 0.0)
        & (points[:, 1] < float(height))
    )
    points = points[valid]
    if points.size == 0:
        return 0.0

    col_index = np.minimum((points[:, 0] * columns / width).astype(int), columns - 1)
    row_index = np.minimum((points[:, 1] * rows / height).astype(int), rows - 1)
    occupied = np.unique(row_index * columns + col_index)
    return float(len(occupied) / (rows * columns))


def keypoint_response_summary(result: ORBFeatureResult) -> dict[str, float | None]:
    """Return compact response statistics for one ORB feature result."""
    responses = result.responses
    if responses.size == 0:
        return {
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "mean": float(np.mean(responses)),
        "median": float(np.median(responses)),
        "minimum": float(np.min(responses)),
        "maximum": float(np.max(responses)),
    }


def draw_orb_keypoints(
    image: ArrayLike,
    result: ORBFeatureResult,
    *,
    rich: bool = True,
) -> NDArray[np.uint8]:
    """Return an RGB visualization of detected ORB keypoints."""
    prepared = _to_orb_uint8(image)
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
