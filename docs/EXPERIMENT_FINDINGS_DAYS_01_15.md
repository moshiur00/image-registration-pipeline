# Experiment Findings and Observations, Days 1 to 15

This document preserves the main observations that are useful for later technical reporting. It is not a replacement for the daily summaries or raw outputs. Measured results remain in `reports/` and full generated evidence remains in local `outputs/`.

## Reporting rules

- Separate measured results from interpretation.
- Keep failed and borderline cases in the record.
- Treat current success thresholds as development criteria until the unified evaluation stage.
- Treat runtime as machine-dependent unless the same machine and configuration are used.
- Do not generalize a result beyond the tested image, condition, and configuration.

## Day 1: Project conventions and translation foundation

### Evidence

```json
{
  "smoke_test": {
    "moving_point": [
      100,
      100
    ],
    "translation": [
      30,
      20
    ],
    "expected_fixed_point": [
      130,
      120
    ]
  },
  "status": "complete"
}
```

### Observations

- The Moving -> Fixed transform convention and the (x, y) geometric coordinate convention were fixed before later registration code was added.
- Forward transformation and inverse recovery were verified numerically on known points.

### Interpretation

- The early convention work reduces ambiguity later when registration methods and image resampling use different transform directions internally.

### Limitations

- This day validates geometry conventions and utilities, not automatic registration accuracy.

### Source records

- `docs/daily/day_01_summary.md`
- `docs/TRANSFORM_CONVENTIONS.md`

## Day 2: Rotation and rigid transforms

### Evidence

```json
{
  "local_tests_passed": 19,
  "worked_example": {
    "angle_degrees": 90,
    "translation": [
      10,
      5
    ],
    "center": [
      100,
      100
    ],
    "moving_point": [
      120,
      100
    ],
    "expected_fixed_point": [
      110,
      85
    ]
  }
}
```

### Observations

- Positive rotation was defined explicitly for displayed image coordinates, where image y increases downward.
- Rigid-transform tests verified inverse recovery, orthogonality, determinant +1, centered rotation, and distance preservation.

### Interpretation

- Rotation-center handling must be explicit. A rotation matrix alone rotates around the coordinate origin.

### Limitations

- The validation is mathematical and synthetic. It does not evaluate registration estimation.

### Source records

- `docs/daily/day_02_summary.md`
- `docs/ROTATION_RIGID_TRANSFORMS.md`

## Day 3: Similarity, affine, warping, and interpolation

### Evidence

```json
{
  "supported_interpolation": [
    "nearest",
    "linear",
    "cubic"
  ],
  "mask_interpolation": "nearest only",
  "status": "complete"
}
```

### Observations

- The project separates geometric transform direction from resampling direction: the stored transform is Moving -> Fixed, while destination pixels use inverse source lookup.
- Nearest-neighbor interpolation is required for masks so resampling does not create invalid label values.

### Interpretation

- Transforming coordinates and resampling image intensities are separate operations and should be tested separately.
- Composing transforms before one resampling step avoids unnecessary repeated interpolation.

### Limitations

- No unknown transform is estimated on this day.

### Source records

- `docs/daily/day_03_summary.md`
- `docs/SIMILARITY_AFFINE_WARPING.md`

## Day 4: Image I/O, preprocessing, evaluation, and visualization

### Evidence

```json
{
  "metrics": [
    "MAE",
    "MSE",
    "NCC",
    "SSIM"
  ],
  "medical_metadata": [
    "spacing",
    "origin",
    "direction"
  ],
  "status": "complete"
}
```

### Observations

- Raster color ordering is normalized at the loading boundary so OpenCV BGR ordering does not leak into later modules.
- Medical image metadata is preserved instead of reconstructed later.
- Image-similarity metrics are recorded as descriptive measures and not treated as proof of geometric correctness.

### Interpretation

- The evaluation layer already distinguishes image appearance from geometric validity, which is important for later multimodal work.

### Limitations

- No geometric ground-truth metric is introduced at this stage.

### Source records

- `docs/daily/day_04_summary.md`
- `docs/IMAGE_IO_PREPROCESSING_EVALUATION.md`

## Day 5: Configuration-driven end-to-end smoke test

### Evidence

```json
{
  "local_tests_passed": 66,
  "metrics": {
    "MAE": {
      "before": 0.1556,
      "after": 0.0699
    },
    "NCC": {
      "before": 0.6057,
      "after": 0.9645
    },
    "SSIM": {
      "before": 0.5371,
      "after": 0.808
    }
  },
  "seed": 42
}
```

