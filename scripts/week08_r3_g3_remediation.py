#!/usr/bin/env python3
"""Validate the R3 evaluator/reporting remediation without opening holdout data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from image_registration.week8_evaluation import (  # noqa: E402
    DECISION_SCHEMA_VERSION,
    EVALUATION_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    PREPARE_SCHEMA_VERSION,
    WEEK8_SCHEMA_VERSION,
    canonical_sha256,
)
from week08_final_evaluation import (  # noqa: E402
    DEFAULT_CONFIG,
    R3_CONFIG,
    build_development_plan,
    load_protocol,
)


REPORT = ROOT / "reports/week08_r3_g3_remediation.json"
CYCLE_ID = "week08-r3-confirmatory-20261116"


class G3RemediationError(ValueError):
    """Raised when the corrected pre-freeze contract does not verify."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise G3RemediationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def _blocked(config_path: Path, expected: str) -> None:
    try:
        load_protocol(config_path, development=False)
    except ValueError as exc:
        require(expected in str(exc), f"Unexpected final-mode block for {config_path.name}: {exc}")
    else:
        raise G3RemediationError(f"Final mode opened prematurely for {config_path.name}")


def validate(root: Path = ROOT) -> dict[str, Any]:
    require(root.resolve() == ROOT.resolve(), "G3 validation must run in the canonical repository")
    report = load_json(REPORT)
    recorded_hash = report.get("report_payload_sha256")
    payload = dict(report)
    payload.pop("report_payload_sha256", None)
    require(recorded_hash == canonical_sha256(payload), "G3 remediation report self-hash mismatch")
    require(report.get("cycle_id") == CYCLE_ID, "G3 report cycle mismatch")
    require(report.get("status") == "PASS_TECHNICAL_REMEDIATION", "G3 remediation is not passing")

    expected_schemas = {
        "runner": WEEK8_SCHEMA_VERSION,
        "plan": PLAN_SCHEMA_VERSION,
        "prepare_receipt": PREPARE_SCHEMA_VERSION,
        "decision_seal": DECISION_SCHEMA_VERSION,
        "evaluation_summary": EVALUATION_SCHEMA_VERSION,
    }
    require(report.get("schema_contract") == expected_schemas, "Evaluator schema contract mismatch")

    bindings = report.get("artifact_bindings")
    require(isinstance(bindings, Mapping) and bindings, "G3 report lacks artifact bindings")
    for name, binding in bindings.items():
        require(isinstance(binding, Mapping), f"Invalid binding: {name}")
        path = root / str(binding.get("path", ""))
        require(path.is_file(), f"Bound artifact is missing: {path}")
        require(sha256_file(path) == binding.get("sha256"), f"Bound artifact changed: {name}")

    _, config, plan, pairs, methods = build_development_plan(R3_CONFIG)
    require(config.get("cycle_id") == CYCLE_ID, "R3 config cycle mismatch")
    require(config.get("state") == "r3_g3_remediation_in_progress_no_source_access", "R3 state is premature")
    plan_record = report.get("development_plan_probe", {})
    require(plan_record.get("plan_sha256") == plan.get("plan_sha256"), "Development plan digest changed")
    require(plan_record.get("expected_counts") == plan.get("expected_counts"), "Development counts changed")
    require(plan_record.get("pair_specs") == len(pairs), "Development pair count changed")
    require(plan_record.get("method_specs") == len(methods), "Development method count changed")
    for field in (
        "uncertainty_sha256",
        "endpoint_availability_sha256",
        "reporting_contract_sha256",
        "mandatory_reporting_strata_sha256",
    ):
        require(plan_record.get(field) == plan.get(field), f"Plan {field} changed")

    _blocked(DEFAULT_CONFIG, "R2 holdout is exposed")
    _blocked(R3_CONFIG, "blocked until renewed G5, G6, and G7")

    ledger = load_json(root / "configs/week08_r3_source_use_ledger.json")
    manifest = load_json(root / "data/manifests/week08_r3_holdout_sources.json")
    require(ledger.get("fresh_sources") == [], "A source was enrolled before G5/G6")
    require(manifest.get("source_ids") == [] and manifest.get("pairs") == [], "R3 manifest is not empty")
    require(manifest.get("execution_authorized") is False, "R3 execution was authorized prematurely")
    for output in ("outputs/week08_r3_holdout", "outputs/week08_r3_final", "outputs/week08_r3_archives"):
        require(not (root / output).exists(), f"R3 evidence output exists before G7: {output}")

    counters = report.get("activity_counters", {})
    require(counters and all(value == 0 for value in counters.values()), "R3 activity counters are nonzero")
    gates = report.get("gate_state", {})
    require(gates.get("G3_corrected_evaluator") == "PASS_TECHNICAL_REMEDIATION", "G3 state mismatch")
    require(gates.get("G5_release_freeze") == "BLOCKED_PENDING_DISTINCT_REVIEW", "G5 opened prematurely")
    require(gates.get("G6_fresh_source_enrollment") == "BLOCKED_PENDING_G5_AND_FRESH_SOURCE", "G6 opened prematurely")
    require(gates.get("G7_one_run_authorization") == "BLOCKED_PENDING_G5_G6", "G7 opened prematurely")

    return {
        "status": "PASS",
        "cycle_id": CYCLE_ID,
        "report_payload_sha256": recorded_hash,
        "tests_passed": report["validation"]["tests_passed"],
        "tests_skipped": report["validation"]["tests_skipped"],
        "fresh_sources": 0,
        "r3_evaluation_runs": 0,
        "next_gate": "G5_DISTINCT_RELEASE_REVIEW",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate the tracked report without writes")
    parser.parse_args()
    print(json.dumps(validate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
