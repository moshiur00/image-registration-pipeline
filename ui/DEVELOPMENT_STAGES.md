# Image Registration Pipeline UI Development Stages

## Purpose

This document is the persistent development record for the pre-Week 6 UI work package.

The UI is an isolated presentation and orchestration layer around the validated image-registration backend. It must not change frozen Weeks 1 to 5 algorithms, experiment configurations, reports, findings, or validated results.

**Planned repository location:** `ui/DEVELOPMENT_STAGES.md`

**Current overall status:** UI v0.1 FROZEN - Stage 5 COMPLETE

**Target release:** UI v0.1 before Week 6

---

## Development rules

1. Keep all UI-specific implementation under `ui/`.
2. Treat `src/image_registration/` as read-only during UI v0.1.
3. Do not modify frozen Weeks 1 to 5 configs or validated research reports to improve UI behavior.
4. Streamlit is only the current presentation layer.
5. Registration logic must remain outside Streamlit callbacks.
6. The framework-neutral service and adapter layers must be reusable by a future FastAPI backend.
7. User-uploaded images must never receive TRE or geometric PASS claims when ground truth is unavailable.
8. Every visible preprocessing step must be explicit in the request and result summary.
9. Preserve method execution status, plausibility, geometric correctness, warnings, and failures as separate concepts.
10. Temporary UI artifacts belong only under `ui/runtime/` or operating-system temporary storage.
11. After every stage, update this document before starting the next stage.

---

# Stage 1 - Isolation, Skeleton, and Development Guardrails

**Status:** COMPLETE

## Goal

Create the UI work package without affecting the validated research repository.

## Main tasks

- Create the top-level `ui/` directory.
- Add:
  - `ui/README.md`
  - `ui/requirements.txt`
  - `ui/pytest.ini`
  - `ui/runtime/.gitkeep`
  - `ui/core/`
  - `ui/adapters/`
  - `ui/streamlit/`
  - `ui/tests/`
  - `ui/assets/`
- Add ignore rules for `ui/runtime/` except `.gitkeep`.
- Record the current root test-suite baseline.
- Verify the UI environment is isolated from the root research dependencies.
- Define the allowed read-only relationships to:
  - `src/image_registration/`
  - `configs/`
  - `data/samples/`
  - `data/manifests/`
  - `reports/`
  - `docs/`
- Confirm no UI code imports week-specific experiment scripts.

## Deliverables

- UI folder skeleton.
- UI-specific dependency file.
- UI README skeleton.
- Initial UI test configuration.
- Baseline validation record.

## Exit criteria

- No validated backend source file is changed.
- No frozen config or report is changed.
- Root test suite remains green.
- UI-specific directories and dependency boundaries are clear.
- `ui/runtime/` is excluded from normal Git tracking.

## Evidence to record

- Root test count and result.
- Files created.
- `git status` summary.
- Any dependency compatibility issue.
- Decision log.

## Stage 1 completion record

**Date:** 2026-10-11  
**Status:** COMPLETE

### Work completed

- Created the isolated `ui/` work package and directory boundaries.
- Added UI-only dependency declaration and isolated pytest configuration.
- Added the persistent development-stage record and Stage 1 evidence document.
- Added runtime artifact ignore policy under `ui/runtime/`.
- Added a minimal Streamlit entry point that does not contain registration logic.
- Added Stage 1 structural guardrail tests.
- Confirmed root test discovery remains restricted to `tests/`.
- Confirmed Streamlit was not added to the root project requirements.

### Files added

- `ui/README.md`
- `ui/DEVELOPMENT_STAGES.md`
- `ui/requirements.txt`
- `ui/pytest.ini`
- `ui/streamlit_app.py`
- `ui/.streamlit/config.toml`
- `ui/core/__init__.py`
- `ui/adapters/__init__.py`
- `ui/streamlit/__init__.py`
- `ui/streamlit/pages/.gitkeep`
- `ui/streamlit/components/.gitkeep`
- `ui/assets/.gitkeep`
- `ui/runtime/.gitignore`
- `ui/tests/test_stage1_structure.py`
- `ui/evidence/stage_01_validation.md`

### Files modified outside `ui/`

- None.

### Tests

- Root project baseline before Stage 1: 353 passed, 11 skipped.
- Root project after Stage 1: 353 passed, 11 skipped in 3.09s.
- UI Stage 1 tests: 4 passed in 0.03s.

### Evidence produced

- `ui/evidence/stage_01_validation.md`

### Failures or limitations observed

- The current local execution environment does not provide SimpleITK, so the existing SimpleITK-dependent root tests remain skipped locally. The authoritative Windows project validation before UI work remains 364 passed.
- Streamlit is declared as a UI-only dependency but is not required for the Stage 1 structural tests.

### Decisions

- Keep all UI implementation inside `ui/` for v0.1.
- Keep the root research environment unchanged.
- Use a late Streamlit import in the Stage 1 entry point so the root environment can run regression tests without Streamlit installed.
- Build Stage 2 service contracts before any real Streamlit registration workflow.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Start Stage 2: framework-neutral contracts, method registry, validation, and `RegistrationService`.

---

# Stage 2 - Framework-Neutral Contracts, Registry, and Service Layer

**Status:** COMPLETE

## Goal

