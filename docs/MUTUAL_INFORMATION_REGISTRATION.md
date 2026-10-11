# Mutual Information Registration

## Current status

Week 5 Days 21 through 25 are complete on the target Windows environment. The final Day 25 benchmark completed with 364 tests passed in 4.56s and the Week 5 configurations are frozen.

Day 24 target Windows validation recorded `358 passed in 4.59s`. Both configured real RIRE rigid MI variants completed successfully, returned plausible physical transforms, preserved metadata, and passed technical validation. TRE, Dice, and anatomical correctness remain unreported because verified RIRE landmarks or masks are not integrated. The latest Week 5 target validation is the completed Day 25 repository with `364 passed in 4.56s`.

## Purpose

Mutual Information is the primary multimodal registration objective in Week 5. The implementation uses SimpleITK Mattes Mutual Information for controlled 2D rigid and affine registration. The rigid path established transform direction, optimizer behavior, sampling, multiresolution settings, and geometric evaluation before the affine extension was added.

## Transform direction

The project convention remains:

`Moving -> Fixed`

SimpleITK registration evaluates a transform that maps fixed-domain physical points into the moving-image domain for resampling. The implementation therefore converts the final SimpleITK transform to a homogeneous physical matrix and inverts it before returning the project transform.

This distinction is explicit in the stored convergence information. Optimizer completion must not be interpreted as geometric correctness.

## Day 21 implementation

`src/image_registration/mutual_information.py` provides:

- 2D rigid registration with `Euler2DTransform`;
- Mattes Mutual Information;
- full, regular, or random metric sampling;
- fixed random seed support for sampled metrics;
- identity, geometry-based, or moments-based initialization;
- Regular Step Gradient Descent;
- optimizer scaling from physical shift;
- coarse-to-fine shrink factors and smoothing sigmas;
- iteration-level metric tracing;
- optimizer stop condition and valid metric-point diagnostics;
- preservation of SimpleITK spacing, origin, and direction in the `register_sitk` path;
- standard project `RegistrationResult` output;
- safe runtime failure records, including initialization failures.

## Validated Day 21 experiment

The experiment uses one monomodal reference and five simulated multimodal rigid cases. The multimodal mappings include intensity inversion, nonlinear gamma, histogram remapping, multiplicative bias, and an edge-emphasized representation.

Target Windows validation:

- full suite: `340 passed in 3.73s`;
- method execution success: 6 / 6;
- within geometric tolerance: 4 / 6;
- median TRE: 0.023 px.

Per-case TRE:

- camera monomodal rigid: 0.013 px, PASS;
- camera intensity inversion: 0.014 px, PASS;
- camera nonlinear gamma: 0.019 px, PASS;
- camera histogram remap: 318.731 px, CHECK;
- coins multiplicative bias: 0.027 px, PASS;
- moon edge-emphasized: 17.992 px, CHECK.

The histogram-remap case reached the maximum 200 optimizer iterations. The edge-emphasized case satisfied the gradient-magnitude stop condition but remained geometrically incorrect. Both results are preserved as evidence that optimizer completion does not guarantee correct registration.

## Scope boundary

Day 21 validates the initial 2D rigid MI path using controlled geometry. It does not claim performance on RIRE CT/MR-T1 data. Real medical-image physical-space registration and affine MI remain later Week 5 tasks.

Day 21 is frozen. Its thresholds are not loosened to convert the two CHECK cases into passes. Day 22 uses controlled validation evidence to study configuration sensitivity before the final Week 5 benchmark.

## Week 5 Day 22 controlled rigid MI study

Day 22 adds a validation-stage configuration study around the Day 21 rigid Mattes MI implementation. It is deliberately sequential one-factor-at-a-time rather than a large grid search.

The study compares initialization, histogram-bin count, sampling strategy, sampling percentage, and a small set of modality-safe preprocessing options. It also repeats random sampling across fixed seeds to quantify stochastic variability. The random seed is diagnostic only and is not selected by best-case accuracy.

