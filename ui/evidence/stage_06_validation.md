# Stage 6 UI Validation Record

## Stage 6.1 - Automatic Service and View Models

**Date:** 2026-10-20  
**Status:** COMPLETE - TARGET WINDOWS VALIDATED

## Scope

Stage 6.1 introduces the framework-neutral application layer required by the planned UI v0.2 Automatic Comparison Preview.

The implementation does not add or modify any Streamlit page yet. The existing manual Workbench remains frozen.

## Files added

- `ui/automatic/__init__.py`
- `ui/automatic/models.py`
- `ui/automatic/automatic_service.py`
- `ui/tests/test_automatic_service.py`
- `ui/evidence/stage_06_validation.md`

## Core behavior implemented

`AutomaticComparisonService` now provides two framework-neutral operations:

- compatibility preview without method execution;
- full automatic comparison with candidate execution and descriptive transform agreement.

The service:

- accepts a fixed and moving `ImageSource`;
- applies explicit preprocessing through the existing UI input layer;
- derives a deterministic pair identity;
- constructs an unknown-ground-truth `AutoPairProfile`;
- derives the default 2D automatic catalog from the existing UI method registry;
- applies transform-model, modality, same-shape, and optional-method compatibility rules;
- reuses the existing `RegistrationService` and validated adapters;
- computes overlap-aware common descriptive evidence when available;
- keeps method-specific diagnostics separate;
- preserves completed, CHECK, failed, and validation-error terminal states;
- calls `build_preliminary_consensus` from the frozen Week 6 agreement layer;
- converts backend evidence into JSON-serializable view models;
- keeps final method recommendation deferred.

## Ground-truth firewall

Stage 6.1 always builds operation-time automatic requests with:

```text
GroundTruthStatus.UNAVAILABLE
ReferenceEvidence()
```

The service rejects any normalized candidate view that unexpectedly contains geometric ground-truth metrics or a geometric tolerance state.

Therefore uploaded automatic-comparison workflows cannot expose:

- TRE;
- parameter error;
- geometric PASS;
- geometric CHECK.

## Compatibility policy

The default catalog is derived from the existing 2D UI method registry rather than from Streamlit-specific hardcoding.

It currently covers:

- Phase Correlation translation;
- ECC translation, rigid, and affine;
- ORB + RANSAC similarity and affine;
- SIFT + RANSAC similarity and affine;
- Mattes MI rigid 2D and affine 2D.

The existing 3D RIRE technical method remains outside the Stage 6.1 2D automatic-comparison catalog.

For `unknown` modality class, candidate discovery is intentionally permissive. This means insufficient modality information is not used to exclude a method before execution. It is not a claim that every candidate will be reliable for unknown modalities.

## View models

The new framework-neutral models include:

- `AutomaticComparisonRequest`;
- `MethodCompatibilityView`;
- `CompatibilityPreviewView`;
- `CandidateComparisonView`;
- `PairwiseAgreementView`;
- `CandidateAgreementView`;
- `AgreementComparisonView`;
- `AutomaticComparisonView`.

The complete result can be converted to a JSON-safe dictionary without importing Streamlit.

## Scientific interpretation safeguards

Stage 6.1 preserves the Week 6 rules:

- common evidence and method-specific diagnostics remain separate;
- raw optimizer objectives are not treated as a common cross-method score;
- a failed candidate remains part of the comparison record;
- an implausible candidate may remain visible while being excluded from agreement;
- one eligible transform produces `insufficient_candidates` rather than invented consensus;
- the consensus anchor is a descriptive transform medoid only;
- final best-method recommendation remains deferred until robustness calibration.

## Tests added

`ui/tests/test_automatic_service.py` contains 15 tests covering:

- deterministic preview identity;
- ground-truth-unavailable policy;
- explicit transform-model exclusion reasons;
- optional-method exclusion;
- same-shape compatibility;
- multimodal compatibility filtering;
- permissive unknown-modality discovery;
- invalid modality rejection;
- multi-candidate execution;
- operation-time ground-truth firewall;
- common-evidence normalization;
- method-diagnostic separation;
- failed-candidate preservation;
- CHECK and implausible-candidate preservation;
- transform-agreement behavior;
- insufficient-candidate behavior;
- JSON serialization;
- absence of a Streamlit dependency;
- default automatic catalog derivation from the existing registry.

