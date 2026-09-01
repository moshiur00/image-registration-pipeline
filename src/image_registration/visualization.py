"""Reusable visualization helpers for image-registration experiments."""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.image import imsave
import numpy as np
from numpy.typing import ArrayLike, NDArray


def _as_grayscale_float(image: ArrayLike) -> NDArray[np.float32]:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("Visualization helper expects a 2D grayscale image.")
    if array.size == 0:
        raise ValueError("Image must be non-empty.")
    return array.astype(np.float32)


def _normalize_display(image: ArrayLike) -> NDArray[np.float32]:
    array = _as_grayscale_float(image)
    lo = float(np.min(array))
    hi = float(np.max(array))
    if np.isclose(hi, lo):
        return np.zeros_like(array, dtype=np.float32)
    return ((array - lo) / (hi - lo)).astype(np.float32)


def alpha_overlay(fixed: ArrayLike, moving: ArrayLike, alpha: float = 0.5) -> NDArray[np.float32]:
    """Create a grayscale alpha blend for quick alignment inspection."""
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("alpha must be between 0 and 1.")
    a = _normalize_display(fixed)
    b = _normalize_display(moving)
    if a.shape != b.shape:
        raise ValueError("Overlay images must have the same shape.")
    return ((1.0 - alpha) * a + alpha * b).astype(np.float32)


def absolute_difference(fixed: ArrayLike, moving: ArrayLike, normalize: bool = True) -> NDArray[np.float32]:
    """Create an absolute-difference image."""
    a = _as_grayscale_float(fixed)
    b = _as_grayscale_float(moving)
    if a.shape != b.shape:
        raise ValueError("Difference images must have the same shape.")
    diff = np.abs(a - b).astype(np.float32)
    return _normalize_display(diff) if normalize else diff


def checkerboard(fixed: ArrayLike, moving: ArrayLike, tile_size: int = 32) -> NDArray[np.float32]:
    """Create a checkerboard alternating between fixed and moving images."""
    if tile_size <= 0:
        raise ValueError("tile_size must be positive.")
    a = _normalize_display(fixed)
    b = _normalize_display(moving)
    if a.shape != b.shape:
        raise ValueError("Checkerboard images must have the same shape.")

    yy, xx = np.indices(a.shape)
    selector = ((yy // tile_size) + (xx // tile_size)) % 2 == 0
    return np.where(selector, a, b).astype(np.float32)


def save_grayscale_image(
    output_path: str | Path,
    image: ArrayLike,
    *,
    normalize: bool = True,
) -> Path:
    """Save a 2D image as an 8-bit grayscale PNG-compatible raster."""
    array = _as_grayscale_float(image)
    display = _normalize_display(array) if normalize else array
    if normalize:
        encoded = np.clip(display * 255.0, 0.0, 255.0).astype(np.uint8)
    else:
        encoded = np.clip(display, 0.0, 255.0).astype(np.uint8)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    imsave(path, encoded, cmap="gray", vmin=0, vmax=255)
    return path


def save_comparison_figure(
    fixed: ArrayLike,
    moving: ArrayLike,
    registered: ArrayLike,
    output_path: str | Path,
    *,
    title: str = "Registration comparison",
) -> Path:
    """Save a compact fixed, moving, registered, and difference figure."""
    fixed_array = _as_grayscale_float(fixed)
    moving_array = _as_grayscale_float(moving)
    registered_array = _as_grayscale_float(registered)
    if fixed_array.shape != moving_array.shape or fixed_array.shape != registered_array.shape:
        raise ValueError("All comparison images must have the same shape.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Use the Agg canvas directly so batch runs do not require a GUI or Tkinter.
    fig = Figure(figsize=(9, 7))
    FigureCanvasAgg(fig)
    axes = fig.subplots(2, 2)
    fig.suptitle(title)
    panels = [
        (fixed_array, "Fixed"),
        (moving_array, "Moving"),
        (registered_array, "Registered"),
        (absolute_difference(fixed_array, registered_array), "Absolute difference"),
    ]
    for axis, (image, panel_title) in zip(axes.flat, panels, strict=True):
        axis.imshow(image, cmap="gray")
        axis.set_title(panel_title)
        axis.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    fig.clear()
    return path
