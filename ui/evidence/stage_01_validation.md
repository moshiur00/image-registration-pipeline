# UI Stage 1 Validation Evidence

**Stage:** 1 - Isolation, Skeleton, and Development Guardrails  
**Date:** 2026-10-11  
**Status:** COMPLETE

## Scope

Stage 1 establishes the isolated UI work package only. It does not implement registration orchestration, adapters, dataset workflows, or the final Streamlit workbench.

## Repository baseline

The latest authoritative target Windows validation before UI development is:

```text
364 passed in 4.56s
```

The local execution environment used for Stage 1 does not provide SimpleITK. The local root-suite baseline before adding `ui/` was:

```text
353 passed, 11 skipped in 2.93s
```

The 11 skipped tests are the existing SimpleITK-dependent tests.

## Post-Stage 1 regression result

After adding the isolated UI skeleton:

```text
353 passed, 11 skipped in 3.09s
```

No expected value in the root test suite was changed.

## UI Stage 1 tests

Command:

```text
python -m pytest -c ui/pytest.ini ui/tests
```

Result:

```text
4 passed in 0.03s
```

The Stage 1 UI tests verify:

- required UI directories and files exist,
- `ui/runtime/` ignores session artifacts,
- root pytest discovery remains limited to `tests/`,
- Streamlit remains outside the root `requirements.txt`.

## Isolation verification

A file-level comparison against the uploaded pre-Stage 1 repository showed no non-UI file changes after generated test caches were removed.

Verified unchanged areas include:

- `src/image_registration/`
- `configs/`
- `reports/`
- `docs/`
- `data/`
- `scripts/`
- root `requirements.txt`
- root `pyproject.toml`

## Stage 1 files added

```text
ui/
├── README.md
├── DEVELOPMENT_STAGES.md
├── requirements.txt
├── pytest.ini
├── streamlit_app.py
├── .streamlit/
│   └── config.toml
├── core/
│   └── __init__.py
├── adapters/
│   └── __init__.py
├── streamlit/
│   ├── __init__.py
│   ├── pages/
│   │   └── .gitkeep
│   └── components/
│       └── .gitkeep
├── assets/
│   └── .gitkeep
├── runtime/
│   └── .gitignore
├── evidence/
│   └── stage_01_validation.md
└── tests/
    └── test_stage1_structure.py
```

## Dependency boundary

Streamlit is declared only in:

```text
ui/requirements.txt
```

It is not added to the validated root environment. The Stage 1 entry point uses a late Streamlit import so root regression tests do not require Streamlit.

## Write policy

During UI v0.1, UI code treats the following areas as read-only dependencies:

- `src/image_registration/`
- `configs/`
- `data/samples/`
- `data/manifests/`
- `reports/`
- `docs/`

Temporary session artifacts are allowed only under `ui/runtime/` or operating-system temporary storage.

## Stage decision

Stage 1 is complete. The project is ready for Stage 2, which will implement framework-neutral contracts, method metadata, validation rules, and `RegistrationService` before any real registration workflow is added to Streamlit.
