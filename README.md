# Image Registration Pipeline

A modular and reproducible Python framework for developing, testing, and benchmarking image-registration methods on monomodal and multimodal image pairs.

The project is organized as an eight-week implementation and evaluation plan. Week 1 established the common transformation, warping, preprocessing, evaluation, configuration, logging, and testing infrastructure. Week 2 completed the controlled ground-truth benchmark that will be used to evaluate the registration algorithms planned for later weeks.

## Current status

**Week 1: Registration Foundations and Pipeline Skeleton**  
**Status: Complete, 5 of 5 working days**

**Week 2: Controlled Dataset and Ground-Truth Benchmark Design**  
**Status: Complete, 5 of 5 working days**

**Current automated test suite: 172 tests**  
**With the full project dependencies installed, all 172 tests are expected to run**

Automatic transform estimation has not started yet. Week 2 has established deterministic synthetic pairs, known ground truth, controlled appearance changes, overlap information, multimodal variants, real-data manifests, and a final integrated benchmark so the registration methods introduced in Week 3 can be measured objectively from the beginning.

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

### Week 2 benchmark foundation

- Deterministic synthetic transform sampling from configured ranges
- Translation, rigid, similarity, and affine ground-truth families
- Exact Moving -> Fixed and Fixed -> Moving matrices
- Synthetic moving-image generation from inverse ground truth
- Deterministic control points with verified correspondence
- Ground-truth JSON records and experiment manifest output
- Reproducible generation from a fixed random seed
- Controlled Gaussian and impulse noise
- Gaussian blur, contrast, gamma, and illumination changes
- Rectangular occlusion with an explicit visibility mask
- Transformed-support masks for geometric validity
- Restricted field-of-view masks for partial-overlap cases
- Valid-overlap masks mapped into fixed-image coordinates
- Overlap-fraction measurement and structured case metadata
- Synthetic multimodal intensity inversion
- Nonlinear gamma modality mapping
- Monotonic histogram remapping
- Smooth multiplicative bias fields
- Edge-emphasized modality representations
- Deterministic signal-dependent modality noise
- Non-overlapping easy, moderate, and hard difficulty tiers
- Difficulty sampling for translation magnitude, rotation magnitude, scale deviation, and modality noise
- Intensity-histogram and joint-histogram outputs within valid overlap
- Small tracked real-image source subset using `scikit-image` sample data
- Dataset manifests with IDs, paths, shapes, data types, SHA-256 digests, modality labels, and ground-truth status
- RIRE training_001 CT and MR-T1 preparation configuration
- Preferred SimpleITK-compatible MHA workflow using fixed CT and moving MR-T1
- Medical-volume metadata validation for size, spacing, origin, direction, and pixel type
- SHA-256 validation for real medical volumes
- Support for a local Zenodo `data.zip` archive that extracts only the two required MHA files
- Optional streamed Zenodo download with retries
- Legacy RIRE raw-header and big-endian voxel support retained as a local fallback
- Dataset integrity checks for missing files, duplicate IDs, shape mismatches, hashes, modality labels, and medical metadata
- Dataset cards for the general real-image subset and RIRE multimodal subset
- Integrated benchmark generator with 20 easy, 20 moderate, and 20 hard cases
- Balanced 30 monomodal and 30 simulated multimodal cases
- Translation, rigid, similarity, and affine families in one benchmark
- Tier-dependent affine shear sampling
- Integrated degradation, occlusion, and restricted field-of-view factors
- Valid-overlap and effective evaluation masks for every case
- Control-point ground-truth verification for every case
- Per-case SHA-256 file hashes and a complete dataset fingerprint
- Repeat-run fingerprint comparison for reproducibility validation
- JSON benchmark manifest, CSV index, and representative visual gallery

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
| Week 2 | Controlled dataset and ground-truth benchmark design | Complete: integrated 60-case benchmark with reproducibility validation |
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
│   ├── day05_week01_smoke_test.yaml
│   ├── week02_day01_synthetic_ground_truth.yaml
│   ├── week02_day02_degradations_overlap.yaml
│   ├── week02_day03_multimodal_difficulty.yaml
│   ├── week02_day04_real_datasets.yaml
│   └── week02_day05_integrated_benchmark.yaml
├── data/
│   ├── manifests/
│   │   └── general_real_sources.json
│   ├── raw/
│   ├── processed/
│   └── samples/
│       ├── week01/
│       │   ├── fixed.png
│       │   └── moving.png
│       └── week02_real_general/
│           ├── camera.png
│           ├── coins.png
│           └── moon.png
├── docs/
│   ├── daily/
│   ├── weekly/
│   ├── datasets/
│   ├── CONFIGURATION_AND_RUN_OUTPUTS.md
│   ├── CONTROLLED_DEGRADATIONS_PARTIAL_OVERLAP.md
│   ├── SIMULATED_MULTIMODAL_DIFFICULTY_TIERS.md
│   ├── IMAGE_IO_PREPROCESSING_EVALUATION.md
│   ├── ROTATION_RIGID_TRANSFORMS.md
│   ├── SIMILARITY_AFFINE_WARPING.md
│   ├── SYNTHETIC_GROUND_TRUTH_BENCHMARK.md
│   └── TRANSFORM_CONVENTIONS.md
├── outputs/
├── scripts/
│   ├── day01_demo.py
│   ├── day02_rigid_demo.py
│   ├── day03_warping_demo.py
│   ├── day04_io_preprocessing_evaluation_demo.py
│   ├── week02_day01_synthetic_demo.py
│   ├── week02_day02_degradations_overlap_demo.py
│   ├── week02_day03_multimodal_difficulty_demo.py
│   ├── week02_day04_prepare_real_data.py
│   ├── week02_day05_generate_benchmark.py
│   ├── run_experiment.py
│   ├── cleanup_obsolete_files.py
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

