# Day 31 Summary: Robustness Framework and Experiment Design

## Objective

Prepare a reproducible, compatible, reference-safe Week 7 robustness benchmark and run a small resource pilot before attempting the full severity sweeps.

## Implementation

Day 31 adds a frozen 2D method configuration snapshot, an explicit severity grid, deterministic task enumeration using the frozen Week 6 benchmark runner, source-file split protection, an 11-attempt registration pilot, focused tests, and tracked design evidence.

The planned grid covers:

- Gaussian noise, blur, rotation, scale, illumination, occlusion, partial overlap, low texture, repeated pattern, and multimodal mapping.
- Four geometric model labels: translation, rigid, similarity and affine.
- Monomodal and simulated-multimodal categories, with three seeds.

Candidate methods are drawn from a tracked Week 7 snapshot of Week 6 settings. Newly exposed translation, rigid, and similarity variants use the same validated UI adapters and share consistent configuration families. They will not be retuned during severity sweeps without documenting a new version.

## Design coverage

- Candidate pair conditions enumerated: 708.
- Compatible development pairs: **522**.
- Explicitly unsupported model-modality pair conditions: **186**.
- Compatible method attempts: **1,026**, across ten candidate method variants.
- Planned full-grid attempts executed on Day 31: **zero**.
- Held-out source used for registration or calibration: **no**.
- Development source: `camera.png`; Week 8 held-out source: `moon.png`.

The 186 incompatible pair conditions are *not* counted as failed registrations. The full-grid task list is design evidence only and contains no simulated results.

## Local pilot evidence

Eleven small, compatible method attempts were planned for five geometrically controlled pairs:

- monomodal translation;
- monomodal rigid;
- monomodal similarity;
- monomodal affine;
- simulated-multimodal affine inversion.

The pilot uses the frozen RegistrationService with ground truth unavailable, then computes TRE only in a separate post-run evaluator when an estimated transform is present. The Week 6 runner resumes existing terminal records without rerunning them.

**Historical local-environment limitation:** The local runtime did not have SimpleITK. MI failures due to the missing dependency are preserved rather than suppressed; therefore the local pilot cannot establish a reliable full-grid serial runtime estimate. The target Windows pilot was subsequently executed successfully; see the authoritative verification below.

## Scientific safeguards

- Exact synthetic ground truth does not enter automatic candidate selection.
- Failure reasons and terminal statuses are preserved.
- One-factor severity levels and split rules are explicit in the YAML.
- Frozen method-configuration hashes and input hashes are part of the plan's provenance.
- No new ranking, confidence values, consensus thresholds or Streamlit features are introduced.

## Validation status

Day 31 passed the authoritative Windows regression: **444 backend tests and 149 UI tests**. The 11-attempt Windows pilot completed with zero missing dependencies, and all attempts were skipped on resume.

After the target tests and pilot evidence are reviewed, Day 32 may begin implementing and executing the controlled severity sweeps.

## Day 31 Windows test collection fix (2026-10-20)

The first Windows run reported 442 passing and two failing backend tests. Both
failures were `ModuleNotFoundError: No module named 'scripts'` from test-only
imports of the standalone Day 31 CLI. The repository's pytest configuration
intentionally adds only `src/` to Python's import path.

The tests now load the CLI by its explicit repository-relative file path using
`importlib.util`. This keeps the CLI as a standalone script, avoids changing
pytest configuration or the validated registration backend, and retains the
pilot compatibility and ground-truth firewall assertions. The Windows result
after applying this patch passed: 444 backend and 149 UI tests.

## Authoritative Windows verification (2026-10-20)

The corrected project passed **444/444 backend** and **149/149 UI** tests on
Windows. The target Day 31 pilot completed **11/11 compatible attempts** with
no missing dependencies; the resume check skipped all 11 without rerunning.
The full planned design remains 522 compatible development pairs and 1,026
registration attempts, not executed during Day 31. Earlier local SimpleITK
limitations and import errors are resolved in the Windows validation record.
**Day 31 is complete, Windows validated.**