### Observations

- The known-transform smoke test improved MAE, NCC, and SSIM after registration.
- The same experiment configuration maps to a deterministic run identity and stores configuration, metrics, transform, timing, metadata, log, and figures.

### Interpretation

- The pipeline infrastructure is reproducible enough to support later automatic registration methods without changing the surrounding experiment structure.

### Limitations

- The transform is known in advance, so this is an integration test rather than an automatic registration benchmark.

### Source records

- `docs/daily/day_05_summary.md`
- `docs/weekly/week_01_summary.md`
- `reports/week01_summary.json`

## Day 6: Deterministic synthetic ground truth

### Evidence

```json
{
  "transform_families": [
    "translation",
    "rigid",
    "similarity",
    "affine"
  ],
  "repeat_hash_check": "identical",
  "day_build_validation": "82 passed, 1 skipped"
}
```

### Observations

- Synthetic pairs store both transform directions and exact point correspondences.
- Repeating the demonstration with the same seed and configuration produced identical generated file hashes.

### Interpretation

- Known geometry can be verified independently before it is used to judge a registration algorithm.

### Limitations

- The skipped test in the day-specific build environment was SimpleITK-dependent. Final Week 2 target validation later ran the complete suite.

### Source records

- `docs/daily/day_06_summary.md`
- `docs/SYNTHETIC_GROUND_TRUTH_BENCHMARK.md`

## Day 7: Controlled degradations, occlusion, and partial overlap

### Evidence

```json
{
  "configured_rigid_transform": {
    "tx_pixels": 10,
    "ty_pixels": -7,
    "rotation_degrees": 5
  },
  "base_geometric_overlap": 0.913,
  "restricted_fov_overlap": 0.533,
  "occlusion_visibility_fraction": 0.881
}
```

### Observations

- Occlusion reduced visible content while leaving geometric overlap unchanged.
- Restricted field of view reduced the actual fixed-space region with valid correspondence.

### Interpretation

- Occlusion and partial overlap must be stored as separate experimental factors because they create different registration failure conditions.

### Limitations

- The reported fractions come from one controlled demonstration and are not general thresholds.

### Source records

- `docs/daily/day_07_summary.md`
- `docs/CONTROLLED_DEGRADATIONS_PARTIAL_OVERLAP.md`

## Day 8: Simulated multimodal mappings and difficulty tiers

### Evidence

```json
{
  "seed": 42,
  "sampled_tiers": {
    "easy": {
      "tx": -3.62,
      "ty": -3.78,
      "rotation_degrees": 2.22,
      "scale": 0.973
    },
    "moderate": {
      "tx": -9.1,
      "ty": -7.46,
      "rotation_degrees": -6.69,
      "scale": 0.9415
    },
    "hard": {
      "tx": 15.32,
      "ty": -15.97,
      "rotation_degrees": 13.56,
      "scale": 1.1336
    }
  },
  "mappings": [
    "intensity inversion",
    "nonlinear gamma",
    "histogram remapping",
    "bias field",
    "edge emphasis",
    "modality-specific noise"
  ]
}
```

### Observations

- The multimodal simulations change the intensity relationship while preserving the exact stored geometry.
- Joint histograms can therefore be interpreted after known ground-truth alignment without mixing intensity change with geometric error.

### Interpretation

- Difficulty tiers provide controlled, non-overlapping parameter ranges for later stratified evaluation.

### Limitations

- Simulated multimodal appearance is a controlled stress test and does not replace validation on real multimodal pairs.

### Source records

- `docs/daily/day_08_summary.md`
- `docs/SIMULATED_MULTIMODAL_DIFFICULTY_TIERS.md`

## Day 9: Real-data manifests and integrity checks

### Evidence

```json
{
  "general_sources": [
    "camera",
    "coins",
    "moon"
  ],
  "real_multimodal_pair": {
    "dataset": "RIRE training_001",
    "fixed": "CT",
    "moving": "MR-T1",
    "format": "MHA"
  }
}
```

### Observations

- The general source images are tracked inputs for controlled transformations, not naturally paired registration cases.
- The real medical pair keeps physical metadata and file hashes and remains outside the lightweight repository archive.

### Interpretation

- Manifest and integrity checks make dataset provenance and metadata failures visible before registration experiments start.

### Limitations

- The real CT and MR-T1 pair is prepared for later multimodal registration and is not yet a completed multimodal registration result.

