# Affine ECC and Multiresolution Registration

## Purpose

Week 3 Day 4 extends the ECC baseline from translation and rigid motion to a general 2D affine model and adds a coarse-to-fine image pyramid.

The main question is whether multiresolution optimization increases ECC capture range when a full-resolution optimizer converges to an incorrect local solution.

## Affine model

An affine Moving -> Fixed transform is represented by

```text
[x_F]   [a00 a01 tx] [x_M]
[y_F] = [a10 a11 ty] [y_M]
[ 1 ]   [ 0   0   1] [ 1 ]
```

The 2x2 linear block can represent rotation, anisotropic scaling, and shear. Translation is stored in the final column.

The Day 4 controlled cases are created around the image center so the configured translation remains interpretable after rotation, scaling, and shear.

## Coarse-to-fine pyramid

The configured pyramid uses the scales:

```text
0.25 -> 0.5 -> 1.0
```

ECC first estimates the affine transform at the coarsest level. The estimate is transferred to the next level and refined. The process continues until full resolution.

Each level is generated from the original image using area downsampling. Optional Gaussian pre-smoothing reduces aliasing before downsampling.

## Transform scaling between levels

A transform cannot be copied between pyramid levels without accounting for the change of coordinate system.

If `S` converts coordinates from one image shape to another, the equivalent affine transform at the new level is

```text
T_new = S @ T_old @ inverse(S)
```

This preserves the Moving -> Fixed convention while correctly scaling translation. It also remains correct when integer image-size rounding creates slightly different horizontal and vertical scale factors.

## Initialization

Day 4 uses phase correlation as the common coarse initialization for both comparison strategies:

```text
single-resolution ECC + phase initialization
multiresolution ECC + phase initialization
```

Using the same initialization isolates the effect of the image pyramid more clearly than comparing different initialization methods.

## Evaluation

Each run records:

- mean TRE on deterministic control points;
- centered translation-parameter error;
- Frobenius error of the 2x2 affine linear component;
- NCC before and after registration;
- final ECC value;
- runtime;
- optimizer success and failure reason;
- number of pyramid levels completed.

The Day 4 development tolerances are:

```text
Mean TRE                  <= 1.0 pixel
Translation error         <= 1.5 pixels
Affine linear error       <= 0.02
```

These are development criteria for Week 3. Formal benchmark success rules will be consolidated during the unified evaluation work.

## Development reference run

The reference configuration contains nine affine cases and compares single-resolution with multiresolution ECC, for 18 registrations.

The development run produced:

```text
Single-resolution: 7/9 within tolerance
Multiresolution:    9/9 within tolerance
```

Two deliberately difficult capture-range cases converged to incorrect full-resolution affine solutions but were recovered accurately by the three-level pyramid.

One representative case produced:

```text
Single-resolution TRE: 97.483 pixels
Multiresolution TRE:     0.595 pixels
```

A second case produced:

```text
Single-resolution TRE: 82.202 pixels
Multiresolution TRE:     0.552 pixels
```

This demonstrates a larger capture range for the configured multiresolution procedure on these controlled cases. It does not imply that a pyramid is universally faster or more accurate for every image pair.

## Outputs

The Day 4 script writes full generated evidence under:

```text
outputs/week03_day04_ecc_affine_multiresolution/
```

The compact tracked report snapshot is:

```text
reports/week03_day04_ecc_affine_multiresolution.json
```

The output directory contains CSV and JSON result tables, the resolved configuration, comparison plots, pyramid-level visualization, and representative success and failure images.
