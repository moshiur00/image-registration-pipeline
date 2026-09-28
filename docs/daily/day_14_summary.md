# Day 14 Summary

## Week 3 Day 4: ECC Affine and Multiresolution Pyramids

**Status:** Complete and locally validated on the target Windows environment

## Objective

Extend ECC to general affine motion and implement a coarse-to-fine image pyramid that transfers the estimated Moving -> Fixed transform correctly between resolution levels.

## Implemented

- affine ECC through OpenCV `MOTION_AFFINE`;
- supplied-transform initialization for ECC refinement;
- reusable image-pyramid utilities;
- configurable pyramid scales and pre-smoothing;
- homogeneous transform conversion between pyramid coordinate systems;
- `MultiResolutionECCRegistration` using the common result interface;
- per-level ECC diagnostics and runtime information;
- affine linear-component error;
- single-resolution versus multiresolution comparison;
- full CSV and JSON output plus a compact tracked report snapshot;
- representative registration figures and a pyramid-level visualization;
- automated tests for affine ECC, pyramid construction, transform rescaling, and affine metrics.

## Experiment design

The Day 4 configuration uses nine affine cases. Every case is registered twice:

```text
single-resolution ECC
multiresolution ECC with scales 0.25, 0.5, 1.0
```

Both strategies use phase-correlation initialization so the experiment isolates the effect of coarse-to-fine refinement.

The configured affine cases cover identity, small and moderate transforms, anisotropic scaling, shear, larger changes, and deliberately difficult capture-range conditions.

## Local validation result

The target Windows environment passed all 232 automated tests present at this stage. The locally executed affine experiment completed all 18 optimizer calls:

```text
Optimizer successes: 18/18
Within tolerance:    16/18

Single-resolution:   7/9
Median TRE:           0.503 px
Mean runtime:        82.49 ms

Multiresolution:     9/9
Median TRE:           0.503 px
Mean runtime:        41.90 ms
```

The multiresolution procedure recovered two difficult cases where full-resolution ECC reached incorrect affine solutions.

Representative target-machine capture-range results:

```text
affine_capture_range
single-resolution TRE: 86.562 px
multiresolution TRE:     0.595 px

affine_strong_capture_range
single-resolution TRE: 81.584 px
multiresolution TRE:     0.552 px
```

The development run also recorded all optimizer outcomes, including geometrically incorrect solutions. Optimizer convergence alone is therefore not treated as proof of registration correctness.

## Result preservation

Full Day 4 evidence is written to:

```text
outputs/week03_day04_ecc_affine_multiresolution/
```

The tracked compact snapshot is:

```text
reports/week03_day04_ecc_affine_multiresolution.json
```

This preserves the quantitative result for future report generation even though large generated outputs remain outside Git.

## Next step

The next stage after this validation was the integrated monomodal baseline comparison combining Phase Correlation and ECC. That stage has since been completed and locally validated.
