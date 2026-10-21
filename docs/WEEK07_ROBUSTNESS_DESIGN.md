# Week 7 Day 31 Technical Notes

## Commands

From the project root with its dependencies installed:

```powershell
python scripts/week07_day01_robustness_design.py --config configs/week07_day01_robustness_grid.yaml
python scripts/week07_day01_robustness_design.py --config configs/week07_day01_robustness_grid.yaml --pilot
pytest -v
pytest -c ui/pytest.ini ui/tests -v
```

The first command only creates task/summary manifests and a tracked design report. The second executes the **11 pilot attempts only**, then immediately tests that repeating them would execute zero additional registrations. The full robustness grid is not executed.

The run is intentionally resumable. Its journal and long-form CSV are written to `outputs/week07_day01_pilot/`, excluded from the project share ZIP. To redo a changed pilot matrix, choose a new output directory and keep the original evidence; the Week 6 runner rejects mixing mismatched plans.

## How compatibility is counted

A method attempts a pair only if its transform model and modality are supported. Method-model-modality combinations excluded by the frozen catalog are not algorithm failures. Some geometries, such as similarity on simulated-multimodal images, have no compatible method in the current snapshot. Their pair cells are recorded separately in the design manifest.

## What is and is not frozen

Frozen at Day 31: configuration snapshot, candidate design grid, source roles, method compatibility, and reproducible task enumeration.

Not yet executed: 1,026 full-grid method attempts. Severity algorithms and analysis belong to Days 32 through 35. Exact threshold policies and confidence estimates remain uncalibrated. Do not interpret Day 31 pilot runtimes as production benchmarks.

## Split and reference firewall

The Day 31 planning code hashes development and held-out source bytes. Only the development source is decoded and fed to the pilot. The held-out source is not registered or scored. Synthetic known GT is stored in offline pilot-pair state and never supplied to the UI `RegistrationService`; its `EvaluationContext` remains `UNAVAILABLE`.

The full grid's `ReferenceEvidence(exact_transform=True)` is an **offline benchmark task reference flag**, not an instruction to reveal ground truth to the automatic registration service. The Day 32 executor must maintain this separation.

## Interpretation of cost estimates

Pilot size is 192 by 192 pixels, unlike many larger real images. Method runtimes depend on resolution, texture and difficulty, and MI requires SimpleITK. If an MI attempt fails because SimpleITK is unavailable, the estimated full-grid runtime is emitted as null and the dependency issue is listed. Storage projections are approximate JSONL extrapolations, not measured full-sweep storage.

Do not start expensive Week 7 sweeps until Windows runtime and resource evidence are reviewed.
