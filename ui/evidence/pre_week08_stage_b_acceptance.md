# Pre-Week 8 Stage B: UI Acceptance and Freeze Checklist

**Status: ATTESTATION V2 IMPLEMENTED, AUTOMATED QA PASSED, HUMAN WINDOWS QA PENDING (0/5 SCENARIOS + 0/5 SUPPLEMENTAL).**

This stage validates the existing UI v0.2 Automatic Comparison Preview. It does not introduce method ranking, deploy the Day 34 policy, or approve the Week 8 evaluation. UI v0.2 is a **release candidate**, not formally frozen, until every manual interaction below has been observed and documented on the target Windows environment.

## Protection and test boundaries

- The QA images are generated from `data/samples/week02_real_general/camera.png`, a **known development source**. They are explicitly ineligible for independent Week 8 evaluation.
- QA images and human observations are stored only under `ui/runtime/pre_week08_stage_b/` and excluded from Git and ordinary project exports.
- Registration algorithms, frozen method settings, source-use ledger, and Day 32 to Day 35 evidence are not modified.
- Automatic Comparison runs compatible methods for **one manually selected transform model**. It does not infer the correct motion model or issue a validated winner.
- A manual operator note records **what was observed**. It is not inferred automatically from passing pytest tests.

## Setup on Windows

From the project root with the project environment active:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pytest -c ui/pytest.ini ui/tests -v
.\.venv\Scripts\python.exe scripts/pre_week08_stage_b_ui_qa.py prepare
.\.venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Select **Automatic comparison** from the sidebar. Fixture images are generated into `ui/runtime/pre_week08_stage_b/`. The fixture manifest lists SHA-256 checksums of the PNG upload bytes.

## Five manual acceptance scenarios

### B1. Simulated multimodal input

1. Upload `multimodal_fixed.png` as Fixed and `multimodal_moving.png` as Moving.
2. Select **Multimodal**, **Affine**, optional methods enabled.
3. Confirm that the compatible-method table contains **Mattes MI Affine 2D** and excludes monomodal-only methods with readable reasons.
4. Click **Run automatic comparison**. Verify that completion, CHECK or failure is displayed accurately. Actual MI success depends on the installed SimpleITK environment and optimization behavior.
5. Verify that the view does **not** claim TRE, geometric PASS, a best method, or calibrated confidence for these uploads.

Do not mark PASS simply because MI is the only compatible method. Inspect the rendering and state semantics in the real UI.

### B2. Single-candidate, insufficient agreement

1. Retain the same pair and Multimodal + Affine configuration.
2. Confirm that exactly one compatible candidate is offered, even if optional methods are enabled.
3. Run the comparison. If the candidate provides a valid transform, the agreement section must state that pairwise agreement is **insufficient**, with **no consensus anchor**. If MI fails, it must still report no agreement rather than invent one.
4. If an analysis ZIP can be prepared, inspect `analysis.json` and verify that its agreement presentation indicates insufficient candidates and no unique anchor.

### B3. Failed or CHECK candidate preservation

1. Upload `flat_fixed.png` and `flat_moving.png`.
2. Select **Monomodal**, **Affine**, optional methods enabled.
3. Run automatic comparison. Flat images intentionally lack features and should challenge feature estimators. **The script does not guarantee a specific optimizer outcome.**
4. If a Failed or CHECK candidate appears, verify that it remains in the comparison table, shows a reason or diagnostics, is inspectable in the candidate panel, and appears in `candidate_execution_issues.csv` when exporting.
5. If no Failed or CHECK candidate occurs, record **blocked/inconclusive**, not PASS. Review the UI with an independently controlled test fixture before freezing.

A candidate may fail to yield a transform, so inspection-only registered images may be absent; this must be explained rather than treated as a UI crash.

### B4. Stale state and export invalidation

1. Upload `paired_fixed.png` and `paired_moving.png`, set **Monomodal + Affine**, and run automatic comparison.
2. Click **Prepare automatic analysis ZIP**, and verify that the download control appears.
3. Change **Gaussian smoothing sigma** or **Include optional methods** without pressing Run. Confirm the old results and prepared-download control disappear.
4. Run again, prepare another ZIP, then replace Moving with `altered_moving.png`. Confirm invalidation again.
5. Remove one upload and confirm that results, candidate selection and export control clear while still showing an informative upload prompt.

The upload and configuration controls should remain usable after state invalidation.

### B5. Analysis ZIP provenance and safety

