# Pre-Week 8 R3 release checklist

**Prepared:** 19 November 2026

**Status:** RENEWED G5 APPROVED - TAG CREATION AUTHORIZED

**Cycle:** `week08-r3-confirmatory-20261116`

**Implementation checkpoint:** `98b56dac785aa455aad2c4d964b8e88869241402`

**Proposed tag:** `pre-week08-g5r3r3-20261119`

This is a technical review package, not a release approval. It incorporates
the corrected evaluator, the G5 and G6 incident dispositions, the phase-stable
test remediation, and restoration of the tracked pre-enrollment boundary.
Neither historical tag is moved or deleted: `pre-week08-g5r3-20261117` and
`pre-week08-g5r3r2-20261117` remain immutable evidence, but neither chain is
eligible for G7.

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

## Incident dispositions

- [x] `r3-g5-post-tag-phase-state-test-20261117` remains recorded; the first
  R3 G5 tag is historical and ineligible for G6.
- [x] `r3-g6-post-enrollment-phase-state-test-20261118` is recorded and
  remediated. The second G5/G6 chain is historical and ineligible for G7.
- [x] The post-G6 failure was a phase-state-coupled test fixture. The
  production evaluator and registration runtime did not require a correction.
- [x] The Phase 3 test now uses a controlled immutable fixture, and the
  production fail-closed ledger hash guard remains intact.
- [x] The tracked source ledger and holdout manifest are restored to their
  exact pre-enrollment hashes, and the obsolete live G6 registration record is
  absent.

## R3 release and authorization boundary

- [x] R3 uses a separate strict verifier; the historical R2 verifier remains
  unchanged evidence.
- [x] Missing, malformed, stale, or tampered G5, G6, or G7 metadata blocks
  final preparation before its first side effect or decoder call.
- [x] The preregistration config is not mutated after the release freeze;
  post-G5 changes are limited to the declared G6/G7 metadata paths.
- [x] The private R3 intake path is ignored by Git.
- [x] A fresh source must differ from every exposed source by path, byte hash,
  canonical identity, and complete lineage.
- [x] One-run G7 authorization must bind the tag, reviewed G6 commit, source
  metadata, runtime files, incident disposition, claim limits, and exact
  prepare -> decide -> evaluate sequence.

## Validation evidence

- [x] Candidate preflight: PASS, metadata-only, zero image or label decoding.
- [x] Focused R3 gate suite: 98 passed, 0 skipped, 0 failed.
- [x] Full regression suite: 780 passed, 3 skipped, 0 failed (783 collected).
- [x] The complete suite was rerun with a repository-scoped E: temp root after
  an earlier run exhausted the ACL-problematic C: pytest temp area. The
  incomplete infrastructure run is discarded and is not counted as evidence.
- [x] Historical Phase 9 scientific finding remains reproducible.
- [x] Git diff check passes.
- [x] R3 has zero currently enrolled sources, decoded pixels, accessed labels,
  registration attempts, policy decisions, and evaluation runs.
- [x] R3 output roots are absent or empty.

## Stage B inheritance

- [x] The inherited base is `reports/pre_week08_stage_b_validation.json`
  (`1d807cb94b1e93be6113b8b9b2ce967d932a45d5bdc836089ca56e846c433398`).
- [x] Changes under `ui/` since the tested checkpoint are Markdown only.
- [x] No UI runtime or UI test path changed.
- [x] The original 5/5 scenarios and 5/5 supplemental checks are unchanged
  inherited observations, not a new manual run.
- [x] Release reviewer Md Moshiur Rahman approved the renewed Stage B
  rebinding and both incident dispositions at `2026-11-19T18:20:10Z`.

## Pre-enrollment and source boundary

- [x] Tracked `fresh_sources` is empty and all activity counters are zero.
- [x] The tracked R3 source registration and G7 authorization are absent.
- [x] The NGA source file and private intake sidecars remain Git-ignored.
- [x] Raw NGA bytes were previously transferred and hashed under the prior G6
  authorization, but the image was never previewed or decoded; no labels,
  outcomes, preparation, decision, registration attempt, or evaluation ran.
- [x] The NGA source is not currently enrolled. Its possible reuse for renewed
  G6 requires the new G5 freeze and a separate renewed custodian approval.
- [x] G6 remains blocked pending creation and binding of the renewed G5 tag,
  followed by separate custodian rebinding.
- [x] G7 remains blocked pending reviewed G5 and G6 evidence.

## Required G5 decision

- **Requested reviewer:** Md Moshiur Rahman
- **Role:** release reviewer
- **Decision: APPROVED**
- **Attested UTC:** `2026-11-19T18:20:10Z`
- **Reviewed implementation:** `98b56dac785aa455aad2c4d964b8e88869241402`
- **Reviewed package:** `ef6968b86beeca9d9f658a9e06f696c4edc77711`
- **Candidate tag:** `pre-week08-g5r3r3-20261119` authorized for creation

Recorded approval statement:

> Approve the renewed R3 G5 release freeze and Stage B rebinding for
> implementation checkpoint 98b56dac785aa455aad2c4d964b8e88869241402,
> reviewed through package commit ef6968b86beeca9d9f658a9e06f696c4edc77711,
> including disposition of incidents r3-g5-post-tag-phase-state-test-20261117
> and r3-g6-post-enrollment-phase-state-test-20261118, under proposed tag
> pre-week08-g5r3r3-20261119 as release reviewer Md Moshiur Rahman. I approve
> the restored tracked pre-enrollment boundary with zero currently enrolled
> sources, zero pixel preview or decode, zero label or outcome access, and zero
> prepare, decide, or evaluate activity. I acknowledge that
> pre-week08-g5r3-20261117 and pre-week08-g5r3r2-20261117 remain immutable
> historical evidence and their respective chains are ineligible for further
> authorization as documented. This approval does not authorize G6 source
> rebinding, synthetic ground-truth generation, G7, or benchmark execution.

This approval is limited to renewed G5, both incident dispositions, and Stage
B rebinding. G6 enrollment and G7 one-run authorization remain separate gates.
