"""Valid-overlap and restricted-field-of-view utilities for benchmark pairs."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .warping import warp_mask


def _validate_shape(image_shape: tuple[int, ...]) -> tuple[int, int]:
    if len(image_shape) < 2:
        raise ValueError("image_shape must contain height and width.")
    height, width = int(image_shape[0]), int(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("Image dimensions must be positive.")
    return height, width


def _binary_mask(mask: ArrayLike, *, name: str = "mask") -> NDArray[np.uint8]:
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a 2D mask.")
    if array.size == 0:
        raise ValueError(f"{name} must be non-empty.")
    if not np.all(np.isin(array, [0, 1])):
        raise ValueError(f"{name} must contain only 0 and 1.")
    return array.astype(np.uint8)


def transformed_support_mask(
    source_shape: tuple[int, ...],
    source_to_destination: ArrayLike,
    *,
    destination_shape: tuple[int, int] | None = None,
) -> NDArray[np.uint8]:
    """Return destination pixels that receive valid samples from the source image."""
    height, width = _validate_shape(source_shape)
    output_shape = destination_shape if destination_shape is not None else (height, width)
    source_support = np.ones((height, width), dtype=np.uint8)
    warped = warp_mask(
        source_support,
        source_to_destination,
        output_shape=output_shape,
        border_value=0,
    )
    return (warped > 0).astype(np.uint8)


def rectangular_field_of_view_mask(
    image_shape: tuple[int, ...],
    *,
    width_fraction: float,
    height_fraction: float,
    center_x_fraction: float = 0.5,
    center_y_fraction: float = 0.5,
) -> NDArray[np.uint8]:
    """Create a rectangular restricted field-of-view mask in image coordinates."""
    height, width = _validate_shape(image_shape)
    if not 0.0 < width_fraction <= 1.0:
        raise ValueError("width_fraction must be in the range (0, 1].")
    if not 0.0 < height_fraction <= 1.0:
        raise ValueError("height_fraction must be in the range (0, 1].")
    if not 0.0 <= center_x_fraction <= 1.0:
        raise ValueError("center_x_fraction must be between 0 and 1.")
    if not 0.0 <= center_y_fraction <= 1.0:
        raise ValueError("center_y_fraction must be between 0 and 1.")

    rect_w = min(width, max(1, int(round(width * width_fraction))))
    rect_h = min(height, max(1, int(round(height * height_fraction))))
    center_x = center_x_fraction * (width - 1)
    center_y = center_y_fraction * (height - 1)

    left = int(round(center_x - (rect_w - 1) / 2.0))
    top = int(round(center_y - (rect_h - 1) / 2.0))
    left = min(max(left, 0), width - rect_w)
    top = min(max(top, 0), height - rect_h)
    right = left + rect_w
    bottom = top + rect_h

    mask = np.zeros((height, width), dtype=np.uint8)
    mask[top:bottom, left:right] = 1
    return mask


def combine_valid_masks(*masks: ArrayLike) -> NDArray[np.uint8]:
    """Combine one or more binary masks using logical intersection."""
    if not masks:
        raise ValueError("At least one mask is required.")
    validated = [_binary_mask(mask, name=f"mask[{index}]") for index, mask in enumerate(masks)]
    shape = validated[0].shape
    if any(mask.shape != shape for mask in validated[1:]):
        raise ValueError("All masks must have the same shape.")
    result = np.logical_and.reduce([mask.astype(bool) for mask in validated])
    return result.astype(np.uint8)


def apply_field_of_view(
    image: ArrayLike,
    field_of_view_mask: ArrayLike,
    *,
    fill_value: float = 0.0,
) -> NDArray[np.generic]:
    """Hide pixels outside a binary field-of-view mask without changing image size."""
    array = np.asarray(image)
    if array.ndim not in (2, 3):
        raise ValueError("Image must have shape (H, W) or (H, W, C).")
    mask = _binary_mask(field_of_view_mask, name="field_of_view_mask")
    if array.shape[:2] != mask.shape:
        raise ValueError("Image and field_of_view_mask must have the same height and width.")

    result = array.copy()
    if array.ndim == 2:
        result[mask == 0] = fill_value
    else:
        result[mask == 0, :] = fill_value
    return result


def overlap_mask_in_fixed_space(
    moving_valid_mask: ArrayLike,
    moving_to_fixed: ArrayLike,
    *,
    fixed_shape: tuple[int, int],
) -> NDArray[np.uint8]:
    """Map valid moving-image support into the fixed-image coordinate system."""
    moving_mask = _binary_mask(moving_valid_mask, name="moving_valid_mask")
    fixed_mask = warp_mask(
        moving_mask,
        moving_to_fixed,
        output_shape=fixed_shape,
        border_value=0,
    )
    return (fixed_mask > 0).astype(np.uint8)


def overlap_fraction(mask: ArrayLike) -> float:
    """Return the fraction of pixels marked as valid overlap."""
    binary = _binary_mask(mask)
    return float(np.mean(binary, dtype=np.float64))
