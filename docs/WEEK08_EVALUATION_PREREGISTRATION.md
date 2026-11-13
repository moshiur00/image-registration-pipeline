# Week 8 Evaluation Preregistration and Firewall Contract

**Status:** Phase 3 implementation complete; G3 passed on 13 November 2026.
This document and `configs/week08_final_evaluation.yaml` define the evaluation
contract.  G3 does not authorize source enrollment, a real holdout run, or a
final evidence claim.

**Authority:** `docs/PRE_WEEK08_INTEGRATION_PLAN.md` remains the maintained
project plan.  If this document conflicts with it, the maintained plan wins.

## Scope and do-not-peek boundary

Phase 3 implements and rehearses the evaluator with the tracked `camera.png`
development asset only.  It must not download, preview, decode, derive
statistics from, or open pixels or labels belonging to a real Week 8 source.
The rehearsal is non-evidentiary and cannot satisfy source enrollment, final
readiness, final evaluation, or release gates.

The two `phase3_allows_real_week08_*` switches are permanent attestations
about Phase 3 scope.  They remain false after later gates pass; final execution
is authorized by the separate G3-G7 gate contract, not by changing the Phase 3
history.

The preregistration freezes the evaluator design before any final source is
opened:

- source roles and claim limits;
- the synthetic known-ground-truth case matrix and deterministic seeds;
- compatible frozen methods and the unchanged exploratory policy;
- geometric endpoints, tolerances, strata, uncertainty, and denominators;
- decision-before-label ordering, artifact hashes, resume rules, and aborts;
- criteria for retaining or rejecting the policy candidate.

The exact enrolled source IDs and count are necessarily supplied later by the
independently reviewed Phase 6 metadata overlay.  The plan hashes those exact
IDs and counts before `prepare` decodes a source.  Once any enrolled pixel or
label is opened, the source set may not be increased, reduced, or replaced.

## Source roles and permitted claims

| Evaluation subset | Ledger/GT contract | Permitted use |
|---|---|---|
| Independent known GT | `full_project_independent` plus post-freeze synthetic GT, verified landmarks, or verified masks | Primary software benchmark and geometric metrics |
| Independent real verified GT | `full_project_independent` plus verified landmarks or masks | Preferred real-data geometric validation; required for full plan conformance unless a deviation is approved |
| Policy transfer check | `policy_transfer_check`, previously used, with valid GT | Secondary transfer evidence reported separately; never full-project independence |
| Real technical only | `real_technical_only` plus `unavailable` GT | Execution, physical-space, runtime, and diagnostic observations only |

At least one genuinely new source identity with valid GT is required for the
software gate.  A single source does not establish cross-source, modality,
population, anatomical, clinical, or external validity.  This benchmark alone
cannot establish those broader claims.  The config requires at least three
distinct independent identities, including real verified-GT evidence, before
even a limited cross-source-support statement can be considered.

Synthetic transforms created from a previously used image do not change that
image's provenance role.  In particular, the development rehearsal never
reclassifies `camera.png` as independent.

## Frozen case and method matrix

For each enrolled `full_project_independent` source whose GT type is
`synthetic_created_after_freeze`, the final plan expands the following matrix:

- geometry seeds `81103`, `81117`, and `81131`;
- monomodal translation, rigid, similarity, and affine cases;
- simulated-multimodal rigid and affine cases, the only such model cells with
  a compatible frozen method;
- clean, moderate Gaussian noise, blur, illumination, occlusion, partial
  overlap, low texture, and repeated-pattern templates;
- one additional fixed histogram-remap template for simulated multimodal
  cases;
- every compatible method in
  `configs/week07_day01_frozen_methods.yaml`, including a planned record for an
  optional method even when its runtime validation fails.

That expansion is 150 pairs, 294 compatible method attempts, and 24
policy-eligible monomodal affine pairs per enrolled synthetic source.  The
counts are derived again by the runner and bound into the plan; a mismatch is
an abort, not a reason to alter the matrix.

The generated transforms use the frozen Moving -> Fixed convention and the
ranges in the YAML configuration.  Labels must pass the independent matrix
inverse and control-point round-trip checks before they can be sealed.
Appearance randomness is derived from the pair identity and condition domain,
not from mutable process state.

Verified real and technical-only pairs are enumerated by the later source
manifest.  Their exact pair list is plan-hashed before source decoding and
cannot change after planning.

### Enrollment-manifest contract

