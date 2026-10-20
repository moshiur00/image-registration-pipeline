# Week 6 Automatic Multi-Method Execution Foundation

## Purpose

Day 29 introduces the first framework-neutral automatic registration orchestration layer. The goal is not to choose a winner. The goal is to take one image-pair profile, determine which configured methods are compatible, execute every compatible candidate, and express the resulting evidence through the common Week 6 contract.

## Scientific boundary

The automatic layer deliberately separates three kinds of information:

1. **Compatibility evidence**
   - dimensionality
   - requested transform model
   - modality class
   - same-shape requirements
   - optional-method policy

2. **Common evidence**
   - Day 26 metric definitions only
   - transform plausibility
   - execution status
   - common runtime values
   - valid overlap
   - ground-truth metrics only when reference evidence is actually available

3. **Method-specific diagnostics**
   - ECC objective values
   - Phase Correlation response
   - RANSAC inlier information
   - MI optimizer traces
   - other family-specific diagnostics

Raw optimizer objectives are not promoted into a shared score and are not compared across method families.

## Main contracts

`AutoPairProfile`
: Describes what is known before candidate execution.

`AutoMethodSpec`
: Describes one callable candidate configuration and its compatibility boundaries.

`CandidateCompatibility`
: Retains an auditable include/exclude decision and explicit reasons.

`AutoCandidateTask`
: Stable pair-plus-method execution identity.

`NormalizedCandidateEvidence`
: Stores common evidence separately from opaque method-specific diagnostics.

`AutomaticRunResult`
: Stores every compatible candidate plus the full compatibility audit. No selected method is produced on Day 29.

`AutomaticMultiMethodService`
: Filters compatibility, executes all compatible candidates, catches executor/integration failures, preserves CHECK/FAILED candidates, and normalizes valid results.

## Failure policy

A candidate is never silently removed because it fails.

- algorithm/integration exceptions become `failed`
- contract or identity mismatches become `validation_error`
- plausible but concerning results may remain `check`
- completed candidates remain `completed`

All terminal states stay in the automatic run result.

## Ground-truth policy

The Day 29 development script deliberately runs the automatic service as if ground truth were unavailable. Therefore the operation-time candidate records contain no TRE, parameter error, or geometric PASS/CHECK state.

The synthetic development pair does have exact ground truth, but it is used only after automatic execution as a validation probe. It is never supplied to the automatic service and cannot influence compatibility or execution.

## Recommendation policy

Day 29 does not rank methods and does not return a best candidate.

The run result explicitly reports:

`deferred_until_robustness_calibration`

Transform-space agreement and preliminary consensus are Day 30 work. Evidence-backed ranking, confidence calibration, alternatives, and abstention require Week 7 robustness evidence.
