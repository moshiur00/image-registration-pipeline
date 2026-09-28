# Week 3 Summary

## Monomodal Intensity and Frequency-Domain Baselines

**Status:** Complete and locally validated  
**Completed and locally validated days:** 5 of 5  
**Final automated test status:** 242 / 242 passed on the target Windows environment

## Weekly objective

Implement and evaluate phase correlation and ECC as reproducible monomodal registration baselines using known synthetic ground truth, explicit runtime and convergence diagnostics, safe failure handling, multiresolution refinement, and standardized visual outputs.

## Progress by day

| Day | Focus | Status |
|---|---|---|
| Day 11, Week 3 Day 1 | Phase correlation for clean translation estimation | Complete and locally validated |
| Day 12, Week 3 Day 2 | Phase-correlation robustness under noise, blur, and partial overlap | Complete and locally validated |
| Day 13, Week 3 Day 3 | ECC translation and rigid registration | Complete and locally validated |
| Day 14, Week 3 Day 4 | ECC affine and multiresolution pyramids | Complete and locally validated |
| Day 15, Week 3 Day 5 | Integrated monomodal baseline benchmark | Complete and locally validated |

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
Median TRE:           0.503 px
Mean runtime:        82.49 ms

Multiresolution:     9/9
Median TRE:           0.503 px
Mean runtime:        41.90 ms
```

The difficult capture-range cases reached geometrically incorrect solutions with single-resolution ECC and were recovered by the coarse-to-fine configuration. On the target machine, the representative single-resolution TRE values were 86.562 and 81.584 pixels, while the corresponding multiresolution TRE values were 0.595 and 0.552 pixels. These results support a condition-specific capture-range benefit rather than a universal claim that multiresolution is always faster or more accurate.

## Day 5 result

The target Windows environment passed the complete 242-test suite before the integrated benchmark was run.

The final integrated benchmark used three tracked real source images, 14 base cases, and 24 registrations. The target-machine result was:

```text
Optimizer successes: 23/24
Within tolerance:    21/24

Phase correlation:              6/6
ECC translation:                4/6
ECC rigid:                      4/4
ECC affine single resolution:   3/4
ECC affine multiresolution:     4/4
```

Method summaries from the validated run:

```text
Phase correlation:            median TRE 0.034 px, mean runtime   2.83 ms
ECC translation:              median TRE 0.290 px, mean runtime  14.85 ms
ECC rigid:                    median TRE 0.295 px, mean runtime  32.69 ms
ECC affine single resolution: median TRE 0.734 px, mean runtime  71.16 ms
ECC affine multiresolution:   median TRE 0.662 px, mean runtime 107.23 ms
```

The affine capture-range case preserved an important failure example: single-resolution ECC returned a transform but failed geometrically, while multiresolution ECC recovered the case within tolerance. The translation subset also retained difficult cases. ECC translation failed the selected geometric tolerance on the blurred Moon and restricted-field-of-view Moon cases, while phase correlation passed all six shared translation cases.

## Weekly completion result

Week 3 is complete. Phase correlation and ECC are implemented through the common registration interface with standardized transforms, diagnostics, runtime, failure handling, geometric evaluation, and representative visual outputs. The locally validated results are preserved in tracked report snapshots for later technical-report generation.

## Report-generation readiness

Results are retained at three levels:

1. full generated run artifacts in `outputs/`;
2. compact machine-readable result snapshots in `reports/`;
3. narrative daily and weekly interpretation in `docs/`.

The tracked snapshots cover phase correlation, robustness, ECC translation and rigid registration, affine multiresolution registration, and the integrated baseline benchmark.

## Next technical stage

The next planned work package is feature-based registration with ORB keypoints, binary descriptors, match filtering, and RANSAC-based similarity or affine model estimation.