The current suite contains 172 tests. With SimpleITK installed, all 172 tests are expected to run.

## Prepare the Week 2 Day 4 real-data subsets

Prepare the tracked general real-image subset and validate any already available RIRE data:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml
```

The preferred RIRE input is a local SimpleITK-compatible pair:

```text
data/raw/rire/training_001/mha/
├── training_001_ct.mha
└── training_001_mr_T1.mha
```

If you download the Zenodo `data.zip` archive manually, save it as:

```text
data/raw/rire/training_001/archives/zenodo_data.zip
```

The normal preparation command will verify the archive and extract only the required CT and MR-T1 MHA files. An optional network download is also available:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml --download-zenodo
```

Large medical data remains excluded from Git and project-sharing ZIP files.

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

Week 2 Day 1, deterministic synthetic pairs and exact ground truth:

```powershell
python scripts/week02_day01_synthetic_demo.py --config configs/week02_day01_synthetic_ground_truth.yaml
```

The demonstration creates one translation, rigid, similarity, and affine pair from seed 42. Each pair stores the sampled parameters, Moving -> Fixed matrix, inverse matrix, control-point correspondences, and numerical round-trip error. Generated files are written under `outputs/` and are not committed to Git.

Week 2 Day 2, controlled degradations and partial overlap:

```powershell
python scripts/week02_day02_degradations_overlap_demo.py --config configs/week02_day02_degradations_overlap.yaml
```

The demonstration keeps one known rigid geometry fixed while creating separate Gaussian-noise, impulse-noise, blur, contrast, gamma, illumination, occlusion, and restricted-field-of-view cases. It stores visibility masks, valid-overlap masks, overlap fractions, degradation metadata, and the exact ground-truth transform under `outputs/`.

## Data and generated outputs

Small sample images required for tests and demonstrations are stored under `data/samples/` and are tracked by Git.

Large raw or processed datasets should not be committed. The `.gitignore` file excludes `data/raw/`, `data/processed/`, and generated `outputs/` while allowing directory placeholders.

## Documentation

Technical notes are available under `docs/`. Daily and weekly summaries record implementation decisions, experiments, validation results, and progress through the internship plan.

## Apply project cleanup after extracting an update

When an update retires an old file, extracting a ZIP does not remove the old local copy automatically. Run:

```powershell
python scripts/cleanup_obsolete_files.py
```

For this update the cleanup removes the obsolete `scripts/scripts.txt` file if it still exists.

## Generate the final Week 2 benchmark

Run the integrated benchmark generator:

```powershell
python scripts/week02_day05_generate_benchmark.py --config configs/week02_day05_integrated_benchmark.yaml
```

The generator creates 60 cases: 20 easy, 20 moderate, and 20 hard. It records exact ground truth, modality class, degradation, overlap, effective evaluation masks, file hashes, and a dataset fingerprint.

Run the same command a second time to compare the new dataset fingerprint with the previous run. With unchanged inputs and configuration, the repeat check should report `MATCH`.

Main outputs are written under:

```text
outputs/week02_day05_integrated_benchmark/
```

## Create a lightweight project archive

```powershell
python scripts/zip_project.py
```

The archive contains source code, tests, configurations, documentation, and small sample data. Virtual environments, caches, generated outputs, Git internals, build artifacts, and large datasets are excluded.

## License

No open-source license has been selected yet. Add an appropriate license before distributing the repository under open-source terms.
