"""ORB descriptor matching and correspondence diagnostics.

Day 17 keeps descriptor matching separate from robust transform estimation.
The module establishes candidate correspondences, applies configurable filters,
and records enough diagnostics to explain why a later geometric estimator has
strong or weak input data.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .orb import ORBFeatureResult, keypoint_grid_coverage

MatchStrategy = Literal["knn_ratio", "cross_check"]
HammingNorm = Literal["hamming", "hamming2"]


@dataclass(frozen=True)
class FeatureMatch:
    """One correspondence from a moving-image keypoint to a fixed-image keypoint."""

    moving_index: int
    fixed_index: int
    distance: float
    second_distance: float | None = None
    ratio: float | None = None


@dataclass(frozen=True)
class FeatureMatchResult:
    """Descriptor matching result with safe failure information."""

    strategy: MatchStrategy
    tentative_matches: tuple[FeatureMatch, ...]
    accepted_matches: tuple[FeatureMatch, ...]
    success: bool
    runtime_seconds: float
    failure_reason: str | None = None
    ratio_threshold: float | None = None
    maximum_distance: float | None = None
    minimum_matches: int = 4

    @property
    def tentative_count(self) -> int:
        return len(self.tentative_matches)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_matches)

    @property
    def rejected_count(self) -> int:
        return max(0, self.tentative_count - self.accepted_count)

    @property
    def acceptance_rate(self) -> float | None:
        if self.tentative_count == 0:
            return None
        return float(self.accepted_count / self.tentative_count)


@dataclass(frozen=True)
class CorrespondenceCoverage:
    """Spatial coverage of accepted correspondences in both images."""

    fixed_coverage: float
    moving_coverage: float
    minimum_coverage: float


def _norm_flag(norm: HammingNorm) -> int:
    if norm == "hamming":
        return cv2.NORM_HAMMING
    if norm == "hamming2":
        return cv2.NORM_HAMMING2
    raise ValueError("norm must be hamming or hamming2.")


def _validate_matching_inputs(
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    *,
    minimum_matches: int,
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]] | str:
    if minimum_matches <= 0:
        raise ValueError("minimum_matches must be greater than zero.")
    if not fixed.success or fixed.descriptors is None:
        return "fixed_descriptors_unavailable"
    if not moving.success or moving.descriptors is None:
        return "moving_descriptors_unavailable"

    fixed_descriptors = np.asarray(fixed.descriptors)
    moving_descriptors = np.asarray(moving.descriptors)
    if fixed_descriptors.dtype != np.uint8 or moving_descriptors.dtype != np.uint8:
        raise ValueError("ORB descriptors must use uint8 binary storage.")
    if fixed_descriptors.ndim != 2 or moving_descriptors.ndim != 2:
        raise ValueError("Descriptor arrays must have shape (N, D).")
    if fixed_descriptors.shape[1] != moving_descriptors.shape[1]:
        raise ValueError("Fixed and moving descriptors must have the same descriptor length.")
    if fixed_descriptors.shape[0] != fixed.keypoint_count:
        raise ValueError("Fixed keypoint and descriptor counts are inconsistent.")
    if moving_descriptors.shape[0] != moving.keypoint_count:
        raise ValueError("Moving keypoint and descriptor counts are inconsistent.")
    return (
        np.ascontiguousarray(fixed_descriptors),
        np.ascontiguousarray(moving_descriptors),
    )


def match_orb_knn_ratio(
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    *,
    ratio_threshold: float = 0.75,
    maximum_distance: float | None = None,
    minimum_matches: int = 4,
    norm: HammingNorm = "hamming",
) -> FeatureMatchResult:
    """Match ORB descriptors with 2-nearest-neighbor ratio filtering.

    Moving descriptors are queries and fixed descriptors are the reference set,
    matching the project Moving -> Fixed convention.
    """
    if not 0.0 < ratio_threshold < 1.0:
        raise ValueError("ratio_threshold must be in the range (0, 1).")
    if maximum_distance is not None and (
        not np.isfinite(maximum_distance) or maximum_distance < 0.0
    ):
        raise ValueError("maximum_distance must be finite and non-negative when provided.")

    validated = _validate_matching_inputs(fixed, moving, minimum_matches=minimum_matches)
    if isinstance(validated, str):
        return FeatureMatchResult(
            strategy="knn_ratio",
            tentative_matches=(),
            accepted_matches=(),
            success=False,
            runtime_seconds=0.0,
            failure_reason=validated,
            ratio_threshold=float(ratio_threshold),
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )
    fixed_descriptors, moving_descriptors = validated
    if fixed_descriptors.shape[0] < 2:
        return FeatureMatchResult(
            strategy="knn_ratio",
            tentative_matches=(),
            accepted_matches=(),
            success=False,
            runtime_seconds=0.0,
            failure_reason="insufficient_fixed_descriptors_for_knn",
            ratio_threshold=float(ratio_threshold),
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )

    matcher = cv2.BFMatcher(_norm_flag(norm), crossCheck=False)
    start = perf_counter()
    try:
        groups = matcher.knnMatch(moving_descriptors, fixed_descriptors, k=2)
    except cv2.error as exc:
        return FeatureMatchResult(
            strategy="knn_ratio",
            tentative_matches=(),
            accepted_matches=(),
            success=False,
            runtime_seconds=perf_counter() - start,
            failure_reason=f"opencv_error: {exc}",
            ratio_threshold=float(ratio_threshold),
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )
    runtime = perf_counter() - start

    tentative: list[FeatureMatch] = []
    accepted: list[FeatureMatch] = []
    for group in groups:
        if not group:
            continue
        best = group[0]
        second_distance: float | None = None
        ratio: float | None = None
        if len(group) >= 2:
            second_distance = float(group[1].distance)
            if second_distance > 0.0:
                ratio = float(best.distance / second_distance)

        item = FeatureMatch(
            moving_index=int(best.queryIdx),
            fixed_index=int(best.trainIdx),
            distance=float(best.distance),
            second_distance=second_distance,
            ratio=ratio,
        )
        tentative.append(item)

        ratio_pass = ratio is not None and ratio < ratio_threshold
        distance_pass = maximum_distance is None or item.distance <= maximum_distance
        if ratio_pass and distance_pass:
            accepted.append(item)

    accepted.sort(key=lambda match: (match.distance, match.moving_index, match.fixed_index))
    success = len(accepted) >= minimum_matches
    failure_reason = None if success else "insufficient_filtered_matches"
    return FeatureMatchResult(
        strategy="knn_ratio",
        tentative_matches=tuple(tentative),
        accepted_matches=tuple(accepted),
        success=success,
        runtime_seconds=runtime,
        failure_reason=failure_reason,
        ratio_threshold=float(ratio_threshold),
        maximum_distance=maximum_distance,
        minimum_matches=minimum_matches,
    )


def match_orb_cross_check(
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    *,
    maximum_distance: float | None = None,
    minimum_matches: int = 4,
    norm: HammingNorm = "hamming",
) -> FeatureMatchResult:
    """Match ORB descriptors with mutual nearest-neighbor cross-checking."""
    if maximum_distance is not None and (
        not np.isfinite(maximum_distance) or maximum_distance < 0.0
    ):
        raise ValueError("maximum_distance must be finite and non-negative when provided.")

    validated = _validate_matching_inputs(fixed, moving, minimum_matches=minimum_matches)
    if isinstance(validated, str):
        return FeatureMatchResult(
            strategy="cross_check",
            tentative_matches=(),
            accepted_matches=(),
            success=False,
            runtime_seconds=0.0,
            failure_reason=validated,
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )
    fixed_descriptors, moving_descriptors = validated

    matcher = cv2.BFMatcher(_norm_flag(norm), crossCheck=True)
    start = perf_counter()
    try:
        raw_matches = matcher.match(moving_descriptors, fixed_descriptors)
    except cv2.error as exc:
        return FeatureMatchResult(
            strategy="cross_check",
            tentative_matches=(),
            accepted_matches=(),
            success=False,
            runtime_seconds=perf_counter() - start,
            failure_reason=f"opencv_error: {exc}",
            maximum_distance=maximum_distance,
            minimum_matches=minimum_matches,
        )
    runtime = perf_counter() - start

    tentative = [
        FeatureMatch(
            moving_index=int(match.queryIdx),
            fixed_index=int(match.trainIdx),
            distance=float(match.distance),
        )
        for match in raw_matches
    ]
    accepted = [
        match
        for match in tentative
        if maximum_distance is None or match.distance <= maximum_distance
    ]
    tentative.sort(key=lambda match: (match.distance, match.moving_index, match.fixed_index))
    accepted.sort(key=lambda match: (match.distance, match.moving_index, match.fixed_index))
    success = len(accepted) >= minimum_matches
    failure_reason = None if success else "insufficient_cross_checked_matches"
    return FeatureMatchResult(
        strategy="cross_check",
        tentative_matches=tuple(tentative),
        accepted_matches=tuple(accepted),
        success=success,
        runtime_seconds=runtime,
        failure_reason=failure_reason,
        maximum_distance=maximum_distance,
        minimum_matches=minimum_matches,
    )


def match_distance_summary(matches: tuple[FeatureMatch, ...]) -> dict[str, float | None]:
    """Return compact Hamming-distance statistics for a match collection."""
    if not matches:
        return {
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "q25": None,
            "q75": None,
        }
    values = np.asarray([match.distance for match in matches], dtype=np.float64)
    return {
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "q25": float(np.quantile(values, 0.25)),
        "q75": float(np.quantile(values, 0.75)),
    }


def correspondence_points(
    result: FeatureMatchResult,
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    *,
    accepted_only: bool = True,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return fixed and moving point arrays for a match result."""
    matches = result.accepted_matches if accepted_only else result.tentative_matches
    if not matches:
        empty = np.empty((0, 2), dtype=np.float64)
        return empty.copy(), empty.copy()

    fixed_points_all = fixed.points_xy
    moving_points_all = moving.points_xy
    fixed_points = np.asarray(
        [fixed_points_all[match.fixed_index] for match in matches], dtype=np.float64
    )
    moving_points = np.asarray(
        [moving_points_all[match.moving_index] for match in matches], dtype=np.float64
    )
    return fixed_points, moving_points


