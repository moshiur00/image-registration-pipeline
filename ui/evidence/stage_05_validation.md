# UI Stage 5 Validation Evidence

Date: 2026-10-11

Status: COMPLETE - UI v0.1 FROZEN

## Stage 4 handoff

Stage 4 is functionally closed after manual validation of both evidence modes:

- curated examples with known ground truth, including Phase Correlation and ECC Affine workflows
- arbitrary uploaded fixed/moving images with ground truth unavailable

The unknown-upload workflow correctly avoids TRE, reference-parameter error, and geometric PASS/CHECK claims while retaining registration completion, runtime, transform plausibility, descriptive metrics, and diagnostics.

## Polish batch 1

Implemented presentation-only cleanup before export and final QA:

- one concise ground-truth-unavailable notice instead of duplicate notices
- `Run status` separated from `Method execution`
- method execution shown as `Success` or `Failed`
- transform direction shown as `Moving → Fixed`
- human-readable transform parameter and ground-truth metric labels
- display-only contrast normalization for the Difference diagnostic
- estimated zero-fill warp-border masking for diagnostic presentation only
- centered, more compact visual-diagnostics presentation
- stronger primary-button text contrast

The warp-border mask is not an evaluation mask. It only identifies zero-valued regions connected to the registered-image boundary for display cleanup. Metrics and registration results remain unchanged.

## Regression coverage added

`ui/tests/test_stage5_polish.py` covers:

- human-readable transform and metric labels
- Moving → Fixed presentation
- boundary-connected zero-fill masking
- display-only difference normalization
- single unknown-ground-truth notice
- primary-button text contrast protection

## Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

## Historical pending checks after polish batch 1

- run the root project suite on Windows
- run `pytest -c ui/pytest.ini ui/tests -v` on Windows
- visually review a curated result and an unknown-upload result after the polish changes
- continue Stage 5 export bundle and final QA work

## Local validation after polish batch 1

- root research suite: 364 collected; all locally available tests passed, with the existing 11 SimpleITK-dependent skips
- isolated UI suite: 59 collected; 57 passed and 2 skipped locally because Streamlit and SimpleITK are unavailable in this environment
- Python compilation: passed
- em dash count under `ui/`: 0
- non-UI repository diff against the uploaded checkpoint: no added, removed, or changed tracked files after excluding generated caches

Target Windows revalidation remains required before the Stage 5 freeze.


## Polish batch 2 and export implementation

- redundant unknown-ground-truth warning is suppressed in the Streamlit view while retained in the normalized run record
- diagnostic keys are presented with human-readable research labels
- raw diagnostics remain available only under `Raw diagnostic record`
- provenance now defaults to a compact summary; hashes and normalized parameters move under `Raw provenance`
- neutral gray is explicitly used for display-only estimated out-of-overlap regions
- diagnostic images use a narrower centered presentation
- session-local registered PNG, transform JSON, summary JSON, comparison PNG, and run-bundle ZIP downloads are implemented
- the ZIP bundle additionally contains the full-precision registered NumPy array
- export generation is framework-neutral and in memory; it never writes automatically to tracked research directories

## Release-candidate local QA

- root suite: 364 collected, 353 passed, 11 SimpleITK-dependent skips
- isolated UI suite: 64 collected, 62 passed, 2 local dependency skips
- export tests validate PNG creation, JSON serialization, ZIP contents, and full-precision NumPy round-trip
- Python compilation: passed
- UI em dash count: 0
- non-UI tracked repository files changed by Stage 5: none

## Formal Stage 5 completion

UI v0.1 passed the target Windows final QA and is frozen.

- Pre-Week-6 root regression: 364 / 364 passed.
- UI regression: 64 / 64 passed.
- Curated known-ground-truth workflow: validated.
- Unknown uploaded-image workflow: validated.
- Registered PNG, transform JSON, summary JSON, comparison PNG, and run-bundle ZIP exports: validated.
- Automatic multi-method recommendation remains deferred to Weeks 6 to 8.

Subsequent Week 6 development has preserved the frozen UI contract. After Day 27, the repository still passes 390 / 390 backend tests and 64 / 64 UI tests.
