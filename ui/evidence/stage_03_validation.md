# UI Stage 3 Validation Evidence

Date: 2026-10-11

Status: COMPLETE - TARGET WINDOWS VALIDATED

## Scope

Stage 3 connects the framework-neutral UI service to the existing validated 2D registration backend and adds the read-only input and dataset layer. No validated research algorithm, configuration, report, finding, or tracked result was changed.

## Implemented adapter families

- Phase Correlation translation
- ECC translation
- ECC rigid
- ECC affine
- ORB + RANSAC similarity
- ORB + RANSAC affine
- SIFT + RANSAC similarity
- SIFT + RANSAC affine
- Mattes Mutual Information rigid 2D
- Mattes Mutual Information affine 2D

The 3D RIRE registration method remains optional and is not wired into the default UI service yet. Stage 3 provides local RIRE availability discovery only.

## Input and dataset layer

Implemented support for:

- NumPy array sources
- local file-path sources
- uploaded PNG, JPEG, BMP, and TIFF bytes through OpenCV decoding
- tracked Week 1 example pair
- deterministic synthetic translation, rigid, similarity, affine, intensity-inversion, and edge-emphasized presets
- local RIRE manifest and volume availability detection

Upload validation enforces non-empty numeric data, finite values, supported raster dimensionality, a 20 MB byte limit, and a 16 million pixel limit. UI v0.1 does not silently resize mismatched images.

## Evidence behavior

- Known-ground-truth presets can return TRE and transform-error evidence.
- Unknown uploaded images remain limited to execution status, plausibility, descriptive metrics, diagnostics, runtime, and warnings.
- Ground-truth metrics and geometric PASS state remain suppressed for unknown uploads by the Stage 2 service policy.
- Adapter failure reasons are normalized into `RegistrationRun` instead of being hidden.

## Local validation

Root research suite:

- 353 passed
- 11 skipped
- 3.05 s

All 11 skips are existing SimpleITK-dependent tests because SimpleITK is unavailable in the local validation environment.

Isolated UI suite:

- 31 passed
- 1 skipped
- 1.78 s

The single UI skip is the 2D Mutual Information adapter integration test because SimpleITK is unavailable locally.

## Non-MI integration checks

The default Stage 3 service was executed against deterministic catalog examples with these results:

- Phase Correlation translation: completed, mean TRE about 0.004 px
- ECC translation: completed, mean TRE about 0.262 px
- ECC rigid: completed, mean TRE about 0.179 px
- ECC affine multiresolution: completed, mean TRE about 0.384 px
- ORB + RANSAC similarity: completed, mean TRE about 0.161 px
- ORB + RANSAC affine: completed, mean TRE about 0.274 px
- SIFT + RANSAC similarity: completed, mean TRE about 0.045 px
- SIFT + RANSAC affine: completed, mean TRE about 0.042 px

These checks validate adapter plumbing and result normalization only. They do not replace the frozen research benchmark results from Weeks 1 to 5.

## Isolation check

Comparison against the user-supplied pre-Stage 3 repository:

- non-UI files added: 0
- non-UI files removed: 0
- non-UI files changed: 0

Backend impact:

- `src/image_registration/` changed: NO
- frozen configs changed: NO
- validated reports changed: NO
- tracked data changed: NO

## Stage 3 decisions

- Keep `RegistrationService` framework-neutral and inject backend adapters through a factory.
- Keep Streamlit out of adapter and service code.
- Use existing backend methods directly rather than calling week-specific experiment scripts.
- Keep preprocessing explicit in `PreprocessingSpec` and include preprocessing reports in diagnostics.
- Do not silently resize unknown uploads.
- Keep RIRE as read-only availability discovery until the 2D workbench is stable.
- Keep all generated UI artifacts outside tracked research evidence.

## Target Windows portability issue and fix

The first target Windows UI validation collected 32 tests and reported:

- 31 passed
- 1 failed
- 3.11 s

The failed test was `test_to_json_safe_handles_numpy_path_and_collections`. The implementation converted `Path` values using `str(path)`, which produced `example\\file.png` on Windows while the transport-neutral JSON representation is expected to use `example/file.png`.

The fix changes path serialization to use `PurePath.as_posix()`. A `PureWindowsPath` regression assertion was added so the Windows path behavior is now testable on any development platform.

Post-fix local validation:

- root research suite: 353 passed, 11 skipped in 3.38s
- isolated UI suite: 31 passed, 1 skipped in 1.76s

The remaining local skip is still the SimpleITK-dependent 2D Mutual Information adapter integration test. No research backend, frozen configuration, validated report, finding, or tracked data file was changed.

## Target Windows revalidation

The corrected Stage 3 implementation was revalidated on the target Windows environment:

- root research suite: 364 passed in 5.08 s
- isolated UI suite: 32 passed in 3.59 s
- SimpleITK-dependent UI integration test: passed
- previous path-serialization failure: resolved

This closes the Stage 3 portability issue and satisfies the Stage 3 target-machine validation gate.

## Next action

Start Stage 4: Streamlit Research Workbench.
