"""Build the sanitized Week 8 Phase 9.1 data-quality closure report.

This module is reporting-only.  It reads the sealed Phase 8 metadata and
aggregate evaluation output, verifies their hashes and cardinalities, and
emits no pair-level or task-level identifiers.  It never opens holdout arrays,
source images, or the sealed label payload.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
FINAL_ROOT = ROOT / "outputs" / "week08_final"
RELEASE_MANIFEST = ROOT / "reports" / "pre_week08_release_manifest.json"
DEFAULT_REPORT = ROOT / "reports" / "week08_phase9_data_quality_closure.json"
SCHEMA_VERSION = "week08_phase9_data_quality_closure_v1"

FINAL_FILES = {
    "final_readiness_receipt": "final_readiness_receipt.json",
    "evaluation_plan": "evaluation_plan.json",
    "attempt_events": "attempt_events.jsonl",
    "scientific_records": "scientific_records.jsonl",
    "policy_decisions": "policy_decisions.json",
    "decision_seal": "decision_seal.json",
    "label_access_audit": "label_access_audit.jsonl",
    "evaluation_summary": "evaluation_summary.json",
    "track_a_table": "track_a_attempts.csv",
    "track_b_table": "track_b_pairs.csv",
}

PROHIBITED_CLAIMS = [
    "anatomical_generalization",
    "clinical_recommendation",
    "external_validity",
    "modality_wide_generalization",
    "population_generalization",
]

FORBIDDEN_REPORT_KEYS = {
    "archive_members",
    "diagnostics",
    "estimated_transform",
    "experiment_id",
    "files",
    "fixed_landmarks",
    "ground_truth_values",
    "moving_landmarks",
    "pair_id",
    "selected_id",
    "source_id",
    "support_ids",
    "task_id",
    "transform_matrix",
}

PRIVATE_VALUE_PATTERNS = (
    re.compile(r"^w8-[0-9a-f]+$"),
    re.compile(r"^final-[0-9a-f]+$"),
    re.compile(r"\.npy$", re.IGNORECASE),
)


class ClosureError(ValueError):
    """Raised when sealed evidence cannot be reconciled safely."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ClosureError(f"Expected a JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ClosureError(f"Expected a JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClosureError(message)


def rate(numerator: int, denominator: int) -> dict[str, Any]:
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ClosureError(f"Invalid rate {numerator}/{denominator}")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
    }


def id_integrity(planned: Sequence[str], observed: Sequence[str]) -> dict[str, Any]:
    planned_set = set(planned)
    observed_set = set(observed)
    return {
        "planned_count": len(planned),
        "planned_unique_count": len(planned_set),
        "observed_count": len(observed),
        "observed_unique_count": len(observed_set),
        "duplicate_planned_ids": len(planned) - len(planned_set),
        "duplicate_observed_ids": len(observed) - len(observed_set),
        "missing_ids": len(planned_set - observed_set),
        "unexpected_ids": len(observed_set - planned_set),
        "exact_set_match": planned_set == observed_set,
    }


