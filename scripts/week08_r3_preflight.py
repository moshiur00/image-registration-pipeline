#!/usr/bin/env python3
"""Fail-closed release and final-readiness verification for Week 8 R3.

The historical ``week08_preflight.py`` is the immutable R2 verifier.  This
module owns the corrected R3 namespace and never decodes image or label
content.  It can be used in three ways:

* :func:`validate_candidate` checks the pre-G5 implementation boundary;
* ``--technical-readiness`` requires G5 and G6 while deferring G7; and
* ``--final-readiness`` additionally requires the one-run G7 authorization.

Every check is read-only.  Raw enrolled files may be streamed for SHA-256
verification, but no image, landmark, mask, or outcome parser is imported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[1]

CYCLE_ID = "week08-r3-confirmatory-20261116"
PREFLIGHT_SCHEMA = "week08_r3_preflight_v1"
RELEASE_SCHEMA = "pre_week08_r3_release_manifest_v1"
STAGE_B_REBINDING_SCHEMA = "pre_week08_r3_stage_b_rebinding_v1"
SOURCE_REGISTRATION_SCHEMA = "pre_week08_r3_source_registration_v1"
AUTHORIZATION_SCHEMA = "pre_week08_r3_phase7_authorization_v1"
G3_REPORT_SCHEMA = "week08_r3_g3_remediation_v1"

CONFIG_REL = "configs/week08_r3_final_evaluation.yaml"
LEDGER_REL = "configs/week08_r3_source_use_ledger.json"
MANIFEST_REL = "data/manifests/week08_r3_holdout_sources.json"
G3_REL = "reports/week08_r3_g3_remediation.json"
RELEASE_REL = "reports/pre_week08_r3_release_manifest.json"
STAGE_B_BASE_REL = "reports/pre_week08_stage_b_validation.json"
STAGE_B_REBINDING_REL = "reports/pre_week08_r3_stage_b_rebinding.json"
CHECKLIST_REL = "docs/PRE_WEEK08_RELEASE_CHECKLIST_R3.md"
VALIDATION_REL = "reports/pre_week08_r3_validation.json"
SOURCE_REGISTRATION_REL = "reports/pre_week08_r3_source_registration.json"
AUTHORIZATION_REL = "reports/pre_week08_r3_phase7_authorization.json"

R3_OUTPUT_ROOTS = (
    "outputs/week08_r3_holdout",
    "outputs/week08_r3_final",
    "outputs/week08_r3_archives",
)
R2_PROHIBITED_ROOTS = (
    "data/holdout/week08",
    "outputs/week08_holdout",
    "outputs/week08_final",
    "outputs/week08_archives",
)
POST_G5_METADATA_ALLOWLIST = frozenset({
    LEDGER_REL,
    MANIFEST_REL,
    SOURCE_REGISTRATION_REL,
    AUTHORIZATION_REL,
    RELEASE_REL,
})
POST_G6_METADATA_ALLOWLIST = frozenset({AUTHORIZATION_REL, RELEASE_REL})
CRITICAL_ARTIFACTS = frozenset({
    CONFIG_REL,
    G3_REL,
    "configs/week08_frozen_baseline.json",
    "configs/week07_day01_frozen_methods.yaml",
    "outputs/week07_day04_calibration/tentative_policy_not_for_ui.json",
    "src/image_registration/week7_calibration.py",
    "src/image_registration/week8_evaluation.py",
    "scripts/week08_final_evaluation.py",
    "scripts/week08_prepare_holdout.py",
    "scripts/week08_r3_preflight.py",
    "scripts/week08_r3_reporting.py",
    "tests/test_week08_final_evaluation.py",
    "tests/test_week08_phase3_cli.py",
    "tests/test_week08_r3_preflight.py",
    STAGE_B_BASE_REL,
    STAGE_B_REBINDING_REL,
    VALIDATION_REL,
    CHECKLIST_REL,
})
REVIEW_PACKAGE_ARTIFACTS = frozenset({
    STAGE_B_REBINDING_REL,
    VALIDATION_REL,
    CHECKLIST_REL,
})
RUNTIME_BINDINGS = {
    "config_sha256": CONFIG_REL,
    "preflight_sha256": "scripts/week08_r3_preflight.py",
    "prepare_sha256": "scripts/week08_prepare_holdout.py",
    "final_evaluation_sha256": "scripts/week08_final_evaluation.py",
    "runner_sha256": "src/image_registration/week8_evaluation.py",
    "reporting_sha256": "scripts/week08_r3_reporting.py",
}
PROHIBITED_CLAIMS = [
    "anatomical_generalization",
    "clinical_recommendation",
    "external_validity",
    "modality_wide_generalization",
    "population_generalization",
]
HEX40_OR_64 = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class R3PreflightError(ValueError):
    """Raised when a caller requests a passing R3 gate and it is blocked."""


class _UniqueYamlLoader(yaml.SafeLoader):
    pass


def _unique_yaml_mapping(
    loader: _UniqueYamlLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
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


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueYamlLoader)
    if not isinstance(value, dict):
        raise ValueError(f"YAML artifact must be an object: {path}")
    return value


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_utc(value: Any) -> bool:
    return isinstance(value, str) and UTC_TIMESTAMP.fullmatch(value) is not None


def safe_file(root: Path, relative: Any) -> Path | None:
    """Return a repository-contained lexical path without following links."""
    if not isinstance(relative, str) or not relative or "\\" in relative or "\0" in relative:
        return None
    windows = PureWindowsPath(relative)
    posix = PurePosixPath(relative)
    if windows.drive or windows.root or relative.startswith("/"):
        return None
    if any(part in {"", ".", ".."} for part in posix.parts):
        return None
    current = root.absolute()
    try:
        for part in posix.parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or bool(
                getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                return None
        return current
    except (OSError, RuntimeError, ValueError):
        return None


def checked_hash(root: Path, relative: Any, expected: Any) -> str | None:
    path = safe_file(root, relative)
    if path is None:
        return f"unsafe project-relative path: {relative!r}"
    if not path.is_file():
        return f"missing file: {relative}"
    if not is_sha256(expected):
        return f"invalid expected SHA-256: {relative}"
    observed = sha256_file(path)
    if observed != expected:
        return f"SHA-256 mismatch: {relative}"
    return None


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.resolve().as_posix()}",
            "-C",
            str(root.resolve()),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _resolve_commit(root: Path, value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or HEX40_OR_64.fullmatch(value) is None:
        errors.append(f"{label} must be a full lowercase Git object ID")
        return None
    result = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
    if result.returncode != 0:
        errors.append(f"cannot resolve {label}")
        return None
    resolved = result.stdout.strip().lower()
    if resolved != value:
        errors.append(f"{label} does not resolve to itself")
        return None
    return resolved


def _changed_paths(root: Path, older: str, newer: str, errors: list[str]) -> list[str]:
    result = _git(root, "log", "--format=", "--name-only", "-z", f"{older}..{newer}", "--")
    if result.returncode != 0:
        errors.append(f"cannot inspect Git changes from {older} to {newer}")
        return []
    return sorted({item.strip() for item in result.stdout.split("\0") if item.strip()})


def _stage_b_protected_path(path: str) -> bool:
    if path in {"pyproject.toml", "requirements.txt"}:
        return True
    if any(path.startswith(prefix) for prefix in ("src/", "scripts/", "configs/", "tests/")):
        return True
    return path.startswith("ui/") and PurePosixPath(path).suffix.lower() != ".md"


def _self_hash_errors(record: Mapping[str, Any], field: str, label: str) -> list[str]:
    expected = record.get(field)
    payload = dict(record)
    payload.pop(field, None)
    if not is_sha256(expected) or canonical_sha256(payload) != expected:
        return [f"{label} self-hash mismatch"]
    return []


def _config_errors(root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    path = safe_file(root, CONFIG_REL)
    if path is None or not path.is_file():
        return [f"missing {CONFIG_REL}"], {}
    try:
        config = read_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"invalid R3 config: {exc}"], {}
    if config.get("schema_version") != "week08_final_evaluation_v2":
        errors.append("R3 config schema_version is not v2")
    if config.get("cycle_id") != CYCLE_ID:
        errors.append("R3 config cycle_id mismatch")
    if config.get("state") != "r3_g3_remediation_in_progress_no_source_access":
        errors.append("R3 config state was mutated after preregistration")
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    authorization = (
        safety.get("phase7_authorization")
        if isinstance(safety.get("phase7_authorization"), dict)
        else {}
    )
    expected_authorization = {
        "release_manifest_path": RELEASE_REL,
        "release_manifest_schema_version": RELEASE_SCHEMA,
        "authorization_path": AUTHORIZATION_REL,
        "authorization_schema_version": AUTHORIZATION_SCHEMA,
        "source_registration_path": SOURCE_REGISTRATION_REL,
    }
    for field, expected in expected_authorization.items():
        if authorization.get(field) != expected:
            errors.append(f"R3 config Phase 7 {field} mismatch")
    if authorization.get("required_for_final_readiness") is not True:
        errors.append("R3 config does not require G7 for final readiness")
    if safety.get("plan_and_dry_run_forbid_image_or_label_decoding") is not True:
        errors.append("R3 metadata planning is not fail-closed")
    sources = config.get("sources") if isinstance(config.get("sources"), dict) else {}
    if sources.get("ledger_path") != LEDGER_REL:
        errors.append("R3 config names the wrong source ledger")
    if sources.get("enrollment_manifest_path") != MANIFEST_REL:
        errors.append("R3 config names the wrong enrollment manifest")
    artifacts = config.get("artifact_paths") if isinstance(config.get("artifact_paths"), dict) else {}
    actual_roots = (
        artifacts.get("final_prepare_root"),
        artifacts.get("final_decision_root"),
        artifacts.get("archive_root"),
    )
    if actual_roots != R3_OUTPUT_ROOTS:
        errors.append("R3 output roots differ from the frozen namespace")
    frozen = config.get("frozen_assets") if isinstance(config.get("frozen_assets"), dict) else {}
    for name in ("method_catalog", "policy", "observable_projection", "frozen_baseline"):
        descriptor = frozen.get(name) if isinstance(frozen.get(name), dict) else {}
        relative = descriptor.get("path", descriptor.get("implementation_file"))
        issue = checked_hash(root, relative, descriptor.get("sha256"))
        if issue:
            errors.append(f"{name}: {issue}")
    return errors, config


def _g3_errors(root: Path) -> tuple[list[str], dict[str, Any]]:
    path = safe_file(root, G3_REL)
    if path is None or not path.is_file():
        return [f"missing {G3_REL}"], {}
    try:
        report = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid G3 report: {exc}"], {}
    errors = _self_hash_errors(report, "report_payload_sha256", "R3 G3 report")
    if report.get("schema_version") != G3_REPORT_SCHEMA:
        errors.append("unsupported R3 G3 report schema")
    if report.get("cycle_id") != CYCLE_ID or report.get("status") != "PASS_TECHNICAL_REMEDIATION":
        errors.append("R3 G3 technical remediation is not passing")
    review = report.get("review_status") if isinstance(report.get("review_status"), dict) else {}
    if review.get("g5_release_freeze_approved") is not False:
        errors.append("historical G3 report improperly claims G5 approval")
    counters = report.get("activity_counters") if isinstance(report.get("activity_counters"), dict) else {}
    if not counters or any(value != 0 for value in counters.values()):
        errors.append("historical G3 report does not attest zero R3 activity")
    return errors, report


def _zero_access_errors(root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed: dict[str, Any] = {}
    try:
        ledger = read_json(root / LEDGER_REL)
        manifest = read_json(root / MANIFEST_REL)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid R3 zero-access metadata: {exc}"], observed
    if ledger.get("schema_version") != "week08_r3_source_use_ledger_v1":
        errors.append("R3 ledger schema mismatch")
    fresh = ledger.get("fresh_sources")
    if fresh != []:
        errors.append("fresh source appeared before the G5 freeze")
    enrollment = ledger.get("enrollment") if isinstance(ledger.get("enrollment"), dict) else {}
    for field in ("source_bytes_accessed_in_r3", "labels_accessed_in_r3", "outcomes_accessed_in_r3"):
        if enrollment.get(field) != 0:
            errors.append(f"R3 ledger {field} is not zero")
    if manifest.get("source_ids") != [] or manifest.get("pairs") != []:
        errors.append("R3 holdout manifest is not empty before G5")
    if manifest.get("source_bytes_accessed") != 0 or manifest.get("labels_accessed") != 0:
        errors.append("R3 holdout manifest records premature access")
    if manifest.get("execution_authorized") is not False:
        errors.append("R3 holdout manifest authorizes execution before G7")
    existing_outputs: list[str] = []
    for relative in R3_OUTPUT_ROOTS:
        path = root / relative
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            existing_outputs.append(relative)
    if existing_outputs:
        errors.append("R3 evidence outputs exist before G7: " + ", ".join(existing_outputs))
    observed.update({
        "fresh_source_count": len(fresh) if isinstance(fresh, list) else None,
        "existing_output_roots": existing_outputs,
    })
    ignored = _git(root, "check-ignore", "--quiet", "data/holdout/week08_r3/probe.bin")
    if ignored.returncode != 0:
        errors.append("R3 private holdout intake is not ignored by Git")
    return errors, observed


def validate_candidate(root: Path = ROOT) -> dict[str, Any]:
    """Validate the implementation boundary before a human G5 review."""
    checks: list[dict[str, Any]] = []
    config_errors, config = _config_errors(root)
    checks.append({
        "check": "candidate_config_contract",
        "status": "PASS" if not config_errors else "BLOCK",
        "errors": config_errors,
    })
    g3_errors, g3 = _g3_errors(root)
    checks.append({
        "check": "candidate_g3_baseline",
        "status": "PASS" if not g3_errors else "BLOCK",
        "errors": g3_errors,
    })
    access_errors, access = _zero_access_errors(root)
    checks.append({
        "check": "candidate_zero_access_boundary",
        "status": "PASS" if not access_errors else "BLOCK",
        "errors": access_errors,
        "observed": access,
    })
    runtime_errors: list[str] = []
    for relative in sorted(CRITICAL_ARTIFACTS - REVIEW_PACKAGE_ARTIFACTS):
        path = safe_file(root, relative)
        if path is None or not path.is_file():
            runtime_errors.append(f"missing candidate artifact: {relative}")
    checks.append({
        "check": "candidate_runtime_surface",
        "status": "PASS" if not runtime_errors else "BLOCK",
        "errors": runtime_errors,
    })
    readiness = "BLOCK" if any(item["status"] == "BLOCK" for item in checks) else "PASS"
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "cycle_id": CYCLE_ID,
        "mode": "g5_candidate",
        "readiness": readiness,
        "checks": checks,
        "config_sha256": sha256_file(root / CONFIG_REL) if config else None,
        "g3_report_payload_sha256": g3.get("report_payload_sha256"),
        "source_or_label_decoded": False,
        "week08_evaluation_executed": False,
    }


EXPECTED_RELEASE_FIELDS = {
    "schema_version",
    "cycle_id",
    "release_id",
    "gate",
    "status",
    "generated_utc",
    "implementation_checkpoint",
    "release_commit",
    "release_tag",
    "proposed_release_tag",
    "clean_worktree",
    "required_signoffs_complete",
    "reviewer",
    "stage_b_binding",
    "dependency_environment",
    "artifacts",
    "post_release_metadata_allowlist",
    "g6_enrollment",
    "g7_authorization",
    "final_readiness",
    "activity_counters",
    "limitations",
}


def _pending_release_record_errors(release: Mapping[str, Any]) -> list[str]:
    """Validate the human-unapproved form used for the G5 review package."""
    errors: list[str] = []
    if set(release) != EXPECTED_RELEASE_FIELDS:
        errors.append("pending R3 release manifest fields are not exact")
    if release.get("schema_version") != RELEASE_SCHEMA:
        errors.append("pending R3 release manifest schema mismatch")
    if release.get("cycle_id") != CYCLE_ID or release.get("gate") != "G5":
        errors.append("pending R3 release cycle or gate mismatch")
    if release.get("status") != "R3_REVIEW_PENDING":
        errors.append("pending R3 release status is not R3_REVIEW_PENDING")
    if not nonempty(release.get("release_id")):
        errors.append("pending R3 release_id is missing")
    if release.get("release_id") != release.get("proposed_release_tag"):
        errors.append("pending R3 release_id and proposed tag differ")
    if release.get("release_commit") is not None or release.get("release_tag") is not None:
        errors.append("pending R3 package must not invent a release commit or tag")
    if release.get("required_signoffs_complete") is not False:
        errors.append("pending R3 package claims completed signoffs")
    reviewer = release.get("reviewer") if isinstance(release.get("reviewer"), dict) else {}
    if set(reviewer) != {"requested_reviewer", "name", "role", "decision", "attested_utc"}:
        errors.append("pending R3 reviewer fields are not exact")
    if (
        not nonempty(reviewer.get("requested_reviewer"))
        or reviewer.get("name") is not None
        or reviewer.get("role") != "release reviewer"
        or reviewer.get("decision") != "PENDING"
        or reviewer.get("attested_utc") is not None
    ):
        errors.append("pending R3 reviewer state is not explicitly unapproved")
    if release.get("post_release_metadata_allowlist") != sorted(POST_G5_METADATA_ALLOWLIST):
        errors.append("pending R3 post-G5 allowlist is not exact")
    g6 = release.get("g6_enrollment") if isinstance(release.get("g6_enrollment"), dict) else {}
    if g6 != {
        "status": "BLOCKED_PENDING_G5_AND_FRESH_SOURCE",
        "reviewed_commit": None,
        "source_ids": [],
        "source_ledger_sha256": None,
        "holdout_manifest_sha256": None,
        "source_registration_sha256": None,
    }:
        errors.append("pending R3 package does not keep G6 blocked")
    g7 = release.get("g7_authorization") if isinstance(release.get("g7_authorization"), dict) else {}
    if g7 != {"status": "BLOCKED_PENDING_G5_G6", "authorization_id": None, "authorization_sha256": None}:
        errors.append("pending R3 package does not keep G7 blocked")
    final = release.get("final_readiness") if isinstance(release.get("final_readiness"), dict) else {}
    if final != {
        "authorized": False,
        "release_reviewer_approval_pending": True,
        "expected_remaining_blocks": ["G5", "G6", "G7"],
        "week08_benchmark_executed": False,
        "real_week08_pixels_accessed": False,
        "real_week08_labels_accessed": False,
    }:
        errors.append("pending R3 final-readiness state is not exact")
    counters = release.get("activity_counters") if isinstance(release.get("activity_counters"), dict) else {}
    if counters != {
        "fresh_sources_enrolled": 0,
        "source_bytes_decoded": 0,
        "labels_accessed": 0,
        "registration_attempts": 0,
        "policy_decisions": 0,
        "evaluation_runs": 0,
    }:
        errors.append("pending R3 activity counters are not exactly zero")
    return errors


def _pending_stage_b_errors(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "stage", "status", "basis", "candidate",
        "automated_validation", "inheritance", "reviewer", "week8_heldout_used",
    }
    if set(report) != expected_fields or report.get("schema_version") != STAGE_B_REBINDING_SCHEMA:
        errors.append("pending R3 Stage B schema or fields are invalid")
    if report.get("stage") != "pre_week08_stage_b_release_rebinding":
        errors.append("pending R3 Stage B stage identifier is wrong")
    if report.get("status") != "PENDING_REVIEW" or report.get("week8_heldout_used") is not False:
        errors.append("pending R3 Stage B status or held-out-use declaration is invalid")
    inheritance = report.get("inheritance") if isinstance(report.get("inheritance"), dict) else {}
    if inheritance != {
        "manual_scenarios_inherited": 5,
        "supplemental_checks_inherited": 5,
        "evidence_unchanged": True,
        "manual_evidence_rerun": False,
    }:
        errors.append("pending R3 Stage B inheritance is not exact")
    validation = (
        report.get("automated_validation")
        if isinstance(report.get("automated_validation"), dict)
        else {}
    )
    full = validation.get("full_suite") if isinstance(validation.get("full_suite"), dict) else {}
    if (
        not isinstance(full.get("collected"), int)
        or not isinstance(full.get("passed"), int)
        or full.get("collected", 0) <= 0
        or full.get("passed", 0) <= 0
        or full.get("skipped", -1) < 0
        or full.get("failed") != 0
        or full.get("passed", 0) + full.get("skipped", 0) != full.get("collected")
    ):
        errors.append("pending R3 Stage B full-suite result is invalid")
    reviewer = report.get("reviewer") if isinstance(report.get("reviewer"), dict) else {}
    if reviewer != {
        "requested_reviewer": "Md Moshiur Rahman",
        "name": None,
        "role": "release reviewer",
        "decision": "PENDING",
        "attested_utc": None,
    }:
        errors.append("pending R3 Stage B reviewer state is not explicitly unapproved")
    return errors


def validate_review_package(root: Path = ROOT) -> dict[str, Any]:
    """Validate a tracked, clean, still-unapproved G5 review package."""
    errors: list[str] = []
    observed: dict[str, Any] = {}
    try:
        release = read_json(root / RELEASE_REL)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": PREFLIGHT_SCHEMA,
            "cycle_id": CYCLE_ID,
            "mode": "g5_review_package",
            "readiness": "BLOCK",
            "errors": [f"invalid pending R3 release manifest: {exc}"],
        }
    errors.extend(_pending_release_record_errors(release))
    implementation_errors: list[str] = []
    implementation = _resolve_commit(
        root,
        release.get("implementation_checkpoint"),
        "R3 review implementation checkpoint",
        implementation_errors,
    )
    errors.extend(implementation_errors)
    head_result = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    head = head_result.stdout.strip().lower() if head_result.returncode == 0 else None
    if head is None:
        errors.append("cannot resolve the R3 review-package HEAD")
    elif implementation:
        if _git(root, "merge-base", "--is-ancestor", implementation, head).returncode != 0:
            errors.append("R3 implementation checkpoint is not an ancestor of the review package")
        else:
            tail = _changed_paths(root, implementation, head, errors)
            observed["review_tail_changed_paths"] = tail
            forbidden = [
                item for item in tail
                if not item.startswith("docs/") and not item.startswith("reports/")
            ]
            if forbidden:
                errors.append("R3 review-package tail exceeds docs/reports: " + ", ".join(forbidden))
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0 or status.stdout.strip():
        errors.append("R3 review-package worktree is not clean")
    observed["worktree_status"] = status.stdout.splitlines()

    artifacts = release.get("artifacts") if isinstance(release.get("artifacts"), dict) else {}
    if set(artifacts) != CRITICAL_ARTIFACTS:
        errors.append("pending R3 artifact inventory is not exact")
    for relative in sorted(CRITICAL_ARTIFACTS):
        issue = checked_hash(root, relative, artifacts.get(relative))
        if issue:
            errors.append(issue)
    dependency = (
        release.get("dependency_environment")
        if isinstance(release.get("dependency_environment"), dict)
        else {}
    )
    for path_field, hash_field in (
        ("lock_path", "lock_sha256"),
        ("environment_path", "environment_sha256"),
    ):
        issue = checked_hash(root, dependency.get(path_field), dependency.get(hash_field))
        if issue:
            errors.append(issue)

    try:
        stage = read_json(root / STAGE_B_REBINDING_REL)
        errors.extend(_pending_stage_b_errors(stage))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        stage = {}
        errors.append(f"invalid pending R3 Stage B report: {exc}")
    if stage:
        basis = stage.get("basis") if isinstance(stage.get("basis"), dict) else {}
        candidate = stage.get("candidate") if isinstance(stage.get("candidate"), dict) else {}
        if basis.get("validation_path") != STAGE_B_BASE_REL:
            errors.append("pending R3 Stage B report names the wrong base validation")
        if basis.get("validation_sha256") != sha256_file(root / STAGE_B_BASE_REL):
            errors.append("pending R3 Stage B base hash mismatch")
        if candidate.get("implementation_commit") != release.get("implementation_checkpoint"):
            errors.append("pending R3 Stage B implementation checkpoint mismatch")
        tested_errors: list[str] = []
        tested = _resolve_commit(root, basis.get("tested_release_commit"), "Stage B base commit", tested_errors)
        errors.extend(tested_errors)
        if tested and implementation:
            paths = _changed_paths(root, tested, implementation, errors)
            protected = [item for item in paths if _stage_b_protected_path(item)]
            ui_runtime = [
                item for item in paths
                if item.startswith("ui/") and PurePosixPath(item).suffix.lower() != ".md"
            ]
            observed["protected_changed_paths"] = protected
            observed["ui_runtime_changed_paths"] = ui_runtime
            if candidate.get("protected_changed_paths") != protected:
                errors.append("pending R3 Stage B protected paths differ from Git")
            if candidate.get("ui_runtime_changed") is not False or ui_runtime:
                errors.append("pending R3 Stage B package cannot inherit across a UI runtime change")

    try:
        validation = read_json(root / VALIDATION_REL)
        errors.extend(_self_hash_errors(validation, "report_payload_sha256", "R3 G5 validation"))
        if validation.get("implementation_checkpoint") != release.get("implementation_checkpoint"):
            errors.append("R3 G5 validation checkpoint mismatch")
        if validation.get("status") != "PASS_TECHNICAL_REVIEW_READY":
            errors.append("R3 G5 validation is not technically review-ready")
        if validation.get("human_g5_decision") != "PENDING":
            errors.append("R3 G5 validation invents a human decision")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid R3 G5 validation report: {exc}")
    checklist = safe_file(root, CHECKLIST_REL)
    if checklist is None or not checklist.is_file():
        errors.append(f"missing {CHECKLIST_REL}")
    else:
        text = checklist.read_text(encoding="utf-8")
        if "G5 REVIEW PENDING" not in text or "Decision: PENDING" not in text:
            errors.append("R3 checklist does not clearly preserve the pending human decision")

    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "cycle_id": CYCLE_ID,
        "mode": "g5_review_package",
        "readiness": "PASS" if not errors else "BLOCK",
        "errors": errors,
        "observed": observed,
        "human_g5_decision": "PENDING",
        "source_or_label_decoded": False,
        "week08_evaluation_executed": False,
    }


def _load_release(root: Path) -> tuple[list[str], dict[str, Any]]:
    path = safe_file(root, RELEASE_REL)
    if path is None or not path.is_file():
        return [f"missing {RELEASE_REL}"], {}
    try:
        release = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid R3 release manifest: {exc}"], {}
    errors: list[str] = []
    if set(release) != EXPECTED_RELEASE_FIELDS:
        errors.append("R3 release manifest fields are not exact")
    if release.get("schema_version") != RELEASE_SCHEMA:
        errors.append("unsupported R3 release manifest schema")
    if release.get("cycle_id") != CYCLE_ID or release.get("gate") != "G5":
        errors.append("R3 release manifest cycle or gate mismatch")
    if release.get("status") != "G5_PASS":
        errors.append("R3 G5 release status is not G5_PASS")
    if not nonempty(release.get("release_id")) or release.get("release_id") != release.get("release_tag"):
        errors.append("R3 release_id and release_tag must identify the same freeze")
    if release.get("proposed_release_tag") != release.get("release_tag"):
        errors.append("R3 proposed and actual release tags differ")
    if release.get("clean_worktree") is not True or release.get("required_signoffs_complete") is not True:
        errors.append("R3 release manifest does not attest a clean, fully signed freeze")
    reviewer = release.get("reviewer") if isinstance(release.get("reviewer"), dict) else {}
    if set(reviewer) != {"requested_reviewer", "name", "role", "decision", "attested_utc"}:
        errors.append("R3 release reviewer fields are not exact")
    if not nonempty(reviewer.get("name")) or reviewer.get("role") != "release reviewer":
        errors.append("R3 G5 requires a named release reviewer")
    if reviewer.get("decision") != "APPROVED" or not valid_utc(reviewer.get("attested_utc")):
        errors.append("R3 G5 reviewer approval is missing or malformed")
    if release.get("post_release_metadata_allowlist") != sorted(POST_G5_METADATA_ALLOWLIST):
        errors.append("R3 post-G5 metadata allowlist is not exact")
    counters = release.get("activity_counters") if isinstance(release.get("activity_counters"), dict) else {}
    if any(counters.get(name) != 0 for name in (
        "source_bytes_decoded", "labels_accessed", "registration_attempts",
        "policy_decisions", "evaluation_runs",
    )):
        errors.append("R3 release manifest records activity before final execution")
    return errors, release


def _release_git_errors(root: Path, release: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed: dict[str, Any] = {"post_release_changed_paths": []}
    implementation = _resolve_commit(
        root, release.get("implementation_checkpoint"), "R3 implementation checkpoint", errors,
    )
    frozen = _resolve_commit(root, release.get("release_commit"), "R3 release commit", errors)
    tag = release.get("release_tag")
    if not nonempty(tag):
        errors.append("R3 release tag is missing")
    elif _git(root, "check-ref-format", f"refs/tags/{tag}").returncode != 0:
        errors.append("R3 release tag is invalid")
    tagged: str | None = None
    if nonempty(tag):
        result = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        if result.returncode != 0:
            errors.append("cannot resolve R3 release tag")
        else:
            tagged = result.stdout.strip().lower()
    if frozen is not None and tagged is not None and frozen != tagged:
        errors.append("R3 release tag does not resolve to release_commit")
    if implementation is not None and frozen is not None:
        if _git(root, "merge-base", "--is-ancestor", implementation, frozen).returncode != 0:
            errors.append("R3 implementation checkpoint is not an ancestor of the release commit")
    head_result = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    head = head_result.stdout.strip().lower() if head_result.returncode == 0 else None
    if head is None:
        errors.append("cannot resolve current HEAD")
    elif frozen is not None:
        if _git(root, "merge-base", "--is-ancestor", frozen, head).returncode != 0:
            errors.append("R3 release commit is not an ancestor of HEAD")
        else:
            changed = _changed_paths(root, frozen, head, errors)
            observed["post_release_changed_paths"] = changed
            forbidden = sorted(set(changed) - POST_G5_METADATA_ALLOWLIST)
            if forbidden:
                errors.append("post-G5 changes exceed the metadata allowlist: " + ", ".join(forbidden))
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    observed["worktree_status"] = status.stdout.splitlines()
    if status.returncode != 0 or status.stdout.strip():
        errors.append("R3 final-readiness worktree is not clean")
    return errors, observed


def _artifact_errors(root: Path, release: Mapping[str, Any]) -> list[str]:
    artifacts = release.get("artifacts") if isinstance(release.get("artifacts"), dict) else {}
    errors: list[str] = []
    if set(artifacts) != CRITICAL_ARTIFACTS:
        errors.append("R3 release artifact inventory is not exact")
    for relative in sorted(CRITICAL_ARTIFACTS):
        issue = checked_hash(root, relative, artifacts.get(relative))
        if issue:
            errors.append(issue)
    dependency = (
        release.get("dependency_environment")
        if isinstance(release.get("dependency_environment"), dict)
        else {}
    )
    if set(dependency) != {"lock_path", "lock_sha256", "environment_path", "environment_sha256"}:
        errors.append("R3 dependency/environment binding fields are not exact")
    for path_field, hash_field in (
        ("lock_path", "lock_sha256"),
        ("environment_path", "environment_sha256"),
    ):
        issue = checked_hash(root, dependency.get(path_field), dependency.get(hash_field))
        if issue:
            errors.append(issue)
    return errors


def _stage_b_errors(root: Path, release: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed: dict[str, Any] = {}
    binding = release.get("stage_b_binding") if isinstance(release.get("stage_b_binding"), dict) else {}
    expected_binding_fields = {
        "base_validation_path", "base_validation_sha256", "base_tested_commit",
        "rebinding_path", "rebinding_sha256", "implementation_checkpoint",
        "frozen_ui_version", "manual_evidence", "ui_runtime_or_ui_test_paths_changed",
        "review_status",
    }
    if set(binding) != expected_binding_fields:
        errors.append("R3 Stage B release binding fields are not exact")
    if binding.get("base_validation_path") != STAGE_B_BASE_REL:
        errors.append("R3 Stage B binding names the wrong base validation")
    for path_field, hash_field in (
        ("base_validation_path", "base_validation_sha256"),
        ("rebinding_path", "rebinding_sha256"),
    ):
        issue = checked_hash(root, binding.get(path_field), binding.get(hash_field))
        if issue:
            errors.append(issue)
    if binding.get("implementation_checkpoint") != release.get("implementation_checkpoint"):
        errors.append("R3 Stage B implementation checkpoint differs from the release")
    if binding.get("ui_runtime_or_ui_test_paths_changed") is not False:
        errors.append("R3 Stage B binding reports a UI runtime/test change")
    if binding.get("review_status") != "APPROVED":
        errors.append("R3 Stage B rebinding is not reviewer-approved")

    report_path = safe_file(root, STAGE_B_REBINDING_REL)
    report: dict[str, Any] = {}
    if report_path is None or not report_path.is_file():
        errors.append(f"missing {STAGE_B_REBINDING_REL}")
    else:
        try:
            report = read_json(report_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid R3 Stage B rebinding: {exc}")
    if report:
        expected_fields = {
            "schema_version", "stage", "status", "basis", "candidate",
            "automated_validation", "inheritance", "reviewer", "week8_heldout_used",
        }
        if set(report) != expected_fields or report.get("schema_version") != STAGE_B_REBINDING_SCHEMA:
            errors.append("R3 Stage B rebinding schema or fields are invalid")
        if report.get("status") != "APPROVED" or report.get("week8_heldout_used") is not False:
            errors.append("R3 Stage B rebinding is not approved with zero held-out use")
        reviewer = report.get("reviewer") if isinstance(report.get("reviewer"), dict) else {}
        if reviewer.get("decision") != "APPROVED" or reviewer.get("role") != "release reviewer":
            errors.append("R3 Stage B reviewer approval is missing")
        basis = report.get("basis") if isinstance(report.get("basis"), dict) else {}
        candidate = report.get("candidate") if isinstance(report.get("candidate"), dict) else {}
        if basis.get("validation_path") != STAGE_B_BASE_REL:
            errors.append("R3 Stage B report names the wrong inherited validation")
        if basis.get("validation_sha256") != binding.get("base_validation_sha256"):
            errors.append("R3 Stage B base validation hash mismatch")
        if candidate.get("implementation_commit") != release.get("implementation_checkpoint"):
            errors.append("R3 Stage B report names the wrong implementation checkpoint")
        tested = _resolve_commit(root, basis.get("tested_release_commit"), "Stage B tested commit", errors)
        implementation = _resolve_commit(
            root, candidate.get("implementation_commit"), "R3 Stage B implementation commit", errors,
        )
        frozen = _resolve_commit(root, release.get("release_commit"), "R3 Stage B release commit", errors)
        if tested and implementation:
            if _git(root, "merge-base", "--is-ancestor", tested, implementation).returncode != 0:
                errors.append("Stage B tested commit is not an ancestor of the R3 implementation")
            changed = _changed_paths(root, tested, implementation, errors)
            protected = [item for item in changed if _stage_b_protected_path(item)]
            ui_runtime = [
                item for item in changed
                if item.startswith("ui/") and PurePosixPath(item).suffix.lower() != ".md"
            ]
            observed.update({
                "candidate_changed_paths": changed,
                "protected_changed_paths": protected,
                "ui_runtime_changed_paths": ui_runtime,
            })
            if candidate.get("protected_changed_paths") != protected:
                errors.append("R3 Stage B protected-path list does not match Git history")
            if ui_runtime:
                errors.append("UI runtime/test paths changed after inherited Stage B acceptance")
        if implementation and frozen:
            tail = _changed_paths(root, implementation, frozen, errors)
            observed["release_tail_changed_paths"] = tail
            forbidden_tail = [
                item for item in tail
                if not item.startswith("docs/") and not item.startswith("reports/")
            ]
            if forbidden_tail:
                errors.append("R3 release tail exceeds docs/reports: " + ", ".join(forbidden_tail))
    return errors, observed


def _fresh_enrollment_errors(
    root: Path,
    release: Mapping[str, Any],
) -> tuple[list[str], dict[str, Any], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    observed: dict[str, Any] = {"source_ids": []}
    try:
        ledger = read_json(root / LEDGER_REL)
        manifest = read_json(root / MANIFEST_REL)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid R3 enrollment metadata: {exc}"], observed, {}, {}
    if ledger.get("schema_version") != "week08_r3_source_use_ledger_v1":
        errors.append("R3 source ledger schema mismatch")
    if ledger.get("cycle_id") != CYCLE_ID or manifest.get("cycle_id") != CYCLE_ID:
        errors.append("R3 enrollment cycle_id mismatch")
    fresh = ledger.get("fresh_sources")
    if not isinstance(fresh, list) or not fresh:
        errors.append("no fresh R3 source is enrolled")
        fresh = []
    required = set(ledger.get("required_fresh_source_fields", []))
    if not required:
        errors.append("R3 ledger does not declare required fresh-source fields")
    prior = ledger.get("prior_exposed_sources")
    prior = prior if isinstance(prior, list) else []
    prohibited_hashes = {item.get("sha256") for item in prior if isinstance(item, dict)}
    prohibited_canonical = {
        item.get("canonical_source_id") for item in prior if isinstance(item, dict)
    }
    prohibited_lineage = {
        value
        for item in prior if isinstance(item, dict)
        for value in item.get("lineage_ancestors", [])
        if isinstance(value, str)
    }
    source_ids: list[str] = []
    for item in fresh:
        if not isinstance(item, dict):
            errors.append("R3 fresh-source record is not an object")
            continue
        missing = sorted(required - set(item))
        if missing:
            errors.append("R3 fresh-source record is missing: " + ", ".join(missing))
        source_id = item.get("source_id")
        if not nonempty(source_id):
            errors.append("R3 fresh source_id is missing")
            continue
        source_ids.append(str(source_id))
        if item.get("previously_used") is not False or item.get("prior_usage") != []:
            errors.append(f"R3 source is not genuinely unused: {source_id}")
        if item.get("role") != "full_project_independent":
            errors.append(f"R3 core source is not fully project-independent: {source_id}")
        if item.get("sha256") in prohibited_hashes:
            errors.append(f"R3 source reuses an exposed byte hash: {source_id}")
        if item.get("canonical_source_id") in prohibited_canonical:
            errors.append(f"R3 source reuses an exposed canonical identity: {source_id}")
        lineage = item.get("lineage_ancestors")
        if not isinstance(lineage, list) or not lineage:
            errors.append(f"R3 source lineage is incomplete: {source_id}")
        elif prohibited_lineage.intersection(str(value) for value in lineage):
            errors.append(f"R3 source shares lineage with an exposed source: {source_id}")
        path_value = item.get("path")
        if isinstance(path_value, str) and any(
            path_value == root_name or path_value.startswith(root_name + "/")
            for root_name in R2_PROHIBITED_ROOTS
        ):
            errors.append(f"R3 source path reuses a prohibited R2 namespace: {source_id}")
        issue = checked_hash(root, path_value, item.get("sha256"))
        if issue:
            errors.append(f"R3 source {source_id}: {issue}")
        attestation = item.get("custodian_attestation")
        if not isinstance(attestation, dict) or attestation.get("decision") != "APPROVED":
            errors.append(f"R3 source lacks an approved custodian attestation: {source_id}")
        evidence = item.get("ground_truth")
        if not isinstance(evidence, dict) or evidence.get("type") not in {
            "synthetic_created_after_freeze", "verified_landmarks", "verified_masks",
        }:
            errors.append(f"R3 source lacks eligible ground truth: {source_id}")
    if len(source_ids) != len(set(source_ids)):
        errors.append("R3 source IDs are duplicated")
    observed["source_ids"] = sorted(source_ids)
    expected_top = {
        "schema_version", "cycle_id", "release_id", "status", "ledger_path",
        "ledger_sha256", "source_ids", "pairs", "source_bytes_accessed",
        "labels_accessed", "synthetic_ground_truth_generated",
        "execution_authorized", "blockers", "output_namespaces",
    }
    if set(manifest) != expected_top:
        errors.append("R3 holdout manifest fields are not exact")
    if manifest.get("schema_version") != "week08_r3_holdout_sources_v1":
        errors.append("R3 holdout manifest schema mismatch")
    if manifest.get("release_id") != release.get("release_id"):
        errors.append("R3 enrollment release_id differs from G5")
    if manifest.get("ledger_path") != LEDGER_REL:
        errors.append("R3 enrollment manifest names the wrong ledger")
    if manifest.get("ledger_sha256") != sha256_file(root / LEDGER_REL):
        errors.append("R3 enrollment manifest ledger hash mismatch")
    if sorted(manifest.get("source_ids", [])) != sorted(source_ids):
        errors.append("R3 manifest source IDs differ from the ledger")
    if manifest.get("source_bytes_accessed") != 0 or manifest.get("labels_accessed") != 0:
        errors.append("R3 enrollment records source or label decoding before G7")
    if manifest.get("execution_authorized") is not False:
        errors.append("G6 enrollment must not authorize execution")

    registration_path = safe_file(root, SOURCE_REGISTRATION_REL)
    registration: dict[str, Any] = {}
    if registration_path is None or not registration_path.is_file():
        errors.append(f"missing {SOURCE_REGISTRATION_REL}")
    else:
        try:
            registration = read_json(registration_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid R3 source registration: {exc}")
    if registration:
        expected_registration = {
            "schema_version", "cycle_id", "gate", "status", "registered_utc",
            "release_binding", "custodian_attestation", "sources",
            "tracked_enrollment", "access_boundary", "limitations",
        }
        if set(registration) != expected_registration:
            errors.append("R3 source-registration fields are not exact")
        if registration.get("schema_version") != SOURCE_REGISTRATION_SCHEMA:
            errors.append("unsupported R3 source-registration schema")
        if registration.get("cycle_id") != CYCLE_ID or registration.get("gate") != "G6":
            errors.append("R3 source-registration cycle or gate mismatch")
        if registration.get("status") != "PASS" or not valid_utc(registration.get("registered_utc")):
            errors.append("R3 source registration is not a timestamped PASS")
        release_binding = (
            registration.get("release_binding")
            if isinstance(registration.get("release_binding"), dict)
            else {}
        )
        if release_binding != {
            "g5_release_commit": release.get("release_commit"),
            "g5_release_tag": release.get("release_tag"),
            "release_id": release.get("release_id"),
        }:
            errors.append("R3 source registration is not bound to the G5 freeze")
        custodian = (
            registration.get("custodian_attestation")
            if isinstance(registration.get("custodian_attestation"), dict)
            else {}
        )
        if (
            custodian.get("role") != "data custodian/provenance reviewer"
            or custodian.get("decision") != "APPROVED"
            or not nonempty(custodian.get("name"))
            or not valid_utc(custodian.get("attested_utc"))
        ):
            errors.append("R3 G6 custodian approval is missing or malformed")
        registered_sources = registration.get("sources")
        registered_ids = sorted(
            str(item.get("source_id"))
            for item in registered_sources
            if isinstance(item, dict) and nonempty(item.get("source_id"))
        ) if isinstance(registered_sources, list) else []
        if registered_ids != sorted(source_ids):
            errors.append("R3 source registration does not enumerate the enrolled sources")
        tracked = (
            registration.get("tracked_enrollment")
            if isinstance(registration.get("tracked_enrollment"), dict)
            else {}
        )
        if tracked.get("source_ledger_sha256") != sha256_file(root / LEDGER_REL):
            errors.append("R3 source registration ledger hash mismatch")
        if tracked.get("holdout_manifest_sha256") != sha256_file(root / MANIFEST_REL):
            errors.append("R3 source registration manifest hash mismatch")
        if sorted(tracked.get("source_ids", [])) != sorted(source_ids):
            errors.append("R3 source registration tracked IDs mismatch")
        access = registration.get("access_boundary") if isinstance(registration.get("access_boundary"), dict) else {}
        if (
            access.get("raw_bytes_hashed_without_decode") is not True
            or access.get("source_pixels_decoded") is not False
            or access.get("labels_accessed") is not False
            or access.get("scientific_outcomes_accessed") is not False
            or access.get("week08_benchmark_executed") is not False
        ):
            errors.append("R3 G6 access boundary is not zero-decode and zero-outcome")

    g6 = release.get("g6_enrollment") if isinstance(release.get("g6_enrollment"), dict) else {}
    expected_g6 = {
        "status", "reviewed_commit", "source_ids", "source_ledger_sha256",
        "holdout_manifest_sha256", "source_registration_sha256",
    }
    if set(g6) != expected_g6 or g6.get("status") != "PASS":
        errors.append("R3 release manifest does not record a passing G6 enrollment")
    if sorted(g6.get("source_ids", [])) != sorted(source_ids):
        errors.append("R3 release G6 source IDs mismatch")
    for field, relative in (
        ("source_ledger_sha256", LEDGER_REL),
        ("holdout_manifest_sha256", MANIFEST_REL),
        ("source_registration_sha256", SOURCE_REGISTRATION_REL),
    ):
        issue = checked_hash(root, relative, g6.get(field))
        if issue:
            errors.append(issue)
    reviewed = _resolve_commit(root, g6.get("reviewed_commit"), "reviewed R3 G6 commit", errors)
    if reviewed:
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
        if _git(root, "merge-base", "--is-ancestor", reviewed, head).returncode != 0:
            errors.append("reviewed R3 G6 commit is not an ancestor of HEAD")
        else:
            changed = _changed_paths(root, reviewed, head, errors)
            observed["post_g6_changed_paths"] = changed
            forbidden = sorted(set(changed) - POST_G6_METADATA_ALLOWLIST)
            if forbidden:
                errors.append("post-G6 changes exceed the authorization allowlist: " + ", ".join(forbidden))
    return errors, observed, ledger, manifest


def _authorization_errors(
    root: Path,
    release: Mapping[str, Any],
    source_ids: Sequence[str],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed: dict[str, Any] = {}
    path = safe_file(root, AUTHORIZATION_REL)
    if path is None or not path.is_file():
        return [f"missing {AUTHORIZATION_REL}"], observed
    try:
        authorization = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid R3 G7 authorization: {exc}"], observed
    expected_top = {
        "schema_version", "authorization_id", "cycle_id", "gate", "decision",
        "reviewer", "release", "enrollment", "runtime_bindings",
        "incident_disposition", "source_freshness", "deviation_approval", "authorization",
    }
    if set(authorization) != expected_top:
        errors.append("R3 G7 authorization fields are not exact")
    if authorization.get("schema_version") != AUTHORIZATION_SCHEMA:
        errors.append("unsupported R3 G7 authorization schema")
    if authorization.get("cycle_id") != CYCLE_ID or authorization.get("gate") != "G7":
        errors.append("R3 G7 authorization cycle or gate mismatch")
    if authorization.get("decision") != "APPROVED" or not nonempty(authorization.get("authorization_id")):
        errors.append("R3 G7 authorization decision is not APPROVED")
    reviewer = authorization.get("reviewer") if isinstance(authorization.get("reviewer"), dict) else {}
    if (
        set(reviewer) != {"name", "role", "attested_utc"}
        or reviewer.get("role") != "release reviewer"
        or not nonempty(reviewer.get("name"))
        or not valid_utc(reviewer.get("attested_utc"))
    ):
        errors.append("R3 G7 reviewer approval is missing or malformed")
    release_binding = authorization.get("release") if isinstance(authorization.get("release"), dict) else {}
    if release_binding != {
        "release_id": release.get("release_id"),
        "release_commit": release.get("release_commit"),
        "release_tag": release.get("release_tag"),
    }:
        errors.append("R3 G7 authorization release binding mismatch")
    g6 = release.get("g6_enrollment") if isinstance(release.get("g6_enrollment"), dict) else {}
    enrollment = authorization.get("enrollment") if isinstance(authorization.get("enrollment"), dict) else {}
    expected_enrollment = {
        "reviewed_commit": g6.get("reviewed_commit"),
        "source_ids": sorted(source_ids),
        "source_ledger_sha256": sha256_file(root / LEDGER_REL),
        "holdout_manifest_sha256": sha256_file(root / MANIFEST_REL),
        "source_registration_sha256": sha256_file(root / SOURCE_REGISTRATION_REL),
    }
    if enrollment != expected_enrollment:
        errors.append("R3 G7 authorization enrollment binding mismatch")
    runtime = authorization.get("runtime_bindings") if isinstance(authorization.get("runtime_bindings"), dict) else {}
    if set(runtime) != set(RUNTIME_BINDINGS):
        errors.append("R3 G7 runtime binding fields are not exact")
    for field, relative in RUNTIME_BINDINGS.items():
        issue = checked_hash(root, relative, runtime.get(field))
        if issue:
            errors.append(issue)
    incident = (
        authorization.get("incident_disposition")
        if isinstance(authorization.get("incident_disposition"), dict)
        else {}
    )
    if incident != {
        "status": "NO_R3_INCIDENT",
        "report_path": None,
        "report_sha256": None,
        "source_pixels_decoded": False,
        "source_labels_accessed": False,
        "scientific_attempts_executed": 0,
    }:
        errors.append("R3 G7 incident disposition is not the exact no-incident record")
    freshness = (
        authorization.get("source_freshness")
        if isinstance(authorization.get("source_freshness"), dict)
        else {}
    )
    if freshness != {
        "fresh_source_required": True,
        "r2_source_reuse_permitted": False,
        "source_reuse_approved": False,
    }:
        errors.append("R3 G7 source-freshness decision is not exact")
    deviation = (
        authorization.get("deviation_approval")
        if isinstance(authorization.get("deviation_approval"), dict)
        else {}
    )
    if set(deviation) != {
        "independent_real_verified_gt_absent", "approved", "claim_scope", "prohibited_claims",
    }:
        errors.append("R3 G7 deviation-approval fields are not exact")
    if deviation.get("independent_real_verified_gt_absent") is True and deviation.get("approved") is not True:
        errors.append("R3 G7 does not approve the declared real-verified-GT deviation")
    if deviation.get("claim_scope") != "source_specific_software_evidence_only":
        errors.append("R3 G7 claim scope is not source-specific software evidence only")
    if deviation.get("prohibited_claims") != PROHIBITED_CLAIMS:
        errors.append("R3 G7 prohibited-claims list is not exact")
    one_run = authorization.get("authorization") if isinstance(authorization.get("authorization"), dict) else {}
    if one_run != {
        "authorizes_phase8_one_run": True,
        "sequence": ["prepare", "decide", "evaluate"],
        "infrastructure_resume_only": True,
    }:
        errors.append("R3 G7 one-run authorization is not exact")
    declared = release.get("g7_authorization") if isinstance(release.get("g7_authorization"), dict) else {}
    if declared != {
        "status": "PASS",
        "authorization_id": authorization.get("authorization_id"),
        "authorization_sha256": sha256_file(path),
    }:
        errors.append("R3 release manifest G7 binding mismatch")
    final = release.get("final_readiness") if isinstance(release.get("final_readiness"), dict) else {}
    if final != {
        "authorized": True,
        "release_reviewer_approval_pending": False,
        "expected_remaining_blocks": [],
        "week08_benchmark_executed": False,
        "real_week08_pixels_accessed": False,
        "real_week08_labels_accessed": False,
    }:
        errors.append("R3 release manifest final-readiness state is not exact")
    observed.update({
        "authorization_id": authorization.get("authorization_id"),
        "reviewer": reviewer.get("name"),
        "authorization_sha256": sha256_file(path),
    })
    return errors, observed


def _output_boundary_errors(root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    nonempty_roots: list[str] = []
    for relative in R3_OUTPUT_ROOTS:
        path = root / relative
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            nonempty_roots.append(relative)
    if nonempty_roots:
        errors.append("R3 final output roots are not absent or empty: " + ", ".join(nonempty_roots))
    return errors, {"nonempty_output_roots": nonempty_roots}


def run_preflight(root: Path = ROOT, *, require_g7: bool) -> dict[str, Any]:
    """Run the read-only R3 technical or authorization-required gate."""
    checks: list[dict[str, Any]] = []

    def add(name: str, errors: Sequence[str], **observed: Any) -> None:
        item: dict[str, Any] = {
            "check": name,
            "status": "BLOCK" if errors else "PASS",
            "errors": list(errors),
        }
        if observed:
            item["observed"] = observed
        checks.append(item)

    config_errors, _config = _config_errors(root)
    add("r3_config_contract", config_errors)
    g3_errors, _g3 = _g3_errors(root)
    add("r3_g3_remediation", g3_errors)

    release_errors, release = _load_release(root)
    add("r3_g5_release_manifest", release_errors)
    if release:
        git_errors, git_observed = _release_git_errors(root, release)
        add("r3_g5_release_commit_tag", git_errors, **git_observed)
        add("r3_g5_artifact_bindings", _artifact_errors(root, release))
        stage_errors, stage_observed = _stage_b_errors(root, release)
        add("r3_g5_stage_b_rebinding", stage_errors, **stage_observed)
    else:
        add("r3_g5_release_commit_tag", ["G5 release manifest is unavailable"])
        add("r3_g5_artifact_bindings", ["G5 release manifest is unavailable"])
        add("r3_g5_stage_b_rebinding", ["G5 release manifest is unavailable"])

    if release:
        source_errors, source_observed, _ledger, _manifest = _fresh_enrollment_errors(root, release)
    else:
        source_errors, source_observed = ["G5 must pass before G6 enrollment"], {"source_ids": []}
    add("r3_g6_fresh_source_enrollment", source_errors, **source_observed)

    if require_g7:
        if release and not source_errors:
            authorization_errors, authorization_observed = _authorization_errors(
                root, release, source_observed.get("source_ids", []),
            )
        else:
            authorization_errors, authorization_observed = [
                "G5 and G6 must pass before G7 authorization"
            ], {}
        add("r3_g7_one_run_authorization", authorization_errors, **authorization_observed)
    else:
        checks.append({
            "check": "r3_g7_one_run_authorization",
            "status": "DEFER",
            "errors": [],
            "observed": {"reason": "technical readiness intentionally defers human G7 approval"},
        })

    output_errors, output_observed = _output_boundary_errors(root)
    add("r3_predecode_output_boundary", output_errors, **output_observed)
    readiness = "BLOCK" if any(item["status"] == "BLOCK" for item in checks) else "PASS"
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "cycle_id": CYCLE_ID,
        "mode": "final_readiness" if require_g7 else "technical_readiness",
        "readiness": readiness,
        "phase7_authorization_required": require_g7,
        "checks": checks,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
        "source_or_label_decoded": False,
        "week08_evaluation_executed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--candidate-readiness", action="store_true")
    mode.add_argument("--review-package", action="store_true")
    mode.add_argument("--technical-readiness", action="store_true")
    mode.add_argument("--final-readiness", action="store_true")
    args = parser.parse_args(argv)
    if args.candidate_readiness:
        report = validate_candidate(ROOT)
    elif args.review_package:
        report = validate_review_package(ROOT)
    else:
        report = run_preflight(ROOT, require_g7=bool(args.final_readiness))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["readiness"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
