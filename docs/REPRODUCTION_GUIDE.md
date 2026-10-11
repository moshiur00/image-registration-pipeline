# Reproduction and Project Operations Guide

This document contains the operational commands that were intentionally moved out of the main README. The README is kept focused on the research objective, methodology, validated findings, and portfolio-level project overview.

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

Validate the environment:

```powershell
pip check
pytest -v
```

The completed Week 5 repository collects 364 tests. The target Windows validation result is `364 passed in 4.56s`.

## Real-data preparation

Prepare the tracked general real-image subset and validate any locally available RIRE data:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml
```

The preferred RIRE input pair is:

```text
data/raw/rire/training_001/mha/
├── training_001_ct.mha
└── training_001_mr_T1.mha
```

If the Zenodo `data.zip` archive is downloaded manually, store it as:

```text
data/raw/rire/training_001/archives/zenodo_data.zip
```

The preparation command verifies the archive and extracts only the required CT and MR-T1 MHA files. Optional streamed download support is available with:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml --download-zenodo
```

Large medical data is intentionally excluded from Git and lightweight project archives.

## Week 1 smoke test

Run the end-to-end pipeline smoke test:

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

The provided smoke test uses the tracked Week 1 sample pair, a known similarity transform, and seed 42.

Typical run output:

```text
outputs/<experiment_name>_<config_hash>/
├── figures/
├── metadata.json
├── metrics.csv
├── metrics.json
├── resolved_config.yaml
├── run.log
├── run_summary.json
├── timing.json
└── transform.json
```

See `docs/CONFIGURATION_AND_RUN_OUTPUTS.md` for the configuration and output schema.

## Experiment command reference

### Week 1

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

### Week 2

Day 6, deterministic synthetic ground-truth pairs:

```powershell
python scripts/week02_day01_synthetic_demo.py --config configs/week02_day01_synthetic_ground_truth.yaml
```

Day 7, controlled degradations and partial overlap:

```powershell
python scripts/week02_day02_degradations_overlap_demo.py --config configs/week02_day02_degradations_overlap.yaml
```

Day 8, simulated multimodal mappings and difficulty tiers:

```powershell
python scripts/week02_day03_multimodal_difficulty_demo.py --config configs/week02_day03_multimodal_difficulty.yaml
```

Day 9, real-data preparation and integrity validation:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml
```

Day 10, integrated 60-case benchmark generation:

```powershell
python scripts/week02_day05_generate_benchmark.py --config configs/week02_day05_integrated_benchmark.yaml
```

The Week 2 final generator creates 20 easy, 20 moderate, and 20 hard cases. Run the same command again with unchanged inputs to verify that the dataset fingerprint reports `MATCH`.

### Week 3

Day 11, Phase Correlation:

```powershell
python scripts/week03_day01_phase_correlation_demo.py --config configs/week03_day01_phase_correlation.yaml
```

Day 12, Phase Correlation robustness:

```powershell
python scripts/week03_day02_phase_robustness.py --config configs/week03_day02_phase_robustness.yaml
```

Day 13, ECC translation and rigid registration:

```powershell
python scripts/week03_day03_ecc_demo.py --config configs/week03_day03_ecc_translation_rigid.yaml
```

Day 14, affine ECC and multiresolution:

```powershell
python scripts/week03_day04_ecc_affine_multiresolution.py --config configs/week03_day04_ecc_affine_multiresolution.yaml
```

Day 15, integrated monomodal baseline benchmark:

```powershell
python scripts/week03_day05_integrated_baselines.py --config configs/week03_day05_integrated_baselines.yaml
```

### Week 4

Day 16, ORB detection and descriptors:

```powershell
python scripts/week04_day01_orb_features.py --config configs/week04_day01_orb_features.yaml
```

Day 17, ORB matching:

```powershell
python scripts/week04_day02_orb_matching.py --config configs/week04_day02_orb_matching.yaml
```

Day 18, similarity RANSAC:

```powershell
python scripts/week04_day03_ransac_similarity.py --config configs/week04_day03_ransac_similarity.yaml
```

Day 19, affine RANSAC and robustness:

```powershell
python scripts/week04_day04_ransac_affine_robustness.py --config configs/week04_day04_ransac_affine_robustness.yaml
```

Day 20, integrated feature benchmark:

```powershell
python scripts/week04_day05_integrated_feature_baseline.py --config configs/week04_day05_integrated_feature_baseline.yaml
```

Optional SIFT Stage 1, detection and L2 matching:

```powershell
python scripts/week04_sift_stage01_features_matching.py --config configs/week04_sift_stage01_features_matching.yaml
```

Optional SIFT Stage 2, shared RANSAC registration:

```powershell
python scripts/week04_sift_stage02_ransac.py --config configs/week04_sift_stage02_ransac.yaml
```

Optional SIFT Stage 3, frozen ORB vs SIFT comparison:

```powershell
python scripts/week04_orb_vs_sift_comparison.py --config configs/week04_orb_vs_sift_comparison.yaml
```

### Week 5

Day 21, rigid Mattes Mutual Information:

```powershell
python scripts/week05_day01_mi_rigid.py --config configs/week05_day01_mi_rigid.yaml --overwrite
```

Day 22, rigid MI controlled validation study:

```powershell
python scripts/week05_day02_mi_rigid_study.py --config configs/week05_day02_mi_rigid_study.yaml --overwrite
```

Day 23, affine MI and multiresolution study:

```powershell
python scripts/week05_day03_mi_affine_multiresolution.py --config configs/week05_day03_mi_affine_multiresolution.yaml --overwrite
```

Day 24, real RIRE CT/MR-T1 rigid physical-space registration:

```powershell
python scripts/week05_day04_rire_physical_registration.py --config configs/week05_day04_rire_physical_registration.yaml --overwrite
```

Day 25, frozen integrated multimodal benchmark:

```powershell
python scripts/week05_day05_integrated_benchmark.py --config configs/week05_day05_integrated_benchmark.yaml --overwrite
```

## Result locations

Detailed experiment artifacts are written under local `outputs/` directories. These may include figures, CSV files, resolved configurations, optimizer traces, per-case JSON files, registered images, and logs.

Compact validated evidence is tracked under `reports/`. Human-readable methodology, findings, interpretations, limitations, and progress summaries are tracked under `docs/`.

The reporting split is intentional:

```text
outputs/   detailed local experiment evidence, not committed
reports/   compact machine-readable evidence, committed
docs/      narrative technical evidence, committed
```

## Cleanup after extracting repository updates

Extracting a project update over an existing repository does not remove obsolete local files. Run:

```powershell
python scripts/cleanup_obsolete_files.py
```

The cleanup utility removes known obsolete project artifacts when they are present, including the retired `PROJECT_MANIFEST.json`, `scripts/scripts.txt`, and generated `src/image_registration_pipeline.egg-info` paths.

## Create a lightweight project archive

```powershell
python scripts/zip_project.py
```

The archive includes source code, tests, configurations, documentation, compact reports, and small sample data. It excludes virtual environments, Git internals, caches, generated outputs, build artifacts, and large datasets.
