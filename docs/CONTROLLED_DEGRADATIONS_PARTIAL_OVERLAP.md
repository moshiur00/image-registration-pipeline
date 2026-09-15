# Controlled Degradations and Partial Overlap

## Purpose

Week 2 Day 2 extends the synthetic ground-truth generator with controlled appearance changes and explicit overlap masks. Geometry and appearance are kept separate so later registration experiments can vary one factor at a time.

The fixed/moving geometric relationship is still defined by the exact Moving -> Fixed ground-truth transform created on Week 2 Day 1. Day 2 modifies only the appearance or visible field of view of the moving image.

## Implemented degradation types

The `image_registration.degradations` module provides deterministic operations when a fixed random seed is used:

- Gaussian noise
- Salt-and-pepper impulse noise
- Gaussian blur
- Contrast scaling
- Gamma mapping
- Horizontal, vertical, or diagonal illumination gradients
- Rectangular occlusion

Each configuration-driven degradation returns the degraded image, the parameters used, and a visibility mask. The visibility mask is all ones for degradations that preserve visible content and marks the hidden rectangle for an occlusion.

## Geometry remains unchanged

Appearance degradation must not alter the stored ground-truth transform. The same exact transformation is valid before and after adding noise, blur, contrast, gamma, illumination changes, or occlusion.

This separation allows later experiments to answer questions such as:

- How does phase correlation respond to increasing noise?
- At what blur level does feature matching become unreliable?
- How sensitive is ECC to illumination or contrast changes?
- How much partial overlap can a method tolerate before failing?

## Valid geometric support

A transformed image can contain invalid border regions because some destination pixels map outside the source image. The benchmark records this geometric support explicitly.

For synthetic pair generation:

```text
Fixed support
    |
    | Fixed -> Moving
    v
Valid moving support
```

The valid moving support can then be mapped back into fixed coordinates using the exact Moving -> Fixed transform. This creates a valid-overlap mask for fair evaluation in the fixed coordinate system.

## Restricted field of view

Partial overlap is created with a configurable rectangular field-of-view mask in moving-image coordinates.

```text
Moving support
      +
Restricted field of view
      |
      v
Moving valid mask
      |
      | Moving -> Fixed
      v
Valid overlap in fixed space
```

The field-of-view operation changes visible content but does not resize the image or change its geometric coordinate system.

## Overlap fraction

The overlap fraction is defined as:

```text
overlap fraction = valid overlap pixels / total fixed-image pixels
```

The Week 2 Day 2 demonstration records both the normal geometric overlap and the reduced overlap after applying the restricted field of view.

## Occlusion versus partial overlap

Occlusion and partial overlap are stored separately.

- Occlusion hides content inside the moving image but does not change the geometric field of view.
- Partial overlap restricts the valid moving field of view and therefore changes the valid geometric overlap with the fixed image.

This distinction is useful because later experiments may evaluate robustness to occlusion differently from robustness to limited overlap.

## Reproducibility

Random degradations use explicit NumPy random generators. The demonstration derives deterministic per-case random generators from the experiment seed so repeated runs with the same configuration reproduce the same noisy pixels and occlusion location.

## Day 2 demonstration

Run:

```powershell
python scripts/week02_day02_degradations_overlap_demo.py --config configs/week02_day02_degradations_overlap.yaml
```

The demonstration creates controlled one-factor examples for each degradation plus one restricted-field-of-view case. It writes image outputs, masks, metadata, the exact ground-truth transform, and a manifest under `outputs/week02_day02_degradations_overlap/`.
