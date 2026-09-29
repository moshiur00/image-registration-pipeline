# Day 17 Summary: ORB Descriptor Matching and Correspondence Filtering

## Status

Complete and validated on the target Windows environment.

The full repository test suite passed with `270 passed in 3.93s`. The Day 17 descriptor-matching experiment also completed successfully on all 9 configured cases for both KNN ratio filtering and cross-check matching.

## 1. Purpose

Day 17 extends the ORB feature-detection layer into descriptor correspondence matching. The experiment asks how many plausible correspondences survive two common filtering strategies and how those correspondences are distributed spatially.

No geometric model is fitted yet. The goal is to study the quality of the correspondence set that Day 18 RANSAC will receive.

## 2. Matching strategies

Two strategies are implemented:

- KNN matching with Hamming distance and ratio filtering;
- mutual nearest-neighbor cross-check matching.

Moving descriptors are queries and fixed descriptors are references, consistent with the project Moving -> Fixed convention.

The default KNN ratio threshold is `0.75`. A threshold sweep also evaluates `0.60`, `0.70`, `0.75`, `0.80`, and `0.90`.

A case is marked as having enough correspondences for the next stage when at least 8 accepted matches remain.

## 3. Controlled cases

Nine cases are included:

1. camera identity
2. camera translation
3. camera rotation
4. camera scale
5. camera illumination change
6. camera Gaussian blur
7. camera restricted field of view
8. coins rotation
9. moon Gaussian blur

The ORB detector configuration remains the same as Day 16 so the experiment isolates the matching stage rather than changing detection parameters at the same time.

## 4. Metrics and diagnostics

For each strategy the experiment records:

- tentative match count;
- accepted match count;
- rejected match count;
- acceptance rate;
- Hamming-distance statistics;
- fixed correspondence coverage;
- moving correspondence coverage;
- minimum fixed/moving coverage;
- matching runtime;
- safe failure reason.

The experiment also saves tentative and filtered match figures, correspondence coverage figures, distance histograms, a ratio-threshold sweep plot, and a strategy match-count comparison plot.

## 5. Target Windows results

At the default KNN ratio threshold of `0.75`, all 9 cases retained at least 8 accepted matches. Cross-check matching also retained at least 8 matches in all 9 cases.

| Case | KNN accepted | KNN min coverage | Cross-check accepted | Cross-check min coverage |
|---|---:|---:|---:|---:|
| camera_identity | 800 | 0.750 | 800 | 0.750 |
| camera_translation | 657 | 0.625 | 650 | 0.625 |
| camera_rotation | 509 | 0.562 | 551 | 0.562 |
| camera_scale | 432 | 0.500 | 480 | 0.500 |
| camera_illumination | 586 | 0.625 | 652 | 0.688 |
| camera_blur | 160 | 0.438 | 237 | 0.562 |
| camera_partial_overlap | 655 | 0.438 | 676 | 0.500 |
| coins_rotation | 414 | 0.812 | 503 | 0.812 |
| moon_blur | 29 | 0.375 | 32 | 0.375 |

Target-machine aggregate values:

- KNN ratio successful cases: 9 / 9
- mean KNN accepted matches: 471.3
- mean KNN minimum spatial coverage: 0.569
- mean KNN matching runtime: 1.787 ms
- cross-check successful cases: 9 / 9
- mean cross-check accepted matches: 509.0
- mean cross-check minimum spatial coverage: 0.597
- mean cross-check matching runtime: 2.801 ms

These runtime values are target-machine measurements from the Windows validation run.

## 6. Ratio-threshold sweep

Relaxing the KNN ratio threshold increased the mean number of accepted matches:

| Ratio threshold | Mean accepted matches | Mean minimum coverage |
|---:|---:|---:|
| 0.60 | 404.2 | 0.535 |
| 0.70 | 448.7 | 0.556 |
| 0.75 | 471.3 | 0.569 |
| 0.80 | 494.3 | 0.576 |
| 0.90 | 556.7 | 0.604 |

This is expected behavior for the filter, but it is not evidence that the looser threshold is better. Geometric validation is required before deciding which threshold produces more correct correspondences.

## 7. Observations

The identity case retained all 800 capped ORB correspondences under both matching strategies.

The blurred moon case remained the most difficult case. It had only 29 accepted KNN matches and 32 cross-checked matches, with minimum correspondence coverage of 0.375. This is consistent with the strong feature loss observed on Day 16.

The rotated coins case had fewer matches than the camera identity case but much stronger spatial support, with minimum coverage of 0.812 under both strategies.

The restricted-field-of-view case still retained many descriptor matches, but its accepted endpoints occupied a smaller portion of the image. This supports keeping match count and spatial distribution as separate diagnostics.

Cross-check retained more matches than the default ratio filter in several cases, including blur and rotation. This difference should not be treated as proof of better matching quality until geometric consistency is measured.

The KNN threshold sweep behaved monotonically in the expected direction: looser filtering retained more matches and slightly increased mean coverage.

## 8. Interpretation

The Day 17 evidence shows that descriptor filtering can provide a substantial number of candidate correspondences across all configured cases, including blur and restricted field of view.

However, descriptor acceptance is not equivalent to geometric correctness. A filtered correspondence can still be an outlier with respect to the true transformation. This motivated the Day 18 RANSAC stage rather than using descriptor matches directly as registration evidence.

Accepted-match count and spatial coverage should be interpreted together. A large number of matches concentrated in a limited area may provide weaker transform support than a smaller but well-distributed set.

The ratio threshold controls a trade-off between retaining correspondences and admitting more ambiguous matches. The current threshold remains configurable until geometric inlier consistency and transform error are measured.

## 9. Limitations

- no similarity or affine transform is estimated yet;
- no RANSAC inlier mask exists yet;
- no TRE or parameter error is calculated from the descriptor matches;
- accepted matches can still contain geometric outliers;
- ratio-threshold observations are specific to the current tracked images and configured conditions;
- KNN and cross-check use different acceptance rules, so match count alone is not a fair quality ranking.

## 10. Validation

Target environment:

- Windows PowerShell project virtual environment
- Python 3.12.6
- pytest result: `270 passed in 3.93s`
- Day 17 configured cases: 9
- KNN cases with at least 8 accepted matches: 9 / 9
- cross-check cases with at least 8 accepted matches: 9 / 9

## 11. Decision and next experiment

Proceed to Day 18 with RANSAC-based similarity estimation.

Day 18 should use the Day 17 correspondences to measure:

- inlier and outlier counts;
- inlier ratio;
- reprojection residuals;
- estimated similarity transform;
- TRE;
- translation error;
- rotation error;
- scale error;
- explicit failure reason when the correspondence set is insufficient or geometrically inconsistent.

The KNN ratio threshold should remain configurable rather than being treated as finalized until geometric results are available.
