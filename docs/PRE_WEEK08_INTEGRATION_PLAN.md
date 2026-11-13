# Image Registration Pipeline
## Week 8 Execution, Validation, and Release Plan

**Status:** ACTIVE PLAN - PHASE 3 COMPLETE; PHASE 4 NEXT
**Revision date:** 2026-11-13
**Authority:** This revision supersedes the earlier planning-only version at this path. It is the single maintained plan for pre-Week 8 integration, final evaluation, and release.

### 1. Purpose and final objective

Complete Week 8 without holdout leakage, post-result tuning, hidden failures, or unsupported accuracy claims.

The final evaluation has two distinct tracks:

1. **Frozen per-method benchmark:** evaluate every planned compatible method, preserving attempts, failures, CHECK, validation errors, runtime, geometric outcomes, and modality/model strata.
2. **Hidden-ground-truth decision-policy evaluation:** apply the unchanged observable-only Day 34 policy, seal decisions before label access, then measure policy coverage, selective correctness, abstention, and limitations.

The final release must make one of two truthful claims:

- a narrowly scoped decision policy was independently validated under preregistered conditions; or
- the product remains a transparent multi-method comparison and abstention system, with general recommendation/confidence explicitly deferred.

The second outcome is acceptable. A broad recommendation feature is not required for project success when the evidence does not justify it.

### 2. Planning basis

This plan reconciles:

- the completed Weeks 1-7 repository evidence and closure reports;
- *Detailed Weekly Plan - Image Registration 8 Week - Updated*, especially Weeks 6-8;
- *Image Registration Pipeline UI Development Plan*;
- *Automated Image Registration Decision-Support Plan*;
- the implemented Stage A preflight and Stage B QA harness;
- the current holdout/firewall protocol.

The external plans are reference specifications. Repository evidence and explicit gates determine actual completion status.

### 3. Verified starting state before Phase 1 checkpoint

At the start of the 3 November 2026 Phase 1 checkpoint:

- Weeks 1-7 are complete.
- Day 32 recorded 963 attempts and 840 geometric successes; all 25 Failed and 4 CHECK outcomes were retained.
- Day 35 recorded 88 attempts and 61 geometric successes; all 11 failures were retained.
- The exploratory Day 34 policy supported 51/486 development pairs and only 2/40 Day 35 combined-stress pairs, abstaining on 38/40. It is not a calibrated general-confidence model and is not deployed to the UI.
- Stage A code is implemented, but final acceptance is **BLOCKED**:
  - latest live dry-run: 13 PASS, 1 BLOCK, 1 WARN;
  - blocker: no genuinely independent Week 8 source is registered;
  - critical warning: no final evaluator yet enforces unique Week 8 IDs and decision-before-label ordering.
- The current source-use ledger is incomplete as a historical inventory because it does not yet include prior RIRE CT/MR identities and canonical lineage.
- Stage B QA support is implemented, but manual status is 0/5 and UI v0.2 is **NOT FROZEN**.
- Latest live regression in the current environment was 575 backend passed / 2 skipped and 166 UI passed. These counts are operational evidence, not yet a tracked final validation record.
- Stage C and Stage D are not started.
- No Week 8 evaluator, final-run journal, label seal, final results, report, presentation, or release snapshot exists.
- The pre-Week 8 worktree is not yet checkpointed: four tracked files are modified and the Stage A/B package is untracked.
- No Week 8 heldout benchmark has run, and no Week 8 pixels or labels have been used for development.

#### 3.1 Current checkpoint state (3 November 2026)

Phase 1 reconciled the maintained status records, reviewed the Stage A/B
package, verified the frozen inventory, and created the recoverable Git
checkpoint containing this record. Current validation is tracked in
`reports/pre_week08_phase1_checkpoint.json`: 39/39 focused Stage A/B tests,
575 backend passed with 2 expected unsupported-symlink skips, 166 UI passed,
preflight 13 PASS / 1 BLOCK / 1 WARN, and Stage B 0/5. Week 8 has not run and
no holdout pixels or labels were accessed. Phase 2 is now the next critical
path; G2-G8 have not been advanced by this checkpoint.

#### 3.2 Phase 2 integrity checkpoint (7 November 2026)

