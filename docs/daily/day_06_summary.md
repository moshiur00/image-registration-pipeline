# Day 6 Summary

**Week:** 2 - Controlled Dataset and Ground-Truth Benchmark Design  
**Week 2 day:** 1 of 5  
**Status:** Complete

## Objective

Build the deterministic synthetic-pair foundation for Week 2. Every generated pair must begin from an explicit Moving -> Fixed ground-truth transformation so later registration algorithms can be evaluated against known geometry.

## Work completed

1. Added `src/image_registration/synthetic.py`.
2. Added `GroundTruthTransform` for storing sampled parameters, the Moving -> Fixed matrix, and its Fixed -> Moving inverse.
3. Added `SyntheticPair` for keeping fixed and moving images together with exact point correspondences.
4. Added deterministic parameter sampling based on NumPy random generators.
5. Added sampling for translation, rigid, similarity, and affine transformation families.
6. Added image-center handling for rigid, similarity, and affine sampling.
7. Added an interpretable affine sampler using rotation, anisotropic scale, shear, and translation.
8. Added synthetic moving-image generation using the inverse of the stored Moving -> Fixed transformation.
9. Added deterministic control points and Moving/Fixed point correspondence storage.
10. Added per-point round-trip error calculation for ground-truth verification.
11. Added `configs/week02_day01_synthetic_ground_truth.yaml`.
12. Added `scripts/week02_day01_synthetic_demo.py`.
13. Added `docs/SYNTHETIC_GROUND_TRUTH_BENCHMARK.md`.
14. Added automated tests covering deterministic sampling, parameter ranges, transform inversion, control-point correspondence, image generation, and validation failures.
15. Removed the obsolete `scripts/scripts.txt` file from the maintained project tree.
16. Added `scripts/cleanup_obsolete_files.py` so an existing local project can remove obsolete files after extracting this update.

## Ground-truth convention

```text
Stored transform: Moving -> Fixed
Synthetic generation: Fixed -> Moving using inverse ground truth
Registration target: Moving -> Fixed using stored ground truth
```

This keeps synthetic data generation consistent with the registration convention established in Week 1.

## Day 1 output

The demonstration generates one deterministic example for each transformation family:

```text
translation
rigid
similarity
affine
```

Each pair stores:

```text
moving image
ground-truth registered image
ground_truth.json
control-point correspondence
forward and inverse transformation matrices
```

A top-level manifest records the experiment seed and all generated transformation records.

## Scope intentionally deferred

The following Week 2 tasks are not part of Day 1:

```text
noise and blur
intensity and illumination changes
occlusion
partial overlap and overlap masks
synthetic multimodal mappings
difficulty tiers
real-data preparation
full benchmark generation
```

These will be added in Days 2 to 5 after the geometric ground truth is verified.

## Validation

The full project suite for this update contains 83 tests. Validation in the current environment produced:

```text
82 passed, 1 skipped
```

The skipped test is the existing SimpleITK metadata test because SimpleITK is not installed in the validation environment. The 17 Week 2 Day 1 synthetic-ground-truth tests passed.

The Day 1 demonstration was executed twice with the same seed and configuration. Generated file hashes were identical across both runs.
