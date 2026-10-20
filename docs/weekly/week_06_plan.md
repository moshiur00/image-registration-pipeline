# Week 6 Plan: Unified Evaluation and Reproducible Experiments

## Current progress

- Day 26 COMPLETE and target-validated: 376 backend tests and 64 UI tests passed on Windows.
- Day 27 COMPLETE and target-validated: 390 backend tests, 64 UI tests, and 18 / 18 hand-constructed metric checks passed on Windows.
- Day 28 COMPLETE and target-validated: deterministic IDs, frozen-plan fingerprinting, durable JSONL evidence, resume/skip behavior, long-form CSV output, and explicit failure records are validated. Target Windows evidence: 403 / 403 backend tests, 64 / 64 UI tests, and a 12 / 12 successful resume probe.
- Day 29 COMPLETE and target-validated: framework-neutral automatic-run contracts, explicit compatibility filtering, existing RegistrationService orchestration, common-evidence normalization, failure/CHECK preservation, and a deferred recommendation state are validated. Target Windows evidence: 418 / 418 backend tests, 64 / 64 UI tests, 4 / 4 compatible candidates completed, 0 failures, 0 validation errors, and no ground-truth exposure to the automatic service.
- Day 30 COMPLETE and target-validated: transform-space disagreement, preliminary consensus, robust method summaries, the four-case closure matrix, and Week 6 closure evidence are validated. Target Windows evidence: 432 / 432 backend tests, 64 / 64 UI tests, 13 / 13 automatic candidates completed, 0 failures, 0 validation errors, no ground-truth exposure to the automatic service, and no final recommendation claim.

## Week objective

Bring all existing registration families under one scientifically consistent evaluation and result system without retuning the validated Weeks 1 to 5 algorithms. Week 6 also starts the automatic multi-method foundation, but it does not yet freeze a final recommendation policy.

## Day 26: Unified evaluation contract

- Freeze metric roles, units, transform conventions, reference-evidence requirements, and valid-overlap policy.
- Introduce a common method-independent evaluation record.
- Enforce the rule that unknown image pairs cannot receive TRE or geometric PASS/CHECK claims.
- Keep method-specific optimizer objectives separate from common evaluation metrics.

## Day 27: Metric implementation and independent validation

- Implement model-aware parameter error.
- Add TRE summaries in pixel and physical units where reference evidence permits.
- Add Dice with explicit empty-mask behavior.
- Add overlap-aware descriptive metrics, including evaluation Mutual Information.
- Validate metrics on identity, known-offset, perfect-alignment, empty-mask, and no-overlap cases.

## Day 28: Resumable benchmark runner

- Enumerate dataset pairs, methods, configurations, and seeds.
- Add deterministic experiment identifiers, resume, and skip-completed behavior.
- Write a standardized long-form result table and explicit failure records.
- Preserve monomodal and multimodal labels.

## Day 29: Automatic multi-method execution foundation

- Add framework-neutral automatic-run contracts.
- Orchestrate several compatible candidates through the existing registration service boundary.
- Normalize heterogeneous method outputs without comparing raw objectives.
- Preserve failures and CHECK candidates in the comparison set.

## Day 30: Comparison, agreement, summaries, and closure

- Add transform-space disagreement in a common image-space representation.
- Add a preliminary consensus view without claiming a final best method.
- Generate per-method robust summaries, success rates, and stage-level runtime evidence.
- Run a small all-method benchmark matrix before Week 7 robustness sweeps.

## Week 6 completion criteria

- Metric calculations are independently tested.
- All core methods can write the same comparable result schema.
- Unknown images remain free of unsupported geometric claims.
- Interrupted benchmark execution can resume without duplicate records.
- Monomodal and multimodal summaries remain explicitly separated.
- Optimization objectives and evaluation metrics are visibly distinct.
- Automatic multi-method execution exists, but evidence-backed ranking remains deferred until robustness calibration.


## Week 6 completion status

Week 6 is COMPLETE and target-validated.

Validated closure evidence:

- backend suite: 432 / 432 passed in 5.05 s;
- frozen UI suite: 64 / 64 passed in 4.68 s;
- Day 30 automatic candidates: 13 / 13 completed;
- CHECK: 0;
- failed: 0;
- validation errors: 0;
- transform agreement never consumed hidden ground truth;
- the transform medoid remained descriptive only;
- final method recommendation remained deferred.

The Week 6 contracts are now frozen. Week 7 will focus on controlled robustness sweeps and calibration evidence.