Phase 2 completed the RIRE-inclusive prior-source ledger, fail-closed source
and ground-truth schemas, strict final-readiness behavior, integrity anchoring,
and deterministic preservation of all 81 ignored Week 7 evidence files. The
tracked result is `reports/pre_week08_phase2_integrity.json`: 63 focused tests
passed with one expected unsupported-symlink skip, 616 backend tests
passed with three expected unsupported-symlink skips, and all 166 UI tests
passed. Development preflight reports 17 PASS / 1 BLOCK / 1 WARN; strict mode
reports 17 PASS / 12 BLOCK and exits nonzero. The current blockers are
intentional later-phase conditions, not Phase 2 failures. Week 8 has not run,
and no holdout pixels or labels were accessed.

#### 3.3 Phase 3 evaluator/firewall checkpoint (13 November 2026)

Phase 3 implemented the preregistered prepare -> decide/seal -> evaluate
workflow, deterministic `w8-*` identities, complete attempt accounting,
infrastructure-only resume rules, exact Track A/Track B denominators, verified
landmark/mask endpoints, and a recursive decision-phase label firewall.  Final
plans bind the source ledger, enrollment manifest, readiness receipt, frozen
gate, tolerances, code, and expected counts while exposing no source or label
locators to the executor.

The tracked G3 evidence is `reports/pre_week08_phase3_evaluator.json`: 57/57
core evaluator tests, 9/9 direct CLI/preparation tests, and 54/54 preflight
tests passed.  Full regression passed 690 backend tests with three expected
skips and all 166 UI tests.  The actual development rehearsal used only the
tracked camera fixture: 4 pairs, 12/12 sealed terminal records, zero
infrastructure errors, 12 geometric successes, and two policy abstentions.
Development preflight is 18 PASS / 1 BLOCK; the sole block is the intentionally
empty Week 8 source enrollment.  Strict preflight is 18 PASS / 11 BLOCK on
later-phase release, UI, source, signoff, environment, and restoration gates.
No real Week 8 source pixels or labels were accessed and no Week 8 benchmark
was run.

### 4. Non-negotiable scientific and engineering invariants

1. Preserve the project transform convention: **Moving -> Fixed**.
2. Do not retune frozen registration algorithms, method configurations, Day 34 thresholds, or Week 7 evidence.
3. Do not compare raw objectives across different methods as if they were commensurate.
4. Do not expose TRE, geometric PASS, anatomical correctness, calibrated confidence, or a best-method claim without the required evidence.
5. Keep Streamlit free of registration algorithms; execution must pass through the existing service/adapters.
6. Keep hidden ground truth outside the observable execution and policy request graph.
7. Persist and seal all observable records, decisions, warnings, failures, and provenance before any label loader can run.
8. Preserve every planned attempt and terminal outcome. Failed, CHECK, validation-error, infrastructure-error, and abstained cases may not disappear from reporting.
9. Previously used sources such as moon and RIRE cannot be relabeled as fully independent.
10. RIRE without verified landmarks or masks remains technical/transfer evidence only.
11. Run the final benchmark once. Only preregistered infrastructure failures may resume; poor valid results may not be rerun.
12. Make no policy, threshold, method, preprocessing, seed, task-matrix, or endpoint changes after label access.
13. Keep private/licensed source bytes and labels out of public archives unless redistribution is authorized.

### 5. Scope

#### 5.1 Priority P0

- reconcile and checkpoint the existing Stage A/B work;
- complete the historical source inventory and harden final-readiness validation;
- preregister and implement both Week 8 evaluation tracks;
- complete Stage B manual UI acceptance;
- freeze code, configs, analysis, and release artifacts before holdout exposure;
- enroll genuinely independent data with provenance and defensible ground truth;
- pass strict final readiness;
- execute once, analyze, document, demonstrate, archive, and release.

#### 5.2 Priority P1

- optional read-only Research Evidence page showing frozen Week 7 development evidence.

**Default decision:** defer Stage C to protect the P0 critical path unless it is explicitly required for the final demonstration. If included, it must be completed and retested before release-candidate freeze.

#### 5.3 Explicitly deferred unless separately approved before freeze

- automatic modality inference or PairProfiler expansion;
- automatic transform-model escalation;
- Fast/Balanced/Thorough execution profiles;
- new inverse-consistency or perturbation-stability workflows for user uploads;
- general recommendation/confidence deployment;
- new ranking weights or learned selectors;
- optional landmark/mask upload UI;
- interactive 3D RIRE expansion;
- FastAPI/React migration;
- new deep-learning or deformable methods.

These are aspirational decision-support capabilities, not prerequisites for a defensible Week 8 evaluation. They must not displace the frozen benchmark, leakage controls, or release work.

### 6. Dependency-aware delivery sequence

