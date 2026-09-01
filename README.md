# Image Registration Pipeline

A modular and reproducible Python framework for developing, testing, and benchmarking image-registration methods on monomodal and multimodal image pairs.

The project is organized as an eight-week implementation and evaluation plan. Week 1 is complete and establishes the common transformation, warping, preprocessing, evaluation, configuration, logging, and testing infrastructure required by the registration algorithms planned for the following weeks.

## Current status

**Week 1: Registration Foundations and Pipeline Skeleton**  
**Status: Complete, 5 of 5 working days**  
**Latest local validation: 66 tests passed on Windows with Python 3.12.6**

Automatic transform estimation is intentionally not part of Week 1. The current end-to-end smoke test uses a known transform so the pipeline can be validated independently before registration algorithms are introduced.

## Completed work

### Transformation foundation

- Fixed and moving image conventions
- Homogeneous coordinates
- Identity transformation
- Translation
- Rotation
- Rigid transformation
- Similarity transformation
- Affine transformation
- Transform composition and inversion
- Centered transformations
- Numerical transform validation

### Warping and interpolation

- Moving -> Fixed transform convention
- Inverse source lookup during resampling
- Nearest-neighbor interpolation
- Bilinear interpolation
- Bicubic interpolation
- Nearest-neighbor-only resampling for masks

### Image I/O and preprocessing

- Raster image loading with OpenCV
- Medical image loading with SimpleITK
- RGB/RGBA standardization for raster images
- Preservation of SimpleITK spacing, origin, and direction
- Fixed/moving compatibility checks
- Grayscale conversion
- Percentile clipping
- Robust intensity normalization
- Gaussian smoothing
- Resizing
- Mask-aware cropping

### Evaluation and visualization

Current descriptive image-similarity measures:

- MAE
- MSE
- NCC
- SSIM

Current visual outputs:

- Fixed, moving, and registered comparison
- Absolute-difference image
- Alpha overlay
- Checkerboard comparison

These measures are currently used to verify pipeline behavior. Later benchmark stages will add geometric and task-specific evaluation such as parameter error, TRE, Dice, success rate, and physical-space error.

### Configuration and reproducibility

- YAML-based experiment configuration
- Deterministic run identifiers
- Structured output directories
- Resolved configuration snapshots
- Transform parameter storage
- JSON and CSV metric output
- Stage-level timing
- Input SHA-256 hashes
- Environment metadata
- Execution logs
- Non-GUI figure rendering for batch execution
- Windows-safe log-handler cleanup for repeatable runs
- Common registration result interface for later algorithms

## Future planned tasks

| Week | Planned work | Main outcome |
|---|---|---|
| Week 2 | Controlled dataset and ground-truth benchmark design | Synthetic monomodal and multimodal pairs with known transforms, degradations, overlap masks, manifests, and small real-data subsets |
| Week 3 | Monomodal intensity and frequency-domain baselines | Phase correlation and ECC registration with multiresolution support, convergence diagnostics, and baseline comparisons |
| Week 4 | Feature-based registration | ORB matching with RANSAC for similarity and affine estimation, match diagnostics, failure checks, and optional SIFT comparison |
| Week 5 | Multimodal registration | SimpleITK mutual-information registration for rigid and affine transforms with physical-coordinate handling |
| Week 6 | Unified evaluation and reproducible benchmarking | Parameter error, TRE, Dice, overlap-aware similarity metrics, runtime measurement, success rules, and resumable benchmark execution |
| Week 7 | Robustness and failure analysis | Controlled degradation sweeps, runtime analysis, failure taxonomy, failure gallery, and condition-specific method comparison |
| Week 8 | Final benchmark and documentation | Frozen benchmark, final tables and plots, technical analysis, documentation, presentation, and reproducible release snapshot |

A limited B-spline deformable-registration experiment is reserved as an optional extension after the core benchmark is complete.

## Core conventions

- Fixed image: reference or target image.
- Moving image: source image that must be aligned to the fixed image.
- Stored transform direction: **Moving -> Fixed**.
- Geometric coordinates: `(x, y) = (column, row)`.
- NumPy indexing: `image[y, x]`.
- Homogeneous points: column-vector form `[x, y, 1]^T`.
- Positive rotation: counterclockwise on the displayed image.
- Rotation angles: degrees.
- Mask interpolation: nearest neighbor only.
- Raster color order inside the project: RGB or RGBA after loading.
- SimpleITK physical metadata: spacing, origin, and direction are preserved.

