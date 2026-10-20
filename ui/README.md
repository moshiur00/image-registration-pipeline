# Image Registration Workbench

This directory contains the isolated user-interface work package for the image-registration research pipeline. UI v0.1 is frozen, and the current development target is the UI v0.2 Automatic Comparison Preview before Week 7.

## Current status

**UI v0.1 is complete and frozen. Stages 6.1 through 6.4 are complete and target Windows validated. Stage 6.5 is implemented, and its target Windows regression passed (432/432 backend and 134/134 UI). Main Automatic comparison and analysis-ZIP export workflows have been visually reviewed. Final edge-case manual QA and formal UI v0.2 freeze are pending.**

- Stage 1 established isolation, directory boundaries, UI-only dependencies, runtime rules, and regression guardrails.
- Stage 2 established framework-neutral contracts, method metadata, validation, evidence policy, provenance, input hashing, JSON-safe presentation, and `RegistrationService`.
- Stage 3 connected the service to Phase Correlation, ECC, ORB/SIFT + RANSAC, and 2D Mutual Information, and added curated examples, deterministic presets, upload decoding, and RIRE availability discovery.
- Stage 4 adds the professional Streamlit research workbench, curated benchmark-example browser, method reference, explicit preprocessing and method controls, image comparison views, evidence-aware results, diagnostics, and provenance display.
- Stage 5 adds final evidence-label cleanup, human-readable diagnostics and provenance, session-local exports, final QA coverage, documentation, and the v0.1 scope-freeze gate.
- Stage 6.1 adds the framework-neutral automatic comparison service and serializable view models.
- Stage 6.2 adds the separate Automatic Comparison page shell, uploaded-pair preview, pair specification, and backend-driven compatibility presentation.
- Stage 6.3 adds explicit automatic candidate execution, terminal-state preservation, normalized common-evidence comparison, candidate issue reporting, and stale-result invalidation without ranking or agreement presentation.
- Stage 6.4 adds a read-only transform-disagreement matrix, descriptive anchor, candidate diagnostics, and inspection-only registered image visualization.
- Stage 6.5 adds a session-local automatic-analysis export with source hashes and explicit image provenance, geometric display-support masks, concise warnings and diagnostics, and final UI refinement.

No validated Weeks 1 to 5 backend source, configuration, report, finding, or tracked result is changed by the UI work package.

## Architecture

```text
Streamlit
    -> RegistrationService
    -> adapters
    -> existing image_registration package
```

The same application core is intended to survive a future transport change:

```text
React
    -> FastAPI
    -> RegistrationService
    -> adapters
    -> existing image_registration package
```

The validated research backend remains authoritative. Streamlit pages do not import `image_registration` directly.

## Stage 4 workbench

The current Streamlit application provides four views.

### Registration workbench

- curated deterministic research examples
- unknown 2D image uploads
- read-only RIRE availability status
- method selection from the transport-independent method registry
- explicit preprocessing controls
- method-specific settings for Phase Correlation, ECC, ORB/SIFT + RANSAC, and 2D Mattes MI
- fixed, moving, and registered image comparison
- transform matrix and interpretable transform parameters
- descriptive metrics before and after registration
- TRE and parameter error only for known-ground-truth examples
- method diagnostics, including feature/RANSAC statistics and MI convergence traces when available
- overlay, checkerboard, difference, and edge views
- provenance with input hashes, normalized parameters, package version, and transform direction

### Automatic comparison

The Automatic comparison page accepts unknown uploaded image pairs and provides fixed/moving uploads, transform-model and modality selection, explicit common preprocessing, input preview, and backend-derived compatible/excluded method views.

Compatibility is obtained through `AutomaticComparisonService.preview()` rather than through a hardcoded Streamlit method list. Stage 6.3 adds explicit `Run automatic comparison` execution through `AutomaticComparisonService.run()` and renders terminal states plus normalized common evidence. Stage 6.4 renders transform agreement, descriptive consensus, and candidate inspection from the existing service. Stage 6.5 adds an in-memory analysis ZIP and mask-aware display; final recommendation and confidence remain deferred until benchmark calibration.