### Source records

- `docs/daily/day_09_summary.md`
- `docs/REAL_DATA_MANIFESTS_INTEGRITY.md`
- `docs/datasets/RIRE_MULTIMODAL.md`

## Day 10: Integrated controlled benchmark

### Evidence

```json
{
  "cases": 60,
  "difficulty": {
    "easy": 20,
    "moderate": 20,
    "hard": 20
  },
  "modality": {
    "monomodal": 30,
    "simulated_multimodal": 30
  },
  "restricted_fov_cases": 15,
  "transform_families": [
    "translation",
    "rigid",
    "similarity",
    "affine"
  ],
  "seed": 42,
  "dataset_fingerprint": "9d74385564129b5bb714b9fb0b088c46097efad1422b20fc09c67e056ed9cd81",
  "repeat_check": "MATCH",
  "final_local_tests_passed": 172
}
```

### Observations

- The full benchmark regenerated with the same fingerprint when the same seed and configuration were used.
- Geometry, appearance, modality simulation, and overlap are represented as separate recorded factors.

### Interpretation

- This benchmark provides a fixed experimental reference for later methods so algorithm changes can be compared on the same generated cases.

### Limitations

- Synthetic and simulated multimodal cases support controlled internal validity, while later real-data experiments are still needed for external validity.

### Source records

- `docs/daily/day_10_summary.md`
- `docs/weekly/week_02_summary.md`
- `reports/week02_summary.json`
- `docs/INTEGRATED_WEEK02_BENCHMARK.md`

## Day 11: Phase Correlation clean translation baseline

### Evidence

```json
{
  "cases": 12,
  "passed": 12,
  "tolerance_pixels": 0.5,
  "mean_error_pixels": 0.0544,
  "median_error_pixels": 0.0041,
  "max_error_pixels": 0.3098,
  "mean_phase_response": 0.9877,
  "local_tests_passed": 188
}
```

### Observations

- All clean translation cases passed the selected 0.5-pixel development tolerance.
- Integer translations were recovered with very small error, while the largest errors occurred on fractional-pixel shifts.

### Interpretation

- Phase Correlation provides a precise translation-only baseline for the current controlled data.
- The phase response is a diagnostic of the correlation peak and is not itself a geometric error metric.

### Limitations

- The conclusion is limited to translation and the tested images and configuration.

### Source records

- `docs/daily/day_11_summary.md`
- `reports/week03_day01_phase_correlation.json`
- `docs/PHASE_CORRELATION.md`

## Day 12: Phase Correlation robustness

### Evidence

```json
{
  "registrations": 43,
  "tolerance_pixels": 0.5,
  "sweeps": {
    "gaussian_noise": "6/6, max error 0.069 px",
    "gaussian_blur": "6/7, sigma 8.0 error 4.181 px",
    "partial_overlap": "6/7, about 0.26 percent overlap error 0.622 px",
    "translation_magnitude": "8/8, largest magnitude about 216.33 px",
    "subpixel": "7/7, max error 0.439 px",
    "windowing": "6/8, severe blur 72.160 px without window vs 4.204 px with window"
  },
  "local_tests_passed": 195
}
```

### Observations

- Strong Gaussian noise and the tested large translations did not cause tolerance failures in this controlled run.
- Severe blur and the most extreme low-overlap case produced failures.
- Hanning windowing reduced the severe-blur error substantially in the tested comparison, although the case still failed.

### Interpretation

- Phase Correlation robustness depends on the type of information loss, not only on a single confidence score.

### Limitations

- The observed failure points are specific to the tested source image, severity ranges, and threshold.

### Source records

- `docs/daily/day_12_summary.md`
- `reports/week03_day02_phase_robustness.json`
- `docs/PHASE_CORRELATION_ROBUSTNESS.md`

## Day 13: ECC translation and rigid registration

### Evidence

```json
{
  "registrations": 24,
  "optimizer_successes": 23,
  "within_tolerance": 23,
  "local_tests_passed": 214,
  "groups": {
    "translation_identity": "6/6, median TRE 0.267 px",
    "translation_phase_init": "6/6, median TRE 0.274 px",
    "rigid_identity": "5/6, median TRE 0.255 px",
    "rigid_phase_init": "6/6, median TRE 0.255 px"
  },
  "challenging_rigid": {
    "true_rotation_degrees": 20,
    "true_translation": [
      50,
      -35
    ],
    "identity_tre_pixels": 65.721,
    "phase_init_tre_pixels": 0.339,
    "phase_init_rotation_error_degrees": 0.03,
    "phase_init_translation_error_pixels": 0.329,
    "phase_init_ecc": 0.9954
  }
}
```