For a moving-image point:

```text
p_F = T_MF @ p_M
```

Image resampling uses inverse source lookup internally. The stored project transform remains Moving -> Fixed.

## Project structure

```text
image-registration-pipeline/
├── configs/
│   ├── day01_translation_demo.yaml
│   ├── day02_rigid_demo.yaml
│   ├── day03_warping_demo.yaml
│   ├── day04_io_preprocessing_evaluation_demo.yaml
│   └── day05_week01_smoke_test.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   └── samples/
│       └── week01/
│           ├── fixed.png
│           └── moving.png
├── docs/
│   ├── daily/
│   ├── weekly/
│   ├── CONFIGURATION_AND_RUN_OUTPUTS.md
│   ├── IMAGE_IO_PREPROCESSING_EVALUATION.md
│   ├── ROTATION_RIGID_TRANSFORMS.md
│   ├── SIMILARITY_AFFINE_WARPING.md
│   └── TRANSFORM_CONVENTIONS.md
├── outputs/
├── scripts/
│   ├── day01_demo.py
│   ├── day02_rigid_demo.py
│   ├── day03_warping_demo.py
│   ├── day04_io_preprocessing_evaluation_demo.py
│   ├── run_experiment.py
│   └── zip_project.py
├── src/
│   └── image_registration/
├── tests/
├── .gitattributes
├── .gitignore
├── pyproject.toml
└── requirements.txt
```

## Environment setup

Python 3.12 is recommended.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Verify the environment:

```powershell
pip check
pytest -v
```

The current project should report:

```text
66 passed
```

## Run the Week 1 end-to-end smoke test

```powershell
python scripts/run_experiment.py --config configs/day05_week01_smoke_test.yaml
```

The runner executes:

```text
load
  -> validate
  -> preprocess
  -> apply configured Moving -> Fixed transform
  -> warp
  -> evaluate
  -> visualize
  -> save structured results
```

The provided smoke test uses:

```text
Fixed image:   data/samples/week01/fixed.png
Moving image:  data/samples/week01/moving.png
Transform:     known similarity transform
Seed:          42
```

A run is stored under:

```text
outputs/<experiment_name>_<config_hash>/
```

Each run contains:

```text
figures/
metadata.json
metrics.csv
metrics.json
resolved_config.yaml
run.log
run_summary.json
timing.json
transform.json
```

See `docs/CONFIGURATION_AND_RUN_OUTPUTS.md` for the configuration and output schema.

## Daily demonstrations

Day 1, translation and homogeneous-coordinate checks:

```powershell
python scripts/day01_demo.py --config configs/day01_translation_demo.yaml
```

Day 2, rotation and rigid-transform checks:

```powershell
python scripts/day02_rigid_demo.py --config configs/day02_rigid_demo.yaml
```

Day 3, similarity, affine, image warping, and interpolation:

```powershell
python scripts/day03_warping_demo.py --config configs/day03_warping_demo.yaml
```

Day 4, image loading, preprocessing, evaluation, and visualization:

```powershell
python scripts/day04_io_preprocessing_evaluation_demo.py --config configs/day04_io_preprocessing_evaluation_demo.yaml
```

## Data and generated outputs

Small sample images required for tests and demonstrations are stored under `data/samples/` and are tracked by Git.

Large raw or processed datasets should not be committed. The `.gitignore` file excludes `data/raw/`, `data/processed/`, and generated `outputs/` while allowing directory placeholders.

## Documentation

Technical notes are available under `docs/`. Daily and weekly summaries record implementation decisions, experiments, validation results, and progress through the internship plan.

## Create a lightweight project archive

```powershell
python scripts/zip_project.py
```

The archive contains source code, tests, configurations, documentation, and small sample data. Virtual environments, caches, generated outputs, Git internals, build artifacts, and large datasets are excluded.

## License

No open-source license has been selected yet. Add an appropriate license before distributing the repository under open-source terms.
