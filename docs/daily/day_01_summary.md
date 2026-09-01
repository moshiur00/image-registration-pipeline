# Day 1 Summary

**Date:** 2026-08-31  
**Week:** 1 - Registration Foundations and Pipeline Skeleton  
**Status:** Complete

## Day 1 objective

Establish the technical foundation of the image-registration project before implementing registration algorithms. The priority was to remove ambiguity around fixed/moving images, transformation direction, coordinate order, and homogeneous-coordinate mathematics.

## Work completed

1. Created the reusable project directory structure for source code, tests, configurations, datasets, outputs, and documentation.
2. Added a pinned Week 1 Python environment and project packaging/test configuration.
3. Defined the project-wide image roles:
   - fixed = reference/target;
   - moving = source image to align;
   - registered = moving image resampled onto the fixed grid.
4. Defined the stored transformation direction as **Moving -> Fixed**.
5. Defined geometric coordinates as `(x, y) = (column, row)` while documenting that NumPy indexing is `image[y, x]`.
6. Implemented 2D homogeneous-coordinate utilities.
7. Implemented identity and translation matrices.
8. Implemented point transformation, transform inversion, and transform composition.
9. Added a configuration-driven Day 1 translation demonstration.
10. Added unit tests for conventions, identity, known translation, inverse recovery, composition, point batches, and invalid inputs.
11. Added a dedicated transformation-conventions document that future modules must follow.

## Numerical smoke test

Configured case:

```text
Moving point = (100, 100)
Translation  = (+30, +20)
```

Expected Moving -> Fixed result:

```text
Fixed point = (130, 120)
```

Applying the inverse transform must recover:

```text
Moving point = (100, 100)
```

The executable demonstration is:

```bash
python scripts/day01_demo.py --config configs/day01_translation_demo.yaml
```

## Files added on Day 1

```text
README.md
requirements.txt
pyproject.toml
.gitignore
configs/day01_translation_demo.yaml
docs/TRANSFORM_CONVENTIONS.md
docs/daily/day_01_summary.md
docs/weekly/week_01_summary.md
scripts/day01_demo.py
src/image_registration/__init__.py
src/image_registration/conventions.py
src/image_registration/transforms.py
tests/test_conventions.py
tests/test_transforms.py
```

## Key technical decision

The most important Day 1 decision is that registration algorithms will logically return a transform that maps **moving coordinates to fixed coordinates**. Later image warping/resampling may internally evaluate the inverse transform because destination pixels must sample the source image. Those two ideas must not be confused.

## Not implemented yet

Day 1 intentionally does not implement:

- image loading or medical metadata handling;
- image preprocessing;
- image resampling/warping;
- rigid, similarity, or affine matrix constructors;
- phase correlation;
- ECC;
- feature matching;
- mutual-information registration;
- final evaluation metrics.

These belong to subsequent work packages/days.

## Next work

Day 2 should extend the transform module to rigid transformation mathematics and begin the remaining Week 1 transformation utilities, while preserving all conventions and tests established today.
