from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_phase9_scientific_review_audit.py"
FINDING = ROOT / "reports/week08_phase9_scientific_review_finding.json"
TABLE_DIR = ROOT / "reports/week08_phase9_review_tables"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_phase9_scientific_review_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_finding() -> dict:
    return json.loads(FINDING.read_text(encoding="utf-8"))


def read_csv(name: str) -> list[dict[str, str]]:
    with (TABLE_DIR / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_finding_is_self_hashed_and_blocks_confirmatory_release():
    module = load_module()
    finding = load_finding()
    assert finding["schema_version"] == module.SCHEMA_VERSION
    payload = dict(finding)
    recorded = payload.pop("finding_payload_sha256")
    assert module.canonical_sha256(payload) == recorded
    assert finding["status"] == "CONFIRMATORY_RUN_INVALID_IMPLEMENTATION_NONCONFORMANCE"
    assert finding["disposition"] == {
        "confirmatory_status": "invalid",
        "fresh_unexposed_holdout_required_for_corrected_confirmatory_claim": True,
        "frozen_evaluator_and_enforcement_must_be_corrected_before_new_g5": True,
        "g8_status": "BLOCKED",
        "phase8_execution_status": "completed_archived",
        "release_review_status": "BLOCKED_BY_SCIENTIFIC_AUDIT",
        "retained_evidence_scope": "source_specific_nonconfirmatory_software_evidence_only",
        "same_holdout_corrected_confirmatory_rerun_permitted": False,
    }
    assert finding["review"]["automated_scientific_audit"] == "FAIL"
    assert finding["review"]["named_human_scientific_attestation"] == "NOT_RECORDED"
    assert finding["unaffected_outcomes"]["policy_status"] == "non_deployed"


def test_immutable_bindings_and_supplement_artifacts_are_exact():
    module = load_module()
    finding = load_finding()
    bindings = finding["immutable_bindings"]
    assert bindings["historical_artifacts_modified"] is False
    assert bindings["historical_phase9_2_artifacts_verified"] == 14
    assert bindings["phase9_1_payload_sha256"] == module.EXPECTED_PAYLOAD_HASHES["phase9_1"]
    assert bindings["phase9_2_payload_sha256"] == module.EXPECTED_PAYLOAD_HASHES["phase9_2"]
    assert bindings["audit_generator_sha256"] == module.git_blob_sha256(
        ROOT,
        module.FINDING_GENERATOR_COMMIT,
        "scripts/week08_phase9_scientific_review_audit.py",
    )
    for relative, expected in bindings["files"].items():
        if relative in module.HISTORICAL_GIT_BINDINGS:
            assert module.git_blob_sha256(ROOT, module.REVIEWED_COMMIT, relative) == expected
        else:
            path = ROOT / relative
            if relative.startswith("outputs/") and not path.is_file():
                continue
            assert module.sha256_file(path) == expected
    assert len(finding["supplement"]["artifacts"]) == 5
    for artifact in finding["supplement"]["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert path.stat().st_size == artifact["size_bytes"]
        assert module.sha256_file(path) == artifact["sha256"]
        module.validate_sanitized_file(path)


def test_interval_erratum_records_exact_frozen_quantile_impact():
    finding = load_finding()
    issue = finding["findings"]["frozen_wilson_quantile_not_used"]
    assert issue["expected_z"] == 1.959963984540054
    assert issue["observed_helper_default_z"] == 1.96
    assert issue["evaluator_call_lines_omitting_z"] == [1739, 1900, 2379]
    assert issue["sealed_impact"] == {
        "changed_endpoints_at_6_decimals": 141,
        "changed_records_at_6_decimals": 132,
        "defined_interval_records": 142,
        "mathematically_changed_records": 142,
        "total_interval_records": 157,
        "undefined_zero_denominator_records": 15,
    }
    rows = read_csv("wilson_interval_erratum.csv")
    assert len(rows) == 54
    assert sum(row["changed_at_6_decimals"] == "true" for row in rows) == 52
    overall = {
        row["metric"]: row
        for row in rows
        if row["historical_table"] == "track_a_overall.csv"
    }
    assert overall["execution_completion_rate"]["historical_lower_z_1_96"] == "0.938530"
    assert overall["execution_completion_rate"]["corrected_lower_z_1_959963984540054"] == "0.938531"
    track_b = next(
        row for row in rows
        if row["historical_table"] == "track_b_policy.csv"
        and row["scope"] == "overall"
        and row["metric"] == "coverage"
    )
    assert track_b["historical_upper_z_1_96"] == "0.137981"
    assert track_b["corrected_upper_z_1_959963984540054"] == "0.137976"


def test_supplement_closes_strata_pairwise_and_endpoint_reporting_gaps():
    track_a = read_csv("track_a_mandatory_strata.csv")
    track_b = read_csv("track_b_mandatory_strata.csv")
    endpoints = read_csv("track_a_endpoint_distributions.csv")
    pairwise = read_csv("pairwise_exact_mcnemar.csv")
    assert len(track_a) == 20
    assert len(track_b) == 15
    assert len(endpoints) == 21
    assert len(pairwise) == 9
    expected_dimensions = {
        "modality_class", "transform_model", "condition", "severity",
        "source_role", "source_identity",
    }
    assert {row["dimension"] for row in track_a} == expected_dimensions
    assert {row["dimension"] for row in track_b} == expected_dimensions | {"overall"}
    assert any(row["dimension"] == "source_identity" and row["stratum"] == "enrolled_source_1" for row in track_a)
    overall_b = next(row for row in track_b if row["dimension"] == "overall")
    assert (overall_b["eligible_pairs"], overall_b["selected_pairs"], overall_b["abstained_pairs"]) == ("24", "0", "24")
    assert (overall_b["invalid_rate_numerator"], overall_b["invalid_rate_denominator"]) == ("0", "24")
    assert (overall_b["missing_decision_rate_numerator"], overall_b["missing_decision_rate_denominator"]) == ("0", "24")
    assert (overall_b["selective_correctness_numerator"], overall_b["selective_correctness_denominator"], overall_b["selective_correctness_value"]) == ("0", "0", "NA")
    overall_endpoints = next(row for row in endpoints if row["dimension"] == "overall")
    assert overall_endpoints["total_runtime_ms_count"] == "294"
    assert overall_endpoints["method_runtime_ms_count"] == "0"
    assert overall_endpoints["valid_overlap_fraction_count"] == "0"
    assert overall_endpoints["tre_mean_px_count"] == overall_endpoints["tre_median_px_count"] == overall_endpoints["tre_p95_px_count"] == "284"
    assert sum(row["mcnemar_exact_two_sided_p"] == "0.250000" for row in pairwise) == 3
    assert sum(row["mcnemar_exact_two_sided_p"] == "1.000000" for row in pairwise) == 6


def test_integrity_gate_defects_are_disclosed_without_changing_outcome():
    finding = load_finding()
    issue = finding["findings"]["recommendation_integrity_checks_not_evidence_derived"]
    assert issue["no_firewall_or_integrity_incident"] == "hardcoded_true"
    assert issue["no_post_label_change"] == "cli_passed_true_unconditionally"
    assert issue["outcome_changed"] is False
    missing = finding["findings"]["frozen_secondary_endpoints_not_captured"]
    assert missing["availability"]["method_runtime_ms"] == 0
    assert missing["availability"]["valid_overlap_fraction"] == 0
    assert missing["retroactive_calculation_permitted"] is False


@pytest.mark.skipif(
    not (ROOT / "outputs/week08_final/evaluation_summary.json").is_file(),
    reason="private Week 8 evidence is not attached",
)
def test_finding_and_supplement_rebuild_byte_for_byte_from_sealed_summary():
    module = load_module()
    verified = module.verify_bundle(ROOT, FINDING)
    assert verified["finding_payload_sha256"] == load_finding()["finding_payload_sha256"]
