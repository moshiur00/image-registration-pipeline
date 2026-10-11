# Day 21 Summary: Rigid Mutual Information Foundation

## Status

Complete on the target Windows environment.

Target validation:

- full test suite: `340 passed in 3.73s`;
- Day 21 experiment cases executed: 6 / 6;
- method execution success: 6 / 6;
- geometrically within the configured tolerance: 4 / 6;
- median TRE: 0.023 px;
- no configuration or infrastructure failures remained in the validated run.

## Purpose

Day 21 starts Week 5 with a controlled 2D rigid Mattes Mutual Information registration path for monomodal and simulated multimodal pairs.

## Setup

The frozen Day 21 configuration used:

- Mattes Mutual Information with 50 histogram bins;
- random metric sampling at 20 percent with seed 42;
- geometry initialization;
- Regular Step Gradient Descent;
- 200 maximum iterations;
- multiresolution shrink factors `[4, 2, 1]`;
- smoothing sigmas `[2.0, 1.0, 0.0]`;
- project transform convention `Moving -> Fixed`.

The SimpleITK registration transform is used in its Fixed -> Moving resampling direction internally and inverted before it is returned through the project interface.

## Metrics and thresholds

The controlled synthetic ground truth allows direct geometric evaluation.

Configured development thresholds:

- TRE: at most 3.0 px;
- rotation error: at most 1.5 degrees;
- centered translation error: at most 4.0 px.

Optimizer execution success and geometric correctness are recorded separately.

## Target Windows results

| Case | Mapping | TRE | Runtime | Geometric status |
|---|---|---:|---:|---|
| camera_monomodal_rigid | none | 0.013 px | 512.59 ms | PASS |
| camera_inversion_rigid | intensity_inversion | 0.014 px | 541.14 ms | PASS |
| camera_gamma_rigid | nonlinear_gamma | 0.019 px | 785.63 ms | PASS |
| camera_histogram_rigid | histogram_remap | 318.731 px | 934.53 ms | CHECK |
| coins_bias_rigid | bias_field | 0.027 px | 149.16 ms | PASS |
| moon_edge_rigid | edge_emphasized | 17.992 px | 171.47 ms | CHECK |

Summary:

- method success: 6 / 6;
- within tolerance: 4 / 6;
- median TRE: 0.023 px;
- maximum TRE: 318.731 px.

## Observations

The monomodal, inversion, nonlinear-gamma, and bias-field cases were recovered with very small geometric error under the Day 21 settings.

The histogram-remap case completed the optimizer but reached the maximum 200 iterations and returned 318.731 px TRE. This is a geometric failure, not an execution failure.

The edge-emphasized case stopped because the gradient-magnitude tolerance was satisfied, but the returned transform still had 17.992 px TRE. This is direct evidence that optimizer convergence does not imply geometric correctness.

## Failure cases

`camera_histogram_rigid` and `moon_edge_rigid` remain recorded as CHECK cases. Their thresholds are not loosened and their results are not removed from later analysis.

## Limitations

- Day 21 uses controlled 2D synthetic geometry with unit spacing.
- Simulated multimodal mappings do not replace real multimodal validation.
- The thresholds are development criteria rather than final benchmark thresholds.
- The final metric value alone is not treated as evidence of correct geometry.

## Decision and next step

Day 21 is frozen as the rigid MI baseline. Day 22 will use a limited multimodal validation subset for controlled initialization, histogram-bin, sampling, stochastic-variability, and preprocessing studies. The histogram-remap and edge-emphasized failures remain in the Day 22 evidence instead of being tuned away.
