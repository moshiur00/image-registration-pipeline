"""Week 8 preflight: metadata and frozen-evidence checks ONLY.

This command never invokes registration, decodes image/label content, or
evaluates held-out results. It may hash enrolled bytes without interpreting
them. BLOCK means the final run must not start.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
from typing import Any

import yaml

VERSION = "pre_week08_preflight_v3"
BASELINE_VERSION = "pre_week08_stage_a_v1"
EXPECTED_FROZEN_FILES = 101
EXPECTED_EVIDENCE_FILES = 81
PHASE1_COMMIT = "0ff4371419f5f6dd436e6b0ff33134e3e7946ebc"
KNOWN_PRIOR_INVENTORY_SHA256 = "7bb4acbaa42c0c57e3f61dbe684ad275d313b3a3426ef7725082abbe8b214359"
REPORT_REL = Path("outputs/week08_preflight/preflight_report.json")
FROZEN_REL = Path("configs/week08_frozen_baseline.json")
LEDGER_REL = Path("configs/week08_source_use_ledger.json")
INTEGRITY_ANCHOR_REL = Path("configs/week08_integrity_anchor.json")
EVIDENCE_ARCHIVE_MANIFEST_REL = Path("reports/week07_evidence_archive_manifest.json")
EVIDENCE_ARCHIVE_REL = Path("deliverables/week07_frozen_evidence.zip")
HANDOFF_REL = Path("reports/week07_day05_week08_handoff.json")
CLOSURE_REL = Path("reports/week07_week_closure.json")
GENERAL_SOURCES_REL = Path("data/manifests/general_real_sources.json")
RIRE_SOURCES_REL = Path("data/manifests/rire_training001.json")
PROTECTED = (
    "outputs/week07_day02_full/",
    "outputs/week07_day03_analysis/",
    "outputs/week07_day04_calibration/",
    "outputs/week07_day05_integration/",
)
SUPPORTED_IMAGE_FORMATS = {
    "png", "jpg", "jpeg", "bmp", "tif", "tiff", "mha", "mhd", "nii", "nii.gz", "nrrd"
}
LANDMARK_FORMATS = {"csv", "tsv", "json"}
SOURCE_ROLES = {"development", "policy_transfer_check", "real_technical_only", "full_project_independent"}
GROUND_TRUTH_TYPES = {"synthetic_created_after_freeze", "verified_landmarks", "verified_masks", "unavailable"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")

FINAL_RUNNER_PATHS = (
    "configs/week08_final_evaluation.yaml",
    "docs/WEEK08_EVALUATION_PREREGISTRATION.md",
    "scripts/week08_prepare_holdout.py",
    "scripts/week08_final_evaluation.py",
    "src/image_registration/week8_evaluation.py",
    "tests/test_week08_final_evaluation.py",
    "tests/test_week08_phase3_cli.py",
)
PHASE3_EVALUATOR_REPORT_REL = Path("reports/pre_week08_phase3_evaluator.json")
PHASE3_EVALUATOR_REPORT_VERSION = "pre_week08_phase3_evaluator_v1"
PHASE3_EVALUATOR_HASH_PATHS = (
    *FINAL_RUNNER_PATHS,
    "scripts/week08_preflight.py",
    "tests/test_week08_preflight.py",
)
WEEK08_EVALUATION_CONFIG_VERSION = "week08_final_evaluation_v1"
WEEK08_RUNNER_PROBE_VERSION = "week08_runner_contract_probe_v1"
RELEASE_MANIFEST_REL = Path("reports/pre_week08_release_manifest.json")
VALIDATION_REL = Path("reports/pre_week08_validation.json")
RELEASE_CHECKLIST_REL = Path("docs/PRE_WEEK08_RELEASE_CHECKLIST.md")
STAGE_B_VALIDATION_REL = Path("reports/pre_week08_stage_b_validation.json")
SOURCE_REGISTRATION_REL = Path("reports/pre_week08_source_registration.json")
HOLDOUT_SOURCE_MANIFEST_REL = Path("data/manifests/week08_holdout_sources.json")
RELEASE_MANIFEST_VERSION = "pre_week08_release_manifest_v1"
VALIDATION_VERSION = "pre_week08_validation_v1"
STAGE_B_VALIDATION_VERSION = "pre_week08_stage_b_validation_v1"
STAGE_B_ACCEPTANCE_RECORD_VERSION = "ui-stage-b-acceptance-v2"
STAGE_B_SCENARIOS = (
    "multimodal",
    "single_candidate",
    "failed_check",
    "stale_state",
    "export_provenance",
)
STAGE_B_ZIP_REQUIRED_SCENARIOS = frozenset(
    {"single_candidate", "failed_check", "export_provenance"}
)
STAGE_B_SCOPE_DECISIONS = (
    "stage_c_research_evidence",
    "interactive_rire_expansion",
    "recommendation_display_path",
)
STAGE_B_SUPPLEMENTAL_CHECKS = (
    "normal_monomodal",
    "unknown_upload_claim_suppression",
    "rire_technical_only_caveat",
    "candidate_inspection_labels",
    "no_frozen_location_writes",
)
STAGE_B_SCREENSHOT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
POST_RELEASE_METADATA_PATHS = {
    LEDGER_REL.as_posix(),
    RELEASE_MANIFEST_REL.as_posix(),
    SOURCE_REGISTRATION_REL.as_posix(),
    HOLDOUT_SOURCE_MANIFEST_REL.as_posix(),
}
REQUIRED_EVIDENCE = {
    "day32_journal": "outputs/week07_day02_full/benchmark_records.jsonl",
    "day32_plan": "outputs/week07_day02_full/benchmark_plan.json",
    "day34_policy": "outputs/week07_day04_calibration/tentative_policy_not_for_ui.json",
    "day35_journal": "outputs/week07_day05_integration/benchmark_records.jsonl",
    "day35_plan": "outputs/week07_day05_integration/benchmark_plan.json",
    "day35_manifest": "outputs/week07_day05_integration/day35_manifest.json",
    "day35_report": "outputs/week07_day05_integration/day35_report.json",
    "day35_results": "outputs/week07_day05_integration/benchmark_results.csv",
}
REQUIRED_WEEK01_SOURCES = {
    "data/samples/week01/fixed.png": {
        "source_id": "week01_fixed",
        "sha256": "6ef03c6191df81913ebaef660ff9299b72c6e05b4a87a131d767f4d53151e6e0",
        "canonical_source_id": "project:week01_smoke_pair:fixed",
    },
    "data/samples/week01/moving.png": {
        "source_id": "week01_moving",
        "sha256": "21e76978ff7929ac85285df9995f02bd19835a84ba3d9f5edd2504316f6fbc31",
        "canonical_source_id": "project:week01_smoke_pair:moving",
    },
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_object)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalized_format(rel: Any) -> str | None:
    if not isinstance(rel, str):
        return None
    name = PurePosixPath(rel).name.lower()
    if name.endswith(".nii.gz"):
        return "nii.gz"
    suffix = PurePosixPath(rel).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else None


def check_path_hash(root: Path, rel: Any, expected: Any) -> str | None:
    path = safe_file(root, rel)
    if path is None or not path.is_file():
        return f"Missing or unsafe file: {rel}"
    if not is_sha256(expected):
        return f"Invalid SHA-256 syntax: {rel}"
    try:
        if digest(path) != expected:
            return f"SHA-256 mismatch: {rel}"
    except OSError as exc:
        return f"Cannot hash {rel}: {exc}"
    return None


def _safe_private_evidence_reference(value: Any, *, suffixes: frozenset[str]) -> bool:
    """Validate a sanitized path relative to the ignored Stage B runtime root."""
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value or ":" in value:
        return False
    windows = PureWindowsPath(value)
    if windows.drive or windows.root or value.startswith("/"):
        return False
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    return PurePosixPath(value).suffix.lower() in suffixes


def _valid_stage_b_utc(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _validate_stage_b_evidence(
    value: Any,
    *,
    scenario: str,
    kind: str,
    required: bool,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list):
        return [f"Stage B {scenario} {kind} evidence is not a list"]
    if required and not value:
        errors.append(f"Stage B {scenario} requires {kind} evidence")
    suffixes = STAGE_B_SCREENSHOT_SUFFIXES if kind == "screenshot" else frozenset({".zip"})
    seen: set[str] = set()
    for index, record in enumerate(value):
        label = f"Stage B {scenario} {kind} evidence {index}"
        if not isinstance(record, dict):
            errors.append(f"{label} is not an object")
            continue
        if set(record) != {"reference", "sha256", "size_bytes"}:
            errors.append(f"{label} metadata fields are not exact")
        reference = record.get("reference")
        if not _safe_private_evidence_reference(reference, suffixes=suffixes):
            errors.append(f"{label} reference is unsafe or has the wrong suffix")
        elif reference in seen:
            errors.append(f"{label} reference is duplicated")
        else:
            seen.add(reference)
        if not is_sha256(record.get("sha256")):
            errors.append(f"{label} SHA-256 is invalid")
        size = record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{label} size_bytes is not a positive integer")
    return errors


def validate_stage_b_validation_report(
    report: Any,
) -> list[str]:
    """Validate the sanitized G4 report without requiring its private evidence files."""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["Stage B validation must be a JSON object"]
    if report.get("schema_version") != STAGE_B_VALIDATION_VERSION:
        errors.append("unsupported Stage B validation schema_version")
    if report.get("stage") != "pre_week08_stage_b_ui_acceptance":
        errors.append("Stage B validation has the wrong stage identifier")
    if report.get("acceptance_record_schema") != STAGE_B_ACCEPTANCE_RECORD_VERSION:
        errors.append("Stage B validation has an unsupported acceptance record schema")

    commit = report.get("tested_release_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        errors.append("Stage B tested_release_commit is not a full lowercase SHA-1 object ID")
    target = report.get("target")
    if not isinstance(target, dict):
        errors.append("Stage B target is not an object")
    else:
        platform_name = target.get("platform")
        if not nonempty_text(platform_name) or "windows" not in platform_name.lower():
            errors.append("Stage B target does not identify Windows")
        if not nonempty_text(target.get("environment")):
            errors.append("Stage B target environment is missing")

    if report.get("manual_status") != "MANUALLY_ACCEPTED":
        errors.append("Stage B manual status is not MANUALLY_ACCEPTED")
    if report.get("manual_cases_accepted") != len(STAGE_B_SCENARIOS):
        errors.append("Stage B does not contain five accepted manual cases")
    if report.get("manual_cases_total") != len(STAGE_B_SCENARIOS):
        errors.append("Stage B manual case total is not five")
    if not is_sha256(report.get("fixture_manifest_sha256")):
        errors.append("Stage B fixture manifest SHA-256 is invalid")

    counts = report.get("automated_validation")
    if not isinstance(counts, dict) or set(counts) != {"backend", "ui"}:
        errors.append("Stage B automated validation must contain exact backend and UI counts")
    else:
        for suite_name in ("backend", "ui"):
            suite = counts.get(suite_name)
            if not isinstance(suite, dict) or set(suite) != {"passed", "skipped", "failed"}:
                errors.append(f"Stage B {suite_name} counts are malformed")
                continue
            for outcome in ("passed", "skipped", "failed"):
                count = suite.get(outcome)
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    errors.append(f"Stage B {suite_name} {outcome} count is invalid")
            passed = suite.get("passed")
            if isinstance(passed, int) and not isinstance(passed, bool) and passed <= 0:
                errors.append(f"Stage B {suite_name} passed count must be positive")
            if suite.get("failed") != 0:
                errors.append(f"Stage B {suite_name} suite has failures")
    if report.get("full_regression_zero_failures") is not True:
        errors.append("Stage B full regression zero-failure record is absent")

    scope = report.get("scope_decisions")
    if not isinstance(scope, dict) or set(scope) != set(STAGE_B_SCOPE_DECISIONS):
        errors.append("Stage B scope decisions are incomplete")
    elif any(scope.get(name) != "DEFERRED" for name in STAGE_B_SCOPE_DECISIONS):
        errors.append("Stage B v0.2 freeze requires all optional scope to be DEFERRED")

    scenarios = report.get("scenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != set(STAGE_B_SCENARIOS):
        errors.append("Stage B scenario set is not exact")
    else:
        expected_fields = {
            "verdict", "reviewer", "attested_utc", "observation", "screenshots", "zips"
        }
        for name in STAGE_B_SCENARIOS:
            scenario = scenarios.get(name)
            if not isinstance(scenario, dict):
                errors.append(f"Stage B {name} record is not an object")
                continue
            if set(scenario) != expected_fields:
                errors.append(f"Stage B {name} fields are not exact")
            if scenario.get("verdict") != "pass":
                errors.append(f"Stage B {name} is not PASS")
            if not nonempty_text(scenario.get("reviewer")):
                errors.append(f"Stage B {name} reviewer is missing")
            if not _valid_stage_b_utc(scenario.get("attested_utc")):
                errors.append(f"Stage B {name} timestamp is not valid UTC")
            if not nonempty_text(scenario.get("observation")):
                errors.append(f"Stage B {name} observation is missing")
            errors.extend(_validate_stage_b_evidence(
                scenario.get("screenshots"), scenario=name, kind="screenshot", required=True,
            ))
            errors.extend(_validate_stage_b_evidence(
                scenario.get("zips"), scenario=name, kind="ZIP",
                required=name in STAGE_B_ZIP_REQUIRED_SCENARIOS,
            ))

    if report.get("supplemental_checks_accepted") != len(STAGE_B_SUPPLEMENTAL_CHECKS):
        errors.append("Stage B does not contain five accepted supplemental checks")
    if report.get("supplemental_checks_total") != len(STAGE_B_SUPPLEMENTAL_CHECKS):
        errors.append("Stage B supplemental check total is not five")
    supplemental = report.get("supplemental_observations")
    if not isinstance(supplemental, dict) or set(supplemental) != set(STAGE_B_SUPPLEMENTAL_CHECKS):
        errors.append("Stage B supplemental observation set is not exact")
    else:
        expected_supplemental_fields = {
            "verdict", "reviewer", "attested_utc", "observation", "screenshots"
        }
        for name in STAGE_B_SUPPLEMENTAL_CHECKS:
            observation = supplemental.get(name)
            if not isinstance(observation, dict):
                errors.append(f"Stage B supplemental {name} record is not an object")
                continue
            if set(observation) != expected_supplemental_fields:
                errors.append(f"Stage B supplemental {name} fields are not exact")
            if observation.get("verdict") != "pass":
                errors.append(f"Stage B supplemental {name} is not PASS")
            if not nonempty_text(observation.get("reviewer")):
                errors.append(f"Stage B supplemental {name} reviewer is missing")
            if not _valid_stage_b_utc(observation.get("attested_utc")):
                errors.append(f"Stage B supplemental {name} timestamp is not valid UTC")
            if not nonempty_text(observation.get("observation")):
                errors.append(f"Stage B supplemental {name} observation is missing")
            errors.extend(_validate_stage_b_evidence(
                observation.get("screenshots"), scenario=f"supplemental {name}",
                kind="screenshot", required=True,
            ))

    if report.get("formal_ui_v02_frozen") is not True or report.get("frozen_ui_version") != "v0.2":
        errors.append("Stage B does not attest a formal UI v0.2 freeze")
    if report.get("week8_heldout_used") is not False:
        errors.append("Stage B does not attest zero Week 8 held-out use")
    return errors


def safe_file(root: Path, rel: str | None) -> Path | None:
    """Validate a project-relative path, blocking internal symlinks/junctions.

    The trust boundary begins at ``root``. Avoid resolving every child path:
    Windows filesystem junctions above root, and differences between Windows
    canonical/lexical paths, should never invalidate an ordinary staged file.
    Reject link/reparse components *inside* the repository with lstat instead.
    This does not open files or follow internal redirects.
    """
    # Manifest and ledger paths use the POSIX project-relative wire format on
    # every OS. Never interpret untrusted metadata via the host OS parser first:
    # on Windows '/etc/passwd' is rooted but Path.is_absolute() is False, and
    # joining it to a project root can escape to the drive root.
    if not isinstance(rel, str) or not rel or "\\" in rel or "\0" in rel or ":" in rel:
        return None
    win = PureWindowsPath(rel)
    if win.drive or win.root or rel.startswith("/"):
        return None
    pieces = rel.split("/")
    if any(part in ("", ".", "..") for part in pieces):
        return None
    relative = PurePosixPath(rel)
    try:
        base = root.absolute()
        current = base
        for part in relative.parts:
            current = current / part
            try:
                info = current.lstat()  # Does not follow symlinks or junctions.
            except FileNotFoundError:
                # Missing paths are separately rejected by checked_file();
                # no untrusted link can be traversed via a missing component.
                continue
            if stat.S_ISLNK(info.st_mode) or bool(
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                return None
        return current
    except (OSError, RuntimeError, ValueError):
        return None


class _UniqueYamlLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate keys."""