The Phase 6 overlay must use `week08_holdout_sources_v1`.  Its top-level
`release_id` must be nonempty, its `ledger_sha256` must match the current source
ledger, and its unique `source_ids` must exactly equal the enrolled Week 8
source IDs.  Duplicate source or pair IDs are invalid.

Every non-synthetic pair row supplies `pair_id`, `case_id`, `source_id`,
`fixed_source_id`, `moving_source_id`, `modality_class`, `transform_model`,
`dimensions`, and `ground_truth_type`.  Dimensions are exactly two;
fixed/moving IDs must reference enrolled ledger records; and the row's GT type
must equal the structured GT type in the ledger.  The manifest may not supply
or override policy eligibility.  Eligibility is derived from the frozen role,
GT, dimension, modality, model, candidate-count, and method-family rules.

A verified-landmark or verified-mask row additionally supplies a nonempty
`label_manifest_id` and a `label` descriptor.  The descriptor binds its type,
pixel units, Moving -> Fixed direction, and fixed/moving label paths and
SHA-256 values.  The type must match the ledger GT type.  A technical-only row
has GT type `unavailable` and must not carry a label descriptor.  All enrolled
source and label paths and hashes are validated as metadata before the first
decoder is called; a failure aborts with zero enrolled pixels decoded.

The durable evaluation plan binds the current ledger and enrollment-manifest
file hashes, exact IDs/counts, canonical provenance fields, and one-way hashes
of complete enrollment records.  It never persists raw source or label
locators.  Those locators exist only in the prepare process, so the plan and
the decision executor cannot reveal a sealed-label path.

The method catalog and policy are file-hash pinned.  Phase 3 may add orchestration
around them, but it must not change registration algorithms, method parameters,
the observable-field projection, or policy thresholds.

## Isolated execution phases

The workflow has three separately invocable phases:

1. **Prepare** validates the frozen plan, decodes enrolled sources, and creates
   observable fixed/moving inputs.  It writes GT to a physically separate
   sealed-label area.  The observable manifest contains no transforms,
   landmarks, masks, TRE, or geometric pass/fail values.  Before its first
   decode it must persist the exact strict-readiness receipt and evaluation
   plan, then verify the ledger, enrollment manifest, and every enrolled source
   and label file hash.  A crash therefore leaves durable evidence of the gate
   and source/count contract that authorized the access.
2. **Decide** can read only the config, plan, observable manifest and inputs,
   frozen method catalog, and frozen policy.  It executes every planned
   compatible attempt, projects the explicit observable allowlist, makes the
   frozen policy decision, preserves all outcomes, and seals the journals.
   It has no label path or label object in its input contract.
3. **Evaluate** verifies every plan, count, source, config, code, method,
   policy, observable, journal, decision, and seal hash before it opens a
   label.  Only after that verification succeeds does it write a label-access
   audit event and compute authorized GT metrics.

`plan` and dry-run modes are metadata-only.  Tests must fail them if they call
an image decoder, NumPy pixel loader, or label reader.

The final and development artifact paths are explicit under `artifact_paths`
in the config.  Observable inputs and sealed labels are not colocated.  The
decision area holds an append-only attempt-event journal, exactly one terminal
scientific record per planned attempt, policy decisions, and a decision seal.
For the final run, `outputs/week08_holdout` and `outputs/week08_final` must be
disjoint: they may not be equal or nested, and every declared final artifact
path must exactly match the path derived from those roots.  The holdout area
contains observable inputs, sealed labels, and the preparation receipt; the
final area contains the plan, strict-readiness receipt, decision artifacts,
and evaluation outputs.

## Identity, completeness, and resume

Every attempt ID has the form `w8-` plus the first 24 lowercase hexadecimal
characters of a canonical SHA-256 digest.  The digest binds the protocol and
evaluation role, source ID and source hash, case/condition/severity, geometry
seed, modality, model, method ID and family, method-config hash, and method
seed.  Duplicate IDs, collisions with Day 32 or Day 35 records, and collisions
within another Week 8 task abort the run.

The scientific terminal states are `completed`, `check`, `failed`, and
`validation_error`.  An infrastructure exception is first an append-only event,
not a scientific outcome.  It may be retried once, before decision sealing and
before all label access, only with an explicit resume request and an exact
code/config/plan/source/observable/method/policy/seed contract match.  All prior
events remain in the journal.  Any unresolved infrastructure event blocks the
decision seal.  Scientific terminal outcomes are never rerun.

