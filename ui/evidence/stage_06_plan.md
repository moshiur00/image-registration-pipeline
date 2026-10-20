# Stage 6 UI Plan: Automatic Comparison Preview

**Plan date:** 2026-10-20  
**Status:** Stages 6.1-6.4 COMPLETE and Windows validated; Stage 6.5 prior Windows regression VALIDATED (432 backend / 134 UI). Final QA patch locally complete; NEW Windows regression and manual acceptance pending; v0.2 is NOT frozen.  
**Target:** UI v0.2 preview before Week 7  
**Parent record:** `ui/DEVELOPMENT_STAGES.md`

## Purpose

Stage 6 integrates the completed Week 6 automatic-registration infrastructure into the research UI.

The goal is to let a user provide a fixed image and moving image, inspect which methods are compatible, execute multiple candidates automatically, compare normalized evidence, inspect transform-space disagreement, and review a preliminary descriptive consensus anchor without requiring ground truth.

Stage 6 does not implement final method ranking, confidence, or best-method recommendation.

## Scientific boundary

The UI may expose:

- compatibility filtering;
- multi-method execution;
- candidate terminal states;
- common descriptive evidence;
- transform plausibility;
- valid overlap;
- runtime;
- method-specific diagnostics;
- transform disagreement;
- descriptive transform medoid;
- candidate-level exports.

The UI must not claim:

- geometric correctness when ground truth is unavailable;
- that a consensus anchor is the correct registration;
- that the candidate with the best NCC, SSIM, MI, or runtime is the best method;
- calibrated confidence;
- final method recommendation.

## User workflow

```text
Fixed + Moving
      |
      v
Choose transform model and modality class
      |
      v
Inspect compatible and excluded methods
      |
      v
Run automatic comparison
      |
      v
Review candidate evidence and terminal states
      |
      v
Review transform disagreement
      |
      v
Inspect descriptive consensus anchor
      |
      v
Open candidate details or export analysis
```

## Page structure

### Header

Title:

`Automatic Registration Comparison`

Subtitle:

`Run compatible registration methods on one image pair and compare their evidence without requiring ground truth.`

Research-status note:

`Experimental decision-support workflow. Final method recommendation and confidence calibration are not yet enabled.`

### Input pair

Controls:

- fixed image;
- moving image;
- requested transform model;
- modality class;
- include optional methods;
- preprocessing expander.

The page should not ask the user to manually select candidate algorithms.

### Compatibility preview

Show compatible candidates and an expandable excluded-method section.

Every excluded method must include the reason supplied by the backend compatibility rules.

### Execution

Primary action:

`Run automatic comparison`

Render per-candidate progress where practical.

### Result summary

Show:

- compatible count;
- completed count;
- CHECK count;
- failed count;
- ground-truth status;
- agreement status;
- recommendation status.

### Candidate evidence table

Show only cross-method evidence:

- execution;
- transform plausibility;
- MAE;
- MSE;
- NCC;
- SSIM;
- evaluation MI;
- valid overlap;
- runtime.

Do not build a combined score.

### Agreement

Show:

- eligible transforms;
- pairwise comparisons;
- median disagreement;
- agreement status;
- descriptive anchor.

Use the required explanation:

`The consensus anchor is the candidate whose estimated transform is most central to the candidate set. It is not a validated best-method recommendation.`

### Pairwise matrix

Display RMS transform-space disagreement over the shared deterministic control grid.

### Candidate inspection

Each candidate can expose:

- registered image;
- transform;
- common evidence;
- method diagnostics;
- visual diagnostics;
- provenance.

### Ground-truth explanation

For unknown uploads, show one concise notice only:

`Ground truth is unavailable for this image pair. TRE, parameter error, and geometric correctness are therefore not reported. Candidate comparison uses execution evidence, transform plausibility, descriptive image metrics, overlap, diagnostics, runtime, and transform agreement.`

### No-recommendation explanation

Explain that Week 7 robustness experiments are required to calibrate:

- thresholds;
- confidence;
- ranking evidence;
- consensus interpretation;
- abstention.

### Export

Provide:

`Download automatic analysis`

The ZIP should contain:

