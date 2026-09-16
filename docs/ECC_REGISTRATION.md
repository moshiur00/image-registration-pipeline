# ECC Registration

## Purpose

Week 3 Day 3 introduced Enhanced Correlation Coefficient registration for 2D monomodal translation and rigid motion. Week 3 Day 4 extends the same implementation to affine motion and multiresolution refinement.

Unlike phase correlation, which directly estimates translation in the frequency domain, ECC is an iterative intensity-based optimizer. It starts from an initial transform, repeatedly warps the moving image, measures the ECC objective against the fixed image, and updates the transform parameters.

## Supported motion models

The current implementation supports:

- translation;
- rigid motion using OpenCV Euclidean motion, which contains rotation and translation;
- general affine motion using OpenCV affine ECC.

Multiresolution affine behavior is documented separately in `docs/MULTIRESOLUTION_ECC.md`.

## Transform convention

The project stores every registration transform as:

```text
Moving -> Fixed
```

OpenCV `findTransformECC` returns the warp in the convention normally used with `WARP_INVERSE_MAP`. The implementation treats that returned matrix as Fixed -> Moving and explicitly inverts it before returning a project result.

This conversion is tested with known synthetic transforms so the common project convention remains unchanged.

## Initialization

Two Day 3 initialization modes are supported:

```text
identity
phase_correlation
```

Identity initialization starts ECC with no displacement.

Phase-correlation initialization first estimates a coarse Moving -> Fixed translation and converts it into the OpenCV ECC initialization convention. ECC then refines the transform.

The two modes are evaluated on the same cases so initialization sensitivity can be measured rather than assumed.

## Configurable optimizer settings

The YAML configuration exposes:

- maximum iteration limit;
- termination epsilon;
- Gaussian filter size;
- interpolation mode;
- optional minimum ECC threshold;
- phase-correlation settings used for coarse initialization.

OpenCV's Python ECC interface reports the final ECC value but does not expose the actual number of iterations performed. The project therefore records the configured iteration limit and termination tolerance together with the final objective value and runtime.

## Ground-truth evaluation

Week 2 provides exact transforms and deterministic control points. Day 3 compares the estimated transform against this known reference using:

- mean target registration error in pixels;
- centered translation-parameter error in pixels;
- rotation error in degrees for rigid cases;
- NCC before and after registration;
- final ECC value;
- optimizer success or failure;
- total runtime.

The current Day 3 validation thresholds are:

```text
Mean TRE <= 1.0 pixel
Translation parameter error <= 1.5 pixels
Rigid rotation error <= 1.0 degree
```

These thresholds are development validation criteria for this controlled benchmark. The final benchmark success policy will be formalized in Week 6.

## Day 3 experiment design

The configuration contains 12 base cases. Every case is run twice, once from identity and once from phase-correlation initialization, for 24 registrations total.

The cases include:

- identity translation;
- small, medium, and large translation;
- translation with contrast change;
- translation with illumination gradient;
- small, medium, and larger rigid transforms;
- one deliberately challenging rigid initialization case;
- rigid motion with contrast change;
- rigid motion with illumination gradient.

The source image is resized to 256 x 256 for this development experiment so iterative ECC validation remains fast while preserving enough image structure for meaningful registration.

## Failure handling

ECC errors are returned as normal `RegistrationResult` objects rather than uncaught exceptions.

Possible failure states include:

```text
invalid_input
ecc_optimization_failed
ecc_runtime_failure
ecc_below_threshold
```

A failed optimizer result still remains in the result table and contributes to the observed success rate.

## Reference development result

The development validation run produced 24 registrations:

```text
Optimizer successes: 23/24
Within tolerance:    23/24
```

All translation cases passed with both initializations. Five of six rigid cases passed from identity initialization. All six rigid cases passed with phase-correlation initialization.

The intentionally difficult rigid case used:

```text
rotation = +20 degrees
translation = (+50, -35) pixels
```

Identity initialization failed to converge. Phase-correlation initialization allowed ECC to converge with approximately 0.339 pixel mean TRE in the development environment.

This is a useful controlled example of ECC initialization sensitivity. It should not be generalized to all images or transform ranges.

## Outputs

Full run artifacts are stored under:

```text
outputs/week03_day03_ecc_translation_rigid/
```

They include:

- `ecc_results.csv`;
- `ecc_results.json`;
- `summary.json`;
- `resolved_config.yaml`;
- TRE and runtime comparison plots;
- NCC before-versus-after plot;
- representative alignment figures for challenging, contrast, and illumination cases.

A compact report snapshot is also stored at:

```text
reports/week03_day03_ecc_translation_rigid.json
```

Unlike `outputs/`, the `reports/` directory is included in Git and lightweight project archives so later report generation retains key quantitative results.