## Local validation

Development environment result:

```text
Stage 6.1 focused tests
15 passed

Complete UI suite
77 passed
2 skipped

Complete backend suite
421 passed
11 skipped
```

The local skips were dependency-related:

- SimpleITK was unavailable locally;
- Streamlit was unavailable locally for the smoke test.

No backend research implementation was changed by Stage 6.1.

## Target Windows validation

Stage 6.1 was validated on the target Windows environment.

```text
Backend regression
432 / 432 passed in 5.93 s

UI regression
79 / 79 passed in 5.40 s
```

The target validation confirms:

- all existing backend tests remain green;
- all existing UI tests plus the new Stage 6.1 tests pass;
- the manual Workbench remains compatible;
- the framework-neutral automatic comparison service is stable;
- the unknown-ground-truth firewall remains intact;
- no Streamlit dependency was introduced into the Stage 6.1 service layer.

## Decision

Stage 6.1 is COMPLETE and target-validated.

Freeze the Stage 6.1 service/view-model contract and proceed to Stage 6.2:

`Automatic comparison page shell and compatibility presentation`

Stage 6.2 should add presentation only:

- navigation entry;
- fixed and moving uploads;
- transform-model selector;
- modality selector;
- optional-method control;
- input preview;
- compatible-method view;
- excluded-method view with explicit reasons.

Candidate execution from the Streamlit page remains deferred to Stage 6.3.

---

## Stage 6.2 - Automatic Comparison Page Shell and Compatibility View

**Date:** 2026-10-20  
**Status:** COMPLETE - TARGET WINDOWS VALIDATED

## Scope

Stage 6.2 introduces the Streamlit presentation shell for automatic comparison while keeping candidate execution disabled until Stage 6.3.

The new page is isolated from the manual Workbench and consumes only the frozen Stage 6.1 service contract.

## Files added or changed

Added:

- `ui/streamlit/pages/automatic_comparison.py`;
- `ui/tests/test_stage6_automatic_page.py`.

Updated:

- `ui/streamlit_app.py`;
- `ui/tests/test_streamlit_smoke.py`;
- `ui/DEVELOPMENT_STAGES.md`;
- `ui/evidence/stage_06_plan.md`;
- `ui/evidence/stage_06_validation.md`;
- `ui/README.md`.

## Page behavior

The new `Automatic comparison` navigation page provides:

- fixed-image upload;
- moving-image upload;
- affine, similarity, rigid, and translation model selection;
- unknown, monomodal, and multimodal pair classification;
- optional-method inclusion policy;
- explicit normalization, percentile clipping, and Gaussian smoothing controls;
- fixed and moving image preview;
- compatible method count and table;
- excluded method count and table;
- human-readable exclusion reasons;
- explicit ground-truth-unavailable state.

No registration candidate is executed from the Stage 6.2 page.

## Compatibility authority

The page does not contain a hardcoded registration-method list.

It constructs an `AutomaticComparisonRequest` and calls:

```text
AutomaticComparisonService.preview()
```

The Stage 6.1 service then applies the frozen backend compatibility policy for:

- transform model;
- dimensionality;
- modality assumptions;
- image-shape requirements;
- optional-method policy.

The resulting compatibility view is rendered without altering backend decisions.

## Upload isolation

Uploaded bytes are decoded in memory through the existing UI image-input layer.

The page does not write uploaded images into:

- `data/`;
- `reports/`;
- `configs/`;
- `docs/`;
- other tracked research directories.

## Scientific boundary

Stage 6.2 reports method eligibility only.

It does not expose:

- candidate execution;
- registered outputs;
- candidate evidence ranking;
- transform agreement;
- consensus anchor;
- final method recommendation;
- confidence.

Those functions remain assigned to later Stage 6 batches.

## Tests added

`ui/tests/test_stage6_automatic_page.py` contains 10 focused checks covering:

- complete 2D transform-model options;
- user-facing modality options;
- human-readable exclusion reasons;
- in-memory uploaded-pair construction;
- compatibility-table rendering data;
- excluded-method reason preservation;
- preview-only behavior with no candidate execution;
- absence of hardcoded registration method IDs in the page;
- navigation and page-header wiring;
- module import without a Streamlit import-time dependency.