```text
summary.json
pair_specification.json
candidate_table.csv
agreement_summary.json
pairwise_disagreement.csv
inputs/fixed.png
inputs/moving.png
candidates/<method_id>/registered.png
candidates/<method_id>/transform.json
candidates/<method_id>/evidence.json
candidates/<method_id>/diagnostics.json
```

## Architecture

Backend authority:

```text
src/image_registration/
    automatic_registration.py
    automatic_agreement.py
```

UI integration:

```text
ui/automatic/
    __init__.py
    models.py
    automatic_service.py
    automatic_presenter.py
    agreement_presenter.py
    automatic_exports.py
```

Tests:

```text
ui/tests/
    test_automatic_service.py
    test_automatic_presenter.py
    test_agreement_presenter.py
    test_automatic_exports.py
```

Streamlit remains a rendering layer only.

## Development sequence

### 6.1 Service and view models - COMPLETE

Implemented framework-neutral UI contracts and an `AutomaticComparisonService`.

Added:

- `ui/automatic/__init__.py`;
- `ui/automatic/models.py`;
- `ui/automatic/automatic_service.py`;
- `ui/tests/test_automatic_service.py`.

The service reuses the existing registration adapters, preserves the unknown-ground-truth firewall, normalizes common evidence, retains failures and CHECK states, and calls the frozen Week 6 transform-agreement layer.

Target Windows validation completed successfully:

```text
Backend regression
432 / 432 passed in 5.93 s

UI regression
79 / 79 passed in 5.40 s

Stage 6.1 focused tests
15 passed
```

No Streamlit dependency is introduced in the Stage 6.1 service layer.

Stages 6.1, 6.2, and 6.3 are complete and target Windows validated. Stage 6.3 candidate execution and common-evidence presentation is frozen at its verified scope. At the Stage 6.3 closure, Stage 6.4 had not started. Stage 6.4 is now complete and Windows validated. Stage 6.5 is implemented and passed its target Windows regression; the main interactive workflow and export were reviewed. Final manual edge-case QA and the formal UI v0.2 freeze remain pending.

### 6.2 Page shell - COMPLETE AND TARGET WINDOWS VALIDATED

Implemented the separate `Automatic comparison` page shell.

Added:

- `ui/streamlit/pages/automatic_comparison.py`;
- navigation wiring in `ui/streamlit_app.py`;
- `ui/tests/test_stage6_automatic_page.py`;
- updated Streamlit smoke-test navigation expectation.

The page now provides:

- fixed and moving uploads;
- requested transform model;
- modality class;
- optional-method policy;
- explicit shared preprocessing;
- input preview;
- compatible-method summary;
- excluded-method reasons.

The page obtains compatibility exclusively through `AutomaticComparisonService.preview()`. It does not call candidate execution and does not hardcode the registration method catalog.

Local validation:

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

The local skips were dependency-related.

Target Windows validation completed successfully:

```text
Backend regression
432 / 432 passed in 4.33 s

UI regression
89 / 89 passed in 4.56 s
```

Stage 6.2 is COMPLETE and frozen. Stage 6.3 may begin.

### 6.3 Candidate execution - COMPLETE AND TARGET WINDOWS VALIDATED

Implemented candidate execution through the frozen Stage 6.1 service contract.

Added:

- `ui/automatic/automatic_presenter.py`;
- `ui/tests/test_stage6_candidate_execution.py`;
- Stage 6.3 execution and result rendering in `ui/streamlit/pages/automatic_comparison.py`.

The page now:

- requires an explicit `Run automatic comparison` action;
- executes all compatible candidates through `AutomaticComparisonService.run()`;
- preserves completed, CHECK, failed, and validation-error terminal states;
- shows normalized common evidence only;
- keeps method-specific diagnostics outside the shared comparison table;
- preserves candidate warnings and failure reasons;
- invalidates stale session results when pair specification or compatibility changes;
- reports recommendation state as not calibrated;
- does not render agreement, consensus, ranking, confidence, or a winner.

Local validation:

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

