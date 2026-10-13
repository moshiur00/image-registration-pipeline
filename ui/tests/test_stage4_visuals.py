from __future__ import annotations

import numpy as np

from ui.streamlit.components.visuals import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    edge_overlay,
    to_display_uint8,
)


def _images() -> tuple[np.ndarray, np.ndarray]:
    fixed = np.zeros((64, 80), dtype=np.float32)
    moving = np.zeros((64, 80), dtype=np.float32)
    fixed[12:42, 18:46] = 2.0
    moving[14:44, 20:48] = 2.0
    return fixed, moving


def test_display_conversion_is_uint8_and_preserves_shape() -> None:
    fixed, _ = _images()
    display = to_display_uint8(fixed)
    assert display.dtype == np.uint8
    assert display.shape == fixed.shape
    assert display.max() == 255


def test_visual_diagnostics_have_expected_shapes() -> None:
    fixed, moving = _images()
    assert alpha_overlay(fixed, moving).shape == (64, 80, 3)
    assert checkerboard(fixed, moving).shape == fixed.shape
    assert absolute_difference(fixed, moving).shape == fixed.shape
    assert edge_overlay(fixed, moving).shape == (64, 80, 3)


def test_visual_diagnostics_reject_shape_mismatch() -> None:
    fixed, _ = _images()
    other = np.zeros((32, 32), dtype=np.float32)
    try:
        alpha_overlay(fixed, other)
    except ValueError as exc:
        assert "matching shapes" in str(exc)
    else:
        raise AssertionError("shape mismatch should be rejected")
