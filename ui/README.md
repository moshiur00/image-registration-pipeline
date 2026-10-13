# Image Registration Workbench

This directory contains the isolated user-interface work package for the image-registration research pipeline. The current target is a compact Streamlit v0.1 workbench built before Week 6.

## Current status

**Stages 1 to 4 are complete. Stage 5 implementation is complete as a UI v0.1 release candidate; final target-Windows regression and visual export checks remain before the formal freeze.**

- Stage 1 established isolation, directory boundaries, UI-only dependencies, runtime rules, and regression guardrails.
- Stage 2 established framework-neutral contracts, method metadata, validation, evidence policy, provenance, input hashing, JSON-safe presentation, and `RegistrationService`.
- Stage 3 connected the service to Phase Correlation, ECC, ORB/SIFT + RANSAC, and 2D Mutual Information, and added curated examples, deterministic presets, upload decoding, and RIRE availability discovery.
- Stage 4 adds the professional Streamlit research workbench, curated benchmark-example browser, method reference, explicit preprocessing and method controls, image comparison views, evidence-aware results, diagnostics, and provenance display.
- Stage 5 adds final evidence-label cleanup, human-readable diagnostics and provenance, session-local exports, final QA coverage, documentation, and the v0.1 scope-freeze gate.

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

The current workbench provides three views.

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

Recorded evidence:

- `ui/evidence/stage_01_validation.md`
- `ui/evidence/stage_02_validation.md`
- `ui/evidence/stage_03_validation.md`
- `ui/evidence/stage_04_validation.md`
- `ui/evidence/stage_05_validation.md`

## Development record

`ui/DEVELOPMENT_STAGES.md` is the persistent UI development record. It must be updated whenever a stage starts, changes materially, or completes.

## Release gate

UI v0.1 is now a release candidate. Local QA passes with only the expected SimpleITK- and Streamlit-dependent skips in this environment. Before the formal freeze and Week 6 start, run the full root and UI suites on the target Windows environment and manually verify one curated run, one unknown-upload run, and the export downloads.


## Page header pattern

The Streamlit presentation uses one consistent page hierarchy:

```text
IMAGE REGISTRATION PIPELINE
Page Title
One concise page subtitle
```

The application-level caption was removed so each page title carries the primary visual hierarchy. Workbench, Benchmark Examples, and Method Reference follow the same pattern.
