# Week 7 Day 33: Failure Diagnosis and Computational Analysis

## Scope and scientific boundary

The Day 33 analysis **reads the frozen Day 32 development-only terminal journal** and does not rerun or alter those 963 experiments. It produces a descriptive failure taxonomy, severity-success curves, runtime distributions, accuracy-runtime plots and a deterministic gallery of re-synthesized cases.

- Automatic registration algorithm implementations and frozen method catalog are unchanged.
- Ground truth is used **offline** to classify synthetic registration error. No ground-truth information enters candidate selection.
- A `Completed` status may still have TRE > 2 px. CHECK and Failed cases stay in the attempt denominator.
- A large-error gallery threshold of 20 px is a **display grouping**, not a new pass/fail gate, calibrated warning level, or method-selection rule.
- The development benchmark uses one `camera.png` source, synthetic modality mappings and periodic-stress appearance. This cannot justify real CT/MRI accuracy or a production confidence score.
- Plot groups with different transform models, modalities, and sample sizes are not directly comparable method rankings.

## Required inputs

The following original, complete, immutable files must exist under `outputs/week07_day02_full/`:

- `benchmark_records.jsonl`
- `day32_manifest.json`

The CLI validates the full 963-attempt journal, experiment uniqueness, full-run provenance, development-only split, task/record identity and manifest consistency. It rejects incomplete or tampered records. A source/generator checksum guard prevents reconstruction with changed code or development images. All other Day 32 files remain intact.

The included project ZIP contains the authoritative Day 32 evidence received earlier, since lightweight project archives normally omit `outputs/`. If using the regular ZIP generator without evidence, supply Day 32 results separately before running the CLI.

## Commands on Windows

From the repository root:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
python scripts/week07_day03_failure_analysis.py
```

Outputs are placed under `outputs/week07_day03_analysis/`. The command can be rerun to reproduce analysis reports without rerunning the registration algorithms. It does not write into the Day 32 evidence directory.

Optional separate CPU and sampled process RSS experiment (requires `psutil`):

```powershell
python -m pip install psutil
python scripts/week07_day03_failure_analysis.py --profile
```

The optional profile uses frozen ECC Rigid and ORB Affine settings at 96, 192 and 384 pixels. These are **new representative runs**, not part of the frozen Day 32 data. Process CPU includes work of the interpreter and library threads. Memory is process-wide RSS sampled approximately every 5 ms, not an exact native allocation peak and not per-method isolated memory. Comparisons share one warm process and may be sensitive to thread scheduling and caches. They should be treated as exploratory, rather than rigorous matched performance rankings.

## Output schema

- `failure_summary.json`: denominators, outcome category counts, stratified method/model/modality/condition summaries and limitations.
- `classified_attempts.csv`: one entry per original benchmark attempt, including geometry seed retrieved from `pair_metadata`, not the empty flat `seed` column.
- `condition_comparison.csv`, `condition_method_comparison.csv`, `method_comparison.csv`, `severity_curves.csv`: attempt-denominator success, conditional TRE and recorded runtime.
- `plots/`: condition-wise success, failure taxonomy, per-method recorded runtime boxes, runtime vs TRE and within-condition numeric severity plots.
- `gallery/`: synthetic fixed, moving, estimated rewarp and overlap-masked absolute difference images for selected representative attempts. These are **regenerated inspection reconstructions**, never claimed as verbatim original algorithm image outputs. Failures without estimated transforms are marked unavailable.
- `gallery/gallery_manifest.json`: attempt ID, status, method, condition, category, TRE where available, and image provenance.
- `day33_manifest.json`: hashes of Day 32 evidence, output inventory, environment and analysis status.
- Optional `representative_cpu_memory.csv` / `.json`: new exploratory CPU/RSS samples.

Each method/condition summary retains failure attempts in the success denominator. TRE medians use only records with estimated transforms and therefore must be read together with unconditional success rates.

## Preliminary local observations

The original Day 32 Windows journal contains 963 attempts across 486 pairs. It records 934 Completed, 4 CHECK and 25 Failed. Exactly 840 meet the experimental 2 px TRE plus plausibility rule. All 123 unsuccessful attempts remain in failure-taxonomy totals.

The descriptive categories in the generated local analysis were:

- Feature-correspondence execution failures: 24.
- Optimizer execution failures: 1.
- Implausible estimated transforms: 4.
- Geometrically incorrect estimated transforms above 20 px: 41.
- Other geometrically incorrect estimated transforms: 53.
- Geometrically successful attempts: 840.

These categories are **observed outcomes**, not proven mechanistic causes. Day 34 may test associations between observable diagnostics and geometry against development evidence only; Week 8 must use held-out evaluation before presenting calibrated recommendations.

## Day 33 acceptance gate

1. Back-end and UI regression suites pass on Windows with no changed registration behavior.
2. All 963 records validate and analysis totals reconcile with Day 32 closure.
3. Plots and gallery reproduce from the same frozen data and source hashes.
4. At least three recurring, supported failure behaviors can be illustrated with quantitative evidence and the gallery.
5. CPU/sample-memory profiling runs in Windows as a separate optional experiment and is reported with its measurement limitations.
6. Windows regression and command-level validation completed (504 backend passed, 2 unsupported-symlink skips; 149 UI passed; 963 records, 13 charts, 12 gallery panels; 6 `--profile` observations). The Windows-exported images and profiling CSV have been independently reviewed and passed the Day 33 closure gate. The Matplotlib 3.11 `vert` deprecation is resolved with `orientation="horizontal"`.

## Day 33 final closure

**Closed on 2026-10-21.** The complete Windows-generated Day 33 report archive was independently inspected. The original Day 32 journal checksum matches the preserved prior full-evidence upload. Windows regression is 504 passed / 2 symlink skips (backend) and 149 passed (UI). All 13 figures, 12 reconstructed gallery panels, and six exploratory process CPU/sampled-RSS rows are present and readable. Scientific limitations above remain unchanged. See `reports/week07_day03_closure.json`. No Day 34 calibrator or UI recommendation policy is activated by this closure.