Build the reusable application core before creating the Streamlit interface.

## Main tasks

Implement framework-neutral objects for:

- `ImageSource`
- `PreprocessingSpec`
- `RegistrationSpec`
- `EvaluationContext`
- `RegistrationRequest`
- `RunStatus`
- `TransformSummary`
- `MetricSummary`
- `DiagnosticSummary`
- `ProvenanceSummary`
- `RegistrationRun`

Implement:

- request validation
- method registry
- method compatibility rules
- transform-model compatibility
- evidence-policy rules
- registration service
- result normalization
- provenance capture
- input hashing

The service interface should support approximately:

```python
class RegistrationService:
    def list_methods(self): ...
    def list_examples(self): ...
    def validate(self, request): ...
    def run(self, request): ...
    def export_summary(self, run): ...
```

## Key design rule

The service must work from a plain Python test without importing Streamlit.

This is the most important requirement for future React + FastAPI migration.

## Deliverables

- `ui/core/contracts.py`
- `ui/core/enums.py`
- `ui/core/validation.py`
- `ui/core/method_registry.py`
- `ui/core/registration_service.py`
- `ui/core/result_presenter.py`
- core unit tests

## Exit criteria

- All core contracts are serializable to JSON-safe summaries.
- Method registry has unique method IDs.
- Invalid method and transform combinations are rejected before execution.
- Unknown-image mode suppresses TRE and geometric PASS.
- Known-ground-truth mode allows ground-truth metrics.
- Core service tests pass without Streamlit.

## Evidence to record

- Contract test results.
- Method registry table.
- Validation-rule test results.
- Example normalized request and result.
- Any contract change made during implementation.

## Stage 2 completion record

**Date:** 2026-10-11  
**Status:** COMPLETE

### Work completed

- Added framework-neutral request, result, provenance, metric, transform, diagnostic, artifact, and adapter-output contracts.
- Added transport-independent enums for source type, ground-truth status, run status, transform model, units, and validation severity.
- Added a validated method registry covering Phase Correlation, ECC, ORB + RANSAC, SIFT + RANSAC, 2D Mattes MI, and the optional 3D RIRE MI path.
- Added request validation for method/model compatibility, known dimensions and shapes, preprocessing values, known-ground-truth evidence, and paired landmarks.
- Added evidence-policy rules that keep unknown-image results from exposing TRE or geometric PASS semantics.
- Added `RegistrationService` with method listing, request validation, adapter dispatch, normalized run assembly, provenance capture, input hashing, and JSON summary export.
- Added an injectable adapter protocol so Stage 3 can connect the existing backend without changing service contracts.
- Added an optional example-provider protocol for the Stage 3 dataset catalog.
- Added JSON-safe result presentation helpers that exclude raw registered arrays from compact summaries.
- Confirmed the service can be imported and tested without importing Streamlit.

### Files added

- `ui/core/contracts.py`
- `ui/core/enums.py`
- `ui/core/validation.py`
- `ui/core/method_registry.py`
- `ui/core/registration_service.py`
- `ui/core/result_presenter.py`
- `ui/tests/test_contracts.py`
- `ui/tests/test_method_registry.py`
- `ui/tests/test_validation.py`
- `ui/tests/test_registration_service.py`
- `ui/tests/test_result_presenter.py`
- `ui/evidence/stage_02_validation.md`

### Files modified inside `ui/`

- `ui/core/__init__.py`
- `ui/README.md`
- `ui/DEVELOPMENT_STAGES.md`

### Files modified outside `ui/`

- None.

### Tests

- Root project after Stage 2: 353 passed, 11 skipped in 2.82s.
- Complete isolated UI suite: 19 passed in 0.56s.
- Stage 2-specific UI tests: 15 tests across contracts, registry, validation, service, and presentation.
- Existing Stage 1 structural tests remain passing.

### Evidence produced

- `ui/evidence/stage_02_validation.md`

### Failures or limitations observed

- Registration adapters are intentionally not implemented in Stage 2. Without an injected adapter, `RegistrationService.run()` returns an explicit failed run stating that the adapter is scheduled for Stage 3.
- Dataset decoding and curated example discovery remain Stage 3 responsibilities.
- The local environment still lacks SimpleITK, so the same 11 existing root tests remain skipped locally.

### Decisions

- Keep request and result contracts independent of Streamlit and FastAPI.
- Use an adapter protocol rather than importing individual registration implementations in the service layer.
- Keep method capabilities in one registry so Streamlit and a future API use the same compatibility rules.
- Enforce evidence policy in the service layer, not only in presentation code, so unknown images cannot accidentally expose ground-truth metrics through a future client.
- Hash actual bytes or arrays when available; Stage 3 will ensure uploaded and catalog sources provide hashable content.
- Keep raw registered arrays out of compact JSON summaries; exported image artifacts are handled later.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Start Stage 3: registration adapters and input/dataset layer.

---

# Stage 3 - Registration Adapters and Input/Dataset Layer

**Status:** COMPLETE

## Goal

Connect the service layer to the existing registration backend without duplicating research logic.

## Registration adapters

Implement adapters for:

- Phase Correlation
- ECC translation
- ECC rigid
- ECC affine
- ORB + RANSAC similarity
- ORB + RANSAC affine
- SIFT + RANSAC similarity
- SIFT + RANSAC affine
- Mattes MI rigid 2D
- Mattes MI affine 2D

