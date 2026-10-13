# UI Stage 4 Validation Evidence

Date: 2026-10-11

Status: TARGET CURATED WORKFLOW VALIDATED, UNKNOWN UPLOAD AND FINAL REGRESSION PENDING

## Scope

Stage 4 implements the Streamlit research workbench on top of the existing framework-neutral service and Stage 3 adapters. No registration algorithm is reimplemented in Streamlit.

## Files added

- `ui/streamlit/view_model.py`
- `ui/streamlit/pages/__init__.py`
- `ui/streamlit/pages/workbench.py`
- `ui/streamlit/pages/benchmark_explorer.py`
- `ui/streamlit/pages/method_reference.py`
- `ui/streamlit/components/__init__.py`
- `ui/streamlit/components/source_selector.py`
- `ui/streamlit/components/method_controls.py`
- `ui/streamlit/components/image_comparison.py`
- `ui/streamlit/components/metrics_panel.py`
- `ui/streamlit/components/diagnostics_panel.py`
- `ui/streamlit/components/visuals.py`
- `ui/assets/research.css`
- `ui/tests/test_stage4_view_model.py`
- `ui/tests/test_stage4_visuals.py`
- `ui/tests/test_stage4_isolation.py`
- `ui/tests/test_streamlit_smoke.py`
- `ui/evidence/stage_04_validation.md`

## Files modified

- `ui/streamlit_app.py`
- `ui/README.md`
- `ui/DEVELOPMENT_STAGES.md`

## Functional coverage

- curated tracked and deterministic examples
- unknown 2D raster uploads
- read-only RIRE availability status
- manual method selection without automatic method ranking
- explicit preprocessing controls
- Phase Correlation controls
- ECC controls
- ORB/SIFT + RANSAC controls
- 2D Mattes MI controls
- fixed/moving/registered image panels
- transform display
- evidence-aware metrics
- warnings and failure reasons
- overlay, checkerboard, difference, and edge views
- feature/RANSAC diagnostics
- MI convergence trace when available
- provenance display
- research example catalog
- method reference

## Evidence policy checks

- Known-ground-truth examples can display TRE and parameter error.
- Existing method-specific development tolerances are carried into curated examples for PASS/CHECK display.
- Unknown uploads do not receive TRE or geometric PASS.
- Descriptive image metrics are labeled as descriptive evidence only.
- RIRE remains a technical physical-space path without anatomical correctness claims.

## Isolation checks

- Streamlit modules contain no direct `image_registration` imports.
- Streamlit calls the framework-neutral service and UI core only.
- No backend source file was modified.
- No frozen research configuration was modified.
- No validated report or tracked result was modified.
- No tracked dataset was modified.

## Local validation

Root research suite:

- 364 tests collected
- 353 passed
- 11 skipped because SimpleITK is unavailable in the local environment

UI suite:

- 42 tests collected
- 40 passed
- 2 skipped
- one skip is the existing SimpleITK-dependent Stage 3 MI adapter integration test
- one skip is the Stage 4 Streamlit AppTest smoke test because Streamlit is unavailable in the local environment

Direct Stage 4 service smoke check:

- deterministic synthetic translation request executed through `RegistrationService`
- Phase Correlation returned `completed`
- mean TRE approximately 0.0039 px
- within-tolerance state was `True`

## Local environment limitation

The execution environment has no network access and Streamlit is not preinstalled, so the actual Streamlit application cannot be rendered locally. The implementation is therefore waiting for target Windows validation in the user's UI environment.

## Target validation commands

Install the isolated UI dependency when needed:

```powershell
pip install -r ui/requirements.txt
```

