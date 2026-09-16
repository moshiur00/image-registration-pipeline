# Image Registration Pipeline

A modular and reproducible Python framework for developing, testing, and benchmarking image-registration methods on monomodal and multimodal image pairs.

The project is organized as an eight-week implementation and evaluation plan. Week 1 established the common transformation, warping, preprocessing, evaluation, configuration, logging, and testing infrastructure. Week 2 completed the controlled ground-truth benchmark. Week 3 now contains phase-correlation baselines, controlled robustness evaluation, ECC translation and rigid registration, affine ECC, and coarse-to-fine multiresolution refinement.

## Current status

**Week 1: Registration Foundations and Pipeline Skeleton**  
**Status: Complete, 5 of 5 working days**

**Week 2: Controlled Dataset and Ground-Truth Benchmark Design**  
**Status: Complete, 5 of 5 working days**

**Week 3: Monomodal Intensity and Frequency-Domain Baselines**  
**Status: Day 5 implemented, local validation pending**

**Current automated test suite: 242 tests**  
**With the full project dependencies installed, all 242 tests are expected to run**

Automatic transform estimation is active. Week 3 Day 1 adds a translation-only phase-correlation method. Day 2 adds 43 controlled robustness evaluations across Gaussian noise, Gaussian blur, partial overlap, translation magnitude, subpixel shifts, and Hanning-window comparisons. Day 3 adds ECC translation and rigid registration with identity and phase-correlation initialization. Day 4 adds affine ECC and coarse-to-fine image pyramids with coordinate-correct transform transfer between levels. Day 5 integrates the supported monomodal baselines into one standardized 14-case, 24-registration comparison with tracked summaries and representative success/failure figures.

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
- Compact tracked report snapshots under `reports/` for later technical-report generation
- Progress registry linking completed days to narrative and quantitative summaries

### Week 3 automatic registration

- OpenCV phase-correlation translation estimator
- Explicit Moving -> Fixed phase-correlation direction
- Optional Hanning window before frequency-domain estimation
- Optional mean subtraction
- Subpixel translation estimates with phase-response diagnostics
- Standard `RegistrationResult` integration
- Estimation, warping, and total runtime measurement
- Safe failure records for invalid or low-information input
- Optional minimum phase-response threshold
- Transparent NumPy FFT cross-power correlation surface for diagnostics
- Clean 12-case translation validation using exact Week 2 ground truth
- Integer and subpixel translation-error measurement
- NCC comparison before and after registration
- CSV, JSON, summary, and representative visual outputs
- Fixed, moving, registered, overlay, checkerboard, difference, and correlation-surface figures
- Controlled Gaussian-noise robustness sweep
- Controlled Gaussian-blur robustness sweep
- Restricted-field-of-view overlap sweep with measured fixed-space overlap
- Increasing translation-magnitude sweep
- Subpixel-shift sensitivity sweep
- Hanning window on/off comparison under clean and stressed conditions
- Robustness CSV/JSON outputs and per-sweep summary statistics
- Error-versus-severity and response-versus-severity plots
- Representative severe-noise, severe-blur, and extreme-overlap case folders
- ECC translation registration
- ECC rigid registration using Euclidean motion
- Identity and phase-correlation ECC initialization
- Explicit conversion of OpenCV ECC output into the project Moving -> Fixed convention
- Configurable ECC iteration limit, termination tolerance, Gaussian filter size, and interpolation
- Final ECC objective, runtime, success status, and failure reason recording
- Ground-truth mean TRE, centered translation-parameter error, and rigid rotation error
- ECC validation under clean, contrast-change, and illumination-gradient conditions
- Controlled challenging rigid case demonstrating initialization sensitivity
- TRE, runtime, and NCC comparison plots for ECC
- Integrated Day 5 monomodal baseline benchmark across camera, coins, and moon source images
- Standardized 14-case, 24-registration result table across supported translation, rigid, and affine models
- Direct phase-correlation versus ECC-translation comparison on identical translation cases
- Single-resolution versus multiresolution affine ECC comparison retained in the integrated benchmark
- Standardized optimizer status, geometric tolerance status, TRE, parameter error, similarity, response/ECC, and runtime fields
- Representative alpha overlays, checkerboards, absolute-difference images, and RGB edge overlays
- Aggregated method, condition, and motion-model summaries for later technical-report generation
- ECC affine registration using general 2D affine motion
- Supplied-transform ECC initialization for multilevel refinement
- Coarse-to-fine image-pyramid construction
- Configurable pyramid scales and Gaussian pre-smoothing
- Homogeneous transform scaling between pyramid coordinate systems
- Multiresolution ECC with per-level convergence diagnostics
- Affine linear-component error in addition to TRE and translation error
- Single-resolution versus multiresolution affine comparison
- Pyramid-level visualization and capture-range case analysis

## Future planned tasks

