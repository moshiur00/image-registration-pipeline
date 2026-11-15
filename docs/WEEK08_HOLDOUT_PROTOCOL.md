# Week 8 Holdout and Evidence Firewall Protocol

**Status:** Phase 3 evaluator/firewall complete; preparation only. No Week 8 benchmark has been run.

## 1. Evaluation roles

- `development`: source images, generated pairs, tuning seeds, model configurations and historical artifacts used in Weeks 1 to 7.
- `policy_transfer_check`: the existing `moon.png` source. It was excluded from Week 7 calibration but *was used earlier in the project*, so it cannot establish full-project independence.
- `full_project_independent`: a genuinely new, source-identified image that has never influenced algorithms, tuning, UI demonstration, selection policies or the pre-Week 8 acceptance process.
- `real_technical_only`: data without validated geometric landmarks or masks. Report physical-space and implementation behavior only, never ground-truth accuracy.

This classification is about **source provenance**, not about generated-pair seeds alone. Synthesizing a new transform from a previously used source does not make it independent at source level.

## 2. Source-use ledger

`configs/week08_source_use_ledger.json` uses schema version 2. Its prior-source
inventory contains the five tracked visible-image assets and both previously
used RIRE `training_001` acquisitions. `week08_sources` remains empty
intentionally: Phases 2 and 3 do not enroll, download, inspect or decode final
data.

The ledger records the Week 1 pair conservatively under one canonical case
because its upstream source and license are not documented. This unresolved
provenance is recorded explicitly rather than guessed. It prevents either file
or a declared derivative from later being presented as independent.

Preflight also pins a canonical digest of the complete seven-record historical
inventory. Therefore changing a known source's modality, role, dataset/case
identity, canonical source, lineage, provenance, or prior-use record fails the
inventory gate even when its path and bytes are unchanged.

### 2.1 Common entry contract

Every prior or reserved source must contain all of these fields:

| Field | Required meaning |
|---|---|
| `source_id` | Unique, stable identifier |
| `path` | Repository-relative path; new independent images go under `data/holdout/week08/` |
| `sha256` | Lowercase 64-hex SHA-256 of the source byte stream, obtained without decoding pixels |
| `format` | Canonical lowercase format name without a leading dot |
| `modality` | Modality identification based on documented provenance, not pixel inference |
| `role` | `development`, `full_project_independent`, `policy_transfer_check`, or `real_technical_only` |
| `previously_used` | Strict JSON Boolean; `true` for every asset seen before final enrollment |
| `prior_usage` | Non-empty list describing actual earlier uses; empty only for a genuinely new source |
| `reference_or_license` | Documented source/right-to-use status; unresolved legacy provenance must be explicit and remains development-only |
| `canonical_dataset_id` | Stable external or project dataset identity |
| `canonical_subject_id` | Stable subject identity, or `not_applicable` when the source has none |
| `canonical_case_id` | Stable case/asset identity inside the dataset |
| `canonical_acquisition_id` | Stable acquisition/representation identity inside the case |
| `canonical_source_id` | Canonical source identity independent of filename |
| `lineage_ancestors` | Non-empty canonical ancestor list used to detect declared derivatives |
| `lineage_evidence` | Repository-relative manifest/config path and its lowercase SHA-256 |
| `lineage_status` | Truthful lineage resolution status; unresolved provenance is never hidden |

The accepted source formats are exactly `png`, `jpg`, `jpeg`, `bmp`, `tif`,
`tiff`, `mha`, `mhd`, `nii`, `nii.gz`, and `nrrd`. A generic `.gz` suffix is
not an image format. An MHD source also requires the referenced companion data
file to be recorded and hashed through its source or ground-truth manifest.

### 2.2 Canonical novelty review

Novelty checks compare byte hashes and safe repository paths, but also compare
`canonical_source_id`, the dataset/subject/case tuple, and intersecting
`lineage_ancestors`. Thus a renamed or re-encoded RIRE `training_001` CT or
MR-T1 volume remains previously used even when its path and byte hash change.
Different canonical assets in the same broad dataset, such as `camera` and
`coins`, are not duplicates merely because their dataset ID matches.

This is a metadata/provenance control, not a perceptual-image search. It can
reject known or declared conversions, crops and derivatives; it cannot infer
an arbitrary undeclared crop without inspecting pixels. An independent data
custodian or provenance reviewer must therefore attest canonical lineage before
source bytes become accessible to the development workflow.