Keep the 3D RIRE MI path optional until the 2D workbench is stable.

## Input sources

Support:

### A. Curated tracked examples

Use existing tracked sample images and selected research examples.

### B. Deterministic synthetic presets

Provide a small curated set such as:

- clean translation
- rigid rotation
- similarity transform
- affine deformation
- blur challenge
- partial overlap
- intensity inversion
- edge-emphasized multimodal challenge

Generated preset files should live under `ui/runtime/`.

### C. Unknown 2D uploads

Initial formats:

- PNG
- JPEG
- BMP
- TIFF

Validate:

- file type
- dimensions
- dtype
- finite values
- non-empty intensity variation
- shape compatibility
- image-size limits

Do not silently resize mismatched image shapes.

### D. Local RIRE availability

Detect the existing local RIRE paths but do not require RIRE for the first workbench release.

## Deliverables

- adapter modules
- dataset catalog
- upload decoder/validator
- deterministic preset catalog
- input hashing
- adapter and dataset tests

## Exit criteria

- Every supported 2D method can be called through `RegistrationService`.
- The service returns one normalized `RegistrationRun` shape for all methods.
- At least one known example works for each main method family.
- Unknown uploads run without ground-truth claims.
- Failures remain structured and visible.

## Evidence to record

- Adapter integration-test results.
- Dataset catalog entries.
- Example method outputs.
- Input-validation failure cases.
- Any backend compatibility issue discovered.

## Stage 3 completion record

**Date:** 2026-10-11  
**Status:** COMPLETE

### Work completed

- Added direct adapter wrappers for Phase Correlation, ECC, ORB/SIFT + RANSAC, and 2D Mattes Mutual Information.
- Added a default service factory that injects the supported 2D adapter families into the framework-neutral `RegistrationService`.
- Added explicit UI-side input decoding and preprocessing without changing the research backend.
- Added support for array, file-path, and uploaded raster-byte sources.
- Added deterministic curated presets with exact Moving -> Fixed ground truth.
- Added tracked Week 1 example discovery and local RIRE availability detection.
- Added descriptive metric normalization, conservative transform-plausibility diagnostics, and ground-truth metric calculation.
- Confirmed unknown uploaded images retain the Stage 2 evidence policy and never expose TRE or geometric PASS.
- Confirmed all non-MI adapter families execute through the same service contract.

### Files added

- `ui/core/image_inputs.py`
- `ui/core/dataset_catalog.py`
- `ui/adapters/common.py`
- `ui/adapters/phase_correlation_adapter.py`
- `ui/adapters/ecc_adapter.py`
- `ui/adapters/feature_adapter.py`
- `ui/adapters/mutual_information_adapter.py`
- `ui/tests/test_image_inputs.py`
- `ui/tests/test_dataset_catalog.py`
- `ui/tests/test_stage3_adapters.py`
- `ui/evidence/stage_03_validation.md`

### Files modified inside `ui/`

- `ui/adapters/__init__.py`
- `ui/core/__init__.py`
- `ui/README.md`
- `ui/DEVELOPMENT_STAGES.md`

### Files modified outside `ui/`

- None.

### Tests

- Root project after Stage 3: 353 passed, 11 skipped in 3.05s.
- Complete isolated UI suite: 31 passed, 1 skipped in 1.78s.
- The one UI skip is the Mutual Information integration check because SimpleITK is unavailable locally.
- Non-MI adapter smoke checks completed for Phase Correlation, ECC translation/rigid/affine, ORB similarity/affine, and SIFT similarity/affine.

### Evidence produced

- `ui/evidence/stage_03_validation.md`

### Failures or limitations observed

- SimpleITK is unavailable in the local environment, so the MI adapter integration test remains skipped locally. The adapter uses the existing backend and is expected to be validated on the user's Windows environment where SimpleITK is already available.
- The 3D RIRE method is not registered in the default UI service yet. Stage 3 only detects whether the existing local RIRE files are available, as planned.
- Stage 3 does not create final visual controls or exports. Those remain Stage 4 and Stage 5 responsibilities.

### Decisions

- Keep backend algorithms read-only and call them directly through adapters.
- Keep the service factory separate from `RegistrationService` so the service remains easy to test with fake adapters and future API dependencies.
- Keep UI preprocessing explicit and record its resolved behavior in adapter diagnostics.
- Keep unknown uploads in session memory or temporary UI storage only.
- Keep deterministic preset generation in memory and do not create new tracked research datasets.
- Do not use week-specific experiment scripts as application APIs.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Windows validation follow-up

- The first target Windows UI run collected 32 tests and produced 31 passed, 1 failed in 3.11s.
- The failure was isolated to `ui/tests/test_result_presenter.py`.
- Cause: `str(Path(...))` emitted Windows backslashes, while the framework-neutral JSON contract expects portable forward-slash paths.
- Fix: `to_json_safe()` now normalizes all `pathlib` path objects with `as_posix()`.
- Added a `PureWindowsPath` regression assertion so this portability issue is covered even on non-Windows development hosts.
- Post-fix local UI validation: 31 passed, 1 skipped in 1.76s. The skip remains the SimpleITK-dependent MI integration test.
- Post-fix local root validation: 353 passed, 11 skipped in 3.38s.
- No backend, frozen config, validated report, or tracked data file changed.

