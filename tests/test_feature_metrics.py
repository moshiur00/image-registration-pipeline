from __future__ import annotations

import numpy as np
import pytest

from image_registration.feature_metrics import (
    classify_texture,
    gradient_energy,
    keypoint_density_per_megapixel,
    texture_diagnostics,
)
from image_registration.orb import ORBFeatureResult, ORBKeypoint


def _features(count: int, shape: tuple[int, int] = (100, 200)) -> ORBFeatureResult:
    keypoints = tuple(
        ORBKeypoint(
            x=float(i % shape[1]),
            y=float(i % shape[0]),
            size=31.0,
            angle_degrees=0.0,
            response=1.0,
            octave=0,
            class_id=-1,
        )
        for i in range(count)
    )
    descriptors = np.zeros((count, 32), dtype=np.uint8) if count else None
    return ORBFeatureResult(
        keypoints=keypoints,
        descriptors=descriptors,
        success=bool(count),
        runtime_seconds=0.0,
        image_shape=shape,
        failure_reason=None if count else "no_keypoints_detected",
    )


def test_gradient_energy_is_zero_for_constant_image() -> None:
    image = np.full((64, 64), 7.0, dtype=np.float32)
    assert gradient_energy(image) == pytest.approx(0.0)


def test_gradient_energy_increases_for_checkerboard() -> None:
    flat = np.zeros((64, 64), dtype=np.float32)
    yy, xx = np.indices((64, 64))
    checker = ((xx // 4 + yy // 4) % 2).astype(np.float32)
    assert gradient_energy(checker) > gradient_energy(flat)


def test_keypoint_density_uses_image_area() -> None:
    result = _features(20, (100, 200))
    assert keypoint_density_per_megapixel(result, (100, 200)) == pytest.approx(1000.0)


@pytest.mark.parametrize(
    ("energy", "expected"),
    [(0.01, "low"), (0.03, "medium"), (0.09, "high")],
)
def test_classify_texture_thresholds(energy: float, expected: str) -> None:
    assert classify_texture(energy, low_threshold=0.02, high_threshold=0.05) == expected


def test_texture_diagnostics_combines_metrics() -> None:
    yy, xx = np.indices((100, 200))
    image = ((xx // 8 + yy // 8) % 2).astype(np.float32)
    diagnostics = texture_diagnostics(
        image,
        _features(40),
        low_threshold=0.01,
        high_threshold=0.05,
    )
    assert diagnostics.gradient_energy > 0.0
    assert diagnostics.keypoint_density_per_megapixel == pytest.approx(2000.0)
    assert diagnostics.label in {"low", "medium", "high"}


def test_invalid_texture_thresholds_are_rejected() -> None:
    with pytest.raises(ValueError):
        classify_texture(0.1, low_threshold=0.05, high_threshold=0.05)
