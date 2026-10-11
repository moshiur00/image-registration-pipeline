# Day 25: Integrated Week 5 Benchmark and Conclusions

## Status

Complete on the target Windows environment. The full suite passed with `364 passed in 4.56s`, and the frozen 13-case, 26-registration benchmark completed without infrastructure errors.

## Purpose

Day 25 closes Week 5 with a frozen final synthetic benchmark and a separate real-data evidence summary. The final synthetic cases were defined after the Day 22 rigid MI configuration and Day 23 affine implementation were frozen. Day 25 must not retune either MI or ECC on these test cases.

## Frozen methods

### Mutual Information

The final MI configuration remains the Day 22 selection:

- 32 histogram bins;
- full metric sampling;
- identity initialization for the controlled 2D benchmark;
- Gaussian smoothing with sigma 1.0;
- Regular Step Gradient Descent with learning rate 2.0;
- minimum step 0.001;
- 200 iterations;
- relaxation factor 0.5;
- gradient magnitude tolerance 0.0001;
- multiresolution shrink factors `[4, 2, 1]`;
- multiresolution smoothing sigmas `[2.0, 1.0, 0.0]`.

Rigid and affine MI use the same frozen metric and optimizer settings with the appropriate transform model.

### ECC comparison

ECC is included only as a compatible historical intensity-based baseline using the frozen Week 3 settings:

- rigid ECC: phase-correlation initialization, 140 iterations, single resolution;
- affine ECC: phase-correlation initialization, 160 iterations, scales `[0.25, 0.5, 1.0]`, pyramid pre-smoothing sigma 0.5.

The comparison uses identical geometric ground truth and identical appearance conditions for each paired case. MI and ECC retain their own previously frozen preprocessing and optimizer choices.

## Final synthetic test set

Day 25 contains 13 final synthetic cases and 26 planned registrations, with one MI and one ECC attempt per case.

The test set keeps rigid and affine motion models separate and covers:

- monomodal references;
- intensity inversion;
- nonlinear gamma mapping;
- histogram remapping;
- multiplicative bias field;
- edge-emphasized appearance;
- one affine restricted-field-of-view case.

The geometric parameters differ from the Day 21 to Day 23 validation cases.

## Evidence retained

For every registration, Day 25 stores:

- method execution status;
- geometric within-tolerance status;
- TRE;
- rigid rotation error or affine linear-component error;
- centered translation error;
- affine plausibility diagnostics where applicable;
- runtime;
- optimization objective value;
- optimizer diagnostics when available;
- failure reason;
- estimated transform;
- comparison images;
- alpha overlays;
- edge overlays;
- before/after joint histograms;
- MI convergence traces.

Failed and CHECK registrations remain in all denominators and in the failure gallery.

## Stochastic evidence

The final MI configuration uses full sampling, so Day 25 does not select or rerun a random seed for final-test accuracy. The Day 22 random-sampling seed study is carried into the final report as separate variability evidence.

## Real RIRE evidence

Day 24 RIRE CT/MR-T1 results are integrated only as a separate technical real-data section. They are not mixed into the synthetic TRE comparison because verified RIRE landmarks or masks are not integrated. TRE, Dice, and anatomical correctness remain unreported for the real pair.

## Target Windows results

Full target validation:

- `364 passed in 4.56s`;
- 13 final synthetic cases;
- 26 registrations;
- no infrastructure failure during the benchmark.

Rigid results:

- Mutual Information: 6 / 6 method successes, 5 / 6 within tolerance, median TRE 0.0161 px;
- ECC: 5 / 6 method successes, 4 / 6 within tolerance, median TRE 0.1260 px.

Affine results:

- Mutual Information: 7 / 7 method successes, 6 / 7 within tolerance, median TRE 0.0862 px;
- ECC: 5 / 7 method successes, 3 / 7 within tolerance, median TRE 0.3928 px.

Paired outcomes across the 13 shared cases:

- both methods within tolerance: 7;
- Mutual Information only within tolerance: 4;
- ECC only within tolerance: 0;
- both CHECK: 2.

Eight failure or CHECK records are retained in the report and failure gallery.

## Important findings

- Intensity inversion is a clear condition-specific separation in this benchmark. Mutual Information passed the rigid and affine inversion cases, while ECC failed to return valid estimates.
- Mutual Information also recovered the affine bias-field case and affine partial-overlap inversion case where ECC did not meet the final criteria.
- Edge-emphasized appearance remains difficult for both methods. Both rigid and affine edge-emphasized cases were outside tolerance for both MI and ECC.
- On cases where both methods passed, Mutual Information often produced lower TRE, but it was generally much slower than ECC.
- These results support condition-specific method selection. They do not justify a universal ranking across motion models or image conditions.
- Day 24 RIRE evidence remains separate from the synthetic TRE comparison. No anatomical accuracy claim is made for RIRE because verified landmarks or masks are not integrated.

## Week 5 closure

All Week 5 completion conditions are satisfied:

1. the target Windows test suite passed;
2. the frozen Day 25 benchmark completed without infrastructure errors;
3. all 13 cases and 26 registrations are present in the tracked report;
4. failures and CHECK cases are preserved;
5. rigid and affine results remain separate;
6. synthetic quantitative results remain separate from real RIRE technical evidence.

Week 5 is complete. The next work package is Week 6 unified evaluation and reproducible benchmarking. Day 25 configurations and results should remain frozen.
