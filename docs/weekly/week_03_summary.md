# Week 3 Summary

## Monomodal Intensity and Frequency-Domain Baselines

**Status:** Day 5 implemented, target-machine validation pending  
**Completed and locally validated days:** 4 of 5

## Weekly objective

Implement and evaluate phase correlation and ECC as reproducible monomodal registration baselines using known synthetic ground truth, explicit runtime and convergence diagnostics, safe failure handling, multiresolution refinement, and standardized visual outputs.

## Progress by day

| Day | Focus | Status |
|---|---|---|
| Day 11, Week 3 Day 1 | Phase correlation for clean translation estimation | Complete and locally validated |
| Day 12, Week 3 Day 2 | Phase-correlation robustness under noise, blur, and partial overlap | Complete and locally validated |
| Day 13, Week 3 Day 3 | ECC translation and rigid registration | Complete and locally validated |
| Day 14, Week 3 Day 4 | ECC affine and multiresolution pyramids | Complete and locally validated |
| Day 15, Week 3 Day 5 | Integrated monomodal baseline benchmark | Implemented, local validation pending |

## Day 1 result

The clean phase-correlation validation recovered all 12 configured translations within the selected 0.5-pixel tolerance:

- success rate: 100 percent;
- mean translation-vector error: 0.0544 pixels;
- median translation-vector error: 0.0041 pixels;
- maximum translation-vector error: 0.3098 pixels;
- mean phase response: 0.9877.

The target Windows environment passed all 188 automated tests present at the end of Day 1.

## Day 2 result

The target Windows environment passed all 195 automated tests present at the end of Day 2.

The controlled robustness experiment evaluated 43 registrations:

- Gaussian noise: 6/6 within tolerance;
- Gaussian blur: 6/7 within tolerance;
- partial overlap: 6/7 within tolerance;
- translation magnitude: 8/8 within tolerance;
- subpixel shifts: 7/7 within tolerance;
- windowing comparison: 6/8 within tolerance.

The failed severe-blur and extreme-overlap cases are retained in the results.

## Day 3 result

The target Windows environment passed all 214 automated tests present at the end of Day 3.

The ECC experiment completed 24 registrations:

```text
Optimizer successes: 23/24
Within tolerance:    23/24
```

Group results:

```text
Translation + identity:          6/6
Translation + phase correlation: 6/6
Rigid + identity:                5/6
Rigid + phase correlation:       6/6
```

The deliberately difficult rigid case failed from identity initialization with a TRE of 65.721 pixels. Phase-correlation initialization recovered the same case with a TRE of 0.339 pixels.

## Day 4 result

The target Windows environment passed all 232 automated tests present at the end of Day 4.

The affine experiment completed 18 registrations:

```text
Optimizer successes: 18/18
Within tolerance:    16/18

Single resolution:   7/9
Multiresolution:     9/9
```

On the target machine, median TRE was 0.503 pixels for both strategies. Mean runtime was 82.49 ms for single-resolution ECC and 41.90 ms for multiresolution ECC in this controlled experiment.

The two difficult capture-range cases reached geometrically incorrect solutions with single-resolution ECC and were recovered by the coarse-to-fine configuration. These results support a condition-specific capture-range benefit rather than a universal claim that multiresolution is always faster or more accurate.

## Day 5 implementation

Day 5 adds an integrated monomodal benchmark across three tracked real source images. The configuration contains 14 base cases and 24 registrations.

The benchmark includes:

- phase correlation and ECC translation on the same six translation cases;
- ECC rigid on four rigid cases;
- single-resolution and multiresolution ECC on four affine cases;
- clean and moderately degraded conditions;
- standardized geometric, similarity, runtime, convergence, and failure fields;
- comparable translation plots and supported-method summary tables;
- representative alpha, checkerboard, difference, and edge-overlay figures.

The reference development run produced:

```text
Optimizer successes: 23/24
Within tolerance:    21/24

Phase correlation:              6/6
ECC translation:                4/6
ECC rigid:                      4/4
ECC affine single resolution:   3/4
ECC affine multiresolution:     4/4
```

Target-machine validation is required before Week 3 is marked complete.

## Report-generation readiness

Results are retained at three levels:

1. full generated run artifacts in `outputs/`;
2. compact machine-readable result snapshots in `reports/`;
3. narrative daily and weekly interpretation in `docs/`.

The Week 3 tracked snapshots cover phase correlation, robustness, ECC translation and rigid registration, affine multiresolution registration, and the integrated baseline benchmark.
