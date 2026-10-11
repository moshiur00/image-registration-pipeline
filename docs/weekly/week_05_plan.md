# Week 5 Plan: Multimodal Registration with Mutual Information

## Week objective

Complete a controlled Mutual Information registration stage that covers synthetic multimodal validation, parameter selection, affine registration, real RIRE CT/MR-T1 physical-space registration, and an integrated comparison against the existing monomodal baselines.

The week keeps the project transform convention as `Moving -> Fixed`. SimpleITK optimizer completion and geometric correctness remain separate result states. Synthetic multimodal mappings are used for controlled ground-truth experiments and do not replace real multimodal validation.

## Day 21: Rigid Mattes Mutual Information foundation

### Technical work

- Validate the 2D rigid SimpleITK Mattes Mutual Information path.
- Preserve spacing, origin, and direction in the SimpleITK path.
- Confirm conversion from the SimpleITK Fixed -> Moving resampling transform to the project Moving -> Fixed transform.
- Use multiresolution shrink factors and smoothing sigmas.
- Record metric trace, optimizer stop condition, valid metric points, runtime, and explicit failure reasons.
- Preflight all configured simulated multimodal mapping names before registration begins.

### Controlled experiment

Run the frozen six-case set:

- monomodal reference;
- intensity inversion;
- nonlinear gamma;
- histogram remapping;
- multiplicative bias field;
- edge-emphasized representation.

### Evaluation

Record TRE, rotation error, centered translation error, optimizer success, geometric tolerance status, final Mattes MI value, valid metric points, runtime, and failure reason.

### Completion criterion

The full test suite passes on the target Windows environment and all six configured cases finish without infrastructure or configuration errors. Any geometrically incorrect case remains recorded as a valid failure and is not retuned away on Day 21.

## Day 22: Rigid MI initialization, sampling, and parameter study

### Technical work

- Compare identity, geometry, and moments initialization on a limited validation subset.
- Evaluate histogram-bin count on a small controlled set.
- Compare full, regular, and random metric sampling.
- Evaluate a limited set of sampling percentages for sampled metrics.
- Repeat random sampling with multiple fixed seeds to measure variability.
- Add joint-histogram views and metric-versus-iteration plots.
- Evaluate multimodal-safe preprocessing options without forcing identical intensity histograms.

### Experimental rule

Use one-factor-at-a-time studies where practical. Do not perform a large unrestricted grid search. Select settings using a validation subset, then freeze them before later Week 5 evaluation.

### Evaluation

Compare success rate, TRE, parameter error, convergence behavior, valid metric samples, runtime, and seed variability.

### Completion criterion

A documented rigid MI configuration is frozen for later synthetic and real-data work, with the selection supported by recorded validation evidence rather than final-test tuning.

## Day 23: Affine Mutual Information and multiresolution capture range

### Technical work

- Extend the MI registration module to 2D affine transforms.
- Preserve the existing physical-coordinate and transform-direction conventions.
- Reuse the frozen MI metric and optimizer configuration where appropriate.
- Add affine plausibility checks and explicit optimizer failure handling.
- Validate multiresolution transform transfer and resampling.

### Controlled experiment

Use known synthetic affine ground truth with monomodal and simulated multimodal appearance mappings. Include mild and moderate affine cases plus at least one difficult partial-overlap or intensity-mismatch case.

Compare rigid and affine MI only on shared cases where that comparison is meaningful, especially true-affine cases that expose model mismatch.

### Evaluation

Record TRE, affine-matrix error, centered translation error, optimizer status, final metric, runtime, and failure reason.

### Completion criterion

Affine MI runs reproducibly on the controlled validation set, returns the project Moving -> Fixed transform, and preserves failed or implausible estimates as explicit result records.

## Day 24: Real RIRE CT/MR-T1 physical-space registration

### Technical work

- Extend or adapt the MI path for the prepared 3D RIRE CT and MR-T1 volumes.
- Preserve voxel spacing, origin, direction, and physical coordinates.
- Add rigid 3D initialization based on image geometry or centers.
- Add affine 3D only if the rigid physical-space path is validated first and implementation remains reliable.
- Add real-data preprocessing that preserves modality differences.
- Store before/after joint histograms, selected slices, overlays where meaningful, optimizer traces, and metadata checks.

### Real-data evaluation rule

Use landmarks or masks for TRE or Dice only if a verified reference is available and integrated. If no verified reference is available, report optimizer behavior, physical transform plausibility, metadata integrity, overlap, and visual diagnostics without claiming anatomical correctness.

### Completion criterion

The RIRE CT/MR-T1 pair runs in physical coordinates without metadata loss or silent axis changes, and the report clearly separates verified geometric evidence from descriptive alignment diagnostics.

## Day 25: Integrated Week 5 benchmark and conclusions

### Technical work

- Freeze the Week 5 configurations selected on validation data.
- Run the integrated synthetic multimodal benchmark with the frozen rigid and affine MI settings.
- Compare MI with compatible ECC baselines on shared synthetic cases, especially intensity inversion, histogram remapping, edge emphasis, gamma change, and bias-field cases.
- Include repeated stochastic MI runs where random sampling is used.
- Integrate the real RIRE result separately from synthetic results.
- Generate compact tables, joint-histogram figures, convergence plots, overlays, and failure examples.

### Final analysis

Report methods by operating condition rather than a universal ranking. Separate:

- monomodal from multimodal evidence;
- rigid from affine motion models;
- optimizer success from geometric success;
- synthetic ground-truth conclusions from real-data descriptive evidence.

### Completion criterion

Week 5 closes with reproducible rigid and affine MI modules, frozen configurations, synthetic multimodal quantitative evidence, real RIRE physical-space evidence, stochastic-variability results, explicit failure cases, and a documented comparison with compatible ECC baselines.

## Week 5 deliverables

- tested rigid and affine Mutual Information registration modules;
- physical-coordinate medical-image registration path;
- initialization, histogram-bin, sampling, and stochastic-repeat evidence;
- synthetic multimodal comparison against compatible ECC baselines;
- real RIRE CT/MR-T1 registration evidence;
- joint histograms and convergence traces;
- machine-readable result snapshots;
- Week 5 findings and limitations documentation.

## Freeze and reporting rules

- Do not change Day 21 thresholds merely to convert a failed registration into a pass.
- Select tunable MI settings on a limited validation subset before final Week 5 evaluation.
- Preserve every optimizer failure, threshold failure, and configuration failure.
- Never interpret a high final MI value alone as proof of geometric or anatomical correctness.
- Keep real RIRE conclusions separate from synthetic multimodal conclusions.
- Do not proceed to Week 6 until the Day 25 integrated report is reproducible from saved configuration and result files.
