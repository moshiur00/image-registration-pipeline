"""Reproducible UI walkthrough fixtures and operator-attested acceptance log.

All generated artifacts are temporary UI QA files. The module never runs the
Week 8 evaluation or modifies frozen backend configuration and evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Final, Iterable, Mapping
import zipfile

import cv2
import numpy as np

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SOURCE: Final[Path] = ROOT / "data/samples/week02_real_general/camera.png"
RUNTIME: Final[Path] = ROOT / "ui/runtime/pre_week08_stage_b"
RECORD: Final[str] = "manual_acceptance.json"
SCHEMA_VERSION: Final[str] = "ui-stage-b-acceptance-v2"
VALIDATION_SCHEMA_VERSION: Final[str] = "pre_week08_stage_b_validation_v1"

SCENARIOS: Final[dict[str, str]] = {
    "multimodal": "Check multimodal method filtering and no ungrounded geometric claims",
    "single_candidate": "Check agreement abstains for exactly one eligible candidate",
    "failed_check": "Check failed/CHECK candidates and diagnostics remain visible and exportable",
    "stale_state": "Check changed inputs/settings invalidate existing result and prepared export",
    "export_provenance": "Check ZIP candidate records, statuses, raw-byte SHA256 and source exclusion",
}
SUPPLEMENTAL_CHECKS: Final[dict[str, str]] = {
    "normal_monomodal": "Check a normal monomodal Automatic Comparison run",
    "unknown_upload_claim_suppression": "Check unknown uploads show no TRE or geometric PASS",
    "rire_technical_only_caveat": "Check the RIRE technical-only caveat is visible",
    "candidate_inspection_labels": "Check candidate inspection labels are accurate",
    "no_frozen_location_writes": "Check UI activity writes nothing to frozen research locations",
}
ZIP_REQUIRED_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"single_candidate", "failed_check", "export_provenance"}
)
SCOPE_DECISIONS: Final[tuple[str, ...]] = (
    "stage_c_research_evidence",
    "interactive_rire_expansion",
    "recommendation_display_path",
)
_COMMIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")
_SCREENSHOT_SUFFIXES: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _nonempty(value: str, label: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{label} is mandatory")
    return cleaned


def _runtime_file(reference: str | Path, *, destination: Path, label: str) -> tuple[Path, str]:
    root = destination.resolve()
    supplied = Path(reference)
    candidate = (root / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain under {root}") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {relative.as_posix()}")
    return candidate, relative.as_posix()


def _require_current_fixtures(destination: Path) -> Path:
    manifest_path = destination / "fixtures_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Prepare UI QA fixtures before recording acceptance")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Prepare UI QA fixtures again; the manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Prepare UI QA fixtures again for the current acceptance schema")
    return manifest_path


def _fixture_manifest_sha(destination: Path) -> str:
    return _sha(_require_current_fixtures(destination))


def _verify_release_commit(release_commit: str, *, repository_root: Path) -> None:
    root = repository_root.resolve()
    git = [
        "git",
        "-c",
        f"safe.directory={root.as_posix()}",
        "-C",
        str(root),
    ]
    exists = subprocess.run(
        [*git, "cat-file", "-e", f"{release_commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if exists.returncode != 0:
        raise ValueError("Release commit does not exist as a Git commit")
    ancestor = subprocess.run(
        [*git, "merge-base", "--is-ancestor", release_commit, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise ValueError("Release commit is not an ancestor of current HEAD")


def _require_current_tested_head(release_commit: str, *, repository_root: Path) -> None:
    _verify_release_commit(release_commit, repository_root=repository_root)
    root = repository_root.resolve()
    head = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            "rev-parse",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        raise ValueError("Cannot resolve the current Git HEAD")
    if release_commit != head.stdout.strip():
        raise ValueError("Release commit must equal the checked-out HEAD at recording time")
    status = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise ValueError("Cannot verify the Git worktree state")
    if status.stdout.strip():
        raise ValueError("Git worktree must be clean when recording UI acceptance")


def _evidence_records(
    references: Iterable[str | Path], *, destination: Path, kind: str
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for reference in references:
        path, relative = _runtime_file(reference, destination=destination, label=f"{kind} evidence")
        if kind == "screenshot" and path.suffix.lower() not in _SCREENSHOT_SUFFIXES:
            raise ValueError("Screenshot evidence must be PNG, JPEG, or WebP")
        if kind == "screenshot" and cv2.imread(str(path), cv2.IMREAD_UNCHANGED) is None:
            raise ValueError(f"Screenshot evidence is not a readable image: {relative}")
        if kind == "zip" and path.suffix.lower() != ".zip":
            raise ValueError("ZIP evidence must have a .zip suffix")
        if kind == "zip" and not zipfile.is_zipfile(path):
            raise ValueError(f"ZIP evidence is not a readable ZIP archive: {relative}")
        records.append({
            "reference": relative,
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
        })
    return records


def _verify_evidence_records(
    records: object, *, destination: Path, kind: str, required: bool
) -> list[dict[str, object]]:
    if not isinstance(records, list) or (required and not records):
        qualifier = "at least one" if required else "a list of"
        raise ValueError(f"Acceptance record requires {qualifier} {kind} evidence reference")
    verified: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"Malformed {kind} evidence record")
        reference = record.get("reference")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if not isinstance(reference, str) or not isinstance(digest, str) or not isinstance(size, int):
            raise ValueError(f"Malformed {kind} evidence metadata")
        path, normalized = _runtime_file(reference, destination=destination, label=f"{kind} evidence")
        if normalized != reference or _sha(path) != digest or path.stat().st_size != size:
            raise ValueError(f"{kind.title()} evidence hash/size no longer matches: {reference}")
        if kind == "screenshot" and path.suffix.lower() not in _SCREENSHOT_SUFFIXES:
            raise ValueError("Screenshot evidence must be PNG, JPEG, or WebP")
        if kind == "screenshot" and cv2.imread(str(path), cv2.IMREAD_UNCHANGED) is None:
            raise ValueError(f"Screenshot evidence is not a readable image: {reference}")
        if kind == "zip" and path.suffix.lower() != ".zip":
            raise ValueError("ZIP evidence must have a .zip suffix")
        if kind == "zip" and not zipfile.is_zipfile(path):
            raise ValueError(f"ZIP evidence is not a readable ZIP archive: {reference}")
        verified.append({"reference": reference, "sha256": digest, "size_bytes": size})
    return verified


def prepare_fixtures(*, destination: Path = RUNTIME) -> dict:
    """Generate deterministic development-only UI fixtures outside frozen datasets."""
    source = cv2.imread(str(SOURCE), cv2.IMREAD_GRAYSCALE)
    if source is None:
        raise FileNotFoundError(f"Tracked development image unavailable: {SOURCE}")
    fixed = cv2.resize(source, (192, 192), interpolation=cv2.INTER_AREA)
    shift = np.float32([[1, 0, 5], [0, 1, -4]])
    moving = cv2.warpAffine(fixed, shift, (192, 192), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    simulated = np.uint8(255 - cv2.GaussianBlur(moving, (3, 3), 0.8))
    flat_fixed = np.full((192, 192), 112, dtype=np.uint8)
    flat_moving = np.full((192, 192), 136, dtype=np.uint8)
    altered_moving = np.uint8(np.clip(moving.astype(np.int16) + 22, 0, 255))
    images = {
        "paired_fixed.png": fixed,
        "paired_moving.png": moving,
        "multimodal_fixed.png": fixed,
        "multimodal_moving.png": simulated,
        "flat_fixed.png": flat_fixed,
        "flat_moving.png": flat_moving,
        "altered_moving.png": altered_moving,
    }
    destination.mkdir(parents=True, exist_ok=True)
    for name, array in images.items():
        success, content = cv2.imencode(".png", array)
        if not success:
            raise RuntimeError(f"Cannot encode UI QA image {name}")
        (destination / name).write_bytes(content.tobytes())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "MANUAL_UI_QA_ONLY_NOT_WEEK08_HELDOUT_DATA",
        "development_source": SOURCE.relative_to(ROOT).as_posix(),
        "geometry": "deterministic translation, display-only test fixtures",
        "files": {name: _sha(destination / name) for name in sorted(images)},
        "scenarios": SCENARIOS,
        "warning": "No scenario is marked passed by generating fixtures; real Streamlit checks require operator review.",
    }
    (destination / "fixtures_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _validate_result(
    name: str,
    result: object,
    *,
    allowed_names: Mapping[str, str],
    zip_required_names: frozenset[str],
    destination: Path,
    repository_root: Path,
) -> dict:
    if name not in allowed_names or not isinstance(result, dict):
        raise ValueError(f"Malformed acceptance result: {name}")
    verdict = result.get("verdict")
    if verdict not in {"pass", "fail", "blocked"}:
        raise ValueError("Invalid manual acceptance verdict")
    for key in ("reviewer", "platform", "environment", "note", "attested_utc", "source"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ValueError(f"Acceptance result {name} lacks {key}")
    if "windows" not in result["platform"].lower():
        raise ValueError(f"Acceptance result {name} does not identify a Windows platform")
    if result["source"] != "human_windows_operator_assertion_not_automated_test":
        raise ValueError(f"Acceptance result {name} is not a human Windows operator assertion")
    try:
        timestamp = datetime.fromisoformat(result["attested_utc"])
    except ValueError as exc:
        raise ValueError(f"Acceptance result {name} has invalid UTC timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ValueError(f"Acceptance result {name} timestamp is not UTC")
    commit = result.get("release_commit")
    if not isinstance(commit, str) or _COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError(f"Acceptance result {name} has invalid release commit")
    _verify_release_commit(commit, repository_root=repository_root)
    fixture_sha = result.get("fixture_manifest_sha256")
    if not isinstance(fixture_sha, str) or fixture_sha != _fixture_manifest_sha(destination):
        raise ValueError(f"Acceptance result {name} is not bound to the current fixture manifest")
    screenshots = _verify_evidence_records(
        result.get("screenshots"), destination=destination, kind="screenshot", required=True
    )
    zips = _verify_evidence_records(
        result.get("zips"), destination=destination, kind="zip",
        required=(verdict == "pass" and name in zip_required_names),
    )
    return {**result, "screenshots": screenshots, "zips": zips}


def load_record(*, destination: Path = RUNTIME, repository_root: Path = ROOT) -> dict:
    path = destination / RECORD
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "results": {}, "supplemental_results": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported UI acceptance record schema")
    if not isinstance(value.get("results"), dict):
        raise ValueError("Malformed acceptance results")
    if not isinstance(value.get("supplemental_results"), dict):
        raise ValueError("Malformed supplemental acceptance results")
    unknown = set(value["results"]) - SCENARIOS.keys()
    if unknown:
        raise ValueError(f"Unexpected acceptance scenario(s): {sorted(unknown)}")
    unknown_supplemental = set(value["supplemental_results"]) - SUPPLEMENTAL_CHECKS.keys()
    if unknown_supplemental:
        raise ValueError(f"Unexpected supplemental check(s): {sorted(unknown_supplemental)}")
    return {
        "schema_version": SCHEMA_VERSION,
        "results": {
            name: _validate_result(
                name,
                result,
                allowed_names=SCENARIOS,
                zip_required_names=ZIP_REQUIRED_SCENARIOS,
                destination=destination,
                repository_root=repository_root,
            )
            for name, result in value["results"].items()
        },
        "supplemental_results": {
            name: _validate_result(
                name,
                result,
                allowed_names=SUPPLEMENTAL_CHECKS,
                zip_required_names=frozenset(),
                destination=destination,
                repository_root=repository_root,
            )
            for name, result in value["supplemental_results"].items()
        },
    }


def record_manual_result(
    *,
    scenario: str,
    verdict: str,
    reviewer: str,
    platform: str,
    environment: str,
    release_commit: str,
    note: str,
    screenshots: Iterable[str | Path],
    zips: Iterable[str | Path] = (),
    destination: Path = RUNTIME,
    repository_root: Path = ROOT,
) -> dict:
    """Record an explicit operator assertion bound to local, hashed evidence."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown UI QA scenario: {scenario}")
    if verdict not in {"pass", "fail", "blocked"}:
        raise ValueError("Verdict must be pass, fail, or blocked")
    reviewer = _nonempty(reviewer, "Reviewer identity")
    platform = _nonempty(platform, "Target Windows/platform")
    if "windows" not in platform.lower():
        raise ValueError("Target platform must identify Windows")
    environment = _nonempty(environment, "Environment description")
    note = _nonempty(note, "operator observation")
    release_commit = release_commit.strip()
    if _COMMIT_PATTERN.fullmatch(release_commit) is None:
        raise ValueError("Release commit must be exactly 40 lowercase hexadecimal characters")
    _require_current_tested_head(release_commit, repository_root=repository_root)
    fixture_sha = _fixture_manifest_sha(destination)
    screenshot_records = _evidence_records(screenshots, destination=destination, kind="screenshot")
    if not screenshot_records:
        raise ValueError("At least one screenshot evidence reference is mandatory")
    zip_records = _evidence_records(zips, destination=destination, kind="zip")
    if verdict == "pass" and scenario in ZIP_REQUIRED_SCENARIOS and not zip_records:
        raise ValueError(f"A ZIP evidence reference is mandatory for passed scenario {scenario}")
    data = load_record(destination=destination, repository_root=repository_root)
    data["results"][scenario] = {
        "verdict": verdict,
        "reviewer": reviewer,
        "platform": platform,
        "environment": environment,
        "release_commit": release_commit,
        "fixture_manifest_sha256": fixture_sha,
        "note": note,
        "attested_utc": datetime.now(timezone.utc).isoformat(),
        "screenshots": screenshot_records,
        "zips": zip_records,
        "source": "human_windows_operator_assertion_not_automated_test",
    }
    (destination / RECORD).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def record_supplemental_result(
    *,
    check: str,
    verdict: str,
    reviewer: str,
    platform: str,
    environment: str,
    release_commit: str,
    note: str,
    screenshots: Iterable[str | Path],
    destination: Path = RUNTIME,
    repository_root: Path = ROOT,
) -> dict:
    """Record one required supplemental human Windows observation."""
    if check not in SUPPLEMENTAL_CHECKS:
        raise ValueError(f"Unknown supplemental UI QA check: {check}")
    if verdict not in {"pass", "fail", "blocked"}:
        raise ValueError("Verdict must be pass, fail, or blocked")
    reviewer = _nonempty(reviewer, "Reviewer identity")
    platform = _nonempty(platform, "Target Windows/platform")
    if "windows" not in platform.lower():
        raise ValueError("Target platform must identify Windows")
    environment = _nonempty(environment, "Environment description")
    note = _nonempty(note, "operator observation")
    release_commit = release_commit.strip()
    if _COMMIT_PATTERN.fullmatch(release_commit) is None:
        raise ValueError("Release commit must be exactly 40 lowercase hexadecimal characters")
    _require_current_tested_head(release_commit, repository_root=repository_root)
    fixture_sha = _fixture_manifest_sha(destination)
    screenshot_records = _evidence_records(screenshots, destination=destination, kind="screenshot")
    if not screenshot_records:
        raise ValueError("At least one screenshot evidence reference is mandatory")
    data = load_record(destination=destination, repository_root=repository_root)
    data["supplemental_results"][check] = {
        "verdict": verdict,
        "reviewer": reviewer,
        "platform": platform,
        "environment": environment,
        "release_commit": release_commit,
        "fixture_manifest_sha256": fixture_sha,
        "note": note,
        "attested_utc": datetime.now(timezone.utc).isoformat(),
        "screenshots": screenshot_records,
        "zips": [],
        "source": "human_windows_operator_assertion_not_automated_test",
    }
    (destination / RECORD).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def readiness(*, destination: Path = RUNTIME, repository_root: Path = ROOT) -> dict:
    record = load_record(destination=destination, repository_root=repository_root)
    results = record["results"]
    supplemental_results = record["supplemental_results"]
    statuses = {name: results.get(name, {}).get("verdict", "pending") for name in SCENARIOS}
    supplemental_statuses = {
        name: supplemental_results.get(name, {}).get("verdict", "pending")
        for name in SUPPLEMENTAL_CHECKS
    }
    combined = (*statuses.values(), *supplemental_statuses.values())
    if any(value == "fail" for value in combined):
        state = "FAIL"
    elif any(value == "blocked" for value in combined):
        state = "BLOCKED"
    elif all(value == "pass" for value in combined):
        state = "MANUALLY_ACCEPTED"
    else:
        state = "PENDING_MANUAL_QA"
    return {
        "status": state,
        "scenarios": statuses,
        "passed": sum(value == "pass" for value in statuses.values()),
        "total": len(SCENARIOS),
        "supplemental": supplemental_statuses,
        "supplemental_passed": sum(value == "pass" for value in supplemental_statuses.values()),
        "supplemental_total": len(SUPPLEMENTAL_CHECKS),
        "limitations": "Manual acceptance alone does not establish Week 8 benchmark readiness or scientific calibration.",
    }


