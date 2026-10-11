# Image Registration Pipeline

A research-focused Python framework for studying classical image registration under controlled monomodal and multimodal conditions. The project combines reproducible experiment design, known-ground-truth synthetic benchmarks, real medical-image handling, quantitative evaluation, and explicit failure analysis.

The central question is not which registration method is universally best. It is **which method is reliable under which geometric and appearance conditions, and why it fails when those conditions change**.

## Project at a glance

| Area | Scope |
|---|---|
| Registration methods | Phase Correlation, ECC, ORB + RANSAC, optional SIFT + RANSAC, Mattes Mutual Information |
| Motion models | Translation, rigid, similarity, affine |
| Data | Controlled synthetic pairs, visible-image samples, simulated multimodal pairs, RIRE CT/MR-T1 |
| Evaluation | TRE, transform-parameter error, overlap-aware similarity, runtime, success/failure status, diagnostic evidence |
| Reproducibility | YAML configurations, fixed seeds, structured reports, deterministic dataset fingerprints, automated tests |
| Current status | Weeks 1 to 5 complete, Week 6 next |
| Target validation | 364 / 364 tests passed on Windows for the completed Week 5 repository |

## Research objectives

This project is designed to answer practical registration questions with controlled evidence:

- How do intensity-based, frequency-domain, feature-based, and multimodal methods behave under different motion models?
- How sensitive are optimization-based methods to initialization, image pyramids, sampling, and preprocessing?
- When do feature methods fail because of low texture, repeated structure, poor correspondence geometry, or model mismatch?
- How do partial overlap, blur, illumination changes, intensity remapping, and simulated modality differences affect registration?
- How should optimizer completion, transform plausibility, and geometric correctness be separated in evaluation?
- How can synthetic ground truth and real medical-image validation be combined without overstating conclusions?

## Registration methods

| Method | Supported role | Current status |
|---|---|---|
| Phase Correlation | Translation estimation in monomodal data | Complete |
| ECC | Translation, rigid, and affine intensity registration | Complete |
| ORB + RANSAC | Similarity and affine feature registration | Complete, core feature baseline |
| SIFT + RANSAC | Controlled alternative feature front-end | Complete, retained as optional complement |
| Mattes Mutual Information | Rigid and affine multimodal registration | Complete for Week 5 |
| 3D Mattes Mutual Information | Rigid physical-space CT/MR registration | Complete technical validation on RIRE pair |

## Selected validated results

The values below are taken from tracked experiment reports and target-machine validation. They are intentionally condition-specific rather than combined into a universal ranking.

| Experiment | Result |
|---|---|
| Clean Phase Correlation translation | 12 / 12 within tolerance, mean translation error 0.0544 px |
| Affine ECC capture-range study | Multiresolution 9 / 9 within tolerance versus single-resolution 7 / 9 |
| Week 4 integrated feature benchmark | 30 / 32 method executions succeeded, 26 / 32 within development tolerance |
| Frozen ORB vs SIFT comparison | ORB 10 / 12 within tolerance, SIFT 11 / 12 |
| ORB vs SIFT runtime | ORB mean 18.98 ms, SIFT mean 55.57 ms on the target Windows run |
| Week 5 final multimodal benchmark | Mutual Information 11 / 13 within tolerance, ECC 7 / 13 |
| Week 5 paired outcomes | 7 both-pass, 4 MI-only pass, 0 ECC-only pass, 2 both-CHECK |
| Real RIRE CT/MR-T1 | 2 / 2 rigid MI variants passed technical validation with metadata preserved |
| Final Week 5 test suite | 364 / 364 passed in 4.56 s on Windows |

The RIRE result is reported as **technical physical-space validation only**. Verified landmarks or masks are not integrated, so the project does not claim TRE, Dice, or anatomical correctness for that real CT/MR pair.

## Key findings so far

### Frequency-domain and intensity registration

Phase Correlation is highly accurate on clean translation cases and remains robust across a useful range of noise, blur, subpixel shifts, and translation magnitude. Severe blur and very low overlap expose clear limits. Windowing can reduce error under stress but does not guarantee a correct estimate.

ECC works well when the motion model and initialization are appropriate, but optimizer completion is not treated as proof of correct geometry. A difficult rigid case demonstrated strong initialization sensitivity, and coarse-to-fine affine optimization improved recovery on controlled cases with larger capture-range demands.

### Feature-based registration

ORB + RANSAC provides a fast and effective feature baseline on textured images. The project keeps descriptor filtering, RANSAC execution, transform plausibility, and final geometric correctness as separate states.

Low texture and repeated patterns fail for different reasons. Low texture can prevent enough reliable correspondences from being formed, while repeated structure can produce apparently plausible local matches that do not support the correct global transform.

The frozen ORB vs SIFT study retained SIFT as an **optional complement**. SIFT recovered one additional difficult case and reduced median TRE on the controlled comparison subset, but required substantially higher runtime. ORB therefore remains the core feature baseline.

### Multimodal registration

The Week 5 final benchmark showed a clear condition-specific advantage for Mutual Information under several multimodal intensity transformations. MI reached 11 of 13 final synthetic cases within tolerance compared with 7 of 13 for ECC.

Intensity inversion produced one of the clearest differences: MI passed the rigid and affine inversion cases while ECC did not return valid estimates. MI also recovered the affine bias-field and partial-overlap inversion cases where ECC did not meet the final criteria.

Edge-emphasized appearance remained difficult for both methods. These failures are retained in the reports rather than removed from the analysis.

## Experimental design

