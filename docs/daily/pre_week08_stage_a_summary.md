# Pre-Week 8 Integration: Stage A Implementation

**Current status (2026-11-13): IMPLEMENTED AND CURRENT WINDOWS REGRESSION GREEN; NOT ACCEPTED. Independent-source enrollment is BLOCKED. The evaluator identity/label-firewall contract is complete; Phase 4 human UI acceptance remains pending.**

This is a pre-evaluation safety stage, not a Week 8 evaluation or a calibration update.

## Delivered

- `scripts/week08_preflight.py`: isolated metadata-only preflight with per-check `PASS/WARN/BLOCK` and nonzero exit for blockers.
- `tests/test_week08_preflight.py`: evidence tampering, duplicate IDs, source reuse, source checksums, bad paths, workspace contamination, ground-truth status and dry-run tests.
- `configs/week08_frozen_baseline.json`: checksum manifest for 101 source/algorithm/configuration files and all 81 retained Week 7 evidence files.
- `configs/week08_source_use_ledger.json`: documented previous source identities, with no fake held-out source declared.
- `docs/WEEK08_HOLDOUT_PROTOCOL.md`: test-data roles, no-ground-truth leakage contract, procedure and limits.
- `outputs/week07_day02_full` through `outputs/week07_day05_integration`: original verified Week 7 evidence restored unchanged from the authoritative closure archive.

## Current metadata-only checks

Frozen code, policy and 81 evidence files verify. Day 32 963 attempts and Day 35 88 attempts reconcile, including execution failures, CHECK and incorrect transform outcomes. The Day 34 observable-only field contract remains unchanged. Full-project holdout independence **does not pass** because no genuinely new source is supplied, and the source used as the old Week 7 holdout (`moon`) appeared in previous project work.

The future Week 8 runner must independently implement decisions-before-label-access ordering, unique final task IDs and complete denominators. Stage A marks this as a warning, not as an already verified runtime guarantee.

## Commands

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
python scripts/week08_preflight.py --dry-run
python scripts/week08_preflight.py
```

Preflight returns `BLOCK` intentionally until a documented, truly independent source with defensible geometric evaluation is registered. **Do not override this gate to make the command green.**

## Boundaries

No changes to existing `src/image_registration`, frozen Weeks 1 to 7 algorithm configurations, Day 34 calibration, `ui`, or original Week 7 result bytes. No image decoding, held-out label access, new registration runs or method retuning.

**Current next step:** A named human Windows reviewer must execute the five
Stage B scenarios and five supplemental observations against the Phase 4
checkpoint. Independent-source enrollment comes only after release-candidate
freeze. The Stage B contract is hardened, but human acceptance remains 0/5
plus 0/5 supplemental checks; Stages C and D remain deferred/not started.

## Windows Stage A preflight path-validator correction (23 October 2026)

Windows regression exposed eight Stage A test failures while prior backend tests passed.
The original `safe_file()` walked `candidate.parents` beyond the temporary
repository root. If an ancestor managed by Windows or pytest is a symlink,
that causes the temporary fixture's required baseline files to be treated as
unsafe, preventing later check records from being emitted.

The corrected validator resolves the repository root and checks only
path components *inside* that root. It still rejects absolute/traversal
paths, symlinks or junctions *inside* the project, and resolved paths that
leave the root. Two regression tests cover these boundaries.

On the local validation environment, **18/18 focused Stage A tests passed**;
backend tests **562 passed, 11 skipped** and UI tests **147 passed, 2 skipped**
with auto-loaded third-party pytest plugins disabled to avoid a local teardown
hang. Run the normal Windows pytest commands for authoritative results.
The original frozen source hashes and all 81 Week 7 evidence files remain
unchanged; the missing independent Week 8 source is still an expected BLOCK.

The latest lightweight Windows share ZIP omitted generated `outputs/` evidence.
The corrective full ZIP restores those unchanged files from the verified
Stage A archive. Preserve them when copying the patch.

## Second Windows correction: filesystem metadata audit (23 October 2026)

The Windows rerun after the initial correction still failed eight Stage A tests
(563 passed, 2 skipped elsewhere). All eight failures were downstream of the
`frozen_baseline` path check not reaching normal audit execution. The exact
low-level Windows filesystem rejection was not present in the terminal trace.

The next correction replaces `Path.resolve()` / `Path.is_junction()`
canonicalization in `safe_file()` with **project-scoped `Path.lstat()`**.
Paths must be repository-relative, cannot contain traversal or backslashes,
and no existing path component *inside* the project may be a symbolic link
or Windows reparse point (junctions included). Ancestors above the project
are never checked or followed as candidate-relative path components.

Two additional tests cover path-resolution independence and all required
checks appearing in a staged fixture. Symlink and junction rejection are
now tested using lstat metadata. If a Windows staging check fails again, the
test helper prints all preceding check names and reasons rather than raising
a context-free `StopIteration`. **20 focused Stage A tests pass locally.**
The full local backend and UI suites and metadata-only preflight also pass
(except the intentional BLOCK for absent independent Week 8 data).
Windows revalidation is required before this issue can be marked closed.
No source algorithms, UI, frozen policies, or original Week 7 evidence
are modified.

## Superseding current validation (3 November 2026)

The later Windows regression no longer reproduces the Stage A path failures:
575 backend tests passed with 2 expected skips, and 166 UI tests passed. The
metadata-only dry-run reports 13 PASS, 1 BLOCK and 1 WARN while verifying all
101 frozen source/configuration files and 81 retained Week 7 evidence files.

This closes the Windows compatibility regression described in the two dated
correction sections above; it does **not** accept Stage A as final-ready. The
hard blocker is still the absence of a genuinely independent source. The
critical warning remains that no final evaluator yet enforces unique Week 8
task IDs and decision sealing before label access. The prior-source ledger and
evidence packaging also require Phase 2 hardening. Week 8 has not run, and no
holdout pixels or labels were accessed.
