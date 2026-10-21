# Day 32 Summary: Controlled Robustness Sweeps

## Official status

**Complete and Windows validated, closed 2026-10-21.**

The development-only full benchmark is complete. Day 33 has **not started**. This closure is not a claim that any registration method or recommendation policy is calibrated for new real-world data.

## Implementation delivered

- `src/image_registration/week7_sweeps.py` generates the ten controlled severity families, deterministic seed-matched geometries, independently checked reference transforms, and geometric source-support masks.
- `scripts/week07_day02_robustness_sweeps.py` executes compatible candidates using the frozen method catalog, `RegistrationService`, and the resumable Week 6 runner. Reference geometry stays outside the registration service and is used only for offline evaluation.
- `tests/test_week7_day32_sweeps.py` covers deterministic geometry, transformation and overlap validity, compatibility, split isolation, method execution, and failure-preserving denominators.
- `docs/WEEK07_DAY32_CONTROLLED_SWEEPS.md` provides commands, experimental limitations, and evidence paths.

## Authoritative Windows validation

- Backend tests: **468/468 passed** in **7.03 seconds**.
- UI tests: **149/149 passed** in **5.19 seconds**.
- Dry run: **16 pairs / 49 attempts**; 48 Completed, 1 CHECK, 0 Failed, 0 validation errors.
- Dry-run resume: **0 executed, 49 reused** on the second run.
- Full run: **486 image pairs / 963 compatible attempts**, 934 Completed, 4 CHECK, 25 Failed, 0 validation errors.
- Full run: **963 distinct experiment IDs and 486 distinct pair IDs**. The complete CSV, JSONL, and benchmark summary agree with the manifest.
- 36 Day 31 pair scenarios were excluded because their requested rotation/scale stress was incompatible with the declared transform model. These are **not algorithm failures**.

## Offline geometric outcome (development evidence)

Geometric success is defined as **TRE at most 2.0 pixels and a plausible transform** against known synthetic reference geometry. All attempted methods, including CHECK and Failed, remain in the denominator.

- **840/963 (87.23%)** pass the development geometric criterion.
- **123/963 (12.77%)** do not pass.
- **94 Completed** cases returned transforms but missed the criterion; **4 CHECK** cases missed it; **25 Failed** cases had no valid estimated transform.
- All four CHECK cases involved ECC Affine under occlusion, with very large geometric errors, and must remain visible for Day 33.
- Execution failure reasons: `insufficient_filtered_matches` (21), `insufficient_ransac_inliers` (3), `ecc_pyramid_level_failed` (1).

### Per-condition geometric success

| Condition | Successes / attempts | Rate |
|---|---:|---:|
| Gaussian Blur | 107/108 | 99.07% |
| Gaussian Noise | 108/108 | 100.00% |
| Illumination | 108/108 | 100.00% |
| Low Texture | 108/108 | 100.00% |
| Multimodal Mapping | 13/18 | 72.22% |
| None | 36/36 | 100.00% |
| Occlusion | 82/108 | 75.93% |
| Partial Overlap | 75/108 | 69.44% |
| Repeated Pattern | 69/108 | 63.89% |
| Rotation | 79/90 | 87.78% |
| Scale | 55/63 | 87.30% |

These condition groups contain different method/transform mixes. Values are observational development evidence, not cross-condition controlled method rankings. In particular, simulated multimodal mapping includes only 18 attempts.

## Files and reproducibility

The full benchmark evidence is preserved under `outputs/week07_day02_full/`:

- `benchmark_plan.json`
- `benchmark_records.jsonl`
- `benchmark_results.csv`
- `benchmark_summary.json`
- `day32_manifest.json`
- `severity_summary.csv`
- `severity_summary.json`

A compact, hash-linked closure artifact is saved at `reports/week07_day02_full_closure.json`. It records the full Windows validation, run totals, condition summaries, CHECK cases, failure reasons, and SHA-256 hashes for each evidence file.

To create a combined source-and-evidence archive without rerunning the benchmark:

```powershell
python scripts/zip_project.py --include-benchmark week07_day02_full
```

Full-mode resume without re-execution was **not separately demonstrated** in the supplied evidence; dry-run resume and runner tests were validated. No need to rerun valid experiments solely to collect poor-performing cases.

## Day 33 handoff (not started)

Use the frozen Day 32 records for failure taxonomy, catastrophic-case gallery, CPU/runtime and peak-memory profiling, severity curves, and success-versus-TRE analyses. Review schema caveats: the flat CSV `seed` field is empty (the actual `geometry_seed` is in `pair_metadata_json`) and `valid_overlap_fraction` appears in more than one flattened context. Interpret columns explicitly rather than silently merging them.

Do not tune against Week 8 held-out data, change frozen registration methods, or enable uncalibrated recommendations/confidence. UI v0.2 remains unchanged.
