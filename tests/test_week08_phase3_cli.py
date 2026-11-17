"""Direct Phase 3 CLI and final-preparation contract tests.

These tests use metadata and tiny synthetic development fixtures only.  They do
not enroll, decode, or inspect any real Week 8 source or label.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from image_registration.week8_evaluation import (
    Week8MethodSpec,
    Week8PairSpec,
    Week8Paths,
    build_week8_plan,
    canonical_sha256,
    enumerate_week8_tasks,
    sha256_file,
)
from scripts import week08_final_evaluation as final_cli
from scripts import week08_prepare_holdout as prepare_cli


def _technical_source(path: str = "outputs/test-fixtures/technical.png") -> dict:
    return {
        "source_id": "technical-source",
        "canonical_source_id": "test:technical-source",
        "canonical_dataset_id": "test:dataset",
        "canonical_subject_id": "test:subject",
        "canonical_case_id": "test:case",
        "canonical_acquisition_id": "test:acquisition",
        "path": path,
        "sha256": "1" * 64,
        "format": "png",
        "modality": "visible",
        "role": "real_technical_only",
        "previously_used": True,
        "prior_usage": ["development-only contract fixture"],
        "reference_or_license": "development-only generated metadata",
        "lineage_ancestors": ["test:technical-source"],
        "lineage_evidence": {"manifest_path": "test", "manifest_sha256": "2" * 64},
        "lineage_status": "development_fixture",
        "ground_truth": {"type": "unavailable", "reason": "technical-only fixture"},
    }


def _technical_row(**changes) -> dict:
    value = {
        "pair_id": "technical-pair",
        "case_id": "technical-case",
        "source_id": "technical-source",
        "fixed_source_id": "technical-source",
        "moving_source_id": "technical-source",
        "modality_class": "monomodal",
        "transform_model": "affine",
        "dimensions": 2,
        "ground_truth_type": "unavailable",
    }
    value.update(changes)
    return value


def _write_enrollment(tmp_path: Path, config: dict, *, row: dict | None = None) -> tuple[dict, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = _technical_source()
    ledger = {
        "schema_version": config["sources"]["required_ledger_schema_version"],
        "week08_sources": [source],
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    manifest = {
        "schema_version": config["sources"]["enrollment_manifest_schema_version"],
        "release_id": "development-contract-test",
        "ledger_sha256": sha256_file(ledger_path),
        "source_ids": [source["source_id"]],
        "pairs": [_technical_row() if row is None else row],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["sources"]["ledger_path"] = str(ledger_path)
    config["sources"]["enrollment_manifest_path"] = str(manifest_path)
    return ledger, manifest


def test_unique_yaml_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("schema_version: one\nschema_version: two\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        final_cli.load_yaml(path)


def test_final_mode_rejects_an_alternate_config_before_reading_it(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate.yaml"
    with pytest.raises(ValueError, match="canonical preregistered config"):
        final_cli.load_protocol(alternate, development=False)


def test_r2_final_is_closed_and_r3_is_blocked_before_g7() -> None:
    with pytest.raises(ValueError, match="R2 holdout is exposed"):
        final_cli.load_protocol(final_cli.DEFAULT_CONFIG, development=False)
    with pytest.raises(ValueError, match="blocked until renewed G5, G6, and G7"):
        final_cli.load_protocol(final_cli.R3_CONFIG, development=False)


def test_r3_development_plan_uses_v2_contract_and_separate_namespaces() -> None:
    _, config, plan, _pairs, _methods = final_cli.build_development_plan(
        final_cli.R3_CONFIG
    )
    assert config["state"] == "r3_g3_remediation_in_progress_no_source_access"
    assert plan["schema_version"] == "week08_evaluation_plan_v2"
    assert plan["uncertainty"]["z_value"] == config["uncertainty"]["z_value"]
    assert plan["reporting_contract"] == config["reporting_enforcement"]
    assert config["artifact_paths"]["final_prepare_root"] == "outputs/week08_r3_holdout"
    assert config["artifact_paths"]["final_decision_root"] == "outputs/week08_r3_final"


def test_final_layout_is_exact_disjoint_and_non_nested() -> None:
    config = final_cli.load_yaml(final_cli.DEFAULT_CONFIG)
    paths = final_cli.final_paths(config)
    assert paths.prepared != paths.root
    assert paths.prepared not in paths.root.parents
    assert paths.root not in paths.prepared.parents
    tampered = deepcopy(config)
    tampered["artifact_paths"]["final_prepare_root"] = tampered["artifact_paths"]["final_decision_root"]
    with pytest.raises(ValueError, match="disjoint"):
        final_cli.final_paths(tampered)
    tampered = deepcopy(config)
    tampered["artifact_paths"]["final"]["observable_manifest"] = "outputs/elsewhere.json"
    with pytest.raises(ValueError, match="derived layout"):
        final_cli.final_paths(tampered)


def test_manifest_cannot_override_gt_or_policy_eligibility(tmp_path: Path) -> None:
    config = final_cli.load_yaml(final_cli.DEFAULT_CONFIG)
    _write_enrollment(tmp_path, config)
    ledger, manifest = final_cli.load_final_enrollment(config)
    methods = final_cli.development_methods(config)
    pairs = final_cli.final_pairs(config, ledger, manifest, methods)
    assert len(pairs) == 1
    assert pairs[0].policy_eligible is False
    assert "path" not in pairs[0].metadata
    assert "label" not in pairs[0].metadata

    config = final_cli.load_yaml(final_cli.DEFAULT_CONFIG)
    _write_enrollment(tmp_path / "override", config, row=_technical_row(policy_eligible=True))
    with pytest.raises(ValueError, match="policy eligibility|unregistered"):
        final_cli.load_final_enrollment(config)

    config = final_cli.load_yaml(final_cli.DEFAULT_CONFIG)
    _write_enrollment(
        tmp_path / "gt-override",
        config,
        row=_technical_row(ground_truth_type="verified_masks"),
    )
    with pytest.raises(ValueError, match="ground-truth type"):
        final_cli.load_final_enrollment(config)


def test_final_plan_path_with_empty_enrollment_is_metadata_only(monkeypatch) -> None:
    calls = 0

    def forbidden_decode(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("final metadata planning decoded an image")

    monkeypatch.setattr(prepare_cli, "load_image", forbidden_decode)
    with pytest.raises((FileNotFoundError, ValueError)):
        final_cli.build_final_plan(final_cli.DEFAULT_CONFIG)
    assert calls == 0


def test_unapproved_final_prepare_blocks_before_any_side_effect(
    tmp_path: Path, monkeypatch,
) -> None:
    paths = Week8Paths.final_layout(
        holdout_root=tmp_path / "holdout",
        final_root=tmp_path / "final",
    )
    calls: list[str] = []

    def blocked_readiness(*_args, **_kwargs):
        calls.append("strict_readiness")
        raise ValueError(
            "Strict final readiness did not pass; no final source was decoded. "
            "Blocking checks: strict_phase7_authorization"
        )

    def forbidden(name):
        def stop(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"unapproved preparation reached {name}")
        return stop

    monkeypatch.setattr(
        prepare_cli, "load_protocol",
        lambda *_a, **_k: (final_cli.DEFAULT_CONFIG, {"test": True}),
    )
    monkeypatch.setattr(prepare_cli, "require_strict_final_readiness", blocked_readiness)
    monkeypatch.setattr(prepare_cli, "final_paths", forbidden("final_paths"))
    monkeypatch.setattr(prepare_cli, "load_final_enrollment", forbidden("enrollment"))
    monkeypatch.setattr(prepare_cli, "_atomic_json", forbidden("write"))
    monkeypatch.setattr(prepare_cli, "load_image", forbidden("decode"))

    with pytest.raises(ValueError, match="strict_phase7_authorization"):
        prepare_cli.make_final_artifacts(final_cli.DEFAULT_CONFIG)
    assert calls == ["strict_readiness"]
    assert not paths.root.exists()
    assert not paths.prepared.exists()


def test_receipt_and_plan_are_persisted_before_first_decode(tmp_path: Path, monkeypatch) -> None:
    holdout = tmp_path / "holdout"
    final = tmp_path / "final"
    paths = Week8Paths.final_layout(holdout_root=holdout, final_root=final)
    source_file = tmp_path / "synthetic-source.bin"
    source_file.write_bytes(b"development-only-source")
    source = {
        **_technical_source(source_file.as_posix()),
        "source_id": "synthetic-source",
        "sha256": sha256_file(source_file),
        "role": "full_project_independent",
        "previously_used": False,
        "prior_usage": [],
        "ground_truth": {"type": "synthetic_created_after_freeze"},
    }
    pair = Week8PairSpec(
        pair_id="synthetic-pair",
        source_id="synthetic-source",
        source_sha256=source["sha256"],
        case_id="synthetic-case",
        geometry_seed=1,
        evaluation_role="independent_known_gt",
        source_role="full_project_independent",
        modality_class="monomodal",
        transform_model="affine",
        condition="none",
        severity="baseline",
        ground_truth_type="synthetic_created_after_freeze",
        metadata={"source_record_sha256": canonical_sha256(source)},
    )
    method = Week8MethodSpec(
        method_id="method",
        config_id="config",
        method_family="intensity_based",
        method_config_sha256="3" * 64,
        supported_transform_models=("affine",),
        supported_modality_classes=("monomodal",),
    )
    plan = build_week8_plan(
        enumerate_week8_tasks([pair], [method]),
        config_sha256="4" * 64,
        method_catalog_sha256="5" * 64,
        policy_sha256="6" * 64,
        code_sha256="7" * 64,
        mode="development_rehearsal",
    )
    config = {
        "task_matrix": {"known_gt_synthetic_cross_product": {"image_shape": [16, 16]}},
    }
    ledger = {"week08_sources": [source]}
    manifest = {"pairs": []}

    monkeypatch.setattr(prepare_cli, "load_protocol", lambda *_a, **_k: (final_cli.DEFAULT_CONFIG, config))
    monkeypatch.setattr(prepare_cli, "require_strict_final_readiness", lambda *_a: {
        "readiness": "PASS",
        "mode": "final_readiness",
        "phase7_authorization_required": True,
        "checks": [{"check": "strict_phase7_authorization", "status": "PASS"}],
    })
    monkeypatch.setattr(prepare_cli, "final_paths", lambda _config: paths)
    monkeypatch.setattr(prepare_cli, "load_final_enrollment", lambda _config: (ledger, manifest))
    monkeypatch.setattr(prepare_cli, "_final_readiness_receipt", lambda *_a: {
        "schema_version": "test",
        "release_manifest_sha256": "8" * 64,
        "phase7_authorization_sha256": "9" * 64,
        "phase7_authorization_id": "g7-test-approval",
        "receipt_sha256": "a" * 64,
    })
    monkeypatch.setattr(prepare_cli, "verify_final_readiness_receipt", lambda *_a: {})
    monkeypatch.setattr(
        prepare_cli,
        "build_final_plan",
        lambda *_a, **_k: (final_cli.DEFAULT_CONFIG, config, plan, [pair], [method]),
    )
    monkeypatch.setattr(
        prepare_cli,
        "prevalidate_final_inputs",
        lambda *_a: ({"synthetic-source": source}, {}),
    )
    monkeypatch.setattr(
        prepare_cli,
        "_verified_file",
        lambda _path, _sha256: source_file,
    )

    class DecodeReached(RuntimeError):
        pass

    def stop_at_decode(*_args, **_kwargs):
        assert paths.final_readiness_receipt.is_file()
        assert paths.plan.is_file()
        receipt = json.loads(paths.final_readiness_receipt.read_text(encoding="utf-8"))
        assert receipt["release_manifest_sha256"] == "8" * 64
        assert receipt["phase7_authorization_sha256"] == "9" * 64
        assert receipt["phase7_authorization_id"] == "g7-test-approval"
        raise DecodeReached

    monkeypatch.setattr(prepare_cli, "load_image", stop_at_decode)
    with pytest.raises(DecodeReached):
        prepare_cli.make_final_artifacts(final_cli.DEFAULT_CONFIG)


def test_final_readiness_receipt_binds_release_manifest_and_authorization(
    tmp_path: Path, monkeypatch,
) -> None:
    config_path = tmp_path / "week08.yaml"
    config_path.write_text("schema_version: test\n", encoding="utf-8")
    release_path = tmp_path / "release.json"
    authorization_path = tmp_path / "authorization.json"
    ledger_path = tmp_path / "ledger.json"
    enrollment_path = tmp_path / "enrollment.json"
    registration_path = tmp_path / "reports/pre_week08_source_registration.json"
    registration_path.parent.mkdir(parents=True)
    release_path.write_text(json.dumps({"release_id": "r2"}), encoding="utf-8")
    authorization = {
        "authorization_id": "g7-r2",
        "release": {"release_commit": "a" * 40, "release_tag": "r2-tag"},
    }
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    ledger_path.write_text(json.dumps({"week08_sources": []}), encoding="utf-8")
    enrollment_path.write_text(json.dumps({"source_ids": []}), encoding="utf-8")
    registration_path.write_text(json.dumps({"status": "test"}), encoding="utf-8")
    config = {
        "safety": {
            "phase7_authorization": {
                "release_manifest_path": str(release_path),
                "authorization_path": str(authorization_path),
            },
        },
        "sources": {
            "ledger_path": str(ledger_path),
            "enrollment_manifest_path": str(enrollment_path),
        },
        "frozen_assets": {
            "method_catalog": {"sha256": "1" * 64},
            "policy": {"sha256": "2" * 64},
        },
    }
    report = {
        "readiness": "PASS",
        "mode": "final_readiness",
        "phase7_authorization_required": True,
        "checks": [{"check": "strict_phase7_authorization", "status": "PASS"}],
    }
    payload = {
        "schema_version": final_cli.FINAL_READINESS_RECEIPT_VERSION,
        "readiness": "PASS",
        "config_sha256": sha256_file(config_path),
        "runner_code_sha256": "3" * 64,
        "release_manifest_sha256": sha256_file(release_path),
        "phase7_authorization_sha256": sha256_file(authorization_path),
        "phase7_authorization_id": "g7-r2",
        "release_commit": "a" * 40,
        "release_tag": "r2-tag",
        "source_ledger_sha256": sha256_file(ledger_path),
        "enrollment_manifest_sha256": sha256_file(enrollment_path),
        "source_registration_sha256": sha256_file(registration_path),
        "method_catalog_sha256": "1" * 64,
        "policy_sha256": "2" * 64,
        "preflight_report": report,
        "preflight_report_sha256": canonical_sha256(report),
        "week08_evaluation_executed": False,
        "real_week08_source_or_label_decoded": False,
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(final_cli, "ROOT", tmp_path)
    monkeypatch.setattr(final_cli, "DEFAULT_CONFIG", config_path)
    monkeypatch.setattr(final_cli, "runner_code_sha256", lambda _config: "3" * 64)
    assert final_cli.verify_final_readiness_receipt(config, receipt_path)[
        "phase7_authorization_id"
    ] == "g7-r2"

    release_path.write_text(json.dumps({"release_id": "tampered"}), encoding="utf-8")
    with pytest.raises(ValueError, match="release_manifest_sha256 mismatch"):
        final_cli.verify_final_readiness_receipt(config, receipt_path)
    release_path.write_text(json.dumps({"release_id": "r2"}), encoding="utf-8")
    authorization_path.write_text(json.dumps({**authorization, "decision": "tampered"}), encoding="utf-8")
    with pytest.raises(ValueError, match="phase7_authorization_sha256 mismatch"):
        final_cli.verify_final_readiness_receipt(config, receipt_path)


def test_recommendation_criteria_are_loaded_from_preregistration() -> None:
    config = final_cli.load_yaml(final_cli.DEFAULT_CONFIG)
    criteria = final_cli.recommendation_criteria(config)
    assert criteria["minimum_selected_pairs"] == 20
    assert criteria["minimum_selective_correctness"] == pytest.approx(0.95)
    assert criteria["minimum_distinct_independent_sources_for_broad_support"] == 3
    assert criteria["broad_support_requires_real_verified_gt"] is True


def test_estimated_transform_diagnostics_are_disambiguated_without_hiding_gt() -> None:
    raw = {
        "levels": [{"moving_to_fixed": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}],
        "fixed_to_moving": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "ground_truth_transform": "must remain visible to the core firewall",
    }
    renamed = final_cli._disambiguate_estimated_diagnostics(raw)
    assert "moving_to_fixed" not in renamed["levels"][0]
    assert "estimated_moving_to_fixed" in renamed["levels"][0]
    assert "estimated_fixed_to_moving" in renamed
    assert renamed["ground_truth_transform"] == raw["ground_truth_transform"]


def test_observable_executor_captures_method_runtime_and_geometric_overlap(monkeypatch) -> None:
    matrix = np.array(
        [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    run = SimpleNamespace(
        run_status=SimpleNamespace(value="completed"),
        transform=SimpleNamespace(matrix=matrix, plausible=True),
        metrics=SimpleNamespace(after={"ncc": 0.8, "mae": 1.25}),
        diagnostics=SimpleNamespace(values={}),
        runtime_seconds=0.0125,
        warnings=(),
        failure_reason=None,
    )
    service = SimpleNamespace(run=lambda _request: run)
    monkeypatch.setattr(
        "ui.adapters.build_default_registration_service",
        lambda: service,
    )
    spec = Week8MethodSpec(
        method_id="ecc_affine_2d",
        config_id="r3-test-config",
        method_family="intensity_based",
        method_config_sha256="a" * 64,
        supported_transform_models=("affine",),
        supported_modality_classes=("monomodal",),
        method_seed=7,
        metadata={"parameters": {}},
    )
    execute = final_cli.observable_executor([spec])
    view = {
        "pair_id": "synthetic-pair",
        "method_id": spec.method_id,
        "config_id": spec.config_id,
        "method_family": spec.method_family,
        "transform_model": "affine",
        "modality_class": "monomodal",
        "dimensions": 2,
        "method_seed": 7,
        "experiment_id": "w8-synthetic",
    }
    observable = {
        "fixed": np.zeros((4, 4), dtype=np.uint8),
        "moving": np.zeros((4, 4), dtype=np.uint8),
    }
    result = execute(view, observable)
    expected_support = final_cli.transformed_support_mask(
        observable["moving"].shape,
        matrix,
        destination_shape=(4, 4),
    )
    assert result["timings_ms"]["registration"] == pytest.approx(12.5)
    assert result["timings_ms"]["total"] >= 0.0
    assert result["valid_overlap_fraction"] == final_cli.overlap_fraction(expected_support)
    assert 0.0 <= result["valid_overlap_fraction"] <= 1.0
    assert result["similarity_metrics"]["ncc"] == pytest.approx(0.8)
    assert result["similarity_metrics"]["mae"] == pytest.approx(1.25)
