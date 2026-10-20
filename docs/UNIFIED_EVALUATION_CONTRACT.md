# Unified Evaluation Contract

## Purpose

Week 6 begins by freezing one method-independent evaluation vocabulary before adding more metrics or automatic multi-method orchestration. Every registration family must eventually be representable using the same execution, transform, evaluation, timing, and provenance concepts.

The contract does not change any Week 1 to Week 5 registration algorithm or frozen configuration.

## Universal conventions

- Transform direction: `Moving -> Fixed`.
- Point coordinate order: `(x, y)` for 2D transforms and `(x, y, z)` for 3D physical-space transforms.
- Optimizer completion is not geometric correctness.
- Method-specific objectives are diagnostics, not directly comparable cross-method scores.
- Failed runs remain valid experiment records and must retain a failure reason.
- Ground-truth metrics are reported only when the required reference evidence exists.
- Descriptive image metrics are computed only inside valid overlap.

## Reference evidence levels

The evaluation layer tracks reference evidence explicitly:

- exact transform;
- corresponding landmarks;
- reference masks;
- physical spacing or physical-coordinate metadata;
- unavailable reference evidence.

These sources enable different claims. An exact transform enables model-aware parameter error. Exact transforms or verified landmarks enable TRE. Reference masks enable Dice. Physical-space metrics require physical spacing or equivalent metadata.

An arbitrary uploaded fixed/moving pair normally has none of these references. Such a pair can still report execution, transform plausibility, valid overlap, descriptive image metrics, runtime, and method-specific diagnostics. It cannot report TRE or a geometric PASS/CHECK label.

## Metric roles

### Geometric error

Examples include translation error, rotation error, scale error, affine linear-component error, and TRE. Lower is better, but these metrics are available only when the required reference exists.

### Anatomical overlap

Dice is reported only when a verified reference mask is available. It is not inferred from ordinary image intensities.

### Descriptive similarity

MAE, MSE, NCC, SSIM, and evaluation Mutual Information describe the relationship between the fixed image and registered image. They are supporting evidence only. They must not be interpreted as proof of true geometric or anatomical correctness.

### Valid overlap

Image similarity must be computed on a valid evaluation region. The valid-overlap mask is the intersection of all applicable validity masks, including transformed moving-image support and any fixed or moving field-of-view masks. An empty overlap is an evaluation error rather than a numeric score.

### Runtime

Week 6 separates preprocessing, registration, warping, evaluation, and total runtime. Runtime is an efficiency measurement, not an accuracy metric.

## Common candidate record

`UnifiedEvaluationRecord` stores the common evidence for one method on one pair:

- pair, method, method family, motion model, modality class, and seed;
- execution status and explicit failure reason;
- Moving -> Fixed estimated transform;
- transform plausibility;
- optional geometric within-tolerance state only when reference geometry exists;
- comparable metrics permitted by the evaluation context;
- stage-level timings;
- method-specific diagnostics kept separate from common metrics;
- warnings and reference-evidence status.

The record accepts 3 x 3 homogeneous transforms for 2D candidates and 4 x 4 homogeneous transforms for 3D physical-space candidates. It is designed as the foundation for the later benchmark runner and automatic multi-method comparison. It does not yet rank methods.

## Day 26 boundary

Day 26 freezes semantics, units, availability rules, and the common result structure. Day 27 will implement and independently validate the metric calculations themselves. Later Week 6 work will add resumable benchmarking and multi-method orchestration on top of this contract.
