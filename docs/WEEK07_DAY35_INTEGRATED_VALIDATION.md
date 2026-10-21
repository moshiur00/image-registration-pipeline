# Week 7 Day 35: Combined-stress integration and Week 8 handoff

**Status: implemented, local dry execution and regression tested; Windows validation pending.**

This stage finishes the development integration work without changing frozen registration methods or Streamlit UI v0.2. This does **not** close Week 7, validate a deployable selector, or use the Week 8 held-out source.

## Inputs and provenance

- Read-only complete Day 32 evidence: `outputs/week07_day02_full/`, 963 attempts and 486 development pairs.
- Read-only exploratory Day 34 policy: `outputs/week07_day04_calibration/tentative_policy_not_for_ui.json`, linked by SHA-256 to Day 32's original journal.
- Frozen method catalog: `configs/week07_day01_frozen_methods.yaml`.
- Development-only image pixels: `data/samples/week02_real_general/camera.png`, resized using the frozen Day 32 grid.
- Week 8's `moon.png` is **not loaded**. Day 35 does not use or tune on Week 8 data.
- Original Day 32 evidence and Day 34 policy hashes are checked again after the run.

## Controlled combined stresses

Forty deterministic image pairs use **new** geometry seeds 202 and 303, disjoint from the Day 34 calibration/audit seeds 7, 42 and 101. Ground truth is Moving -> Fixed and kept entirely outside the registration service.

| Study class | Geometric models | Condition pairs |
|---|---|---|
| Monomodal | Translation, rigid, similarity, affine | Noise + blur; blur + 25% occlusion; 65% target valid overlap + illumination; weak texture + repeated pattern |
| Simulated multimodal | Rigid, affine | Intensity inversion + noise; histogram remapping + blur |

The design yields 40 pairs and **88 compatible frozen-method registration attempts**. This is intentionally a small development integration suite, not a replacement for Day 32's severity grid. Each case has exact offline reference geometry, a checked valid-support mask, a seed-dependent reproducible image appearance and a content-hash-bearing experiment ID. Motion parameters remain matched across combined appearances for a given model and seed. Missing combinations are excluded on method/model/modality compatibility, not counted as algorithm failures.

## Command

