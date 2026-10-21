# Day 34: Offline evidence calibration

**Status: COMPLETE AND WINDOWS VALIDATED (2026-10-21).** Day 34 closed; the tentative policy is not deployed or independently validated.

- Built strict observable-only projection and independent offline synthetic-geometric labels in `src/image_registration/week7_calibration.py`.
- Added conservative three-family geometric agreement gate, deterministic tie breaking, diagnostics/overlap checks and **abstention** for single/two candidates or unsupported agreement.
- Added the read-only reproducible CLI `scripts/week07_day04_offline_calibration.py`, 23 focused tests, and the full experimental-methodology document `docs/WEEK07_DAY34_OFFLINE_CALIBRATION.md`.
- Analyzed 963 Day 32 attempts across 486 pairs without rerunning registration, accessing Week 8 data, or modifying original evidence hashes.
- Seeds 7 and 42 tune a provisional 2 px agreement threshold from 324 development pairs. Seed 101 serves as internal synthetic audit only. Provisional training: 33/324 supported and 33/33 geometrically correct; internal audit: 18/162 supported and 18/18 geometrically correct. Overall 435/486 pairs abstain. These are **not** calibrated confidence probabilities or final accuracy estimates.
- Method-specific signal-bin tables inspect feature correspondence evidence, ECC convergence, MI optimizer diagnostics and estimated overlap separately; they do not compare unlike raw algorithm objective scales.
- Windows validation: 530 backend tests passed and 2 symlink-related tests skipped, with 149 UI tests passed. The offline calibration command completed and the uploaded evidence ZIP was inspected: 486 unique pair decisions, 51 tentative supports, 435 abstentions, three valid figures, and four original Day 32 SHA-256 checksums matched.
- All 51 supported cases are **monomodal affine**. Translation, rigid, similarity and simulated multimodal development pairs have no support under this conservative rule. The 18/18 internal audit result must not be marketed as independent precision or calibrated confidence.
- Closure records: `reports/week07_day04_windows_validation.json` and `reports/week07_day04_closure.json`. Original generated outputs, including the run-time manifest, are preserved unchanged.
- Day 35 integrated validation is not started.

The provided archive includes frozen Day 32 and Day 33 evidence for reproducibility. UI v0.2 and registration algorithms are unchanged.