### Benchmark examples

A curated research browser presents the deterministic examples as human-readable benchmark cards rather than raw internal IDs. Each card summarizes motion model, modality class, ground-truth availability, and suitable method families, and can open the selected case directly in the Workbench. Internal IDs remain available only inside a collapsed technical-metadata view.

The real RIRE CT/MR-T1 case is presented separately as technical physical-space evidence with the existing limitation that verified landmarks or masks are not integrated.

### Method reference

A read-only registry view shows supported dimensions, motion models, intended use, expected diagnostics, and evidence interpretation rules.


## Session-local exports

A completed registration can be downloaded without writing into tracked research directories. The Workbench exposes:

- registered PNG for quick inspection
- `transform.json` containing the project-direction Moving -> Fixed transform
- `summary.json` containing the normalized run summary, diagnostics, warnings, and provenance
- fixed/moving/registered comparison PNG
- a run-bundle ZIP containing all of the above plus `registered_array.npy` for the full-precision registered array

The export layer is framework-neutral and builds byte payloads in memory. A future FastAPI backend can return the same payloads without depending on Streamlit. Exports are convenience artifacts and are never written automatically to `reports/`, `configs/`, `data/manifests/`, or `docs/`.


### Automatic analysis export, Stage 6.5

After running Automatic comparison, choose **Prepare automatic analysis ZIP**, then **Download automatic analysis ZIP**. The archive contains `analysis.json`, `manifest.json`, `candidate_comparison.csv`, `candidate_execution_issues.csv`, `pairwise_agreement.csv`, and per-candidate evidence JSON. Candidates with usable transforms also include display-normalized `registered_INSPECTION_ONLY.png`, numeric `registered_INSPECTION_ONLY.npy`, input/preprocessed previews, diagnostic images, and a geometrically computed source-support mask.

The original adapter registered arrays are not retained in the Stage 6 automatic view model; exported registered images are explicitly **inspection-only reconstructions** using the estimated Moving -> Fixed transform and linear resampling. Geometric source support is computed using the backend mask warp, independently of black source pixels. Images are not recalculated as registration evidence. Method defaults, preprocessing, runtime, raw diagnostics, package versions and SHA256 input hashes are recorded for auditability. Uploaded source bytes are not packaged. No export writes into tracked research directories.

The comparison distinguishes **execution issues** from **missing-reference evaluation limitations**, includes interpretable diagnostic highlights with expandable raw method JSON, and leaves all best-method and confidence choices deferred until Week 7.

## Evidence policy

The application preserves the distinction between execution and correctness.

For known-ground-truth examples, the normalized result may contain TRE, parameter error, and a method-specific within-tolerance state using the existing development thresholds.

For unknown uploaded images, the service suppresses ground-truth metrics and geometric PASS. A completed method may still report descriptive metrics, transform plausibility, diagnostics, runtime, and warnings.

The real RIRE pair remains a technical physical-space demonstration until verified landmarks or masks are integrated. The UI does not claim anatomical TRE, Dice, or anatomical correctness for that pair.

## Repository ownership

The UI may read from the following project areas but does not write to them during v0.1:

- `src/image_registration/`
- `configs/`
- `data/samples/`
- `data/manifests/`
- `reports/`
- `docs/`

Temporary uploads and generated UI artifacts belong under `ui/runtime/` or operating-system temporary storage. `ui/runtime/` is excluded from Git and lightweight project archives.

## UI environment

Create a UI environment separately from the validated research environment when practical:

```bash
python -m venv .venv-ui
# activate the environment
pip install -e .
pip install -r ui/requirements.txt
```

The root `requirements.txt` intentionally remains unchanged.

## Launch

