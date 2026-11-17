# Pre-Week 8 R3 release checklist

**Prepared:** 17 November 2026  
**Status:** G5 REVIEW PENDING  
**Cycle:** `week08-r3-confirmatory-20261116`  
**Implementation checkpoint:** `98b50cb071b5bea9657bd8e151b41741b1718092`  
**Proposed tag:** `pre-week08-g5r3-20261117`

This checklist presents the corrected R3 candidate for a distinct human G5
review. It does not approve G5, enroll a holdout, authorize G7, or permit any
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
- [ ] A release reviewer has approved the R3 Stage B rebinding.

## Pre-enrollment boundary

- [x] `fresh_sources` is empty.
- [x] The R3 source registration and G7 authorization artifacts are absent.
- [x] No R3 release tag exists.
- [x] G6 remains blocked until G5 passes and a genuinely new source is
  supplied by a data custodian.
- [x] G7 remains blocked until reviewed G5 and G6 evidence exists.

## Required G5 decision

- **Requested reviewer:** Md Moshiur Rahman
- **Role:** release reviewer
- **Decision: PENDING**
- **Attested UTC:** pending
- **Reviewed implementation:** `98b50cb071b5bea9657bd8e151b41741b1718092`
- **Candidate tag:** proposed only; not created

The reviewer must confirm that the corrected evaluator, complete R3 gate,
regression evidence, Stage B inheritance, frozen artifacts, and zero-access
pre-enrollment boundary are sufficient for the new G5 freeze. Approval must be
an explicit user attestation; it is never inferred from project-owner
instructions or from this technically passing package.
