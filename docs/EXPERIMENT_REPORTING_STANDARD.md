# Experiment Reporting Standard

Use this structure for every experiment from Day 16 onward so final report preparation does not depend on memory or terminal history.

## Required machine-readable fields

Each experimental run should preserve, when applicable:

- experiment and case identifier;
- source image or dataset identifier;
- configuration and random seed;
- ground-truth transform or reference status;
- estimated transform;
- primary geometric metrics;
- method-specific diagnostics;
- runtime;
- success status;
- within-threshold status;
- explicit failure reason;
- paths to generated figures and tables.

## Required narrative record

Each daily summary should include:

1. Purpose
2. Setup
3. Variable changed
4. Factors kept fixed
5. Metrics and thresholds
6. Results
7. Observations
8. Interpretation
9. Failure cases
10. Limitations
11. Decision or next experiment

## Interpretation rules

- A successful optimizer call is not automatically a geometrically correct registration.
- Similarity metrics are descriptive unless the experiment establishes a geometric reference.
- Keep failed runs in aggregate results.
- State when a result is specific to one image, condition, threshold, or machine.
- Compare methods directly only on common cases and compatible motion models.
- Do not convert a controlled observation into a universal method claim.

## Storage layers

```text
outputs/   complete local run evidence
reports/   compact tracked quantitative snapshots
docs/      narrative findings, interpretation, and limitations
```

The compact findings registry for completed work is `reports/findings_days_01_15.json`.