### 2.3 Reserved-source ground-truth contract

Every item in `week08_sources` additionally requires a `ground_truth` object
whose `type` is one of `synthetic_created_after_freeze`,
`verified_landmarks`, `verified_masks`, or `unavailable`.

For `synthetic_created_after_freeze`, the object must bind all of the following
before generation or evaluation:

- frozen generator ID and version;
- generator/config path and SHA-256;
- transform/case specification path and SHA-256;
- non-empty unique integer seeds;
- interpolation and border/overlap policy;
- Moving -> Fixed coordinate convention;
- generated-case manifest path and SHA-256;
- release-freeze identity showing that the specification was fixed first.

For `verified_landmarks` or `verified_masks`, the object must include:

- safe label path(s), lowercase SHA-256s and exact label formats;
- label provenance and applicable use/license terms;
- units and coordinate convention;
- validation notes describing correspondence, mask semantics or review;
- a manifest path and SHA-256 binding the labels to the source/case identity.

`unavailable` is permitted only for `real_technical_only` evidence. It can
support physical-space or implementation observations, never numeric geometric
correctness, TRE, Dice, a recommendation, or a confidence claim.

### 2.4 Template only

After release-candidate freeze and independent provenance review, a reserved
record has this shape (placeholders are not valid values):

```json
{
  "source_id": "new_public_source_001",
  "path": "data/holdout/week08/new_public_source_001.png",
  "sha256": "<lowercase 64-hex SHA-256>",
  "format": "png",
  "modality": "visible",
  "role": "full_project_independent",
  "previously_used": false,
  "prior_usage": [],
  "reference_or_license": "<actual public dataset citation or license>",
  "canonical_dataset_id": "<canonical dataset>",
  "canonical_subject_id": "<subject or not_applicable>",
  "canonical_case_id": "<case>",
  "canonical_acquisition_id": "<acquisition>",
  "canonical_source_id": "<stable source identity>",
  "lineage_ancestors": ["<canonical ancestor>"],
  "lineage_evidence": {
    "manifest_path": "<tracked provenance manifest>",
    "manifest_sha256": "<lowercase 64-hex SHA-256>"
  },
  "lineage_status": "<reviewed status>",
  "ground_truth": {
    "type": "synthetic_created_after_freeze",
    "generator_id": "<frozen generator>",
    "generator_version": "<version>",
    "config_path": "<tracked config>",
    "config_sha256": "<lowercase 64-hex SHA-256>",
    "case_spec_path": "<tracked specification>",
    "case_spec_sha256": "<lowercase 64-hex SHA-256>",
    "seeds": [7001],
    "interpolation": "<predeclared interpolation>",
    "border_overlap_policy": "<predeclared policy>",
    "coordinate_convention": "moving_to_fixed",
    "manifest_path": "<generated-case manifest>",
    "manifest_sha256": "<lowercase 64-hex SHA-256>",
    "release_freeze_id": "<clean release commit/tag>"
  }
}
```

This record is a **template, not an actual or registered source**. Do not
populate the ledger with fabricated references or hashes. An independently
sourced medical or other multimodal case requires verified landmarks/masks for
geometric accuracy claims; absent those, report descriptive or technical
evidence only.

### 2.5 Phase ordering

1. Phase 2 completed metadata, lineage, schema and evidence hardening with development artifacts only.
2. Phase 3 completed the evaluator/firewall with development fixtures only.
3. Phase 5 froze code, policy, configuration, analysis and release manifests at
   immutable tag `pre-week08-g5-20261114` after named human release review.
4. Phase 6 enrolls independently reviewed sources; only a custodian handles inaccessible source/label bytes before enrollment.
5. Phase 7 runs strict final readiness. Any missing or invalid source, lineage, label evidence, release identity or signoff is `BLOCK`.
6. Phase 8 performs the one-run prepare -> decide/seal -> evaluate sequence.

Phase 7 has two machine-distinct modes. Technical readiness verifies all
non-authorization gates for reviewer inspection. Final readiness additionally
requires a separate `pre_week08_phase7_authorization_v1` artifact. Preparation
uses only authorization-required final readiness and must fail before any
output write or decoder call when approval is missing or stale.

No real Week 8 source may be downloaded, previewed, decoded or used to shape
implementation before the Phase 5 freeze passes.

