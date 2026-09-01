# Transformation and Coordinate Conventions

These conventions are project-level rules. Every future registration, warping, evaluation, and visualization module must follow them.

## 1. Fixed, moving, and registered images

- `fixed`: reference image defining the target coordinate system.
- `moving`: source image that must be aligned.
- `registered`: resampled moving image expressed on the fixed-image grid.

The registration problem is therefore:

```text
moving -> fixed
```

## 2. Stored transformation direction

A stored transform is named `T_MF` and maps a point from moving-image coordinates to fixed-image coordinates:

```text
p_F = T_MF @ p_M
```

where `p_M` and `p_F` are homogeneous column vectors.

The inverse is:

```text
p_M = inverse(T_MF) @ p_F
```

This distinction matters because image resampling normally asks, for each destination/fixed pixel, which source/moving location should be sampled. That operation uses inverse mapping internally. It does not change the project-level meaning of the stored transform.

## 3. Image coordinates

For NumPy image access:

```python
value = image[y, x]
```

For geometric points and transformation matrices:

```text
point = (x, y)
```

Therefore:

- `x` is the image column and increases to the right.
- `y` is the image row and increases downward.

Do not pass NumPy array index order `(row, column)` into transform functions without converting it to `(x, y)`.

## 4. Homogeneous 2D coordinates

A Cartesian point `(x, y)` becomes:

```text
[x, y, 1]^T
```

A 2D affine-form transformation is represented by a 3 x 3 homogeneous matrix.

Identity:

```text
[1 0 0]
[0 1 0]
[0 0 1]
```

Translation by `(tx, ty)`:

```text
[1 0 tx]
[0 1 ty]
[0 0  1]
```

For `(x, y) = (100, 100)` and `(tx, ty) = (30, 20)`:

```text
x' = 100 + 30 = 130
y' = 100 + 20 = 120
```

## 5. Rotation direction

Positive rotation angles are measured in **degrees** and mean **counterclockwise when viewed on the displayed image**.

Because the project uses image coordinates where `y` increases downward, the 2D point-coordinate rotation matrix is:

```text
[ cos(theta)   sin(theta) ]
[-sin(theta)   cos(theta) ]
```

Therefore a +90 degree rotation maps:

```text
(1, 0) -> (0, -1)
```

which is visually upward from a point initially to the right of the origin.

This sign convention must be checked when converting matrices to or from OpenCV, SimpleITK, or other libraries.

## 6. Rigid transformation

A 2D rigid transform has three degrees of freedom:

```text
theta, tx, ty
```

For a rotation center `c` and translation `t`:

```text
p_F = R @ (p_M - c) + c + t
```

Rigid transformations preserve distance, angle, length, shape, and area. They do not include scaling or shear.

See `docs/ROTATION_RIGID_TRANSFORMS.md` for the worked Day 2 derivation.

## 7. Transform composition

The code accepts transforms in the order in which they are applied.

```python
T_total = compose_transforms(T1, T2)
```

means:

```text
point -> T1 -> T2
```

and mathematically:

```text
T_total = T2 @ T1
```

This rule is tested explicitly.

## 8. Numerical tolerance

Exact point transformations can be checked very tightly. Image resampling in later days will require interpolation-dependent tolerances.

## 9. Future physical-coordinate rule

For ordinary 2D images, early synthetic experiments may use pixel coordinates. For medical data, later modules must preserve spacing, origin, and direction and report geometric errors in physical coordinates where appropriate.

## 10. Similarity transformation

A 2D similarity transform adds one positive isotropic scale to rigid motion:

```text
p_F = s R @ (p_M - c) + c + t
```

The same scale factor is applied to both coordinate axes. Angles and shape are preserved, while lengths are multiplied by `s`.

## 11. Affine transformation

A general 2D affine transform is:

```text
p_F = A @ (p_M - c) + c + t
```

where `A` is a finite, non-singular 2 x 2 matrix. It can represent rotation, anisotropic scaling, shear, and combinations of these effects.

Affine transformations preserve straight lines and parallelism but do not generally preserve lengths or angles.

## 12. Image resampling convention

The public warping API accepts a forward source-to-destination transform.

For registration this is normally:

```text
Moving -> Fixed
```

For each fixed-grid destination coordinate, the resampler needs the corresponding moving-image source coordinate:

```text
p_M = inverse(T_MF) @ p_F
```

The project does not change the stored transform direction for warping. The inverse lookup is an implementation detail of resampling.

## 13. Interpolation convention

Intensity images may use:

```text
nearest
linear
cubic
```

Discrete label masks must use:

```text
nearest
```

This prevents interpolation from creating label values that were not present in the source mask.

## 14. Output shape order

Warping functions express output image shape as:

```text
(height, width)
```

This follows NumPy array shape order. Geometric points remain `(x, y)`.
