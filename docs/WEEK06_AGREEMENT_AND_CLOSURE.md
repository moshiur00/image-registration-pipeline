# Week 6 Day 30: Transform Agreement and Preliminary Consensus

## Purpose

Day 30 closes the Week 6 evaluation and automatic-execution foundation by adding a ground-truth-free comparison layer over the normalized candidate records produced on Day 29.

The goal is not to select a final best method. The goal is to answer a narrower operational question:

> When several compatible registration methods finish on the same unknown image pair, how strongly do their estimated transforms agree in image space?

Week 7 will supply the condition-specific robustness evidence needed to calibrate ranking, confidence, and abstention.

## Common transform-space comparison

Each eligible candidate already stores a Moving -> Fixed homogeneous transform. Day 30 samples a deterministic control grid inside the image and maps the same points through every eligible candidate transform.

For two transforms, the disagreement vector at control point `i` is the Euclidean distance between the two mapped point locations. The pairwise record stores:

- RMS disagreement in pixels,
- median disagreement in pixels,
- 95th percentile disagreement,
- maximum disagreement,
- RMS normalized by the image diagonal.

This comparison does not require ground truth.

## Eligibility

A candidate enters transform agreement only when:

- its execution state is `completed` or `check`,
- it returned an estimated transform,
- its transform was not explicitly classified as implausible.

Failed, validation-error, missing-transform, and explicitly implausible candidates remain visible but are excluded from the agreement calculation.

## Preliminary consensus anchor

When at least two candidates are eligible, the module computes a transform medoid.

For each candidate, it calculates the median pairwise RMS disagreement to the other eligible candidates. The candidate with the smallest median disagreement becomes the preliminary consensus anchor.

The anchor is only a descriptive geometric reference. It is not a best-method recommendation and is never exposed as one.

A single eligible candidate cannot establish cross-method agreement. Such a case is reported as `insufficient_candidates`.

## Robust operation summaries

Day 30 aggregates only common Week 6 evidence, separated by modality class and method:

- attempt count,
- completed, CHECK, failed, and validation-error counts,
- terminal execution success rate,
- plausible-transform rate among terminal candidates,
- median, unscaled MAD, and p95 for available common metrics,
- available stage runtime summaries.

Raw ECC objectives, RANSAC inlier values, and MI optimizer objectives remain method-specific diagnostics and are not aggregated as common scores.

## Small closure matrix

The development matrix contains four affine cases:

1. clean monomodal affine,
2. Gaussian-blurred monomodal affine,
3. Gaussian-noise monomodal affine,
4. intensity-inverted simulated-multimodal affine.

The candidate catalog remains the validated Day 29 configuration. Compatibility rules are not loosened for Day 30.

The simulated-multimodal case intentionally demonstrates an important limitation: if only one method is compatible, there is no cross-method consensus signal.

## Ground-truth firewall

Every automatic run uses `ReferenceEvidence()` with ground truth unavailable.

Therefore operation-time candidate evidence contains no TRE, parameter error, or geometric PASS/CHECK state.

The synthetic transform is retained only outside the automatic service for development validation after execution. These development-only values are never used to determine compatibility, consensus anchor, or operation-time candidate evidence.

## Week 6 closure boundary

Day 30 completes the infrastructure needed before robustness calibration:

- common evaluation semantics,
- independently tested metrics,
- resumable benchmark execution,
- normalized automatic candidate evidence,
- transform-space disagreement,
- preliminary consensus,
- robust common summaries.

It deliberately does not implement:

- a calibrated best-method ranking,
- a confidence score,
- learned pair characterization,
- calibrated consensus thresholds,
- automatic abstention,
- 3D RIRE consensus.

Those are later-stage tasks, primarily dependent on Week 7 robustness evidence.
