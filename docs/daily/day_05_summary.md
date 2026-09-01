# Day 5 Summary

**Date:** 2026-09-01  
**Week:** 1 - Registration Foundations and Pipeline Skeleton  
**Status:** Complete

## Objective

Integrate the Week 1 components into a reusable YAML-driven workflow and verify the full load -> preprocess -> warp -> evaluate -> save path.

## Work completed

1. Added `src/image_registration/config.py` for YAML loading, default handling, validation, path resolution, configuration hashing, and transform construction.
2. Added `src/image_registration/pipeline.py` as the common Week 1 experiment runner.
3. Added `src/image_registration/registration.py` with a standard `RegistrationResult` structure and registration-method protocol for later algorithms.
4. Added `scripts/run_experiment.py` as the command-line entry point for configuration-driven experiments.
5. Added `configs/day05_week01_smoke_test.yaml`.
6. Added a small fixed/moving sample pair under `data/samples/week01/` for the Week 1 integration test.
7. Added deterministic run identifiers based on experiment name and configuration hash.
8. Added structured run directories containing resolved configuration, metrics, transform parameters, timing, metadata, logs, and figures.
9. Added input file SHA-256 hashes and environment information to run metadata.
10. Added JSON and CSV metric outputs.
11. Added tests for configuration handling, transform construction, registration result structure, pipeline execution, deterministic run naming, and overwrite behavior.
12. Updated the project archive script so required sample data is included automatically while virtual environments, generated outputs, caches, Git data, and large datasets remain excluded.
13. Removed the redundant `scripts/scripts.txt` helper file.
14. Refined core module docstrings for technical clarity.
15. Updated visualization output to use the Matplotlib Agg canvas directly, removing the runtime dependency on Tkinter for saved figures.
16. Updated run-log handling so file handlers are flushed, closed, and detached after each completed run and before an existing run directory is replaced. This prevents Windows file-lock errors during deterministic reruns.

## Smoke test configuration

```text
Fixed image:    data/samples/week01/fixed.png
Moving image:   data/samples/week01/moving.png
Transform:      known similarity transform
Direction:      Moving -> Fixed
Interpolation:  linear
Seed:           42
```

The test configuration runs with:

```powershell
python scripts/run_experiment.py --config configs/day05_week01_smoke_test.yaml
```

## Validation result

Final local validation on Windows with Python 3.12.6 produced:

```text
66 passed
```

The Day 5 smoke test produced:

```text
Unregistered MAE:   0.1556
Registered MAE:     0.0699
Unregistered NCC:   0.6057
Registered NCC:     0.9645
Unregistered SSIM:  0.5371
Registered SSIM:    0.8080
```

The known transform improves all three reported comparison measures in this controlled test.

## Run outputs

A successful run contains:

```text
resolved_config.yaml
metrics.json
metrics.csv
transform.json
timing.json
metadata.json
run_summary.json
run.log
figures/
```

This satisfies the Week 1 requirement that saved runs contain enough information to reproduce and inspect the result.

## Week 1 status

Week 1 is complete. The project now has a tested foundation for transformation conventions, image I/O, preprocessing, resampling, evaluation, visualization, configuration management, structured result storage, and reproducible execution.

Automatic transform estimation has not been introduced yet. That begins with the registration methods planned for later weeks.
