from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def read_json(relative: str) -> dict:
    return json.loads(read_text(relative))


def test_readme_reports_current_week08_state_without_old_current_blockers():
    readme = read_text("README.md")
    assert "## Week 8 final evaluation and analysis" in readme
    assert "284/294 completed (96.60%)" in readme
    assert "278/294 met the frozen geometric-success criterion (94.56%)" in readme
    assert "Track B abstained on all 24 eligible pairs" in readme
    assert "NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS" in readme
    assert "policy remains non-deployed" in readme
    assert "Phase 6 independent-source enrollment is next; Week 8 not run" not in readme
    assert "Planned; blocked pending pre-Week 8 gates" not in readme


def test_reproduction_guide_separates_public_and_authorized_checks():
    guide = read_text("docs/REPRODUCTION_GUIDE.md")
    assert "## Week 8 final-analysis verification" in guide
    assert "### Public or lightweight checkout" in guide
    assert "### Authorized attached sealed evidence" in guide
    assert "tests\\test_week08_phase9_final_analysis.py" in guide
    assert "week08_phase9_data_quality_closure.py --check" in guide
    assert "week08_phase9_final_analysis.py --check" in guide
    assert "do not execute registration or evaluation" in guide
    assert "Never use `week08_prepare_holdout.py`" in guide


def test_maintained_gate_register_is_current_and_g8_remains_open():
    plan = read_text("docs/PRE_WEEK08_INTEGRATION_PLAN.md")
    assert "ACTIVE PLAN - PHASE 9 RELEASE CLOSURE IN PROGRESS" in plan
    assert "**Revision date:** 2026-11-16" in plan
    for gate in range(8):
        assert f"| G{gate} " in plan
        gate_row = next(line for line in plan.splitlines() if line.startswith(f"| G{gate} "))
        assert "| PASSED |" in gate_row
    g8_row = next(line for line in plan.splitlines() if line.startswith("| G8 "))
    assert "| IN PROGRESS |" in g8_row
    assert "policy remains non-deployed" in plan
    assert "No new run, post-label tuning" in plan
    assert "Complete and verify the Phase 9.3" not in plan


def test_progress_registry_tracks_phase9_3_and_pending_g8_reviews():
    registry = read_json("reports/progress_registry.json")
    week8 = registry["weeks"]["week_08"]
    assert week8["status"] == "in_progress"
    assert week8["latest_completed_phase"] == "phase_9_3_documentation"
    assert week8["final_run_status"] == "completed_archived"
    assert week8["g8_status"] == "in_progress"
    assert week8["policy_status"] == "non_deployed"
    assert week8["scientific_review"] == "pending"
    assert week8["release_review"] == "pending"

    integration = registry["pre_week08_integration"]
    assert integration["phase_9_3_documentation"]["status"] == "complete"
    assert integration["phase_9_3_documentation"]["frozen_methods_changed"] is False
    assert integration["phase_9_3_documentation"]["frozen_policy_changed"] is False
    assert integration["gate_summary"] == {
        **{f"G{gate}": "passed" for gate in range(8)},
        "G8": "in_progress",
    }


def test_phase9_documentation_links_resolve_and_reviews_remain_pending():
    registry = read_json("reports/progress_registry.json")
    week8 = registry["weeks"]["week_08"]
    for field in (
        "release_manifest",
        "data_quality_closure",
        "analysis_manifest",
        "final_analysis",
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