1. Return to the `paired_fixed.png` / `paired_moving.png` case and run it.
2. Prepare and download the automatic analysis ZIP.
3. Verify that the ZIP includes `analysis.json`, `manifest.json`, candidate comparison CSV, issues CSV and per-candidate evidence JSON.
4. Verify that `manifest.json` has `fixed_sha256` and `moving_sha256` identical to the **raw uploaded PNG bytes** (the hashes in `ui/runtime/pre_week08_stage_b/fixtures_manifest.json`).
5. Verify `ground_truth=unavailable`, `recommendation_status=deferred_until_robustness_calibration`, `source_image_bytes_included=false`, transform direction **Moving -> Fixed**, and no geometric accuracy claim.
6. Inspect registered images only when available. All reconstructions must be marked `INSPECTION_ONLY`; CHECK and Failed candidates must not disappear from evidence.

## Recording manual observations

After a named human reviewer actually observes each scenario, retain the
screenshots and downloaded analysis ZIPs under
`ui/runtime/pre_week08_stage_b/`. The recorder rejects evidence outside that
directory and rechecks its SHA-256 and byte size whenever status or a report is
read. Record against the exact checked-out `HEAD` in a clean Git worktree;
ignored runtime evidence is allowed, while tracked or ordinary untracked
changes block attestation. Relative evidence arguments are resolved from that
runtime directory, so pass a filename or runtime-relative path rather than
repeating `ui/runtime/pre_week08_stage_b/`.

Every record requires one or more screenshots. Passed `single_candidate`,
`failed_check`, and `export_provenance` records also require a readable ZIP.
A named human reviewer must separately attest the five supplemental checks listed
under the freeze criteria; `status` stays pending until all ten required
observations pass.
For example:

```powershell
$reviewer = "<human reviewer name>"
$platform = "Windows 11 x64 <build>"
$environment = ".venv; Python <version>; Streamlit <version>; SimpleITK <version>"
$releaseCommit = (git rev-parse HEAD).Trim()

.\.venv\Scripts\python.exe scripts/pre_week08_stage_b_ui_qa.py record multimodal pass `
  --reviewer $reviewer --platform $platform --environment $environment `
  --release-commit $releaseCommit `
  --screenshot b1_multimodal.png `
  --note "MI Affine was the sole compatible method; status was accurate; no TRE, winner, or confidence was shown"

.\.venv\Scripts\python.exe scripts/pre_week08_stage_b_ui_qa.py status
```

Record each supplemental observation with `record-supplemental`. The available
check IDs are `normal_monomodal`, `unknown_upload_claim_suppression`,
`rire_technical_only_caveat`, `candidate_inspection_labels`, and
`no_frozen_location_writes`:

```powershell
.\.venv\Scripts\python.exe scripts/pre_week08_stage_b_ui_qa.py record-supplemental normal_monomodal pass `
  --reviewer $reviewer --platform $platform --environment $environment `
  --release-commit $releaseCommit `
  --screenshot supplemental_normal_monomodal.png `
  --note "Normal monomodal Affine comparison completed and retained truthful unknown-ground-truth limits"
```

Use `pass`, `fail` or `blocked` truthfully. The `status` command exits with
nonzero status until **all five scenarios and all five supplemental checks**
are manually attested PASS. No command automatically marks an observation
passed. Screenshot or ZIP proof can be retained separately, but never include
private image bytes in a public report.

After 5/5 scenario acceptance, 5/5 supplemental acceptance, and the full
suites, generate the sanitized tracked report with the exact observed counts
and the three recorded DEFERRED scope decisions:

```powershell
.\.venv\Scripts\python.exe scripts/pre_week08_stage_b_ui_qa.py report `
  --backend-passed <count> --backend-skipped <count> --backend-failed 0 `
  --ui-passed <count> --ui-skipped <count> --ui-failed 0 `
  --stage-c DEFERRED --rire-expansion DEFERRED --recommendation-path DEFERRED
```

## Automated checks and freeze criteria

- Run `.\.venv\Scripts\python.exe -m pytest -c ui/pytest.ini ui/tests/test_pre_week08_stage_b_acceptance.py -v`.
- Run the full backend and UI suites on Windows. Record exact pass, skip, and failure counts.
- Review the manual screenshots, results, and ZIP artifacts. Mark any unsupported or unobserved scenario blocked.
- Confirm the Stage A frozen-source and Week 7 evidence preflight still passes its corresponding checks. A BLOCK for an unregistered independent Week 8 source remains legitimate.
- Only after every scenario and supplemental check passes, update `ui/DEVELOPMENT_STAGES.md`, `ui/README.md`, and the progress registry to **UI v0.2 FROZEN**. Do not freeze the UI based on the test suite alone.

**Current decision (2026-11-13):** The hardened evidence contract is ready and
its 30 focused tests pass. Human acceptance and formal freeze remain pending at
0/5 scenarios and 0/5 supplemental checks. Stage C Research Evidence,
interactive RIRE expansion, and the dormant
recommendation display path are DEFERRED. Week 8 held-out data has not been
opened for these QA fixtures.
