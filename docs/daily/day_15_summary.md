# Day 15 Summary

## Week 3 Day 5: Integrated monomodal baseline benchmark

**Status:** Complete and locally validated on the target Windows environment

### Objective

Combine the Week 3 phase-correlation and ECC implementations into one configuration-driven benchmark with standardized result fields, comparable translation experiments, representative figures, runtime measurements, and a compact report snapshot.

### Implemented

- Added `configs/week03_day05_integrated_baselines.yaml`.
- Added `scripts/week03_day05_integrated_baselines.py`.
- Added `src/image_registration/week3_baseline.py` for Week 3 tolerance checks and grouped summaries.
- Extended visualization utilities with edge overlays.
- Added a standardized case-level CSV/JSON result table.
- Added an aggregated method table and method/condition/motion-model summaries.
- Added representative success and failure visualizations.
- Added automatic compact report snapshot generation.
- Added automated tests for Week 3 baseline tolerance logic, aggregation, and edge overlays.

### Benchmark design

The benchmark uses the tracked `camera`, `coins`, and `moon` source images at 256 x 256 resolution.

It contains:

```text
14 base cases
24 total registrations
```

Supported baselines:

```text
Phase correlation                 translation
ECC translation                  translation
ECC rigid                        rigid
ECC affine single resolution     affine
ECC affine multiresolution       affine
```

Phase correlation and ECC translation are evaluated on the same six translation cases. Rigid and affine methods are evaluated only on their supported motion models.

### Local validation result

The target Windows environment passed all 242 automated tests in the complete project. The integrated benchmark then reproduced the expected 24 registrations:

```text
Optimizer successes: 23/24
Within tolerance:    21/24

Phase correlation               6/6
ECC translation                 4/6
ECC rigid                       4/4
ECC affine single resolution    3/4
ECC affine multiresolution      4/4
```

Target-machine method summaries:

```text
Phase correlation:            median TRE 0.034 px, mean runtime   2.83 ms
ECC translation:              median TRE 0.290 px, mean runtime  14.85 ms
ECC rigid:                    median TRE 0.295 px, mean runtime  32.69 ms
ECC affine single resolution: median TRE 0.734 px, mean runtime  71.16 ms
ECC affine multiresolution:   median TRE 0.662 px, mean runtime 107.23 ms
```

The affine capture-range case preserved an important Week 3 failure example: single-resolution ECC returned a transform but failed geometrically, while multiresolution ECC recovered the case within tolerance.

The translation subset also preserved difficult cases rather than filtering them out. In the reference run, ECC translation failed the selected geometric tolerance on the blurred Moon case and the restricted-field-of-view Moon case, while phase correlation passed all six translation cases.

### Result preservation

Full outputs are local under:

```text
outputs/week03_day05_integrated_baselines/
```

The compact tracked result snapshot is:

```text
reports/week03_day05_integrated_baselines.json
```

### Validation status

Target Windows validation is complete. The complete automated test suite passed 242 / 242, and the integrated benchmark completed with 23 / 24 optimizer successes and 21 / 24 registrations within the selected development tolerances. Week 3 is therefore complete and locally validated.
