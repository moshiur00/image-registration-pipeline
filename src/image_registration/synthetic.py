"""Synthetic image-pair generation with explicit ground-truth geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .transforms import (
    affine_matrix,
    apply_transform,
    invert_transform,
    rigid_matrix,
    rotation_matrix,
    similarity_matrix,
    translation_matrix,
)
from .warping import InterpolationName, warp_image

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class GroundTruthTransform:
    """A sampled transform stored in both project directions."""

    transform_type: str
    parameters: dict[str, Any]
    moving_to_fixed: FloatArray
    fixed_to_moving: FloatArray

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the ground truth."""
        return {
            "transform_type": self.transform_type,
            "parameters": self.parameters,
            "moving_to_fixed": self.moving_to_fixed.tolist(),
            "fixed_to_moving": self.fixed_to_moving.tolist(),
        }


@dataclass(frozen=True)
class SyntheticPair:
    """Fixed and moving images plus exact geometric correspondence."""

    fixed: NDArray[np.generic]
    moving: NDArray[np.generic]
    ground_truth: GroundTruthTransform
    control_points_moving: FloatArray
    control_points_fixed: FloatArray


def _validate_image_shape(image_shape: tuple[int, ...]) -> tuple[int, int]:
    if len(image_shape) < 2:
        raise ValueError("image_shape must contain at least height and width.")
    height = int(image_shape[0])
    width = int(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("Image dimensions must be positive.")
    return height, width


def image_center(image_shape: tuple[int, ...]) -> FloatArray:
    """Return the geometric center of an image in project x,y coordinates."""
    height, width = _validate_image_shape(image_shape)
    return np.array([(width - 1) / 2.0, (height - 1) / 2.0], dtype=np.float64)


def _sample_range(
    rng: np.random.Generator,
    ranges: Mapping[str, Any],
    name: str,
    default: tuple[float, float],
) -> float:
    value = ranges.get(name, default)
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (2,):
        raise ValueError(f"Range '{name}' must contain [minimum, maximum].")
    low, high = float(array[0]), float(array[1])
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError(f"Range '{name}' must contain finite values.")
    if low > high:
        raise ValueError(f"Range '{name}' minimum must not exceed maximum.")
    if np.isclose(low, high):
        return low
    return float(rng.uniform(low, high))


def _affine_linear_matrix(
    angle_degrees: float,
    scale_x: float,
    scale_y: float,
    shear_x: float,
) -> FloatArray:
    """Build a non-singular affine linear block from interpretable parameters."""
    if scale_x <= 0.0 or scale_y <= 0.0:
        raise ValueError("Affine scales must be greater than zero.")
    rotation = rotation_matrix(angle_degrees)[:2, :2]
    scale = np.array([[scale_x, 0.0], [0.0, scale_y]], dtype=np.float64)
    shear = np.array([[1.0, shear_x], [0.0, 1.0]], dtype=np.float64)
    return rotation @ shear @ scale


def sample_ground_truth_transform(
    transform_type: str,
    rng: np.random.Generator,
    image_shape: tuple[int, ...],
    ranges: Mapping[str, Any] | None = None,
) -> GroundTruthTransform:
    """Sample one Moving -> Fixed transform from configured parameter ranges.

    Supported transform families are translation, rigid, similarity, and affine.
    The image center is used as the rotation and scaling center for all centered
    models so the sampled parameters remain easy to interpret.
    """
    ranges = {} if ranges is None else ranges
    if not isinstance(ranges, Mapping):
        raise ValueError("ranges must be a mapping.")

    name = str(transform_type).strip().lower()
    center = image_center(image_shape)
    tx = _sample_range(rng, ranges, "tx", (0.0, 0.0))
    ty = _sample_range(rng, ranges, "ty", (0.0, 0.0))

    parameters: dict[str, Any] = {"tx": tx, "ty": ty}

    if name == "translation":
        matrix = translation_matrix(tx, ty)

    elif name == "rigid":
        angle = _sample_range(rng, ranges, "angle_degrees", (0.0, 0.0))
        parameters.update({"angle_degrees": angle, "center": center.tolist()})
        matrix = rigid_matrix(angle, tx=tx, ty=ty, center=center)

    elif name == "similarity":
        angle = _sample_range(rng, ranges, "angle_degrees", (0.0, 0.0))
        scale = _sample_range(rng, ranges, "scale", (1.0, 1.0))
        if scale <= 0.0:
            raise ValueError("Sampled similarity scale must be greater than zero.")
        parameters.update(
            {
                "angle_degrees": angle,
                "scale": scale,
                "center": center.tolist(),
            }
        )
        matrix = similarity_matrix(scale, angle, tx=tx, ty=ty, center=center)

    elif name == "affine":
        angle = _sample_range(rng, ranges, "angle_degrees", (0.0, 0.0))
        scale_x = _sample_range(rng, ranges, "scale_x", (1.0, 1.0))
        scale_y = _sample_range(rng, ranges, "scale_y", (1.0, 1.0))
        shear_x = _sample_range(rng, ranges, "shear_x", (0.0, 0.0))
        linear = _affine_linear_matrix(angle, scale_x, scale_y, shear_x)
        parameters.update(
            {
                "angle_degrees": angle,
                "scale_x": scale_x,
                "scale_y": scale_y,
                "shear_x": shear_x,
                "center": center.tolist(),
                "linear": linear.tolist(),
            }
        )
        matrix = affine_matrix(linear, tx=tx, ty=ty, center=center)

    else:
        raise ValueError("transform_type must be translation, rigid, similarity, or affine.")

    return GroundTruthTransform(
        transform_type=name,
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )


def default_control_points(
    image_shape: tuple[int, ...],
    margin_fraction: float = 0.20,
) -> FloatArray:
    """Return five deterministic control points inside the image bounds."""
    height, width = _validate_image_shape(image_shape)
    if not 0.0 <= margin_fraction < 0.5:
        raise ValueError("margin_fraction must be in the range [0, 0.5).")

    left = margin_fraction * (width - 1)
    right = (1.0 - margin_fraction) * (width - 1)
    top = margin_fraction * (height - 1)
    bottom = (1.0 - margin_fraction) * (height - 1)
    center = image_center(image_shape)

    return np.array(
        [
            [left, top],
            [right, top],
            [right, bottom],
            [left, bottom],
            center,
        ],
        dtype=np.float64,
    )


def generate_synthetic_pair(
    fixed_image: ArrayLike,
    ground_truth: GroundTruthTransform,
    *,
    interpolation: InterpolationName = "linear",
    border_value: float | tuple[float, ...] = 0.0,
    control_points_fixed: ArrayLike | None = None,
) -> SyntheticPair:
    """Generate a moving image from a fixed image and exact ground truth.

    The project stores registration transforms as Moving -> Fixed. To synthesize
    a moving image from the fixed reference, the inverse Fixed -> Moving transform
    is applied to the fixed image. Reapplying Moving -> Fixed later should align
    the moving image back to the fixed coordinate system, subject to interpolation
    and field-of-view loss.
    """
    fixed = np.asarray(fixed_image)
    if fixed.ndim not in (2, 3):
        raise ValueError("fixed_image must have shape (H, W) or (H, W, C).")
    if fixed.shape[0] <= 0 or fixed.shape[1] <= 0:
        raise ValueError("fixed_image must be non-empty.")

    output_shape = (int(fixed.shape[0]), int(fixed.shape[1]))
    moving = warp_image(
        fixed,
        ground_truth.fixed_to_moving,
        output_shape=output_shape,
        interpolation=interpolation,
        border_value=border_value,
    )

    if control_points_fixed is None:
        fixed_points = default_control_points(fixed.shape)
    else:
        fixed_points = np.asarray(control_points_fixed, dtype=np.float64)
        if fixed_points.ndim != 2 or fixed_points.shape[1] != 2:
            raise ValueError("control_points_fixed must have shape (N, 2).")
        if not np.all(np.isfinite(fixed_points)):
            raise ValueError("control_points_fixed must contain finite values.")

    moving_points = apply_transform(fixed_points, ground_truth.fixed_to_moving)
    recovered_fixed_points = apply_transform(moving_points, ground_truth.moving_to_fixed)

    return SyntheticPair(
        fixed=fixed.copy(),
        moving=moving,
        ground_truth=ground_truth,
        control_points_moving=moving_points,
        control_points_fixed=recovered_fixed_points,
    )


def control_point_round_trip_error(pair: SyntheticPair) -> FloatArray:
    """Return per-point Moving -> Fixed ground-truth recovery error in pixels."""
    recovered = apply_transform(
        pair.control_points_moving,
        pair.ground_truth.moving_to_fixed,
    )
    return np.linalg.norm(recovered - pair.control_points_fixed, axis=1)
