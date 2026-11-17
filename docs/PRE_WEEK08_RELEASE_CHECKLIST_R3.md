# Pre-Week 8 R3 release checklist

**Prepared:** 17 November 2026

**Status:** G5 APPROVED — TAG CREATION AUTHORIZED

**Cycle:** `week08-r3-confirmatory-20261116`

**Implementation checkpoint:** `98b50cb071b5bea9657bd8e151b41741b1718092`

**Proposed tag:** `pre-week08-g5r3-20261117`

This checklist records the distinct human G5 approval of the corrected R3
candidate. It does not enroll a holdout, authorize G7, or permit any source or
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
- [x] Focused R3 gate suite: 21 passed, 0 skipped, 0 failed.
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
- [x] Release reviewer Md Moshiur Rahman approved the R3 Stage B rebinding at
  `2026-11-17T19:37:41Z`.

## Pre-enrollment boundary

- [x] `fresh_sources` is empty.
- [x] The R3 source registration and G7 authorization artifacts are absent.
- [x] Creation of `pre-week08-g5r3-20261117` is authorized by the recorded G5
  approval; this checklist itself does not create the tag.
- [x] G6 remains blocked until the approved freeze is tagged and a genuinely
  new source is supplied by a data custodian.
- [x] G7 remains blocked until reviewed G5 and G6 evidence exists.

## Required G5 decision

- **Requested reviewer:** Md Moshiur Rahman
- **Role:** release reviewer
- **Decision: APPROVED**
- **Attested UTC:** `2026-11-17T19:37:41Z`
- **Reviewed implementation:** `98b50cb071b5bea9657bd8e151b41741b1718092`
- **Reviewed package:** `44d9783b2247a9033d2ce702673e641944972e47`
- **Candidate tag:** `pre-week08-g5r3-20261117` authorized for creation

Recorded approval statement:

> Approve the R3 G5 release freeze and Stage B rebinding for implementation
> checkpoint 98b50cb071b5bea9657bd8e151b41741b1718092, reviewed through package
> commit 44d9783b2247a9033d2ce702673e641944972e47, under proposed tag
> pre-week08-g5r3-20261117 as release reviewer Md Moshiur Rahman. I approve the
> zero-access pre-enrollment boundary.

This approval is limited to G5 and the Stage B rebinding. G6 fresh-source
enrollment and G7 one-run execution authorization remain separate blocked
gates.
