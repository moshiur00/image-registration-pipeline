# Day 14 Summary

## Week 3 Day 4: ECC Affine and Multiresolution Pyramids

**Status:** Implementation complete, target-machine validation pending

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

## Development reference result

The reference run completed 18 registrations:

```text
Single-resolution: 7/9 within tolerance
Multiresolution:    9/9 within tolerance
Overall:           16/18 within tolerance
```

The multiresolution procedure recovered two difficult cases where full-resolution ECC reached incorrect affine solutions.

Representative capture-range results:

```text
affine_capture_range
single-resolution TRE: 97.483 px
multiresolution TRE:     0.595 px

affine_strong_capture_range
single-resolution TRE: 82.202 px
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

Run the complete automated test suite and Day 4 experiment on the target Windows environment. After validation, Week 3 Day 5 will integrate phase correlation and ECC into a standardized monomodal baseline comparison.
