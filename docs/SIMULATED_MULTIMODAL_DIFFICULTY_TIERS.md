# Simulated Multimodal Data and Difficulty Tiers

## Purpose

Week 2 Day 3 extends the synthetic benchmark from geometric and appearance degradations to controlled multimodal appearance changes. The geometric correspondence remains known exactly while the intensity relationship between the fixed and moving images is deliberately changed.

This separation is important because later multimodal registration methods should be evaluated on cases where corresponding structures can have different intensities even when the geometry is correct.

## Geometric ground truth remains unchanged

For every case, the stored transform still follows the project convention:

```text
Moving -> Fixed
```

The fixed image is transformed into a synthetic moving image using the inverse ground-truth transform. A modality mapping is then applied to the moving image without modifying its coordinates.

```text
Fixed image
    |
    | known Fixed -> Moving geometry
    v
Moving geometry
    |
    | appearance mapping only
    v
Simulated multimodal moving image
```

The same Moving -> Fixed transform therefore remains the exact geometric ground truth after the modality mapping.

## Implemented simulated modality mappings

### Intensity inversion

The observed intensity range is inverted. Bright structures become dark and dark structures become bright while spatial positions remain unchanged.

### Nonlinear gamma mapping

Normalized intensity is transformed with:

```text
y = x^gamma
```

Different gamma values create increasingly nonlinear intensity correspondence.

### Histogram remapping

A monotonic piecewise-linear mapping changes the intensity distribution using configured input and output knots. Geometry is unchanged, but the relationship between corresponding intensities becomes nonlinear.

### Smooth multiplicative bias field

A spatially varying Gaussian-shaped multiplicative field changes intensity according to image location. This creates a local bias without moving structures.

### Edge-emphasized representation

Sobel gradient magnitude is combined with the original normalized image. Higher blend values move the appearance toward an edge representation while retaining the same geometric structures.

### Modality-specific noise

Each simulated multimodal case can receive signal-dependent Gaussian noise. Noise is deterministic for a fixed seed and becomes stronger across the configured difficulty tiers.

## Difficulty tiers

Day 3 introduces three benchmark difficulty levels:

```text
Easy
Moderate
Hard
```

The tiers use non-overlapping severity ranges. The current configuration increases:

- absolute translation magnitude;
- absolute rotation magnitude;
- isotropic scale deviation from 1.0;
- base modality-noise level;
- signal-dependent modality-noise level.

The mapping-specific parameters also become stronger from easy to hard where a natural severity ordering exists. Examples include gamma value, bias-field strength, and edge-emphasis blend.

The tiers do not currently define partial-overlap severity. Partial overlap is represented independently by the Day 2 overlap utilities and will be combined into the final Week 2 benchmark later.

## Histograms and joint histograms

For each tier, the demonstration saves a monomodal histogram and joint histogram after applying the known ground-truth registration.

For every multimodal mapping it also saves:

```text
intensity_histogram.png
joint_histogram.png
```

The histogram compares the fixed and ground-truth-registered multimodal intensity distributions within valid geometric overlap.

The joint histogram shows the relationship between corresponding fixed and multimodal intensities after geometry is already aligned. This makes it possible to inspect intensity correspondence independently from registration error.

For example, intensity inversion produces a descending relationship in the joint histogram rather than the near-diagonal relationship expected for a monomodal pair.

## Output structure

The Day 3 demonstration creates:

```text
outputs/week02_day03_multimodal_difficulty/
├── fixed.png
├── manifest.json
├── resolved_config.yaml
├── easy/
├── moderate/
└── hard/
```

Each tier contains:

```text
moving_geometry.png
registered_monomodal.png
valid_overlap_fixed.png
monomodal_histogram.png
monomodal_joint_histogram.png
tier_metadata.json
```

Each simulated multimodal case contains:

```text
moving_multimodal.png
ground_truth_registered_multimodal.png
intensity_histogram.png
joint_histogram.png
metadata.json
```

## Reproducibility

Difficulty sampling, geometric transforms, and modality-specific noise use deterministic NumPy random generators derived from the experiment seed. Repeating the same configuration with the same seed should reproduce the same images, mappings, transform parameters, metadata, and histogram figures.

## Scope of Day 3

Day 3 creates controlled synthetic multimodal examples and difficulty tiers. It does not claim that these appearance mappings reproduce the full physical image-formation process of CT, MRI, PET, or infrared imaging. They are controlled tests for breaking simple intensity correspondence while preserving exact geometry.

Real multimodal data is scheduled for Week 2 Day 4 so synthetic observations can later be compared with real cross-modality pairs.
