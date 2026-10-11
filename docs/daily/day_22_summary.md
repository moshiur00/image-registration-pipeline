# Day 22 Summary: Rigid MI Initialization, Sampling, and Parameter Study

## Status

Complete on the target Windows environment.

Target validation:

- Python 3.12.6 on win32
- pytest 9.1.1
- 347 / 347 tests passed in 8.65 s
- 5 validation cases
- baseline: 3 / 5 within tolerance
- sequential composite candidate: 5 / 5 within tolerance
- frozen confirmation: 5 / 5 within tolerance

Day 22 is validation evidence used to freeze the rigid Mutual Information configuration. It is not final benchmark evidence.

## Purpose

Select a rigid Mattes Mutual Information configuration on a limited simulated-multimodal validation subset before Day 23 affine MI and the later held-out Week 5 benchmark.

## Validation cases

The five validation cases are:

- intensity inversion;
- nonlinear gamma mapping;
- histogram remapping;
- multiplicative bias field;
- edge-emphasized representation.

The histogram-remap and edge-emphasized cases preserve the difficult conditions observed on Day 21.

## Experimental design

The study is sequential one-factor-at-a-time rather than an unrestricted grid search. Each stage changes one factor while retaining the previously selected values.

The selection priority is:

1. higher geometric within-tolerance count;
2. higher method-success count;
3. lower median TRE;
4. lower maximum TRE;
5. lower mean runtime.

Random-seed repetitions are diagnostic only. A seed is never selected because it gives the best accuracy.

## Results

### Baseline

The Day 21 configuration produced 3 / 5 validation cases within tolerance, with median TRE 0.0284 px.

### Initialization

- identity: 3 / 5 within tolerance, median TRE 0.0272 px
- geometry: 3 / 5, median TRE 0.0278 px
- moments: 1 / 5, median TRE 21.8575 px

Identity initialization was selected for the sequential study.

### Histogram bins

- 32 bins: 3 / 5, median TRE 0.0264 px
- 50 bins: 3 / 5, median TRE 0.0278 px
- 64 bins: 1 / 5, median TRE 21.6749 px

Thirty-two bins were selected under the predefined ranking rule. This does not imply that 32 bins are universally optimal.

### Sampling strategy

- full sampling: 5 / 5, median TRE 0.0247 px, maximum TRE 0.5702 px
- regular sampling: 3 / 5, median TRE 0.0145 px
- random sampling: 3 / 5, median TRE 0.0264 px

Full sampling was selected because all five validation cases were geometrically correct. Because the frozen strategy is full sampling, sampling percentage is not applicable to the frozen configuration.

### Sampling-percentage diagnostic

The percentage sweep used random sampling only as a diagnostic:

- 10 percent: 2 / 5 within tolerance
- 20 percent: 3 / 5
- 50 percent: 4 / 5

These values were not used to override the selected full-sampling strategy.

### Preprocessing

All five preprocessing candidates reached 5 / 5 within tolerance after full sampling had been selected.

- none: median TRE 0.0247 px, maximum TRE 0.5703 px
- robust clipping: median TRE 0.0224 px, maximum TRE 0.3985 px
- robust normalization: median TRE 0.0225 px, maximum TRE 0.3889 px
- z-score normalization: median TRE 0.0205 px, maximum TRE 0.5586 px
- Gaussian smoothing, sigma 1.0: median TRE 0.0173 px, maximum TRE 0.0950 px

Gaussian smoothing with sigma 1.0 was selected.

### Random-sampling variability

Random sampling at 20 percent was repeated with seeds 7, 42, 101, 202, and 909 after the selected preprocessing stage. All five cases were within tolerance for all five seeds.

The edge-emphasized moon case showed the largest stochastic spread, with TRE ranging from approximately 0.0738 px to 0.5066 px. This confirms that random sampling can introduce meaningful variability even when all attempts remain inside the configured tolerance.

The seed study is diagnostic only. The frozen full-sampling configuration does not depend on a favorable random seed.

### Sequential composite candidate

The combined sequential candidate achieved:

- 5 / 5 within tolerance
- median TRE 0.0192 px
- maximum TRE 0.0950 px

It ranked above the Day 21 baseline on the validation subset.

### Frozen-candidate confirmation

A separate confirmation run of the selected configuration achieved:

- 5 / 5 method successes
- 5 / 5 within tolerance
- median TRE 0.0173 px
- maximum TRE 0.0950 px
- mean runtime 1060.84 ms

The frozen rigid MI configuration is therefore accepted for later Week 5 work.

## Frozen rigid MI configuration

The selected configuration is:

- initialization: identity
- histogram bins: 32
- sampling strategy: full
- preprocessing: Gaussian smoothing with sigma 1.0
- optimizer: RegularStepGradientDescent
- learning rate: 2.0
- minimum step: 0.001
- iterations: 200
- relaxation factor: 0.5
- gradient magnitude tolerance: 0.0001
- multiresolution shrink factors: 4, 2, 1
- smoothing sigmas: 2.0, 1.0, 0.0
- transform convention: Moving -> Fixed

The stored `sampling_percentage` and `sampling_seed` fields remain part of the common configuration schema but are not active when the sampling strategy is full.

## Evidence preserved

Tracked quantitative evidence is stored in:

- `reports/week05_day02_mi_rigid_study.json`

The local detailed evidence produced by the run includes:

- all run records;
- CSV results;
- the frozen rigid MI candidate;
- metric traces;
- before/after joint histograms;
- confirmation visualizations.

Detailed local evidence remains under `outputs/` and is intentionally excluded from the shared project ZIP.

## Interpretation

The main Day 22 result is not simply a lower median TRE. The important change is that full sampling recovered both difficult validation conditions and moved the validation subset from 3 / 5 to 5 / 5 within tolerance.

Gaussian smoothing then reduced the remaining worst-case error on this subset.

The result also shows that optimizer execution must remain separate from geometric correctness. Several inferior settings completed successfully while producing large TRE.

## Limitations

- The configuration was selected on five simulated multimodal validation cases.
- The study is sequential one-factor-at-a-time and does not exhaustively test parameter interactions.
- The selected settings are not final test evidence.
- Synthetic multimodal mappings do not replace real multimodal validation.
- Joint histograms and MI objective values do not prove anatomical correctness.
- Real RIRE CT/MR-T1 physical-space validation remains reserved for Day 24.

## Decision

Day 22 is complete.

The rigid MI configuration is frozen for subsequent Week 5 experiments. Day 23 may now begin with affine Mutual Information and multiresolution capture-range validation.