The project follows a controlled evaluation philosophy:

1. Use known geometric ground truth whenever possible.
2. Keep the stored transform convention fixed as **Moving -> Fixed**.
3. Compare methods only on shared cases with compatible motion models.
4. Separate method execution success from geometric correctness.
5. Preserve failed and CHECK cases in aggregate reporting.
6. Freeze validated configurations before final-test evaluation.
7. Keep simulated multimodal evidence separate from real medical-image evidence.
8. Avoid conclusions that are not supported by landmarks, masks, or known transforms.

Core evaluation signals include:

- Target Registration Error (TRE)
- translation, rotation, scale, and affine parameter error
- RANSAC inlier count and reprojection residuals
- transform plausibility checks
- NCC, SSIM, and Mutual Information where meaningful
- overlap-aware evaluation
- runtime and stage-level timing
- optimizer convergence diagnostics
- explicit success, CHECK, and failure reasons

## Pipeline architecture

```text
Input data and metadata
        |
        v
Preprocessing and modality handling
        |
        v
Initialization
        |
        v
Registration method
        |
        v
Moving -> Fixed transform
        |
        v
Warping / resampling
        |
        v
Ground-truth and diagnostic evaluation
        |
        v
Structured results, figures, reports, and findings
```

The framework uses common interfaces so that different registration methods can be evaluated with the same conventions and reporting structure.

## Core conventions

- Fixed image: reference or target image.
- Moving image: source image that must be aligned to the fixed image.
- Stored transform direction: **Moving -> Fixed**.
- Geometric coordinates: `(x, y) = (column, row)`.
- NumPy indexing: `image[y, x]`.
- Homogeneous points: column-vector form `[x, y, 1]^T`.
- Positive rotation: counterclockwise on the displayed image.
- Rotation angles: degrees.
- Mask interpolation: nearest neighbor only.
- SimpleITK physical metadata: spacing, origin, and direction are preserved.

Image resampling uses inverse source lookup internally while the project-level transform remains Moving -> Fixed.

## Reproducibility and evidence model

The project separates detailed experiment artifacts from compact tracked evidence:

```text
outputs/   local detailed experiment evidence
reports/   tracked quantitative summaries and findings
docs/      methodology, interpretation, limitations, and progress summaries
```

Each experiment is designed to preserve its purpose, setup, changed variables, fixed factors, thresholds, numerical results, observations, interpretation, failure cases, limitations, and next decision.

The project also uses:

- configuration-driven experiments with YAML
- fixed random seeds where applicable
- dataset hashes and deterministic fingerprints
- structured JSON and CSV result records
- target-machine validation
- automated tests for transforms, metrics, registration methods, data handling, and reporting

Operational setup, dataset preparation, experiment commands, cleanup, and archive creation are documented separately in [docs/REPRODUCTION_GUIDE.md](docs/REPRODUCTION_GUIDE.md). This keeps the main README focused on the research contribution and evidence.

## Repository structure

```text
image-registration-pipeline/
├── configs/                    experiment configurations
├── data/
│   ├── manifests/              dataset metadata and provenance
│   └── samples/                small tracked sample images
├── docs/
│   ├── daily/                  daily experiment summaries
│   ├── weekly/                 weekly research summaries
│   └── datasets/               dataset preparation and provenance notes
├── reports/                    compact quantitative evidence and findings
├── scripts/                    experiment and maintenance entry points
├── src/image_registration/     reusable registration modules
├── tests/                      automated validation suite
├── pyproject.toml
├── README.md
└── requirements.txt
```

Large raw datasets and detailed experiment outputs are intentionally excluded from the lightweight repository archive.

## Documentation and evidence

The most useful entry points are:

- [Transform conventions](docs/TRANSFORM_CONVENTIONS.md)
- [Experiment reporting standard](docs/EXPERIMENT_REPORTING_STANDARD.md)
- [Configuration and run outputs](docs/CONFIGURATION_AND_RUN_OUTPUTS.md)
- [Week 3 baseline comparison](docs/WEEK03_BASELINE_COMPARISON.md)
- [Week 4 feature baseline comparison](docs/WEEK04_FEATURE_BASELINE_COMPARISON.md)
- [ORB vs SIFT comparison](docs/ORB_VS_SIFT_COMPARISON.md)
- [Mutual Information registration](docs/MUTUAL_INFORMATION_REGISTRATION.md)
- [Week 5 summary](docs/weekly/week_05_summary.md)
- [Reproduction guide](docs/REPRODUCTION_GUIDE.md)
- [Progress registry](reports/progress_registry.json)
- [Week 5 findings](reports/findings_week05.json)

## Project status and roadmap

| Week | Focus | Status |
|---|---|---|
| 1 | Registration foundations and pipeline skeleton | Complete |
| 2 | Controlled dataset and ground-truth benchmark | Complete |
| 3 | Phase Correlation and ECC baselines | Complete |
| 4 | ORB + RANSAC and optional SIFT comparison | Complete |
| 5 | Multimodal Mutual Information and RIRE validation | Complete |
| 6 | Unified evaluation and reproducible benchmarking | Next |
| 7 | Robustness, runtime analysis, and failure diagnosis | Planned |
| 8 | Final benchmark, analysis, documentation, and demonstration | Planned |

Week 6 will consolidate model-aware parameter errors, TRE, overlap-aware similarity metrics, runtime accounting, success policies, benchmark execution, and standardized aggregation across the completed registration methods.

## License

No open-source license has been selected yet. An appropriate license should be added before distributing the repository under open-source terms.
