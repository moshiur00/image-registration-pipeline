# Day 33 Summary: Failure Diagnosis and Computational Analysis

**Status: COMPLETE, closed on 2026-10-21.** Windows regression, failure analysis, profiling and independent review of the uploaded Windows-generated evidence have passed. Day 32 remains closed and its original evidence is unchanged.

## Implementation and scope

- `src/image_registration/week7_failure_analysis.py` validates the frozen Day 32 journal, classifies **observed outcomes**, and includes both Failed and CHECK records in denominators.
- `scripts/week07_day03_failure_analysis.py` produces descriptive severity and runtime plots and a deterministic **reconstructed** failure gallery. The optional `--profile` experiment runs separately; it does not alter Day 32 results.
- The Matplotlib 3.11 horizontal boxplot now uses `orientation="horizontal"`, with regression-test coverage.
- Neither the registration algorithms, frozen method configurations nor UI v0.2 was modified by this closure.

## Final authoritative Windows validation

- Backend: **504 passed, 2 skipped, 0 failed**. Both skips concern symlink creation unsupported in the user's Windows environment.
- UI: **149 passed, 0 failed**.
- `python scripts/week07_day03_failure_analysis.py --profile` completed without the previous deprecation warning.
- CLI: **963 original records, 840 development geometric successes, 13 charts, 12 gallery panels, 6 CPU/sampled-RSS profiles**.

## Independent artifact review

- The uploaded Day 33 ZIP passes ZIP integrity checks and contains 963 unique classified attempt IDs, matching all Day 32 status and geometric-success totals.
- All **13 plots and 12 gallery panels** decode as valid PNG images; selected gallery panels were visually inspected, including a failed ORB Affine occlusion case and a failed SIFT Similarity repeated-pattern case.
- The **6 representative Windows CPU/RSS samples** cover ECC Rigid and ORB Affine at image sizes 96, 192 and 384 pixels; all six are recorded as completed.
- Day 32's seven original evidence files were retrieved from the earlier user-supplied evidence archive and verified against the SHA-256 checksums in `reports/week07_day02_full_closure.json`; the Day 33 source-journal checksum matches the original record checksum.
- Original Day 32 records and uploaded Day 33 results have been retained unchanged in the closure ZIP.

## Research findings and limits

- **840/963 = 87.23%** reached the synthetic-development 2 px TRE and plausibility criterion; **123** were geometrically unsuccessful, including **25** execution failures and **4** CHECK cases.
- Observed categories: **24** feature-correspondence execution failures, **1** optimizer execution failure, **4** implausible transforms, **41** large geometric errors greater than 20 px, and **53** other geometric threshold failures. Labels describe outcomes, not proven mechanistic causes.
- Three supported failure behavior groups for further study: repeated-pattern correspondence failures (20 of the 25 execution failures), degraded/partial overlap producing wrong geometry, and severe ECC Affine occlusion CHECK errors.
- Gallery images are deterministic *reconstructions*, not captured original algorithm outputs. Profile RSS is sampled process-wide memory, not an exact peak allocation or isolated algorithm memory.
- Method and condition groups have different denominators. No calibrated confidence score, universally best method or production recommendation is established. Week 8 data remain held out.

## Evidence and status

- `reports/week07_day03_closure.json` is the permanent closure record.
- `reports/week07_day03_windows_validation.json` records final target-machine checks.
- `outputs/week07_day03_analysis/day33_manifest.json` retains its original generation-time `analysis_generated_review_pending` state to preserve the user's generated evidence. The separate closure report records subsequent independent review.

**Next:** Day 34, offline development-only evidence calibration and abstention analysis; Day 34 is not started.
