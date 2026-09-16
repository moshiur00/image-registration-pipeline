# Day 15 Summary

## Week 3 Day 5: Integrated monomodal baseline benchmark

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

### Reference development result

```text
Optimizer successes: 23/24
Within tolerance:    21/24

phase_correlation               6/6
ECC translation                 4/6
ECC rigid                       4/4
ECC affine single resolution    3/4
ECC affine multiresolution      4/4
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

Implementation and reference development validation are complete. Target Windows validation remains pending. The target sequence is:

```powershell
pytest -v
python scripts/week03_day05_integrated_baselines.py --config configs/week03_day05_integrated_baselines.yaml
```
