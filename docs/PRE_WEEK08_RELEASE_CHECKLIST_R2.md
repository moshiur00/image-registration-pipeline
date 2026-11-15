# Pre-Week 8 Release Checklist — Authorization-Hardening Cycle

**Prepared:** 15 November 2026  
**Status:** IN PROGRESS — not approved and not tagged  
**Historical release:** `pre-week08-g5-20261114` remains immutable evidence

This checklist governs the new release cycle started after the documented
Phase 7 pre-decode test incident. It does not approve G5, enroll a source,
authorize G7, or permit access to held-out pixels or labels.

## Incident disposition

- [x] The incident is tracked in `reports/pre_week08_phase7_incident.json`.
- [x] The two pre-decode artifacts were hash-verified and moved to the ignored
  incident archive.
- [x] No real image decoder or label reader ran; zero scientific attempts ran.
- [x] Canonical Week 8 final-output locations are absent or empty.
- [x] The new candidate was reset to a pre-enrollment state.
- [ ] Reuse of PIA18033 is approved during renewed G6 review.

## Machine-enforced G7 authorization

- [ ] Technical readiness and authorization-required readiness are separate.
- [ ] Missing, malformed, stale, or tampered authorization fails closed.
- [ ] Preparation cannot create directories, receipts, plans, or decoder calls
  before authorization-required readiness passes.
- [ ] Authorization binds the release commit/tag, reviewed G6 commit, source
  ledger, enrollment manifest, source registration, runtime files, incident
  disposition, source-reuse decision, deviation approval, claim limits, and
  one-run Phase 8 sequence.
- [ ] The final-readiness receipt binds the exact release manifest and Phase 7
  authorization hashes.
- [ ] No test invokes canonical final preparation against the live repository.

## Regression and release bindings

- [ ] Focused authorization, preflight, preparation, evaluator, and tamper
  tests pass with zero failures.
- [ ] Full backend and UI regressions pass with zero failures.
- [ ] Frozen baseline, integrity anchor, evaluator evidence, dependency and
  environment records, executable inventory, and validation report are
  regenerated and mutually consistent.
- [ ] Stage B release binding is renewed for the changed protected paths.
- [ ] Clean-staging restoration passes.
- [ ] The candidate worktree is clean.
- [ ] A unique candidate commit is identified.

## Pre-enrollment boundary

- [x] `week08_sources` is empty in the candidate ledger.
- [x] The Phase 6 enrollment manifest and source-registration attestation are
  absent from the candidate.
- [x] Private PIA18033 bytes remain ignored and unopened.
- [ ] The candidate tag is created only after explicit G5 approval.
- [ ] After tagging, only the declared G6/G7 metadata allowlist may change.

## Required renewed G5 signoff

- **Release reviewer:** pending
- **Decision:** pending
- **Attested UTC:** pending
- **Candidate commit:** pending
- **Candidate tag:** proposed `pre-week08-g5r2-20261115`

Required attestation: the reviewer confirms that the authorization hardening,
incident disposition, regression evidence, renewed Stage B binding, frozen
artifacts, and pre-enrollment boundary are sufficient for a new G5 freeze.