### Target Windows revalidation

- Root research suite: 364 passed in 5.08s.
- Isolated UI suite: 32 passed in 3.59s.
- The previous Windows path-serialization failure is resolved.
- The SimpleITK-dependent UI integration test passed on the target environment.
- No backend algorithm, frozen config, validated report, or tracked data change was required.

### Next action

- Start Stage 4: Streamlit Research Workbench.

---

# Stage 4 - Streamlit Research Workbench

**Status:** COMPLETE - curated and unknown-upload workflows manually validated

## Goal

Build the first usable interface while keeping Streamlit as a thin client of the framework-neutral service.

## Main layout

The workbench should contain:

### Source selection

- Example
- Upload
- optional RIRE

### Registration controls

- method
- transform model
- preprocessing
- initialization where relevant
- method-specific advanced settings

### Image comparison area

- fixed image
- moving image
- registered image

### Result summary

- method execution
- plausibility
- ground-truth status
- runtime
- transform
- metrics
- warnings

### Visual diagnostics

- alpha overlay
- checkerboard
- difference
- edge overlay
- feature matches and inliers where applicable
- MI convergence trace where applicable

## Visual direction

The interface should look like a research workstation:

- light neutral background
- dark slate text
- restrained accent
- subtle borders
- no gradients
- no chat layout
- no decorative illustrations
- no oversized marketing cards
- no AI-style phrases
- technical concise wording
- images and evidence remain visually dominant

## Important evidence rules

### Known-ground-truth cases

May show:

- TRE
- parameter error
- PASS/CHECK according to frozen policy

### Unknown uploads

May show:

- Completed / Warning / Failed
- descriptive metrics
- transform plausibility
- diagnostics
- runtime

Must not show:

- TRE
- geometric PASS

## Deliverables

- `ui/streamlit_app.py`
- workbench page
- reusable components
- research-oriented styling
- method control panel
- image comparison component
- metrics and diagnostics panels

## Exit criteria

A reviewer can:

1. select a curated example,
2. select a compatible method,
3. run registration,
4. inspect fixed, moving, and registered images,
5. inspect transform and diagnostics,
6. repeat the workflow with unknown uploaded images.

## Evidence to record

- Screenshots of main workflows.
- Supported method matrix.
- UI smoke-test result.
- Known-image and unknown-image behavior verification.
- Visual review notes.

---

## Stage 4 - Update

**Date:** 2026-10-11  
**Status:** COMPLETE - curated and unknown-upload workflows manually validated

### Work completed

- Replaced the Stage 1 placeholder page with a professional Streamlit research workbench.
- Added Workbench, Research examples, and Method reference views.
- Added curated example selection, unknown 2D uploads, and read-only RIRE availability status.
- Added method controls for Phase Correlation, ECC, ORB/SIFT + RANSAC, and 2D Mattes MI.
- Added explicit preprocessing controls with no silent resizing.
- Added fixed, moving, and registered image comparison.
- Added overlay, checkerboard, difference, and edge diagnostics.
- Added evidence-aware status language, descriptive metrics, ground-truth metrics only when allowed, transform display, warnings, method diagnostics, and provenance.
- Added deterministic request IDs derived from inputs and normalized configuration.
- Added pure view-model and visualization helpers that can be tested without Streamlit.
- Added a Streamlit AppTest smoke test that activates when Streamlit is installed.

### Files added

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

### Files modified

- `ui/streamlit_app.py`
- `ui/README.md`
- `ui/DEVELOPMENT_STAGES.md`

### Tests

- Root project: 364 collected, 353 passed, 11 skipped locally because SimpleITK is unavailable.
- UI: 42 collected, 40 passed, 2 skipped locally.
- Streamlit smoke: pending target validation because Streamlit is not installed in the local execution environment.
- Direct service smoke: synthetic translation through the Stage 4 view-model path completed with mean TRE approximately 0.0039 px and within-tolerance state `True`.

### Evidence produced

- `ui/evidence/stage_04_validation.md`
- Pure view-model tests verify method filtering, method-specific thresholds, deterministic request IDs, and unknown-image status language.
- Visualization tests verify display conversion and diagnostic image shapes.
- Isolation tests verify Streamlit modules do not import the research backend directly.

### Failures or limitations observed

- Streamlit is not installed in the local execution environment and cannot be fetched because network access is unavailable.
- The actual workbench therefore requires target Windows rendering and smoke validation before Stage 4 is marked complete.
- Stage 4 does not add export bundles. Export is intentionally reserved for Stage 5.
- Stage 4 exposes RIRE availability only; the first interactive release remains focused on 2D registration.

### Decisions

- Keep Streamlit as a thin presentation client of `RegistrationService`.
- Keep UI-only method defaults in the Streamlit view-model layer rather than changing frozen research configs.
- Carry existing method-specific development TRE thresholds into curated known-ground-truth examples only.
- Keep unknown-image output language to Completed, Warning, or Failed rather than geometric PASS/CHECK.
- Keep the visual design restrained and research-oriented with no gradients, chat layout, or marketing copy.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Target Windows validation and CLI launch follow-up

