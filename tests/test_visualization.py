from __future__ import annotations

from pathlib import Path

import numpy as np

from image_registration.visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
)


def test_alpha_overlay_preserves_shape() -> None:
    fixed = np.zeros((10, 12), dtype=np.float32)
    moving = np.ones((10, 12), dtype=np.float32)
    overlay = alpha_overlay(fixed, moving, alpha=0.25)
    assert overlay.shape == fixed.shape
    assert overlay.dtype == np.float32


def test_absolute_difference_identical_is_zero() -> None:
    image = np.arange(100, dtype=np.float32).reshape(10, 10)
    diff = absolute_difference(image, image)
    assert np.allclose(diff, 0.0)


def test_checkerboard_uses_both_images() -> None:
    fixed = np.zeros((8, 8), dtype=np.float32)
    moving = np.indices((8, 8))[1].astype(np.float32)
    board = checkerboard(fixed, moving, tile_size=2)
    assert board.shape == fixed.shape
    assert np.any(board == 0.0)
    assert np.any(board > 0.0)


def test_save_comparison_figure_creates_file(tmp_path: Path) -> None:
    fixed = np.zeros((12, 12), dtype=np.float32)
    moving = fixed.copy()
    moving[3:6, 3:6] = 1.0
    path = save_comparison_figure(fixed, moving, fixed, tmp_path / "comparison.png")
    assert path.exists()
    assert path.stat().st_size > 0
