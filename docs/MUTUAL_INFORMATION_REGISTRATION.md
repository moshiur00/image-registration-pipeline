# Mutual Information Registration

## Current status

Week 5 Day 21 implementation is complete and target Windows validation is pending.

## Purpose

Mutual Information is the primary multimodal registration objective in Week 5. The first implementation stage uses SimpleITK Mattes Mutual Information with a 2D rigid transform so the transform direction, optimizer behavior, sampling, multiresolution settings, and geometric evaluation can be validated before affine and real medical-image experiments are added.

## Transform direction

The project convention remains:

`Moving -> Fixed`

SimpleITK registration evaluates a transform that maps fixed-domain physical points into the moving-image domain for resampling. The implementation therefore converts the final SimpleITK transform to a homogeneous physical matrix and inverts it before returning the project transform.

This distinction is explicit in the stored convergence information. Optimizer completion must not be interpreted as geometric correctness.

## Day 21 implementation

`src/image_registration/mutual_information.py` provides:

- 2D rigid registration with `Euler2DTransform`;
- Mattes Mutual Information;
- full, regular, or random metric sampling;
- fixed random seed support for sampled metrics;
- identity, geometry-based, or moments-based initialization;
- Regular Step Gradient Descent;
- optimizer scaling from physical shift;
- coarse-to-fine shrink factors and smoothing sigmas;
- iteration-level metric tracing;
- optimizer stop condition and valid metric-point diagnostics;
- preservation of SimpleITK spacing, origin, and direction in the `register_sitk` path;
- standard project `RegistrationResult` output;
- safe runtime failure records.

## Controlled Day 21 experiment

The initial experiment uses one monomodal reference and five simulated multimodal rigid cases. The multimodal mappings include intensity inversion, nonlinear gamma, histogram remapping, multiplicative bias, and an edge-emphasized representation.

The experiment records:

- method execution success;
- TRE against exact synthetic ground truth;
- rotation error;
- centered translation error;
- final Mattes MI value;
- optimizer iterations and stop condition;
- valid metric points;
- metric trace;
- runtime;
- explicit failure reason;
- comparison figures.

The initial development thresholds are stored in `configs/week05_day01_mi_rigid.yaml`. They are not final benchmark thresholds and should not be changed simply to convert failed cases into passes.

## Scope boundary

Day 21 does not yet claim performance on RIRE CT/MR-T1 data. It validates the initial 2D rigid MI path using controlled geometry. Real medical-image physical-space registration, affine MI, initialization comparisons, histogram-bin studies, sampling studies, and stochastic-repeat analysis remain Week 5 tasks.

## Target validation command

```powershell
pytest -v
python scripts/week05_day01_mi_rigid.py --config configs/week05_day01_mi_rigid.yaml --overwrite
```

The resulting numerical evidence should be recorded before expanding the method.