def _unique_yaml_mapping(loader: _UniqueYamlLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _unique_yaml_mapping,
)


def verify_phase3_evaluator_evidence(root: Path) -> tuple[list[str], dict[str, Any]]:
    """Verify tracked G3 evidence and its exact runner/test byte bindings."""
    errors: list[str] = []
    observed: dict[str, Any] = {
        "state": "missing",
        "report_path": PHASE3_EVALUATOR_REPORT_REL.as_posix(),
    }
    report_path = safe_file(root, PHASE3_EVALUATOR_REPORT_REL.as_posix())
    if report_path is None or not report_path.is_file():
        return [f"missing {PHASE3_EVALUATOR_REPORT_REL.as_posix()}"], observed
    try:
        report = read_json(report_path)
        if not isinstance(report, dict):
            raise TypeError("Phase 3 evaluator report must be a JSON object")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        observed["state"] = "invalid"
        return [f"invalid Phase 3 evaluator report: {exc}"], observed

    observed.update({
        "state": "invalid",
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "gate": report.get("gate"),
    })
    if report.get("schema_version") != PHASE3_EVALUATOR_REPORT_VERSION:
        errors.append("unsupported Phase 3 evaluator report schema_version")
    if report.get("gate") != "G3" or report.get("status") != "PASS":
        errors.append("Phase 3 evaluator report does not attest G3 PASS")
    if report.get("scope") != "development_rehearsal_only":
        errors.append("Phase 3 evaluator evidence scope is not development-rehearsal-only")
    for field, expected in {
        "development_only": True,
        "final_evidence": False,
        "real_week08_source_pixels_accessed": False,
        "real_week08_labels_accessed": False,
        "week08_benchmark_executed": False,
        "final_claims_allowed": False,
    }.items():
        if report.get(field) is not expected:
            errors.append(f"Phase 3 evaluator report has invalid {field}")

    artifact_hashes = report.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        errors.append("Phase 3 evaluator artifact_hashes must be an object")
        artifact_hashes = {}
    expected_hash_paths = set(PHASE3_EVALUATOR_HASH_PATHS)
    if set(artifact_hashes) != expected_hash_paths:
        missing = sorted(expected_hash_paths - set(artifact_hashes))
        unexpected = sorted(set(artifact_hashes) - expected_hash_paths)
        if missing:
            errors.append("Phase 3 evaluator hashes are missing: " + ", ".join(missing))
        if unexpected:
            errors.append("Phase 3 evaluator hashes have unexpected paths: " + ", ".join(unexpected))
    for rel in sorted(expected_hash_paths):
        issue = check_path_hash(root, rel, artifact_hashes.get(rel))
        if issue:
            errors.append(f"Phase 3 evaluator binding: {issue}")

    focused = report.get("focused_tests")
    if not isinstance(focused, dict):
        errors.append("Phase 3 evaluator focused_tests must be an object")
        focused = {}
    required_test_runs = {
        "week08_final_evaluation": "tests/test_week08_final_evaluation.py",
        "week08_phase3_cli": "tests/test_week08_phase3_cli.py",
        "week08_preflight": "tests/test_week08_preflight.py",
    }
    for name, expected_path in required_test_runs.items():
        run = focused.get(name)
        if not isinstance(run, dict):
            errors.append(f"missing Phase 3 focused test record: {name}")
            continue
        if run.get("path") != expected_path:
            errors.append(f"Phase 3 focused test path mismatch: {name}")
        for count_name in ("passed", "failed", "errors", "skipped"):
            value = run.get(count_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"invalid {name} {count_name} count")
        if not isinstance(run.get("passed"), int) or run.get("passed", 0) < 1:
            errors.append(f"Phase 3 focused test run has no passes: {name}")
        if run.get("failed") != 0 or run.get("errors") != 0:
            errors.append(f"Phase 3 focused test run is not zero-failure: {name}")

    rehearsal = report.get("development_rehearsal")
    if not isinstance(rehearsal, dict):
        errors.append("Phase 3 development_rehearsal evidence is missing")
        rehearsal = {}
    expected_rehearsal = {
        "mode": "development_rehearsal",
        "source_id": "phase3_camera_fixture",
        "pair_count": 4,
        "planned_attempt_count": 12,
        "terminal_record_count": 12,
        "decision_sealed": True,
        "label_access_after_verified_decision_seal": True,
        "final_evidence": False,
        "real_week08_source_or_label_accessed": False,
    }
    for field, expected in expected_rehearsal.items():
        if rehearsal.get(field) != expected:
            errors.append(f"Phase 3 rehearsal evidence mismatch: {field}")
    for field in ("evaluation_summary_sha256", "decision_seal_sha256"):
        if not is_sha256(rehearsal.get(field)):
            errors.append(f"Phase 3 rehearsal evidence has invalid {field}")

    preflight = report.get("preflight")
    if not isinstance(preflight, dict):
        errors.append("Phase 3 preflight evidence is missing")
        preflight = {}
    if preflight.get("report_version") != VERSION:
        errors.append("Phase 3 preflight evidence report_version mismatch")
    if preflight.get("mode") != "development" or preflight.get("runner_contract_status") != "PASS":
        errors.append("Phase 3 preflight did not record a passing runner contract")
    for field in ("pass_count", "warn_count", "block_count"):
        value = preflight.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"Phase 3 preflight has invalid {field}")
    if preflight.get("real_week08_source_or_label_accessed") is not False:
        errors.append("Phase 3 preflight does not attest zero real Week 8 access")

    observed["artifact_count"] = len(artifact_hashes)
    observed["focused_tests"] = focused
    observed["development_rehearsal"] = rehearsal
    observed["preflight"] = preflight
    observed["state"] = "pass" if not errors else "invalid"
    return errors, observed


