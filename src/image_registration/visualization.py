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



def edge_overlay(
    fixed: ArrayLike,
    comparison: ArrayLike,
    *,
    low_threshold: float = 50.0,
    high_threshold: float = 150.0,
) -> NDArray[np.float32]:
    """Create an RGB edge overlay for alignment inspection.

    Fixed-image edges are shown in the first channel, comparison-image edges in
    the second channel, and coincident edges therefore appear in both channels.
    """
    if low_threshold < 0.0 or high_threshold <= low_threshold:
        raise ValueError("Canny thresholds must satisfy 0 <= low < high.")
    a = _normalize_display(fixed)
    b = _normalize_display(comparison)
    if a.shape != b.shape:
        raise ValueError("Edge-overlay images must have the same shape.")

    import cv2

    a_u8 = np.clip(a * 255.0, 0.0, 255.0).astype(np.uint8)
    b_u8 = np.clip(b * 255.0, 0.0, 255.0).astype(np.uint8)
    edge_a = cv2.Canny(a_u8, int(round(low_threshold)), int(round(high_threshold))) > 0
    edge_b = cv2.Canny(b_u8, int(round(low_threshold)), int(round(high_threshold))) > 0

    overlay = np.zeros((*a.shape, 3), dtype=np.float32)
    overlay[..., 0] = edge_a.astype(np.float32)
    overlay[..., 1] = edge_b.astype(np.float32)
    return overlay


def save_rgb_image(output_path: str | Path, image: ArrayLike) -> Path:
    """Save a normalized RGB image without requiring an interactive backend."""
    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 3 or array.shape[2] != 3 or array.size == 0:
        raise ValueError("RGB image must have shape (H, W, 3).")
    if not np.all(np.isfinite(array)):
        raise ValueError("RGB image must contain only finite values.")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    imsave(path, np.clip(array, 0.0, 1.0))
    return path

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


def save_intensity_histogram(
    fixed: ArrayLike,
    comparison: ArrayLike,
    output_path: str | Path,
    *,
    mask: ArrayLike | None = None,
    bins: int = 64,
    title: str = "Intensity histograms",
) -> Path:
    """Save fixed and comparison intensity histograms within an optional mask."""
    if bins <= 1:
        raise ValueError("bins must be greater than 1.")
    fixed_array = _as_grayscale_float(fixed)
    comparison_array = _as_grayscale_float(comparison)
    if fixed_array.shape != comparison_array.shape:
        raise ValueError("Histogram images must have the same shape.")

    if mask is None:
        selector = np.ones(fixed_array.shape, dtype=bool)
    else:
        mask_array = np.asarray(mask)
        if mask_array.shape != fixed_array.shape:
            raise ValueError("Histogram mask must match the image shape.")
        selector = mask_array.astype(bool)
    if not np.any(selector):
        raise ValueError("Histogram mask must contain at least one valid pixel.")

    fixed_values = fixed_array[selector]
    comparison_values = comparison_array[selector]
    combined_low = float(min(np.min(fixed_values), np.min(comparison_values)))
    combined_high = float(max(np.max(fixed_values), np.max(comparison_values)))
    if np.isclose(combined_low, combined_high):
        combined_high = combined_low + 1.0

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(7, 4.5))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    axis.hist(
        fixed_values,
        bins=bins,
        range=(combined_low, combined_high),
        histtype="step",
        linewidth=1.6,
        label="Fixed",
    )
    axis.hist(
        comparison_values,
        bins=bins,
        range=(combined_low, combined_high),
        histtype="step",
        linewidth=1.6,
        label="Comparison",
    )
    axis.set_title(title)
    axis.set_xlabel("Intensity")
    axis.set_ylabel("Pixel count")
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    fig.clear()
    return path


def save_joint_histogram(
    fixed: ArrayLike,
    comparison: ArrayLike,
    output_path: str | Path,
    *,
    mask: ArrayLike | None = None,
    bins: int = 64,
    title: str = "Joint intensity histogram",
) -> Path:
    """Save a joint histogram for corresponding fixed and comparison pixels."""
    if bins <= 1:
        raise ValueError("bins must be greater than 1.")
    fixed_array = _as_grayscale_float(fixed)
    comparison_array = _as_grayscale_float(comparison)
    if fixed_array.shape != comparison_array.shape:
        raise ValueError("Joint-histogram images must have the same shape.")

    if mask is None:
        selector = np.ones(fixed_array.shape, dtype=bool)
    else:
        mask_array = np.asarray(mask)
        if mask_array.shape != fixed_array.shape:
            raise ValueError("Joint-histogram mask must match the image shape.")
        selector = mask_array.astype(bool)
    if not np.any(selector):
        raise ValueError("Joint-histogram mask must contain at least one valid pixel.")

    fixed_values = fixed_array[selector]
    comparison_values = comparison_array[selector]

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(5.5, 5.0))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    histogram = axis.hist2d(fixed_values, comparison_values, bins=bins)
    axis.set_title(title)
    axis.set_xlabel("Fixed intensity")
    axis.set_ylabel("Comparison intensity")
    fig.colorbar(histogram[3], ax=axis, label="Pixel count")
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    fig.clear()
    return path
