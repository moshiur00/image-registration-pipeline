# Phase Correlation Robustness

## Purpose

Week 3 Day 2 evaluates the translation-only phase-correlation baseline under controlled changes in image quality and overlap. The experiment uses exact synthetic Moving -> Fixed ground truth from the Week 2 infrastructure, so every estimated translation can be compared numerically with the known translation.

The main question is no longer only whether phase correlation works on a clean pair. The goal is to measure how accuracy and the phase-response diagnostic change as the input becomes more difficult.

## Experiment design

The tracked `camera.png` image is used as the fixed image. A moving image is generated with a known translation, then one factor is changed at a time.

The default acceptance rule is:

```text
translation-vector error <= 0.5 pixels
```

The experiment records:

- true Moving -> Fixed translation;
- estimated translation;
- Euclidean translation-vector error;
- phase-correlation response;
- valid geometric overlap fraction;
- NCC before and after registration;
- runtime;
- Hanning-window setting;
- success status and failure reason.

## Controlled sweeps

### Gaussian noise

The base pair is evaluated with increasing Gaussian-noise severity. The random generator is reset to the same seed for each severity, so the same standardized noise realization is scaled rather than changing the random pattern at every level.

This isolates the effect of noise magnitude more cleanly.

### Gaussian blur

The moving image is progressively blurred while geometry remains unchanged. This tests loss of high-frequency information, which is particularly relevant to a frequency-domain registration method.

### Partial overlap

A centered rectangular field of view is applied to the moving image. The valid moving support is combined with the field-of-view mask and mapped into fixed-image coordinates.

The script records the actual geometric overlap fraction instead of assuming that the configured field-of-view fraction is equal to final overlap.

The phase-correlation method itself is not given the overlap mask. The mask is used only to characterize the experiment.

### Translation magnitude

Known translations of increasing magnitude are evaluated. This tests how increasing boundary loss and decreasing natural overlap affect the estimate and response.

### Subpixel translation

Integer and fractional translations are compared. This exposes the difference between nearly exact integer-shift recovery and the larger error that can occur during subpixel peak refinement and interpolation.

### Hanning window comparison

Windowing is tested both on and off for selected conditions:

- clean input;
- severe blur;
- severe Gaussian noise;
- limited overlap.

The goal is not to assume that windowing always improves the result. The experiment records both outcomes so its effect can be interpreted from evidence.

## Reference validation observations

A reference run with seed 42 produced 43 registrations across all sweeps.

Key observations from that run were:

- Gaussian-noise sweep: 6 of 6 cases remained within 0.5 pixels, while phase response decreased strongly at high noise levels.
- Gaussian-blur sweep: 6 of 7 cases passed; sigma 8.0 exceeded the selected tolerance.
- Partial-overlap sweep: 6 of 7 cases passed; the most extreme case had about 0.26 percent valid overlap and exceeded tolerance.
- Translation-magnitude sweep: 8 of 8 cases passed, while phase response decreased as natural overlap fell.
- Subpixel sweep: 7 of 7 cases passed, but half-pixel cases showed noticeably larger error than integer cases.
- Windowing comparison: Hanning windowing greatly reduced the severe-blur error in the reference run, but severe blur still remained outside tolerance. The comparison is retained as a measured result rather than a universal rule.

These observations describe this controlled image and configuration only. They are not treated as general performance claims.

## Outputs

The Day 2 script writes:

```text
outputs/week03_day02_phase_robustness/
├── phase_robustness_results.csv
├── phase_robustness_results.json
├── summary.json
├── resolved_config.yaml
├── plots/
│   ├── translation_error_vs_noise.png
│   ├── phase_response_vs_noise.png
│   ├── translation_error_vs_blur.png
│   ├── phase_response_vs_blur.png
│   ├── translation_error_vs_overlap.png
│   ├── phase_response_vs_overlap.png
│   ├── translation_error_vs_magnitude.png
│   ├── subpixel_error.png
│   └── windowing_comparison.png
└── representative_cases/
    ├── severe_gaussian_noise/
    ├── severe_gaussian_blur/
    └── extreme_partial_overlap/
```

The representative folders contain fixed, moving, registered, overlay, checkerboard, and absolute-difference images. The extreme partial-overlap case also stores the moving valid mask and fixed-space valid-overlap mask.

## Interpretation for later weeks

Day 2 establishes a measured robustness baseline for translation-only phase correlation. These records will later be compared with ECC and ORB-based methods under conditions that each method is intended to support.

A lower phase response often accompanies more difficult inputs in this controlled experiment, but response is retained as a diagnostic rather than treated as an independent proof of geometric correctness.
