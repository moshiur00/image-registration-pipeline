from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

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


def test_save_intensity_histogram_creates_file(tmp_path) -> None:
    from image_registration.visualization import save_intensity_histogram

    fixed = np.arange(100, dtype=np.float32).reshape(10, 10)
    comparison = fixed * 0.8 + 5.0
    mask = np.ones((10, 10), dtype=np.uint8)
    path = save_intensity_histogram(
        fixed,
        comparison,
        tmp_path / "histogram.png",
        mask=mask,
        bins=16,
    )
    assert path.exists()
    assert path.stat().st_size > 0


def test_save_joint_histogram_creates_file(tmp_path) -> None:
    from image_registration.visualization import save_joint_histogram

    fixed = np.arange(100, dtype=np.float32).reshape(10, 10)
    comparison = np.flipud(fixed)
    mask = np.ones((10, 10), dtype=np.uint8)
    path = save_joint_histogram(
        fixed,
        comparison,
        tmp_path / "joint.png",
        mask=mask,
        bins=16,
    )
    assert path.exists()
    assert path.stat().st_size > 0


def test_histogram_helpers_reject_empty_mask(tmp_path) -> None:
    from image_registration.visualization import save_intensity_histogram

    fixed = np.ones((8, 8), dtype=np.float32)
    mask = np.zeros((8, 8), dtype=np.uint8)
    with pytest.raises(ValueError, match="at least one valid pixel"):
        save_intensity_histogram(
            fixed,
            fixed,
            tmp_path / "unused.png",
            mask=mask,
        )