- Root research suite passed: 364 passed in 5.59s.
- Isolated UI suite passed: 42 passed in 5.73s.
- The first manual CLI launch failed before rendering with `ModuleNotFoundError: No module named 'ui'`.
- Cause: `streamlit run ui/streamlit_app.py` executes the entry file with `ui/` as the script import root, so the repository root was not guaranteed to be on `sys.path`. The source-layout backend also requires `src/` when the package is not installed editable.
- Fix: `ui/streamlit_app.py` now bootstraps both the repository root and `src/` before importing the framework-neutral UI package.
- Added a CLI-context regression test that loads the entry point from an unrelated working directory with the repository root and `src/` removed from the initial import path.
- Post-fix local UI validation: 43 collected, 41 passed, 2 skipped. The skips remain Streamlit AppTest and SimpleITK dependent in the local environment.
- Post-fix local root validation: 364 collected, 353 passed, 11 skipped because SimpleITK is unavailable locally.
- No research backend, frozen config, validated report, or tracked dataset was changed.


### Target curated-example visual validation

Manual target review completed on Windows using the synthetic translation example with Phase Correlation.

Observed evidence:

- The Streamlit workbench rendered successfully after the CLI import-path fix.
- Fixed, moving, and registered images were displayed in the expected workflow.
- Result status was `PASS` for the known-ground-truth example.
- Runtime was approximately 25.49 ms in the reviewed run.
- Method execution completed and the estimated transform was marked plausible.
- Estimated Moving -> Fixed translation was approximately +13.998 px in x and -8.996 px in y.
- Ground-truth evaluation reported matrix-offset error and mean TRE of approximately 0.0039 px.
- Descriptive metrics improved after registration: MAE and MSE decreased while NCC and SSIM increased.
- Overlay, checkerboard, difference, and edge diagnostic tabs rendered.

Visual review notes carried into Stage 5 polish:

- The `Method execution` metric card truncates the word `Completed` at the current width.
- The raw difference view is visually very dark for near-correct alignment and should receive display-only normalization or contrast scaling in Stage 5.
- Checkerboard and edge views expose invalid warp-border regions. Stage 5 should add overlap-aware presentation or a clear caption so border artifacts are not mistaken for registration error.
- The initial and result layouts are scientifically clear, but final density and spacing can be tightened during Stage 5 without changing the service contract.

This review validates the curated known-ground-truth workflow. It does not yet satisfy the Stage 4 exit criterion for an unknown uploaded image pair.

### Next action

- Run the post-fix isolated UI suite again; expected target count is 43 passed.
- Manually validate one unknown uploaded image pair and confirm that TRE and geometric PASS are not displayed.
- After those two checks pass, mark Stage 4 complete and start Stage 5.
- Do not reopen validated backend algorithms or Weeks 1 to 5 evidence for UI polish.

<!-- Previous relaunch checklist superseded by successful curated-example render. -->

### Previous relaunch checklist

- Apply the CLI launch fix on Windows.
- Run `pytest -c ui/pytest.ini ui/tests -v`; the expected target count is now 43 tests.
- Launch `streamlit run ui/streamlit_app.py` again and manually validate one curated example and one unknown upload pair.
- Mark Stage 4 complete only after the real workbench renders and the manual workflow is reviewed.
- Do not start Stage 5 until Stage 4 target relaunch validation is complete.

---

# Stage 5 - Diagnostics, Export, QA, Documentation, and Scope Freeze

**Status:** IN PROGRESS - RELEASE CANDIDATE; target Windows final QA pending

## Goal

Complete UI v0.1, validate isolation, preserve evidence, and stop UI development before Week 6.

## Diagnostics

Expose method-specific diagnostics:

- Phase Correlation:
  - phase response
  - estimated shift
  - runtime

- ECC:
  - final objective
  - initialization
  - termination information
  - transform parameters

- ORB/SIFT + RANSAC:
  - keypoints
  - retained matches
  - RANSAC inliers
  - inlier ratio
  - spatial coverage
  - reprojection residuals

- Mutual Information:
  - final MI value
  - metric trace
  - stop condition
  - valid metric points
  - pyramid settings

- optional RIRE view:
  - physical transform
  - spacing/origin/direction integrity
  - coverage
  - runtime
  - explicit limitation that anatomical correctness is not verified

## Export

Allow session-local export of:

- registered image
- `transform.json`
- `summary.json`
- selected comparison figure
- optional run bundle ZIP

Exports are convenience artifacts only and must not be written to tracked research reports automatically.

## QA

Run:

- full existing repository test suite
- all UI tests
- contract tests
- adapter tests
- input tests
- service tests
- artifact tests
- Streamlit smoke test if supported
- manual visual review

Verify:

- no UI write to `reports/`
- no UI write to `configs/`
- no UI write to `data/manifests/`
- no UI write to `docs/`
- no modification of frozen Weeks 1 to 5 results
- no unexpected root dependency changes

## Documentation

Complete:

- `ui/README.md`
- architecture description
- setup instructions
- supported methods
- known limitations
- evidence policy
- future FastAPI migration notes
- development-stage record

## Exit criteria

UI v0.1 is complete only when:

