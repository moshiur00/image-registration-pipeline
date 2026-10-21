# Week 7 Day 34: Offline evidence calibration and abstention

**Status: completed and Windows validated on 2026-10-21.** This is development-only, exploratory evidence. The Week 8 holdout has **not** been accessed. Day 34 does **not** deploy a selector, report user-facing confidence, or change UI v0.2.

## Reproduction

From the repository root:

```powershell
pytest -v
pytest -c ui/pytest.ini ui/tests -v
python scripts/week07_day04_offline_calibration.py
```

Requires `outputs/week07_day02_full/` with the original Day 32 journal, plan, CSV and manifest; all are bundled in the Day 34 full project ZIP. The script does not rerun registration, mutate input evidence, train a predictive model or load the held-out `moon.png` pixels.

Outputs are written to `outputs/week07_day04_calibration/`:

- `calibration_report.json`: source checksum, selection rules, train and internal audit summaries, conditions and limitations
- `tentative_policy_not_for_ui.json`: explicitly non-deployed exploratory gate and provenance
- `threshold_sensitivity.csv`: complete coarse grid, including unsupported configurations
- `pair_decisions_offline.csv`: each pair's observable-based decision and **separate** offline outcome label
- `observable_signal_bins.csv`: diagnostic associations, not family-agnostic raw objective comparisons
- `condition_summary.csv`, `model_summary.csv`: selection and abstention by stress and motion model
- `plots/train_coverage_sensitivity.png`, `plots/train_selective_precision.png`, `plots/abstention_reasons.png`
- `day34_manifest.json`: input hashes and analysis provenance

## Scientific design and leakage firewall

- All 963 attempts from the 486 unique development pairs are read, with Failed and CHECK attempts preserved.
- The `project_observables` function strictly allowlists execution status, plausibility, estimated Moving -> Fixed transform, fixed image dimensions, estimated valid overlap and **method-specific observable diagnostics**. It **never** reads synthetic TRE, geometric PASS, known transform, offline reference overlap, degradation severity, or held-out pixels.
- `labels_by_pair` is a **different offline-only** path which evaluates the observable selection against Day 32's 2 px TRE plus plausibility result. There is no path from these labels into the observable gate.
- Estimates are compared by five-point displacement over the source image corners and center, measured in pixels. Only same-pair, same-transform-model transforms with matching dimensions are compared.
- Eligible methods must have `completed` status, plausible finite transform, estimated overlap above the exploratory floor and recorded family-specific diagnostics. `check`, `failed` and unavailable diagnostics do not contribute to agreement support.
- Feature methods require recorded inlier ratio and match coverage; ECC requires finite final ECC and a completed pyramid level; MI requires finite metric, nonzero valid metric points and a reported optimizer stop; Phase requires a reported response. **Different objectives are not ranked against one another numerically.**
- Three mutually agreeing candidates from **three distinct method families** must form a pairwise-consistent triangle. Two candidates, or three methods of the same family, cannot support a consensus claim. Method-family diversity is a conservative heuristic, not proof of independent statistical errors.
- A deterministic geometric medoid from the supporting triangle serves **only** as an evaluation proxy; no automatic recommendation is published.
- Pairs without enough compatible candidates, missing diagnostics, invalid overlap or mutually consistent cross-family agreement **abstain**, including single- and two-method pairs. An agreement among incorrect transforms can still lead to a wrong decision: guardrail tests demonstrate this explicitly.

## Development split and threshold sensitivity

For a reproducible **internal** seed partition, geometry seeds `7` and `42` (324 pairs) provide the threshold-selection sample. Geometry seed `101` (162 pairs) is an **internal audit** and is not consulted when picking a threshold. These are not independent real-world data or a Week 8 holdout: they share source-image content and severity templates. Correlation between cases makes naive binomial uncertainty intervals potentially optimistic.

A declared exploratory grid examines maximum cross-family five-point disagreement in `{0.5, 1, 2, 3, 5, 8} px` and estimated overlap floors `{0.35, 0.50, 0.65}`. The provisional candidate is the **narrowest** agreement threshold meeting predeclared training-only criteria: >=10% pair coverage, >=20 selected training pairs, >=95% empirical conditional precision, and Wilson 95% lower bound >=0.80. Ties prefer a higher overlap floor. If no candidate qualifies, the fallback abstains on all pairs. These rules are *exploratory decisions*, not empirically justified deployment guarantees.

On the current data, the selected **tentative** gate is 2.0 px, with 0.65 estimated-overlap floor and three-family consensus. All three evaluated overlap floors happen to yield **identical selection coverage** in this dataset. Thus the preference for 0.65 is a conservative tie-break, **not evidence that 0.65 is optimal or informative**.

| Metric | Tuning seeds 7 & 42 | Internal audit seed 101 |
|---|---:|---:|
| Unique development pairs | 324 | 162 |
| Tentatively supported | 33 | 18 |
| Abstained | 291 | 144 |
| Selection coverage | 10.19% | 11.11% |
| Correct among supported | 33/33 | 18/18 |
| Descriptive Wilson lower 95% bound | 0.896 | 0.824 |

**Important:** 51/51 successful *selected* cases is not 100% overall accuracy. Combined selection coverage is just 51/486 (10.49%), and the remaining 435 pairs abstain. The underlying Day 32 benchmark had 840/963 geometrically successful attempts. No calibrated confidence percentage or proof of real-world reliability follows from this narrow, correlated development evidence.

## Interpretation and handoff

This day answers whether available observable signals support a **conservative abstention policy candidate**, not which method is best. It maps feature inlier/coverage, ECC convergence, MI termination and estimated overlap against offline known synthetic error, with method-family-specific bins and missing-value counts.

The limited multi-family availability is structural: 177 pairs have one candidate, 225 pairs have two, and only 84 have four. In this benchmark, only the monomodal affine four-method cases offer three families. Any reliable policy supporting other models requires a different evaluation design or separate observable safeguards. This is a **research finding**, not a reason to fake two-method consensus.

Day 35 may freeze this tentative proposal **for Week 8 independent testing**, but must not treat it as already validated. Maintain the exact original Day 32 input hashes and leave Week 6 algorithms and UI v0.2 unchanged.

## Day 34 Windows closure

The user-run Windows checks passed: 530 backend tests, with 2 expected symbolic-link skips; all 149 UI tests. The Day 34 offline calibration completed from 963 frozen registration attempts. The exported 486 pair decisions reconcile to 33/324 tuning supports, 18/162 internal-seed audit supports, and 435/486 total abstentions. Three figures were verified and frozen input hashes matched archived Day 32 evidence.

**Support restriction:** 51 of 51 supported pairs are monomodal affine. The conservative gate abstains on all 177 simulated-multimodal pairs and every translation, rigid, and similarity pair in this development dataset. This is not production calibration, and the internal audit is not independent validation. Original generated output files including the `local_calibration_generated_review_pending` manifest are intentionally preserved as created; closure status is tracked separately in `reports/week07_day04_closure.json`. Day 35 remains unstarted.
