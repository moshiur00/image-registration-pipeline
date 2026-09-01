# Day 4 Summary

**Date:** 2026-09-01  
**Week:** 1 - Registration Foundations and Pipeline Skeleton  
**Status:** Complete

## Day 4 objective

Add reusable image loading, input validation, baseline preprocessing, descriptive evaluation metrics, and visualization helpers so the transformation and warping foundation can operate on explicit pipeline inputs rather than only in-memory arrays.

## Implemented today

### Image loading and metadata

Added `src/image_registration/io.py` with:

```text
LoadedImage
load_image()
validate_image_pair()
```

Raster support currently includes PNG, JPEG, BMP, TIFF, and TIF through OpenCV.

Medical-image support currently includes MHA, MHD, NIfTI, and NRRD through SimpleITK.

SimpleITK spacing, origin, and direction metadata are preserved. Raster color images are standardized from OpenCV BGR/BGRA ordering to RGB/RGBA at the loading boundary.

### Baseline preprocessing

Added `src/image_registration/preprocessing.py` with:

```text
to_grayscale()
clip_percentiles()
robust_normalize()
gaussian_smooth()
resize_image()
crop_to_mask()
preprocess_image()
```

The default Day 4 preprocessing path is:

```text
grayscale
  -> 1st to 99th percentile clipping
  -> normalization to [0, 1]
  -> Gaussian smoothing
```

Optional resizing is supported using explicit `(height, width)` project semantics.

### Initial evaluation skeleton

Added `src/image_registration/evaluation.py` with:

```text
MAE
MSE
NCC
SSIM
evaluate_pair()
```

These metrics are intentionally treated as descriptive image-similarity checks. They are not interpreted as automatic proof of correct registration.

### Visualization helpers

Added `src/image_registration/visualization.py` with:

```text
alpha_overlay()
absolute_difference()
checkerboard()
save_comparison_figure()
```

### Controlled Day 4 demo

Added:

```text
configs/day04_io_preprocessing_evaluation_demo.yaml
scripts/day04_io_preprocessing_evaluation_demo.py
```

The demo creates deterministic fixed and moving images, writes them to disk, reloads them through the common loader, preprocesses them, applies the known Moving -> Fixed transform, evaluates before and after alignment, and saves visual outputs.

No automatic transform estimation is introduced.

## Tests added

Added test modules for:

```text
tests/test_io.py
tests/test_preprocessing.py
tests/test_evaluation.py
tests/test_visualization.py
```

Coverage includes:

- grayscale raster loading;
- BGR-to-RGB conversion at the raster boundary;
- SimpleITK spacing, origin, and direction preservation;
- missing input rejection;
- pair shape validation;
- robust normalization;
- constant-image normalization;
- Gaussian smoothing;
- resize dimension order;
- mask-aware cropping;
- preprocessing reports;
- identity evaluation metrics;
- masked metric evaluation;
- shape mismatch rejection;
- overlay, difference, checkerboard, and saved comparison figures.

## Day 4 outputs

Running the Day 4 script writes generated files under:

```text
outputs/day04_io_preprocessing_evaluation_demo/
```

Expected files include:

```text
inputs/fixed_raw.png
inputs/moving_raw.png
fixed_preprocessed.png
moving_preprocessed.png
registered_known_transform.png
registered_difference.png
registered_overlay.png
registered_checkerboard.png
comparison.png
result.json
```

Generated outputs remain excluded from the lightweight share ZIP.

## Concepts reinforced

- File format and image-array conventions must be explicit.
- OpenCV color ordering should not leak into the rest of the project.
- Medical-image physical metadata must be preserved rather than reconstructed later.
- Robust preprocessing should change intensities deliberately without changing geometry unexpectedly.
- Width-height API differences must be handled at module boundaries.
- Similarity metrics and geometric registration correctness are different concepts.
- Visual inspection is useful, but it should accompany rather than replace quantitative checks.

## Day 4 completion check

- Image loading interface added: complete
- Common raster loading tested: complete
- Medical metadata loading tested: complete
- Pair validation added: complete
- Baseline preprocessing added: complete
- Evaluation skeleton added: complete
- Visualization helpers added: complete
- Configured Day 4 demonstration added: complete
- Daily summary updated: complete
- Weekly summary updated: complete

## Next step

Day 5 will combine the Week 1 components into a reusable configuration-driven load -> preprocess -> warp -> evaluate -> save smoke-test workflow, add structured run metadata and deterministic result directories, then perform Week 1 integration validation.
