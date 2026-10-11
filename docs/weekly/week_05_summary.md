# Week 5 Progress: Multimodal Registration with Mutual Information

## Current status

Week 5 is complete on the target Windows environment. Days 21 through 25 are validated and the final Day 25 benchmark is frozen.

Latest target Windows validation:

- full Windows suite: `364 passed in 4.56s`;
- Day 25 final synthetic cases: 13;
- Day 25 registrations: 26;
- Mutual Information within tolerance: 11 / 13;
- ECC within tolerance: 7 / 13;
- paired outcomes: 7 both-pass, 4 MI-only pass, 0 ECC-only pass, 2 both-CHECK;
- failure/CHECK records retained: 8.

The Day 22 frozen MI configuration remained unchanged through the final test benchmark. Day 24 real RIRE evidence remains technically validated but separate from synthetic TRE conclusions because verified landmarks or masks are not integrated.

## Five-day structure

- Day 21: rigid Mattes Mutual Information foundation and six-case target validation, complete.
- Day 22: rigid MI initialization, histogram-bin, sampling, stochastic-repeat, preprocessing, and frozen-candidate study, complete.
- Day 23: affine MI with single-resolution and multiresolution comparison plus rigid model-mismatch diagnostics, complete.
- Day 24: real RIRE CT/MR-T1 physical-space registration with strict metadata preservation and evidence limits.
- Day 25: integrated synthetic multimodal benchmark, compatible ECC comparison, real-data summary, variability analysis, and Week 5 closure, complete.

## Day 21 findings

The baseline rigid MI configuration recovered the monomodal, intensity-inversion, nonlinear-gamma, and bias-field cases with very small TRE.

The histogram-remap case reached the maximum 200 optimizer iterations and returned a large geometric error. The edge-emphasized case satisfied the optimizer gradient-magnitude stop condition but still returned 17.992 px TRE. These cases demonstrate why optimizer completion and geometric correctness remain separate result fields.

Detailed evidence is stored in:

- `reports/week05_day01_mi_rigid.json`;
- `docs/daily/day_21_summary.md`.

## Day 22 validated study

Day 22 used a limited five-case simulated-multimodal validation subset and sequential one-factor-at-a-time studies rather than an unrestricted grid search.

The completed studies covered:

- initialization: identity, geometry, moments;
- histogram bins: 32, 50, 64;
- metric sampling: full, regular, random;
- sampling percentage: 10, 20, 50 percent for diagnostic random sampling;
- multimodal-safe preprocessing: none, robust clipping, robust normalization, z-score normalization, Gaussian smoothing;
- random-sampling variability with seeds 7, 42, 101, 202, 909.

Selection prioritized geometric within-tolerance count, method execution success, median TRE, maximum TRE, then mean runtime. Random seeds were used only to characterize stochastic variability and were not selected by best-case accuracy.

The baseline reached 3 / 5 within tolerance. The sequential composite candidate reached 5 / 5. The frozen confirmation also reached 5 / 5, with median TRE 0.0173 px and maximum TRE 0.0950 px.

The frozen rigid MI configuration is:

- initialization: identity;
- histogram bins: 32;
- metric sampling: full;
- preprocessing: Gaussian smoothing, sigma 1.0;
- learning rate: 2.0;
- minimum step: 0.001;
- iterations: 200;
- relaxation factor: 0.5;
- gradient magnitude tolerance: 0.0001;
- shrink factors: `[4, 2, 1]`;
- smoothing sigmas: `[2.0, 1.0, 0.0]`.

This is a validation-selected configuration for later Week 5 work on this benchmark. It is not claimed to be universally optimal and must not be retuned using the final Day 25 benchmark.

Detailed evidence is stored in:

- `reports/week05_day02_mi_rigid_study.json`;
- `docs/daily/day_22_summary.md`.

## Day 23 validated study

Day 23 extended the frozen Day 22 MI configuration to 2D affine registration and compared single-resolution with multiresolution optimization on seven controlled affine cases.

Target Windows evidence:

- full suite: `352 passed in 8.68s`;
- affine single-resolution: 7 / 7 method successes, 5 / 7 within tolerance, median TRE 0.1681 px;
- affine multiresolution: 7 / 7 method successes, 5 / 7 within tolerance, median TRE 0.0887 px;
- capture-range paired outcomes: 5 both-pass, 0 multiresolution-only pass, 0 single-resolution-only pass, 2 both-CHECK;
- rigid model-mismatch comparator: 0 / 3 within tolerance, median TRE 13.986 px.

Multiresolution improved median geometric accuracy but did not increase the number of within-tolerance cases on this controlled set. The project therefore does not claim an observed capture-range expansion from the pyramid on Day 23.

