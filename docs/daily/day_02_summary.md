# Day 2 Summary

**Date:** 2026-09-01  
**Week:** 1 - Registration Foundations and Pipeline Skeleton  
**Status:** Complete

## Day 2 objective

Extend the Day 1 translation and homogeneous-coordinate foundation to 2D rotation and rigid transformations. The main goal was to understand the mathematics, make the rotation sign convention explicit for image coordinates, and verify rigid-transform properties numerically before image warping is introduced.

## Work completed

1. Added an explicit project-wide positive rotation convention: counterclockwise when viewed on the image display.
2. Documented why the image-coordinate rotation matrix differs in sign from the usual y-up Cartesian matrix.
3. Implemented `rotation_matrix(angle_degrees)` for rotation around the origin.
4. Implemented `rigid_matrix(angle_degrees, tx, ty, center)` for rotation around an arbitrary center followed by translation.
5. Kept the stored transformation direction as **Moving -> Fixed**.
6. Added validation for non-finite rotation, translation, and center parameters.
7. Added a YAML-configured Day 2 rigid-transform numerical demonstration.
8. Added checks that a rigid rotation block is orthonormal and has determinant +1.
9. Added tests for known rotation, known centered rigid motion, fixed rotation center, distance preservation, orthogonality, determinant, and inverse recovery.
10. Added a dedicated technical note explaining rigid transformation mathematics and the Day 2 worked example.
11. Ran the complete test suite successfully: **19 tests passed**.

## Mathematical model

For rotation center `c`, translation `t`, moving point `p_M`, and rotation matrix `R`:

```text
p_F = R @ (p_M - c) + c + t
```

The project stores this as a homogeneous Moving -> Fixed transform.

## Day 2 numerical smoke test

Configured case:

```text
Moving point    = (120, 100)
Rotation center = (100, 100)
Angle           = +90 degrees
Translation     = (+10, +5)
```

Expected result:

```text
Fixed point = (110, 85)
```

The demo also applies the inverse transform and must recover:

```text
Moving point = (120, 100)
```

Run:

```bash
python scripts/day02_rigid_demo.py --config configs/day02_rigid_demo.yaml
```

## Files added on Day 2

```text
configs/day02_rigid_demo.yaml
docs/ROTATION_RIGID_TRANSFORMS.md
docs/daily/day_02_summary.md
scripts/day02_rigid_demo.py
```

## Files updated on Day 2

```text
README.md
docs/TRANSFORM_CONVENTIONS.md
docs/weekly/week_01_summary.md
src/image_registration/__init__.py
src/image_registration/conventions.py
src/image_registration/transforms.py
tests/test_transforms.py
```

## What was learned

A rigid transformation has three degrees of freedom in 2D: one rotation angle and two translations. It preserves geometric distances and angles, unlike later similarity and affine models. Rotation around an image center must be expressed explicitly because a rotation matrix by itself rotates around the coordinate origin.

## Not implemented yet

Day 2 still intentionally excludes:

- image resampling/warping;
- interpolation;
- similarity transforms;
- affine transforms;
- automatic registration algorithms;
- image loading and preprocessing.

## Next work

Day 3 will add similarity and affine transformation foundations, then begin image warping and interpolation so the project can move from transforming points to transforming actual images.