The existing Streamlit smoke test is also updated to expect the new navigation entry.

## Local validation

```text
Stage 6.2 focused tests
10 passed

Complete UI suite
87 passed
2 skipped

Complete backend suite
421 passed
11 skipped
```

The local skips are dependency-related:

- SimpleITK is unavailable locally;
- Streamlit is unavailable locally for the AppTest smoke test.

## Target Windows validation

Stage 6.2 was validated on the target Windows environment.

```text
Backend regression
432 / 432 passed in 4.33 s

UI regression
89 / 89 passed in 4.56 s
```

The target validation confirms:

- all backend research regressions remain green;
- all 89 UI tests pass;
- the new Automatic comparison navigation and page shell are stable;
- compatibility presentation is driven by the frozen Stage 6.1 service;
- excluded-method reasons remain visible;
- uploaded images remain in memory;
- candidate execution is still disabled in the Streamlit page;
- the manual Workbench remains compatible.

## Stage 6.2 decision

Stage 6.2 is COMPLETE and target-validated.

Freeze the page-shell and compatibility-presentation contract and proceed to Stage 6.3:

`Candidate execution and common-evidence presentation`

Stage 6.3 may add the automatic execution action and candidate result presentation, while final ranking, calibrated confidence, and best-method recommendation remain deferred.

---

## Stage 6.3 - Candidate Execution and Common-Evidence Presentation

**Date:** 2026-10-20  
**Status:** COMPLETE - TARGET WINDOWS VALIDATED (2026-10-20)

## Scope

Stage 6.3 activates the automatic execution path from the validated Stage 6.2 page shell.

The page now runs all backend-compatible registration candidates only after an explicit user action and renders a normalized cross-method evidence table. It intentionally stops before transform-agreement presentation and candidate-detail inspection, which remain assigned to Stage 6.4.

## Files added or changed

Added:

- `ui/automatic/automatic_presenter.py`;
- `ui/tests/test_stage6_candidate_execution.py`.

Updated:

- `ui/streamlit/pages/automatic_comparison.py`;
- `ui/tests/test_stage6_automatic_page.py`;
- `ui/DEVELOPMENT_STAGES.md`;
- `ui/evidence/stage_06_plan.md`;
- `ui/evidence/stage_06_validation.md`;
- `ui/README.md`.

## Execution behavior

The Stage 6.3 page adds:

`Run automatic comparison`

Candidate execution is delegated to:

```text
AutomaticComparisonService.run()
```

The Streamlit page does not call ECC, ORB, SIFT, Phase Correlation, or Mattes MI directly.

All terminal states remain visible:

- completed;
- CHECK;
- failed;
- validation error.

A failed method is not removed from the comparison record.

## Session-state safety

The page stores one automatic result only for the active compatibility signature.

The signature incorporates:

- the backend pair ID;
- compatible method IDs;
- excluded method IDs.

This ensures that changes to images, preprocessing, transform model, modality class, or optional-method policy invalidate a stale displayed result.

## Common evidence table

Stage 6.3 displays only shared evidence:

- execution state;
- transform plausibility;
- MAE;
- MSE;
- NCC;
- SSIM;
- evaluation Mutual Information;
- valid-overlap fraction;
- runtime.

Method-specific diagnostics such as ECC objective, RANSAC inliers, or MI optimizer traces remain outside the common table.

No weighted score is computed.

## Ground-truth boundary

Automatic uploaded pairs continue to use the Stage 6.1 unknown-ground-truth policy.

The result view does not display:

- TRE;
- parameter error;
- geometric PASS;
- geometric CHECK.

The UI states that common image metrics are descriptive evidence and do not independently establish geometric correctness.

## Recommendation boundary

The backend recommendation state remains:

`deferred_until_robustness_calibration`

The Stage 6.3 page renders this as:

`Not calibrated`

No method is selected.

No confidence score is shown.

## Agreement boundary

Although the Stage 6.1 service already computes the frozen Week 6 agreement view, Stage 6.3 intentionally does not render:

- pairwise transform disagreement;
- agreement status;
- descriptive consensus anchor;
- candidate-detail diagnostics.

Those remain Stage 6.4 work.

## Tests added

`ui/tests/test_stage6_candidate_execution.py` contains 11 focused checks covering:

