# Week 8 Holdout and Evidence Firewall Protocol

**Status:** Preparation only. No Week 8 benchmark has been run.

## 1. Evaluation roles

- `development`: source images, generated pairs, tuning seeds, model configurations and historical artifacts used in Weeks 1 to 7.
- `policy_transfer_check`: the existing `moon.png` source. It was excluded from Week 7 calibration but *was used earlier in the project*, so it cannot establish full-project independence.
- `full_project_independent`: a genuinely new, source-identified image that has never influenced algorithms, tuning, UI demonstration, selection policies or the pre-Week 8 acceptance process.
- `real_technical_only`: data without validated geometric landmarks or masks. Report physical-space and implementation behavior only, never ground-truth accuracy.

This classification is about **source provenance**, not about generated-pair seeds alone. Synthesizing a new transform from a previously used source does not make it independent at source level.

## 2. Source-use ledger

Edit `configs/week08_source_use_ledger.json` *before* using any held-out test pixels or labels for evaluation. The initial ledger contains the known general-image sources from Weeks 1 and 2 and has an empty `week08_sources` collection intentionally. It is a **partial inventory**, not a completed novelty proof: prior RIRE CT/MR-T1 identities and canonical source lineage are not yet represented. Phase 2 must reconcile those records before source enrollment or final readiness.

For each reserved source, record:

| Field | Required meaning |
|---|---|
| `source_id` | Unique, stable identifier |
| `path` | Repository-relative path; new independent images go under `data/holdout/week08/` |
| `sha256` | SHA-256 of the source file, obtained without decoding image pixels |
| `role` | `full_project_independent`, `policy_transfer_check`, or `real_technical_only` |
| `previously_used` | `true` for any image seen in the earlier project |
| `modality` | Modality identification based on documented provenance, not pixel inference |
| `reference_or_license` | Documented source and right to use it |
| `ground_truth_status` | `synthetic_created_after_freeze`, `verified_landmarks`, `verified_masks`, or `unavailable` |

For example, **after a genuinely new source has been obtained**, add a record similar to:

```json
{
  "source_id": "new_public_source_001",
  "path": "data/holdout/week08/new_public_source_001.png",
  "sha256": "<replace with the file's real 64-digit SHA-256>",
  "role": "full_project_independent",
  "previously_used": false,
  "modality": "visible",
  "reference_or_license": "<actual public dataset citation or license>",
  "ground_truth_status": "synthetic_created_after_freeze"
}
```

This record is a **template, not an actual or registered source**. Do not populate the ledger with fabricated references or hashes. An independently sourced medical or other multimodal case requires verified landmarks/masks for geometric accuracy claims; absent those, report descriptive or technical evidence only.

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
python scripts/week08_preflight.py --dry-run
python scripts/week08_preflight.py
```

Both commands are metadata-only. The latter writes `outputs/week08_preflight/preflight_report.json`. Both exit with code 1 on any `BLOCK` check. `WARN` means a limitation or future enforcement requirement remains and should be explicitly assessed before final evaluation.
