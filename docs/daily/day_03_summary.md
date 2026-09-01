# Day 3 Summary

**Date:** 2026-09-01  
**Week:** 1 - Registration Foundations and Pipeline Skeleton  
**Status:** Complete

## Day 3 objective

Extend the transformation foundation from rigid motion to similarity and affine models, then introduce image resampling so known geometric transforms can be applied to actual image arrays.

## Work completed

1. Implemented `similarity_matrix()` with isotropic scale, rotation, translation, and an optional transformation center.
2. Implemented `affine_matrix()` with a general non-singular 2 x 2 linear component, translation, and an optional center.
3. Added validation for invalid similarity scales, malformed affine matrices, singular affine matrices, and non-finite parameters.
4. Added `warp_image()` for 2D grayscale or multichannel image resampling.
5. Standardized the warping API around a forward source-to-destination transform while allowing the resampler to perform inverse lookup internally.
6. Added nearest-neighbor, bilinear, and bicubic interpolation options.
7. Added `warp_mask()` that always uses nearest-neighbor interpolation to protect discrete labels.
8. Added tests that verify forward translation direction on an actual image pixel.
9. Added tests for exact identity warping, interpolation behavior, output shape, mask labels, and invalid input handling.
10. Added a configuration-driven Day 3 demonstration that creates a synthetic image, generates a transformed moving image, and resamples it back to the fixed grid.
11. Added an affine control-point demonstration with numerical inverse recovery.
12. Added technical documentation covering transform hierarchy, inverse resampling, interpolation, mask handling, and repeated-resampling effects.

## Transformation hierarchy reached

```text
Translation
    -> Rigid
    -> Similarity
    -> Affine
```

### Similarity

```text
p_F = s R @ (p_M - c) + c + t
```

Similarity adds one isotropic scale parameter to rigid motion.

### Affine

```text
p_F = A @ (p_M - c) + c + t
```

The general 2 x 2 matrix `A` can represent rotation, anisotropic scaling, shear, and their combinations.

## Image resampling rule

The stored registration transform remains:

```text
Moving -> Fixed
```

For a fixed-grid destination location, source sampling requires:

```text
p_M = inverse(T_MF) @ p_F
```

The warping API accepts the forward transform. The underlying resampler handles this inverse lookup internally.

## Interpolation rule established

```text
Intensity images:
nearest, linear, or cubic

Discrete masks:
nearest only
```

Nearest-neighbor interpolation is mandatory for masks because other interpolation modes can create label values that never existed in the original mask.

## Day 3 demo

Run:

```bash
python scripts/day03_warping_demo.py --config configs/day03_warping_demo.yaml
```

Generated local outputs include:

```text
fixed.png
moving.png
registered_nearest.png
registered_linear.png
registered_cubic.png
fixed_mask.png
moving_mask.png
registered_mask.png
result.json
```

## Files added on Day 3

```text
configs/day03_warping_demo.yaml
docs/SIMILARITY_AFFINE_WARPING.md
docs/daily/day_03_summary.md
scripts/day03_warping_demo.py
src/image_registration/warping.py
tests/test_warping.py
```

## Files updated on Day 3

```text
README.md
docs/TRANSFORM_CONVENTIONS.md
docs/weekly/week_01_summary.md
src/image_registration/__init__.py
src/image_registration/transforms.py
tests/test_transforms.py
```

## What was learned

Day 3 establishes the distinction between transforming coordinates and resampling an image. A forward transform states where source geometry moves, while image resampling needs an inverse source lookup for every destination pixel. Interpolation then determines how values are estimated at non-integer source coordinates.

Similarity is more flexible than rigid motion because it allows uniform scale. Affine is more flexible again because it can also model anisotropic scaling and shear.

## Not implemented yet

Day 3 intentionally excludes:

- automatic estimation of unknown transforms;
- image-file loading and metadata preservation;
- preprocessing pipeline;
- evaluation metric framework;
- standardized visualization module;
- registration method interfaces such as ECC, phase correlation, ORB, or mutual information.

## Next work

Day 4 will add image loading, validation, baseline preprocessing, visualization utilities, and an initial evaluation skeleton. These modules will make the project ready for the complete configuration-driven Week 1 smoke test on Day 5.