def correspondence_grid_coverage(
    result: FeatureMatchResult,
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    *,
    rows: int = 4,
    columns: int = 4,
) -> CorrespondenceCoverage:
    """Measure grid coverage of accepted match endpoints in both images."""
    fixed_points, moving_points = correspondence_points(result, fixed, moving)
    fixed_coverage = keypoint_grid_coverage(
        fixed_points, fixed.image_shape, rows=rows, columns=columns
    )
    moving_coverage = keypoint_grid_coverage(
        moving_points, moving.image_shape, rows=rows, columns=columns
    )
    return CorrespondenceCoverage(
        fixed_coverage=fixed_coverage,
        moving_coverage=moving_coverage,
        minimum_coverage=float(min(fixed_coverage, moving_coverage)),
    )


def _draw_uint8(image: ArrayLike) -> NDArray[np.uint8]:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("Match visualization expects 2D grayscale images.")
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)
    work = array.astype(np.float64, copy=False)
    if not np.all(np.isfinite(work)):
        raise ValueError("Match visualization input must contain finite values.")
    minimum = float(np.min(work))
    maximum = float(np.max(work))
    if np.isclose(maximum, minimum):
        return np.zeros(array.shape, dtype=np.uint8)
    normalized = (work - minimum) / (maximum - minimum)
    return np.ascontiguousarray(np.clip(np.rint(normalized * 255.0), 0, 255).astype(np.uint8))


def _cv_keypoints(result: ORBFeatureResult) -> list[cv2.KeyPoint]:
    return [
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


def draw_feature_matches(
    fixed_image: ArrayLike,
    moving_image: ArrayLike,
    fixed: ORBFeatureResult,
    moving: ORBFeatureResult,
    matches: tuple[FeatureMatch, ...],
    *,
    maximum_drawn: int = 80,
) -> NDArray[np.uint8]:
    """Return an RGB side-by-side visualization of descriptor correspondences."""
    if maximum_drawn <= 0:
        raise ValueError("maximum_drawn must be greater than zero.")
    selected = sorted(matches, key=lambda item: item.distance)[:maximum_drawn]
    cv_matches = [
        cv2.DMatch(
            _queryIdx=int(match.moving_index),
            _trainIdx=int(match.fixed_index),
            _imgIdx=0,
            _distance=float(match.distance),
        )
        for match in selected
    ]
    rendered = cv2.drawMatches(
        _draw_uint8(moving_image),
        _cv_keypoints(moving),
        _draw_uint8(fixed_image),
        _cv_keypoints(fixed),
        cv_matches,
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    return cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