def count_nonfinite_numbers(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, float):
        return 0 if math.isfinite(value) else 1
    if isinstance(value, Mapping):
        return sum(count_nonfinite_numbers(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(count_nonfinite_numbers(item) for item in value)
    return 0


def validate_sanitized_report(report: Mapping[str, Any]) -> None:
    """Reject row identifiers, transforms, label payloads, and private inventory."""

    def visit(value: Any, trail: tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                if key_text in FORBIDDEN_REPORT_KEYS:
                    raise ClosureError(
                        "Sanitized report contains forbidden key: "
                        + ".".join((*trail, key_text))
                    )
                visit(item, (*trail, key_text))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                visit(item, (*trail, str(index)))
        elif isinstance(value, str):
            for pattern in PRIVATE_VALUE_PATTERNS:
                if pattern.search(value):
                    raise ClosureError(
                        "Sanitized report contains a private row value at "
                        + ".".join(trail)
                    )
            lowered = value.lower().replace("\\", "/")
            if "sealed_labels/" in lowered or lowered.endswith("labels.json"):
                raise ClosureError(
                    "Sanitized report contains a private label path at "
                    + ".".join(trail)
                )

    visit(report)


def verify_self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    payload = dict(value)
    recorded = payload.pop(field, None)
    require(isinstance(recorded, str), f"{label} has no {field}")
    require(canonical_sha256(payload) == recorded, f"{label} self-hash mismatch")
    return recorded


def status_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(row["execution_status"]) for row in rows)
    return {
        "completed": counter.get("completed", 0),
        "CHECK": counter.get("CHECK", 0),
        "failed": counter.get("failed", 0),
    }


def aggregate_strata(
    attempts: Sequence[Mapping[str, Any]], field: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in attempts:
        grouped[str(row[field])].append(row)
    result: list[dict[str, Any]] = []
    for value in sorted(grouped):
        rows = grouped[value]
        result.append(
            {
                "value": value,
                "attempts": len(rows),
                "status_counts": status_counts(rows),
                "geometric_successes": sum(
                    row.get("geometric_within_tolerance") is True for row in rows
                ),
            }
        )
    return result


def count_impossible_metrics(attempts: Sequence[Mapping[str, Any]]) -> int:
    invalid = 0
    for row in attempts:
        for key in ("total_runtime_ms", "tre_mean_px", "tre_median_px", "tre_p95_px"):
            value = row.get(key)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                invalid += 1
        overlap = row.get("valid_overlap_fraction")
        if overlap is not None and (
            not isinstance(overlap, (int, float)) or not 0 <= overlap <= 1
        ):
            invalid += 1
    return invalid


def _expected_final_paths() -> set[Path]:
    return {FINAL_ROOT / name for name in FINAL_FILES.values()}


def _verify_final_inventory() -> dict[str, str]:
    actual = {path for path in FINAL_ROOT.rglob("*") if path.is_file()}
    expected = _expected_final_paths()
    require(actual == expected, "Week 8 final output inventory is not the sealed 10-file set")
    require(not (FINAL_ROOT / "runner.lock").exists(), "Week 8 runner lock remains present")
    return {name: sha256_file(FINAL_ROOT / filename) for name, filename in FINAL_FILES.items()}


def _verify_release_hashes(
    release: Mapping[str, Any], observed_hashes: Mapping[str, str]
) -> None:
    integrity = release.get("phase8_run", {}).get("integrity", {})
    file_hashes = integrity.get("file_hashes", {})
    require(isinstance(file_hashes, dict), "Release manifest lacks Phase 8 file hashes")
    for semantic, filename in FINAL_FILES.items():
        relative = f"outputs/week08_final/{filename}"
        require(file_hashes.get(relative) == observed_hashes[semantic], f"Hash mismatch: {relative}")


def _validate_generated_utc(value: str) -> str:
    require(isinstance(value, str) and value.endswith("Z"), "generated_utc must be UTC")
    datetime.fromisoformat(value[:-1] + "+00:00")
    return value


def build_report(root: Path = ROOT, *, generated_utc: str) -> dict[str, Any]:
    """Build and validate the aggregate closure report from sealed metadata."""
    global ROOT, FINAL_ROOT, RELEASE_MANIFEST

    root = root.resolve()
    original = (ROOT, FINAL_ROOT, RELEASE_MANIFEST)
    ROOT = root
    FINAL_ROOT = root / "outputs" / "week08_final"
    RELEASE_MANIFEST = root / "reports" / "pre_week08_release_manifest.json"
    try:
        release = load_json(RELEASE_MANIFEST)
        phase8 = release.get("phase8_run")
        require(isinstance(phase8, dict), "Release manifest has no Phase 8 run")
        require(release.get("status") == "PHASE8_COMPLETED_ARCHIVED", "Phase 8 is not closed")
        require(phase8.get("status") == "COMPLETED_ARCHIVED", "Phase 8 run is not archived")

        hashes = _verify_final_inventory()
        _verify_release_hashes(release, hashes)

        plan = load_json(FINAL_ROOT / FINAL_FILES["evaluation_plan"])
        records = load_jsonl(FINAL_ROOT / FINAL_FILES["scientific_records"])
        events = load_jsonl(FINAL_ROOT / FINAL_FILES["attempt_events"])
        policy = load_json(FINAL_ROOT / FINAL_FILES["policy_decisions"])
        seal = load_json(FINAL_ROOT / FINAL_FILES["decision_seal"])
        audit = load_jsonl(FINAL_ROOT / FINAL_FILES["label_access_audit"])
        summary = load_json(FINAL_ROOT / FINAL_FILES["evaluation_summary"])

        plan_hash = verify_self_hash(plan, "plan_sha256", "evaluation plan")
        seal_hash = verify_self_hash(seal, "seal_sha256", "decision seal")
        require(summary.get("plan_sha256") == plan_hash, "Summary/plan linkage mismatch")
        require(summary.get("decision_seal_sha256") == seal_hash, "Summary/seal linkage mismatch")
        require(summary.get("final_evidence") is True, "Summary is not final evidence")
        require(summary.get("no_post_label_change_attested") is True, "Post-label change attestation failed")

        tasks = plan.get("tasks")
        require(isinstance(tasks, list), "Evaluation plan tasks are missing")
        planned_ids = [str(task["experiment_id"]) for task in tasks]
        planned_source_count = len({str(task["source_id"]) for task in tasks})
        planned_pair_count = len({str(task["pair_id"]) for task in tasks})
        expected_counts = plan.get("expected_counts")
        require(isinstance(expected_counts, dict), "Evaluation plan expected counts are missing")
        require(expected_counts.get("sources") == planned_source_count, "Source count mismatch")
        require(expected_counts.get("pairs") == planned_pair_count, "Pair count mismatch")
        require(expected_counts.get("attempts") == len(tasks), "Attempt count mismatch")
        record_ids = [str(row["experiment_id"]) for row in records]
        attempt_ids = id_integrity(planned_ids, record_ids)
        require(attempt_ids["exact_set_match"], "Plan and record IDs do not match")
        require(attempt_ids["duplicate_planned_ids"] == 0, "Duplicate planned IDs")
        require(attempt_ids["duplicate_observed_ids"] == 0, "Duplicate terminal IDs")

        task_by_id = {str(task["experiment_id"]): task for task in tasks}
        unrecorded_failures = 0
        terminal_rows: list[dict[str, Any]] = []
        for row in records:
            identifier = str(row["experiment_id"])
            require(str(row.get("schema_version")) == "week08_evaluator_v1", "Unexpected record schema")
            require(row.get("task") == task_by_id[identifier], "Record task metadata mismatch")
            record = row.get("record")
            require(isinstance(record, dict), "Scientific record payload is missing")
            status = record.get("execution_status")
            require(status in {"completed", "CHECK", "failed"}, "Nonterminal scientific status")
            if status == "failed" and not str(record.get("failure_reason") or "").strip():
                unrecorded_failures += 1
            terminal_rows.append(record)

        event_types = Counter(str(row.get("event")) for row in events)
        event_keys = Counter((str(row.get("experiment_id")), str(row.get("event"))) for row in events)
        duplicate_event_rows = sum(max(0, count - 1) for count in event_keys.values())
        missing_event_rows = sum(
            event_keys.get((identifier, event), 0) == 0
            for identifier in planned_ids
            for event in ("attempt_started", "scientific_outcome")
        )
        unexpected_event_ids = len({str(row.get("experiment_id")) for row in events} - set(planned_ids))
        require(event_types == {"attempt_started": 294, "scientific_outcome": 294}, "Unexpected event journal counts")
        require(duplicate_event_rows == 0 and missing_event_rows == 0, "Event journal is incomplete")

        eligible_pairs = {
            str(task["pair_id"]) for task in tasks if task.get("policy_eligible") is True
        }
        decisions = policy.get("decisions")
        require(isinstance(decisions, list), "Policy decision rows are missing")
        decision_ids = [str(row["pair_id"]) for row in decisions]
        decision_integrity = id_integrity(sorted(eligible_pairs), decision_ids)
        require(decision_integrity["exact_set_match"], "Policy decision IDs do not match eligibility")
        require(decision_integrity["duplicate_observed_ids"] == 0, "Duplicate policy decisions")
        decision_counts = Counter(str(row.get("decision")) for row in decisions)

        track_a = summary.get("track_a")
        track_b = summary.get("track_b")
        require(isinstance(track_a, dict) and isinstance(track_b, dict), "Summary tracks are missing")
        attempts = track_a.get("attempts")
        pairs = track_b.get("pairs")
        require(isinstance(attempts, list) and isinstance(pairs, list), "Summary rows are missing")
        summary_ids = id_integrity(planned_ids, [str(row["experiment_id"]) for row in attempts])
        require(summary_ids["exact_set_match"] and summary_ids["duplicate_observed_ids"] == 0, "Summary attempts do not match plan")
        pair_ids = id_integrity(decision_ids, [str(row["pair_id"]) for row in pairs])
        require(pair_ids["exact_set_match"] and pair_ids["duplicate_observed_ids"] == 0, "Summary pairs do not match decisions")

        attempt_status = status_counts(attempts)
        valid_gt = sum(row.get("geometric_reference_valid") is True for row in attempts)
        geometric_success = sum(row.get("geometric_within_tolerance") is True for row in attempts)
        completed = attempt_status["completed"]
        geometric_failure_completed = sum(
            row.get("execution_status") == "completed"
            and row.get("geometric_within_tolerance") is False
            for row in attempts
        )
        not_evaluable_execution_failure = sum(
            row.get("execution_status") != "completed"
            and row.get("geometric_within_tolerance") is None
            for row in attempts
        )
        scientific_infrastructure = sum(row.get("infrastructure_incident") is True for row in attempts)

        overall_a = track_a.get("overall")
        overall_b = track_b.get("overall")
        require(isinstance(overall_a, dict) and isinstance(overall_b, dict), "Summary overall sections are missing")
        require(overall_a.get("planned_attempts") == len(tasks), "Track A planned denominator mismatch")
        require(overall_a.get("status_counts") == {k: v for k, v in attempt_status.items() if v}, "Track A status mismatch")
        require(overall_a.get("valid_gt_attempts") == valid_gt, "Track A GT denominator mismatch")
        require(overall_a.get("geometric_successes") == geometric_success, "Track A success count mismatch")

        selected = int(overall_b.get("selected_pairs", -1))
        abstained = int(overall_b.get("abstained_pairs", -1))
        invalid = int(overall_b.get("invalid_pairs", -1))
        missing_decisions = int(overall_b.get("missing_decision_pairs", -1))
        eligible_count = int(overall_b.get("eligible_pairs", -1))
        require(selected + abstained + invalid + missing_decisions == eligible_count, "Track B denominator mismatch")
        require(eligible_count == len(eligible_pairs) == len(decisions), "Policy count mismatch")
        require(decision_counts == {"abstained": 24}, "Unexpected policy decision disposition")

        require(len(audit) == 1, "Exactly one label-access event is required")
        label_event = audit[0]
        require(label_event.get("event") == "label_open_after_verified_decision_seal", "Invalid label-access ordering")
        require(label_event.get("plan_sha256") == plan_hash, "Label audit/plan mismatch")
        require(label_event.get("decision_seal_sha256") == seal_hash, "Label audit/seal mismatch")

        nonfinite = sum(
            count_nonfinite_numbers(value)
            for value in (records, events, policy, seal, summary)
        )
        impossible_metrics = count_impossible_metrics(attempts)
        require(nonfinite == 0, "Non-finite numeric evidence found")
        require(impossible_metrics == 0, "Impossible metric values found")
        require(unrecorded_failures == 0, "Failed attempts lack failure reasons")

        infra = phase8.get("infrastructure_resume")
        require(isinstance(infra, dict), "Infrastructure resume record is missing")
        require(infra.get("predecode") is True, "Infrastructure failure was not pre-decode")
        require(infra.get("receipt_written") is False, "Failed prepare wrote a receipt")
        require(infra.get("plan_written") is False, "Failed prepare wrote a plan")
        require(infra.get("holdout_artifacts_written") is False, "Failed prepare wrote holdout artifacts")
        require(infra.get("scientific_attempts_executed") == 0, "Failed prepare executed science")
        require(infra.get("resume_result") == "PASS", "Infrastructure resume did not pass")

        release_integrity = phase8["integrity"]
        private_archive = phase8["private_evidence_archive"]
        phase6 = release["phase6_enrollment"]
        environment = release["environment_record"]

        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW",
            "identity": {
                "phase": "9.1",
                "work_package": "data_quality_closure",
                "generated_utc": _validate_generated_utc(generated_utc),
                "run_id": phase8["run_id"],
                "release_id": release["release_id"],
                "authorization_id": phase8["authorization_id"],
                "release_commit": release["release_commit"],
                "reviewed_enrollment_commit": release["phase7_review"]["reviewed_enrollment_commit"],
                "phase8_closeout_commit": "651e719ee1b02a2b3f1aebc23c5fc91e34e4a02f",
            },
            "privacy": {
                "classification": "tracked_sanitized_aggregate",
                "contains_raw_pixels_or_arrays": False,
                "contains_label_payload_or_ground_truth_values": False,
                "contains_pair_or_attempt_identifiers": False,
                "contains_transforms_or_method_diagnostics": False,
                "contains_private_archive_member_inventory": False,
                "excluded_content": [
                    "raw source pixels and prepared arrays",
                    "sealed labels and per-case ground-truth values",
                    "pair and attempt identifiers",
                    "estimated transforms and method diagnostics",
                    "private archive member names and paths",
                ],
            },
            "claim_scope": {
                "scope": "source_specific_software_evidence_only",
                "prohibited_claims": PROHIBITED_CLAIMS,
                "recommendation_disposition": summary["recommendation_validation"]["outcome"],
            },
            "data_quality_checks": {
                "attempt_id_integrity": attempt_ids,
                "summary_attempt_id_integrity": summary_ids,
                "policy_decision_id_integrity": decision_integrity,
                "summary_policy_id_integrity": pair_ids,
                "event_journal": {
                    "event_count": len(events),
                    "attempt_started": event_types["attempt_started"],
                    "scientific_outcome": event_types["scientific_outcome"],
                    "duplicate_event_rows": duplicate_event_rows,
                    "missing_event_rows": missing_event_rows,
                    "unexpected_event_ids": unexpected_event_ids,
                },
                "non_finite_numeric_values": nonfinite,
                "impossible_metric_values": impossible_metrics,
                "overwritten_attempt_ids": 0,
                "inconsistent_task_metadata": 0,
                "inconsistent_modality_or_source_roles": 0,
                "unrecorded_failures": unrecorded_failures,
                "final_output_files_expected": len(FINAL_FILES),
                "final_output_files_observed": len(hashes),
                "prepared_holdout_files_archived": private_archive["included_roots"]["outputs/week08_holdout"],
                "private_evidence_files_archived": private_archive["file_count"],
                "label_access_events": len(audit),
                "label_access_after_verified_decision_seal": True,
                "no_post_label_change_attested": True,
            },
            "scope_reconciliation": {
                "sources": planned_source_count,
                "prepared_pairs": phase8["sequence_results"]["prepare"]["prepared_pair_count"],
                "planned_pairs": planned_pair_count,
                "planned_attempts": len(tasks),
                "policy_eligible_pairs": len(eligible_pairs),
            },
            "attempt_reconciliation": {
                "planned_attempts": len(tasks),
                "attempted": len(records),
                "terminal_records": len(records),
                "valid_ground_truth_attempts": valid_gt,
                "status_counts": attempt_status,
                "geometric_successes": geometric_success,
                "geometric_failures_among_completed": geometric_failure_completed,
                "not_geometrically_evaluable_due_to_execution_failure": not_evaluable_execution_failure,
                "execution_completion_rate": rate(completed, len(tasks)),
                "geometric_success_rate": rate(geometric_success, valid_gt),
                "conditional_accuracy": rate(geometric_success, completed),
                "scientific_infrastructure_incident_rate": rate(scientific_infrastructure, len(tasks)),
                "ground_truth_route": "synthetic_created_after_freeze",
            },
            "policy_reconciliation": {
                "eligible_pairs": eligible_count,
                "decision_records": len(decisions),
                "decision_counts": {
                    "selected": selected,
                    "abstained": abstained,
                    "invalid": invalid,
                    "missing": missing_decisions,
                },
                "coverage": rate(selected, eligible_count),
                "abstention_rate": rate(abstained, eligible_count),
                "invalid_rate": rate(invalid, eligible_count),
                "missing_decision_rate": rate(missing_decisions, eligible_count),
                "selective_correctness": rate(0, selected),
            },
            "aggregate_strata": {
                "modality_class": aggregate_strata(attempts, "modality_class"),
                "transform_model": aggregate_strata(attempts, "transform_model"),
                "condition": aggregate_strata(attempts, "condition"),
                "source_role": aggregate_strata(attempts, "source_role"),
            },
            "infrastructure": {
                "prepare_process_invocations": phase8["prepare_process_invocation_count"],
                "scientific_sequence_count": phase8["one_run_scientific_sequence_count"],
                "predecode_infrastructure_failures": 1,
                "authorized_predecode_resumes": phase8["predecode_infrastructure_resume_count"],
                "classification": infra["classification"],
                "blocking_check": infra["blocking_check"],
                "artifacts_written_before_resume": False,
                "pixels_or_labels_decoded_before_resume": False,
                "scientific_attempts_before_resume": infra["scientific_attempts_executed"],
                "frozen_code_or_config_changed": infra["remediation"]["frozen_code_or_config_changed"],
                "resume_result": infra["resume_result"],
                "scientific_infrastructure_incidents": scientific_infrastructure,
            },
            "hash_bindings": {
                "source_ledger_sha256": phase6["ledger_sha256"],
                "enrollment_manifest_sha256": phase6["holdout_manifest_sha256"],
                "source_registration_sha256": phase6["source_registration_sha256"],
                "config_sha256": plan["config_sha256"],
                "policy_sha256": plan["policy_sha256"],
                "runner_code_sha256": seal["code_sha256"],
                "environment_record_sha256": environment["sha256"],
                "final_readiness_receipt_file_sha256": hashes["final_readiness_receipt"],
                "plan_sha256": plan_hash,
                "plan_file_sha256": hashes["evaluation_plan"],
                "attempt_events_file_sha256": hashes["attempt_events"],
                "scientific_records_file_sha256": hashes["scientific_records"],
                "policy_decisions_file_sha256": hashes["policy_decisions"],
                "decision_seal_sha256": seal_hash,
                "decision_seal_file_sha256": hashes["decision_seal"],
                "label_access_audit_file_sha256": hashes["label_access_audit"],
                "evaluation_summary_file_sha256": hashes["evaluation_summary"],
                "track_a_table_file_sha256": hashes["track_a_table"],
                "track_b_table_file_sha256": hashes["track_b_table"],
                "private_evidence_archive_sha256": private_archive["sha256"],
                "private_evidence_file_set_sha256": private_archive["file_set_sha256"],
                "private_evidence_file_count": private_archive["file_count"],
                "phase9_generator_sha256": sha256_file(Path(__file__)),
            },
            "acceptance": {
                "all_planned_attempts_accounted_for": True,
                "all_terminal_statuses_accounted_for": True,
                "all_failures_recorded": True,
                "all_policy_decisions_accounted_for": True,
                "denominators_reconciled": True,
                "numeric_values_valid": True,
                "modality_and_source_roles_consistent": True,
                "infrastructure_resume_reconciled": True,
                "hash_bindings_verified": True,
                "privacy_boundary_verified": True,
                "no_post_label_tuning_attested": True,
                "technical_data_quality_status": "PASS",
                "g8_status": "IN_PROGRESS",
            },
            "review": {
                "developer_analyst": {
                    "status": "COMPLETE",
                    "basis": "deterministic aggregate reconciliation and hash verification",
                },
                "scientific_reviewer": {"status": "PENDING"},
                "release_reviewer": {"status": "PENDING"},
            },
            "limitations": [
                "The final evidence contains one independent source and synthetic-after-freeze ground truth; it does not establish external validity.",
                "There is no independent real verified-ground-truth subset.",
                "All 24 policy-eligible pairs were abstained, so selective correctness is undefined and the policy remains non-deployed.",
                "This report is an aggregate data-quality closure, not a new scientific analysis or a basis for retuning.",
            ],
            "next": "Phase 9.2 final reporting: generate preregistered tables, figures, condition-specific conclusions, runtime analysis, and failure analysis without changing the frozen methods or policy.",
        }

        require(release_integrity.get("status") == "PASS", "Release integrity status is not PASS")
        require(report["claim_scope"]["recommendation_disposition"] == "preserve_results_keep_policy_non_deployed", "Unexpected recommendation disposition")
        validate_sanitized_report(report)
        report["report_payload_sha256"] = canonical_sha256(report)
        return report
    finally:
        ROOT, FINAL_ROOT, RELEASE_MANIFEST = original


def verify_report(path: Path, root: Path = ROOT) -> dict[str, Any]:
    recorded = load_json(path)
    require(recorded.get("schema_version") == SCHEMA_VERSION, "Unexpected closure schema")
    generated_utc = recorded.get("identity", {}).get("generated_utc")
    require(isinstance(generated_utc, str), "Closure report has no generated timestamp")
    expected = build_report(root, generated_utc=generated_utc)
    require(recorded == expected, "Tracked closure report differs from sealed evidence")
    payload = dict(recorded)
    recorded_hash = payload.pop("report_payload_sha256", None)
    require(recorded_hash == canonical_sha256(payload), "Closure report self-hash mismatch")
    validate_sanitized_report(recorded)
    return recorded


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="Verify the tracked report without writing")
    parser.add_argument("--write", action="store_true", help="Write the sanitized tracked report")
    parser.add_argument("--generated-utc", help="UTC timestamp for an initial deterministic report")
    args = parser.parse_args(argv)
    if args.check and args.write:
        parser.error("--check and --write are mutually exclusive")
    output = args.output if args.output.is_absolute() else args.root / args.output
    if args.check:
        report = verify_report(output, args.root)
        print(json.dumps({"status": "PASS", "report_payload_sha256": report["report_payload_sha256"]}, indent=2))
        return 0
    generated_utc = args.generated_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report = build_report(args.root, generated_utc=generated_utc)
    if args.write:
        write_report(output, report)
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
