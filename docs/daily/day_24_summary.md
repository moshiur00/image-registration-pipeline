# Day 24 Summary: Real RIRE CT/MR-T1 Physical-Space Registration

## 1. Purpose

Day 24 extends the validated 2D Mutual Information work to the prepared real RIRE `training_001` CT/MR-T1 pair. The goal is to validate a rigid 3D physical-space registration path while preserving medical-image geometry and keeping the evidence claims limited to what the current dataset preparation supports.

## 2. Setup

Fixed image:

```text
CT
```

Moving image:

```text
MR-T1
```

Prepared manifest:

```text
data/manifests/rire_training001.json
```

Expected local files:

```text
data/raw/rire/training_001/mha/training_001_ct.mha
data/raw/rire/training_001/mha/training_001_mr_T1.mha
```

The large MHA files remain local and are intentionally excluded from normal shared project ZIPs.

## 3. Variables changed

Day 24 changes the experiment from controlled 2D synthetic geometry to real 3D medical volumes in physical coordinates.

Two rigid initialization paths are executed:

- `geometry_multiresolution`, the primary physical-space path;
- `identity_multiresolution`, a diagnostic initialization comparator.

No affine 3D registration is introduced before the rigid path is reviewed.

## 4. Factors kept fixed

The validated Day 22 metric and optimizer choices remain fixed where applicable:

- Mattes Mutual Information;
- 32 histogram bins;
- full metric sampling;
- learning rate 2.0;
- minimum step 0.001;
- 200 iterations;
- relaxation factor 0.5;
- gradient magnitude tolerance 0.0001;
- shrink factors `[4, 2, 1]`;
- smoothing sigmas `[2.0, 1.0, 0.0]`;
- Gaussian preprocessing sigma 1.0, interpreted in physical units for the 3D medical path.

The stored project transform remains Moving -> Fixed. SimpleITK internally uses Fixed -> Moving during resampling, and the returned project matrix is the inverse.

## 5. Metrics and evidence rules

The current RIRE manifest states that verified reference landmarks are not integrated. Therefore Day 24 intentionally does not report:

- TRE;
- Dice;
- anatomical correctness;
- a quantitative claim that one initialization is more anatomically accurate.

Day 24 records instead:

- method execution success;
- optimizer metric trace and stop condition;
- valid metric-point count;
- physical Moving -> Fixed matrix;
- broad rigid-transform plausibility diagnostics;
- spacing, origin, direction, and output-grid integrity;
- physical field-of-view coverage before and after registration;
- before/after joint histograms;
- central x/y/z slice comparisons;
- before/after overlays;
- runtime;
- explicit failure reasons.

Physical field-of-view coverage is a geometry-only domain-overlap measure. It is not anatomical overlap.

## 6. Results

Target Windows validation completed successfully:

- full suite: `358 passed in 4.59s`;
- real RIRE rigid MI variants: 2;
- method success: 2 / 2;
- technical validation pass: 2 / 2;
- plausible rigid transforms: 2 / 2;
- metadata integrity: 2 / 2.

### Geometry initialization

- runtime: 10969.64 ms;
- optimizer iteration count: 10;
- final Mattes MI value: -0.646849;
- rotation magnitude: 5.435 degrees;
- translation magnitude: 33.576 mm;
- minimum bidirectional physical field-of-view coverage before registration: 0.818;
- minimum bidirectional physical field-of-view coverage after registration: 0.668.

### Identity initialization

- runtime: 14318.95 ms;
- optimizer iteration count: 15;
- final Mattes MI value: -0.646828;
- rotation magnitude: 5.424 degrees;
- translation magnitude: 33.508 mm;
- minimum bidirectional physical field-of-view coverage before registration: 0.818;
- minimum bidirectional physical field-of-view coverage after registration: 0.668.

Both runs preserved the fixed CT output geometry and passed the configured metadata checks.

## 7. Observations

Both initialization paths converged to nearly the same rigid physical transform and nearly identical final MI values. The translation components of the two Moving -> Fixed estimates differ by only about 0.074 mm in Euclidean norm.

Geometry initialization converged in fewer iterations and required about 23 percent less runtime than identity initialization on this pair.

The physical field-of-view coverage decreased after registration for both variants. The minimum bidirectional coverage changed from about 0.818 before registration to about 0.668 after registration. This result is preserved rather than filtered or tuned away.

## 8. Interpretation

Day 24 validates the technical real-data path: 3D rigid Mattes MI executes in physical coordinates, returns plausible rigid transforms, preserves medical-image metadata, and resamples onto the fixed CT grid.

The close agreement between geometry and identity initialization indicates initialization consistency for this specific pair. Geometry initialization is more efficient here, but the project does not interpret that as evidence of greater anatomical accuracy.

The reduced physical field-of-view overlap after registration requires caution. Field-of-view coverage measures geometric domain intersection only. It does not establish whether anatomical structures are better or worse aligned. Without verified RIRE landmarks or masks, the project cannot make that determination quantitatively.

## 9. Failure cases

No optimizer, transform-plausibility, metadata, or technical-validation failure occurred in the two configured Day 24 runs.

The decrease in physical domain overlap is retained as an important diagnostic observation rather than classified as an algorithm failure.

## 10. Limitations

- The real pair currently has no verified landmarks or masks integrated into the project.
- TRE, Dice, and anatomical correctness are therefore not reported.
- Visual overlays and joint histograms are descriptive only.
- Physical field-of-view coverage is not anatomical overlap.
- Only one real CT/MR-T1 pair is evaluated on Day 24.
- Day 24 evaluates rigid 3D registration only.
- A successful technical registration does not establish anatomical correctness.

## 11. Decision and next experiment

Day 24 is complete on the target Windows environment. Geometry initialization remains the primary documented real-data path because it converged to essentially the same solution as identity initialization with fewer iterations and lower runtime.

No 3D affine extension is added solely to improve descriptive diagnostics. Proceed to Day 25 integrated Week 5 benchmarking and closure. Synthetic quantitative evidence and real RIRE descriptive evidence must remain clearly separated.
