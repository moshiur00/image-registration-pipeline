# Pre-Week 8 Phase 2 Integrity Summary

**Date:** 7 November 2026
**Status:** PASSED - G2 complete; final readiness remains blocked

Phase 2 hardened the project boundary without opening, previewing, or decoding
any Week 8 holdout image or label. Registration algorithms, the Streamlit UI,
and the frozen Day 34 policy were not changed.

## Completed work

- Upgraded `configs/week08_source_use_ledger.json` to schema v2 with all seven
  known project assets: the Week 1 pair, camera, coins, moon, and RIRE
  `training_001` CT/MR-T1. Paths, byte hashes, modalities, roles, prior use,
  canonical identities, and lineage evidence are recorded and bound by a
  canonical full-inventory digest.
- Hardened `scripts/week08_preflight.py` to reject ambiguous JSON, unsafe paths,
  malformed hashes/formats, missing or changed source bytes, false prior-use
  claims, empty/duplicate lineage, and unstructured ground-truth status strings.
- Added explicit evidence contracts for post-freeze synthetic truth, verified
  landmarks, verified masks, and technical-only cases with unavailable truth.
- Added `--final-readiness`. Strict mode verifies the actual evidence archive,
  Git tag ancestry and worktree cleanliness, release-bound artifacts,
  an exact metadata-only Phase 6 post-tag diff, clean-staging attestation,
  Stage B, source enrollment, signoffs, and dependency/environment records.
  Missing or unauthorized later-phase artifacts are `BLOCK`, never a
  releasable warning.
- Added `configs/week08_integrity_anchor.json` and the deterministic
  `scripts/week07_evidence_archive.py` workflow. The tracked manifest covers
  exactly 81 files across all four frozen Week 7 trees with per-file paths,
  sizes, SHA-256s, closure references, and an archive SHA-256.
- Restored the archive into an empty staging directory and ran the Phase 2
  integrity preflight against that staged tree rather than the original output
  directories.

## Validation

- Focused Phase 2: 63 passed, 1 expected unsupported-symlink skip, 0 failed.
- Full backend: 616 passed, 3 expected unsupported-symlink skips, 0 failed.
- Full UI: 166 passed, 0 skipped, 0 failed.
- Frozen inventory: 101/101 source/configuration files and 81/81 Week 7
  evidence files verified.
- Development preflight: 17 PASS, 1 BLOCK, 1 WARN, nonzero exit as designed.
- Strict preflight: 17 PASS, 12 BLOCK, 0 WARN, nonzero exit as designed.
- Archive: 25,764,279 bytes, SHA-256
  `0081dfb436d585f4a4d91fd83c0ee6ae8f2b6d468a78aea260a158d8b7430b26`.

The development blocker is the intentionally empty `week08_sources` list. The
development warning is the absent Phase 3 evaluator; strict mode correctly
turns it and all missing release prerequisites into blockers. These conditions
do not invalidate G2, but they prohibit a Week 8 run.

## Provenance limitations

The Week 1 upstream source/license remains explicitly unresolved, and
asset-specific redistribution terms for the scikit-image samples still require
verification. They remain development-only and must not be included in a
public redistribution package until those rights are resolved.

## Next step

Proceed to Phase 3: preregister and implement the two-track Week 8 evaluator,
unique-ID accounting, decision seal, and label-access firewall using development
fixtures only. Stage B manual acceptance may continue in parallel. Real holdout
pixels and labels remain inaccessible until the later release-candidate freeze.

Machine-readable evidence: `reports/pre_week08_phase2_integrity.json`.
