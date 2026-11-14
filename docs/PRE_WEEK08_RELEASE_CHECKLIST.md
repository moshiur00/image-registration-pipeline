# Pre-Week 8 G5 Release Checklist

**Status:** G5 APPROVED; IMMUTABLE RELEASE CANDIDATE BOUND

**Prepared:** 2026-11-14

**Proposed immutable tag:** `pre-week08-g5-20261114`

This checklist freezes the release candidate before any independent Week 8
source is enrolled. It is not authorization to open source pixels or labels,
and it is not a Week 8 result.

## Boundary and scope

- [x] G0 through G4 are recorded as passed.
- [x] UI v0.2 is frozen; Stage C Research Evidence, interactive RIRE expansion,
  and the recommendation display path remain `DEFERRED`.
- [x] No real Week 8 source pixel or label was procured, previewed, decoded, or
  evaluated during Phase 5 preparation.
- [x] The evaluator, frozen configurations, Day 34 policy, analysis code, UI
  scope, and dependency inputs were not changed after Stage B testing.
- [x] Private enrollment bytes are excluded by `.gitignore`; the only tracked
  file below `data/holdout/week08/` is its attachment contract README.
- [x] Post-tag changes are limited to the four exact Phase 6 metadata paths
  enforced by preflight.

## Frozen evidence and integrity

- [x] Integrity anchor passes.
- [x] 101/101 immutable source/configuration files verify.
- [x] 81/81 Week 7 evidence files verify.
- [x] Deterministic archive verifies at SHA-256
  `0081dfb436d585f4a4d91fd83c0ee6ae8f2b6d468a78aea260a158d8b7430b26`.
- [x] The archive restored into a new empty staging directory and the restored
  tree verified.
- [x] The clean-staging preflight restoration test passed.
- [x] The 219-file tracked Python executable/test inventory is exact-hashed in
  `reports/pre_week08_executable_inventory.json`.

## Automated validation

- [x] Backend authoritative run: 702 passed, 3 expected Windows symlink skips,
  0 failed.
- [x] UI run: 179 passed, 0 skipped, 0 failed.
- [x] Release-critical suite: 149 passed, 1 expected Windows symlink skip,
  0 failed across 150 collected tests.
- [x] Runner identity, denominator, label-firewall, tamper, resume, strict-gate,
  and archive-restoration tests passed.
- [x] Development preflight: 18 PASS / 1 expected BLOCK
  (`heldout_source_independence` only).
- [x] Strict preflight was exercised and remained BLOCK on later-phase release
  binding and source-enrollment prerequisites, as required before G5/G6.

The first backend diagnostic used Windows system temp on `C:` while the project
is on `E:`. One final-CLI test correctly rejected that external test-source
path. The unchanged suite was rerun with `TEMP` and `TMP` in ignored,
project-local staging and passed 702/702 runnable tests. This staging constraint
and the initial diagnostic are retained in `reports/pre_week08_validation.json`;
they are not hidden or counted as product execution evidence.

## Dependency and environment freeze

- [x] `reports/pre_week08_dependency_lock.txt` exact-pins all 55 external
  distributions from the accepted environment.
- [x] A new isolated Python 3.14.2 environment installed 55/55 locked external
  distributions with zero post-install differences.
- [x] The local project built and installed as
  `image-registration-pipeline==0.1.0` with dependencies disabled after the
  lock installation.
- [x] Scientific, evaluator, pytest, and Streamlit imports passed.
- [x] The clean-install metadata-only plan passed without reading pixels or
  labels.
- [x] Exact platform, tool, input, lock, and clean-install details are recorded
  in `reports/pre_week08_environment.json`.

## Development-only runner rehearsal

- [x] Planning produced 4 pairs, 12 compatible attempts, and 2 policy-eligible
  pairs without reading pixels or labels.
- [x] Preparation used only the tracked `phase3_camera_fixture` development
  source and marked all artifacts non-final.
- [x] First decide executed and sealed 12/12 terminal records with 0
  infrastructure incidents.
- [x] Resume decide executed 0 and reused all 12 terminal records.
- [x] Evaluation read labels only after the verified decision seal.
- [x] Evaluation retained 12/12 geometric successes and 2/2 policy
  abstentions; no recommendation was deployed.
- [x] Rehearsal outputs remain ignored under
  `outputs/pre_week08_phase5_development_rehearsal_20261114/` and are not
  represented as final evidence.

## UI release rehearsal

- [x] Named Windows reviewer Md Moshiur Rahman accepted 5/5 Stage B scenarios.
- [x] The same reviewer accepted 5/5 supplemental observations.
- [x] Export provenance, stale-state clearing, failed-candidate retention,
  single-candidate agreement limits, inspection labels, RIRE caveat, and frozen
  write behavior are hash-attested in the Stage B validation report.
- [x] The tested UI commit is
  `2cb75adef4e616b34f70d7697c781b23ab861174`.
- [x] Release binding will reject protected implementation, test,
  configuration, dependency, or non-Markdown UI changes after that commit.

## Git and manifest freeze

- [x] Current implementation content is still the accepted Phase 4 checkpoint;
  Phase 5 changes are limited to release documentation, reports, and the
  private-data attachment/ignore contract.
- [x] `git diff --check` is required before the release-candidate commit.
- [x] Named release reviewer approves this checklist and the disclosed
  test-staging constraint.
- [x] Create one clean release-candidate commit containing the signed checklist
  and all Phase 5 candidate artifacts.
- [x] Create immutable tag `pre-week08-g5-20261114` at that exact commit.
- [x] Add the release manifest in a metadata-only follow-up commit so the
  manifest can name the already-immutable candidate without self-reference.
- [x] Verify the manifest binds the candidate commit/tag, dependency lock,
  environment record, validation reports, Week 7 evidence, frozen runner and
  policy/config artifacts, UI release, and executable inventory.
- [x] Rerun strict preflight; only Phase 6 source/enrollment-dependent blocks
  may remain.
- [x] Confirm the post-tag diff contains only
  `reports/pre_week08_release_manifest.json` before Phase 6 begins.

## Required G5 signoff

The named human release reviewer approved this checklist and the three Phase 5
reports. Automated checks did not provide or infer this approval.

- **Release reviewer:** Md Moshiur Rahman
- **Decision:** APPROVED — G5 release freeze
- **Attested UTC:** 2026-11-14T18:41:16Z
- **Candidate tag:** `pre-week08-g5-20261114`
- **Attestation:** The reviewer confirmed that the disclosed evidence is
  sufficient for G5, the repository may be frozen, and real Week 8 pixels and
  labels remain unopened until G7.

The immutable candidate commit/tag and metadata-only manifest overlay are the
machine-verifiable completion record. G5 is **PASSED**; Phase 6 source
enrollment remains blocked until an independent custodian provides valid
metadata and ground-truth evidence.
