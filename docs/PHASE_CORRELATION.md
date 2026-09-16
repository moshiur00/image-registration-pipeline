# Phase Correlation for Translation Registration

## Purpose

Week 3 Day 1 introduces the first automatic registration method in the project. Phase correlation estimates a translation between a moving image and a fixed image using frequency-domain phase information.

The project convention remains:

```text
Moving -> Fixed
```

The estimator does not receive the synthetic ground-truth transform. Ground truth is used only after estimation to measure translation error.

## Core idea

For a translation-only relationship,

```text
g(x, y) = f(x - dx, y - dy)
```

the Fourier shift theorem states that the Fourier transforms differ by a phase term. If `F` and `G` are the image spectra, phase correlation forms a normalized cross-power spectrum. Its inverse Fourier transform contains a peak at the relative displacement.

The diagnostic implementation in this project uses the conceptual sequence:

```text
Fixed FFT
Moving FFT
    |
    v
Fixed FFT * conjugate(Moving FFT)
    |
Normalize magnitude
    |
    v
Inverse FFT
    |
    v
Correlation peak
    |
    v
Integer Moving -> Fixed shift
```

The production estimate uses OpenCV `phaseCorrelate`, which adds weighted-centroid subpixel refinement around the correlation peak.

## Direction convention

OpenCV reports the displacement from its first source to its second source. The project therefore calls it in this order:

```text
phaseCorrelate(moving, fixed)
```

This directly produces the project's stored Moving -> Fixed translation.

For example, if the expected registration transform is:

```text
tx = +5 pixels
ty = -3 pixels
```

then the estimated homogeneous transform is:

```text
[1  0  +5]
[0  1  -3]
[0  0   1]
```

## Hanning window

Finite image boundaries introduce abrupt edges. These edges add frequency components that can reduce the quality of the phase-correlation peak.

Week 3 Day 1 supports an optional Hanning window. The window smoothly attenuates the image near the borders before the Fourier-domain calculation.

The configuration uses:

```yaml
phase_correlation:
  use_hanning_window: true
```

Windowing is especially useful when synthetic translations create new image borders.

## Mean subtraction

The estimator can subtract the mean intensity before the Fourier calculation:

```yaml
phase_correlation:
  subtract_mean: true
```

This reduces the dominant zero-frequency component and keeps the estimate focused on spatial structure.

## Subpixel estimation

A discrete inverse FFT has an integer pixel grid, but OpenCV refines the detected peak using a local weighted centroid. This allows non-integer translation estimates.

Subpixel accuracy is affected by:

- interpolation used to create the moving image;
- image texture;
- boundary loss;
- noise and blur;
- windowing;
- overlap.

Week 3 Day 1 uses a configurable translation-error tolerance rather than requiring an exact floating-point match.

## Response value

OpenCV returns a phase-correlation response together with the estimated displacement. The project stores this response as a method diagnostic.

A larger response generally indicates a more concentrated correlation peak, but the response is not treated as a geometric accuracy metric. Translation error against known ground truth remains the main Day 1 validation criterion.

## Standard registration result

`PhaseCorrelationRegistration` returns the existing common `RegistrationResult` structure:

```text
transform
registered_image
success
runtime_seconds
convergence_info
failure_reason
```

The convergence information records:

```text
method
motion model
estimated tx
estimated ty
phase response
window setting
mean-subtraction setting
interpolation
response threshold
estimation time
warping time
```

## Failure handling

The module returns a failed registration record instead of propagating common input or OpenCV errors through the benchmark runner.

Handled conditions include:

- non-2D inputs;
- shape mismatch;
- empty arrays;
- non-finite values;
- insufficient intensity variation;
- non-finite phase-correlation output;
- optional response below a configured threshold.

When estimation itself cannot be performed, the result uses the identity transform and preserves the moving image as the fallback registered image.

## Day 1 validation

The Day 1 configuration evaluates 12 clean translation cases using the tracked `camera.png` source image. The set contains:

- identity;
- positive and negative translations;
- small, medium, and larger translations;
- two subpixel translations.

For every case the script records:

```text
true tx and ty
estimated tx and ty
Euclidean translation error
phase response
NCC before registration
NCC after registration
runtime
success flag
within-tolerance flag
failure reason
```

The estimator is considered correct for a Day 1 case when the Euclidean translation-vector error is within the configured tolerance.

## Diagnostic surface

The module also exposes `phase_correlation_surface`. This is a transparent NumPy FFT implementation of the normalized cross-power calculation. It is not used for the production subpixel estimate. It is included so the frequency-domain mechanism can be inspected directly.

The Day 1 script saves a centered correlation-surface figure for a representative case. The peak location relative to the center corresponds to the integer Moving -> Fixed displacement.

## Scope limitation

Phase correlation in Week 3 Day 1 is intentionally translation-only. Rotation, scale, and general affine changes are outside the motion model and should not be interpreted as failures of a translation-only method.

Week 3 Day 2 evaluates the translation estimator under controlled noise, blur, partial-overlap, translation-magnitude, subpixel, and windowing conditions. See `PHASE_CORRELATION_ROBUSTNESS.md` for the experiment design and reference observations. ECC registration is introduced after the phase-correlation robustness baseline.
