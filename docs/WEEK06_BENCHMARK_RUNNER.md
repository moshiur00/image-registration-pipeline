# Week 6 Deterministic Resumable Benchmark Runner

## Purpose

Day 28 adds experiment orchestration around the frozen Day 26 evaluation contract and the validated Day 27 metric implementation. It does not modify registration algorithms or retune method configurations.

## Scientific identity

Each attempt is defined by the pair, method, frozen configuration identifier, transform model, modality class, degradation, dimensionality, reference-evidence flags, seed, and explicit pair/method metadata. A canonical JSON representation of that identity is hashed with SHA-256 to produce a stable experiment ID.

Changing a scientifically relevant identity field creates a different experiment ID. Dictionary key ordering does not.

## Frozen plan

The runner writes `benchmark_plan.json` before execution. The file contains the complete task matrix and a deterministic plan fingerprint. A later resume must use the same plan fingerprint. The runner rejects attempts to silently mix a different matrix into an existing output directory.

## Durable records

Each terminal attempt is appended immediately to `benchmark_records.jsonl`. Terminal records include successful execution, CHECK, algorithm failure, and runner validation error. Failure records are retained for later success-rate and failure-taxonomy analysis.

The journal is the resume authority. A repeated run skips experiment IDs already present instead of executing or overwriting them.

## Long-form table

`benchmark_results.csv` is regenerated from the journal in deterministic experiment-ID order. The table retains:

- pair and modality identifiers;
- degradation;
- method family and frozen configuration identifier;
- transform model and seed;
- execution status and failure reason;
- reference-evidence label;
- transform plausibility and geometric threshold state;
- every common Day 26 metric column;
- stage-level timings;
- estimated transform, diagnostics, warnings, and task metadata as JSON columns.

Missing metrics remain empty rather than being fabricated. Failed attempts remain rows.

## Day 28 validation matrix

The development script uses three controlled translation pairs and two already validated registration implementations:

- clean monomodal translation;
- blurred monomodal translation;
- intensity-inverted simulated-multimodal translation;
- Phase Correlation;
- ECC translation.

Two seed values are included to validate pair x method x seed enumeration and deterministic experiment identity. Phase Correlation and ECC are deterministic in this study, so these seeds are orchestration probes rather than independent stochastic accuracy trials.

## Scope boundary

Day 28 does not yet:

- select candidate methods automatically;
- compare raw optimizer objectives across methods;
- define a final method ranking;
- calculate consensus or confidence;
- launch the final robustness grid.

Those remain later Week 6 and Week 7 tasks.
