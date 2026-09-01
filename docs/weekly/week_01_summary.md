# Week 1 Summary

## Registration Foundations and Pipeline Skeleton

**Status:** Complete  
**Completed days:** 5 of 5

## Weekly objective

Build a reproducible 2D image-registration foundation before adding automatic registration methods. The week focused on coordinate conventions, transform mathematics, image handling, resampling, preprocessing, evaluation, configuration, tests, and structured outputs.

## Work completed by day

| Day | Focus | Status |
|---|---|---|
| Day 1 | Repository setup, environment, conventions, homogeneous coordinates, translation | Complete |
| Day 2 | Rotation and rigid transformations | Complete |
| Day 3 | Similarity, affine, image warping, interpolation | Complete |
| Day 4 | Image I/O, metadata, preprocessing, evaluation, visualization | Complete |
| Day 5 | YAML-driven runner, structured outputs, integration smoke test | Complete |

## Technical foundation completed

### Conventions

- Fixed image is the reference or target.
- Moving image is the source to be aligned.
- Stored geometric transforms map Moving -> Fixed.
- Geometric coordinates use `(x, y)`.
- NumPy image indexing uses `image[y, x]`.
- Positive image-plane rotation is counterclockwise on the displayed image.
- Masks use nearest-neighbor interpolation.

### Transform support

```text
Identity       complete
Translation    complete
Rotation       complete
Rigid          complete
Similarity     complete
Affine         complete
```

Point transformation, inversion, composition, centered transforms, and numerical validation are covered by tests.

### Image handling

- Common raster loading through OpenCV.
- Medical-image loading through SimpleITK.
- Raster color conversion at the input boundary.
- SimpleITK spacing, origin, and direction preservation.
- Fixed/moving compatibility checks.

### Preprocessing

- grayscale conversion;
- percentile clipping;
- robust normalization;
- Gaussian smoothing;
- resizing;
- mask-aware cropping.

### Warping and interpolation

- forward Moving -> Fixed transform semantics;
- inverse sampling handled by the resampler;
- nearest, linear, and cubic interpolation for intensity images;
- nearest-neighbor-only mask resampling.

### Evaluation and visualization

Current descriptive metrics:

```text
MAE
MSE
NCC
SSIM
```

Current visual outputs:

```text
fixed/moving/registered comparison
absolute difference
alpha overlay
checkerboard
```

These image-similarity metrics are pipeline checks. Later benchmark work will add geometric and task-specific measures such as parameter error, TRE, Dice, success rate, and physical-space reporting.

### Configuration and reproducibility

Day 5 added a single YAML-driven runner:

```powershell
python scripts/run_experiment.py --config configs/day05_week01_smoke_test.yaml
```

Each run receives a deterministic identifier from the experiment name and configuration hash. The run directory stores:

```text
resolved configuration
metrics in JSON and CSV
transform parameters and matrix
stage-level timing
input metadata and SHA-256 hashes
environment information
execution log
visual figures
```

A standard registration result interface is also in place for later algorithm modules.

## Week 1 integration validation

Final local validation on Windows with Python 3.12.6 produced:

```text
66 passed
```

The final Week 1 smoke test improved the controlled pair from:

```text
MAE:   0.1556 -> 0.0699
NCC:   0.6057 -> 0.9645
SSIM:  0.5371 -> 0.8080
```

## Completion criteria

1. **Configuration-driven end-to-end workflow:** complete.
2. **Known and identity transform validation:** complete through unit and integration tests.
3. **Reproducible run metadata:** complete through configuration snapshots, hashes, transform files, timings, and environment metadata.
4. **Core test suite:** 66 tests passing in the configured local environment.
5. **Coordinate and transform conventions:** documented and enforced across the codebase.

## Week 1 deliverables

- installable Python package structure;
- pinned dependency file;
- documented transformation conventions;
- transform, warping, I/O, preprocessing, evaluation, and visualization modules;
- common registration result interface;
- YAML experiment configuration support;
- structured result storage;
- unit and integration tests;
- non-GUI figure rendering for portable batch execution;
- explicit run-log handler cleanup for repeatable execution on Windows;
- one complete Week 1 smoke-test configuration;
- daily and weekly technical summaries.

Week 1 is complete and ready for the controlled benchmark-data work planned next.
