from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def read_json(relative: str) -> dict:
    return json.loads(read_text(relative))


def test_readme_reports_scientific_blocker_and_unchanged_outcomes():
    readme = read_text("README.md")
    assert "## Week 8 final evaluation and analysis" in readme
    assert "284/294 completed (96.60%)" in readme
    assert "278/294 met the frozen geometric-success criterion (94.56%)" in readme
    assert "Track B abstained on all 24 eligible pairs" in readme
    assert "NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS" in readme
    assert "policy remains non-deployed" in readme
    assert "invalid for preregistration-conformant confirmatory claims" in readme
    assert "G8 is **BLOCKED**" in readme
    assert "newly reserved, unexposed holdout" in readme
    assert "week08_phase9_scientific_review_finding.json" in readme
    assert "Phase 6 independent-source enrollment is next; Week 8 not run" not in readme
    assert "Planned; blocked pending pre-Week 8 gates" not in readme


def test_reproduction_guide_separates_public_and_authorized_scientific_checks():
    guide = read_text("docs/REPRODUCTION_GUIDE.md")
    assert "## Week 8 archived-run and scientific-review verification" in guide
    assert "### Public or lightweight checkout" in guide
    assert "### Authorized attached sealed evidence" in guide
    assert "tests\\test_week08_phase9_final_analysis.py" in guide
    assert "tests\\test_week08_phase9_scientific_review_audit.py" in guide
    assert "week08_phase9_data_quality_closure.py --check" in guide
    assert "week08_phase9_final_analysis.py --check" in guide
    assert "week08_phase9_scientific_review_audit.py --check" in guide
    assert "do not execute registration or evaluation" in guide
    assert "Never use `week08_prepare_holdout.py`" in guide


def test_maintained_gate_register_is_current_and_g8_is_blocked():
    plan = read_text("docs/PRE_WEEK08_INTEGRATION_PLAN.md")
    assert "ACTIVE PLAN - PHASE 9 SCIENTIFIC REVIEW BLOCKED" in plan
    assert "**Revision date:** 2026-11-16" in plan
    for gate in range(8):
        assert f"| G{gate} " in plan
        gate_row = next(line for line in plan.splitlines() if line.startswith(f"| G{gate} "))
        assert "| PASSED |" in gate_row
    g8_row = next(line for line in plan.splitlines() if line.startswith("| G8 "))
    assert "| BLOCKED |" in g8_row
    assert "policy remains non-deployed" in plan
    assert "newly reserved, unexposed holdout" in plan
    assert "week08_phase9_scientific_review_finding.json" in plan
    assert "no rerun of the exposed holdout, post-label tuning" in plan
    assert "Complete and verify the Phase 9.3" not in plan


def test_progress_registry_tracks_phase9_4_blocker_and_new_cycle_requirement():
    registry = read_json("reports/progress_registry.json")
    week8 = registry["weeks"]["week_08"]
    assert week8["status"] == "blocked"
    assert week8["latest_completed_phase"] == "phase_9_4_scientific_review_finding"
    assert week8["final_run_status"] == "completed_archived_confirmatory_invalid"
    assert week8["confirmatory_status"] == "invalid"
    assert week8["g8_status"] == "blocked"
    assert week8["policy_status"] == "non_deployed"
    assert week8["scientific_review"] == "failed"
    assert week8["human_scientific_attestation"] == "not_recorded"
    assert week8["release_review"] == "blocked_by_scientific_review"
    assert week8["fresh_holdout_required"] is True

    integration = registry["pre_week08_integration"]
    assert integration["phase_9_3_documentation"]["status"] == "complete"
    assert integration["phase_9_3_documentation"]["frozen_methods_changed"] is False
    assert integration["phase_9_3_documentation"]["frozen_policy_changed"] is False
    phase94 = integration["phase_9_4_scientific_review_finding"]
    assert phase94["status"] == "complete_blocking_finding"
    assert phase94["supplement_tables"] == 5
    assert phase94["historical_phase8_phase9_artifacts_modified"] is False
    assert phase94["fresh_holdout_required"] is True
    assert integration["gate_summary"] == {
        **{f"G{gate}": "passed" for gate in range(8)},
        "G8": "blocked",
    }


def test_phase9_documentation_links_resolve_and_historical_manifests_remain_immutable():
    registry = read_json("reports/progress_registry.json")
    week8 = registry["weeks"]["week_08"]
    for field in (
        "release_manifest",
        "data_quality_closure",
        "analysis_manifest",
        "final_analysis",
        "scientific_review_finding",
        "scientific_review_document",
    ):
        assert (ROOT / week8[field]).is_file(), field

    phase93 = registry["pre_week08_integration"]["phase_9_3_documentation"]
    for field in (
        "readme",
        "reproduction_guide",
        "maintained_plan",
        "report_index",
        "progress_registry",
    ):
        assert (ROOT / phase93[field]).is_file(), field

    for relative in (
        "reports/week08_phase9_data_quality_closure.json",
        "reports/week08_phase9_final_analysis.json",
    ):
        report = read_json(relative)
        assert report["status"] == "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW"
        assert report["review"]["scientific_reviewer"]["status"] == "PENDING"
        assert report["review"]["release_reviewer"]["status"] == "PENDING"

    finding = read_json("reports/week08_phase9_scientific_review_finding.json")
    assert finding["status"] == "CONFIRMATORY_RUN_INVALID_IMPLEMENTATION_NONCONFORMANCE"
    assert finding["disposition"]["g8_status"] == "BLOCKED"
    assert finding["review"]["automated_scientific_audit"] == "FAIL"
    assert finding["review"]["named_human_scientific_attestation"] == "NOT_RECORDED"
    assert len(finding["supplement"]["artifacts"]) == 5
    for artifact in finding["supplement"]["artifacts"]:
        assert (ROOT / artifact["path"]).is_file(), artifact["path"]