## 3. Do-not-peek boundary

The Stage A preflight checks names, roles, paths, file-byte SHA-256s, frozen code, and development journals. It does **not decode new image pixels**, open reference label files, call registration, select methods or calculate held-out TRE. If future data handling requires even byte-level hashing to be performed by an independent custodian, provide its attested hash in a separate review workflow.

When the Week 8 evaluator is implemented:

1. Freeze `configs/week08_frozen_baseline.json`, the Day 34 policy and the source-use ledger in Git.
2. Generate final experiment IDs in a new Week 8 namespace. Reject duplicates or overlap with Week 7 IDs.
3. For each pair, prepare observable image inputs without revealing reference transforms or labels to automatic selection.
4. Call the **unchanged** existing registration methods and compute observable-only evidence and abstention decisions.
5. Persist those decisions, warnings, failures and provenance **before** loading any ground-truth reference for evaluation.
6. Reveal labels only in a separate evaluation step. Compute TRE only where ground truth is verified, and account for all attempted cases and abstentions in denominators.
7. Never modify the frozen policy or thresholds after inspecting final labels. Further research needs a newly reserved test split.

The current Stage A script can inspect the Day 34 observable-field contract and source hashes. It **cannot certify future Week 8 runner code that has not been implemented**. Add runner-level tests and a separate label-access ordering assertion before the final benchmark.

## 4. Abort / BLOCK conditions

Do not start Week 8 final evaluation if the preflight reports `BLOCK`, such as:

- Missing or changed Week 7 benchmark evidence or Day 34 policy hash.
- Source reused while claiming full-project independence, missing source, or false checksum.
- No independently reserved source with a defensible geometric evaluation strategy.
- Corrupt/duplicate development IDs, incompatible transform conventions, or modified frozen algorithms.
- Existing files in reserved Week 8 final-output directories.

The existing RIRE technical path cannot claim registration correctness without verified landmarks or masks. Previously seen `moon` is valid for transfer assessment only and must be reported as such.

## 5. Preflight commands

```powershell
python scripts/week07_evidence_archive.py build
python scripts/week07_evidence_archive.py verify
python scripts/week07_evidence_archive.py restore --destination <new-empty-staging-directory>
python scripts/week07_evidence_archive.py verify-restored --destination <staging-directory>
python scripts/week08_preflight.py --dry-run
python scripts/week08_preflight.py
python scripts/week08_preflight.py --dry-run --final-readiness
```

The archive commands deterministically build, verify, and cleanly restore all 81
frozen Week 7 evidence files. The preflight commands are metadata/byte-hash
only. The non-dry development command writes
`outputs/week08_preflight/preflight_report.json`; any `BLOCK` returns exit code
1. Development mode currently reports 18 PASS / 1 BLOCK; the sole block is the
intentionally empty `week08_sources` enrollment. The tracked G3 evidence,
metadata-only runner probe, and Stage B human acceptance report pass. Strict
mode reported 21 PASS / 8 BLOCK immediately before the Phase 5 binding. The
manifest-bound run passes every G5-owned strict check; only the Phase 6
source/enrollment-dependent blocks remain. Runner validation, Stage B binding,
release signoff, dependency/environment binding, clean-staging restoration,
and the integrity/restoration aggregate pass. A
`WARN` can never qualify as strict final readiness.

Strict mode recognizes the release contracts
`pre_week08_release_manifest_v1`, `pre_week08_validation_v1`, and
`pre_week08_stage_b_validation_v1`. Phase 3 through Phase 5 must create and
release-bind those reports; a merely non-empty or differently versioned JSON
document is not accepted.

After the Phase 5 tag, tracked changes are limited to the Phase 6 metadata
overlay: `configs/week08_source_use_ledger.json`,
`data/manifests/week08_holdout_sources.json`,
`reports/pre_week08_source_registration.json`, and
`reports/pre_week08_release_manifest.json`; Phase 7 may additionally add
`reports/pre_week08_phase7_authorization.json`. Strict mode compares the tagged
commit with the current clean commit and blocks every other changed path.

The authorization record must bind the tagged release, reviewed G6 enrollment
commit, enrollment and runtime hashes, incident disposition, source-reuse
decision, deviation approval, restricted claims, reviewer identity/time, and
the one-run Phase 8 sequence. The readiness receipt binds the exact release
manifest and authorization hashes before any decoder can run.