| Week | Planned work | Main outcome |
|---|---|---|
| Week 2 | Controlled dataset and ground-truth benchmark design | Complete: integrated 60-case benchmark with reproducibility validation |
| Week 3 | Monomodal intensity and frequency-domain baselines | In progress: Days 1 to 4 implemented; integrated baseline benchmark remains |
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
│   ├── week02_day05_integrated_benchmark.yaml
│   ├── week03_day01_phase_correlation.yaml
│   ├── week03_day02_phase_robustness.yaml
│   └── week03_day03_ecc_translation_rigid.yaml
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
│   ├── PHASE_CORRELATION.md
│   ├── PHASE_CORRELATION_ROBUSTNESS.md
│   ├── ECC_REGISTRATION.md
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
│   ├── week03_day01_phase_correlation_demo.py
│   ├── week03_day02_phase_robustness.py
│   ├── week03_day03_ecc_demo.py
│   ├── run_experiment.py
│   ├── cleanup_obsolete_files.py
│   └── zip_project.py
├── reports/
│   ├── progress_registry.json
│   ├── week01_summary.json
│   ├── week02_summary.json
│   ├── week03_day01_phase_correlation.json
│   ├── week03_day02_phase_robustness.json
│   └── week03_day03_ecc_translation_rigid.json
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

The current suite contains 242 tests. With SimpleITK installed, all 242 tests are expected to run.

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

Week 3 Day 1, phase-correlation translation estimation:

```powershell
python scripts/week03_day01_phase_correlation_demo.py --config configs/week03_day01_phase_correlation.yaml
```

The validation generates 12 clean translation-only cases from the tracked `camera.png` source image. Ground truth is used only for evaluation. The estimator records the Moving -> Fixed translation, phase response, runtime, translation-vector error, NCC before and after registration, success status, and representative frequency-domain and image-alignment figures.

Week 3 Day 2, phase-correlation robustness:

```powershell
python scripts/week03_day02_phase_robustness.py --config configs/week03_day02_phase_robustness.yaml
```

The robustness script performs one-factor sweeps for Gaussian noise, Gaussian blur, partial overlap, translation magnitude, and subpixel displacement. It also compares Hanning windowing on and off under selected clean and stressed conditions. Results include exact ground-truth error, phase response, actual geometric overlap, NCC before and after registration, runtime, CSV/JSON tables, summary statistics, plots, and representative severe cases.

Week 3 Day 3, ECC translation and rigid registration:

```powershell
python scripts/week03_day03_ecc_demo.py --config configs/week03_day03_ecc_translation_rigid.yaml
```

The ECC script runs 12 controlled base cases with both identity and phase-correlation initialization, for 24 registrations. It records final ECC, mean TRE, translation-parameter error, rigid rotation error, NCC before and after registration, runtime, optimizer success, failure reason, CSV/JSON tables, plots, and representative cases.

Week 3 Day 4, affine ECC and multiresolution pyramids:

```powershell
python scripts/week03_day04_ecc_affine_multiresolution.py --config configs/week03_day04_ecc_affine_multiresolution.yaml
```

The Day 4 script compares single-resolution and three-level coarse-to-fine affine ECC on nine controlled affine cases. Both strategies use phase-correlation initialization so the comparison isolates the contribution of multiresolution refinement. Results include TRE, centered translation error, affine linear error, NCC before and after registration, final ECC, runtime, per-level diagnostics, CSV/JSON tables, plots, representative cases, a pyramid visualization, and a tracked report snapshot.

Week 3 Day 5, integrated monomodal baseline benchmark:

```powershell
python scripts/week03_day05_integrated_baselines.py --config configs/week03_day05_integrated_baselines.yaml
```

The Day 5 script consolidates the Week 3 baselines across 14 controlled cases and 24 registrations using the tracked camera, coins, and moon images. Phase correlation and ECC translation are compared on the same translation cases. ECC rigid is evaluated on rigid cases, while single-resolution and multiresolution ECC are evaluated on affine cases. The script writes standardized CSV/JSON results, an aggregated method table, success/runtime/TRE plots, representative alpha/checkerboard/difference/edge overlays, and a tracked compact report snapshot.

## Data and generated outputs

Small sample images required for tests and demonstrations are stored under `data/samples/` and are tracked by Git.

Large raw or processed datasets should not be committed. The `.gitignore` file excludes `data/raw/`, `data/processed/`, and generated `outputs/` while allowing directory placeholders.

Full experiment artifacts remain under `outputs/` and are intentionally local. Compact quantitative summaries are stored under `reports/` and are tracked with the project so later report generation retains the key validated results.

## Documentation

Technical notes are available under `docs/`. Daily and weekly summaries record implementation decisions, experiments, validation results, and progress through the internship plan. `reports/progress_registry.json` provides a machine-readable index linking completed days to compact quantitative snapshots and narrative summaries.

## Apply project cleanup after extracting an update

When an update retires an old file, extracting a ZIP does not remove the old local copy automatically. Run:

```powershell
python scripts/cleanup_obsolete_files.py
```

The cleanup currently removes an obsolete `scripts/scripts.txt` file and generated `src/image_registration_pipeline.egg-info` directory if either exists.

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

The archive contains source code, tests, configurations, documentation, compact report snapshots, and small sample data. Virtual environments, caches, generated outputs, Git internals, build artifacts, and large datasets are excluded.

## License

No open-source license has been selected yet. Add an appropriate license before distributing the repository under open-source terms.
