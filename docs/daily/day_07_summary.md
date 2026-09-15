# Day 7 Summary

## Week 2 Day 2: Controlled Degradations and Partial Overlap

### Objective

Extend the deterministic synthetic benchmark with controlled appearance changes, explicit transformed support, restricted field-of-view cases, and fixed-space overlap masks without changing the known ground-truth geometry.

### Completed work

- Added a reusable controlled-degradation module.
- Added deterministic Gaussian noise.
- Added deterministic salt-and-pepper impulse noise.
- Added Gaussian blur.
- Added contrast scaling around the image mean.
- Added gamma intensity mapping.
- Added configurable illumination gradients.
- Added deterministic rectangular occlusion with a visibility mask.
- Added transformed-support mask generation.
- Added configurable rectangular field-of-view masks.
- Added mask intersection utilities.
- Added restricted field-of-view application without changing image dimensions.
- Added valid-overlap mapping from moving coordinates to fixed coordinates.
- Added overlap-fraction calculation.
- Added a configuration-driven Day 2 demonstration and manifest output.
- Added tests for deterministic degradations, parameter validation, support masks, field-of-view masks, and overlap calculations.

### Demonstration configuration

The Day 2 demonstration uses one known rigid transformation and applies each degradation independently. This keeps geometry constant while appearance difficulty changes.

The configured rigid transform is:

```text
translation x: +10 px
translation y: -7 px
rotation: +5 degrees
```

The controlled cases are:

```text
Gaussian noise
Impulse noise
Gaussian blur
Contrast change
Gamma change
Illumination gradient
Rectangular occlusion
Restricted field of view
```

### Validation result

The demonstration produced a base geometric overlap of approximately `0.913` for the selected rigid transformation. The restricted field-of-view example reduced fixed-space overlap to approximately `0.533`.

The occlusion example retained the same geometric overlap while its moving-image visibility fraction was approximately `0.881`, showing that occlusion and partial overlap are represented separately.

### Automated tests

The project now contains 110 automated tests. Validation in the build environment produced:

```text
109 passed
1 skipped
```

The skipped test requires SimpleITK, which is not installed in that validation environment. The Day 2 degradation and overlap tests all passed.

### Next step

Week 2 Day 3 will add synthetic multimodal appearance mappings and easy, moderate, and hard benchmark difficulty tiers while preserving exact geometric ground truth.
