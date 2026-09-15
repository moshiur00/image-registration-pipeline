# Synthetic Ground-Truth Benchmark Foundation

## Purpose

Week 2 begins by creating synthetic fixed and moving image pairs with known geometric correspondence. The goal is to make later registration evaluation objective. A registration method will estimate a transformation, and that estimate can then be compared with the transformation that was used to generate the pair.

## Project convention

The stored registration transform remains:

```text
Moving -> Fixed
```

For synthetic generation, the fixed image is treated as the reference. A Moving -> Fixed ground-truth matrix is sampled first. Its inverse is then used to create the moving image from the fixed image:

```text
T_MF = sampled Moving -> Fixed transform
T_FM = inverse(T_MF)

moving = warp(fixed, T_FM)
```

Later, applying `T_MF` to the moving image returns it to the fixed coordinate system, subject to interpolation and field-of-view loss.

## Supported transform families on Day 1

### Translation

Parameters:

```text
tx
ty
```

### Rigid

Parameters:

```text
angle_degrees
tx
ty
center
```

The image center is used as the rotation center.

### Similarity

Parameters:

```text
scale
angle_degrees
tx
ty
center
```

The scale is isotropic.

### Affine

The Day 1 affine sampler uses interpretable parameters:

```text
angle_degrees
scale_x
scale_y
shear_x
tx
ty
center
```

These parameters are converted into a non-singular 2 x 2 affine linear block and then into the common homogeneous matrix representation.

## Deterministic sampling

Every sampling function receives a NumPy random generator. When the same seed, image shape, transform family, and parameter ranges are used, the sampled transformation is identical.

This property is required for reproducible benchmark generation.

## Ground-truth storage

Every generated pair stores:

```text
transform type
sampled parameters
Moving -> Fixed matrix
Fixed -> Moving inverse matrix
moving control points
fixed control points
control-point round-trip error
```

The stored inverse is checked numerically against the inverse of the forward matrix.

## Control points

Five deterministic control points are defined inside the image:

```text
top-left interior point
top-right interior point
bottom-right interior point
bottom-left interior point
image center
```

The fixed control points are mapped into moving coordinates with `T_FM`. Applying `T_MF` to those moving points should recover the original fixed points to numerical precision.

This creates a simple geometric verification mechanism that will later support landmark error and target registration error calculations.

## Day 1 scope boundary

Day 1 intentionally does not add:

```text
noise
blur
intensity changes
occlusion
partial overlap masks
multimodal simulation
difficulty tiers
real datasets
```

Those belong to later days of Week 2. Keeping them separate makes it possible to verify the geometry before appearance changes are introduced.