def verify_week08_runner_contract(root: Path) -> tuple[list[str], dict[str, Any]]:
    """Verify tracked G3 evidence, then run the metadata-only import smoke probe."""
    errors: list[str] = []
    observed: dict[str, Any] = {
        "probe": None,
        "config_schema_version": None,
        "phase3_evidence": None,
    }
    missing: list[str] = []
    for rel in FINAL_RUNNER_PATHS:
        path = safe_file(root, rel)
        if path is None or not path.is_file():
            missing.append(rel)
    if missing:
        return ["missing runner artifacts: " + ", ".join(missing)], observed

    config_path = safe_file(root, "configs/week08_final_evaluation.yaml")
    if config_path is None:
        return ["unsafe Week 8 evaluation config path"], observed
    try:
        config = yaml.load(config_path.read_text(encoding="utf-8"), Loader=_UniqueYamlLoader)
        if not isinstance(config, dict):
            raise TypeError("configuration is not a mapping")
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return [f"invalid Week 8 evaluation config: {exc}"], observed
    observed["config_schema_version"] = config.get("schema_version")
    if config.get("schema_version") != WEEK08_EVALUATION_CONFIG_VERSION:
        errors.append("unsupported Week 8 evaluation config schema_version")
    if config.get("state") != "phase3_preregistered_development_rehearsal_only":
        errors.append("Phase 3 config is not development-rehearsal-only")
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    if safety.get("phase3_allows_real_week08_pixel_access") is not False:
        errors.append("Phase 3 config does not forbid real Week 8 pixel access")
    if safety.get("phase3_allows_real_week08_label_access") is not False:
        errors.append("Phase 3 config does not forbid real Week 8 label access")
    if safety.get("plan_and_dry_run_forbid_image_or_label_decoding") is not True:
        errors.append("plan/dry-run decoding prohibition is missing")
    execution = config.get("execution_contract") if isinstance(config.get("execution_contract"), dict) else {}
    if execution.get("phases") != ["prepare", "decide", "evaluate"]:
        errors.append("execution contract does not declare prepare/decide/evaluate isolation")
    if execution.get("id_namespace") != "w8":
        errors.append("execution contract does not reserve the w8 ID namespace")
    reruns = config.get("reruns") if isinstance(config.get("reruns"), dict) else {}
    if reruns.get("permitted_reason") != "infrastructure_error_only":
        errors.append("rerun contract is not infrastructure-error-only")
    denominators = config.get("denominators") if isinstance(config.get("denominators"), dict) else {}
    if not isinstance(denominators.get("track_a"), dict) or not isinstance(denominators.get("track_b"), dict):
        errors.append("separate Track A and Track B denominator contracts are missing")

    frozen_assets = config.get("frozen_assets") if isinstance(config.get("frozen_assets"), dict) else {}
    for key in ("method_catalog", "policy", "observable_projection", "frozen_baseline"):
        asset = frozen_assets.get(key) if isinstance(frozen_assets.get(key), dict) else {}
        asset_path = asset.get("path") or asset.get("implementation_file")
        issue = check_path_hash(root, asset_path, asset.get("sha256"))
        if issue:
            errors.append(f"{key}: {issue}")

    evidence_errors, evidence_observed = verify_phase3_evaluator_evidence(root)
    observed["phase3_evidence"] = evidence_observed
    errors.extend(evidence_errors)

    probe_source = (
        "import json\n"
        "from image_registration.week8_evaluation import runner_contract_probe\n"
        "print(json.dumps(runner_contract_probe(), sort_keys=True))\n"
    )
    probe_environment = dict(os.environ)
    python_paths = [str((root / "src").resolve()), str(root.resolve())]
    inherited = probe_environment.get("PYTHONPATH")
    if inherited:
        python_paths.append(inherited)
    probe_environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe_source],
            cwd=root,
            env=probe_environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"cannot execute Week 8 runner contract probe: {exc}")
        return errors, observed
    if result.returncode != 0:
        errors.append("Week 8 runner contract probe failed: " + result.stderr.strip()[:500])
        return errors, observed
    try:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        probe = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        errors.append(f"Week 8 runner contract probe returned invalid JSON: {exc}")
        return errors, observed
    observed["probe"] = probe
    if not isinstance(probe, dict) or probe.get("schema_version") != WEEK08_RUNNER_PROBE_VERSION:
        errors.append("unsupported Week 8 runner probe schema")
    elif probe.get("status") != "pass" or probe.get("reads_pixels_or_labels") is not False:
        errors.append("Week 8 runner probe did not pass metadata-only contract checks")
    else:
        checks = probe.get("checks") if isinstance(probe.get("checks"), dict) else {}
        required = {
            "deterministic_w8_id",
            "prior_id_collision_rejected",
            "plan_and_count_hashes_verified",
            "isolated_phases_declared",
            "infrastructure_not_terminal_scientific_status",
        }
        failed = sorted(name for name in required if checks.get(name) is not True)
        if failed:
            errors.append("runner probe checks failed: " + ", ".join(failed))
    return errors, observed