Run:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
streamlit run ui/streamlit_app.py
```

Expected target test counts after Streamlit and SimpleITK are available:

- root suite: 364 passed
- UI suite: 42 passed

## Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

## Next action

Validate Stage 4 on the target Windows environment. Do not start Stage 5 until the UI test suite and manual workbench smoke check are reviewed.


## Target Windows validation and CLI launch follow-up

Initial target validation completed on Windows:

- root suite: 364 passed in 5.59s
- UI suite: 42 passed in 5.73s

The test suites passed, but the first real CLI launch failed before the application rendered:

```text
ModuleNotFoundError: No module named 'ui'
```

The failure occurred when running:

```powershell
streamlit run ui/streamlit_app.py
```

Cause:

- Streamlit executes `ui/streamlit_app.py` with the entry script directory on the import path.
- The repository root was therefore not guaranteed to be available for `import ui`.
- The repository uses a `src/` package layout, so `src/` also needs to be importable when the project package is not installed editable.

Fix:

- `ui/streamlit_app.py` now adds the repository root and `src/` to `sys.path` before importing `ui.adapters`, `ui.core`, or the Streamlit page modules.
- The bootstrap is limited to the application entry point and does not change the research backend.
- `ui/tests/test_streamlit_smoke.py` now includes a CLI-context regression test that loads the entry point from an unrelated working directory with the repository root and `src/` removed from the initial import path.

Post-fix local validation:

- root suite: 364 collected, 353 passed, 11 skipped because SimpleITK is unavailable locally
- UI suite: 43 collected, 41 passed, 2 skipped
- CLI-context import regression: passed

Target revalidation required:

```powershell
pytest -c ui/pytest.ini ui/tests -v
streamlit run ui/streamlit_app.py
```

Expected target UI count after the new regression test: 43 passed.

Stage 4 remains open until the workbench renders successfully and the real curated-example and upload workflows are manually reviewed.

## Target curated-example manual review

The repaired Streamlit application rendered successfully on the target Windows environment. The synthetic translation example was run with Phase Correlation and the post-registration interface was manually reviewed.

Reviewed result:

- status: PASS
- runtime: approximately 25.49 ms
- method execution: completed
- transform plausibility: plausible
- transform direction: Moving -> Fixed
- estimated x offset: approximately +13.998 px
- estimated y offset: approximately -8.996 px
- matrix-offset error: approximately 0.0039 px
- mean TRE: approximately 0.0039 px

Descriptive metrics changed in the expected direction after registration in the reviewed run:

- MAE: 28.1473 -> 5.0613
- MSE: 3092.1548 -> 838.2056
- NCC: 0.7289 -> 0.9287
- SSIM: 0.4568 -> 0.9581

The overlay, checkerboard, difference, and edge diagnostic tabs rendered successfully.

### Visual observations for Stage 5

- The Method execution status card currently truncates `Completed`.
- The difference image is technically valid but too dark for useful visual inspection when residual error is small. Stage 5 should apply display-only contrast normalization without altering metric computation.
- Checkerboard and edge views show border artifacts from invalid warped regions. Stage 5 should make overlap support explicit or mask/caption invalid borders in the diagnostic presentation.
- Layout and research wording are suitable for the intended research-workbench style. Final spacing and density refinements can be handled during Stage 5.

### Remaining Stage 4 target checks

- rerun the post-fix isolated UI suite and obtain 43 passed on Windows
- run one unknown uploaded image pair and verify that the UI does not show TRE or geometric PASS

Stage 4 should be marked complete only after both checks pass.


## Portfolio catalog cleanup

- Removed the internal `Week 1 tracked pair` fixture from the public Workbench and Research Examples catalog.
- The fixture remains available by internal ID for regression and development use.
- No backend research data, algorithms, reports, or frozen configurations were changed.

## Sidebar portfolio refinement

- Removed visible internal implementation notes from the sidebar.
- Sidebar now contains only Navigation plus the subtle footer `Image Registration Pipeline · v0.1`.
- Transform direction remains visible where scientifically relevant, including the estimated-transform panel and Method Reference.
- No registration logic, evidence policy, backend module, report, or frozen configuration changed.


## Benchmark-example browser refinement

The Stage 4 public example browser was refined after target visual review:

- navigation label changed from `Research examples` to `Benchmark examples`
- public example names no longer expose development-oriented `Synthetic ...` prefixes where the research scenario itself is clearer
- the raw public metadata table was replaced by curated research cards
- internal identifiers such as `synthetic_multimodal`, `mi_affine_2d`, and `sift_similarity` are no longer required for normal interpretation
- each card shows human-readable motion model, modality coverage, ground-truth status, and method families
- each card can open its case directly in the Workbench through Streamlit session state, without bypassing `RegistrationService`
- the RIRE case is now one compact real-multimodal research panel instead of three oversized metric cards
- exact IDs remain available under a collapsed technical-metadata view for reproducibility and debugging

This refinement changes only UI presentation, navigation state, public example labels, UI tests, and UI documentation. Research backend code and frozen evidence remain unchanged.

## Windows smoke-test regression fix

A target Windows UI run exposed one stale AppTest assumption: the smoke test indexed `app.radio[0]`, but widget ordering changed after the Workbench gained its source selector. The application itself loaded correctly. The test now locates the sidebar navigation by the stable `ui_page` key and separately verifies the `ui_source_mode` source selector.

The same maintenance update replaces deprecated Streamlit `use_container_width` calls in the presentation layer with the current `width` API. No research backend, frozen configuration, report, or tracked dataset was changed.

**Target status:** Windows UI revalidation pending.



## Benchmark browser portfolio refinement

Target visual review identified that the benchmark browser still exposed too much internal metadata and used excessive vertical space. The presentation was refined without changing any registration backend behavior.

Changes:

- replaced the large summary metric cards with one compact summary line
- changed the synthetic-case layout to three compact cards per row on wide screens
- removed duplicate category/modality tags
- replaced `Known GT` with `Known ground truth`
- made the case action visually secondary
- compacted the RIRE panel around `CT → MR-T1`, `3D rigid`, `Mattes MI`, and physical coordinates
- replaced the large RIRE availability card with a small status badge
- replaced raw RIRE JSON as the first technical view with a human-readable technical table
- kept raw RIRE metadata behind an explicit secondary control
- removed absolute local file-system paths from public technical presentation
- simplified benchmark metadata to human-facing fields with internal IDs opt-in only
- changed the global application heading to a restrained `IMAGE REGISTRATION PIPELINE` label so page titles remain visually dominant

No backend algorithm, frozen research configuration, validated report, or tracked dataset was changed.


## Stage 4 top-content spacing fix

**Date:** 2026-10-11

Target visual review showed that the fixed Streamlit toolbar could overlap the first application label and caption at the top of the main content area. The UI stylesheet now reserves explicit top clearance for the current Streamlit main-container selector and retains the legacy `.block-container` selector as a compatibility fallback. A responsive top offset is also defined for narrower layouts.

This is presentation-only. No registration service, adapter, backend algorithm, research configuration, report, finding, or tracked dataset was changed.

## Header hierarchy refinement

Target visual review showed that the top of each page contained redundant hierarchy: the global application caption repeated the same role as the page title and page subtitle. The presentation was simplified to one compact application eyebrow plus one dominant page title and one concise subtitle.

Current page headers:

- `Registration Workbench` with `Configure, run, and inspect monomodal and multimodal image registration.`
- `Benchmark Examples` with `Curated cases covering supported motion models and modality conditions.`
- `Method Reference` with `Registration methods, supported transformations, and diagnostic outputs.`

The Workbench section label `Inputs` was renamed to `Input images`.

A source-level regression test now protects this structure. Local validation after the change produced 49 passed and 2 skipped in the UI suite, with the skips limited to unavailable Streamlit and SimpleITK dependencies. Root validation remained 353 passed and 11 skipped locally.

No research backend, frozen configuration, validated report, finding, or tracked dataset was changed.


## Method Reference portfolio refinement

**Date:** 2026-10-11

Target visual review showed that the original Method Reference exposed framework-registry details too prominently. The page has been redesigned as a research method catalog while continuing to derive capabilities from the existing transport-independent registry.

Changes:

- grouped method variants into Phase Correlation, ECC, ORB + RANSAC, SIFT + RANSAC, and Mattes Mutual Information
- separated the RIRE CT / MR-T1 path as an advanced real-data extension
- replaced raw diagnostic identifiers with human-readable labels in the primary view
- replaced `Optional yes/no` with research-facing status labels such as `Core method`, `Optional complement`, and `Advanced path`
- added a compact compatibility matrix for dimension, motion-model support, and typical use
- reduced the interpretation section to execution, geometric correctness, and unknown-image evidence principles
- retained exact implementation IDs and raw registry fields under a collapsed technical registry for reproducibility

No registration backend behavior, frozen configuration, validated report, finding, or tracked dataset was changed.

### Local validation after Method Reference refinement

- root research suite: 364 collected, 353 passed, 11 skipped because SimpleITK is unavailable locally
- isolated UI suite: 54 collected, 52 passed, 2 skipped because SimpleITK and Streamlit are unavailable locally
- Python compilation: passed
- no research backend, frozen configuration, validated report, finding, or tracked dataset changed

Target Windows revalidation and visual review remain required before Stage 4 is formally closed.