~~~text
Phase 0: Preserve holdout boundary
    |
Phase 1: Reconcile and checkpoint current Stage A/B work
    |
    +----------------------+-----------------------+
    |                      |                       |
Phase 2: Integrity     Phase 3: Evaluator      Phase 4: UI acceptance
hardening              preregistration/build   and scope decision
    |                      |                       |
    +----------------------+-----------------------+
                           |
Phase 5: Code/config/analysis release-candidate freeze
                           |
Phase 6: Independent-source enrollment
                           |
Phase 7: Strict final-readiness gate
                           |
Phase 8: One-run execution: prepare -> decide/seal -> evaluate
                           |
Phase 9: Analysis, reproducibility, report, demo, archive, release
~~~

Phases 2, 3, and 4 may proceed in parallel using development data only. Real holdout pixels and labels remain inaccessible until Phase 5 passes.

### 7. Phase 0 - preserve the holdout boundary

**Status:** PASSED, must remain continuously true.
**Owner:** developer/release reviewer; optional independent data custodian.

Before release-candidate freeze:

- evaluate candidate datasets only from provenance, license, modality, subject/case identifiers, and other non-pixel metadata;
- do not download into, preview, decode, or derive images inside the development workflow;
- quarantine any already acquired bytes so development code cannot access them;
- preregister source roles, source-count rationale, inclusion/exclusion rules, and the selection procedure.

**Abort condition:** if holdout pixels or labels influence runner design, case selection, seeds, thresholds, methods, metrics, UI changes, or analysis endpoints, that source is contaminated and cannot remain full_project_independent.

### 8. Phase 1 - reconcile and checkpoint current Stage A/B work

**Status:** PASSED (2026-11-03)
**Priority:** P0
**Owner:** developer; release reviewer signs off.

#### Work

1. Reconcile current status across:
   - README.md;
   - this plan;
   - Stage A/B summaries and reports;
   - reports/progress_registry.json;
   - ui/README.md;
   - ui/DEVELOPMENT_STAGES.md;
   - ui/evidence/stage_06_validation.md.
