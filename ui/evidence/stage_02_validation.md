# UI Stage 2 Validation Evidence

## Stage

Framework-Neutral Contracts, Registry, and Service Layer

**Date:** 2026-10-11  
**Status:** COMPLETE

## Scope

Stage 2 adds only the reusable UI application core. It does not connect production registration adapters, decode uploaded images, create dataset presets, or build the Streamlit workbench. Those responsibilities remain in later stages.

## Implemented application core

- Framework-neutral request and result dataclasses.
- Source, ground-truth, run-status, transform-model, and units enums.
- Transport-independent method registry.
- Request validation and evidence-policy rules.
- Registration service with injectable adapters.
- Deterministic input hashing for bytes, arrays, and local files.
- Provenance capture with Moving -> Fixed direction.
- JSON-safe result presentation and compact summary export.
- Explicit adapter-missing behavior until Stage 3.

## Method registry

The Stage 2 registry includes:

- `phase_translation`
- `ecc_translation`
- `ecc_rigid`
- `ecc_affine`
- `orb_similarity`
- `orb_affine`
- `sift_similarity`
- `sift_affine`
- `mi_rigid_2d`
- `mi_affine_2d`
- `mi_rigid_3d_rire`

The registry owns method dimensions, supported transform models, modality guidance, same-shape requirements, diagnostics, and adapter IDs. No Streamlit-specific metadata is required.

## Evidence-policy verification

The service layer, not only the UI, enforces the evidence distinction:

- known ground truth may retain TRE or other ground-truth metrics and a within-tolerance state;
- unavailable ground truth removes ground-truth metrics from the normalized result;
- unavailable ground truth forces `within_tolerance=None`;
- unavailable ground truth adds an explicit warning that TRE and geometric PASS are not reported;
- method execution failure and geometric CHECK remain separate states.

This keeps the same behavior available to Streamlit now and to a future FastAPI client.

## Test results

### Root research suite

```text
353 passed, 11 skipped in 2.82s
```

The 11 skips are the existing SimpleITK-dependent local skips. No expected root test value changed.

### Isolated UI suite

```text
19 passed in 0.56s
```

This includes the 4 Stage 1 guardrail tests and 15 Stage 2 tests covering contracts, method registry, request validation, service semantics, input hashing, summary export, and Streamlit independence.

## Isolation check

Stage 2 changes are confined to `ui/`.

Unchanged research areas:

- `src/image_registration/`
- `configs/`
- `reports/`
- `docs/`
- `data/manifests/`
- root `requirements.txt`
- root `pyproject.toml`

## Known limitation

Production registration adapters are intentionally absent at the end of Stage 2. Calling a valid method without an injected adapter returns a structured failed `RegistrationRun` with an explicit Stage 3 message rather than importing or duplicating backend logic prematurely.

## Decision

Stage 2 exit criteria are met. Stage 3 may connect these stable contracts and service semantics to the validated image-registration backend and dataset/input layer.
