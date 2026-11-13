# Pre-Week 8 Phase 3 Summary

**Date:** 2026-11-13

**Gate:** G3 Evaluator/firewall

**Status:** PASSED

Phase 3 preregistered and implemented the Week 8 evaluation runner without
accessing any real Week 8 source pixel or label.  The tracked camera image was
used only as a non-evidentiary development fixture.

## Delivered

- Frozen evaluation configuration and preregistration contract.
- Metadata-only planning with deterministic `w8-*` identities and collision
  rejection.
- Isolated prepare, observable-only decide/seal, and post-seal evaluate phases.
- Exact bindings for config, code, method catalog, policy gate, tolerances,
  enrollment ledger/manifest, readiness receipt, expected counts, observable
  inputs, journals, decisions, and labels.
- Recursive ground-truth firewall, locator-free executor views, append-only
  attempt events, exclusive locking, and infrastructure-only resume.
- Track A and Track B rates, mandatory strata, Wilson intervals, exact McNemar
  comparisons, runtime/diagnostic summaries, recommendation validation, and
  atomic CSV outputs.
- Synthetic-transform, verified-landmark, verified-mask/Dice, and
  technical-only endpoint contracts.
- Hash-bound G3 evidence verification in the authoritative preflight.

## Validation

- Core evaluator: 57 passed, 0 failed.
- Final CLI/preparation contract: 9 passed, 0 failed.
- Current preflight after Phase 4 Stage B validator hardening: 66 passed, 0 failed.
- Current full backend regression: 702 passed, 3 expected skips.
- Current full UI regression: 179 passed.
- Development rehearsal: 4 pairs, 12 planned attempts, 12 terminal records,
  12 geometric successes, 0 infrastructure errors, 2/2 policy abstentions,
  and one label-access event after the verified decision seal.
- Development preflight: 18 PASS / 1 BLOCK; only source enrollment remains.
- Strict preflight: 18 PASS / 11 BLOCK on expected later-phase prerequisites.

The original G3 runner/evaluator did not change during Phase 4. Its tracked
evidence hashes and regression counts were refreshed solely to bind the added
Stage B report validator and tamper tests to the authoritative preflight.

The first integration rehearsal safely stopped before label access when an
adapter diagnostic used the ambiguous name `moving_to_fixed` for an estimated
intermediate transform.  The adapter boundary now renames only those estimated
diagnostics to `estimated_*`; genuine ground-truth keys remain hard failures. A
fresh output root then passed end to end. The stopped run was not resumed or
used as evidence.

## Evidence and boundary

Machine-readable evidence is in
`reports/pre_week08_phase3_evaluator.json`.  The result is development-only and
does not satisfy G4 UI acceptance, G5 release freeze, G6 source enrollment, G7
final readiness, or G8 analysis/release closure. No Week 8 benchmark or
independent-validation claim has been made.

The next phase is Phase 4: complete and attest the five manual Stage B UI
acceptance scenarios while keeping real holdout data inaccessible.