- existing research tests remain green,
- UI tests pass,
- supported methods work through the service layer,
- curated and unknown-image workflows both work,
- unknown images never receive unsupported ground-truth claims,
- CHECK and failure cases remain visible,
- exports include provenance and normalized parameters,
- UI-specific changes remain isolated,
- future FastAPI can reuse contracts, registry, adapters, and service,
- this development-stage document is fully updated.

After this stage, freeze UI v0.1 and start Week 6.

---

# Stage Tracking Table

| Stage | Status | Main outcome | Start | Completed | Evidence |
|---|---|---|---|---|---|
| 1. Isolation and guardrails | COMPLETE | Isolated UI skeleton | 2026-10-11 | 2026-10-11 | `ui/evidence/stage_01_validation.md` |
| 2. Contracts and service | COMPLETE | Framework-neutral application core | 2026-10-11 | 2026-10-11 | `ui/evidence/stage_02_validation.md` |
| 3. Adapters and inputs | COMPLETE | Existing backend exposed safely | 2026-10-11 | 2026-10-11 | `ui/evidence/stage_03_validation.md` |
| 4. Streamlit workbench | COMPLETE | Usable research interface | 2026-10-11 | 2026-10-11 | `ui/evidence/stage_04_validation.md` |
| 5. Diagnostics, QA, freeze | IN PROGRESS - RELEASE CANDIDATE | UI v0.1 implementation complete; target freeze gate pending | 2026-10-11 |  | `ui/evidence/stage_05_validation.md` |

---

# Stage Update Template

Use this section each time a stage changes.

## Stage N - Update

**Date:**  
**Status:** NOT STARTED / IN PROGRESS / BLOCKED / COMPLETE

### Work completed

- 

### Files added

- 

### Files modified

- 

### Tests

- Root project:
- UI:
- Integration:

### Evidence produced

- 

### Failures or limitations observed

- 

### Decisions

- 

### Backend impact check

- `src/image_registration/` changed: NO / YES
- frozen configs changed: NO / YES
- validated reports changed: NO / YES
- tracked data changed: NO / YES

### Next action

- 

---

# Pre-Week 6 Completion Gate

Before starting Week 6, all items below must be true:

- [x] Stage 1 complete
- [x] Stage 2 complete
- [x] Stage 3 complete on target Windows environment
- [x] Stage 4 complete
- [ ] Stage 5 complete
- [ ] Existing repository test suite still passes
- [ ] UI tests pass
- [x] UI code is isolated under `ui/`
- [x] Backend research code was not changed for convenience
- [x] Unknown-image mode never shows TRE or geometric PASS
- [x] Known-ground-truth examples preserve correct metric semantics
- [x] Method failures remain visible
- [x] Temporary UI files are excluded from Git
- [x] UI README is complete
- [x] Future FastAPI migration path remains viable
- [x] This development-stage document reflects the v0.1 release-candidate state

Once all items pass, freeze UI v0.1 and proceed to Week 6 unified evaluation and reproducible benchmarking.


## Stage 4 portfolio catalog refinement - 11 October 2026

- Public example selection no longer exposes the development-history label `Week 1 tracked pair`.
- The tracked pair remains an internal catalog fixture for tests and regression workflows.
- Public research examples now contain only research scenarios suitable for the portfolio-facing workbench.
- Backend impact: none.

## Stage 4 sidebar refinement - 11 October 2026

- Removed internal development notes from the visible sidebar: `UI v0.1 pre-Week 6 work package`, `Research backend: read only`, and `Transform convention: Moving -> Fixed`.
- Kept the sidebar focused on navigation and a single subtle product/version footer: `Image Registration Pipeline · v0.1`.
- The Moving -> Fixed convention remains displayed contextually with estimated transforms and in the Method Reference interpretation rules.
- Backend impact: none.


## Stage 4 benchmark-browser refinement - 11 October 2026

- Renamed the public navigation item from `Research examples` to `Benchmark examples`.
- Replaced the raw public example table with curated two-column research cards.
- Simplified public case names to research-facing labels: Translation, Rigid rotation, Similarity transform, Affine transform, Intensity inversion, and Edge-emphasized multimodal.
- Added concise category, motion-model, modality, and ground-truth tags without exposing internal underscore-style identifiers.
- Added method-family display names such as Phase Correlation, ECC, ORB + RANSAC, SIFT + RANSAC, and Mattes MI.
- Added `Open in Workbench` actions that preserve the framework-neutral service architecture while preselecting the chosen example in the Workbench.
- Replaced the large RIRE metric cards with one compact `RIRE CT / MR-T1` research panel containing availability, modalities, method, ground-truth limitation, and collapsed technical details.
- Moved raw example IDs and exact method IDs into an optional `View technical metadata` expander.
- No backend algorithm, frozen configuration, validated report, finding, or tracked dataset changed.

## Stage 4 - Streamlit smoke-test portability update

**Date:** 11 October 2026  
**Status:** IMPLEMENTATION COMPLETE, TARGET REVALIDATION PENDING

### Work completed

- Replaced the positional Streamlit AppTest navigation assertion with stable widget-key lookup.
- Added explicit smoke assertions for both the sidebar navigation control and the Workbench source selector.
- Replaced deprecated `use_container_width` usage in the Streamlit presentation layer with the current `width` API.
- Kept all changes confined to `ui/`.

### Reason

