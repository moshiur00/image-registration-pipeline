from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_phase9_data_quality_closure.py"
REPORT = ROOT / "reports/week08_phase9_data_quality_closure.json"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_phase9_data_quality_closure", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_tracked_report_is_self_hashed_and_sanitized():
    module = load_module()
    report = load_report()
    assert report["schema_version"] == module.SCHEMA_VERSION
    payload = dict(report)
    recorded = payload.pop("report_payload_sha256")
    assert module.canonical_sha256(payload) == recorded
    module.validate_sanitized_report(report)
    assert report["privacy"] == {
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
    }


def test_tracked_report_reconciles_attempt_and_policy_denominators():
    report = load_report()
    attempts = report["attempt_reconciliation"]
    assert attempts["planned_attempts"] == 294
    assert attempts["attempted"] == 294
    assert attempts["terminal_records"] == 294
    assert attempts["valid_ground_truth_attempts"] == 294
    assert attempts["status_counts"] == {"completed": 284, "CHECK": 0, "failed": 10}
    assert attempts["geometric_successes"] == 278
    assert attempts["geometric_failures_among_completed"] == 6
    assert attempts["not_geometrically_evaluable_due_to_execution_failure"] == 10
    assert attempts["execution_completion_rate"] == {
        "numerator": 284,
        "denominator": 294,
        "value": 284 / 294,
    }
    assert attempts["geometric_success_rate"] == {
        "numerator": 278,
        "denominator": 294,
        "value": 278 / 294,
    }
    assert attempts["conditional_accuracy"] == {
        "numerator": 278,
        "denominator": 284,
        "value": 278 / 284,
    }

    policy = report["policy_reconciliation"]
    assert policy["eligible_pairs"] == 24
    assert policy["decision_records"] == 24
    assert policy["decision_counts"] == {
        "selected": 0,
        "abstained": 24,
        "invalid": 0,
        "missing": 0,
    }
    assert policy["coverage"] == {"numerator": 0, "denominator": 24, "value": 0.0}
    assert policy["abstention_rate"] == {"numerator": 24, "denominator": 24, "value": 1.0}
    assert policy["selective_correctness"] == {
        "numerator": 0,
        "denominator": 0,
        "value": None,
    }


def test_strata_reconcile_to_all_attempts_without_row_identifiers():
    report = load_report()
    for rows in report["aggregate_strata"].values():
        assert sum(row["attempts"] for row in rows) == 294
        assert sum(sum(row["status_counts"].values()) for row in rows) == 294
        assert sum(row["geometric_successes"] for row in rows) == 278
    assert report["aggregate_strata"]["modality_class"] == [
        {
            "value": "monomodal",
            "attempts": 240,
            "status_counts": {"completed": 230, "CHECK": 0, "failed": 10},
            "geometric_successes": 227,
        },
        {
            "value": "simulated_multimodal",
            "attempts": 54,
            "status_counts": {"completed": 54, "CHECK": 0, "failed": 0},
            "geometric_successes": 51,
        },
    ]


def test_review_and_claim_scope_remain_fail_closed():
    report = load_report()
    assert report["status"] == "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW"
    assert report["acceptance"]["g8_status"] == "IN_PROGRESS"
    assert report["review"]["developer_analyst"]["status"] == "COMPLETE"
    assert report["review"]["scientific_reviewer"]["status"] == "PENDING"
    assert report["review"]["release_reviewer"]["status"] == "PENDING"
    assert report["claim_scope"]["scope"] == "source_specific_software_evidence_only"
    assert report["claim_scope"]["recommendation_disposition"] == (
        "preserve_results_keep_policy_non_deployed"
    )
    assert report["claim_scope"]["prohibited_claims"] == [
        "anatomical_generalization",
        "clinical_recommendation",
        "external_validity",
        "modality_wide_generalization",
        "population_generalization",
    ]


def test_privacy_guard_rejects_row_identifiers_and_private_paths():
    module = load_module()
    report = load_report()
    with_identifier = copy.deepcopy(report)
    with_identifier["leak"] = {"pair_id": "final-deadbeef"}
    with pytest.raises(module.ClosureError, match="forbidden key"):
        module.validate_sanitized_report(with_identifier)
    with_private_path = copy.deepcopy(report)
    with_private_path["leak"] = "outputs/week08_holdout/sealed_labels/labels.json"
    with pytest.raises(module.ClosureError, match="private label path"):
        module.validate_sanitized_report(with_private_path)


def test_integrity_helpers_detect_duplicates_missing_and_nonfinite_values():
    module = load_module()
    result = module.id_integrity(["a", "b", "b"], ["a", "c", "c"])
    assert result == {
        "planned_count": 3,
        "planned_unique_count": 2,
        "observed_count": 3,
        "observed_unique_count": 2,
        "duplicate_planned_ids": 1,
        "duplicate_observed_ids": 1,
        "missing_ids": 1,
        "unexpected_ids": 1,
        "exact_set_match": False,
    }
    assert module.count_nonfinite_numbers({"ok": [0.0, None], "bad": math.inf}) == 1


@pytest.mark.skipif(
    not (ROOT / "outputs/week08_final/evaluation_summary.json").is_file(),
    reason="private Week 8 evidence is not attached",
)
def test_tracked_report_matches_attached_sealed_evidence():
    module = load_module()
    verified = module.verify_report(REPORT, ROOT)
    assert verified["acceptance"]["technical_data_quality_status"] == "PASS"