Candidate ranking is restricted to the same rigid MI method on the same validation cases. The priority is geometric within-tolerance count, method execution success, median TRE, maximum TRE, then mean runtime. The selected factor values are combined and compared against the original Day 21 baseline before a configuration is frozen.

Local detailed evidence is written under `outputs/week05_day02_mi_rigid_study/`. The tracked compact snapshot is `reports/week05_day02_mi_rigid_study.json`. The frozen confirmation saves comparison figures, before/after joint histograms, metric traces, and per-case JSON records.

The five Day 22 cases are validation cases, not the final Week 5 test set. Histogram-remap and edge-emphasized failure modes are intentionally retained. Real RIRE CT/MR-T1 evidence remains a later Day 24 task.

## Validated Day 22 result

Target Windows validation:

- full suite: `347 passed in 8.65s`;
- baseline validation subset: 3 / 5 within tolerance;
- sequential composite candidate: 5 / 5 within tolerance;
- frozen confirmation: 5 / 5 within tolerance;
- frozen confirmation median TRE: 0.0173 px;
- frozen confirmation maximum TRE: 0.0950 px;
- frozen confirmation mean runtime: 1060.84 ms.

The frozen rigid MI configuration uses identity initialization, 32 histogram bins, full metric sampling, Gaussian smoothing with sigma 1.0, Regular Step Gradient Descent with learning rate 2.0, minimum step 0.001, 200 iterations, relaxation factor 0.5, gradient magnitude tolerance 0.0001, shrink factors `[4, 2, 1]`, and smoothing sigmas `[2.0, 1.0, 0.0]`.

Day 22 used a sequential one-factor-at-a-time validation study, not an exhaustive grid search. The selected settings are therefore frozen for later Week 5 work on this benchmark, not claimed as universally optimal. Day 23 should extend the MI path to affine registration without reopening the completed rigid-configuration study.

## Week 5 Day 23 affine MI implementation

Day 23 extends the shared Mattes MI module with `MutualInformationAffineRegistration` based on SimpleITK `AffineTransform(2)`. It keeps the validated Day 22 metric, optimizer, identity initialization, full sampling, and Gaussian smoothing choices frozen.

The controlled experiment compares affine single-resolution and affine multiresolution registration on seven known-ground-truth cases. The cases include monomodal affine geometry, intensity inversion, nonlinear gamma, multiplicative bias, histogram remapping, restricted field of view, and edge-emphasized appearance. A limited rigid multiresolution comparator is run only on selected true-affine cases as transform-model mismatch evidence.

Day 23 evaluates TRE, affine linear-component error, centered translation error, transform plausibility, optimizer status, final metric value, valid metric points, runtime, and failure reason. Optimizer success, plausibility, and geometric correctness remain separate.

Detailed local evidence is written under `outputs/week05_day03_mi_affine_multiresolution/`. The tracked compact snapshot is `reports/week05_day03_mi_affine_multiresolution.json`.

Target Windows Day 23 validation completed with `352 passed in 8.68s`. Single-resolution and multiresolution affine MI both reached 5 / 7 cases within tolerance. Multiresolution reduced median TRE from 0.1681 px to 0.0887 px, but produced no additional within-tolerance cases, so a capture-range expansion is not demonstrated by this controlled set. The partial-overlap and edge-emphasized failures are retained. The limited rigid comparator was 0 / 3 within tolerance on selected true-affine cases.


## Week 5 Day 24 real RIRE 3D implementation

Day 24 adds a separate 3D medical-image MI path in `src/image_registration/medical_mutual_information.py`. The 2D rigid and affine implementation remains unchanged.

The Day 24 path provides:

