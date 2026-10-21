# Week 7 Day 32: Controlled One-Factor Robustness Sweeps

## Purpose

Day 32 implements the Day 31 severity grid using the existing synthetic-pair,
preprocessing, degradation, multimodal-mapping, overlap, registration-service,
unified-evaluation, and resumable-runner APIs. This is **development-only**
synthetic evidence, not final method calibration or a Week 8 test.

## Windows commands

Run from the repository root with the project environment activated:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
python scripts/week07_day02_robustness_sweeps.py
python scripts/week07_day02_robustness_sweeps.py
```

The first CLI call runs a **16-pair / 49-method-attempt stratified dry run**;
the second must execute zero new attempts and resume 49 existing records.
Review its `outputs/week07_day02_dry_run/` files and runtime before deciding
to run the larger study.

Only after confirming the dry run and resource budget:

```powershell
python scripts/week07_day02_robustness_sweeps.py --full
```

The full mode enumerates **486 physically meaningful compatible pairs and 963
method attempts**. The authoritative Windows run **has completed** all 963
attempts and is documented in `docs/daily/day_32_summary.md`. This mode
uses a different output directory, so it cannot overwrite dry-run evidence. The runner refuses a plan-fingerprint
mismatch when resuming. Use `--output` to select a separate results directory.

## Scientific design and exclusions

- The Day 31 grid contains 522 method-compatible pairs and 1,026 attempts.
- Rotation severity on a translation-only model is not geometrically valid.
- Scale severity under translation or rigid geometry is not supported by the
  declared model. After applying the frozen method catalog, 36 pair scenarios
  are excluded for these reasons, **not counted as algorithm failures**.
- Every candidate for a pair receives the same fixed/moving images and its
  stated transform model; all three seeds are distinct, deterministic geometric
  cases. For the same model and seed, non-geometric conditions share geometry.
- Noise, blur, gamma, occlusion, low texture, repeated-pattern appearance,
  multimodal intensity mapping, and field-of-view restriction use deterministic
  existing utilities or documented combinations. Severity is applied to moving
  appearance, not to ground-truth correspondences.
- For partial overlap, a centered rectangular moving-image field of view is
  generated and binary-searched against the **actual geometrically warped
  support**. The realized fraction is checked against the requested level
  within 0.03. A source-visibility mask is explicitly stored in the offline
  prepared pair; black pixel values are never used as a validity heuristic.
- Repeated pattern stress is an artificial periodic appearance overlay; it
  does not model a real physically repeated scene. The final report must state
  this limitation rather than generalize the result to real repeated patterns.
- The input image is the development `camera.png` from Day 31. The `moon.png`
  holdout file is content-hashed only; its image pixels are never loaded for
  Day 32 preparation, registration, or tuning.

## Ground-truth firewall

Each generated pair is independently checked with matrix-inverse and control-
point round-trip errors. `RegistrationService` receives `UNAVAILABLE` ground
truth and no reference matrix or landmarks. **Only after it returns** does the
offline evaluator compare estimated Moving -> Fixed geometry to the synthetic
reference via TRE and parameter error. A completed registration is not treated
as proof of correctness. Geometric success uses the tracked Day 31 pilot TRE
threshold of 2.0 px and transform plausibility. This is an **experimental
threshold**, not a calibrated clinical or production guarantee.

## Results and interpretation

Every attempted task, including CHECK, failed, validation-error, and geometry-
threshold failures, remains in the benchmark journal and aggregate **denominator**.

Under `outputs/week07_day02_dry_run/` (or `..._full/`):

- `benchmark_plan.json`, `benchmark_records.jsonl`: immutable experiment IDs,
  task provenance and terminal results.
- `benchmark_results.csv`, `benchmark_summary.json`: standardized runner data.
- `severity_summary.csv`, `severity_summary.json`: per-condition, severity,
  model, modality and method attempts, execution rates, unconditional geometric
  success rates, TRE conditional on estimated transforms, and runtime.
- `day32_manifest.json`: input hashes, frozen catalog hash, generator code
  hash, preflight overlap and independent-geometry-check evidence.

The generator code hash and severity version are part of each Day 32 task's
identity. Changing pair generation cannot silently resume data generated with
an earlier implementation. Source and frozen-method hashes are also preserved.

## Environment and interpretation notes

The original development container lacked SimpleITK, so its early local MI
failures were dependency-related and are **not** registration performance
evidence. The authoritative Windows environment has since completed both
the 49-attempt stratified dry run and the full 963-attempt benchmark. Do not
replace its results with the local container's partial pilot. Results remain
development-only synthetic evidence, not final recommendation scores.
Calibration and confidence/outlier thresholds are deferred to Day 34 and
independent Week 8 assessment.

## Sharing Day 32 benchmark evidence

The project ZIP utility defaults to a lightweight code/configuration archive and
continues to omit `outputs/` unless evidence is explicitly requested. To send
the complete Day 32 generated results alongside the code, run from the repository
root:

```powershell
python scripts/zip_project.py --include-benchmark week07_day02_full
```

To share only the selected benchmark outputs:

```powershell
python scripts/zip_project.py --evidence-only week07_day02_full
```

Both modes retain `outputs/week07_day02_full/` paths in the archive. They include
JSON, JSONL, CSV, documentation and result images, but omit unrelated runs,
raw source datasets, cache folders, logs, temporary files and common secrets.
Only direct directory names within `outputs/` are accepted; paths and symlinks
are rejected. Review any benchmark files for sensitive data before sharing.

The benchmark run itself is not altered or rerun by ZIP creation.

## Formal Day 32 closure (2026-10-21)

- Windows suites: 468 backend and 149 UI tests passed.
- Dry run: 49 attempts, 48 Completed, 1 CHECK, 0 Failed; resume reused all 49.
- Full run: 963 attempts across 486 pairs, 934 Completed, 4 CHECK, 25 Failed,
  0 validation errors.
- Offline ground-truth scoring: 840/963 (87.23%) meet the development TRE and
  plausibility criterion. There are 94 geometrically incorrect Completed
  records, 4 CHECK records with incorrect geometry, and 25 execution failures.
- The journal, CSV, plan and manifest were reconciled by unique task/pair ID.
- Full-run zero-execution resume was not separately demonstrated; do not
  treat this as a failed check, but preserve the distinction from dry-run resume.
- See `reports/week07_day02_full_closure.json` for hashes and machine-readable
  validation evidence, and `docs/daily/day_32_summary.md` for interpretation.
- Day 33 is next and not started. Frozen registration algorithms and UI v0.2
  remain unchanged.