def build_validation_report(
    *,
    backend_passed: int,
    backend_skipped: int,
    backend_failed: int,
    ui_passed: int,
    ui_skipped: int,
    ui_failed: int,
    scope_decisions: Mapping[str, str],
    destination: Path = RUNTIME,
    repository_root: Path = ROOT,
) -> dict:
    """Build a deterministic, path-sanitized Stage B tracked validation report."""
    counts = {
        "backend": {"passed": backend_passed, "skipped": backend_skipped, "failed": backend_failed},
        "ui": {"passed": ui_passed, "skipped": ui_skipped, "failed": ui_failed},
    }
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for suite in counts.values() for value in suite.values()):
        raise ValueError("Automated validation counts must be non-negative integers")
    if set(scope_decisions) != set(SCOPE_DECISIONS):
        raise ValueError(f"Scope decisions must contain exactly: {', '.join(SCOPE_DECISIONS)}")
    normalized_scope = {name: str(scope_decisions[name]).upper() for name in SCOPE_DECISIONS}
    if any(value not in {"INCLUDED", "DEFERRED"} for value in normalized_scope.values()):
        raise ValueError("Every scope decision must be INCLUDED or DEFERRED")

    record = load_record(destination=destination, repository_root=repository_root)
    state = readiness(destination=destination, repository_root=repository_root)
    results = record["results"]
    supplemental_results = record["supplemental_results"]
    all_results = (*results.values(), *supplemental_results.values())
    commits = {result["release_commit"] for result in all_results}
    platforms = {result["platform"] for result in all_results}
    environments = {result["environment"] for result in all_results}
    if len(commits) > 1 or len(platforms) > 1 or len(environments) > 1:
        raise ValueError("All Stage B observations must describe one commit, platform, and environment")

    scenarios: dict[str, dict[str, object]] = {}
    for name in SCENARIOS:
        result = results.get(name)
        if result is None:
            scenarios[name] = {"verdict": "pending"}
            continue
        scenarios[name] = {
            "verdict": result["verdict"],
            "reviewer": result["reviewer"],
            "attested_utc": result["attested_utc"],
            "observation": result["note"],
            "screenshots": [dict(item) for item in result["screenshots"]],
            "zips": [dict(item) for item in result["zips"]],
        }
    supplemental: dict[str, dict[str, object]] = {}
    for name in SUPPLEMENTAL_CHECKS:
        result = supplemental_results.get(name)
        if result is None:
            supplemental[name] = {"verdict": "pending"}
            continue
        supplemental[name] = {
            "verdict": result["verdict"],
            "reviewer": result["reviewer"],
            "attested_utc": result["attested_utc"],
            "observation": result["note"],
            "screenshots": [dict(item) for item in result["screenshots"]],
        }

    full_regression_passed = (
        backend_failed == 0 and ui_failed == 0
        and backend_passed > 0 and ui_passed > 0
    )
    all_optional_scope_deferred = all(value == "DEFERRED" for value in normalized_scope.values())
    frozen = (
        state["status"] == "MANUALLY_ACCEPTED"
        and full_regression_passed
        and all_optional_scope_deferred
    )
    fixture_manifest = _require_current_fixtures(destination)
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "stage": "pre_week08_stage_b_ui_acceptance",
        "acceptance_record_schema": SCHEMA_VERSION,
        "tested_release_commit": next(iter(commits), None),
        "target": {
            "platform": next(iter(platforms), None),
            "environment": next(iter(environments), None),
        },
        "manual_status": state["status"],
        "manual_cases_accepted": state["passed"],
        "manual_cases_total": state["total"],
        "supplemental_checks_accepted": state["supplemental_passed"],
        "supplemental_checks_total": state["supplemental_total"],
        "scenarios": scenarios,
        "supplemental_observations": supplemental,
        "fixture_manifest_sha256": _sha(fixture_manifest) if fixture_manifest.is_file() else None,
        "automated_validation": counts,
        "full_regression_zero_failures": full_regression_passed,
        "scope_decisions": normalized_scope,
        "formal_ui_v02_frozen": frozen,
        "frozen_ui_version": "v0.2" if frozen else None,
        "week8_heldout_used": False,
        "limitations": state["limitations"],
    }


def write_validation_report(*, output: Path, **kwargs: object) -> dict:
    """Write the sanitized validation report; freeze status is derived, never supplied."""
    report = build_validation_report(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
