# Rotation and Rigid Transformation Notes

This document records the Day 2 mathematical conventions used by the project.

## 1. What is a rigid transformation?

A 2D rigid transformation combines:

1. **rotation**, and
2. **translation**.

It changes an object's position and orientation, but it does not change its size or shape.

A rigid transform preserves:

- distances;
- angles;
- lengths;
- parallel lines;
- collinearity;
- area;
- shape.

It does **not** include scale or shear.

## 2. Degrees of freedom

A 2D rigid transformation has three degrees of freedom:

```text
rotation angle theta
translation tx
translation ty
```

So the parameter vector can be written as:

```text
(theta, tx, ty)
```

The optional rotation center used by the utility is an application choice, not an additional degree of freedom in the rigid motion itself.

## 3. Rotation sign convention

The project uses image coordinates:

```text
x -> right
y -> down
```

Positive angles are defined as **counterclockwise when viewed on the displayed image**.

Because image `y` increases downward, the 2D point-coordinate rotation matrix is:

```text
R(theta) =
[ cos(theta)   sin(theta) ]
[-sin(theta)   cos(theta) ]
```

In homogeneous form:

```text
[ cos(theta)   sin(theta)   0 ]
[-sin(theta)   cos(theta)   0 ]
[     0             0        1 ]
```

A +90 degree rotation therefore maps a point to the right of the origin:

```text
(1, 0) -> (0, -1)
```

which is visually upward and therefore counterclockwise on an image display.

## 4. Rotation about an arbitrary center

Images are rarely meant to rotate around coordinate `(0, 0)`, which is the top-left corner. A useful rotation often occurs around a center:

```text
c = (cx, cy)
```

For a point `p`, rotation around `c` is:

```text
p_rotated = R @ (p - c) + c
```

This can also be understood as three operations:

```text
1. translate center to origin:   p - c
2. rotate around origin:         R @ (p - c)
3. translate back:               R @ (p - c) + c
```

## 5. Rigid transformation equation

After adding translation `t = (tx, ty)`, the full rigid transformation is:

```text
p_fixed = R @ (p_moving - c) + c + t
```

Expanding the expression:

```text
p_fixed = R @ p_moving + (c - R @ c + t)
```

Therefore the homogeneous transform has the form:

```text
T_MF =
[ r11  r12  bx ]
[ r21  r22  by ]
[  0    0    1 ]
```

where:

```text
[b_x, b_y]^T = c - R @ c + t
```

The stored direction remains:

```text
Moving -> Fixed
```

## 6. Day 2 numerical example

Use:

```text
moving point = (120, 100)
center       = (100, 100)
angle        = +90 degrees
translation  = (+10, +5)
```

Relative to the center, the moving point is:

```text
(120, 100) - (100, 100) = (20, 0)
```

After +90 degrees counterclockwise in the image display:

```text
(20, 0) -> (0, -20)
```

Translate back to the center:

```text
(100, 100) + (0, -20) = (100, 80)
```

Apply the rigid translation:

```text
(100, 80) + (10, 5) = (110, 85)
```

Therefore:

```text
(120, 100) -> (110, 85)
```

## 7. Numerical properties checked in tests

For a proper 2D rigid rotation matrix `R`:

```text
R^T R = I
```

and:

```text
det(R) = +1
```

These properties mean the rotation block is orthonormal and does not introduce scale, shear, or reflection.

The tests also verify:

- a known +90 degree rotation;
- centered rotation;
- a known rigid transform;
- distance preservation;
- inverse recovery;
- determinant and orthogonality.

## 8. Important warning for later library integration

OpenCV, SimpleITK, NumPy, and mathematical texts may expose rotation and transform conventions differently. Future adapters must explicitly convert to the project convention instead of assuming that a library matrix can be stored unchanged.
