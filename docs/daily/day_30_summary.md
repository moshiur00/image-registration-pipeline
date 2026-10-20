# Day 30 Summary: Transform Agreement, Preliminary Consensus, and Week 6 Closure

## Objective

Add a ground-truth-free transform comparison layer over Day 29 automatic candidate evidence, generate preliminary consensus without selecting a final best method, produce robust method and runtime summaries, and run a small closure matrix before Week 7 robustness sweeps.

## Implementation

Day 30 adds:

- `src/image_registration/automatic_agreement.py`
- `tests/test_automatic_agreement.py`
- `configs/week06_day05_agreement_consensus.yaml`
- `scripts/week06_day05_agreement_consensus.py`
- `docs/WEEK06_AGREEMENT_AND_CLOSURE.md`
- `reports/week06_day05_agreement_consensus.json`

The comparison layer evaluates candidate Moving -> Fixed transforms on one deterministic image-space control grid. Pairwise displacement is summarized with RMS, median, p95, maximum, and image-diagonal-normalized RMS.

The transform medoid is exposed as a preliminary consensus anchor only. It is explicitly not a best-method recommendation.

## Closure matrix

The Day 30 development matrix contains four controlled affine cases:

- clean monomodal,
- Gaussian blur,
- Gaussian noise,
- simulated multimodal intensity inversion.

The automatic service still behaves as if ground truth is unavailable. Synthetic ground truth is used only after automatic execution for development validation.

## Local development evidence

The local environment executed the non-SimpleITK candidates and preserved the missing-SimpleITK Mattes MI attempts as failures.

Local development output:

- cases: 4,
- method catalog: 6,
- automatic candidate attempts: 13,
- completed: 9,
- failed: 4,
- validation errors: 0,
- ground truth exposed to automatic service: no,
- final method recommendation: deferred.

For the three monomodal cases, ECC, ORB, and SIFT produced enough successful transforms to create agreement views. The simulated-multimodal case had no locally executable candidate because Mattes MI requires SimpleITK in this environment, so its agreement state was correctly `insufficient_candidates`.

The target Windows environment regenerated the tracked report with SimpleITK available. All 13 automatic candidates completed successfully, including Mattes MI.

## Scientific interpretation

The agreement layer provides evidence that is unavailable from a single method:

- candidate transforms can be compared even when true geometric error is unknown,
- candidate disagreement can expose uncertainty or competing solutions,
- the transform medoid gives a stable descriptive reference,
- failed or implausible candidates do not disappear from the audit trail,
- one compatible method cannot establish cross-method consensus.

Agreement is not correctness. Several methods can agree on the same wrong solution, so Week 7 robustness calibration remains necessary.

## Target Windows validation

Day 30 and the full Week 6 closure were validated on the target Windows environment.

- Backend regression: 432 / 432 passed in 5.05 s.
- UI regression: 64 / 64 passed in 4.68 s.
- Closure cases: 4.
- Method catalog: 6.
- Automatic candidate executions: 13.
- Candidate terminal states: 13 completed, 0 CHECK, 0 failed, 0 validation errors.
- Ground truth exposed to automatic service: no.
- Final method recommendation: deferred.
- Agreement available for the three monomodal cases.
- The simulated multimodal intensity-inversion case correctly reported insufficient cross-method candidates because only Mattes MI was compatible.
- The consensus anchor remained a descriptive transform medoid only and was not promoted to a best-method claim.

Target agreement summaries:

- clean affine: median pairwise RMS 1.378 px, descriptive anchor SIFT + RANSAC Affine;
- blur affine: median pairwise RMS 0.988 px, descriptive anchor Mattes MI Affine;
- noise affine: median pairwise RMS 0.516 px, descriptive anchor SIFT + RANSAC Affine;
- intensity-inverted affine: insufficient candidates for cross-method agreement.

## Decision and next experiment

Day 30 is complete and Week 6 is formally closed.

The Week 6 evaluation contract, unified metric implementation, deterministic resumable benchmark runner, automatic multi-method execution contract, and transform-agreement layer are frozen for the next work package.

Week 7 will begin controlled robustness sweeps for noise, blur, rotation, scale, illumination, low texture, repeated texture, occlusion, partial overlap, and multimodal differences. Those results will provide the calibration evidence needed for later ranking, confidence, consensus thresholds, and abstention.
