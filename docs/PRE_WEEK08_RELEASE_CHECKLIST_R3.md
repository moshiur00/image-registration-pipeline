# Pre-Week 8 R3 release checklist

**Prepared:** 17 November 2026

**Status:** RENEWED G5 APPROVED — TAG CREATION AUTHORIZED

**Cycle:** `week08-r3-confirmatory-20261116`

**Implementation checkpoint:** `caf7717d0f138df0c8dfe7eb95be98f3c0e2495f`

**Proposed tag:** `pre-week08-g5r3r2-20261117`

This checklist records the renewed human G5 approval after post-tag validation
found and remediated a phase-state-coupled test. The historical tag
`pre-week08-g5r3-20261117` remains immutable and ineligible for G6. This
approval does not enroll a holdout, authorize G7, or permit any source or
label decoding.

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
- [x] Release reviewer Md Moshiur Rahman approved the renewed R3 Stage B
  rebinding and incident disposition at `2026-11-17T19:52:58Z`.

## Pre-enrollment boundary

- [x] `fresh_sources` is empty.
- [x] The R3 source registration and G7 authorization artifacts are absent.
- [x] The historical tag `pre-week08-g5r3-20261117` is invalid for G6 and has
  not been moved or deleted.
- [x] Creation of `pre-week08-g5r3r2-20261117` is authorized by the renewed
  approval; this checklist itself does not create the tag.
- [x] G6 remains blocked until the renewed tag is bound and a genuinely new
  source is supplied by a data custodian.
- [x] G7 remains blocked until reviewed G5 and G6 evidence exists.

## Required G5 decision

- **Requested reviewer:** Md Moshiur Rahman
- **Role:** release reviewer
- **Decision: APPROVED**
- **Attested UTC:** `2026-11-17T19:52:58Z`
- **Reviewed implementation:** `caf7717d0f138df0c8dfe7eb95be98f3c0e2495f`
- **Reviewed package:** `8a164fe71bb31ecc4fcdc70b51634e748bd2a8c3`
- **Candidate tag:** `pre-week08-g5r3r2-20261117` authorized for creation

Recorded approval statement:

> Approve the renewed R3 G5 release freeze and Stage B rebinding for
> implementation checkpoint caf7717d0f138df0c8dfe7eb95be98f3c0e2495f,
> reviewed through package commit 8a164fe71bb31ecc4fcdc70b51634e748bd2a8c3,
> including disposition of incident r3-g5-post-tag-phase-state-test-20261117,
> under proposed tag pre-week08-g5r3r2-20261117 as release reviewer Md Moshiur
> Rahman. I approve the zero-access pre-enrollment boundary and acknowledge
> that pre-week08-g5r3-20261117 is historical and ineligible for G6.

This approval is limited to renewed G5, the incident disposition, and Stage B
rebinding. G6 enrollment and G7 one-run authorization remain separate gates.