The target Windows AppTest exposed that `app.radio[0]` was the Workbench source selector rather than the sidebar navigation control after the UI grew. Widget order is presentation-dependent, so the smoke test now identifies controls by their stable keys instead of list position.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Run `pytest -c ui/pytest.ini ui/tests -v` on the target Windows environment.
- Confirm the Streamlit launch is warning-free for the removed `use_container_width` calls.
- Continue the remaining unknown-upload validation before formally closing Stage 4.



## Stage 4 benchmark-browser refinement

**Date:** 2026-10-11  
**Status:** IMPLEMENTATION COMPLETE, TARGET VISUAL REVALIDATION PENDING

### Work completed

- Compacted the benchmark-example browser for a more research-portfolio-oriented hierarchy.
- Reduced duplicated metadata and internal terminology in the public case cards.
- Reworked RIRE presentation into a concise real multimodal technical case.
- Prevented local absolute manifest paths from appearing in the public UI.
- Kept internal benchmark identifiers available only through an explicit secondary metadata control.
- Reduced the global application title so each page title carries the primary visual hierarchy.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Run the isolated UI test suite on Windows and visually review the refined Benchmark Examples page before Stage 4 is closed.


## Stage 4 top-content spacing fix

**Date:** 2026-10-11

Target visual review showed that the fixed Streamlit toolbar could overlap the first application label and caption at the top of the main content area. The UI stylesheet now reserves explicit top clearance for the current Streamlit main-container selector and retains the legacy `.block-container` selector as a compatibility fallback. A responsive top offset is also defined for narrower layouts.

This is presentation-only. No registration service, adapter, backend algorithm, research configuration, report, finding, or tracked dataset was changed.

## Stage 4 header hierarchy refinement

**Date:** 2026-10-11  
**Status:** IMPLEMENTATION COMPLETE, TARGET VISUAL REVALIDATION PENDING

### Work completed

- Removed the redundant global application caption from the Streamlit entry point.
- Kept `IMAGE REGISTRATION PIPELINE` as the single compact application eyebrow label.
- Standardized all three page headers to one pattern: application label, one dominant page title, one concise page subtitle.
- Updated the Workbench title to `Registration Workbench`.
- Updated the Workbench subtitle to `Configure, run, and inspect monomodal and multimodal image registration.`
- Renamed `Inputs` to `Input images`.
- Updated `Benchmark Examples` and `Method Reference` to the same title/subtitle hierarchy.
- Added regression tests for the shared header structure.

### Validation

- Root research suite: 353 passed, 11 skipped locally because SimpleITK is unavailable.
- UI suite: 49 passed, 2 skipped locally because Streamlit and SimpleITK are unavailable.
- All changes remain confined to `ui/`.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Re-run the UI suite on Windows.
- Visually confirm the simplified top section on Workbench, Benchmark Examples, and Method Reference before closing Stage 4.


## Stage 4 method-reference portfolio refinement

**Date:** 2026-10-11  
**Status:** IMPLEMENTATION COMPLETE, TARGET VISUAL REVALIDATION PENDING

### Work completed

- Replaced the primary developer-style method registry table with grouped research method cards.
- Consolidated ECC, ORB + RANSAC, SIFT + RANSAC, and Mattes MI variants into human-facing method families while keeping the existing method registry as the data source.
- Added separate sections for intensity-based, feature-based, multimodal, and real-data registration.
- Moved the RIRE 3D path into a dedicated real-data extension panel.
- Added a compact method-compatibility matrix derived from registered capabilities.
- Reduced evidence interpretation to three research principles plus the Moving -> Fixed transform convention.
- Moved implementation IDs, adapter IDs, and raw diagnostic field names into a collapsed `View technical registry` section.
- Added regression tests for family grouping, human-readable diagnostic labels, and the compatibility matrix.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Next action

- Run the isolated UI suite on Windows.
- Visually review the redesigned Method Reference page before closing Stage 4.

### Validation after Method Reference refinement

- Root research suite: 364 collected, 353 passed, 11 skipped locally because SimpleITK is unavailable.
- UI suite: 54 collected, 52 passed, 2 skipped locally because SimpleITK and Streamlit are unavailable.
- Method Reference regression coverage includes registry-family grouping, human-readable diagnostics, and capability-matrix generation.
- Target Windows test and visual revalidation are still required before Stage 4 is closed.


## Stage 4 closure record

**Date:** 2026-10-11  
**Status:** COMPLETE

### Acceptance evidence

- Curated known-ground-truth workflows were manually validated in the real Streamlit application, including Phase Correlation and ECC Affine examples.
- Unknown uploaded fixed/moving images were manually validated with ECC Affine.
- Unknown-image results correctly reported completion, runtime, transform plausibility, descriptive metrics, and diagnostics without TRE, reference-parameter error, or geometric PASS/CHECK claims.
- Benchmark Examples, Method Reference, RIRE availability, and the shared research-style page hierarchy were visually reviewed.
- Remaining presentation issues were explicitly transferred to Stage 5 polish rather than reopening the Stage 4 architecture.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

### Decision

- Freeze the Stage 4 architecture and start Stage 5 visual polish, diagnostics cleanup, export support, final QA, documentation, and v0.1 scope freeze.
- The next target Windows full UI regression is part of the Stage 5 QA gate.


