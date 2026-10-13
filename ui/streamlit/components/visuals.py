"""Pure image visualization helpers for the research workbench."""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.generic]


def to_display_uint8(image: Array) -> NDArray[np.uint8]:
    """Convert numeric image data into a robust 8-bit display representation."""
    values = np.asarray(image)
    if values.ndim == 3 and values.shape[2] in {3, 4}:
        if values.dtype == np.uint8:
            return values[..., :3].copy()
        values = values[..., :3].astype(np.float32)
        low = np.nanpercentile(values, 1.0)
        high = np.nanpercentile(values, 99.0)
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            low = float(np.nanmin(values))
            high = float(np.nanmax(values))
        if high <= low:
            return np.zeros(values.shape, dtype=np.uint8)
        scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
        return np.rint(scaled * 255.0).astype(np.uint8)

    if values.ndim == 3:
        values = values[..., 0]
    values = values.astype(np.float32)
    low = float(np.nanpercentile(values, 1.0))
    high = float(np.nanpercentile(values, 99.0))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(np.nanmin(values))
        high = float(np.nanmax(values))
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    return np.rint(scaled * 255.0).astype(np.uint8)


def ensure_gray_uint8(image: Array) -> NDArray[np.uint8]:
    display = to_display_uint8(image)
    if display.ndim == 2:
        return display
    return cv2.cvtColor(display, cv2.COLOR_RGB2GRAY)


def estimated_valid_warp_mask(registered: Array) -> NDArray[np.bool_]:
    """Estimate display-only valid overlap by masking zero regions connected to the border.

    Registration warps in this project use zero-valued fill outside the source field of
    view. The mask is used only for visualization and never for evaluation metrics.
    """
    values = np.asarray(registered)
    if values.ndim == 3:
        zero = np.all(np.isclose(values, 0.0, atol=1e-8), axis=2)
    else:
        zero = np.isclose(values, 0.0, atol=1e-8)
    zero_u8 = zero.astype(np.uint8)
    if not np.any(zero_u8):
        return np.ones(zero.shape, dtype=bool)

    count, labels = cv2.connectedComponents(zero_u8, connectivity=8)
    invalid = np.zeros(zero.shape, dtype=bool)
    border_labels = set(np.unique(labels[0, :]))
    border_labels.update(np.unique(labels[-1, :]))
    border_labels.update(np.unique(labels[:, 0]))
    border_labels.update(np.unique(labels[:, -1]))
    border_labels.discard(0)
    for label in border_labels:
        if 0 < int(label) < count:
            invalid |= labels == int(label)
    return ~invalid


def _neutralize_invalid(image: NDArray[np.uint8], valid_mask: NDArray[np.bool_]) -> NDArray[np.uint8]:
    """Show estimated out-of-FOV regions in neutral gray for visual diagnostics."""
    output = image.copy()
    if output.ndim == 2:
        output[~valid_mask] = 96
    else:
        output[~valid_mask, :] = 96
    return output


def alpha_overlay(fixed: Array, registered: Array, alpha: float = 0.5) -> NDArray[np.uint8]:
    fixed_u8 = ensure_gray_uint8(fixed)
    registered_u8 = ensure_gray_uint8(registered)
    if fixed_u8.shape != registered_u8.shape:
        raise ValueError("Overlay images must have matching shapes.")
    fixed_rgb = cv2.cvtColor(fixed_u8, cv2.COLOR_GRAY2RGB)
    registered_rgb = cv2.cvtColor(registered_u8, cv2.COLOR_GRAY2RGB)
    output = cv2.addWeighted(fixed_rgb, float(alpha), registered_rgb, 1.0 - float(alpha), 0.0)
    return _neutralize_invalid(output, estimated_valid_warp_mask(registered))


def checkerboard(fixed: Array, registered: Array, tile_size: int = 32) -> NDArray[np.uint8]:
    fixed_u8 = ensure_gray_uint8(fixed)
    registered_u8 = ensure_gray_uint8(registered)
    if fixed_u8.shape != registered_u8.shape:
        raise ValueError("Checkerboard images must have matching shapes.")
    yy, xx = np.indices(fixed_u8.shape)
    mask = ((yy // int(tile_size)) + (xx // int(tile_size))) % 2 == 0
    output = registered_u8.copy()
    output[mask] = fixed_u8[mask]
    return _neutralize_invalid(output, estimated_valid_warp_mask(registered))


def absolute_difference(fixed: Array, registered: Array) -> NDArray[np.uint8]:
    """Return a contrast-normalized absolute difference for display only."""
    fixed_u8 = ensure_gray_uint8(fixed)
    registered_u8 = ensure_gray_uint8(registered)
    if fixed_u8.shape != registered_u8.shape:
        raise ValueError("Difference images must have matching shapes.")
    difference = cv2.absdiff(fixed_u8, registered_u8).astype(np.float32)
    valid = estimated_valid_warp_mask(registered)
    valid_values = difference[valid]
    positive = valid_values[valid_values > 0.0]
    if positive.size:
        high = float(np.percentile(positive, 99.0))
        if high <= 0.0:
            high = float(np.max(positive))
        if high > 0.0:
            difference = np.clip(difference / high, 0.0, 1.0) * 255.0
    output = np.rint(difference).astype(np.uint8)
    output[~valid] = 96
    return output


def edge_overlay(fixed: Array, registered: Array) -> NDArray[np.uint8]:
    fixed_u8 = ensure_gray_uint8(fixed)
    registered_u8 = ensure_gray_uint8(registered)
    if fixed_u8.shape != registered_u8.shape:
        raise ValueError("Edge overlay images must have matching shapes.")
    fixed_edges = cv2.Canny(fixed_u8, 70, 150)
    registered_edges = cv2.Canny(registered_u8, 70, 150)
    canvas = np.zeros((*fixed_u8.shape, 3), dtype=np.uint8)
    canvas[..., 0] = fixed_edges
    canvas[..., 1] = registered_edges
    canvas[..., 2] = np.minimum(fixed_edges, registered_edges)
    return _neutralize_invalid(canvas, estimated_valid_warp_mask(registered))
