# Pre-Week 8 R3 release checklist

**Prepared:** 17 November 2026

**Status:** RENEWED G5 REVIEW PENDING

**Cycle:** `week08-r3-confirmatory-20261116`

**Implementation checkpoint:** `caf7717d0f138df0c8dfe7eb95be98f3c0e2495f`

**Proposed tag:** `pre-week08-g5r3r2-20261117`

This checklist presents the renewed R3 G5 candidate after post-tag validation
found a phase-state-coupled test. The historical tag
`pre-week08-g5r3-20261117` remains immutable but is not eligible for G6. This
checklist does not approve G5, enroll a holdout, authorize G7, or permit any
source or label decoding.

## Corrected evaluator and reporting boundary

- [x] The v2 evaluator binds the frozen Wilson quantile and propagates it into
  the plan, decision seal, evaluation summary, and reporting contract.
- [x] Method runtime, external wall-clock runtime, and geometric valid overlap
  are captured and schema-validated.
- [x] Integrity and no-post-label-change decisions are derived from verified
  evidence rather than caller-supplied booleans.
- [x] Evaluation is one-shot and fails closed on a prior label-access or
  evaluation artifact.
- [x] Mandatory strata, endpoint tables, exact paired comparisons, sanitized
  identifiers, and report hashes are machine-enforced.
- [x] The exposed R2 holdout remains permanently closed.

## R3 release and authorization boundary

- [x] R3 uses a separate strict verifier; the historical R2 verifier remains
  unchanged evidence.
- [x] Missing, malformed, stale, or tampered G5, G6, or G7 metadata blocks
  final preparation before its first side effect or decoder call.
- [x] The preregistration config is not mutated after the release freeze;
  post-G5 changes are limited to the declared G6/G7 metadata paths.
- [x] The private R3 intake path is ignored by Git.
- [x] The R3 ledger normalizes only in memory for shared final planning; the
  tracked ledger bytes and hash remain authoritative.
- [x] A fresh source must differ from every exposed source by path, byte hash,
  canonical identity, and complete lineage.
- [x] One-run G7 authorization must bind the tag, reviewed G6 commit, source
  metadata, runtime files, no-incident disposition, claim limits, and exact
  prepare → decide → evaluate sequence.

## Validation evidence

- [x] Candidate preflight: PASS, metadata-only, zero source/label decoding.
- [x] Focused R3 gate suite: 26 passed, 0 skipped, 0 failed.
- [x] Full regression suite: 780 passed, 3 skipped, 0 failed (783 collected).
- [x] Historical Phase 9 scientific finding remains reproducible.
- [x] Git diff check passes.
- [x] R3 has zero enrolled sources, decoded pixels, accessed labels,
  registration attempts, policy decisions, and evaluation runs.
- [x] R3 output roots are absent or empty.

## Stage B inheritance

- [x] The inherited base is `reports/pre_week08_stage_b_validation.json`
  (`1d807cb94b1e93be6113b8b9b2ce967d932a45d5bdc836089ca56e846c433398`).
- [x] Changes under `ui/` since the tested checkpoint are Markdown only.
- [x] No UI runtime or UI test path changed.
- [x] The original 5/5 scenarios and 5/5 supplemental checks are identified
  as unchanged inherited observations, not as a new manual run.
- [ ] A release reviewer has approved the renewed R3 Stage B rebinding.

## Pre-enrollment boundary

- [x] `fresh_sources` is empty.
- [x] The R3 source registration and G7 authorization artifacts are absent.
- [x] The historical tag `pre-week08-g5r3-20261117` is invalid for G6 and has
  not been moved or deleted.
- [x] The corrected tag `pre-week08-g5r3r2-20261117` is proposed only and does
  not exist.
- [x] G6 remains blocked until renewed G5 approval, tag binding, and a
  genuinely new source supplied by a data custodian.
- [x] G7 remains blocked until reviewed G5 and G6 evidence exists.

## Required G5 decision

- **Requested reviewer:** Md Moshiur Rahman
- **Role:** release reviewer
- **Decision: PENDING**
- **Attested UTC:** pending
- **Reviewed implementation:** `caf7717d0f138df0c8dfe7eb95be98f3c0e2495f`
- **Candidate tag:** `pre-week08-g5r3r2-20261117` proposed only

The reviewer must confirm the recorded incident disposition, phase-stable test
fixtures, immutable cycle-start validation, complete regression evidence,
Stage B inheritance, and zero-access boundary. Approval must be explicit and
is not inherited from the invalid historical freeze.
