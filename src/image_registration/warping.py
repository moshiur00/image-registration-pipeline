"""Image resampling utilities for known 2D geometric transforms."""

from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

from .transforms import _validate_transform

InterpolationName = Literal["nearest", "linear", "cubic"]

_INTERPOLATION_FLAGS: dict[str, int] = {
    "nearest": cv2.INTER_NEAREST,
    "linear": cv2.INTER_LINEAR,
    "cubic": cv2.INTER_CUBIC,
}


def _validate_image(image: ArrayLike) -> NDArray[np.generic]:
    array = np.asarray(image)
    if array.ndim not in (2, 3):
        raise ValueError("Image must have shape (H, W) or (H, W, C).")
    if array.shape[0] <= 0 or array.shape[1] <= 0:
        raise ValueError("Image dimensions must be positive.")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("Image dtype must be numeric.")
    return array


def _validate_output_shape(output_shape: tuple[int, int] | None, image: NDArray) -> tuple[int, int]:
    if output_shape is None:
        return int(image.shape[0]), int(image.shape[1])

    if len(output_shape) != 2:
        raise ValueError("output_shape must be (height, width).")

    height, width = output_shape
    if not isinstance(height, (int, np.integer)) or not isinstance(width, (int, np.integer)):
        raise ValueError("output_shape values must be integers.")
    if height <= 0 or width <= 0:
        raise ValueError("output_shape values must be positive.")
    return int(height), int(width)


def warp_image(
    image: ArrayLike,
    transform_source_to_destination: ArrayLike,
    output_shape: tuple[int, int] | None = None,
    interpolation: InterpolationName = "linear",
    border_value: float | tuple[float, ...] = 0.0,
) -> NDArray[np.generic]:
    """Resample an image using a forward geometric transform.

    ``transform_source_to_destination`` maps source image coordinates into the
    destination coordinate system. OpenCV performs the required inverse lookup
    internally when ``WARP_INVERSE_MAP`` is not supplied.

    Parameters
    ----------
    image:
        Source image with shape ``(H, W)`` or ``(H, W, C)``.
    transform_source_to_destination:
        3x3 affine-form homogeneous matrix mapping source points to destination
        points.
    output_shape:
        Destination ``(height, width)``. If omitted, the source size is used.
    interpolation:
        One of ``nearest``, ``linear``, or ``cubic``.
    border_value:
        Constant value used when inverse-mapped samples fall outside the source.
    """
    source = _validate_image(image)
    matrix = _validate_transform(transform_source_to_destination)
    height, width = _validate_output_shape(output_shape, source)

    if interpolation not in _INTERPOLATION_FLAGS:
        allowed = ", ".join(sorted(_INTERPOLATION_FLAGS))
        raise ValueError(f"Unsupported interpolation '{interpolation}'. Use one of: {allowed}.")

    affine_2x3 = matrix[:2, :]
    result = cv2.warpAffine(
        source,
        affine_2x3,
        dsize=(width, height),
        flags=_INTERPOLATION_FLAGS[interpolation],
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    return result


def warp_mask(
    mask: ArrayLike,
    transform_source_to_destination: ArrayLike,
    output_shape: tuple[int, int] | None = None,
    border_value: int = 0,
) -> NDArray[np.generic]:
    """Warp a discrete label mask using nearest-neighbor interpolation only."""
    array = _validate_image(mask)
    if array.ndim != 2:
        raise ValueError("Mask must be a 2D label image.")

    return warp_image(
        array,
        transform_source_to_destination,
        output_shape=output_shape,
        interpolation="nearest",
        border_value=float(border_value),
    )
