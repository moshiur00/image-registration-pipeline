# Integrated Week 2 Benchmark

## Purpose

Week 2 Day 5 combines the synthetic ground-truth, degradation, overlap, multimodal, difficulty-tier, and real-data preparation work into one reproducible benchmark generator.

The integrated benchmark is designed to become the common test set for the registration methods introduced from Week 3 onward.

## Required benchmark coverage

The generator creates 60 controlled synthetic registration cases:

- 20 easy cases;
- 20 moderate cases;
- 20 hard cases.

Each tier contains both monomodal and simulated multimodal cases. The case plan cycles through translation, rigid, similarity, and affine transformations, multiple appearance degradations, and restricted field-of-view cases.

## Source images

The synthetic benchmark uses the tracked real grayscale source subset prepared on Week 2 Day 4:

- `camera.png`;
- `coins.png`;
- `moon.png`.

These images provide realistic image content while the benchmark generator preserves exact synthetic ground truth.

The prepared RIRE CT and MR-T1 manifest is referenced separately as the real multimodal dataset for later registration experiments. The integrated synthetic benchmark does not modify the RIRE volumes.

## Ground-truth geometry

Every case stores the exact Moving -> Fixed transform and its inverse.

The benchmark cycles through:

- translation;
- rigid;
- similarity;
- affine.

The easy, moderate, and hard tiers use non-overlapping ranges for translation, rotation, scale deviation, affine shear, and modality noise.

Control points are transformed through the exact geometry and then mapped back. The benchmark validator requires the maximum round-trip error to remain below numerical tolerance.

## Appearance factors

The benchmark cycles through the following controlled degradations:

- no additional degradation;
- Gaussian noise;
- impulse noise;
- Gaussian blur;
- gamma change;
- illumination gradient;
- rectangular occlusion.

The severity increases by difficulty tier.

## Simulated multimodal cases

Half of the cases in each tier are monomodal and half are simulated multimodal.

The multimodal mappings include:

- intensity inversion;
- nonlinear gamma mapping;
- histogram remapping;
- multiplicative bias field;
- edge-emphasized representation.

The geometry is unchanged by the modality mapping.

## Partial overlap

Every fourth case receives a restricted field of view. This produces 15 partial-overlap cases across the complete 60-case benchmark.

Each case records:

- geometric valid-overlap fraction;
- visibility fraction in moving coordinates;
- effective evaluation fraction after combining geometry, field of view, and occlusion visibility.

This keeps geometric overlap, occlusion, and appearance changes as separate controlled factors.

## Output structure

The benchmark is generated under:

```text
outputs/week02_day05_integrated_benchmark/
```

Main files:

```text
benchmark_manifest.json
benchmark_index.csv
benchmark_summary.json
representative_gallery.png
resolved_config.yaml
```

Each case directory contains:

```text
fixed.png
moving.png
ground_truth_registered.png
valid_overlap_fixed.png
effective_evaluation_mask_fixed.png
metadata.json
```

## Reproducibility

The case plan is deterministic from the configured seed. The final manifest includes SHA-256 digests for generated case files and a dataset fingerprint over all benchmark records.

If the benchmark is generated again in the same output directory with the same configuration and source files, the script compares the new dataset fingerprint with the previous run and reports `MATCH` or `MISMATCH`.

## Run command

```powershell
python scripts/week02_day05_generate_benchmark.py --config configs/week02_day05_integrated_benchmark.yaml
```

Running the same command a second time performs the cross-run fingerprint check automatically.

## Completion criteria

Week 2 is complete when the integrated benchmark satisfies all of the following:

- at least 20 cases exist in each difficulty tier;
- both monomodal and simulated multimodal cases are present;
- at least three transformation families are represented;
- at least four non-empty degradation types are represented;
- every case has exact ground truth and a valid-overlap mask;
- control-point verification passes;
- the same seed and configuration reproduce the same benchmark fingerprint;
- the general real-image source manifest and real multimodal RIRE manifest are available for later experiments.