def verify_release_git(root: Path, commit: Any, tag: Any) -> tuple[list[str], dict[str, Any]]:
    """Verify an actual tagged release ancestor and the current clean worktree."""
    errors: list[str] = []
    observed: dict[str, Any] = {"head": None, "release_commit": commit, "release_tag": tag}
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) is None:
        errors.append("release_commit must be a full lowercase Git object ID")
    if not nonempty_text(tag):
        errors.append("release_tag is missing")
    if errors:
        return errors, observed

    command = ["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root.resolve())]

    def git(*args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [*command, *args], capture_output=True, text=True, check=False, timeout=20
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"cannot execute Git verification: {exc}")
            return None

    ref_check = git("check-ref-format", f"refs/tags/{tag}")
    if ref_check is None:
        return errors, observed
    if ref_check.returncode != 0:
        errors.append("release_tag is not a valid Git tag name")
        return errors, observed

    def resolve(specification: str, label: str) -> str | None:
        result = git("rev-parse", "--verify", specification)
        if result is None:
            return None
        if result.returncode != 0:
            errors.append(f"cannot resolve {label}")
            return None
        value = result.stdout.strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
            errors.append(f"invalid resolved object ID for {label}")
            return None
        return value

    head = resolve("HEAD^{commit}", "HEAD")
    release = resolve(f"{commit}^{{commit}}", "release_commit")
    tagged = resolve(f"refs/tags/{tag}^{{commit}}", "release_tag")
    observed.update({"head": head, "resolved_release_commit": release, "tagged_commit": tagged})
    if release is not None and release != commit:
        errors.append("release_commit does not resolve to itself")
    if tagged is not None and tagged != commit:
        errors.append("release_tag does not resolve to release_commit")
    if head is not None and release is not None:
        ancestor = git("merge-base", "--is-ancestor", release, head)
        if ancestor is None or ancestor.returncode != 0:
            errors.append("release_commit is not an ancestor of HEAD")
        else:
            changed = git("diff", "--name-only", "-z", release, head, "--")
            if changed is None:
                return errors, observed
            if changed.returncode != 0:
                errors.append("cannot inspect post-release path changes")
            else:
                changed_paths = sorted(path for path in changed.stdout.split("\0") if path)
                observed["post_release_changed_paths"] = changed_paths
                forbidden = sorted(set(changed_paths) - POST_RELEASE_METADATA_PATHS)
                if forbidden:
                    errors.append(
                        "post-release changes exceed the Phase 6 metadata allowlist: "
                        + ", ".join(forbidden)
                    )
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    if status is None:
        return errors, observed
    observed["worktree_status"] = status.stdout.splitlines()
    if status.returncode != 0:
        errors.append("cannot inspect Git worktree status")
    elif status.stdout.strip():
        errors.append("Git worktree is not clean")
    return errors, observed


def verify_stage_b_release_binding(
    root: Path,
    tested_commit: Any,
    release_commit: Any,
) -> tuple[list[str], dict[str, Any]]:
    """Bind the tested UI checkpoint to a descendant documentation-only release."""
    errors: list[str] = []
    observed: dict[str, Any] = {
        "tested_commit": tested_commit,
        "release_commit": release_commit,
        "changed_paths": [],
        "protected_changed_paths": [],
    }
    if not isinstance(tested_commit, str) or re.fullmatch(r"[0-9a-f]{40}", tested_commit) is None:
        errors.append("Stage B tested commit must be a full lowercase SHA-1 object ID")
    if not isinstance(release_commit, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", release_commit) is None:
        errors.append("release manifest commit must be a full lowercase Git object ID")
    if errors:
        return errors, observed

    command = ["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root.resolve())]

    def git(*args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [*command, *args], capture_output=True, text=True, check=False, timeout=20
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"cannot execute Stage B Git binding verification: {exc}")
            return None

    def resolve(commit: str, label: str) -> str | None:
        result = git("rev-parse", "--verify", f"{commit}^{{commit}}")
        if result is None:
            return None
        if result.returncode != 0:
            errors.append(f"cannot resolve {label}")
            return None
        resolved = result.stdout.strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", resolved) is None:
            errors.append(f"invalid resolved object ID for {label}")
            return None
        return resolved

    tested = resolve(tested_commit, "Stage B tested commit")
    release = resolve(release_commit, "release manifest commit")
    observed.update({"resolved_tested_commit": tested, "resolved_release_commit": release})
    if tested is not None and tested != tested_commit:
        errors.append("Stage B tested commit does not resolve to itself")
    if release is not None and release != release_commit:
        errors.append("release manifest commit does not resolve to itself")
    if tested is None or release is None:
        return errors, observed

    ancestor = git("merge-base", "--is-ancestor", tested, release)
    if ancestor is None:
        return errors, observed
    if ancestor.returncode != 0:
        errors.append("Stage B tested commit is not an ancestor of the release manifest commit")
        return errors, observed

    changed = git("log", "--format=", "--name-only", "-z", f"{tested}..{release}", "--")
    if changed is None:
        return errors, observed
    if changed.returncode != 0:
        errors.append("cannot inspect changes after the Stage B tested commit")
        return errors, observed
    changed_paths = sorted({path.strip() for path in changed.stdout.split("\0") if path.strip()})
    observed["changed_paths"] = changed_paths

    def protected(path: str) -> bool:
        if path in {"pyproject.toml", "requirements.txt"}:
            return True
        if any(path.startswith(prefix) for prefix in ("src/", "scripts/", "configs/", "tests/")):
            return True
        return path.startswith("ui/") and PurePosixPath(path).suffix.lower() != ".md"

    protected_paths = [path for path in changed_paths if protected(path)]
    observed["protected_changed_paths"] = protected_paths
    if protected_paths:
        errors.append(
            "protected implementation/test/config paths changed after Stage B testing: "
            + ", ".join(protected_paths)
        )
    return errors, observed


class Audit:
    def __init__(self, root: Path, *, final_readiness: bool = False):
        self.root = root.resolve()
        self.final_readiness = final_readiness
        self.checks: list[dict[str, Any]] = []
        self.development_metadata: dict[str, dict[str, Any]] = {}
        self.evidence_archive_record: dict[str, Any] = {}

    def add(self, code: str, status: str, details: str, **fields: Any) -> None:
        if status not in {"PASS", "WARN", "BLOCK"}:
            raise ValueError(f"Invalid audit status: {status}")
        self.checks.append({"check": code, "status": status, "details": details, **fields})

    def check_status(self, code: str) -> str | None:
        return next((item["status"] for item in self.checks if item["check"] == code), None)

    def checked_file(self, rel: str | None, kind: str) -> Path | None:
        path = safe_file(self.root, rel)
        if path is None or not path.is_file():
            self.add(kind, "BLOCK", f"Missing or unsafe required file: {rel}")
            return None
        return path

    def integrity_anchor(self) -> None:
        anchor_path = safe_file(self.root, INTEGRITY_ANCHOR_REL.as_posix())
        if anchor_path is None or not anchor_path.is_file():
            self.add("integrity_anchor", "BLOCK", f"Missing integrity anchor: {INTEGRITY_ANCHOR_REL.as_posix()}")
            return
        errors: list[str] = []
        try:
            anchor = read_json(anchor_path)
            if not isinstance(anchor, dict):
                raise TypeError("integrity anchor must be a JSON object")
            if anchor.get("schema_version") != "week08_integrity_anchor_v1":
                errors.append("unsupported schema_version")
            if anchor.get("phase1_commit") != PHASE1_COMMIT:
                errors.append("Phase 1 checkpoint binding mismatch")
            if anchor.get("expected_frozen_file_count") != EXPECTED_FROZEN_FILES:
                errors.append("frozen-file count is not anchored to 101")
            if anchor.get("expected_week7_evidence_file_count") != EXPECTED_EVIDENCE_FILES:
                errors.append("evidence-file count is not anchored to 81")
            expected = {
                "frozen_baseline": FROZEN_REL,
                "week07_closure": CLOSURE_REL,
                "week07_handoff": HANDOFF_REL,
                "evidence_archive_manifest": EVIDENCE_ARCHIVE_MANIFEST_REL,
            }
            for key, required_path in expected.items():
                record = anchor.get(key)
                if not isinstance(record, dict) or record.get("path") != required_path.as_posix():
                    errors.append(f"invalid {key} path")
                    continue
                problem = check_path_hash(self.root, record.get("path"), record.get("sha256"))
                if problem:
                    errors.append(problem)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid anchor JSON: {exc}")
        self.add(
            "integrity_anchor",
            "BLOCK" if errors else "PASS",
            "Integrity anchor binds the baseline, closure, handoff and evidence archive manifest",
            errors=errors,
        )

    def evidence_packaging(self, baseline: dict) -> None:
        manifest_path = safe_file(self.root, EVIDENCE_ARCHIVE_MANIFEST_REL.as_posix())
        if manifest_path is None or not manifest_path.is_file():
            self.add("week07_evidence_packaging", "BLOCK", f"Missing archive manifest: {EVIDENCE_ARCHIVE_MANIFEST_REL.as_posix()}")
            return
        errors: list[str] = []
        try:
            package = read_json(manifest_path)
            if not isinstance(package, dict):
                raise TypeError("archive manifest must be a JSON object")
            if package.get("schema_version") != "week07_evidence_archive_v1":
                errors.append("unsupported schema_version")
            if package.get("phase1_commit") != PHASE1_COMMIT:
                errors.append("Phase 1 checkpoint binding mismatch")
            references = {
                "baseline": FROZEN_REL,
                "closure": CLOSURE_REL,
                "handoff": HANDOFF_REL,
            }
            for key, required_path in references.items():
                record = package.get(key)
                if not isinstance(record, dict) or record.get("path") != required_path.as_posix():
                    errors.append(f"invalid {key} reference")
                    continue
                problem = check_path_hash(self.root, record.get("path"), record.get("sha256"))
                if problem:
                    errors.append(problem)
            files = package.get("files")
            evidence = baseline.get("week7_evidence_files", {}) if isinstance(baseline, dict) else {}
            if not isinstance(evidence, dict):
                errors.append("frozen baseline evidence inventory must be an object")
                evidence = {}
            if package.get("file_count") != EXPECTED_EVIDENCE_FILES or not isinstance(files, list) or len(files) != EXPECTED_EVIDENCE_FILES:
                errors.append("archive manifest must contain exactly 81 file records")
                files = files if isinstance(files, list) else []
            observed: dict[str, dict] = {}
            for record in files:
                if not isinstance(record, dict) or not nonempty_text(record.get("path")):
                    errors.append("malformed archive file record")
                    continue
                rel = record["path"]
                if rel in observed:
                    errors.append(f"duplicate archive path: {rel}")
                    continue
                observed[rel] = record
                if not isinstance(record.get("size_bytes"), int) or isinstance(record.get("size_bytes"), bool) or record["size_bytes"] < 0:
                    errors.append(f"invalid size: {rel}")
                if not is_sha256(record.get("sha256")):
                    errors.append(f"invalid hash: {rel}")
                if not nonempty_text(record.get("closure_reference")):
                    errors.append(f"missing closure reference: {rel}")
            if set(observed) != set(evidence):
                errors.append("archive file set does not match the frozen 81-file inventory")
            for rel, expected_hash in evidence.items():
                record = observed.get(rel)
                path = safe_file(self.root, rel)
                if record is None:
                    continue
                if record.get("sha256") != expected_hash:
                    errors.append(f"archive hash contradicts baseline: {rel}")
                if path is None or not path.is_file():
                    errors.append(f"missing frozen evidence: {rel}")
                else:
                    try:
                        if record.get("size_bytes") != path.stat().st_size:
                            errors.append(f"archive size contradicts workspace: {rel}")
                    except OSError as exc:
                        errors.append(f"cannot stat {rel}: {exc}")
            archive = package.get("archive")
            if not isinstance(archive, dict):
                errors.append("missing archive metadata")
            else:
                filename = archive.get("filename")
                if filename != EVIDENCE_ARCHIVE_REL.name:
                    errors.append("invalid archive filename")
                if not isinstance(archive.get("size_bytes"), int) or isinstance(archive.get("size_bytes"), bool) or archive["size_bytes"] <= 0:
                    errors.append("invalid archive size")
                if not is_sha256(archive.get("sha256")):
                    errors.append("invalid archive SHA-256")
                self.evidence_archive_record = dict(archive)
                if self.final_readiness:
                    archive_path = safe_file(self.root, EVIDENCE_ARCHIVE_REL.as_posix())
                    if archive_path is None or not archive_path.is_file():
                        errors.append(f"missing release evidence archive: {EVIDENCE_ARCHIVE_REL.as_posix()}")
                    else:
                        try:
                            if archive_path.stat().st_size != archive.get("size_bytes"):
                                errors.append("release evidence archive size mismatch")
                            if is_sha256(archive.get("sha256")) and digest(archive_path) != archive["sha256"]:
                                errors.append("release evidence archive SHA-256 mismatch")
                        except OSError as exc:
                            errors.append(f"cannot verify release evidence archive: {exc}")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid archive manifest: {exc}")
        self.add(
            "week07_evidence_packaging",
            "BLOCK" if errors else "PASS",
            "Tracked manifest covers the deterministic 81-file Week 7 evidence archive",
            errors=errors[:40],
        )

    def frozen(self) -> tuple[dict, dict]:
        manifest_path = self.checked_file(FROZEN_REL.as_posix(), "frozen_baseline")
        handoff_path = self.checked_file(HANDOFF_REL.as_posix(), "week07_handoff")
        closure_path = self.checked_file(CLOSURE_REL.as_posix(), "week07_closure")
        if not all((manifest_path, handoff_path, closure_path)):
            return {}, {}
        try:
            manifest, handoff, closure = map(read_json, (manifest_path, handoff_path, closure_path))
            if not all(isinstance(value, dict) for value in (manifest, handoff, closure)):
                raise TypeError("baseline, handoff and closure must be JSON objects")
            if manifest.get("version") != BASELINE_VERSION:
                raise ValueError("unsupported frozen-baseline version")
            if closure.get("status") != "complete_development_stage":
                raise ValueError("Week 7 closure is not complete")
            if handoff.get("independent_validation_completed") is not False:
                raise ValueError("handoff incorrectly claims independent validation")
            if handoff.get("policy_deployed_to_ui") is not False:
                raise ValueError("handoff incorrectly claims UI policy deployment")
            self.add("week07_closure_state", "PASS", "Week 7 closed, policy not independently validated or deployed")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.add("week07_closure_state", "BLOCK", f"Invalid closure/handoff contract: {exc}")
            return {}, {}
        file_hashes = manifest.get("frozen_files", {})
        source_errors: list[str] = []
        if not isinstance(file_hashes, dict) or len(file_hashes) != EXPECTED_FROZEN_FILES:
            source_errors.append(f"expected exactly {EXPECTED_FROZEN_FILES} frozen files")
            file_hashes = file_hashes if isinstance(file_hashes, dict) else {}
        for rel, expected in sorted(file_hashes.items()):
            problem = check_path_hash(self.root, rel, expected)
            if problem:
                source_errors.append(problem)
        self.add("frozen_sources", "BLOCK" if source_errors else "PASS",
                 f"Validated {len(file_hashes) - len(source_errors)}/{len(file_hashes)} immutable files",
                 errors=source_errors[:30])
        evidence_map = manifest.get("week7_evidence_files", {})
        evidence_errors: list[str] = []
        if not isinstance(evidence_map, dict) or len(evidence_map) != EXPECTED_EVIDENCE_FILES:
            evidence_errors.append(f"expected exactly {EXPECTED_EVIDENCE_FILES} evidence files")
            evidence_map = evidence_map if isinstance(evidence_map, dict) else {}
        tree_counts = {prefix: 0 for prefix in PROTECTED}
        for rel, expected in sorted(evidence_map.items()):
            matching = [prefix for prefix in PROTECTED if rel.startswith(prefix)] if isinstance(rel, str) else []
            if len(matching) != 1:
                evidence_errors.append(f"evidence outside protected trees: {rel}")
            else:
                tree_counts[matching[0]] += 1
            problem = check_path_hash(self.root, rel, expected)
            if problem:
                evidence_errors.append(problem)
        if any(count == 0 for count in tree_counts.values()):
            evidence_errors.append("all four frozen evidence trees must be represented")
        self.add("week7_complete_evidence", "BLOCK" if evidence_errors else "PASS",
                 f"{len(evidence_map) - len(evidence_errors)}/{len(evidence_map)} Week 7 evidence files match the closure snapshot",
                 errors=evidence_errors[:35], tree_counts=tree_counts)
        return manifest, handoff

    def evidence(self, handoff: dict) -> None:
        if not handoff:
            self.add("evidence_hashes", "BLOCK", "Week 7 handoff missing")
            return
        closure_path = self.root / CLOSURE_REL
        try:
            closure = read_json(closure_path)
            hashes = closure["provenance"]
            expected = {
                "day32_journal": hashes["day32_journal_sha256"],
                "day32_plan": hashes["day32_plan_sha256"],
                "day34_policy": handoff["policy_sha256"],
                "day35_journal": hashes["day35_journal_sha256"],
                "day35_plan": hashes["day35_plan_sha256"],
                "day35_manifest": hashes["day35_manifest_sha256"],
                "day35_report": hashes["day35_report_sha256"],
                "day35_results": hashes["day35_results_sha256"],
            }
            if expected["day32_journal"] != handoff["reference_day32_journal_sha256"]:
                raise ValueError("Day 32 journal contradicts handoff")
        except (ValueError, KeyError, TypeError) as exc:
            self.add("evidence_hashes", "BLOCK", f"Missing authoritative checksums: {exc}")
            return
        bad = []
        for key, rel in REQUIRED_EVIDENCE.items():
            p = safe_file(self.root, rel)
            if p is None or not p.is_file() or digest(p) != expected[key]:
                bad.append(rel)
        self.add("evidence_hashes", "BLOCK" if bad else "PASS",
                 "Frozen evidence checked against Week 7 closure and handoff",
                 verified=len(REQUIRED_EVIDENCE)-len(bad), total=len(REQUIRED_EVIDENCE), invalid=bad)
        if bad:
            self.add("evidence_restoration", "BLOCK",
                     "Restore original outputs/ from the complete Week 7 closure ZIP. Do not regenerate evidence")
            return
        try:
            policy = read_json(self.root / REQUIRED_EVIDENCE["day34_policy"])
            if policy.get("gate") != handoff.get("gate"):
                raise ValueError("policy gate contradicts handoff")
            if policy.get("status") != "exploratory_not_deployed":
                raise ValueError("policy status is not exploratory_not_deployed")
            if policy.get("independent_validation") is not False:
                raise ValueError("policy incorrectly claims independent validation")
            self.add("policy_gate", "PASS", "Frozen Day 34 thresholds and non-deployment status verified")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.add("policy_gate", "BLOCK", f"Policy/handoff mismatch: {exc}")
        try:
            self.verify_journals()
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            self.add("development_journal_schema", "BLOCK", f"Invalid or duplicate benchmark journal records: {exc}")

    def verify_journals(self) -> None:
        pair_sets = []
        for day, count, pairs in ((32, 963, 486), (35, 88, 40)):
            folder = f"outputs/week07_day0{2 if day == 32 else 5}_{'full' if day == 32 else 'integration'}"
            # Day 32 directory is day02_full; Day 35 is day05_integration.
            plan = read_json(self.root / folder / "benchmark_plan.json")
            expected = [t["experiment_id"] for t in plan["tasks"]]
            seen, pair_ids, statuses, successes = [], set(), {}, 0
            with (self.root / folder / "benchmark_records.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    seen.append(row["experiment_id"])
                    pair_ids.add(row["record"]["pair_id"])
                    status = row["record"]["execution_status"]
                    statuses[status] = statuses.get(status, 0) + 1
                    successes += row["record"].get("geometric_within_tolerance") is True
                    if row["experiment_id"] != row["task"]["experiment_id"]:
                        raise ValueError(f"Day {day} journal identity mismatch")
            ok = (len(expected) == len(seen) == count and len(set(seen)) == count
                  and set(seen) == set(expected) and len(pair_ids) == pairs
                  and successes == (840 if day == 32 else 61)
                  and sum(statuses.values()) == count
                  and set(statuses).issubset({"completed", "check", "failed", "validation_error"}))
            self.add(f"day{day}_journal_integrity", "PASS" if ok else "BLOCK",
                     f"{len(seen)} records; {len(pair_ids)} pairs; {successes} correct; statuses {statuses}")
            seeds = sorted({t.get("pair_metadata", {}).get("geometry_seed") for t in plan["tasks"]}, key=str)
            source_hashes = sorted({str(t.get("pair_metadata", {}).get("source_sha256", "")) for t in plan["tasks"]})
            directions = sorted({t.get("pair_metadata", {}).get("transform_direction") for t in plan["tasks"]}, key=str)
            metadata_complete = (all(x is not None for x in seeds) and all(len(x) == 64 for x in source_hashes)
                                 and directions == ["moving_to_fixed"] and len(source_hashes) > 0
                                 and all(t.get("config_id") and t.get("method_id") and t.get("method_family")
                                         and t.get("transform_model") for t in plan["tasks"]))
            self.add(f"day{day}_provenance_fields", "PASS" if metadata_complete else "BLOCK",
                     "Frozen task plan records geometry seeds, source hashes, method/config IDs and Moving->Fixed convention")
            self.development_metadata[f"day{day}"] = {
                "plan_fingerprint": plan.get("plan_fingerprint"), "geometry_seeds": seeds,
                "source_sha256": source_hashes, "transform_directions": directions,
                "method_ids": sorted({t["method_id"] for t in plan["tasks"]}),
                "task_count": len(expected),
            }
            pair_sets.append(set(seen))
        self.add("development_task_id_isolation", "BLOCK" if pair_sets[0] & pair_sets[1] else "PASS",
                 "Day 32 and Day 35 task IDs do not overlap" if not pair_sets[0] & pair_sets[1] else "Duplicate development IDs")

    def ground_truth_firewall(self) -> None:
        """Static, immutable contract check without importing registration or held-out data.

        The existing Day 34 regression tests additionally exercise label-mutation
        invariance. The Week 8 runner's separate metadata-only runtime probe is
        checked by ``final_workspace``.
        """
        import ast
        source = self.root / "src/image_registration/week7_calibration.py"
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            functions = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
            if not {"project_observables", "select_pair"}.issubset(functions):
                raise ValueError("observable projection or selection function missing")
            project = functions["project_observables"]
            returns = [x.value for x in ast.walk(project) if isinstance(x, ast.Return)]
            if len(returns) != 1 or not isinstance(returns[0], ast.Dict):
                raise ValueError("observable projection return contract changed")
            keys = {x.value for x in returns[0].keys if isinstance(x, ast.Constant) and isinstance(x.value, str)}
            expected = {"experiment_id", "pair_id", "method_id", "family", "model", "modality",
                        "execution_status", "plausible", "transform", "shape_hw", "overlap",
                        "inlier_ratio", "match_coverage", "inliers", "ecc_final", "ecc_levels",
                        "mi_stop", "mi_metric", "mi_valid_points", "phase_response"}
            if keys != expected:
                raise ValueError("observable projection field set changed")
            prohibited = {"geometric_within_tolerance", "reference", "metrics", "ground_truth_transform",
                          "tre_mean_px", "geometry_seed", "degradation", "severity"}
            body = project.body[1:] if (project.body and isinstance(project.body[0], ast.Expr)
                                              and isinstance(project.body[0].value, ast.Constant)) else project.body
            observed_constants = {n.value for stmt in body for n in ast.walk(stmt)
                                  if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            if prohibited.intersection(observed_constants):
                raise ValueError("ground-truth fields entered observable projection")
            select = functions["select_pair"]
            identifiers = {x.id for x in ast.walk(select) if isinstance(x, ast.Name)}
            if {"offline_evaluate", "labels_by_pair", "ground_truth"}.intersection(identifiers):
                raise ValueError("selection function references ground truth")
            test_file = self.root / "tests/test_week7_day34_offline_calibration.py"
            if not test_file.is_file() or "test_changing_ground_truth_and_synthetic_severity_cannot_change_gate" not in test_file.read_text(encoding="utf-8"):
                raise ValueError("label-invariance regression is missing")
            self.add("day34_gt_firewall_contract", "PASS", "Immutable observable-only projection and Day 34 label-invariance regression verified; Week 8 runtime firewall is checked separately")
        except (SyntaxError, OSError, ValueError, KeyError, TypeError) as exc:
            self.add("day34_gt_firewall_contract", "BLOCK", f"Ground-truth firewall contract failed: {type(exc).__name__}: {exc}")

    def validate_lineage(self, entry: dict, source_id: str, errors: list[str]) -> None:
        for field in (
            "canonical_dataset_id", "canonical_subject_id", "canonical_case_id",
            "canonical_acquisition_id", "canonical_source_id", "lineage_status",
        ):
            if not nonempty_text(entry.get(field)):
                errors.append(f"Missing {field}: {source_id}")
        ancestors = entry.get("lineage_ancestors")
        if (not isinstance(ancestors, list) or not ancestors or
                any(not nonempty_text(value) for value in ancestors)):
            errors.append(f"Invalid lineage_ancestors: {source_id}")
        elif len(set(ancestors)) != len(ancestors):
            errors.append(f"Duplicate lineage ancestor: {source_id}")
        lineage = entry.get("lineage_evidence")
        if not isinstance(lineage, dict):
            errors.append(f"Missing lineage_evidence: {source_id}")
        else:
            problem = check_path_hash(self.root, lineage.get("manifest_path"), lineage.get("manifest_sha256"))
            if problem:
                errors.append(f"Lineage evidence for {source_id}: {problem}")

    def validate_mhd_components(self, entry: dict, source_id: str, errors: list[str]) -> None:
        if entry.get("format") != "mhd":
            return
        components = entry.get("components")
        if not isinstance(components, list) or not components:
            errors.append(f"MHD source requires hashed components: {source_id}")
            return
        for component in components:
            if not isinstance(component, dict):
                errors.append(f"Malformed MHD component: {source_id}")
                continue
            problem = check_path_hash(self.root, component.get("path"), component.get("sha256"))
            if problem:
                errors.append(f"MHD component for {source_id}: {problem}")

    def validate_ground_truth(self, entry: dict, source_id: str, errors: list[str], warnings: list[str]) -> None:
        evidence = entry.get("ground_truth")
        if not isinstance(evidence, dict):
            errors.append(f"Structured ground_truth evidence is required: {source_id}")
            return
        kind = evidence.get("type")
        if kind not in GROUND_TRUTH_TYPES:
            errors.append(f"Invalid ground_truth type: {source_id}")
            return
        role = entry.get("role")
        if kind == "unavailable":
            if role != "real_technical_only":
                errors.append(f"Unavailable GT cannot authorize geometric evaluation: {source_id}")
            if not nonempty_text(evidence.get("reason")):
                errors.append(f"Unavailable GT requires a reason: {source_id}")
            warnings.append(f"No verified geometric GT for {source_id}: technical/descriptive evaluation only")
            return
        if role == "real_technical_only":
            errors.append(f"Technical-only source cannot declare geometric GT: {source_id}")
        if kind == "synthetic_created_after_freeze":
            text_fields = (
                "generator_id", "generator_version", "interpolation",
                "border_overlap_policy", "release_freeze_id",
            )
            for field in text_fields:
                if not nonempty_text(evidence.get(field)):
                    errors.append(f"Synthetic GT missing {field}: {source_id}")
            if evidence.get("coordinate_convention") != "moving_to_fixed":
                errors.append(f"Synthetic GT must use moving_to_fixed coordinates: {source_id}")
            seeds = evidence.get("seeds")
            if (not isinstance(seeds, list) or not seeds or
                    any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds) or
                    len(set(seeds)) != len(seeds)):
                errors.append(f"Synthetic GT requires unique integer seeds: {source_id}")
            for prefix in ("config", "case_spec", "manifest"):
                problem = check_path_hash(
                    self.root, evidence.get(f"{prefix}_path"), evidence.get(f"{prefix}_sha256")
                )
                if problem:
                    errors.append(f"Synthetic GT {prefix} for {source_id}: {problem}")
            return
        for field in (
            "provenance", "reference_or_license", "units",
            "coordinate_convention", "validation_notes",
        ):
            if not nonempty_text(evidence.get(field)):
                errors.append(f"{kind} missing {field}: {source_id}")
        labels = evidence.get("label_files")
        if not isinstance(labels, list) or not labels:
            errors.append(f"{kind} requires label_files: {source_id}")
            return
        manifest_problem = check_path_hash(
            self.root, evidence.get("manifest_path"), evidence.get("manifest_sha256")
        )
        if manifest_problem:
            errors.append(f"{kind} manifest for {source_id}: {manifest_problem}")
        for label in labels:
            if not isinstance(label, dict) or not nonempty_text(label.get("role")):
                errors.append(f"Malformed label record: {source_id}")
                continue
            label_format = normalized_format(label.get("path"))
            allowed = LANDMARK_FORMATS if kind == "verified_landmarks" else SUPPORTED_IMAGE_FORMATS
            if label.get("format") != label_format or label_format not in allowed:
                errors.append(f"Unsupported label format for {source_id}: {label.get('path')}")
            problem = check_path_hash(self.root, label.get("path"), label.get("sha256"))
            if problem:
                errors.append(f"Label evidence for {source_id}: {problem}")

    def validate_source_entry(
        self, entry: Any, *, known: bool, errors: list[str], warnings: list[str]
    ) -> str:
        if not isinstance(entry, dict):
            errors.append("Source record is not an object")
            return "<invalid>"
        source_id = entry.get("source_id") if nonempty_text(entry.get("source_id")) else "<missing>"
        required_text = ("source_id", "path", "sha256", "format", "modality", "role", "reference_or_license")
        for field in required_text:
            if not nonempty_text(entry.get(field)):
                errors.append(f"Missing {field}: {source_id}")
        if not is_sha256(entry.get("sha256")):
            errors.append(f"Invalid SHA-256 syntax: {source_id}")
        if entry.get("role") not in SOURCE_ROLES:
            errors.append(f"Invalid role: {source_id}")
        if type(entry.get("previously_used")) is not bool:
            errors.append(f"previously_used must be Boolean: {source_id}")
        elif known and entry["previously_used"] is not True:
            errors.append(f"Known source must be previously_used: {source_id}")
        usage = entry.get("prior_usage")
        if (not isinstance(usage, list) or any(not nonempty_text(value) for value in usage) or
                (known and not usage)):
            errors.append(f"prior_usage must be a valid string list: {source_id}")
        elif entry.get("previously_used") is True and not usage:
            errors.append(f"Previously used source requires prior_usage: {source_id}")
        elif entry.get("previously_used") is False and usage:
            errors.append(f"Unused source must have empty prior_usage: {source_id}")
        actual_format = normalized_format(entry.get("path"))
        if entry.get("format") not in SUPPORTED_IMAGE_FORMATS or entry.get("format") != actual_format:
            errors.append(f"Unsupported or mismatched image format: {source_id}")
        path = safe_file(self.root, entry.get("path"))
        if path is None:
            errors.append(f"Unsafe source path: {source_id}")
        elif not path.is_file():
            errors.append(f"Missing source file: {source_id}")
        elif is_sha256(entry.get("sha256")):
            try:
                if digest(path) != entry["sha256"]:
                    errors.append(f"Source checksum mismatch: {source_id}")
            except OSError as exc:
                errors.append(f"Cannot hash source {source_id}: {exc}")
        self.validate_lineage(entry, source_id, errors)
        self.validate_mhd_components(entry, source_id, errors)
        if not known:
            self.validate_ground_truth(entry, source_id, errors, warnings)
        return source_id

    def sources(self) -> None:
        ledger_path = self.checked_file(LEDGER_REL.as_posix(), "source_use_ledger")
        if ledger_path is None:
            self.add("prior_source_inventory", "BLOCK", "Source ledger is unavailable")
            self.add("heldout_source_independence", "BLOCK", "Source ledger is unavailable")
            return
        schema_errors: list[str] = []
        inventory_errors: list[str] = []
        source_errors: list[str] = []
        warnings: list[str] = []
        known: list[dict] = []
        reserved: list[dict] = []
        try:
            ledger = read_json(ledger_path)
            if not isinstance(ledger, dict):
                raise TypeError("source-use ledger must be a JSON object")
            if ledger.get("schema_version") != 2:
                schema_errors.append("source ledger schema_version must be 2")
            known = ledger.get("known_prior_sources")
            reserved = ledger.get("week08_sources")
            if not isinstance(known, list):
                schema_errors.append("known_prior_sources must be a list")
                known = []
            if not isinstance(reserved, list):
                schema_errors.append("week08_sources must be a list")
                reserved = []
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            schema_errors.append(f"Invalid source-use ledger: {exc}")

        if isinstance(known, list):
            canonical_known = json.dumps(
                known, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if hashlib.sha256(canonical_known).hexdigest() != KNOWN_PRIOR_INVENTORY_SHA256:
                inventory_errors.append("Known prior-source canonical inventory does not match the Phase 2 anchor")

        known_ids: set[str] = set()
        known_paths: set[str] = set()
        known_hashes: set[str] = set()
        known_canonical_sources: set[str] = set()
        known_lineage: set[str] = set()
        known_cases: set[tuple[Any, Any, Any]] = set()
        for entry in known:
            source_id = self.validate_source_entry(entry, known=True, errors=schema_errors, warnings=warnings)
            if source_id in known_ids:
                schema_errors.append(f"Duplicate known source_id: {source_id}")
            known_ids.add(source_id)
            if isinstance(entry, dict):
                path = entry.get("path") if isinstance(entry.get("path"), str) else "<invalid-path>"
                source_hash = entry.get("sha256") if isinstance(entry.get("sha256"), str) else "<invalid-hash>"
                canonical_source = (
                    entry.get("canonical_source_id")
                    if isinstance(entry.get("canonical_source_id"), str) else "<invalid-source>"
                )
                case = tuple(
                    entry.get(field) if isinstance(entry.get(field), str) else f"<invalid-{field}>"
                    for field in ("canonical_dataset_id", "canonical_subject_id", "canonical_case_id")
                )
                if path in known_paths:
                    schema_errors.append(f"Duplicate known source path: {source_id}")
                if source_hash in known_hashes:
                    schema_errors.append(f"Duplicate known source hash: {source_id}")
                if canonical_source in known_canonical_sources:
                    schema_errors.append(f"Duplicate known canonical source: {source_id}")
                known_paths.add(path)
                known_hashes.add(source_hash)
                known_canonical_sources.add(canonical_source)
                ancestors = entry.get("lineage_ancestors") if isinstance(entry.get("lineage_ancestors"), list) else []
                known_lineage.add(canonical_source)
                known_lineage.update(value for value in ancestors if isinstance(value, str))
                known_cases.add(case)

        try:
            general = read_json(self.root / GENERAL_SOURCES_REL)
            rire = read_json(self.root / RIRE_SOURCES_REL)
            expected = {(row["path"], row["sha256"]) for row in general["records"]}
            for row in rire["records"]:
                expected.add((row["fixed_image"], row["fixed_sha256"]))
                expected.add((row["moving_image"], row["moving_sha256"]))
            expected.update(
                (path, record["sha256"])
                for path, record in REQUIRED_WEEK01_SOURCES.items()
            )
            observed = {(entry.get("path"), entry.get("sha256")) for entry in known if isinstance(entry, dict)}
            missing = expected - observed
            if missing:
                inventory_errors.extend(f"Missing required prior source: {path}" for path, _ in sorted(missing))
            by_path = {
                entry.get("path"): entry for entry in known
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            }
            for path, required in REQUIRED_WEEK01_SOURCES.items():
                entry = by_path.get(path)
                if entry is None:
                    continue
                if entry.get("source_id") != required["source_id"]:
                    inventory_errors.append(f"Week 1 source_id mismatch: {path}")
                if entry.get("canonical_source_id") != required["canonical_source_id"]:
                    inventory_errors.append(f"Week 1 canonical identity mismatch: {path}")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            inventory_errors.append(f"Cannot reconcile prior-source manifests: {exc}")

        reserved_ids: set[str] = set()
        reserved_paths: set[str] = set()
        reserved_hashes: set[str] = set()
        reserved_sources: set[str] = set()
        independent_count = 0
        for entry in reserved:
            source_id = self.validate_source_entry(entry, known=False, errors=source_errors, warnings=warnings)
            if source_id in reserved_ids:
                source_errors.append(f"Duplicate reserved source_id: {source_id}")
            if source_id in known_ids:
                source_errors.append(f"Reserved source_id collides with prior inventory: {source_id}")
            reserved_ids.add(source_id)
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") if isinstance(entry.get("path"), str) else "<invalid-path>"
            sha = entry.get("sha256") if isinstance(entry.get("sha256"), str) else "<invalid-hash>"
            canonical_source = (
                entry.get("canonical_source_id")
                if isinstance(entry.get("canonical_source_id"), str) else "<invalid-source>"
            )
            case = tuple(
                entry.get(field) if isinstance(entry.get(field), str) else f"<invalid-{field}>"
                for field in ("canonical_dataset_id", "canonical_subject_id", "canonical_case_id")
            )
            ancestors = {
                value for value in entry.get("lineage_ancestors", []) if isinstance(value, str)
            } if isinstance(entry.get("lineage_ancestors"), list) else set()
            if path in reserved_paths or sha in reserved_hashes or canonical_source in reserved_sources:
                source_errors.append(f"Duplicate held-out identity: {source_id}")
            reserved_paths.add(path); reserved_hashes.add(sha); reserved_sources.add(canonical_source)
            role = entry.get("role")
            previously_used = entry.get("previously_used")
            collides = path in known_paths or sha in known_hashes or canonical_source in known_lineage or bool(ancestors & known_lineage) or case in known_cases
            if role == "full_project_independent":
                independent_count += 1
                if previously_used is not False or collides:
                    source_errors.append(f"Previously used or derivative source claimed independent: {source_id}")
                if not str(path).startswith("data/holdout/week08/"):
                    source_errors.append(f"Independent source must be staged under data/holdout/week08: {source_id}")
            elif role in {"policy_transfer_check", "real_technical_only"} and previously_used is not True:
                source_errors.append(f"Transfer/technical source must be marked previously_used: {source_id}")
        if independent_count == 0:
            source_errors.append("No genuinely new full-project independent source declared")

        self.add("source_ledger_schema", "BLOCK" if schema_errors else "PASS",
                 "Source-use ledger v2 schema and lineage evidence validated", errors=schema_errors[:40])
        self.add("prior_source_inventory", "BLOCK" if inventory_errors else "PASS",
                 "Week 1, general-image and RIRE prior identities reconcile to the ledger",
                 errors=inventory_errors[:20])
        combined = schema_errors + inventory_errors + source_errors
        self.add("heldout_source_independence", "BLOCK" if combined else "PASS",
                 "Metadata, lineage and byte-level source audit (no pixel decoding)",
                 errors=combined[:60], warnings=warnings, sources=len(reserved))
        if warnings:
            self.add("ground_truth_availability", "WARN", "; ".join(warnings))

    def final_workspace(self) -> None:
        for rel in ("outputs/week08_final", "outputs/week08_holdout"):
            p = safe_file(self.root, rel)
            if p is None or (p.exists() and (not p.is_dir() or any(p.iterdir()))):
                self.add("clean_" + rel.split("/")[-1], "BLOCK", f"Final-test output must be absent or empty: {rel}")
            else:
                self.add("clean_" + rel.split("/")[-1], "PASS", f"Clean final-test output location: {rel}")
        runner_missing = [
            rel for rel in FINAL_RUNNER_PATHS
            if not (safe_file(self.root, rel) or Path()).is_file()
        ]
        runner_errors: list[str] = []
        runner_observed: dict[str, Any] = {}
        if not runner_missing:
            runner_errors, runner_observed = verify_week08_runner_contract(self.root)
        if runner_missing:
            runner_status = "BLOCK" if self.final_readiness else "WARN"
            details = (
                "Week 8 runner/config/tests are missing; deterministic IDs and "
                "decision-before-label ordering are not enforced"
            )
        elif runner_errors:
            evidence_state = (
                runner_observed.get("phase3_evidence", {}).get("state")
                if isinstance(runner_observed.get("phase3_evidence"), dict)
                else None
            )
            only_missing_evidence = (
                evidence_state == "missing"
                and runner_errors == [f"missing {PHASE3_EVALUATOR_REPORT_REL.as_posix()}"]
            )
            runner_status = (
                "BLOCK" if self.final_readiness or not only_missing_evidence else "WARN"
            )
            details = (
                "Week 8 evaluator evidence or executable metadata-only smoke probe did not verify"
            )
        else:
            runner_status = "PASS"
            details = (
                "Tracked G3 evaluator evidence hashes and the metadata-only runner smoke probe passed"
            )
        self.add(
            "week08_runner_identity_contract",
            runner_status,
            details,
            missing=runner_missing,
            errors=runner_errors,
            observed=runner_observed,
        )

    def strict_release_gates(self) -> None:
        release: dict[str, Any] = {}
        release_errors: list[str] = []
        release_path = safe_file(self.root, RELEASE_MANIFEST_REL.as_posix())
        if release_path is None or not release_path.is_file():
            release_errors.append(f"missing {RELEASE_MANIFEST_REL.as_posix()}")
        else:
            try:
                release = read_json(release_path)
                if not isinstance(release, dict):
                    raise TypeError("release manifest must be a JSON object")
                if release.get("schema_version") != RELEASE_MANIFEST_VERSION:
                    release_errors.append("unsupported release manifest schema_version")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                release_errors.append(f"invalid release manifest: {exc}")
        self.add("strict_release_manifest", "BLOCK" if release_errors else "PASS",
                 "Release manifest is present and parseable", errors=release_errors)

        git_errors, git_state = verify_release_git(
            self.root, release.get("release_commit"), release.get("release_tag")
        )
        if release.get("clean_worktree") is not True:
            git_errors.append("release manifest does not attest a clean worktree")
        self.add("strict_release_commit_tag", "BLOCK" if git_errors else "PASS",
                 "Git verifies the tagged release ancestor and current clean worktree",
                 errors=git_errors, observed=git_state)

        artifacts = release.get("artifacts") if isinstance(release.get("artifacts"), dict) else {}
        required_artifacts = {
            *FINAL_RUNNER_PATHS,
            PHASE3_EVALUATOR_REPORT_REL.as_posix(),
            FROZEN_REL.as_posix(),
            LEDGER_REL.as_posix(),
            INTEGRITY_ANCHOR_REL.as_posix(),
            EVIDENCE_ARCHIVE_MANIFEST_REL.as_posix(),
            "scripts/week08_preflight.py",
            "tests/test_week08_preflight.py",
            REQUIRED_EVIDENCE["day34_policy"],
            VALIDATION_REL.as_posix(),
            STAGE_B_VALIDATION_REL.as_posix(),
            RELEASE_CHECKLIST_REL.as_posix(),
            SOURCE_REGISTRATION_REL.as_posix(),
            HOLDOUT_SOURCE_MANIFEST_REL.as_posix(),
        }
        artifact_errors: list[str] = []
        for rel in sorted(required_artifacts):
            expected = artifacts.get(rel)
            problem = check_path_hash(self.root, rel, expected)
            if problem:
                artifact_errors.append(problem)
        self.add("strict_policy_config_analysis_hashes", "BLOCK" if artifact_errors else "PASS",
                 "Runner, policy/config, preflight and evidence artifacts are release-bound",
                 errors=artifact_errors[:30])

        validation_path = safe_file(self.root, VALIDATION_REL.as_posix())
        validation: dict[str, Any] = {}
        validation_errors: list[str] = []
        if validation_path is None or not validation_path.is_file():
            validation_errors.append(f"missing {VALIDATION_REL.as_posix()}")
        else:
            try:
                validation = read_json(validation_path)
                if not isinstance(validation, dict):
                    raise TypeError("validation report must be a JSON object")
                if validation.get("schema_version") != VALIDATION_VERSION:
                    validation_errors.append("unsupported validation report schema_version")
                if validation.get("runner_contract_passed") is not True:
                    validation_errors.append("runner identity/firewall contract is not passed")
                if validation.get("full_regression_zero_failures") is not True:
                    validation_errors.append("full regression zero-failure record is absent")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                validation_errors.append(f"invalid validation report: {exc}")
        self.add("strict_runner_validation", "BLOCK" if validation_errors else "PASS",
                 "Focused runner/firewall and full regression evidence is passed", errors=validation_errors)

        restoration_errors: list[str] = []
        if validation.get("clean_staging_restoration_passed") is not True:
            restoration_errors.append("clean-staging evidence restoration is not passed")
        expected_archive_hash = self.evidence_archive_record.get("sha256")
        if not is_sha256(expected_archive_hash) or validation.get("evidence_archive_sha256") != expected_archive_hash:
            restoration_errors.append("restoration evidence is not bound to the verified archive")
        self.add("strict_clean_staging_restoration", "BLOCK" if restoration_errors else "PASS",
                 "Clean staging restored the release-bound Week 7 evidence archive",
                 errors=restoration_errors)

        stage_b_path = safe_file(self.root, STAGE_B_VALIDATION_REL.as_posix())
        stage_b_errors: list[str] = []
        stage_b: dict[str, Any] = {}
        stage_b_binding: dict[str, Any] = {}
        if stage_b_path is None or not stage_b_path.is_file():
            stage_b_errors.append(f"missing {STAGE_B_VALIDATION_REL.as_posix()}")
        else:
            try:
                stage_b = read_json(stage_b_path)
                if not isinstance(stage_b, dict):
                    raise TypeError("Stage B validation must be a JSON object")
                stage_b_errors.extend(validate_stage_b_validation_report(stage_b))
                binding_errors, stage_b_binding = verify_stage_b_release_binding(
                    self.root,
                    stage_b.get("tested_release_commit"),
                    release.get("release_commit"),
                )
                stage_b_errors.extend(binding_errors)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                stage_b_errors.append(f"invalid Stage B validation: {exc}")
        self.add("strict_stage_b_acceptance", "BLOCK" if stage_b_errors else "PASS",
                 "Tracked Stage B acceptance is 5/5 and UI v0.2 is frozen",
                 errors=stage_b_errors, observed=stage_b_binding)

        checklist_path = safe_file(self.root, RELEASE_CHECKLIST_REL.as_posix())
        signoff_ok = checklist_path is not None and checklist_path.is_file() and release.get("required_signoffs_complete") is True
        self.add("strict_release_signoffs", "PASS" if signoff_ok else "BLOCK",
                 "Release checklist exists and all required signoffs are complete")

        dependency_errors: list[str] = []
        for key in ("dependency_lock", "environment_record"):
            record = release.get(key)
            if not isinstance(record, dict):
                dependency_errors.append(f"missing {key}")
                continue
            problem = check_path_hash(self.root, record.get("path"), record.get("sha256"))
            if problem:
                dependency_errors.append(problem)
        self.add("strict_dependency_environment", "BLOCK" if dependency_errors else "PASS",
                 "Dependency lock and environment record are release-bound", errors=dependency_errors)

        source_ready = self.check_status("heldout_source_independence") == "PASS"
        self.add("strict_source_enrollment", "PASS" if source_ready else "BLOCK",
                 "Independent source, lineage and ground-truth evidence are enrolled and valid")

        phase2_ready = (
            self.check_status("integrity_anchor") == "PASS" and
            self.check_status("week07_evidence_packaging") == "PASS" and
            self.check_status("frozen_sources") == "PASS" and
            self.check_status("week7_complete_evidence") == "PASS" and
            self.check_status("evidence_hashes") == "PASS" and
            self.check_status("strict_clean_staging_restoration") == "PASS"
        )
        self.add("strict_integrity_and_restoration", "PASS" if phase2_ready else "BLOCK",
                 "Integrity anchor and complete Week 7 evidence packaging verify")

    def run(self) -> dict:
        self.integrity_anchor()
        baseline, handoff = self.frozen()
        self.evidence_packaging(baseline)
        self.evidence(handoff)
        self.ground_truth_firewall()
        self.sources()
        self.final_workspace()
        if self.final_readiness:
            self.strict_release_gates()
        status = "BLOCK" if any(x["status"] == "BLOCK" for x in self.checks) else ("WARN" if any(x["status"] == "WARN" for x in self.checks) else "PASS")
        env = {"python": platform.python_version(), "platform": platform.platform(), "architecture": platform.machine(),
               "cpu_model": platform.processor() or "unavailable", "dependencies": {}}
        for pkg in ("numpy", "opencv-python", "SimpleITK", "scikit-image", "matplotlib", "pytest", "streamlit"):
            try:
                env["dependencies"][pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                env["dependencies"][pkg] = "not_installed"
        evidence_immutable = all(
            self.check_status(code) == "PASS"
            for code in (
                "integrity_anchor", "week07_evidence_packaging", "frozen_sources",
                "week7_complete_evidence", "evidence_hashes",
            )
        )
        report = {"version": VERSION, "readiness": status, "checks": self.checks,
                  "environment": env, "development_plan_metadata": self.development_metadata,
                  "mode": "final_readiness" if self.final_readiness else "development_preflight",
                  "week08_evaluation_executed": False,
                  "baseline_sha256": digest(self.root / FROZEN_REL) if (self.root / FROZEN_REL).is_file() else None,
                  "development_evidence_immutable": evidence_immutable,
                  "limitations": ["The Phase 3 runner contract is validated only on development fixtures; it does not authorize or constitute a Week 8 benchmark run.",
                                  "An unknown-ground-truth image cannot support numeric geometric correctness claims."]}
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true", help="Print report only, do not write preflight output")
    parser.add_argument(
        "--final-readiness", action="store_true",
        help="Fail closed on every missing evaluator, source, release, UI and signoff gate",
    )
    args = parser.parse_args(argv)
    audit = Audit(args.root, final_readiness=args.final_readiness)
    report = audit.run()
    for check in report["checks"]:
        print(f"[{check['status']}] {check['check']}: {check['details']}")
    print(f"Week 8 preflight readiness: {report['readiness']}")
    if not args.dry_run:
        outfile = audit.root / REPORT_REL
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Report: {outfile}")
    return 1 if report["readiness"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