Changing a source, config, code contract, plan, method, seed, policy, observable
input, or prior record requires a new evaluation cycle.  It is not a resume.

## Track A: frozen per-method benchmark

Track A preserves every planned compatible attempt, including CHECK, failure,
validation-error, and infrastructure events.  It reports runtime and observable
diagnostics and, only for valid-GT roles, geometric results.

| Quantity | Frozen denominator |
|---|---|
| Execution completion | Completed attempts / all planned compatible attempts |
| Geometric success rate | Successful attempts / all preregistered attempts with valid GT |
| Conditional accuracy | Successful attempts / geometrically evaluable completed attempts |
| Infrastructure incident rate | Attempts with at least one infrastructure event / all planned attempts |

Success rate and conditional accuracy are distinct.  A failure does not vanish
from the preregistered success-rate denominator merely because no TRE can be
calculated.  Pairwise method comparisons use only pairs on which both methods
were planned and geometrically evaluable, and always publish that common raw
denominator.  Technical-only records have all geometric fields set to null.

Synthetic-transform and verified-landmark cases use the preregistered 2-pixel
TRE endpoint.  Verified-mask cases use Dice with success defined as Dice >=
0.80 and a plausible transform.  Both masks must be binary and nonempty; the
fixed mask must match the fixed observable image shape and the moving mask must
match the moving image shape.  Empty/empty masks are invalid evidence rather
than a perfect Dice result.

Mandatory strata are modality, transform model, condition, severity, source
role, and source identity.  Low-count cells remain visible with raw counts and
are labeled descriptive.

## Track B: frozen policy evaluation

Policy eligibility is fixed before execution.  The final policy denominator is
the set of monomodal affine pairs from independent or separately reported
transfer sources that had at least three planned candidates from at least three
method families.  A candidate failure or CHECK does not remove its pair from
the denominator.  Technical-only data are excluded from policy correctness.

Every eligible pair ends in exactly one of `selected`, `abstained`, `invalid`,
or `missing_decision`.  Candidate failures and CHECK records remain available
even when the policy abstains.

| Quantity | Frozen denominator |
|---|---|
| Coverage | Selected pairs / all eligible pairs |
| Selective correctness | Correct selected pairs / selected pairs |
| Abstention rate | Abstained pairs / all eligible pairs |
| Invalid rate | Invalid pairs / all eligible pairs |
| Missing-decision rate | Missing decisions / all eligible pairs |

Coverage is not selective correctness.  Every rate carries its numerator and
denominator; a zero denominator produces `null`, never zero or one.

## Uncertainty and recommendation decision

Binomial rates use two-sided 95% Wilson score intervals with the frozen normal
quantile in the config.  Paired method success comparisons use exact McNemar
counts on the stated common denominator.  Intervals over many cases derived
from one source are not independent-source intervals and do not create external
validity.

The exploratory policy can receive only `limited_independent_support` when all
of the following are true on independent data: at least 20 selected pairs,
coverage of at least 0.10, selective correctness of at least 0.95, a 95% Wilson
lower bound of at least 0.80, no missing decisions, no firewall or integrity
incident, and no post-label change.  Failure preserves the evidence and leaves
the policy non-deployed.  Abstention is legitimate behavior but reduces
coverage.

No result may be presented as a calibrated probability, user-facing confidence
percentage, clinical recommendation, or population/anatomical claim.  Real
technical-only observations cannot validate a recommendation.

## Phase 3 development rehearsal

The tracked `camera.png` fixture and its known SHA-256 are declared under
`development_rehearsal`.  The tiny rehearsal uses seed `93103`, monomodal
translation and affine cases, and clean plus moderate-noise templates.  This
produces four pairs and 12 compatible method attempts; the two affine pairs
exercise the Track B code path under an explicit development-only eligibility
override.  The override never changes source provenance and is legal only while
`final_evidence` is false.

The rehearsal and tests must exercise:

- both Track A and Track B end to end;
- a policy abstention or invalid path;
- a technical-only record with no geometric metric;
- deterministic IDs and prior-ID rejection;
- early label-read failure and label-independence of decisions;
- source, config, policy, journal, and seal tamper blocking;
- exact terminal-record completeness and resume-contract enforcement;
- the distinct Track A and Track B denominators.

Those checks passed on development-only fixtures, the actual runner contract is
hash-bound into preflight, and the machine-readable result is recorded in
`reports/pre_week08_phase3_evaluator.json`.  No Phase 3 rehearsal result is a
Week 8 benchmark result.
