# Configuration and Run Outputs

## Purpose

Day 5 integrates the Week 1 modules into one configuration-driven workflow. A single YAML file now controls input paths, preprocessing, a known transform, image warping, evaluation, visualization, and output handling.

The Week 1 runner uses a known transform. Transform estimation begins in later work packages.

## Run command

```powershell
python scripts/run_experiment.py --config configs/day05_week01_smoke_test.yaml
```

The runner performs:

```text
load configuration
  -> resolve paths and defaults
  -> load fixed and moving images
  -> validate inputs
  -> preprocess both images
  -> construct the configured Moving -> Fixed transform
  -> warp the moving image onto the fixed grid
  -> evaluate unregistered and registered pairs
  -> save figures, metrics, transform, timing, metadata, and logs
```

## Configuration sections

### experiment

```yaml
experiment:
  name: week01_smoke_test
  seed: 42
```

The experiment name is used in the deterministic run identifier. The seed is stored with the run metadata.

### data

```yaml
data:
  fixed: data/samples/week01/fixed.png
  moving: data/samples/week01/moving.png
  color_mode: grayscale
  require_same_shape: true
  require_same_ndim: true
```

Paths can be absolute or relative to the project root.

### preprocessing

```yaml
preprocessing:
  grayscale: true
  clip_lower_percentile: 1.0
  clip_upper_percentile: 99.0
  normalize: true
  gaussian_sigma: 0.6
  resize: null
```

The same preprocessing configuration is applied independently to fixed and moving images.

### transform

```yaml
transform:
  source: known
  type: similarity
  parameters:
    scale: 0.97
    angle_degrees: 5.0
    tx: 12.0
    ty: -7.0
    center: [110.0, 80.0]
```

Supported Week 1 transform types are:

```text
identity
translation
rigid
similarity
affine
```

The stored transform direction is always Moving -> Fixed.

### warp

```yaml
warp:
  interpolation: linear
  border_value: 0.0
```

Intensity images can use nearest, linear, or cubic interpolation.

### evaluation and visualization

```yaml
evaluation:
  enabled: true

visualization:
  enabled: true
  alpha: 0.5
  checkerboard_tile_size: 24
  title: Week 1 smoke test
```

Week 1 evaluation uses MAE, MSE, NCC, and SSIM as descriptive image-similarity measures.

### output

```yaml
output:
  root: outputs
  overwrite: true
```

The run directory name contains the experiment name and a short SHA-256 hash of the resolved configuration. Re-running the same configuration produces the same run identifier.

## Structured run directory

A successful run creates:

```text
outputs/<run_id>/
├── figures/
│   ├── fixed_preprocessed.png
│   ├── moving_preprocessed.png
│   ├── registered.png
│   ├── difference.png
│   ├── overlay.png
│   ├── checkerboard.png
│   └── comparison.png
├── metadata.json
├── metrics.csv
├── metrics.json
├── resolved_config.yaml
├── run.log
├── run_summary.json
├── timing.json
└── transform.json
```

### resolved_config.yaml

Stores the complete configuration used by the runner, including default values and resolved input paths.

### metrics.json and metrics.csv

Store the same metric values in machine-readable JSON and table form. Both unregistered and registered states are recorded.

### transform.json

Stores:

- transform type;
- source, currently `known`;
- Moving -> Fixed direction;
- coordinate order;
- configured parameters;
- final 3 x 3 matrix.

### timing.json

Records stage-level execution time for loading, preprocessing, warping, evaluation, visualization, and total runtime.

### metadata.json

Records input metadata, input SHA-256 hashes, preprocessing reports, Python version, platform information, CPU count, and key package versions.

### run.log

Stores a small execution log with the run identifier and resolved input paths.

## Registration interface

`src/image_registration/registration.py` defines the standard result structure that later registration algorithms will use:

```text
transform
registered_image
success
runtime_seconds
convergence_info
failure_reason
```

This keeps later methods such as phase correlation, ECC, feature-based registration, and mutual-information registration compatible with the same pipeline.

## Week 1 completion check

The Day 5 smoke test verifies that one configuration can execute the complete load -> preprocess -> warp -> evaluate -> save workflow without editing Python code. It also verifies deterministic run naming, structured outputs, input traceability, and integration of the Week 1 modules.