- stable result-cache signature;
- signature invalidation when compatible methods change;
- common-evidence table contents;
- CHECK preservation;
- failed-candidate preservation;
- explicit zero-count terminal states;
- human-readable execution and transform states;
- descriptive-evidence interpretation text;
- explicit execution-button gating;
- stale-session result invalidation;
- absence of agreement or best-method rendering;
- no Streamlit dependency in the presenter module.

The Stage 6.2 page test is updated so it continues to verify the frozen compatibility-preview contract without blocking the Stage 6.3 execution extension.

## Local validation

```text
Stage 6.3 focused tests
11 passed

Complete UI suite
98 passed
2 skipped

Complete backend suite
421 passed
11 skipped
```

The local skips are dependency-related:

- SimpleITK is unavailable locally;
- Streamlit is unavailable locally for the AppTest smoke test.

## Target Windows validation: COMPLETE

**Date:** 2026-10-20  
**Evidence source:** User-supplied Windows terminal screenshots of the complete regression-suite outcomes.

Commands executed on Windows:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
```

Observed final output:

```text
Root backend: 432 passed in 6.60 s
Isolated UI: 100 passed in 5.27 s
Failures:    0
Skips:       0
```

The isolated UI run reported `platform win32`, Python 3.12.6, pytest 9.1.1, and 100 collected tests. The backend and UI suites were run independently.

### Validation assessment

- Root backend regression gate: PASS (432 / 432).
- Full UI regression gate: PASS (100 / 100).
- Stage 6.3 local focused tests: PASS (11 passed, previously recorded).
- Target Windows validation: PASS.
- Stage 6.3 status: COMPLETE and target Windows validated.
- Stage 6.4 status: NOT STARTED; unblocked for implementation.
- Stage 6.5 status: PLANNED; NOT STARTED.

**Scientific scope remains unchanged:** No final recommendation, calibrated confidence, ranking, visible transform-agreement matrix, or candidate-detail inspection has been added by this status update. Unknown images still do not receive TRE, parameter error, or geometric PASS/CHECK.

**Remaining QA note:** The passing automated suites confirm regression coverage. A manual interactive Streamlit review of the Automatic comparison page remains recommended before a later UI v0.2 freeze; it is not claimed as completed here.

**Decision:** Close Stage 6.3 and proceed next to Stage 6.4, Transform Agreement and Candidate Inspection, when implementation is requested.



---

## Stage 6.4 - Transform Agreement and Candidate Inspection

**Implementation date:** 2026-10-20  
**Status:** COMPLETE - TARGET WINDOWS VALIDATED

### Implementation record

Stage 6.4 exposes the frozen Stage 6.1 transform agreement in the Automatic comparison Streamlit page. It provides a summary of eligible/excluded transforms, a symmetric pairwise RMS disagreement matrix in pixels, full pairwise statistics, and candidate centrality summaries in service order. Candidates excluded from agreement retain explicit reasons. When agreement status is `insufficient_candidates`, the page does not fabricate a matrix or consensus anchor.

The anchor is the descriptive transform medoid, not an evidence-calibrated best registration. All candidates remain inspectable, including CHECK, failed, and validation-error runs. Candidate detail includes execution, plausibility, Moving -> Fixed matrix, warnings, failure reasons, method diagnostics, and timings, outside the common comparison table.

Selected-candidate visual inspection uses the candidate's estimated transform to rewarp the explicitly preprocessed moving image into fixed-image geometry using existing `warp_image` and visualization utilities. This is labeled as an inspection-only reconstruction rather than the original adapter output. It neither reruns registration nor affects saved evaluation evidence.

New modules:

- `ui/automatic/agreement_presenter.py`
- `ui/automatic/candidate_inspection.py`
- `ui/tests/test_stage6_agreement_inspection.py`

Updated:

- `ui/streamlit/pages/automatic_comparison.py`

No modification to frozen `src/image_registration/`, existing Workbench or research reports.

### Scientific guardrails

- No final method recommendation, method ranking, confidence number or universal disagreement threshold.
- No ground-truth geometric correctness claim on unknown pairs.
- Matrix gaps are blank, not silently treated as zero.
- Explicit exclusions and incomplete/failed candidate records remain visible.
- Automatic-analysis export is still reserved for Stage 6.5.

### Local test results

```text
Stage 6.4 focused tests: 17 passed
Root backend: 421 passed, 11 skipped, 0 failed
Isolated UI: 115 passed, 2 skipped, 0 failed
```

The local environment lacks optional dependencies including SimpleITK and Streamlit, so the skip counts are not an authoritative Windows pass. Subsequent Windows target validation passed Stage 6.4: backend 432/432 in 7.51 s and UI 117/117 in 5.13 s, zero failures and zero skips.

### Live service smoke test

The tracked Week 1 fixed/moving PNG pair was executed through the actual `AutomaticComparisonService` with monomodal translation settings (no mocks). Both `ECC Translation` and `Phase Correlation` completed with plausible transforms. The resulting agreement status was `available`, the symmetric 2 x 2 matrix had a single pairwise RMS value of approximately 4.082 px, and the backend medoid was Phase Correlation. Both visual reconstructions produced 160 x 220 pixel arrays using the estimated transforms. Recommendation remained `deferred_until_robustness_calibration`. This is an implementation smoke test, not evidence that either transform was geometrically correct.

### Windows validation and interactive QA: COMPLETE

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
streamlit run ui/streamlit_app.py
```

