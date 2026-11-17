from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_r3_reporting.py"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_r3_reporting", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(module):
    dimensions = [
        {
            "modality_class": "monomodal",
            "transform_model": "affine",
            "condition": "none",
            "severity": "none",
            "source_role": "full_project_independent",
            "source_id": "source-alpha",
        },
        {
            "modality_class": "simulated_multimodal",
            "transform_model": "affine",
            "condition": "repeated_pattern",
            "severity": "moderate",
            "source_role": "full_project_independent",
            "source_id": "source-beta",
        },
    ]
    attempts = []
    outcomes = ((True, False), (True, True))
    for pair_index, values in enumerate(outcomes):
        for method_index, outcome in enumerate(values):
            attempts.append(
                {
                    "pair_id": f"pair-{pair_index + 1}",
                    "method_id": f"method-{method_index + 1}",
                    "config_id": f"config-{method_index + 1}",
                    "execution_status": "completed",
                    "estimated_transform_present": True,
                    "geometric_reference_valid": True,
                    "geometric_within_tolerance": outcome,
                    "infrastructure_incident": False,
                    "diagnostic_keys": ["ncc"],
                    "tre_mean_px": 0.5 + method_index,
                    "tre_median_px": 0.4 + method_index,
                    "tre_p95_px": 0.9 + method_index,
                    "valid_overlap_fraction": 0.9 - 0.1 * method_index,
                    "method_runtime_ms": 10.0 + pair_index + method_index,
                    "total_runtime_ms": 12.0 + pair_index + method_index,
                    "mae": None,
                    "mse": None,
                    "ncc": None,
                    "ssim": None,
                    "mi_nats": None,
                    **dimensions[pair_index],
                }
            )
    pairs = [
        {
            "pair_id": "pair-1",
            "decision": "selected",
            "selected_geometrically_correct": True,
            **dimensions[0],
        },
        {
            "pair_id": "pair-2",
            "decision": "abstained",
            "selected_geometrically_correct": None,
            **dimensions[1],
        },
    ]

    def category_rows(rows):
        return {
            dimension: [
                {dimension: value}
                for value in sorted({str(row[dimension]) for row in rows})
            ]
            for dimension in module.MANDATORY_STRATA
        }

    summary = {
        "schema_version": "week08_evaluation_summary_v2",
        "mode": "final",
        "track_a": {
            "attempts": attempts,
            "overall": module._track_a_summary(attempts),
            "strata": category_rows(attempts),
            "pairwise_method_comparisons": module._pairwise(attempts),
        },
        "track_b": {
            "pairs": pairs,
            "overall": module._track_b_summary(pairs),
            "strata": category_rows(pairs),
        },
    }
    plan = {
        "schema_version": "week08_evaluation_plan_v2",
        "uncertainty": {
            "confidence_level": 0.95,
            "binomial_interval": "wilson_score",
            "z_value": 1.2345,
        },
        "endpoint_availability": {
            "contract": "synthetic_reporting_fixture",
        },
        "reporting_contract": {
            "mandatory_strata": list(module.MANDATORY_STRATA),
            "required_tables": list(module.TABLE_FILES),
            "endpoint_metrics": list(module.ENDPOINT_METRICS),
            "source_alias_format": "enrolled_source_{ordinal:03d}",
        },
    }
    plan["plan_sha256"] = module.canonical_sha256(plan)
    integrity = {
        "no_firewall_or_integrity_incident": True,
        "no_post_label_change": True,
        "label_access_event_count": 1,
        "prior_label_access_event_count": 0,
        "prior_evaluation_output_count": 0,
    }
    integrity["evidence_sha256"] = module.canonical_sha256(integrity)
    summary.update({
        "plan_sha256": plan["plan_sha256"],
        "uncertainty_contract": dict(plan["uncertainty"]),
        "endpoint_availability_contract": dict(plan["endpoint_availability"]),
        "reporting_contract": dict(plan["reporting_contract"]),
        "mandatory_reporting_strata": list(module.MANDATORY_STRATA),
        "integrity_evidence": integrity,
    })
    return summary, plan


def test_builds_complete_data_driven_tables_with_frozen_wilson_z():
    module = load_module()
    summary, plan = fixture(module)
    tables = module.build_tables(summary, plan)

    assert tuple(tables) == module.TABLE_FILES
    assert {row["dimension"] for row in tables["track_a_mandatory_strata.csv"]} == set(module.MANDATORY_STRATA)
    assert {row["dimension"] for row in tables["track_b_mandatory_strata.csv"]} == set(module.MANDATORY_STRATA)
    assert len(tables["track_a_endpoint_distributions.csv"]) == (
        1 + sum(len(summary["track_a"]["strata"][name]) for name in module.MANDATORY_STRATA)
    ) * len(module.ENDPOINT_METRICS)

    overall_a = tables["track_a_overall.csv"][0]
    expected_low, expected_high = module.wilson_interval(4, 4, 1.2345)
    assert overall_a["execution_completion_rate_ci_lower"] == expected_low
    assert overall_a["execution_completion_rate_ci_upper"] == expected_high
    assert overall_a["execution_completion_rate_ci_z"] == 1.2345

    overall_b = tables["track_b_overall.csv"][0]
    assert overall_b["selective_correctness_denominator"] == 1
    assert overall_b["selective_correctness_value"] == 1.0
    pairwise = tables["pairwise_exact_mcnemar.csv"]
    assert len(pairwise) == 1
    assert pairwise[0]["method_a_only_success"] == 1
    assert pairwise[0]["method_b_only_success"] == 0