### Observations

- The difficult rigid case failed from identity initialization and was recovered when Phase Correlation supplied a coarse translation initialization.
- Most non-challenging translation and rigid cases were accurate from either initialization.

### Interpretation

- ECC can be accurate once its optimizer starts inside a useful capture region. Initialization should therefore be treated as part of the registration configuration.

### Limitations

- The challenging case demonstrates initialization sensitivity for this case only. It does not establish Phase Correlation initialization as universally superior.

### Source records

- `docs/daily/day_13_summary.md`
- `reports/week03_day03_ecc_translation_rigid.json`
- `docs/ECC_REGISTRATION.md`

## Day 14: Affine ECC and multiresolution refinement

### Evidence

```json
{
  "registrations": 18,
  "optimizer_successes": 18,
  "within_tolerance": 16,
  "local_tests_passed": 232,
  "single_resolution": {
    "passed": 7,
    "cases": 9,
    "median_tre_pixels": 0.503,
    "mean_runtime_ms": 82.49
  },
  "multiresolution": {
    "passed": 9,
    "cases": 9,
    "median_tre_pixels": 0.503,
    "mean_runtime_ms": 41.9
  },
  "capture_range_examples": [
    {
      "single_tre_pixels": 86.562,
      "multi_tre_pixels": 0.595
    },
    {
      "single_tre_pixels": 81.584,
      "multi_tre_pixels": 0.552
    }
  ]
}
```

### Observations

- All optimizer calls returned a transform, but two single-resolution results were geometrically incorrect.
- The coarse-to-fine configuration recovered both difficult capture-range cases within the selected tolerance.

### Interpretation

- Optimizer completion must be stored separately from geometric success.
- The pyramid can increase capture range for difficult affine motion in the tested configuration.

### Limitations

- The Day 14 runtime comparison is specific to this experiment and machine and should not be generalized to all image sizes or configurations.

### Source records

- `docs/daily/day_14_summary.md`
- `reports/week03_day04_ecc_affine_multiresolution.json`
- `docs/MULTIRESOLUTION_ECC.md`

## Day 15: Integrated monomodal baseline benchmark

### Evidence

```json
{
  "base_cases": 14,
  "registrations": 24,
  "optimizer_successes": 23,
  "within_tolerance": 21,
  "local_tests_passed": 242,
  "methods": {
    "phase_correlation": {
      "passed": "6/6",
      "median_tre_pixels": 0.034,
      "mean_runtime_ms": 2.83
    },
    "ecc_translation": {
      "passed": "4/6",
      "median_tre_pixels": 0.29,
      "mean_runtime_ms": 14.85
    },
    "ecc_rigid": {
      "passed": "4/4",
      "median_tre_pixels": 0.295,
      "mean_runtime_ms": 32.69
    },
    "ecc_affine_single": {
      "passed": "3/4",
      "median_tre_pixels": 0.734,
      "mean_runtime_ms": 71.16
    },
    "ecc_affine_multiresolution": {
      "passed": "4/4",
      "median_tre_pixels": 0.662,
      "mean_runtime_ms": 107.23
    }
  },
  "shared_translation_failures": {
    "blurred_moon": {
      "phase_tre_pixels": 0.093,
      "ecc_translation_tre_pixels": 1.336
    },
    "restricted_fov_moon": {
      "phase_tre_pixels": 0.041,
      "ecc_translation_tre_pixels": 26.627
    }
  }
}
```

### Observations

- Phase Correlation passed all six shared translation cases, while ECC Translation missed the selected tolerance on the blurred Moon and restricted-field-of-view Moon cases.
- The affine capture-range failure remained visible in the integrated benchmark instead of being removed from the summary.

### Interpretation

- Direct method comparisons should use common cases and compatible motion models. Different motion models should not be ranked as if they solve the same task.
- Keeping failures in the result table makes later robustness and failure analysis possible.

### Limitations

- The current thresholds are development criteria. A unified final success policy is planned later. Runtime values are target-machine measurements and remain configuration-dependent.

### Source records

- `docs/daily/day_15_summary.md`
- `reports/week03_day05_integrated_baselines.json`
- `docs/WEEK03_BASELINE_COMPARISON.md`
- `docs/weekly/week_03_summary.md`