2. Preserve dated historical validation results. Add a superseding current record rather than rewriting history.
3. Separate and review the existing Stage A and Stage B changes.
4. Run focused and full regression tests.
5. Commit the current Stage A/B package as a recoverable checkpoint.
6. Do not force-add ignored outputs/** or ui/runtime/**.

#### Exit gate G1

- one coherent status everywhere: Week 7 complete, Stage A implemented but not accepted, Stage B 0/5, Week 8 not run;
- frozen Week 7 bytes unchanged;
- zero test failures and all skips documented;
- no accidental production algorithm changes;
- clean checkpoint commit exists.

**Gate evidence:** `reports/pre_week08_phase1_checkpoint.json` and the Git
commit containing it. Historical validation records remain intact and are
explicitly superseded by the current checkpoint record.

### 9. Phase 2 - integrity, ledger, preflight, and evidence hardening

**Status:** PASSED on 7 November 2026
**Priority:** P0
**Owner:** developer; provenance reviewer validates source inventory.

#### 9.1 Complete prior-source inventory

Update configs/week08_source_use_ledger.json to include:

- Week 1 and general visible-image sources;
- prior RIRE CT and MR-T1 paths, hashes, dataset ID, subject/case identity, modalities, and role;
- canonical dataset/source/subject/case identities;
- accurate prior-usage descriptions;
- provenance and lineage sufficient to detect renamed, re-encoded, cropped, or converted derivatives.

Novelty checks must use canonical lineage as well as byte hashes.

#### 9.2 Strengthen source and GT validation

Update scripts/week08_preflight.py and tests/test_week08_preflight.py to validate:

- required modality;
- Boolean previously_used;
- 64-hex SHA-256 syntax;
- safe paths and exact supported formats, including project-relevant medical formats;
- canonical source lineage and duplicates;
- source/license provenance;
- ground-truth evidence rather than a trusted status string.

For synthetic_created_after_freeze, require a frozen generator/config version, transform/case specification, seeds, interpolation and overlap policy, and manifest hash.

For verified_landmarks or verified_masks, require label paths, hashes, provenance, units, coordinate convention, and validation notes.

#### 9.3 Add strict final-readiness behavior

Development preflight may report limitations, but final-readiness mode must return BLOCK and nonzero when any of the following is missing or unfrozen:

- Week 8 runner and focused tests;
- unique-ID and label-order contract;
- source/label evidence;
- ledger and release manifest;
- clean release commit/tag;
- immutable policy/config/analysis hashes;
- clean final-output locations;
- Stage B acceptance;
- required release signoffs.

The present unconditional runner WARN cannot qualify as final readiness.

#### 9.4 Preserve ignored Week 7 evidence

Create a deterministic release mode or archive process covering all four frozen trees:

- outputs/week07_day02_full;
- outputs/week07_day03_analysis;
- outputs/week07_day04_calibration;
- outputs/week07_day05_integration.

A tracked manifest must record relative path, size, SHA-256, archive SHA-256, and closure reference for all 81 frozen evidence files. Verify the archive by extracting it into clean staging and running preflight without the original workspace.

#### Exit gate G2

- historical source inventory is complete;
- tampered lineage, schema, hashes, GT evidence, and formats fail closed;
- all 101 existing frozen source/config files and 81 Week 7 evidence files still verify;
- clean-staging evidence restoration passes;
- missing runner or source remains an explicit blocker, not a releasable warning.

**Gate evidence:** `reports/pre_week08_phase2_integrity.json`,
`reports/week07_evidence_archive_manifest.json`, and the Phase 2 checkpoint
commit. The ignored local archive is reproducible from the exact frozen trees;
its tracked manifest records SHA-256
`0081dfb436d585f4a4d91fd83c0ee6ae8f2b6d468a78aea260a158d8b7430b26`.

### 10. Phase 3 - preregister and implement the Week 8 evaluator

**Status:** PASSED (2026-11-13)
**Priority:** P0
**Owner:** developer; release/scientific reviewer approves preregistration.

No real Week 8 source pixels or labels may be used in this phase.

#### 10.1 Preregister before implementation freeze

Create a versioned configuration, proposed as configs/week08_final_evaluation.yaml, that freezes:

- source roles and source-count rationale;
- task/pair matrix;
- transform models and case distributions;
- conditions and severity levels;
- geometry and method seeds;
- frozen methods and configurations;
- primary endpoints and tolerances;
- modality/model/source-role strata;
- uncertainty method;
- policy eligibility rules;
- method and policy denominators;
- infrastructure-only rerun policy;
- final recommendation validation criteria.

The source count may not be increased after pixels are opened. A single independent source can satisfy a software gate but cannot support broad cross-source or external-validity claims.

#### 10.2 Required data roles

The preregistered design must distinguish:

1. **Independent known-GT subset:** genuinely new source identities with synthetic transforms created only after freeze, or real cases with verified landmarks/masks.
2. **Independent real subset:** preferred for full conformance with the eight-week plan. It requires verified labels for geometric claims.
3. **Policy transfer checks:** previously used sources such as moon, reported separately.
4. **Real technical-only evidence:** previously used RIRE or other unlabeled real data, reported without geometric/anatomical correctness claims.

If independent real GT cannot be secured, the core benchmark may proceed only with explicit deviation approval and a narrowed external-validity claim. It must not be described as full held-out real-data geometric validation.

#### 10.3 Runner architecture

Implemented artifacts:

- scripts/week08_prepare_holdout.py;
- scripts/week08_final_evaluation.py;
- tests/test_week08_final_evaluation.py;
- optional framework-neutral orchestration helper under src/image_registration/ that does not modify frozen algorithms;
- protocol and progress-registry updates.

Implement three isolated phases:

1. **Prepare:** automated source decoding and pair generation after freeze; write observable inputs and a separate sealed label artifact.
2. **Decide:** read observable inputs only; execute all frozen compatible methods; compute observable-only evidence; apply the frozen policy; persist every outcome; seal the complete decision journal.
3. **Evaluate:** verify the decision seal and expected counts before opening labels; compute geometric results only where GT is valid.

#### 10.4 Evaluation track A - per-method final benchmark

Report:

- all planned compatible attempts;
- Completed, CHECK, Failed, validation-error, and infrastructure-error outcomes;
- geometric success rate over the preregistered attempt denominator;
- conditional accuracy among geometrically evaluable completed cases;
- runtime and diagnostics;
- pairwise comparisons on explicitly stated common denominators;
- modality, transform-model, condition, source-role, and source-identity strata where sample size permits.

#### 10.5 Evaluation track B - frozen policy

Report:

- all eligible pairs;
- selected/support, abstained, invalid, and missing-decision counts;
- coverage = selected / eligible;
- selective correctness = correct selected / selected;
- abstention rate = abstained / eligible;
- uncertainty and raw counts;
- failures/CHECK records even when the policy abstains.

#### 10.6 Required runner tests

- deterministic w8-* IDs and no overlap with Day 32, Day 35, or another Week 8 task;
- IDs bind source, case/seed, method, model, config, and evaluation role;
- plan and expected-count hashes verify;
- early label access fails closed;
- changing labels cannot change execution, decisions, or abstention;
- source/config/policy/decision-seal tampering blocks;
- every planned attempt has exactly one final scientific record;
- resume cannot alter code/config/source/method/seed;
- success rate and conditional accuracy use separate denominators;
- coverage and selective correctness use separate denominators;
- technical-only data receive no geometric metric;
- plan/dry-run mode reads no pixels or labels.

#### Exit gate G3

- both evaluation tracks work end-to-end on development-only fixtures;
- runner/firewall/denominator/tamper tests pass;
- preflight verifies the actual runner contract;
- all code/config/analysis artifacts are ready to freeze;
- no Week 8 benchmark has run.

**Result:** PASSED. Evidence:
`reports/pre_week08_phase3_evaluator.json` and
`docs/daily/pre_week08_phase3_summary.md`.

### 11. Phase 4 - Stage B UI acceptance and final UI scope

**Status:** BLOCKED at 0/5 manual acceptance
**Priority:** P0
**Owner:** developer for harness; human Windows operator/reviewer for attestation.

This phase may proceed in parallel with Phases 2 and 3 using development-only fixtures.

#### 11.1 Harden the attestation

Update the Stage B record schema, CLI, and tests to require:

- reviewer identity;
- target Windows/platform and environment;
- date/time;
- release commit;
- observation note;
- screenshot and ZIP references;
- evidence SHA-256 hashes.

Keep private screenshots, uploads, and ZIPs under ignored ui/runtime/; publish a sanitized tracked validation report proposed as reports/pre_week08_stage_b_validation.json.

#### 11.2 Execute and attest

Pass all five current scenarios:

1. multimodal compatibility and evidence limits;
2. one compatible candidate with no invented consensus;
3. Failed/CHECK preservation in UI and export;
4. stale result/export invalidation after input or setting changes;
5. ZIP provenance, hashes, statuses, transform convention, and safety.

Also verify:

- a normal monomodal run;
- unknown uploads show no TRE/geometric PASS;
- the RIRE technical-only caveat is visible;
- candidate inspection labels are accurate;
- UI writes nothing to frozen research locations.

If the failure fixture produces no Failed/CHECK candidate, the scenario remains blocked. Create a deterministic development-only fixture; do not infer PASS.

#### 11.3 Decide optional scope

Before release-candidate freeze, record each item as INCLUDED or DEFERRED:

- Stage C Research Evidence page;
- interactive RIRE expansion;
- any dormant/narrow recommendation display path.

**Default:** defer all three. The final UI remains Automatic Comparison with descriptive agreement and no deployed recommendation/confidence.

#### Exit gate G4

- Stage B status is 5/5 manually accepted;
- exact backend/UI counts and skips are stored in the tracked validation record;
- full suites have zero failures;
- all scope decisions are explicit;
- UI v0.2 is formally frozen, or v0.2.1 is frozen if Stage C was included.

### 12. Phase 5 - release-candidate freeze

**Status:** NOT STARTED
**Priority:** P0
**Owner:** developer; release reviewer signs.

#### Required artifacts

- this maintained plan;
- docs/PRE_WEEK08_RELEASE_CHECKLIST.md;
- updated docs/WEEK08_HOLDOUT_PROTOCOL.md;
- reports/pre_week08_validation.json;
- reports/pre_week08_release_manifest.json;
- Stage B tracked validation report;
- deterministic Week 7 evidence archive and manifest;
- exact dependency lock/environment record;
- clean-install and development-fixture rehearsal records.

Before G5, define the private holdout staging policy. If bytes will be staged under the repository root, add an explicit ignore rule and a tracked README/attachment contract for data/holdout/week08 so private source or label files cannot enter a public commit accidentally.

The release manifest must cover:

- frozen algorithms and method configurations;
- Day 34 policy;
- Week 8 runner, task matrix, analysis code, and tests;
- preflight;
- source ledger and all prior-source manifests;
- dependencies and lock files;
- UI release;
- validation reports;
- Week 7 evidence hashes;
- expected executable-code inventory, rejecting unexpected additions.

#### Validation before freeze

- full backend and UI suites;
- focused preflight and runner suites;
- tampered-copy blocking rehearsal;
- clean-output and resume rehearsal on development fixtures;
- clean-environment install/smoke test;
- manual Workbench and Automatic Comparison demo rehearsal;
- optional Research Evidence rehearsal if included;
- Git diff and manifest review.

#### Exit gate G5

- clean worktree;
- immutable release-candidate commit and tag;
- evaluator, configs, policy, analysis, UI scope, and dependencies frozen;
- release checklist signed through G5;
- holdout pixels and labels still unopened by the development workflow.

### 13. Phase 6 - independent-source enrollment

**Status:** BLOCKED - no source registered
**Priority:** P0
**Owner:** data custodian/provenance reviewer; developer performs metadata-only integration.

Only after G5:

1. Receive the selected source package through a custodian or quarantined workflow.
2. Verify provenance, license, canonical dataset/subject/case identity, modality, and declared role without visual screening.
3. Hash raw bytes without decoding them.
4. Register source and label metadata in the ledger.
5. Stage actual source/label bytes privately or ignored; do not place unauthorized bytes in public archives.
6. Create a source-registration attestation and a metadata-only enrollment commit.
7. Make no code, method, config, threshold, seed, task-matrix, or endpoint changes.

The G5 code/config tag remains immutable. The G6 enrollment commit layers only the source ledger, attestation, and source-manifest hashes on that tag; together they identify the final runnable release candidate.

The strict post-tag allowlist is exact: `configs/week08_source_use_ledger.json`,
`data/manifests/week08_holdout_sources.json`,
`reports/pre_week08_source_registration.json`, and
`reports/pre_week08_release_manifest.json`. Any other path changed between the
G5 tag and the current clean enrollment commit blocks final readiness.

#### Exit gate G6

- independent-source and GT-evidence checks pass;
- hashes and canonical identities match;
- no prior-use or derivative-lineage conflict exists;
- source roles are unambiguous;
- only ledger/attestation/manifest metadata changed after G5;
- pixels and labels remain uninspected by developers.

### 14. Phase 7 - strict final-readiness gate

**Status:** BLOCKED by G3, G4, G5, and G6
**Priority:** P0
**Owner:** release reviewer.

The final benchmark may start only when:

- strict preflight returns **PASS**, not an unresolved critical WARN;
- Stage B is 5/5 accepted;
- source provenance, independence, hashes, and GT evidence verify;
- runner identity, firewall, seal, denominator, and tamper tests pass;
- release commit/tag and manifest verify;
- all frozen Week 7 evidence and Day 34 policy hashes verify;
- dependency/environment record is complete;
- clean staging can restore evidence and pass preflight;
- outputs/week08_holdout and outputs/week08_final are absent or empty;
- the signed checklist contains no open P0 item.

Any failure means **do not run**. Fixes before source exposure require a new release candidate. Fixes after enrollment invalidate G5/G6 and require renewed review.

### 15. Phase 8 - one-run execution

**Status:** NOT STARTED
**Priority:** P0
**Owner:** designated run operator; release reviewer observes records.

Expected command sequence after implementation:

~~~powershell
python scripts/week08_preflight.py --final-readiness
python scripts/week08_prepare_holdout.py --config configs/week08_final_evaluation.yaml
python scripts/week08_final_evaluation.py decide --config configs/week08_final_evaluation.yaml
python scripts/week08_final_evaluation.py evaluate --config configs/week08_final_evaluation.yaml
~~~

#### Execution rules

1. Preparation is automated; no manual source inspection or case selection occurs.
2. Create one release ID, run ID, environment record, and start record.
3. Execute every preregistered method attempt and preserve all outcomes.
4. Produce all observable evidence and policy decisions.
5. Verify expected counts, then hash and seal the complete decision journal.
6. Start a separate evaluation process that verifies the seal before label access.
7. Compute GT metrics only for valid labeled cases.
8. Apply only the preregistered infrastructure-rerun policy.

#### Permitted rerun

Only a recorded infrastructure failure may resume: process interruption, storage failure, unavailable dependency, or corrupted transport artifact. The original incident remains recorded, only affected task IDs may resume, and code/config/source/seed must remain identical.

#### Prohibited rerun

- valid poor performance;
- method failure or CHECK;
- changing seed, initialization, timeout, preprocessing, case, metric, threshold, method, or policy;
- removing an unfavorable case;
- restarting the whole benchmark after reviewing outcomes.

If a scientific or implementation defect is discovered after label reveal, report the run as invalid. A corrected confirmatory claim requires a newly reserved holdout split.

#### Exit gate G7

- all planned tasks accounted for;
- decision seal and evaluation linkage verify;
- no unauthorized rerun or post-freeze change occurred;
- immutable raw Week 8 evidence archive and tracked checksum manifest exist.

### 16. Phase 9 - final analysis, documentation, demonstration, and release

**Status:** NOT STARTED
**Priority:** P0
**Owner:** developer/analyst; scientific and release reviewers sign.

#### 16.1 Data-quality closure

Check and report:

- missing, duplicate, unexpected, or overwritten IDs;
- impossible/non-finite metric values;
- inconsistent modality/source roles;
- unrecorded failures;
- task-count and denominator reconciliation;
- source/config/policy/code/environment hashes;
- any infrastructure incidents and resumes.

#### 16.2 Required reporting

Always show raw counts and denominators for:

- planned and attempted method executions;
- terminal statuses;
- geometric success rate;
- conditional accuracy;
- policy eligibility;
- policy coverage;
- selective correctness;
- abstention rate;
- runtime and uncertainty;
- modality, model, condition, and source-role strata;
- similarity-versus-geometric disagreement;
- failure categories and limitations.

Produce separate monomodal and multimodal conclusions, followed by condition-specific guidance rather than a universal ranking.

#### 16.3 Recommendation disposition

Apply only preregistered criteria:

- if independent evidence validates a narrow policy, document the exact supported scope and abstention boundary;
- otherwise retain Automatic Comparison and explicit abstention/deferred recommendation.

Do not deploy a new recommendation UI after label access unless a dormant, fully tested activation path was included before G5. Otherwise deployment belongs to a future cycle with newly reserved evaluation data.

#### 16.4 Release deliverables

- final machine-readable summaries and tables;
- robustness/runtime/failure figures;
- clean reproduction of at least one headline table and one figure;
- final README and API/reproduction documentation;
- final technical report;
- presentation and timed demo rehearsal;
- dependency lock and environment record;
- immutable public release archive and authorized private evidence package;
- archive/checksum manifests;
- final Git tag/release snapshot;
- updated progress registry and closure summary.

#### Exit gate G8

- a new user can install, smoke-test, and reproduce a representative result from documentation;
- every final table/figure traces to frozen config and machine-readable evidence;
- failures and limitations are documented as clearly as successes;
- public/private evidence boundaries are verified;
- all mandatory P0 objectives are signed complete;
- no post-label tuning occurred.

### 17. Metric definitions to preregister

Exact tolerances and uncertainty methods belong in the frozen Week 8 config. The following meanings are fixed:

| Metric | Required denominator |
|---|---|
| Method execution completion | completed attempts / all planned compatible attempts |
| Geometric success rate | geometrically successful attempts / all preregistered attempts eligible for that metric |
| Conditional accuracy | geometrically successful attempts / geometrically evaluable completed attempts |
| Policy coverage | selected pairs / all policy-eligible pairs |
| Selective correctness | correct selected pairs / selected pairs |
| Abstention rate | abstained pairs / all policy-eligible pairs |
| Infrastructure incident rate | infrastructure incidents / all planned attempts |

Do not conflate success rate with conditional accuracy or coverage with selective correctness.

### 18. Change control and global abort policy

#### Before G5

Changes are permitted only with plan/config updates, tests, and recorded review.

#### After G5 but before enrollment

Any release-critical change requires a new release-candidate commit, tag, manifest, regression, and G5 signoff.

#### After G6

No code, config, policy, seed, method, task-matrix, endpoint, or analysis change is permitted. A required change returns the project to a new evaluation cycle and may require a new independent source set.

#### After label access

- never retune on the Week 8 labels;
- do not add or remove cases to improve results;
- deterministic table/figure regeneration from immutable records is allowed;
- reporting-only corrections must be versioned and disclosed;
- outcome-affecting corrections invalidate confirmatory reuse of the same holdout.

#### Global abort conditions

Do not begin or continue final evaluation when any of the following holds:

- preflight BLOCK or critical runner WARN;
- ambiguous provenance, lineage, license, or GT evidence;
- label access before decision sealing;
- dirty/unfrozen release-critical files;
- policy/config/evidence hash mismatch;
- duplicate/missing IDs;
- contaminated output directory;
- denominator mismatch or missing terminal records;
- Stage B release acceptance incomplete;
- unauthorized public redistribution risk;
- post-label tuning request.

Every abort must produce a tracked incident record with phase, affected IDs/artifacts, label-exposure status, recoverability, and whether new holdout data are required.

### 19. Evidence packaging rules

Because outputs/** and ui/runtime/** are ignored:

- do not assume Git preserves Week 7 or Week 8 raw evidence;
- create deterministic archives with tracked path/size/hash manifests;
- validate archives in clean staging;
- keep UI screenshots/ZIPs private while tracking their hashes in sanitized attestations;
- exclude caches, temporary uploads, stale outputs, and accidental labels;
- exclude private/licensed holdout data from public bundles unless authorized;
- provide attachment instructions for authorized data packages.

### 20. Roles and required human inputs

| Role | Responsibility |
|---|---|
| Developer / Codex | Code, tests, configs, manifests, documentation, automated QA |
| UI operator / reviewer | Real Windows walkthrough, screenshots/ZIP inspection, attestation |
| Data custodian / provenance reviewer | Independent source selection, custody, licensing, identity and hash approval |
| Scientific reviewer | Preregistration, metrics, denominators, uncertainty, claim scope |
| Release reviewer | Gate signoff, clean freeze, archive, demo and final release approval |

One person may hold multiple roles, but every attestation must identify the acting reviewer.

### 21. Maintained gate register

Use only NOT STARTED, IN PROGRESS, PASSED, BLOCKED, or DEFERRED.

| Gate | Current status | Evidence / blocking condition |
|---|---|---|
| G0 Holdout boundary | PASSED | No Week 8 pixels/labels accessed |
| G1 Reconcile/checkpoint | PASSED | `reports/pre_week08_phase1_checkpoint.json`; recoverable checkpoint commit contains the reconciled Stage A/B package |
| G2 Integrity/preflight hardening | PASSED | `reports/pre_week08_phase2_integrity.json`; ledger v2, strict mode, 101/101 + 81/81 verification, deterministic archive and clean restore passed |
| G3 Evaluator/firewall | PASSED | `reports/pre_week08_phase3_evaluator.json`; 120 focused tests, 12/12 sealed development attempts, hash-bound preflight contract, no real Week 8 access |
| G4 UI acceptance/scope | BLOCKED | 0/5 manual scenarios; UI v0.2 not frozen |
| G5 Release-candidate freeze | NOT STARTED | Checklist, manifest, lock, clean tag absent |
| G6 Source enrollment | BLOCKED | week08_sources is empty |
| G7 Final readiness/execution | BLOCKED | Depends on G4-G6 and the remaining strict release/readiness prerequisites |
| G8 Analysis/release closure | NOT STARTED | Week 8 has not run |

Update this table and link the tracked evidence whenever a gate changes.

### 22. Validation commands

Current commands:

~~~powershell
git status --short
git diff --check
python -m pytest -v
python -m pytest -c ui/pytest.ini ui/tests -v
python -m pytest tests/test_week08_preflight.py tests/test_week07_evidence_archive.py -v
python scripts/week07_evidence_archive.py build
python scripts/week07_evidence_archive.py verify
python scripts/week07_evidence_archive.py restore --destination <new-empty-staging-directory>
python scripts/week07_evidence_archive.py verify-restored --destination <staging-directory>
python scripts/week08_preflight.py --dry-run
python scripts/week08_preflight.py --dry-run --final-readiness
python scripts/pre_week08_stage_b_ui_qa.py prepare
python scripts/pre_week08_stage_b_ui_qa.py status
~~~

Phase 3 commands now available:

~~~powershell
python -m pytest tests/test_week08_preflight.py tests/test_week08_final_evaluation.py tests/test_week08_phase3_cli.py -v
python scripts/week08_final_evaluation.py plan --config configs/week08_final_evaluation.yaml
~~~

Never run prepare, decide, or evaluate on real Week 8 data before G7.

### 23. Immediate next actions

1. Execute and sign off the five Stage B manual UI acceptance scenarios; freeze the final UI scope.
2. Record Stage C, RIRE UI, and recommendation UI as deferred unless explicitly approved before G5.
3. Prepare the Phase 5 release checklist, dependency/environment record, validation report, clean-restoration evidence, and immutable release-candidate tag.
4. Keep real holdout pixels and labels inaccessible until the release candidate is frozen.

**Current boundary:** This revision records completed Phase 3 evaluator and
firewall controls. It does not procure or enroll data, open real heldout pixels
or labels, modify frozen algorithms/policy, complete manual UI acceptance,
freeze a release candidate, or run Week 8.