Target Windows validation completed on 2026-10-20. The user supplied terminal screenshots for both required commands:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
```

Observed results:

```text
Backend: 432 / 432 passed in 6.60 s; 0 failed; 0 skipped.
UI:      100 / 100 passed in 5.27 s; 0 failed; 0 skipped.
```

Stage 6.3 is now COMPLETE and target Windows validated. This clears the automated regression gate for Stage 6.4. A manual interactive Streamlit visual check remains recommended and is not represented as completed.

### 6.4 Agreement - COMPLETE AND TARGET WINDOWS VALIDATED

Implemented: read-only pairwise disagreement matrix and statistics, explicit agreement eligibility/exclusions, descriptive medoid anchor, all-candidate detail expanders, and inspection-only image reconstruction with the existing visual utilities. The existing Stage 6.1 service and validated backend were not modified.

Local regression: 17 focused tests passed; backend 421 passed and 11 skipped; UI 115 passed and 2 skipped. Target Windows regression passed: backend 432/432 (7.51 s), UI 117/117 (5.13 s). User-provided Streamlit screenshots verify upload, four completed affine candidates, agreement, descriptive anchor, candidate detail and visual inspection. Stage 6.4 is frozen at its verified scope; no recommendation, ranking, confidence or universal threshold has been introduced.

### 6.5 Export and freeze - IMPLEMENTATION COMPLETE; WINDOWS REGRESSION VALIDATED; FINAL QA PENDING

Implemented: in-memory ZIP export with manifest, method settings, input hashes, evidence JSON, CSV summaries, candidate diagnostics, and explicitly labeled inspection-only registered images; geometric support masking for automatic visualization; clear separation between execution issues and missing-GT limitations; diagnostic highlights; caption, table and sidebar polish; and 17 new focused tests.

Local: backend 421 passed / 11 skipped; UI 132 passed / 2 skipped. Real Week 1 translation-pair smoke check successfully generated automatic-analysis evidence and images. **Target Windows gate PASSED on 2026-10-20:** 432 backend passed in 8.06 s, 134 UI passed in 6.80 s, with no failures or skips. Main Streamlit screenshots show a successful uploaded affine pair (4/4 candidates completed), agreement/inspection views, geometric source-support masks, and download of the analysis ZIP. Remaining manual cases: multimodal, one compatible candidate, failed/CHECK execution, and stale-result/export invalidation. UI v0.2 is not formally frozen. No automatic winner or confidence was added.

## Acceptance criteria

- Existing manual Workbench remains stable.
- Existing UI regression remains green.
- Automatic comparison is isolated as a separate page.
- No ground truth is required for uploaded pairs.
- Compatibility decisions are explicit.
- Exclusion reasons are visible.
- Failures are retained.
- Common evidence and method diagnostics are separate.
- Transform agreement is visible.
- Insufficient-candidate cases do not invent consensus.
- Consensus anchor remains descriptive.
- No best-method recommendation is shown.
- No confidence percentage is shown.
- Export is session-local.
- Streamlit contains no registration algorithm implementation.
- The integration remains suitable for future FastAPI exposure.

## Deferred until after Week 7

- calibrated recommendation;
- confidence score;
- winner selection;
- weighted score;
- universal disagreement threshold;
- automated preprocessing search;
- fallback policy;
- abstention threshold;
- learned ranking.

## Handoff

When Stage 6 is frozen, Week 7 can calibrate the automatic decision layer using controlled robustness experiments rather than UI assumptions.


### Final Stage 6.5 QA patch and release gate (2026-10-20)

- Present zero/one eligible candidate as insufficient agreement; two eligible candidates as a centrality tie; three or more as a unique descriptive anchor only when the smallest unrounded median pairwise RMS is unique.
- Retain the frozen backend's raw deterministic medoid and add a separate UI/export interpretation in analysis and manifest JSON.
- Explicitly include optional-method selection in the page-state signature. Clear result, export, and old visual selection on input removal, decoding/preview failure, changed settings, and re-execution.
- Before export, verify the active request's pair ID and optional-method compatibility against the saved comparison result.
- Add 15 focused tests including simulated page early-return branches, report ties, export provenance, single-candidate paths, and stale-result handling.
- Do not change validated registration backend, known-GT policy, metrics, ranking, confidence, or manual Workbench.

**Local gate:** backend 421 passed/11 skipped; UI 147 passed/2 skipped. Prior Windows regression of 432/134 is historical, not validation of this patch. The patched Windows target should produce 432 backend and 149 UI passed if all optional dependencies are present. Manual final checks and UI v0.2 freeze remain open. Week 7 has not started.