- rigid `Euler3DTransform` registration;
- physical-coordinate optimization with spacing, origin, and direction preserved;
- Moving -> Fixed 4 x 4 homogeneous output;
- geometry, identity, and moments initialization support at the implementation level;
- geometry initialization as the primary RIRE experiment path;
- identity initialization as a diagnostic comparator;
- the Day 22 Mattes MI and optimizer choices kept frozen where applicable;
- Gaussian preprocessing with sigma expressed in physical units;
- optimizer metric traces, stop conditions, valid metric points, and runtime;
- broad rigid-transform plausibility diagnostics in physical units;
- bidirectional physical field-of-view coverage diagnostics;
- registered-output geometry checks against the fixed CT grid;
- central x/y/z slice comparisons, overlays, and before/after joint histograms.

The configured RIRE pair is `training001_mr_t1_to_ct`, with CT fixed and MR-T1 moving. The script verifies the prepared manifest metadata and optionally verifies both SHA-256 hashes before registration.

The current RIRE manifest does not contain integrated verified landmarks or masks. Therefore Day 24 explicitly disables TRE and Dice and does not claim anatomical correctness. Optimizer completion, transform plausibility, metadata integrity, physical field-of-view coverage, and visual diagnostics are reported separately.

Target Windows validation completed with `358 passed in 4.59s`. Both geometry and identity initialization passed the configured technical checks. They converged to nearly the same physical transform and final MI value. Geometry initialization used fewer iterations and lower runtime. The minimum bidirectional physical field-of-view coverage decreased from about 0.818 before registration to about 0.668 after registration, which is preserved as a descriptive limitation rather than interpreted as anatomical correctness.

The experiment runner is:

```text
python scripts/week05_day04_rire_physical_registration.py --config configs/week05_day04_rire_physical_registration.yaml --overwrite
```

The local MHA files must remain available under `data/raw/rire/training_001/mha/`. They are intentionally excluded from normal shared ZIPs.

## Week 5 Day 25 integrated benchmark implementation

Day 25 adds the frozen Week 5 closure benchmark in `scripts/week05_day05_integrated_benchmark.py` with configuration `configs/week05_day05_integrated_benchmark.yaml`.

The final synthetic test set contains 13 cases covering rigid and affine motion models, monomodal references, intensity inversion, nonlinear gamma, histogram remapping, multiplicative bias, edge-emphasized appearance, and a restricted-field-of-view affine case. The geometric parameters differ from the earlier validation cases.

Mutual Information retains the Day 22 frozen configuration and Gaussian preprocessing. ECC is included as a compatible historical baseline using the frozen Week 3 rigid and affine settings. Each MI/ECC pair uses the same synthetic geometry and appearance condition, while each method retains its own previously frozen method-specific preprocessing and optimizer settings.

The runner records method execution success separately from geometric within-tolerance status. Rigid results report TRE, rotation error, and centered translation error. Affine results additionally report affine linear-component error and transform plausibility diagnostics. Failed and CHECK records remain in aggregate summaries.

The final report carries the Day 22 random-sampling seed variability study rather than selecting a random seed on the Day 25 test set. The frozen Day 25 MI path uses full metric sampling. Day 24 real RIRE evidence is included as a separate technical section and is not mixed into the synthetic TRE-based comparison.

Week 5 is complete. The Day 25 tracked report is target-Windows validated, and the final configurations and test cases should remain frozen before Week 6.


## Day 25 target Windows validation

The target Windows suite completed with `364 passed in 4.56s`. The frozen final benchmark completed all 13 cases and 26 planned registrations without infrastructure errors.

Rigid results: MI 5 / 6 within tolerance versus ECC 4 / 6. Affine results: MI 6 / 7 versus ECC 3 / 7. Across all paired cases there were 7 both-pass cases, 4 MI-only pass cases, 0 ECC-only pass cases, and 2 both-CHECK cases.

Intensity inversion was a clear multimodal condition where MI passed and ECC failed for both rigid and affine models. Edge-emphasized appearance remained a shared difficult condition. MI was generally slower, so these results support condition-specific method selection rather than a universal method ranking.

Real RIRE CT/MR-T1 evidence remains separate because verified reference landmarks or masks are not integrated.
