"""2D homogeneous-coordinate transformation utilities.

Transforms are represented in the Moving -> Fixed direction and geometric
points use ``(x, y)`` coordinate order.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


def _validate_transform(transform: ArrayLike) -> FloatArray:
    """Return a validated 3x3 affine-form homogeneous transform as float64."""
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError(f"Expected a 3x3 transform, got shape {matrix.shape}.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Transform contains non-finite values.")
    if not np.isclose(matrix[2, 2], 1.0):
        raise ValueError("Expected homogeneous transform with bottom-right value 1.")
    if not np.allclose(matrix[2, :2], [0.0, 0.0]):
        raise ValueError("Only affine-form 2D homogeneous transforms are supported.")
    return matrix


def identity_matrix() -> FloatArray:
    """Return the 3x3 identity transformation."""
    return np.eye(3, dtype=np.float64)


def translation_matrix(tx: float, ty: float) -> FloatArray:
    """Return a Moving->Fixed 2D translation matrix.

    Positive ``tx`` moves geometric points to the right. Positive ``ty`` moves
    geometric points downward under the project's image-coordinate convention.
    """
    if not np.isfinite(tx) or not np.isfinite(ty):
        raise ValueError("Translation parameters must be finite.")

    return np.array(
        [
            [1.0, 0.0, float(tx)],
            [0.0, 1.0, float(ty)],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def rotation_matrix(angle_degrees: float) -> FloatArray:
    """Return a 2D rotation about the origin in image coordinates.

    The project defines positive angles as counterclockwise when viewed on an
    image display. Because image ``y`` increases downward, the corresponding
    point-coordinate matrix is::

        [ cos(theta)   sin(theta)  0 ]
        [-sin(theta)   cos(theta)  0 ]
        [     0             0      1 ]

    This convention makes a +90 degree rotation move a point located to the
    right of the origin upward on the displayed image.
    """
    if not np.isfinite(angle_degrees):
        raise ValueError("Rotation angle must be finite.")

    theta = np.deg2rad(float(angle_degrees))
    cos_theta = float(np.cos(theta))
    sin_theta = float(np.sin(theta))

    # Remove tiny floating-point remnants for exact quarter turns where useful.
    if np.isclose(cos_theta, 0.0, atol=1e-15):
        cos_theta = 0.0
    if np.isclose(sin_theta, 0.0, atol=1e-15):
        sin_theta = 0.0

    return np.array(
        [
            [cos_theta, sin_theta, 0.0],
            [-sin_theta, cos_theta, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def rigid_matrix(
    angle_degrees: float,
    tx: float = 0.0,
    ty: float = 0.0,
    center: ArrayLike | None = None,
) -> FloatArray:
    """Return a 2D rigid transform: rotation followed by translation.

    Parameters
    ----------
    angle_degrees:
        Positive values rotate counterclockwise in the displayed image.
    tx, ty:
        Translation applied after rotation, in geometric ``(x, y)`` units.
    center:
        Optional rotation center ``(cx, cy)``. If omitted, the origin ``(0, 0)``
        is used.

    Notes
    -----
    For a point ``p`` and center ``c`` the transformation is::

        p_fixed = R @ (p_moving - c) + c + t

    where ``R`` follows the project's image-coordinate rotation convention.
    """
    if not np.isfinite(tx) or not np.isfinite(ty):
        raise ValueError("Rigid translation parameters must be finite.")

    if center is None:
        center_xy = np.array([0.0, 0.0], dtype=np.float64)
    else:
        center_xy = np.asarray(center, dtype=np.float64)
        if center_xy.shape != (2,):
            raise ValueError("Rigid rotation center must have shape (2,).")
        if not np.all(np.isfinite(center_xy)):
            raise ValueError("Rigid rotation center must contain finite values.")

    rotation = rotation_matrix(angle_degrees)
    linear = rotation[:2, :2]
    translation = np.array([float(tx), float(ty)], dtype=np.float64)

    # p' = R(p-c) + c + t = Rp + (c - Rc + t)
    offset = center_xy - linear @ center_xy + translation

    transform = identity_matrix()
    transform[:2, :2] = linear
    transform[:2, 2] = offset
    return transform


def to_homogeneous(points: ArrayLike) -> FloatArray:
    """Convert one point ``(x, y)`` or an ``(N, 2)`` array to homogeneous form.

    A single point returns shape ``(3,)``. Multiple points return shape
    ``(N, 3)``.
    """
    array = np.asarray(points, dtype=np.float64)

    if array.ndim == 1:
        if array.shape != (2,):
            raise ValueError("A single Cartesian point must have shape (2,).")
        return np.array([array[0], array[1], 1.0], dtype=np.float64)

    if array.ndim == 2 and array.shape[1] == 2:
        ones = np.ones((array.shape[0], 1), dtype=np.float64)
        return np.concatenate([array, ones], axis=1)

    raise ValueError("Points must have shape (2,) or (N, 2).")


def from_homogeneous(points: ArrayLike) -> FloatArray:
    """Convert homogeneous point(s) back to Cartesian ``(x, y)`` coordinates."""
    array = np.asarray(points, dtype=np.float64)

    if array.ndim == 1:
        if array.shape != (3,):
            raise ValueError("A single homogeneous point must have shape (3,).")
        if np.isclose(array[2], 0.0):
            raise ValueError("Cannot normalize a homogeneous point with w=0.")
        return array[:2] / array[2]

    if array.ndim == 2 and array.shape[1] == 3:
        w = array[:, 2]
        if np.any(np.isclose(w, 0.0)):
            raise ValueError("Cannot normalize homogeneous points containing w=0.")
        return array[:, :2] / w[:, None]

    raise ValueError("Homogeneous points must have shape (3,) or (N, 3).")


def apply_transform(points: ArrayLike, transform: ArrayLike) -> FloatArray:
    """Apply a 3x3 transform to Cartesian point(s).

    Geometric points use ``(x, y)`` order and column-vector mathematics. The
    implementation handles multiple points in a vectorized form.
    """
    matrix = _validate_transform(transform)
    homogeneous = to_homogeneous(points)

    if homogeneous.ndim == 1:
        transformed = matrix @ homogeneous
    else:
        transformed = (matrix @ homogeneous.T).T

    return from_homogeneous(transformed)


def invert_transform(transform: ArrayLike) -> FloatArray:
    """Return the inverse of a valid, non-singular 3x3 transform."""
    matrix = _validate_transform(transform)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Transform is singular and cannot be inverted.") from exc
    return _validate_transform(inverse)


def compose_transforms(*transforms: Iterable[float] | ArrayLike) -> FloatArray:
    """Compose transforms supplied in application order.

    ``compose_transforms(T1, T2)`` means first apply ``T1``, then apply ``T2``.
    With column vectors the returned matrix is therefore ``T2 @ T1``.
    """
    if not transforms:
        return identity_matrix()

    total = identity_matrix()
    for transform in transforms:
        matrix = _validate_transform(transform)
        total = matrix @ total
    return _validate_transform(total)


def similarity_matrix(
    scale: float,
    angle_degrees: float = 0.0,
    tx: float = 0.0,
    ty: float = 0.0,
    center: ArrayLike | None = None,
) -> FloatArray:
    """Return a 2D similarity transform with isotropic scale.

    The transformation is applied around ``center`` and follows::

        p_fixed = s R @ (p_moving - c) + c + t

    where ``s`` is a positive isotropic scale, ``R`` is the project rotation
    matrix, ``c`` is the center, and ``t`` is translation.
    """
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("Similarity scale must be finite and greater than zero.")
    if not np.isfinite(tx) or not np.isfinite(ty):
        raise ValueError("Similarity translation parameters must be finite.")

    if center is None:
        center_xy = np.array([0.0, 0.0], dtype=np.float64)
    else:
        center_xy = np.asarray(center, dtype=np.float64)
        if center_xy.shape != (2,):
            raise ValueError("Similarity center must have shape (2,).")
        if not np.all(np.isfinite(center_xy)):
            raise ValueError("Similarity center must contain finite values.")

    rotation = rotation_matrix(angle_degrees)[:2, :2]
    linear = float(scale) * rotation
    translation = np.array([float(tx), float(ty)], dtype=np.float64)

    offset = center_xy - linear @ center_xy + translation

    transform = identity_matrix()
    transform[:2, :2] = linear
    transform[:2, 2] = offset
    return transform


def affine_matrix(
    linear: ArrayLike,
    tx: float = 0.0,
    ty: float = 0.0,
    center: ArrayLike | None = None,
) -> FloatArray:
    """Return a general 2D affine transform.

    Parameters
    ----------
    linear:
        A finite, non-singular 2x2 matrix controlling rotation, anisotropic
        scaling, shear, or combinations of those effects.
    tx, ty:
        Translation applied after the centered linear transformation.
    center:
        Optional center ``(cx, cy)``. If omitted, the origin is used.

    Notes
    -----
    For point ``p`` and center ``c``::

        p_fixed = A @ (p_moving - c) + c + t
    """
    linear_matrix = np.asarray(linear, dtype=np.float64)
    if linear_matrix.shape != (2, 2):
        raise ValueError("Affine linear component must have shape (2, 2).")
    if not np.all(np.isfinite(linear_matrix)):
        raise ValueError("Affine linear component must contain finite values.")
    if np.isclose(np.linalg.det(linear_matrix), 0.0):
        raise ValueError("Affine linear component must be non-singular.")
    if not np.isfinite(tx) or not np.isfinite(ty):
        raise ValueError("Affine translation parameters must be finite.")

    if center is None:
        center_xy = np.array([0.0, 0.0], dtype=np.float64)
    else:
        center_xy = np.asarray(center, dtype=np.float64)
        if center_xy.shape != (2,):
            raise ValueError("Affine center must have shape (2,).")
        if not np.all(np.isfinite(center_xy)):
            raise ValueError("Affine center must contain finite values.")

    translation = np.array([float(tx), float(ty)], dtype=np.float64)
    offset = center_xy - linear_matrix @ center_xy + translation

    transform = identity_matrix()
    transform[:2, :2] = linear_matrix
    transform[:2, 2] = offset
    return transform