def test_source_identifiers_are_replaced_by_deterministic_aliases(tmp_path: Path):
    module = load_module()
    summary, plan = fixture(module)
    summary_path = tmp_path / "summary.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "tables"
    manifest_path = tmp_path / "manifest.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    manifest = module.generate_bundle(summary_path, plan_path, output, manifest_path)
    module.check_bundle(summary_path, plan_path, output, manifest_path)
    emitted = "\n".join(path.read_text(encoding="utf-8") for path in [*output.iterdir(), manifest_path])
    assert "source-alpha" not in emitted
    assert "source-beta" not in emitted
    assert "enrolled_source_001" in emitted
    assert "enrolled_source_002" in emitted
    assert manifest["sanitization"]["raw_source_identifiers_emitted"] is False
    payload = dict(manifest)
    recorded = payload.pop("payload_sha256")
    assert module.canonical_sha256(payload) == recorded


def test_zero_selected_pairs_keep_selective_correctness_null():
    module = load_module()
    summary, plan = fixture(module)
    for row in summary["track_b"]["pairs"]:
        row["decision"] = "abstained"
        row["selected_geometrically_correct"] = None
    summary["track_b"]["overall"] = module._track_b_summary(summary["track_b"]["pairs"])
    tables = module.build_tables(summary, plan)
    overall = tables["track_b_overall.csv"][0]
    assert overall["coverage_numerator"] == 0
    assert overall["selective_correctness_numerator"] == 0
    assert overall["selective_correctness_denominator"] == 0
    assert overall["selective_correctness_value"] is None
    assert overall["selective_correctness_ci_lower"] is None
    assert overall["selective_correctness_ci_upper"] is None


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda s, p: s["track_a"]["strata"].pop("severity"), "strata are incomplete"),
        (lambda s, p: s["track_a"]["attempts"][0].pop("method_runtime_ms"), "lacks fields"),
        (lambda s, p: s["track_a"]["attempts"][0].__setitem__("total_runtime_ms", float("nan")), "not finite"),
        (lambda s, p: s["track_a"]["attempts"][0].__setitem__("valid_overlap_fraction", None), "overlap is not numeric"),
        (lambda s, p: p["uncertainty"].__setitem__("z_value", 0), "plan self-hash mismatch"),
        (lambda s, p: p["reporting_contract"]["mandatory_strata"].pop(), "plan self-hash mismatch"),
        (lambda s, p: s["integrity_evidence"].__setitem__("no_post_label_change", False), "Integrity evidence self-hash mismatch"),
        (lambda s, p: s["track_a"]["overall"]["execution_completion_rate"].__setitem__("numerator", 0), "does not reconcile"),
        (lambda s, p: s["track_a"]["pairwise_method_comparisons"][0].__setitem__("mcnemar_exact_two_sided_p", 0.0), "do not reconcile"),
    ],
)
def test_fails_closed_on_missing_malformed_or_unreconciled_evidence(mutate, message):
    module = load_module()
    summary, plan = fixture(module)
    mutate(summary, plan)
    with pytest.raises(module.ReportingError, match=message):
        module.build_tables(summary, plan)


def test_check_detects_table_tampering(tmp_path: Path):
    module = load_module()
    summary, plan = fixture(module)
    summary_path = tmp_path / "summary.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "tables"
    manifest_path = tmp_path / "manifest.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    module.generate_bundle(summary_path, plan_path, output, manifest_path)
    table = output / "track_a_overall.csv"
    table.write_text(table.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    with pytest.raises(module.ReportingError, match="Table hash mismatch"):
        module.check_bundle(summary_path, plan_path, output, manifest_path)


def test_similarity_disagreement_table_reports_unavailable_without_inventing_threshold():
    module = load_module()
    summary, plan = fixture(module)
    rows = module.build_tables(summary, plan)["runtime_failure_similarity.csv"]
    assert rows
    assert all(row["comparison_status"] == "NOT_EVALUABLE_NO_COMMON_THRESHOLD" for row in rows)
    assert all(row["similarity_geometry_comparable"] == 0 for row in rows)
    assert all(row["method_runtime_count"] == row["attempts"] for row in rows)
