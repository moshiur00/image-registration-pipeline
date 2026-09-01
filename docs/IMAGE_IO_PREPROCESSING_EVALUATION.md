# Image I/O, Preprocessing, Evaluation, and Visualization

## Purpose

Day 4 connects the geometric work from Days 1 to 3 to actual pipeline inputs and outputs. The goal is not automatic registration yet. The goal is to make image handling explicit, reproducible, and testable before Day 5 combines the pieces into the Week 1 smoke-test workflow.

## 1. Image loading

The project now uses `load_image()` as the common entry point for supported image files.

Supported raster formats:

```text
PNG
JPEG
BMP
TIFF
TIF
```

Supported medical-image formats:

```text
MHA
MHD
NIfTI (.nii and .nii.gz)
NRRD
```

Raster images are read with OpenCV. Because OpenCV normally returns color data in BGR order, the project converts color raster images to RGB at the loading boundary. This avoids hidden color-order assumptions in later preprocessing code.

Medical images are read with SimpleITK. The loader preserves:

```text
spacing
origin
direction
```

For a 2D SimpleITK image, the physical geometry follows SimpleITK `(x, y)` conventions while the returned NumPy array uses `(y, x)` indexing. For a 3D image, SimpleITK physical metadata is `(x, y, z)` while the NumPy array returned by `GetArrayFromImage()` is indexed as `(z, y, x)`.

The `LoadedImage` object therefore keeps both the NumPy array and metadata describing its source and axis order.

## 2. Fixed and moving image validation

`validate_image_pair()` performs basic checks before a pair is passed into preprocessing or warping.

Current Day 4 checks include:

- both arrays are non-empty;
- dimensionality can be required to match;
- complete array shape can be required to match.

The Day 4 demo uses equal-sized 2D grayscale images. Later dataset preparation can relax some checks when a registration method is designed to handle unequal input sizes.

## 3. Baseline preprocessing

The Day 4 preprocessing sequence is intentionally simple:

```text
load
  -> grayscale if needed
  -> percentile clipping
  -> robust normalization to [0, 1]
  -> optional Gaussian smoothing
  -> optional resize
```

The sequence is implemented by `preprocess_image()` and controlled by a configuration dictionary.

### Grayscale conversion

Raster color data is standardized to RGB when loaded. `to_grayscale()` therefore uses RGB-to-grayscale conversion rather than OpenCV's default BGR assumption.

### Percentile clipping

A small number of extreme intensity values can dominate min-max scaling. The project therefore supports clipping between configurable percentiles, for example:

```text
1st percentile
99th percentile
```

This is a robust intensity-preparation step. It does not change image geometry.

### Robust normalization

After clipping, `robust_normalize()` maps the clipped intensity range to:

```text
[0, 1]
```

The output type is `float32`.

### Gaussian smoothing

`gaussian_smooth()` can suppress high-frequency noise before later similarity or optimization stages. The standard deviation is configured in pixel units.

A sigma of zero disables smoothing.

### Resizing

`resize_image()` uses explicit `(height, width)` output shape at the public interface. Internally, OpenCV receives `(width, height)` as required by its API.

This distinction is tested because width-height confusion is a common source of image-pipeline bugs.

### Mask-aware cropping utility

`crop_to_mask()` returns:

```text
cropped image
cropped mask
bounding box (x0, y0, x1, y1)
```

The right and lower bounds are exclusive, matching standard Python slicing behavior.

## 4. Initial evaluation skeleton

Day 4 introduces a small descriptive metric set:

```text
MAE   mean absolute error
MSE   mean squared error
NCC   normalized cross correlation
SSIM  structural similarity
```

These metrics are used to check whether a known transform improves the synthetic Day 4 example.

Important limitation:

Image similarity is not automatic proof that registration is geometrically or anatomically correct. Later weeks will add ground-truth parameter error, TRE, Dice, success criteria, physical-space reporting, and benchmark-level aggregation.

The Day 4 implementation therefore describes these values as pipeline and image-similarity checks only.

## 5. Visualization helpers

The project now provides reusable helpers for:

```text
alpha overlay
absolute difference
checkerboard
comparison figure
```

These visualizations make alignment behavior inspectable while keeping quantitative metrics separate.

## 6. Day 4 demonstration

Run:

```powershell
python scripts/day04_io_preprocessing_evaluation_demo.py --config configs/day04_io_preprocessing_evaluation_demo.yaml
```

The demonstration performs the following controlled sequence:

```text
create deterministic fixed image
  -> create a moving image with a known similarity transform
  -> add controlled brightness and noise changes
  -> save both inputs
  -> load them through load_image()
  -> validate the pair
  -> preprocess both images
  -> warp the moving image with the known Moving -> Fixed transform
  -> evaluate before and after warping
  -> save visual comparisons
  -> save result.json
```

The transform is still known and supplied directly. No registration algorithm estimates it yet.

## 7. Why this belongs before automatic registration

If image loading, color handling, normalization, metadata, or visualization is inconsistent, later algorithms can appear to fail even when the registration mathematics is correct. Day 4 separates those concerns and gives them independent tests.

At the end of Day 4, the project has the pieces needed for Day 5 to build a single configuration-driven Week 1 workflow.