Run from the project root so the top-level `ui` package and installed research package resolve consistently:

```bash
streamlit run ui/streamlit_app.py
```
#
## Benchmark example browser

The portfolio-facing benchmark browser uses compact research cards and human-readable method names. Internal identifiers remain available only under the optional benchmark metadata view. Local absolute file-system paths are not shown in the public interface.

## Development launch path

The Streamlit entry point bootstraps both the repository root and the project `src/` directory before importing the UI package. This keeps the documented project-root launch command working even when the package is not installed editable:

```powershell
streamlit run ui/streamlit_app.py
```


The application is desktop-first and intended as a compact research workbench rather than a consumer image editor.

## Validation

Run the root regression suite:

```bash
pytest
```

Run the isolated UI suite:

```bash
pytest -c ui/pytest.ini ui/tests
```

Stage 4 adds a Streamlit AppTest smoke test. It is skipped automatically when Streamlit is not installed in the current environment.

Latest Stage 6.5 target Windows validation (2026-10-20):

```text
pytest -v                           432 passed in 8.06 s
pytest -c ui/pytest.ini ui/tests -v  134 passed in 6.80 s
```

Both suites completed with zero failures and zero skips. The local development environment previously reported dependency-related skips; those local results remain recorded separately in the Stage 6 evidence file.

Recorded evidence:

- `ui/evidence/stage_01_validation.md`
- `ui/evidence/stage_02_validation.md`
- `ui/evidence/stage_03_validation.md`
- `ui/evidence/stage_04_validation.md`
- `ui/evidence/stage_05_validation.md`
- `ui/evidence/stage_06_validation.md`

## Development record

`ui/DEVELOPMENT_STAGES.md` is the persistent UI development record. It must be updated whenever a stage starts, changes materially, or completes.

## Release state

UI v0.1 is frozen and target-validated. Stage 6.4 is complete and Windows validated (2026-10-20: 432/432 backend and 117/117 UI, with multi-candidate Streamlit screenshots). Stage 6.5 also passed authoritative Windows regression on 2026-10-20: 432/432 backend in 8.06 s and 134/134 UI in 6.80 s, zero failures and zero skips. User screenshots show an uploaded four-candidate affine comparison, agreement and visual inspection, mask-aware previews, execution limitations, and successful automatic-analysis ZIP download. Remaining manual acceptance: a multimodal case, a one-candidate case, failed/CHECK behavior, and changed-input/settings result/export invalidation. UI v0.2 has not been formally frozen; no final method recommendation or confidence is provided.


## Page header pattern

The Streamlit presentation uses one consistent page hierarchy:

```text
IMAGE REGISTRATION PIPELINE
Page Title
One concise page subtitle
```

The application-level caption was removed so each page title carries the primary visual hierarchy. Workbench, Automatic Registration Comparison, Benchmark Examples, and Method Reference follow the same pattern.


## UI v0.2 final QA patch (2026-10-20)

Two compatible candidates are always tied under pairwise centrality, so the page now says there is no unique descriptive anchor. One eligible transform reports insufficient agreement. With three or more eligible transforms, only a unique minimum median RMS is displayed as the descriptive anchor; the backend medoid remains available in raw evidence. Automatic-analysis ZIP files record this distinction in `analysis.json` and `manifest.json`.

Changing or removing input images, changing pair settings or preprocessing, or starting a new comparison clears the old result and prepared export. Exports also reject stale request identities. The original manual Workbench and validated backend were not changed.

The final patch passed local backend tests (421 passed, 11 optional-dependency skips) and UI tests (147 passed, 2 optional-dependency skips). The previous release candidate passed 432 backend and 134 UI tests on Windows, but the new patch awaits fresh authoritative Windows checks. With all dependencies installed, expected counts are 432 backend and 149 UI tests. Do not freeze UI v0.2 or remove its `preview` sidebar label until manual edge-case acceptance and these tests are complete. Week 7 remains not started.