## Stage 5 polish batch 1

**Date:** 2026-10-11  
**Status:** IN PROGRESS, TARGET WINDOWS REGRESSION PENDING

### Work completed

- Removed the duplicate unknown-ground-truth notice from the Workbench.
- Standardized the single unknown-image notice to: `Ground truth unavailable. TRE and geometric correctness are not reported.`
- Changed the result cards to `Run status` and `Method execution: Success/Failed` so execution evidence is not duplicated.
- Humanized transform direction as `Moving → Fixed` and motion-model labels for the presentation layer.
- Humanized transform parameters such as `Translation X`, `Translation Y`, `Rotation`, `Scale`, and `Determinant`.
- Humanized known-ground-truth metric labels such as `Mean TRE (px)` and `Affine linear error`.
- Added display-only contrast normalization to the Difference diagnostic.
- Added an estimated warp-validity mask that neutralizes zero-filled border regions connected to the image boundary in Overlay, Checkerboard, and Edge diagnostics. This mask is presentation-only and does not affect evaluation metrics.
- Reduced the visual-diagnostics presentation width with a centered content column.
- Strengthened primary-button text contrast against the research accent background.
- Added Stage 5 regression tests for the evidence wording, human-facing labels, border mask, difference normalization, and button contrast.

### Scope rule

- No registration algorithm, adapter decision rule, frozen research configuration, report, finding, or tracked dataset was changed.
- Stage 5 polish remains a presentation and packaging layer around the existing framework-neutral service.

### Next action

- Run the root and isolated UI test suites on the target Windows environment.
- Review the polished unknown-upload and curated-example result views.
- Continue with export bundle support, final diagnostic cleanup, documentation completion, and the v0.1 freeze.

### Local validation for Stage 5 polish batch 1

- Root suite: 364 collected; all locally available tests passed with the existing 11 SimpleITK-dependent skips.
- UI suite: 59 collected; 57 passed and 2 skipped locally because Streamlit and SimpleITK are unavailable.
- Python compilation: PASS.
- Em dash count under `ui/`: 0.
- Non-UI diff against the uploaded Stage 4 checkpoint: no tracked source, configuration, report, finding, or dataset changes.

Target Windows regression is still required before UI v0.1 can be frozen.


## Stage 5 polish batch 2, exports, and release-candidate QA

**Date:** 2026-10-11  
**Status:** COMPLETE - UI v0.1 FROZEN

### Work completed

- Suppressed the redundant service-level ground-truth warning in the Streamlit presentation while preserving it in the normalized run record and exported summary.
- Humanized method diagnostics, including labels such as `Final ECC score`, `RANSAC inliers`, `Valid metric points`, and `Initialization`.
- Renamed the expandable machine record to `Raw diagnostic record` so implementation metadata remains available without dominating the research view.
- Replaced raw-first provenance with a compact research-facing summary containing method, Moving -> Fixed direction, ground-truth availability, package version, and SHA-256 integrity status.
- Moved full hashes and normalized parameters under a nested `Raw provenance` expander.
- Reduced the visual-diagnostics presentation width and standardized neutral gray as the display-only representation of estimated regions outside valid overlap.
- Added framework-neutral, in-memory export generation in `ui/core/export_service.py`.
- Added Streamlit download controls for registered PNG, transform JSON, summary JSON, comparison PNG, and a complete run-bundle ZIP.
- Added the full-precision registered NumPy array to the ZIP bundle in addition to the display-ready PNG.
- Confirmed exports never write automatically to tracked research reports, configurations, manifests, documentation, or datasets.
- Added Stage 5 export and presentation regression tests.
- Completed the UI README release-candidate documentation and preserved the future FastAPI reuse path.

### Local final QA

- Root suite: 364 collected, 353 passed, 11 skipped because SimpleITK is unavailable locally.
- UI suite: 64 collected, 62 passed, 2 skipped because SimpleITK and Streamlit are unavailable locally.
- Python compilation: PASS.
- JSON/YAML parsing of the unchanged research repository remains covered by the existing project suites.
- UI em dash count: 0.
- Non-UI tracked file diff against the uploaded Stage 5 checkpoint: none.
- Export bundle unit checks validate PNG decoding, transform and summary JSON, ZIP membership, and lossless full-precision `.npy` round-trip.

### Scope-freeze decision

- No new UI architecture or method-selection logic should be added before Week 6.
- The v0.1 feature set is frozen as a release candidate: Manual Workbench, Benchmark Examples, Method Reference, evidence-aware results, diagnostics, provenance, and session-local exports.
- Automatic multi-method selection and ranking belongs to Weeks 6 to 8 and is explicitly outside the v0.1 pre-Week 6 scope.

### Formal Stage 5 completion

Target Windows final QA completed successfully.

- Pre-Week-6 root suite: 364 / 364 passed.
- UI suite: 64 / 64 passed.
- Curated known-ground-truth workflow: validated.
- Unknown-upload workflow: validated without unsupported TRE or geometric PASS claims.
- Export bundle and download controls: validated.
- UI v0.1 is formally frozen.

Later Week 6 regression continues to preserve compatibility: 390 / 390 backend tests and 64 / 64 UI tests passed after Day 27.

### Backend impact check

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO
