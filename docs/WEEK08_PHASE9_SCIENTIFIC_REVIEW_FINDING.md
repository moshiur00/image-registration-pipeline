# Week 8 Phase 9 scientific-review finding

**Status:** Confirmatory run invalid; G8 blocked.

The automated scientific audit of commit `8bbe782247dec025a95e34cbae9b4ff075e66d0f` found release-significant preregistration nonconformance after label reveal. This is a finding record, not a human scientific or release approval. The named-reviewer fields remain unrecorded in the [machine-readable finding](../reports/week08_phase9_scientific_review_finding.json).

## Consequence

The Phase 8 execution remains completed and archived, and its original Phase 9.1/9.2 files remain immutable historical evidence. It cannot be described as a preregistration-conformant confirmatory run. Under the maintained plan's post-label defect rule, a corrected confirmatory claim requires a new evaluation cycle and a newly reserved, unexposed holdout.

The unchanged results may be retained only as source-specific, non-confirmatory software evidence. No anatomical, clinical, cross-source, external-validity, modality-wide, population, calibrated-confidence, or deployment claim is supported. The recommendation policy remains non-deployed.

## Findings

1. The frozen configuration required a two-sided 95% Wilson interval with `z = 1.959963984540054`. Three evaluator call sites omitted `z` and inherited the helper default `1.96`.
   - All 142 defined sealed intervals are mathematically affected.
   - At the stored six-decimal precision, 132/157 interval records and 141 endpoints differ.
   - In the Phase 9.2 public tables, 52/54 displayed intervals and 57 endpoints differ at six decimals.
   - The two-decimal percentages in the narrative happen not to change.
2. Two frozen secondary endpoints were not captured: method-only runtime was available for 0/294 attempts and `valid_overlap_fraction` for 0/294. Total runtime was available for 294/294 and TRE mean/median/p95 for the 284 completed attempts.
3. Two recommendation-integrity gates were assertions rather than evidence-derived checks: `no_firewall_or_integrity_incident` was hardcoded true, and the final CLI passed `no_post_label_change_attested=True` unconditionally. The recommendation result is unchanged because selected-pair count, coverage, selective correctness, and its Wilson lower-bound gate already failed.
4. The Phase 9 reporting package omitted 15 mandatory stratum rows, all nine estimable exact-McNemar comparisons, and complete TRE endpoint-distribution reporting.

## Unchanged outcomes

- Track A: 294 planned attempts, 284 completed, 10 failed, and 278 geometric successes.
- Track B: 24 eligible pairs, 0 selected, 24 abstained, 0 invalid, and 0 missing decisions.
- Coverage remains 0%; selective correctness remains undefined (`0/0`), not zero.
- The 24 pre-label decisions, terminal classifications, recorded transforms, runtimes, evidence hashes, and non-deployment disposition are unchanged.
- Similarity-versus-geometric disagreement remains `NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS`.

## Versioned reporting supplement

The following sanitized tables are regenerated deterministically from the immutable sealed aggregate summary. They correct or complete reporting only; they do not rerun registration/evaluation or restore confirmatory validity.

- [Wilson interval erratum](../reports/week08_phase9_review_tables/wilson_interval_erratum.csv)
- [Track A mandatory strata](../reports/week08_phase9_review_tables/track_a_mandatory_strata.csv)
- [Track B overall and mandatory strata](../reports/week08_phase9_review_tables/track_b_mandatory_strata.csv)
- [Track A endpoint distributions](../reports/week08_phase9_review_tables/track_a_endpoint_distributions.csv)
- [Exact paired McNemar comparisons](../reports/week08_phase9_review_tables/pairwise_exact_mcnemar.csv)

The source-identity stratum is sanitized as `enrolled_source_1`. No source, pair, or attempt identifiers; pixels; arrays; labels; transforms; or diagnostic traces are published.

Reproduce the finding and all five table bytes with attached authorized sealed evidence:

```powershell
.venv\Scripts\python.exe -B scripts\week08_phase9_scientific_review_audit.py --check
```

## Required next cycle

Before any new confirmatory run:

1. pass the frozen Wilson quantile explicitly at every evaluator call site;
2. capture or remove, before freeze, every declared endpoint;
3. derive integrity and post-label-change gates from bound evidence instead of constants;
4. make mandatory-stratum, endpoint, and paired-comparison reporting complete and test-enforced;
5. complete a new G5/G6/G7 cycle; and
6. reserve a new independent holdout that has not been exposed to this cycle.

The current holdout must not be rerun to produce a corrected confirmatory claim.