From the repository root:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
python scripts/week07_day05_integrated_validation.py
```

**Run the command again to check resuming:** `Executed 0`, `resumed 88` is the expected post-run behavior. The default writes to `outputs/week07_day05_integration/`. Never reuse that folder after changing frozen configuration or the generator code; the runner rejects a mismatched plan.

This supplied code archive deliberately **does not contain a Day 35 Linux execution journal**, so the first Windows run executes all 88 tasks with your working SimpleITK installation. The local authoring host lacks SimpleITK and its 24 MI attempts failed because of the dependency; those are preserved only in the *local preview summary*, not handed to Windows for resume. Do not interpret the local preview as Windows performance or as the Week 7 final outcome.

The generated output directory contains:

- `benchmark_plan.json`, `benchmark_records.jsonl`, `benchmark_results.csv`, `benchmark_summary.json`
- `day35_report.json`, `day35_manifest.json`
- `combined_stress_summary.csv`, `week07_comparison_matrix.csv`
- `offline_policy_decisions.csv`, `condition_specific_guidance.csv`, `recurring_failure_types.csv`
- `stratified_failure_review.csv`, `gallery/gallery_manifest.json`, and up to ten reconstructed gallery PNGs
- `plots/combined_condition_success.png`, `combined_runtime_by_method.png`, `frozen_policy_abstention.png`, `development_study_comparison_not_matched.png`

The comparison matrix deliberately retains different denominators and study labels for one-factor versus combined-stress experiments. It is a *descriptive side-by-side*, not a paired treatment-effect estimate or a justified universal ranking. TRE summaries condition on methods returning a transform; geometric-success rates include Failed and CHECK attempts in their denominators.

## Frozen exploratory evidence policy

The Day 34 three-family agreement gate is read from the *unmodified* policy JSON. Candidate selection uses only an explicit observable allowlist: method family, completed status, estimated transform, plausible flag, overlap and method-specific diagnostics. No synthetic truth, TRE, severity label or failure categorization enters the gate. Ground truth is used **after** selection to report synthetic correctness or abstention. There is no retuning, confidence percentage, deployed recommendation or UI change. A zero-support outcome is a legitimate conservative result and must not be converted into unconditional confidence.

## Failure diagnosis and human review

The `recurring_failure_types.csv` summarizes at least three observed Day 32 categories using its existing Day 33 taxonomy: feature correspondence breakdown, large wrong-geometry estimates, and smaller ground-truth threshold failures. The separate CHECK and implausible-transform category is retained as well. Condition labels are associated stresses, not proven root causes.

Day 35 automatically constructs a stratified **candidate** review CSV and up to ten image panels with Fixed, Moving, Reconstructed (if any), and valid-mask-only difference. Panels reconstruct the scene deterministically from saved provenance; they are *not* recovered original algorithm-rendered outputs. Inspect the review queue and enter manual notes before formally closing Day 35; the code does not falsely claim that a human has inspected those panels. The Day 33 12-panel gallery remains available for comparison.

Six condition-specific conservative guidance entries accompany observed sample counts. These are handling recommendations and proposed precautions, **not calibrated method recommendations**.

## Validation / closure requirements

1. On Windows, backend and UI regression suites pass (existing Day 34 baseline was 530 passed, 2 symlink skips; UI 149 passed).
2. All 88 compatible tasks have unique journal IDs; run once, then verify `Executed 0 / resumed 88`.
3. Check the zero validation-error constraint and inspect all CHECK/Failed attempts without dropping any rows.
4. Verify all four charts, up to ten gallery images, manual-failure-review queue, and six guidance rows.
5. Inspect the Day 35 report and calibration decisions, including coverage and abstentions. Do not promote a zero-error-but-zero-coverage policy.
6. Verify SHA-256 provenance against original Day 32 records and the Day 34 policy. All outputs remain development-only.
7. Close Day 35 only after Windows output inspection. Week 8 should evaluate the unchanged candidate policy independently on previously reserved held-out cases. If new data or results suggest modifying the policy, freeze a new version and evaluate it with new, genuinely independent held-out data.

## Reproducible packaging after Windows execution

```powershell
python scripts/zip_project.py --include-benchmark week07_day05_integration
```

This includes Day 35 generated evidence; the current supplied full ZIP also retains the original Day 32-Day 34 evidence for provenance. If the sharing tool excludes other output directories, do not overwrite or rerun Day 32 or Day 34 to regenerate them. Refer to their original immutable archives.

## Windows execution results and formal development handoff

The Windows run passed 552 backend tests (3 expected skips) and 149 UI tests. The combined stress execution completed 88/88 unique tasks: 77 Completed, 11 Failed, 0 CHECK, 0 validation errors; 61 were geometrically correct offline. A repeat execution resumed all 88 without running another task. The 11 failures comprise 9 insufficient filtered matches and 2 insufficient RANSAC inliers.

The frozen agreement gate tentatively supported 2 of 40 development pairs, both synthetic geometry correct, and abstained on 38. This is not calibrated probability or broad robustness. The source evidence and policy hashes were validated against the original Day 32 to Day 34 preserved archive. No held-out Week 8 data were used.

Four plots and ten reconstruction-based case panels were visually inspected by the assistant and recorded in `reports/week07_day05_gallery_visual_review.json`; independent human signoff is recommended before publication. The gallery output metadata remain an immutable record of the original run, including any pre-review wording. The complete closure archive includes the user's Windows Day 35 execution journal and recovered matching Days 32 to 34 baseline evidence; unlike the earlier implementation archive, it is suitable for resuming and inspection, not for blindly rerunning the first-run 88 attempts.

Day 35 and the Week 7 development stage are now closed. See `reports/week07_day05_closure.json` and `reports/week07_week_closure.json`. Week 8 remains pending.