Observed on Windows: 432 backend and 117 UI passing tests, with no skips. Supplied Streamlit screenshots show a four-candidate affine pair, descriptive agreement, each candidate inspection, and rewarped visual comparisons. A single-candidate no-consensus path remains covered by automated tests; manual single-candidate walkthrough is recommended during Stage 6.5 QA.

**Decision:** Stage 6.4 COMPLETE and target Windows validated on 2026-10-20. Stage 6.5 is unblocked. No claim of real-image geometric accuracy is implied.


---

## Stage 6.5 - Export, Final QA, and UI v0.2 Preview Freeze

**Implementation date:** 2026-10-20  
**Status:** IMPLEMENTATION COMPLETE - TARGET WINDOWS REGRESSION VALIDATED; final manual edge-case QA and UI v0.2 freeze pending

### Changes

- Automatic ZIP contains full unknown-GT candidate/compatibility/agreement JSON and CSV comparisons, input hashes, explicit preprocessing, method settings, diagnostic and runtime data, terminal failure statuses, and a README that limits interpretation.
- Any registered images within that ZIP are explicitly labeled `INSPECTION_ONLY`. Their reconstruction uses the recorded Moving -> Fixed transform, linear interpolation, and the existing validated `warp_image`; neither backend registration nor stored evaluation metrics are rerun or modified. Array `.npy` and display-normalized PNG are distinguished.
- Geometric source-support masks are obtained from the existing `transformed_support_mask` function rather than inferred from black pixels. These masks guide automatic Overlay, Checkerboard, Difference, and Edges visualizations without altering prior manual Workbench defaults.
- Comparison no longer counts routine unknown-reference notices as execution issues; global evaluation limitations remain visible. Human-readable method-diagnostic highlights supplement raw JSON without deriving quality scores.
- Compatibility caption switches after execution, common-evidence table gains units/tooltips, and sidebar indicates `UI v0.2 preview`.
- Export preparation occurs only on explicit click and is invalidated when the inputs/configuration or run changes. ZIP bytes are prepared in memory only.

### Local evidence

```text
Focused Stage 6.5 tests: 17 passed
UI suite: 132 passed, 2 skipped, 0 failed
Root backend suite: 421 passed, 11 skipped, 0 failed
Week 1 real-pair service check: 2 completed, 0 failed; 26-entry ZIP, both candidate image sets exported, 0 rendering errors
```

Skipped local tests depend on unavailable optional SimpleITK or Streamlit features. Subsequent authoritative target Windows regression passed fully, with no skips.

### Target Windows regression: PASSED (2026-10-20) and remaining release gate

On target Windows:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
streamlit run ui/streamlit_app.py
```

Observed results from user-supplied Windows terminal screenshots:

```text
pytest -v                           432 passed in 8.06 s; 0 failed; 0 skipped
pytest -c ui/pytest.ini ui/tests -v  134 passed in 6.80 s; 0 failed; 0 skipped
```

Interactive Windows screenshots document the main Automatic comparison path for uploaded 220 x 160 fixed/moving images, requested Affine transform and Unknown image class: four compatible and six excluded methods; four completed candidates, zero CHECK and zero failures; normalized comparison evidence; four eligible transforms and six pairwise comparisons; the descriptive ECC Affine consensus anchor; and all-candidate visual inspection with geometric source-support masking. Warnings about absent ground truth remain separate from zero actionable execution issues. No TRE, parameter error, geometric PASS, confidence or final recommendation is presented for the unknown pair.

Export screenshots show explicit preparation and download of the automatic-analysis ZIP. The Windows Explorer screenshot shows top-level `analysis.json`, `manifest.json`, `candidate_comparison.csv`, `candidate_execution_issues.csv`, `pairwise_agreement.csv`, `README.txt`, and `candidates/`. The screenshots alone do not prove every internal file was independently inspected, so exact archive-content/provenance checks remain a final QA task.

**Not yet manually evidenced:** a simulated multimodal pair, a one-compatible-candidate no-consensus case, a failed/CHECK candidate including export, and stale result/prepared-export invalidation after changing an image or preprocessing/other settings. These have automated coverage but remain open manual acceptance checks.

**Stage 6.5 decision (2026-10-20):** IMPLEMENTATION COMPLETE, TARGET WINDOWS REGRESSION PASSED, main interactive workflow and ZIP download reviewed. Final manual edge-case acceptance remains OPEN; UI v0.2 is NOT YET FROZEN. Week 7 has NOT started and recommendation/confidence calibration remains deferred.


---

## Stage 6.5 final QA patch: tie interpretation, single candidate, stale state (2026-10-20)

**Decision:** IMPLEMENTED AND LOCALLY VALIDATED. NEW WINDOWS VALIDATION PENDING; UI v0.2 NOT FROZEN.

### Root cause and boundary

For two eligible transforms, both candidates necessarily have the same pairwise RMS centrality. The frozen Week 6 backend supplies a deterministic medoid, but this does not establish a unique consensus. The UI now explicitly reports a two-candidate tie. It also reports no agreement for a single eligible transform and checks equal minimum median centrality for larger candidate sets. Raw backend evidence is preserved, not rewritten.

### Changes

- `ui/automatic/agreement_presenter.py`: descriptive `descriptive_anchor_interpretation()` function, no new ranking or threshold.
- `ui/automatic/automatic_export.py`: interpretation attached to analysis and manifest; reject mismatched request/pair or optional policy; keep original evidence and the unknown-GT firewall.
- `ui/automatic/automatic_presenter.py`: optional-method toggle included in comparison signature even if the candidate ID list stays unchanged.
- `ui/streamlit/pages/automatic_comparison.py`: show tie/no-anchor message and clear results/export/visual selection on missing or invalid pair, incompatible preview, changed signature, or re-run.
- `ui/tests/test_stage6_final_qa_patch.py`: 15 focused regression tests; previous source-contract tests adjusted to recognize centralized state invalidation and tie presentation.

### Local test results

```text
pytest -ra                           421 passed, 11 skipped (SimpleITK unavailable)
pytest -c ui/pytest.ini ui/tests -ra 147 passed, 2 skipped (SimpleITK and Streamlit unavailable)
Focused Stage 6.5 final-QA tests     15 passed
```

### Real-service checks

The included Week 1 translation fixed/moving image pair produced two compatible/completed methods, with status `two_candidate_tie`; a 26-entry export passed ZIP integrity, with `agreement_presentation` in analysis JSON. A multimodal affine request yielded one compatible Mattes MI Affine 2D method and `insufficient_candidates` agreement. This method failed to execute locally because its optional SimpleITK dependency is unavailable. The single-candidate failed result still exported successfully in a seven-entry ZIP with its terminal status intact. This is not a geometric correctness validation.

### Final Windows acceptance still required

Run the backend and UI test suites on the target environment, then verify: (1) 2-candidate no-unique-anchor message; (2) one-compatible-method path with absent agreement; (3) failed method preserved; (4) upload removal/invalid upload and transform, modality, preprocessing and optional-method changes invalidate result and prepared export; (5) freshly generated export has current pair identity and coherent agreement interpretation. Keep the UI sidebar as `v0.2 preview` until these checks pass.

Historical target results for the preceding Stage 6.5 build: 432 backend and 134 UI tests passed with no skips. These are not new-patch Windows results. Expected target counts after this patch are 432 backend and 149 UI.
