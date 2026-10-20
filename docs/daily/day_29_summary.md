# Day 29 Summary: Automatic Multi-Method Execution Foundation

## Objective

Create the first automatic registration orchestration layer without changing or retuning the validated registration algorithms.

The Day 29 layer must:

- filter candidate methods using explicit compatibility rules,
- execute every compatible candidate through the existing registration service boundary,
- normalize only common Week 6 evidence,
- keep optimizer-specific diagnostics separate,
- preserve COMPLETED, CHECK, FAILED, and VALIDATION_ERROR candidates,
- operate correctly when ground truth is unavailable,
- avoid selecting a final best method.

## Implementation

Added:

- `src/image_registration/automatic_registration.py`
- `tests/test_automatic_registration.py`
- `configs/week06_day04_automatic_multi_method.yaml`
- `scripts/week06_day04_automatic_multi_method.py`
- `docs/WEEK06_AUTOMATIC_MULTI_METHOD.md`
- `reports/week06_day04_automatic_multi_method.json`

The automatic service is framework neutral. The Day 29 integration script supplies an executor that uses the existing UI `RegistrationService` and validated 2D adapters. This keeps orchestration independent from Streamlit while demonstrating that the frozen workbench service boundary can be reused.

## Compatibility filtering

Each configured method is checked against:

- dimensions,
- candidate transform models,
- modality class,
- same-shape requirements,
- optional-method policy.

Excluded methods remain in a compatibility audit with explicit reasons.

The controlled Day 29 affine study defines six catalog entries. Four are compatible with the affine pair and two are excluded because their transform models do not match the requested affine model.

## Common evidence normalization

Only values defined by the Day 26 common metric catalog are promoted into normalized evidence groups:

- geometric,
- anatomical,
- descriptive,
- valid overlap,
- runtime.

Method-specific diagnostics remain separate. For example, ECC objective values and RANSAC inlier information are retained but are not converted into a common score.

## Unknown-ground-truth behavior

The automatic run is intentionally given:

`ReferenceEvidence()`

even though the development pair was generated synthetically.

Therefore operation-time evidence contains:

- execution status,
- estimated transform when available,
- transform plausibility,
- overlap-aware MAE/MSE/NCC/SSIM/evaluation MI,
- valid-overlap fraction,
- runtime,
- method-specific diagnostics,
- warnings and failure reasons.

It does not contain:

- TRE,
- transform parameter error,
- geometric PASS/CHECK,
- any hidden development ground truth.

The exact synthetic transform is evaluated only after the automatic run and is written under a clearly separate `development_only_ground_truth_validation` section.

## Development run

The local development environment selected four compatible affine candidates:

- ECC Affine
- ORB + RANSAC Affine
- SIFT + RANSAC Affine
- Mattes MI Affine 2D

Phase Correlation and rigid MI were correctly excluded because their transform models did not match the requested affine model.

In the local environment, ECC, ORB, and SIFT completed. Mattes MI was retained as a FAILED candidate because SimpleITK is unavailable in the local development environment. This is expected to be re-evaluated on the target Windows environment, where the earlier Week 5 SimpleITK path is available.

No method was selected as best.

## Tests

Day 29 adds focused tests for:

- deterministic candidate identities,
- transform compatibility,
- modality compatibility,
- shape compatibility,
- optional-method policy,
- common metric grouping,
- separation of raw optimizer diagnostics,
- multi-candidate execution,
- CHECK preservation,
- failure preservation,
- validation-error preservation,
- compatibility audit retention,
- no-compatible-candidate rejection,
- no unsupported geometric PASS for unknown reference evidence.

## Status

Status: COMPLETE. Target Windows validation passed.

## Target Windows validation

Day 29 was validated on the target Windows environment.

- Backend regression: 418 / 418 passed in 5.29 s.
- UI regression: 64 / 64 passed in 4.99 s.
- Method catalog: 6.
- Compatible affine candidates: 4.
- Transform-incompatible candidates excluded: 2.
- Candidate terminal states: 4 completed, 0 CHECK, 0 failed, 0 validation errors.
- Mattes MI Affine completed successfully on the target environment.
- Ground truth exposed to automatic service: no.
- Final recommendation: deferred until robustness calibration.
- Operational candidate evidence remained free of TRE, parameter error, and geometric PASS/CHECK claims.

The four completed candidates were ECC Affine, Mattes MI Affine 2D, ORB + RANSAC Affine, and SIFT + RANSAC Affine. Phase Correlation and Mattes MI Rigid 2D were correctly excluded because they did not match the requested affine transform model.

## Decision and next experiment

Day 29 is complete. The automatic multi-method execution contract is frozen for the next work package. Day 30 may begin.

Day 30 will add transform-space disagreement, preliminary consensus, robust method summaries, and Week 6 closure without introducing a final calibrated best-method recommendation.
