from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_phase9_final_analysis.py"
MANIFEST = ROOT / "reports/week08_phase9_final_analysis.json"
TABLE_DIR = ROOT / "reports/week08_phase9_tables"
FIGURE_DIR = ROOT / "docs/figures/week08_phase9"
REPORT = ROOT / "docs/WEEK08_FINAL_ANALYSIS.md"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_phase9_final_analysis", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def read_csv(name: str) -> list[dict[str, str]]:
    with (TABLE_DIR / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_manifest_self_hashes_and_keeps_reviews_pending():
    module = load_module()
    manifest = load_manifest()
    assert manifest["schema_version"] == module.SCHEMA_VERSION
    payload = dict(manifest)
    recorded = payload.pop("manifest_payload_sha256")
    assert module.canonical_sha256(payload) == recorded
    assert manifest["status"] == "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW"
    assert manifest["review"] == {
        "developer_analyst": {"status": "COMPLETE"},
        "scientific_reviewer": {"status": "PENDING"},
        "release_reviewer": {"status": "PENDING"},
    }
    assert manifest["claim_scope"]["scope"] == "source_specific_software_evidence_only"
    assert manifest["claim_scope"]["policy_status"] == "non_deployed"
    assert "authorization_id" not in manifest["identity"]
    module.validate_sanitized_file(MANIFEST)
    module.validate_sanitized_file(REPORT)


def test_manifest_binds_exact_sanitized_artifact_set():
    module = load_module()
    manifest = load_manifest()
    outputs = manifest["outputs"]
    assert len(outputs) == 14
    assert {Path(row["path"]).name for row in outputs} == set(
        module.TABLE_FILES + module.FIGURE_FILES
    )
    for row in outputs:
        path = ROOT / row["path"]
        assert path.is_file()
        assert path.stat().st_size == row["size_bytes"]
        assert module.sha256_file(path) == row["sha256"]
        module.validate_sanitized_file(path)


def test_track_a_overall_and_modality_tables_preserve_denominators():
    overall = read_csv("track_a_overall.csv")
    assert len(overall) == 1
    row = overall[0]
    assert (row["attempts"], row["completed"], row["failed"]) == ("294", "284", "10")
    assert row["geometric_successes"] == "278"
    assert row["completion_value"] == "0.965986"
    assert row["geometric_success_value"] == "0.945578"
    assert row["conditional_accuracy_value"] == "0.978873"
    assert row["completion_ci_lower"] == "0.938530"
    assert row["geometric_success_ci_lower"] == "0.913435"
    assert row["conditional_accuracy_ci_lower"] == "0.954682"

    modality = {row["scope"]: row for row in read_csv("track_a_by_modality.csv")}
    assert set(modality) == {"monomodal", "simulated_multimodal"}
    assert (modality["monomodal"]["attempts"], modality["monomodal"]["completed"], modality["monomodal"]["geometric_successes"]) == ("240", "230", "227")
    assert (modality["simulated_multimodal"]["attempts"], modality["simulated_multimodal"]["completed"], modality["simulated_multimodal"]["geometric_successes"]) == ("54", "54", "51")
    assert (modality["monomodal"]["completion_ci_lower"], modality["monomodal"]["geometric_success_ci_lower"], modality["monomodal"]["conditional_accuracy_ci_lower"]) == ("0.925012", "0.909544", "0.962359")
    assert (modality["monomodal"]["runtime_median_ms"], modality["monomodal"]["runtime_p95_ms"]) == ("69.531200", "451.567820")
    assert (modality["simulated_multimodal"]["runtime_median_ms"], modality["simulated_multimodal"]["runtime_p95_ms"]) == ("334.363300", "551.043995")


def test_condition_runtime_and_repeated_pattern_tables_are_complete():
    conditions = {row["scope"]: row for row in read_csv("track_a_by_condition.csv")}
    assert len(conditions) == 9
    repeated = conditions["repeated_pattern"]
    assert (repeated["attempts"], repeated["completed"], repeated["failed"], repeated["geometric_successes"]) == ("36", "26", "10", "25")
    assert repeated["completion_value"] == "0.722222"
    assert repeated["geometric_success_value"] == "0.694444"
    perfect = {"none", "gaussian_noise", "gaussian_blur", "illumination", "low_texture"}
    assert all(conditions[name]["completed"] == "36" and conditions[name]["geometric_successes"] == "36" for name in perfect)
    assert (conditions["occlusion"]["completed"], conditions["occlusion"]["geometric_successes"]) == ("36", "34")
    assert (conditions["partial_overlap"]["completed"], conditions["partial_overlap"]["geometric_successes"]) == ("36", "33")
    assert (conditions["multimodal_mapping"]["completed"], conditions["multimodal_mapping"]["geometric_successes"]) == ("6", "6")

    runtime = read_csv("track_a_runtime_by_method.csv")
    assert len(runtime) == 11
    assert runtime[0]["method_id"] == "overall"
    assert all(row["runtime_scope"] == "total_runtime_ms" for row in runtime)
    assert all(row["uncertainty_note"] == "distribution_summary_not_confidence_interval" for row in runtime)
    runtime_expected = {
        "phase_translation": ("27.584050", "40.383440"),
        "ecc_translation": ("52.034900", "126.704335"),
        "ecc_rigid": ("57.236050", "129.151145"),
        "ecc_affine": ("60.432650", "162.744280"),
        "orb_similarity": ("59.706800", "75.775885"),
        "sift_similarity": ("78.023350", "102.159555"),
        "orb_affine": ("56.831650", "84.069470"),
        "sift_affine": ("83.824350", "105.058405"),
        "mi_rigid_2d": ("270.767200", "502.041000"),
        "mi_affine_2d": ("371.981300", "616.036800"),
    }
    runtime_by_method = {row["method_id"]: row for row in runtime}
    assert {
        method: (runtime_by_method[method]["runtime_median_ms"], runtime_by_method[method]["runtime_p95_ms"])
        for method in runtime_expected
    } == runtime_expected

    repeated_methods = read_csv("repeated_pattern_by_method.csv")
    assert sum(int(row["attempts"]) for row in repeated_methods) == 36
    assert sum(int(row["geometric_successes"]) for row in repeated_methods) == 25
    assert sum(int(row["completed_geometric_failures"]) for row in repeated_methods) == 1
    assert sum(int(row["execution_failures"]) for row in repeated_methods) == 10
    assert sum(int(row["insufficient_filtered_matches"]) for row in repeated_methods) == 6
    assert sum(int(row["insufficient_ransac_inliers"]) for row in repeated_methods) == 4


def test_similarity_geometry_audit_reports_unavailability_not_zero_disagreement():
    rows = read_csv("similarity_geometry_availability.csv")
    common = {
        row["evidence_field"]: row
        for row in rows
        if row["category"] in {"common_image_similarity", "common_support"}
    }
    assert set(common) == {"mae", "mse", "ncc", "ssim", "mi_nats", "valid_overlap_fraction"}
    for row in common.values():
        assert row["available_count"] == "0"
        assert row["denominator"] == "294"
        assert row["comparison_status"] == "NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS"
    geometry = {row["evidence_field"]: row for row in rows}
    assert geometry["valid_geometric_reference"]["available_count"] == "294"
    assert geometry["tre_mean_px"]["available_count"] == "284"
    family_native = [row for row in rows if row["category"] == "family_specific_raw_diagnostic"]
    assert sum(int(row["available_count"]) for row in family_native) == 294
    assert {row["evidence_field"]: row["available_count"] for row in family_native} == {
        "ecc_final_ecc": "72",
        "mi_final_metric_value": "102",
        "phase_response": "24",
        "feature_ransac_inlier_ratio": "96",
    }
    assert all(row["comparison_status"] == "NONCOMMENSURATE_NOT_COMPARED" for row in family_native)


def test_track_b_table_reports_full_abstention_and_undefined_selective_correctness():
    rows = read_csv("track_b_policy.csv")
    assert len(rows) == 9
    overall = rows[0]
    assert overall["scope"] == "overall"
    assert (overall["eligible_pairs"], overall["selected_pairs"], overall["abstained_pairs"]) == ("24", "0", "24")
    assert overall["coverage_value"] == "0.000000"
    assert overall["abstention_value"] == "1.000000"
    assert overall["selective_correctness_value"] == "NA"
    assert overall["coverage_ci_upper"] == "0.137981"
    assert overall["abstention_ci_lower"] == "0.862019"
    strata = {row["scope"]: row for row in rows[1:]}
    assert set(strata) == {"none", "gaussian_noise", "gaussian_blur", "illumination", "occlusion", "partial_overlap", "low_texture", "repeated_pattern"}
    assert all(row["eligible_pairs"] == "3" and row["selected_pairs"] == "0" and row["abstained_pairs"] == "3" for row in strata.values())


def test_figures_are_vector_only_and_parse_as_svg():
    for name in (
        "track_a_overall_rates.svg",
        "track_a_modality_rates.svg",
        "track_a_condition_rates.svg",
        "track_a_runtime_by_method.svg",
        "repeated_pattern_outcomes.svg",
        "similarity_geometry_availability.svg",
        "track_b_policy.svg",
    ):
        path = FIGURE_DIR / name
        root = ElementTree.parse(path).getroot()
        assert root.tag.endswith("svg")
        assert not any(element.tag.endswith("image") for element in root.iter())


@pytest.mark.skipif(
    not (ROOT / "outputs/week08_final/evaluation_summary.json").is_file(),
    reason="private Week 8 evidence is not attached",
)
def test_bundle_rebuilds_byte_for_byte_from_attached_sealed_evidence():
    module = load_module()
    verified = module.verify_bundle(ROOT, MANIFEST)
    assert verified["manifest_payload_sha256"] == load_manifest()["manifest_payload_sha256"]
