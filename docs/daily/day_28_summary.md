# Day 28: Deterministic Resumable Benchmark Runner

## Status

Status: COMPLETE. Target Windows validation passed.

## Purpose

Day 28 converts the Day 26 evaluation contract and Day 27 metric layer into a reproducible experiment runner. The primary goal is to make interrupted benchmark execution resumable without duplicate or overwritten evidence.

## Added capability

The project now has:

- deterministic experiment IDs derived from scientific task identity;
- stable pair x method x configuration x seed enumeration;
- compatibility filtering by transform model and optional modality class;
- a frozen plan fingerprint;
- durable JSONL terminal records;
- resume and skip-completed behavior;
- explicit failed and validation-error records;
- a standardized long-form CSV table;
- preserved monomodal, multimodal, degradation, configuration, seed, timing, and failure fields.

## Factors kept fixed

- Moving -> Fixed transform convention;
- Day 26 metric semantics and evidence-availability policy;
- Day 27 metric calculations;
- all Weeks 1 to 5 algorithm implementations;
- frozen historical benchmark evidence;
- UI v0.1.

## Development validation study

The Day 28 script constructs three controlled translation pairs from the tracked camera source:

1. clean monomodal translation;
2. blurred monomodal translation;
3. intensity-inverted simulated-multimodal translation.

It executes Phase Correlation and ECC translation under two seed identities. This creates a 3 x 2 x 2 matrix of 12 attempts. The methods are deterministic here; the seeds validate runner enumeration and identity rather than stochastic accuracy.

The script immediately invokes the same frozen matrix a second time. The resume acceptance condition is zero new executions and all 12 experiment IDs skipped.

## Evidence semantics

Execution completion, transform plausibility, and geometric correctness remain separate fields. A method may complete while failing the known-ground-truth tolerance. Such a case is not deleted or relabeled as an infrastructure failure.

Unexpected executor exceptions are retained as `failed` records. Contract or identity mismatches are retained as `validation_error` records. Unit tests verify both paths.

## Local artifacts

The full local run writes:

- `benchmark_plan.json`;
- `benchmark_records.jsonl`;
- `benchmark_results.csv`;
- `benchmark_summary.json`.

These remain under `outputs/week06_day03_benchmark_runner/`. The compact tracked summary is `reports/week06_day03_benchmark_runner.json`.

## Limitations

Day 28 is an orchestration milestone, not the final benchmark. It intentionally uses only two translation methods in the development matrix. Full multi-method candidate orchestration, common evidence normalization, transform agreement, robust statistics, and recommendation are later tasks.

## Target Windows validation

Day 28 was validated on the target Windows environment.

- Backend regression: 403 / 403 passed in 4.72 s.
- UI regression: 64 / 64 passed in 5.11 s.
- Planned benchmark attempts: 12.
- First run: 12 executed, 0 skipped, 12 completed, 0 failed, 0 validation errors.
- Resume probe: 0 executed and 12 / 12 persisted experiment IDs skipped.
- Unique long-form records: 12 / 12.
- The monomodal development cases were 8 / 8 within geometric tolerance.
- The intensity-inversion development cases completed execution but were 0 / 4 within geometric tolerance, preserving the distinction between execution and correctness.

## Decision and next experiment

Day 28 is complete. The deterministic resumable benchmark-runner contract is frozen for the next work package. Day 29 may begin.

Day 29 will add framework-neutral automatic-run contracts, compatible candidate orchestration, common evidence normalization, and preservation of failure and CHECK candidates without yet claiming a final best method.
