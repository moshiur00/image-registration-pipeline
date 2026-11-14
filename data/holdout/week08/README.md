# Private Week 8 Holdout Attachment Contract

This directory is a local attachment point for Phase 6 enrollment. Its contents
are not part of the public repository or the Phase 5 release candidate.

- Keep source pixels, labels, manifests received from a custodian, archives,
  and format sidecars private and untracked.
- Do not add an exception to `.gitignore` for any enrollment artifact.
- Before decoding any source or label, the custodian/provenance reviewer must
  complete the Phase 6 metadata-only source ledger, enrollment manifest, and
  source-registration attestation defined by `docs/WEEK08_HOLDOUT_PROTOCOL.md`.
- Hash raw bytes without visual screening. For compound formats, register and
  hash every component before decoding.
- The developer must not inspect real Week 8 pixels or labels before strict G7
  final readiness passes.
- Final preparation and evaluation may use only paths and hashes registered in
  the signed Phase 6 metadata. Any mismatch aborts the evaluation cycle.

This README is intentionally the only tracked file beneath this directory.
