from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_r3_cycle_scaffold.py"
SPEC = importlib.util.spec_from_file_location("week08_r3_cycle_scaffold", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_tracked_r3_scaffold_is_zero_access_and_self_hashed() -> None:
    result = MODULE.validate_scaffold(ROOT)

    assert result["status"] == "PASS"
    assert result["fresh_sources"] == 0
    assert result["source_accesses"] == 0
    assert result["evaluation_runs"] == 0


def test_r3_instruction_does_not_invent_human_gate_approvals() -> None:
    record = load("reports/week08_r3_cycle_start.json")
    instruction = record["project_owner_instruction"]

    assert instruction["instruction"] == "Do it"
    assert instruction["role"] == "project_owner_instruction"
    assert not instruction["is_release_reviewer_attestation"]
    assert not instruction["is_data_custodian_attestation"]
    assert not instruction["authorizes_source_access"]
    assert not instruction["authorizes_g5_freeze"]
    assert not instruction["authorizes_g6_enrollment"]
    assert not instruction["authorizes_g7_execution"]


def test_r2_source_is_rejected_by_content_identity_and_lineage() -> None:
    ledger = load("configs/week08_r3_source_use_ledger.json")
    prohibited = ledger["prior_exposed_sources"][0]

    assert prohibited["sha256"] == MODULE.R2_SOURCE_SHA256
    assert prohibited["canonical_source_id"] == "nasa_photojournal:pia18033:suomi_npp_viirs_2012_01_composite"
    assert prohibited["lineage_ancestors"]
    assert prohibited["r3_disposition"] == "permanently_ineligible_for_confirmatory_reuse"
    assert all(value == "reject" for value in ledger["reuse_rejection_rules"].values())


def test_r3_paths_do_not_overlap_r2_evidence_namespaces() -> None:
    record = load("reports/week08_r3_cycle_start.json")
    roots = set(record["output_namespaces"].values())

    assert roots == {
        "outputs/week08_r3_holdout",
        "outputs/week08_r3_final",
        "outputs/week08_r3_archives",
    }
    assert roots.isdisjoint({
        "outputs/week08_holdout",
        "outputs/week08_final",
        "outputs/week08_archives",
    })


def test_scaffold_fails_if_a_source_is_enrolled_early(tmp_path: Path) -> None:
    ledger = load("configs/week08_r3_source_use_ledger.json")
    ledger["fresh_sources"] = [{"source_id": "premature"}]
    fake_root = tmp_path / "repo"
    for relative in (
        "reports/week08_r3_cycle_start.json",
        "configs/week08_r3_source_use_ledger.json",
        "data/manifests/week08_r3_holdout_sources.json",
        "docs/WEEK08_R3_CONFIRMATORY_CYCLE.md",
        "data/holdout/week08_r3/README.md",
    ):
        target = fake_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / relative
        target.write_bytes(source.read_bytes())
    (fake_root / "configs/week08_r3_source_use_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(MODULE.R3ScaffoldError, match="fresh source appeared"):
        MODULE.validate_scaffold(fake_root)
