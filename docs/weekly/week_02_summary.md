# Week 2 Summary

## Controlled Dataset and Ground-Truth Benchmark Design

**Status:** Complete  
**Completed days:** 5 of 5

## Weekly objective

Build a deterministic benchmark layer that produces monomodal and simulated multimodal image pairs with known geometry, controlled degradations, overlap information, manifests, and documented real-data subsets.

## Progress by day

| Day | Focus | Status |
|---|---|---|
| Day 6, Week 2 Day 1 | Synthetic pair generator and exact ground truth | Complete |
| Day 7, Week 2 Day 2 | Controlled degradations and partial overlap | Complete |
| Day 8, Week 2 Day 3 | Simulated multimodal data and difficulty tiers | Complete |
| Day 9, Week 2 Day 4 | Real datasets, manifests, and integrity checks | Complete |
| Day 10, Week 2 Day 5 | Integrated benchmark generation and validation | Complete |

## Day 1 completed foundation

- deterministic random sampling from configured parameter ranges;
- translation, rigid, similarity, and affine ground-truth families;
- exact Moving -> Fixed and Fixed -> Moving matrices;
- synthetic moving-image generation from the inverse transformation;
- deterministic control points;
- numerical ground-truth round-trip verification;
- structured ground-truth JSON output;
- experiment manifest generation;
- tests for deterministic sampling and transform correctness.

## Day 2 completed foundation

- deterministic Gaussian and impulse noise;
- Gaussian blur;
- contrast and gamma intensity changes;
- configurable illumination gradients;
- rectangular occlusion and visibility masks;
- transformed geometric support masks;
- configurable restricted field-of-view masks;
- moving-space valid-mask intersection;
- valid-overlap masks in fixed coordinates;
- overlap-fraction measurement;
- configuration-driven one-factor degradation examples;
- structured degradation and overlap metadata.

## Day 3 completed foundation

- synthetic intensity inversion;
- nonlinear gamma modality mapping;
- monotonic histogram remapping;
- smooth multiplicative bias fields;
- edge-emphasized representations;
- deterministic signal-dependent modality-specific noise;
- easy, moderate, and hard difficulty tiers;
- validation of non-overlapping severity intervals;
- similarity-transform difficulty sampling with translation, rotation, and scale variation;
- tier-dependent modality-noise severity;
- intensity histograms within valid overlap;
- joint histograms for aligned monomodal and simulated multimodal pairs;
- structured tier and modality metadata.

## Day 4 completed foundation

- small tracked real-image source subset using `scikit-image` sample data;
- general real-source manifest with shape, data type, source, and SHA-256 metadata;
- RIRE training_001 CT and MR-T1 preparation configuration;
- preferred SimpleITK-compatible MHA workflow with fixed CT and moving MR-T1;
- medical-volume metadata validation for size, spacing, origin, direction, and pixel type;
- SHA-256 validation for real medical volumes;
- support for a local Zenodo `data.zip` archive with selective extraction of the two required MHA files;
- optional streamed Zenodo download with retries;
- legacy original-format RIRE parser retained as a local fallback;
- real multimodal pair manifest generation;
- dataset cards and source documentation;
- integrity checks for missing files, duplicate IDs, image decoding, dimensions, hashes, modality labels, medical metadata, and legacy voxel counts;
- tests that use local fixtures and do not require network access.

## Day 5 completed foundation

- integrated benchmark generator using real grayscale source images with exact synthetic ground truth;
- 60 benchmark cases with 20 easy, 20 moderate, and 20 hard samples;
- balanced monomodal and simulated multimodal coverage;
- translation, rigid, similarity, and affine transformation families;
- tier-dependent affine shear sampling;
- integrated clean, noise, blur, gamma, illumination, occlusion, and restricted field-of-view cases;
- valid-overlap and effective evaluation masks;
- exact control-point round-trip verification;
- per-case SHA-256 file hashes;
- deterministic benchmark plan and dataset fingerprints;
- automatic comparison with the previous run from the same output directory;
- JSON benchmark manifest and CSV benchmark index;
- representative visual gallery;
- references to the prepared general real-image and RIRE multimodal manifests.

## Current validation

The full project now contains 172 automated tests when all dependencies are available. In the validation environment, 168 tests passed and 4 SimpleITK-dependent tests were skipped because SimpleITK was unavailable there.

The integrated benchmark was generated twice with seed 42. Both runs produced the same dataset fingerprint:

```text
7f5e0730a150ef0a89dcc3ad459d72cea99c392f5e91ff083d1bf5d1a5660c15
```

The second run reported a reproducibility `MATCH`.

The final Week 2 benchmark contains 60 cases: 20 easy, 20 moderate, and 20 hard. It contains 30 monomodal and 30 simulated multimodal cases, four transformation families, seven degradation categories including clean baseline cases, and 15 restricted field-of-view cases.

## Week 2 outcome

Week 2 is complete. The project now has deterministic synthetic benchmark data with known transformations, controlled appearance changes, overlap information, multimodal variants, non-overlapping difficulty tiers, documented real datasets, dataset manifests, integrity checks, and final reproducibility validation.

This benchmark is ready to support Week 3 phase-correlation and ECC experiments.
