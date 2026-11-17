from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_r3_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_r3_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r3_candidate_boundary_is_static_zero_access_and_private() -> None:
    report = load_module().validate_candidate(ROOT)

    assert report["readiness"] == "PASS"
    assert report["mode"] == "g5_candidate"
    assert not report["source_or_label_decoded"]
    assert not report["week08_evaluation_executed"]
    assert all(item["status"] == "PASS" for item in report["checks"])


def test_r3_final_readiness_fails_closed_before_g5_g6_g7() -> None:
    module = load_module()
    report = module.run_preflight(ROOT, require_g7=True)

    assert report["readiness"] == "BLOCK"
    assert report["mode"] == "final_readiness"
    assert not report["source_or_label_decoded"]
    blockers = {
        item["check"]
        for item in report["checks"]
        if item["status"] == "BLOCK"
    }
    assert {
        "r3_g5_release_manifest",
        "r3_g6_fresh_source_enrollment",
        "r3_g7_one_run_authorization",
    }.issubset(blockers)


def test_r3_technical_readiness_defers_only_the_human_g7_check() -> None:
    report = load_module().run_preflight(ROOT, require_g7=False)
    authorization = next(
        item for item in report["checks"]
        if item["check"] == "r3_g7_one_run_authorization"
    )

    assert report["mode"] == "technical_readiness"
    assert authorization["status"] == "DEFER"
    assert report["readiness"] == "BLOCK"  # G5 and G6 do not exist yet.


def test_safe_file_rejects_escape_and_windows_absolute_paths(tmp_path: Path) -> None:
    module = load_module()

    assert module.safe_file(tmp_path, "../escape") is None
    assert module.safe_file(tmp_path, "/absolute") is None
    assert module.safe_file(tmp_path, "C:/absolute") is None
    assert module.safe_file(tmp_path, "safe/path.json") == tmp_path / "safe/path.json"


def test_pending_release_record_cannot_claim_human_or_later_gate_approval() -> None:
    module = load_module()
    record = {field: None for field in module.EXPECTED_RELEASE_FIELDS}
    record.update({
        "schema_version": module.RELEASE_SCHEMA,
        "cycle_id": module.CYCLE_ID,
        "release_id": "pre-week08-g5r3-20261117",
        "gate": "G5",
        "status": "R3_REVIEW_PENDING",
        "proposed_release_tag": "pre-week08-g5r3-20261117",
        "release_commit": None,
        "release_tag": None,
        "required_signoffs_complete": False,
        "reviewer": {
            "requested_reviewer": "Md Moshiur Rahman",
            "name": None,
            "role": "release reviewer",
            "decision": "PENDING",
            "attested_utc": None,
        },
        "post_release_metadata_allowlist": sorted(module.POST_G5_METADATA_ALLOWLIST),
        "g6_enrollment": {
            "status": "BLOCKED_PENDING_G5_AND_FRESH_SOURCE",
            "reviewed_commit": None,
            "source_ids": [],
            "source_ledger_sha256": None,
            "holdout_manifest_sha256": None,
            "source_registration_sha256": None,
        },
        "g7_authorization": {
            "status": "BLOCKED_PENDING_G5_G6",
            "authorization_id": None,
            "authorization_sha256": None,
        },
        "final_readiness": {
            "authorized": False,
            "release_reviewer_approval_pending": True,
            "expected_remaining_blocks": ["G5", "G6", "G7"],
            "week08_benchmark_executed": False,
            "real_week08_pixels_accessed": False,
            "real_week08_labels_accessed": False,
        },
        "activity_counters": {
            "fresh_sources_enrolled": 0,
            "source_bytes_decoded": 0,
            "labels_accessed": 0,
            "registration_attempts": 0,
            "policy_decisions": 0,
            "evaluation_runs": 0,
        },
    })
    assert module._pending_release_record_errors(record) == []

    record["reviewer"]["decision"] = "APPROVED"
    assert any(
        "unapproved" in error
        for error in module._pending_release_record_errors(record)
    )


def test_strict_readiness_bridge_propagates_named_blockers(monkeypatch) -> None:
    from scripts import week08_prepare_holdout as prepare
    import scripts.week08_r3_preflight as preflight

    monkeypatch.setattr(preflight, "run_preflight", lambda *_a, **_k: {
        "readiness": "BLOCK",
        "checks": [
            {"check": "r3_g7_one_run_authorization", "status": "BLOCK"},
            {"check": "r3_predecode_output_boundary", "status": "PASS"},
        ],
    })

    with pytest.raises(ValueError, match="r3_g7_one_run_authorization"):
        prepare.require_strict_final_readiness(prepare.R3_CONFIG)
