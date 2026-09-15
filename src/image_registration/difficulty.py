"""Difficulty-tier sampling for controlled synthetic registration benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .synthetic import GroundTruthTransform, image_center
from .transforms import invert_transform, similarity_matrix


@dataclass(frozen=True)
class DifficultySample:
    """One sampled similarity transform and its benchmark difficulty metadata."""

    tier: str
    ground_truth: GroundTruthTransform
    severity: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "tier": self.tier,
            "ground_truth": self.ground_truth.as_dict(),
            "severity": dict(self.severity),
        }


def _interval(specification: Mapping[str, Any], key: str) -> tuple[float, float]:
    values = np.asarray(specification.get(key), dtype=np.float64)
    if values.shape != (2,):
        raise ValueError(f"Difficulty field '{key}' must contain [minimum, maximum].")
    low, high = float(values[0]), float(values[1])
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError(f"Difficulty field '{key}' must contain finite values.")
    if low < 0.0 or low > high:
        raise ValueError(f"Difficulty field '{key}' must satisfy 0 <= minimum <= maximum.")
    return low, high


def _sample_interval(rng: np.random.Generator, interval: tuple[float, float]) -> float:
    low, high = interval
    if np.isclose(low, high):
        return low
    return float(rng.uniform(low, high))


def _signed_value(rng: np.random.Generator, magnitude: float) -> float:
    if np.isclose(magnitude, 0.0):
        return 0.0
    sign = -1.0 if int(rng.integers(0, 2)) == 0 else 1.0
    return sign * magnitude


def validate_difficulty_tiers(
    tiers: Mapping[str, Mapping[str, Any]],
    *,
    ordered_names: Sequence[str] = ("easy", "moderate", "hard"),
) -> None:
    """Validate required non-overlapping severity intervals from easy to hard."""
    if not isinstance(tiers, Mapping):
        raise ValueError("difficulty_tiers must be a mapping.")

    fields = (
        "translation_abs_px",
        "rotation_abs_degrees",
        "scale_deviation_abs",
        "noise_base_sigma_fraction",
        "noise_signal_sigma_fraction",
    )

    for name in ordered_names:
        if name not in tiers:
            raise ValueError(f"Missing difficulty tier '{name}'.")

    for field in fields:
        intervals = [_interval(tiers[name], field) for name in ordered_names]
        for left, right in zip(intervals, intervals[1:]):
            if not left[1] < right[0]:
                raise ValueError(
                    f"Difficulty intervals for '{field}' must be non-overlapping and increase from easy to hard."
                )


def sample_similarity_difficulty(
    tier: str,
    specification: Mapping[str, Any],
    rng: np.random.Generator,
    image_shape: tuple[int, ...],
) -> DifficultySample:
    """Sample a signed translation, rotation, and scale deviation for one tier."""
    if not isinstance(specification, Mapping):
        raise ValueError("Difficulty tier specification must be a mapping.")

    translation = _sample_interval(rng, _interval(specification, "translation_abs_px"))
    rotation = _sample_interval(rng, _interval(specification, "rotation_abs_degrees"))
    scale_deviation = _sample_interval(rng, _interval(specification, "scale_deviation_abs"))
    noise_base = _sample_interval(rng, _interval(specification, "noise_base_sigma_fraction"))
    noise_signal = _sample_interval(rng, _interval(specification, "noise_signal_sigma_fraction"))

    tx = _signed_value(rng, translation)
    ty = _signed_value(rng, _sample_interval(rng, _interval(specification, "translation_abs_px")))
    angle = _signed_value(rng, rotation)
    scale_sign = -1.0 if int(rng.integers(0, 2)) == 0 else 1.0
    scale = 1.0 + scale_sign * scale_deviation
    if scale <= 0.0:
        raise ValueError("Sampled scale must remain greater than zero.")

    center = image_center(image_shape)
    moving_to_fixed = similarity_matrix(scale, angle, tx=tx, ty=ty, center=center)
    fixed_to_moving = invert_transform(moving_to_fixed)
    parameters = {
        "tx": tx,
        "ty": ty,
        "angle_degrees": angle,
        "scale": scale,
        "center": center.tolist(),
    }
    ground_truth = GroundTruthTransform(
        transform_type="similarity",
        parameters=parameters,
        moving_to_fixed=moving_to_fixed,
        fixed_to_moving=fixed_to_moving,
    )
    severity = {
        "translation_abs_px": translation,
        "rotation_abs_degrees": rotation,
        "scale_deviation_abs": scale_deviation,
        "noise_base_sigma_fraction": noise_base,
        "noise_signal_sigma_fraction": noise_signal,
    }
    return DifficultySample(tier=str(tier), ground_truth=ground_truth, severity=severity)