The partial-overlap and edge-emphasized affine cases remain explicit failures for both affine variants. The restricted rigid comparator failed all three selected true-affine cases, which supports transform-model mismatch as a separate failure mechanism on those examples.

Detailed evidence is stored in:

- `reports/week05_day03_mi_affine_multiresolution.json`;
- `docs/daily/day_23_summary.md`.

## Day 24 validated real-data study

Day 24 now implements real RIRE `training_001` CT/MR-T1 rigid registration in 3D physical coordinates.

The implementation keeps the validated Day 22 Mattes MI and optimizer choices frozen where applicable. Geometry initialization is the primary real-data path, while identity initialization is retained only as a diagnostic comparator. Day 24 does not select an initialization from visual appearance alone.

The runner verifies the prepared manifest metadata and SHA-256 hashes before registration, preserves spacing, origin, and direction, returns the project Moving -> Fixed 4 x 4 physical transform, records physical field-of-view coverage, and checks that the registered volume uses the fixed CT grid.

Because verified RIRE landmarks or masks are not integrated, Day 24 explicitly does not report TRE, Dice, or anatomical correctness. Joint histograms, optimizer traces, central-slice comparisons, overlays, physical overlap, and transform plausibility are descriptive or technical evidence only.

Target Windows results:

- full suite: `358 passed in 4.59s`;
- geometry initialization: method success, plausible transform, metadata integrity, and technical validation all passed; runtime 10969.64 ms; rotation magnitude 5.435 degrees; translation magnitude 33.576 mm;
- identity initialization: method success, plausible transform, metadata integrity, and technical validation all passed; runtime 14318.95 ms; rotation magnitude 5.424 degrees; translation magnitude 33.508 mm;
- both paths converged to nearly the same physical transform and final MI value;
- minimum bidirectional physical field-of-view coverage decreased from about 0.818 before registration to about 0.668 after registration for both variants.

The overlap decrease is retained as a diagnostic limitation. It is not interpreted as anatomical failure because verified anatomical reference data is not integrated. Geometry initialization remains the primary documented path because it reached essentially the same solution with fewer iterations and lower runtime.

Implementation files:

- `src/image_registration/medical_mutual_information.py`;
- `configs/week05_day04_rire_physical_registration.yaml`;
- `scripts/week05_day04_rire_physical_registration.py`;
- `tests/test_medical_mutual_information.py`;
- `reports/week05_day04_rire_physical_registration.json`;
- `docs/daily/day_24_summary.md`.

The repository collects 358 tests. Target Windows validation completed with `358 passed in 4.59s`. Both configured real RIRE rigid MI variants executed successfully, returned plausible transforms, preserved metadata, and passed the technical validation checks.

## Day 25 validated integrated benchmark

The frozen Day 25 benchmark completed on the target Windows environment with `364 passed in 4.56s`. The benchmark contains 13 final synthetic test cases and 26 registrations, with one Mutual Information and one compatible ECC attempt per case. Rigid and affine results remain separate.

Final rigid results:

- Mutual Information: 6 / 6 method successes, 5 / 6 within tolerance, median TRE 0.0161 px;
- ECC: 5 / 6 method successes, 4 / 6 within tolerance, median TRE 0.1260 px.

Final affine results:

- Mutual Information: 7 / 7 method successes, 6 / 7 within tolerance, median TRE 0.0862 px;
- ECC: 5 / 7 method successes, 3 / 7 within tolerance, median TRE 0.3928 px.

Paired outcomes across the 13 cases were 7 both-pass, 4 MI-only pass, 0 ECC-only pass, and 2 both-CHECK. Eight failure or CHECK records are retained.

The strongest condition-specific differences are intensity inversion, where ECC failed for both rigid and affine cases while MI passed, and affine bias field plus affine partial overlap, where MI passed and ECC did not meet the final criteria. Edge-emphasized appearance remained difficult for both methods in both motion models.

MI was substantially slower than ECC on many successful cases. The final conclusion is therefore not a universal ranking. The evidence supports MI as the more reliable frozen multimodal intensity baseline on this synthetic test set, while ECC remains computationally cheaper and performs well on several compatible conditions.

Day 22 stochastic sampling evidence is carried forward separately because the final MI configuration uses full sampling. Day 24 RIRE CT/MR-T1 evidence remains a separate technical real-data section with no TRE, Dice, or anatomical correctness claim.

Week 5 is complete.

## Next step

Start Week 6 unified evaluation and reproducible benchmarking. Keep all Day 25 final-test cases, configurations, and evidence frozen.
