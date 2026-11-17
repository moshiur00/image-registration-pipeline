#!/usr/bin/env python3
"""Validate the zero-access R3 confirmatory-cycle scaffold."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping


BASELINE_COMMIT = "68e2ecf1cd7c3e1172dea1d8bfd93127d2a1cd16"
CYCLE_ID = "week08-r3-confirmatory-20261116"
FINDING_PATH = "reports/week08_phase9_scientific_review_finding.json"
R2_SOURCE_SHA256 = "872e1a5317ac31612a766ef6dfa7e774e2d10509b1e564b38e3aa384d6b0bf19"


class R3ScaffoldError(ValueError):
    """Raised when the R3 boundary is incomplete or internally inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise R3ScaffoldError(message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo_root.as_posix()}",
            "show",
            f"{commit}:{path}",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def validate_scaffold(repo_root: Path) -> dict[str, Any]:
    record_path = repo_root / "reports/week08_r3_cycle_start.json"
    ledger_path = repo_root / "configs/week08_r3_source_use_ledger.json"
    manifest_path = repo_root / "data/manifests/week08_r3_holdout_sources.json"
    protocol_path = repo_root / "docs/WEEK08_R3_CONFIRMATORY_CYCLE.md"
    intake_readme = repo_root / "data/holdout/week08_r3/README.md"

    record = load_json(record_path)
    ledger = load_json(ledger_path)
    manifest = load_json(manifest_path)

    recorded_hash = record.get("record_payload_sha256")
    unhashed = dict(record)
    unhashed.pop("record_payload_sha256", None)
    require(recorded_hash == canonical_sha256(unhashed), "R3 cycle record self-hash mismatch")
    require(record.get("cycle_id") == CYCLE_ID, "R3 cycle id mismatch")
    require(record.get("baseline", {}).get("git_commit") == BASELINE_COMMIT, "baseline commit mismatch")
    require(ledger.get("cycle_id") == CYCLE_ID, "ledger cycle id mismatch")
    require(manifest.get("cycle_id") == CYCLE_ID, "manifest cycle id mismatch")
    # Fail on premature enrollment before consulting Git so this safety check
    # remains testable against a copied, non-repository scaffold.
    require(ledger.get("fresh_sources") == [], "fresh source appeared before G5/G6")
    require(manifest.get("source_ids") == [] and manifest.get("pairs") == [], "holdout manifest is not empty")

    finding_binding = record["baseline"]["scientific_review_finding"]
    require(finding_binding.get("binding") == "git_blob_at_baseline_commit", "finding must bind a Git blob")
    finding_blob = git_blob(repo_root, BASELINE_COMMIT, FINDING_PATH)
    require(hashlib.sha256(finding_blob).hexdigest() == finding_binding.get("file_sha256"), "baseline finding blob mismatch")
    finding = json.loads(finding_blob.decode("utf-8"))
    require(
        finding.get("finding_payload_sha256") == finding_binding.get("finding_payload_sha256"),
        "baseline finding payload mismatch",
    )
    require(
        finding.get("status") == "CONFIRMATORY_RUN_INVALID_IMPLEMENTATION_NONCONFORMANCE",
        "baseline finding no longer blocks confirmatory use",
    )

    require(manifest.get("release_id") is None, "release id exists before G5")
    require(manifest.get("execution_authorized") is False, "execution was authorized before G7")
    require(manifest.get("ledger_sha256") == file_sha256(ledger_path), "manifest ledger binding mismatch")

    artifacts = record.get("r3_artifacts", {})
    require(artifacts.get("source_ledger", {}).get("sha256") == file_sha256(ledger_path), "record ledger binding mismatch")
    require(artifacts.get("holdout_manifest", {}).get("sha256") == file_sha256(manifest_path), "record manifest binding mismatch")
    require(protocol_path.is_file() and intake_readme.is_file(), "R3 protocol boundary is incomplete")

    prior_sources = ledger.get("prior_exposed_sources", [])
    require(len(prior_sources) >= 1, "R2 exposed source is absent from the rejection ledger")
    r2 = next((item for item in prior_sources if item.get("sha256") == R2_SOURCE_SHA256), None)
    require(r2 is not None, "R2 source hash is not rejected")
    require(r2.get("previously_used") is True, "R2 source must be marked previously used")
    require(r2.get("r3_disposition") == "permanently_ineligible_for_confirmatory_reuse", "R2 source disposition mismatch")
    rules = ledger.get("reuse_rejection_rules", {})
    for rule in (
        "path_match",
        "byte_hash_match",
        "canonical_dataset_subject_case_or_acquisition_match",
        "canonical_source_id_match",
        "lineage_ancestor_intersection",
        "renamed_copy",
        "derived_or_transcoded_copy",
        "ambiguous_or_incomplete_lineage",
    ):
        require(rules.get(rule) == "reject", f"reuse rule {rule} is not fail-closed")

    counters = record.get("activity_counters", {})
    require(counters and all(value == 0 for value in counters.values()), "R3 activity is nonzero at cycle start")
    require(ledger.get("enrollment", {}).get("fresh_source_count") == 0, "ledger has an enrolled source")
    require(manifest.get("source_bytes_accessed") == 0, "manifest records source-byte access")
    require(manifest.get("labels_accessed") == 0, "manifest records label access")

    instruction = record.get("project_owner_instruction", {})
    require(instruction.get("role") == "project_owner_instruction", "instruction role was overstated")
    for field in (
        "is_release_reviewer_attestation",
        "is_data_custodian_attestation",
        "authorizes_source_access",
        "authorizes_g5_freeze",
        "authorizes_g6_enrollment",
        "authorizes_g7_execution",
    ):
        require(instruction.get(field) is False, f"project instruction improperly sets {field}")

    required_gates = {
        "G3_corrected_evaluator": "IN_PROGRESS",
        "G5_release_freeze": "BLOCKED_PENDING_G3_AND_TESTS",
        "G6_fresh_source_enrollment": "BLOCKED_PENDING_G5_AND_FRESH_SOURCE",
        "G7_one_run_authorization": "BLOCKED_PENDING_G5_G6",
        "G8_scientific_release_review": "NOT_STARTED",
    }
    require(record.get("gate_state") == required_gates, "R3 gate state is premature or incomplete")

    r3_roots = set(record.get("output_namespaces", {}).values())
    require(r3_roots == {
        "outputs/week08_r3_holdout",
        "outputs/week08_r3_final",
        "outputs/week08_r3_archives",
    }, "R3 output namespaces are incomplete")
    require(set(manifest.get("output_namespaces", {}).values()) == r3_roots, "manifest output namespaces differ")

    return {
        "status": "PASS",
        "cycle_id": CYCLE_ID,
        "record_payload_sha256": recorded_hash,
        "fresh_sources": 0,
        "source_accesses": 0,
        "evaluation_runs": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="validate without changing any files")
    args = parser.parse_args()
    print(json.dumps(validate_scaffold(args.repo_root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
