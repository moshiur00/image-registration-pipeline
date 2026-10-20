# Day 27: Metric Implementation and Independent Validation

## Status

Development implementation complete. Target Windows validation is pending.

## Purpose

Day 27 implements the common metric calculations defined by the frozen Day 26 evaluation contract and validates them on hand-constructed cases with independently known answers.

## Setup

The validated registration algorithms and their Weeks 1 to 5 settings remain unchanged. Day 27 adds a method-independent metrics module, tests, configuration, validation script, documentation, and a compact tracked report.

## Variable changed

The project now has executable implementations for:

- model-aware transform-parameter error;
- TRE summaries from exact transforms or landmarks;
- pixel and physical-unit TRE;
- Dice with explicit empty-mask behavior;
- overlap-aware MAE, MSE, NCC, SSIM, and evaluation Mutual Information;
- valid-overlap fraction and no-overlap rejection.

## Factors kept fixed

- Moving -> Fixed transform convention;
- `(x, y)` and `(x, y, z)` coordinate order;
- all registration algorithms;
- all frozen method configurations;
- the Day 26 metric availability and evidence policy;
- existing benchmark reports.

## Independent validation design

Metrics are checked against cases where the expected result is known analytically rather than against another implementation of the same metric.

Examples include:

- `(3, 4)` translation giving `5 px` error;
- anisotropic physical spacing conversion;
- identity transform giving zero TRE;
- exact rigid rotation wrap-around;
- known similarity scale difference;
- known affine Frobenius discrepancy;
- exact landmark offsets;
- perfect, disjoint, and empty masks;
- binary identical variables with MI equal to `ln(2)`;
- invalid image borders excluded from descriptive metrics;
- zero-overlap input rejected rather than summarized.

## Empty-mask Dice policy

The project records both-empty masks as Dice `1.0`, because both segmentations agree that the structure is absent. One-empty cases return `0.0`. This policy is explicit so later reports cannot silently change the interpretation.

## Descriptive metric policy

MAE, MSE, NCC, SSIM, and evaluation MI are calculated only inside the valid-overlap region. They remain descriptive evidence. In particular, NCC and SSIM may behave poorly for geometrically correct multimodal pairs.

The Day 27 validation script includes an aligned intensity-inversion example to make this limitation visible rather than treating it as a later surprise.

## Results

The development validation script writes detailed local evidence under `outputs/week06_day02_metric_validation/` and the compact tracked report `reports/week06_day02_metric_validation.json`.

The expected Day 27 script evidence includes:

- `5 px` translation parameter error;
- `5 px` mean TRE for the same known offset;
- correct anisotropic physical conversion;
- Dice `1.0 / 0.0 / 1.0 / 0.0` for perfect, disjoint, both-empty, and one-empty cases;
- evaluation MI equal to `ln(2)` for a balanced identical binary pair;
- perfect descriptive metrics inside a valid region despite deliberately corrupted invalid borders;
- explicit no-overlap rejection.

## Interpretation

The Week 6 metric layer can now calculate the common evidence that the Day 26 contract only defined. This is the prerequisite for a benchmark runner that can compare methods without manual spreadsheet logic.

## Failure cases

Day 27 rejects:

- malformed homogeneous transforms;
- transform shape mismatches;
- invalid spacing;
- empty TRE point sets;
- non-finite landmark coordinates;
- non-binary masks;
- invalid Dice empty-policy values;
- empty valid-overlap regions;
- invalid MI histogram settings.

## Limitations

Day 27 does not yet:

- define final success/failure thresholds;
- aggregate full benchmark results;
- resume interrupted experiment matrices;
- compare method consensus;
- recommend one registration method.

## Target Windows validation

Day 27 was validated on the target Windows environment.

- Backend regression: 390 / 390 passed in 5.42 s.
- UI regression: 64 / 64 passed in 4.87 s.
- Hand-constructed metric checks: 18 / 18 passed.
- No-overlap rejection: passed.
- Known 3-4-5 translation produced 5.000 px parameter error and 5.000 px TRE.
- Physical conversion produced 6.325 mm translation error and TRE.
- Binary evaluation MI matched ln(2).
- The aligned intensity-inversion case produced NCC = -1.000 while evaluation MI remained informative.

## Decision and next experiment

Day 27 is complete. The unified metric implementation is frozen for the next work package. Day 28 may begin.

Day 28 will build the deterministic resumable benchmark runner, standardized long-form result table, and explicit failure records around the frozen Day 26 contract and validated Day 27 metrics.
