# Week 8 R3 corrected confirmatory cycle

## Decision and boundary

The project owner instructed the recommended corrected cycle to begin on 2026-11-16. That instruction starts remediation only. It is not a release-review attestation, data-custodian attestation, source-access authorization, G5 freeze, G6 enrollment, or G7 execution authorization.

R3 begins from commit `68e2ecf1cd7c3e1172dea1d8bfd93127d2a1cd16` and the self-hashed Phase 9 scientific-review finding at that commit. The R2 run remains archived, scientifically nonconfirmatory, and limited to source-specific software evidence. Its pixels, labels, transforms, decisions, outputs, and archives must not be copied into or rerun as R3 evidence.

## Required order

1. Finish the v2 evaluator and reporting contract.
2. Prove the frozen Wilson quantile is bound and propagated.
3. Prove method runtime and geometric valid-overlap endpoints are captured and validated.
4. Prove integrity and no-post-label-change gates are derived from verified evidence, not caller-provided booleans.
5. Prove evaluation is one-shot and fails closed on pre-existing label-access or evaluation artifacts.
6. Pass renewed development tests and G3 review.
7. Create and review a new G5 release freeze in the R3 namespace.
8. Only after G5, enroll a genuinely new, unexposed source through G6.
9. Obtain a new one-run G7 authorization before prepare → decide → evaluate.
10. Complete G8 scientific review from the R3 evidence package.

No step may be inferred from an earlier R2 approval.

## Fresh-source rule

The R2 source `nasa_pia18033_earth` is exposed and permanently ineligible for corrected confirmatory reuse. Rejection is based on all of the following, not merely the filename:

- path or prior holdout-root match;
- byte-hash match;
- canonical dataset, subject, case, acquisition, or source identity match;
- any shared lineage ancestor;
- a rename, copy, crop, transcode, or other derivative of a prior source; or
- incomplete or ambiguous provenance and lineage.

The R3 ledger and holdout manifest intentionally contain no fresh source. A custodian must supply and attest a genuinely new source after G5. Until then, G6 and G7 remain blocked.

## Namespaces

R3 uses only these new paths:

- configuration and ledger: `configs/week08_r3_*`
- holdout manifest: `data/manifests/week08_r3_holdout_sources.json`
- private intake boundary: `data/holdout/week08_r3/`
- prepared evidence: `outputs/week08_r3_holdout/`
- evaluated evidence: `outputs/week08_r3_final/`
- private archive: `outputs/week08_r3_archives/`
- public reports: `reports/week08_r3_*`

The historical R2 paths remain unchanged.

## Current gate state

Technical remediation completed on 2026-11-17 and is recorded in
`reports/week08_r3_g3_remediation.json`. This is a machine-validated G3 result,
not a G5 release-review approval.

| Gate | State | Reason |
|---|---|---|
| Corrected G3 | Passed technical remediation | Evaluator, endpoints, integrity gates, reporting enforcement, and full regression tests passed. |
| G5 | Blocked | A distinct release reviewer has not approved a new R3 freeze. |
| G6 | Blocked | G5 has not passed and no fresh source is enrolled. |
| G7 | Blocked | New G5 and G6 evidence do not exist. |
| G8 | Not started | No R3 evaluation exists. |

R3 has accessed zero source bytes and labels and has executed zero registration attempts, policy decisions, or evaluations. The cycle boundary is recorded in `reports/week08_r3_cycle_start.json`; the current technical state is recorded in `reports/week08_r3_g3_remediation.json`.
