# Day 12 Summary

## Week 3 Day 2: Phase-Correlation Robustness

**Status:** Complete and locally validated on the target Windows environment.

## Goal

Stress the Week 3 Day 1 translation estimator under controlled degradation and overlap changes while continuing to evaluate against exact Week 2 ground truth.

## Implemented

- configuration-driven Gaussian-noise sweep;
- Gaussian-blur sweep;
- partial-overlap sweep using restricted field of view;
- increasing translation-magnitude sweep;
- subpixel-shift sweep;
- Hanning window on/off comparison;
- translation-vector error with a 0.5-pixel selected tolerance;
- phase-response, overlap, NCC, and runtime recording;
- machine-readable CSV and JSON result tables;
- per-sweep summary statistics;
- robustness plots;
- representative severe-noise, severe-blur, and extreme-overlap outputs;
- seven automated robustness tests.

## Controlled design

For the noise sweep, each severity uses the same seed and therefore the same standardized noise realization scaled to a different magnitude.

For the overlap sweep, configured field-of-view fractions are converted into an actual fixed-space geometric-overlap fraction. The registration method does not receive the overlap mask.

## Local validation result

The target Windows environment passed all 195 automated tests present at the end of Day 2.

The local robustness run evaluated 43 registrations:

| Sweep | Within 0.5 px | Median error | Maximum error |
|---|---:|---:|---:|
| Gaussian noise | 6/6 | 0.016 px | 0.069 px |
| Gaussian blur | 6/7 | 0.007 px | 4.181 px |
| Partial overlap | 6/7 | 0.030 px | 0.622 px |
| Translation magnitude | 8/8 | 0.008 px | 0.026 px |
| Subpixel | 7/7 | 0.046 px | 0.439 px |
| Windowing comparison | 6/8 | 0.116 px | 72.160 px |

Severe Gaussian blur at sigma 8.0 exceeded the selected tolerance. The most extreme restricted-field-of-view case had approximately 0.26 percent actual overlap and also exceeded tolerance.

The large-translation sweep passed all eight cases, including the 216.33-pixel translation-magnitude case in this source image and configuration.

The Hanning-window comparison showed that severe blur failed with both settings, but windowing reduced the error substantially in that specific run.

These observations are evidence for this controlled source image and configuration, not universal claims about phase correlation.

## Report preservation

The full tables and figures remain under:

```text
outputs/week03_day02_phase_robustness/
```

A compact tracked snapshot is preserved at:

```text
reports/week03_day02_phase_robustness.json
```

## Next step

Week 3 Day 3 introduces ECC translation and rigid registration with identity and phase-correlation initialization.
