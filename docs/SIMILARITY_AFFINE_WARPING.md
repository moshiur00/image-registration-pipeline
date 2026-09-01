# Similarity, Affine, and Image Warping

This note documents the Day 3 transformation and resampling foundations.

## 1. Why Day 3 matters

Days 1 and 2 transformed geometric points. Day 3 connects that mathematics to actual image arrays.

The main sequence is now:

```text
source image
    -> known geometric transform
    -> inverse destination-to-source lookup
    -> interpolation
    -> resampled destination image
```

The project still stores transforms in the forward geometric direction, such as Moving -> Fixed. The image warper handles the inverse lookup required for resampling.

## 2. Similarity transformation

A 2D similarity transform has four degrees of freedom:

```text
scale, rotation, tx, ty
```

For center `c`, isotropic scale `s`, rotation `R`, and translation `t`:

```text
p_F = s R @ (p_M - c) + c + t
```

The same scale is applied in both spatial directions.

A similarity transform preserves:

- angles;
- overall shape;
- parallel lines;
- relative geometry.

It does not preserve absolute lengths when `s != 1`. Every distance is multiplied by `s`, and area is multiplied by `s^2`.

Rigid transformation is a special case of similarity transformation where:

```text
s = 1
```

## 3. Affine transformation

A general 2D affine transform is:

```text
p_F = A @ (p_M - c) + c + t
```

where `A` is a non-singular 2 x 2 matrix.

An affine transform has six degrees of freedom in its general 2D form. It can represent combinations of:

- translation;
- rotation;
- anisotropic scaling;
- shear.

Affine transformations preserve straight lines, collinearity, and parallelism. They do not generally preserve lengths or angles.

The homogeneous form is:

```text
[a00 a01 tx_effective]
[a10 a11 ty_effective]
[ 0   0       1      ]
```

## 4. Transform family relationship

The transform families form an increasing sequence of flexibility:

```text
Translation
    -> Rigid
    -> Similarity
    -> Affine
```

More flexibility can model more geometric variation, but it also introduces more parameters that a registration algorithm will later need to estimate reliably.

## 5. Forward geometric mapping

The project stores:

```text
p_F = T_MF @ p_M
```

This tells us where a moving-image point lands in fixed-image coordinates.

Forward point mapping is natural for geometric reasoning, landmarks, and ground-truth transforms.

## 6. Why image resampling uses inverse mapping

A destination image is filled pixel by pixel. For every destination pixel, the resampler must determine where its value should come from in the source image.

For Moving -> Fixed registration:

```text
p_M = inverse(T_MF) @ p_F
```

The destination fixed-grid pixel `p_F` therefore samples the moving image at `p_M`.

This avoids holes that can appear when source pixels are simply pushed forward.

The `warp_image()` API still accepts the forward source-to-destination transform. OpenCV performs the inverse sampling lookup internally.

## 7. Interpolation

Inverse-mapped source coordinates are often fractional, for example:

```text
(103.4, 82.7)
```

An image only stores values at discrete pixel locations, so an interpolation rule is required.

### Nearest neighbor

Uses the nearest source pixel.

Advantages:

- fast;
- does not invent new label values;
- correct choice for masks and segmentation labels.

Disadvantage:

- blocky appearance for intensity images.

### Bilinear

Uses nearby pixels in a 2 x 2 neighborhood.

Advantages:

- smooth;
- efficient;
- a good default for many intensity images.

Disadvantage:

- changes pixel intensities because values are blended.

### Bicubic

Uses a larger neighborhood and cubic interpolation.

Advantages:

- can produce smoother visual results.

Disadvantages:

- slower;
- can overshoot local intensity values;
- still unsuitable for discrete masks.

## 8. Mask rule

Segmentation masks must use nearest-neighbor interpolation.

For example, if a mask contains labels:

```text
0, 2, 7
```

linear interpolation could create invalid values such as:

```text
1, 3, 4, 5, 6
```

`warp_mask()` therefore forces nearest-neighbor interpolation.

## 9. Repeated resampling

Repeatedly warping an already warped image compounds interpolation error and blur.

Whenever possible, compose geometric transforms first and resample the original image once.

For transforms `T1` then `T2`:

```text
T_total = T2 @ T1
```

Then use one image resampling operation with `T_total`.

## 10. Day 3 demonstration

Run:

```bash
python scripts/day03_warping_demo.py --config configs/day03_warping_demo.yaml
```

The script:

1. creates a deterministic synthetic grayscale image and label mask;
2. defines a known Similarity Moving -> Fixed transform;
3. generates a synthetic moving image using the inverse transform;
4. warps the moving image back to the fixed grid;
5. compares nearest, linear, and cubic interpolation;
6. verifies that mask labels remain discrete under nearest-neighbor interpolation;
7. demonstrates a general affine transform on control points;
8. verifies affine inverse recovery;
9. saves the generated images and a machine-readable JSON result under `outputs/day03_warping_demo/`.

## 11. Day 3 boundary

Day 3 does not estimate a transformation from two unknown images. All transforms are still known and controlled.

Automatic registration methods begin later. This separation is intentional because transformation and resampling correctness must be established before optimization or feature matching is introduced.
