"""Build, verify, and restore the deterministic frozen Week 7 evidence archive.

The archive contains exactly the 81 files named by the frozen baseline. Entries
are sorted, uncompressed, and written with fixed ZIP metadata. This utility
does not inspect or use Week 8 sources or labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
from typing import Any, Mapping
import zipfile


SCHEMA_VERSION = "week07_evidence_archive_v1"
PHASE1_COMMIT = "0ff4371419f5f6dd436e6b0ff33134e3e7946ebc"
BASELINE_REL = "configs/week08_frozen_baseline.json"
BASELINE_SHA256 = "03306f1b71453865944f611eb2da934be35f817d0bca78b11e4a36eb9989da01"
DEFAULT_ARCHIVE_REL = "deliverables/week07_frozen_evidence.zip"
DEFAULT_MANIFEST_REL = "reports/week07_evidence_archive_manifest.json"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FIXED_FILE_MODE = stat.S_IFREG | 0o644
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class FileAnchor:
    path: str
    sha256: str


@dataclass(frozen=True)
class ArchivePolicy:
    phase1_commit: str
    baseline: FileAnchor
    closure: FileAnchor
    handoff: FileAnchor
    closures: Mapping[str, FileAnchor]
    tree_counts: Mapping[str, int]


DEFAULT_POLICY = ArchivePolicy(
    phase1_commit=PHASE1_COMMIT,
    baseline=FileAnchor(BASELINE_REL, BASELINE_SHA256),
    closure=FileAnchor(
        "reports/week07_week_closure.json",
        "f42b3c2228939c5e27e4e4f1bb63257e6ce18b67fe9529036d02ab1157ebee43",
    ),
    handoff=FileAnchor(
        "reports/week07_day05_week08_handoff.json",
        "f5d0298b57d1e59b8b3dc8f52cf058b5a61ac0450b58af2524523e55fbd479f5",
    ),
    closures={
        "week07_day02_full": FileAnchor(
            "reports/week07_day02_full_closure.json",
            "4fce71bd1522b85a036dff8d6c1d6085f4ee63cef12330e45f6f1f5bdfd78829",
        ),
        "week07_day03_analysis": FileAnchor(
            "reports/week07_day03_closure.json",
            "f1978713371398fb9d1d8d68fb3643ff2366cf413845ad0dff6c4a0e6fa60e30",
        ),
        "week07_day04_calibration": FileAnchor(
            "reports/week07_day04_closure.json",
            "4ac27736eb2cff60fde2c54354bf304af8409b0feb9ec05e8a1d0905554effc2",
        ),
        "week07_day05_integration": FileAnchor(
            "reports/week07_day05_closure.json",
            "0a891963220d180651f613c49cb7c898b94b53aba2e793d9a3a16e36a88632e9",
        ),
    },
    tree_counts={
        "week07_day02_full": 7,
        "week07_day03_analysis": 36,
        "week07_day04_calibration": 11,
        "week07_day05_integration": 27,
    },
)


class EvidenceArchiveError(ValueError):
    """The evidence workspace, manifest, or archive violates the contract."""


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceArchiveError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceArchiveError(f"Cannot read JSON {path}: {exc}") from exc


def _stable_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_relative_path(value: str) -> PurePosixPath:
    """Validate the portable project-relative path wire format."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvidenceArchiveError(f"Invalid relative path: {value!r}")
    if "\\" in value or "\0" in value or ":" in value or value.startswith("/"):
        raise EvidenceArchiveError(f"Unsafe relative path: {value!r}")
    windows = PureWindowsPath(value)
    parts = value.split("/")
    if windows.drive or windows.root or any(part in {"", ".", ".."} for part in parts):
        raise EvidenceArchiveError(f"Unsafe relative path: {value!r}")
    relative = PurePosixPath(value)
    if relative.as_posix() != value:
        raise EvidenceArchiveError(f"Non-canonical relative path: {value!r}")
    return relative


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EvidenceArchiveError(f"Cannot inspect filesystem metadata: {path}: {exc}") from exc
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _checked_file(root: Path, relative: str) -> Path:
    rel = safe_relative_path(relative)
    current = root
    for part in rel.parts:
        current = current / part
        if not current.exists():
            raise EvidenceArchiveError(f"Missing required file: {relative}")
        if _is_link_or_reparse(current):
            raise EvidenceArchiveError(f"Symlink or reparse point is forbidden: {relative}")
    if not current.is_file():
        raise EvidenceArchiveError(f"Required path is not a file: {relative}")
    return current


def _verify_anchor(root: Path, anchor: FileAnchor, label: str) -> dict[str, str]:
    if HEX64.fullmatch(anchor.sha256) is None:
        raise EvidenceArchiveError(f"Invalid pinned SHA-256 for {label}")
    actual = file_sha256(_checked_file(root, anchor.path))
    if actual != anchor.sha256:
        raise EvidenceArchiveError(f"{label} hash mismatch: {actual} != {anchor.sha256}")
    return {"path": anchor.path, "sha256": actual}


def _tree_for(relative: str, policy: ArchivePolicy) -> str:
    parts = safe_relative_path(relative).parts
    if len(parts) < 3 or parts[0] != "outputs" or parts[1] not in policy.closures:
        raise EvidenceArchiveError(f"Evidence path is outside the four frozen trees: {relative}")
    return parts[1]


def _evidence_map(root: Path, policy: ArchivePolicy) -> dict[str, str]:
    _verify_anchor(root, policy.baseline, "Frozen baseline")
    document = read_json(root / Path(*safe_relative_path(policy.baseline.path).parts))
    evidence = document.get("week7_evidence_files") if isinstance(document, dict) else None
    if not isinstance(evidence, dict):
        raise EvidenceArchiveError("Baseline lacks a Week 7 evidence-file map")
    counts: Counter[str] = Counter()
    validated: dict[str, str] = {}
    for relative, expected_hash in evidence.items():
        tree = _tree_for(relative, policy)
        if not isinstance(expected_hash, str) or HEX64.fullmatch(expected_hash) is None:
            raise EvidenceArchiveError(f"Invalid SHA-256 for {relative}")
        validated[relative] = expected_hash
        counts[tree] += 1
    if set(counts) != set(policy.tree_counts):
        raise EvidenceArchiveError("Baseline does not cover exactly the four frozen evidence trees")
    for tree, expected_count in policy.tree_counts.items():
        if counts[tree] != expected_count:
            raise EvidenceArchiveError(
                f"Unexpected evidence count for {tree}: {counts[tree]} != {expected_count}"
            )
    return dict(sorted(validated.items()))


def _closure_records(root: Path, policy: ArchivePolicy) -> dict[str, dict[str, str]]:
    if set(policy.closures) != set(policy.tree_counts):
        raise EvidenceArchiveError("Closure and tree-count policies disagree")
    return {
        tree: _verify_anchor(root, policy.closures[tree], f"{tree} closure")
        for tree in sorted(policy.closures)
    }


def _scan_trees(root: Path, policy: ArchivePolicy) -> set[str]:
    found: set[str] = set()
    for tree in sorted(policy.tree_counts):
        tree_root = root / "outputs" / tree
        if not tree_root.is_dir():
            raise EvidenceArchiveError(f"Missing frozen evidence tree: outputs/{tree}")
        if _is_link_or_reparse(tree_root):
            raise EvidenceArchiveError(f"Frozen evidence tree cannot be a link: outputs/{tree}")
        for directory, dirnames, filenames in os.walk(tree_root, followlinks=False):
            directory_path = Path(directory)
            for name in dirnames:
                candidate = directory_path / name
                if _is_link_or_reparse(candidate):
                    raise EvidenceArchiveError(f"Linked evidence directory is forbidden: {candidate}")
            for name in filenames:
                candidate = directory_path / name
                if _is_link_or_reparse(candidate) or not candidate.is_file():
                    raise EvidenceArchiveError(f"Linked or non-file evidence is forbidden: {candidate}")
                found.add(candidate.relative_to(root).as_posix())
    return found


def _workspace_records(
    root: Path,
    evidence_map: Mapping[str, str],
    closures: Mapping[str, Mapping[str, str]],
    policy: ArchivePolicy,
) -> list[dict[str, Any]]:
    actual = _scan_trees(root, policy)
    expected = set(evidence_map)
    if actual != expected:
        raise EvidenceArchiveError(
            "Frozen evidence file set mismatch; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    records: list[dict[str, Any]] = []
    for relative, expected_hash in evidence_map.items():
        path = _checked_file(root, relative)
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise EvidenceArchiveError(f"Evidence hash mismatch: {relative}")
        tree = _tree_for(relative, policy)
        records.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": actual_hash,
                "closure_reference": closures[tree]["path"],
            }
        )
    return records


def _write_zip(root: Path, archive_path: Path, records: list[dict[str, Any]]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(archive_path.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for record in records:
                relative = record["path"]
                content = (root / Path(*PurePosixPath(relative).parts)).read_bytes()
                info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = FIXED_FILE_MODE << 16
                info.extra = b""
                info.comment = b""
                archive.writestr(info, content)
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)


def build_archive(
    *,
    project_root: Path,
    archive_path: Path,
    manifest_path: Path,
    policy: ArchivePolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """Build and self-verify the deterministic archive and tracked manifest."""
    root = project_root.resolve()
    archive_path = archive_path.resolve()
    manifest_path = manifest_path.resolve()
    evidence = _evidence_map(root, policy)
    closure = _verify_anchor(root, policy.closure, "Week 7 closure")
    handoff = _verify_anchor(root, policy.handoff, "Week 7 handoff")
    closures = _closure_records(root, policy)
    records = _workspace_records(root, evidence, closures, policy)
    _write_zip(root, archive_path, records)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase1_commit": policy.phase1_commit,
        "baseline": {"path": policy.baseline.path, "sha256": policy.baseline.sha256},
        "closure": closure,
        "handoff": handoff,
        "file_count": len(records),
        "tree_counts": dict(sorted(policy.tree_counts.items())),
        "closures": closures,
        "files": records,
        "archive": {
            "filename": archive_path.name,
            "size_bytes": archive_path.stat().st_size,
            "sha256": file_sha256(archive_path),
        },
    }
    _atomic_write(manifest_path, _stable_json(manifest))
    verify_archive(
        project_root=root,
        archive_path=archive_path,
        manifest_path=manifest_path,
        policy=policy,
        require_workspace=True,
    )
    return manifest


def _validated_manifest(
    root: Path,
    manifest_path: Path,
    policy: ArchivePolicy,
) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceArchiveError("Unsupported evidence-archive manifest schema")
    if manifest.get("phase1_commit") != policy.phase1_commit:
        raise EvidenceArchiveError("Phase 1 checkpoint binding mismatch")
    evidence = _evidence_map(root, policy)
    if manifest.get("baseline") != {"path": policy.baseline.path, "sha256": policy.baseline.sha256}:
        raise EvidenceArchiveError("Baseline record does not match the pinned inventory")
    if manifest.get("closure") != _verify_anchor(root, policy.closure, "Week 7 closure"):
        raise EvidenceArchiveError("Week 7 closure record mismatch")
    if manifest.get("handoff") != _verify_anchor(root, policy.handoff, "Week 7 handoff"):
        raise EvidenceArchiveError("Week 7 handoff record mismatch")
    closures = _closure_records(root, policy)
    if manifest.get("closures") != closures:
        raise EvidenceArchiveError("Per-tree closure records mismatch")
    if manifest.get("file_count") != len(evidence):
        raise EvidenceArchiveError("Manifest file count mismatch")
    if manifest.get("tree_counts") != dict(sorted(policy.tree_counts.items())):
        raise EvidenceArchiveError("Manifest tree counts mismatch")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(evidence):
        raise EvidenceArchiveError("Manifest file inventory has the wrong length")
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    for record in files:
        if not isinstance(record, dict) or set(record) != {
            "path", "size_bytes", "sha256", "closure_reference"
        }:
            raise EvidenceArchiveError("Malformed evidence file record")
        relative = record["path"]
        if relative in seen:
            raise EvidenceArchiveError(f"Duplicate manifest evidence path: {relative}")
        seen.add(relative)
        tree = _tree_for(relative, policy)
        counts[tree] += 1
        if relative not in evidence or record["sha256"] != evidence[relative]:
            raise EvidenceArchiveError(f"Manifest evidence hash is not baseline-bound: {relative}")
        size = record["size_bytes"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise EvidenceArchiveError(f"Invalid evidence size: {relative}")
        if record["closure_reference"] != closures[tree]["path"]:
            raise EvidenceArchiveError(f"Closure reference mismatch: {relative}")
    if seen != set(evidence) or dict(counts) != dict(policy.tree_counts):
        raise EvidenceArchiveError("Manifest does not contain the exact frozen evidence set")
    if files != sorted(files, key=lambda item: item["path"]):
        raise EvidenceArchiveError("Manifest evidence records are not sorted")
    return manifest, evidence, files


def _verify_zip(archive_path: Path, records: list[dict[str, Any]]) -> None:
    by_path = {record["path"]: record for record in records}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise EvidenceArchiveError("Archive contains duplicate member names")
            if names != sorted(by_path):
                raise EvidenceArchiveError("Archive member set or order differs from the manifest")
            if archive.testzip() is not None:
                raise EvidenceArchiveError("Archive CRC verification failed")
            for member in members:
                safe_relative_path(member.filename)
                if member.is_dir() or member.compress_type != zipfile.ZIP_STORED:
                    raise EvidenceArchiveError(f"Invalid archive member type: {member.filename}")
                if member.date_time != FIXED_ZIP_TIMESTAMP:
                    raise EvidenceArchiveError(f"Non-deterministic ZIP timestamp: {member.filename}")
                mode = member.external_attr >> 16
                if stat.S_IFMT(mode) != stat.S_IFREG or stat.S_IMODE(mode) != 0o644:
                    raise EvidenceArchiveError(f"Invalid ZIP member mode: {member.filename}")
                content = archive.read(member)
                record = by_path[member.filename]
                if len(content) != record["size_bytes"] or sha256(content).hexdigest() != record["sha256"]:
                    raise EvidenceArchiveError(f"Archived evidence mismatch: {member.filename}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceArchiveError(f"Cannot verify evidence archive: {exc}") from exc


def verify_archive(
    *,
    project_root: Path,
    archive_path: Path,
    manifest_path: Path,
    policy: ArchivePolicy = DEFAULT_POLICY,
    require_workspace: bool = True,
) -> dict[str, Any]:
    """Verify anchored metadata, archive bytes, and optionally workspace files."""
    root = project_root.resolve()
    archive_path = archive_path.resolve()
    manifest, evidence, records = _validated_manifest(root, manifest_path.resolve(), policy)
    archive_record = manifest.get("archive")
    if not isinstance(archive_record, dict) or set(archive_record) != {
        "filename", "size_bytes", "sha256"
    }:
        raise EvidenceArchiveError("Malformed archive record")
    if archive_record["filename"] != archive_path.name:
        raise EvidenceArchiveError("Archive filename does not match the manifest")
    if not archive_path.is_file():
        raise EvidenceArchiveError(f"Evidence archive is missing: {archive_path}")
    if archive_path.stat().st_size != archive_record["size_bytes"]:
        raise EvidenceArchiveError("Archive size does not match the manifest")
    if HEX64.fullmatch(str(archive_record["sha256"])) is None or file_sha256(archive_path) != archive_record["sha256"]:
        raise EvidenceArchiveError("Archive SHA-256 does not match the manifest")
    _verify_zip(archive_path, records)
    if require_workspace:
        workspace = _workspace_records(root, evidence, manifest["closures"], policy)
        if workspace != records:
            raise EvidenceArchiveError("Workspace evidence differs from the archive manifest")
    return manifest


def verify_restored_tree(
    *, project_root: Path, destination: Path, manifest_path: Path,
    policy: ArchivePolicy = DEFAULT_POLICY,
) -> None:
    """Verify an extracted evidence tree against the fully anchored manifest."""
    root = project_root.resolve()
    destination = destination.resolve()
    _, _, files = _validated_manifest(root, manifest_path.resolve(), policy)
    expected = {record["path"]: record for record in files}
    actual: set[str] = set()
    for directory, dirnames, filenames in os.walk(destination, followlinks=False):
        directory_path = Path(directory)
        for name in dirnames:
            if _is_link_or_reparse(directory_path / name):
                raise EvidenceArchiveError("Restored tree contains a linked directory")
        for name in filenames:
            candidate = directory_path / name
            if _is_link_or_reparse(candidate) or not candidate.is_file():
                raise EvidenceArchiveError("Restored tree contains a linked or non-file entry")
            actual.add(candidate.relative_to(destination).as_posix())
    if actual != set(expected):
        raise EvidenceArchiveError("Restored evidence file set differs from the manifest")
    for relative, record in expected.items():
        safe_relative_path(relative)
        path = destination / Path(*PurePosixPath(relative).parts)
        if path.stat().st_size != record.get("size_bytes") or file_sha256(path) != record.get("sha256"):
            raise EvidenceArchiveError(f"Restored evidence mismatch: {relative}")


def restore_archive(
    *,
    project_root: Path,
    archive_path: Path,
    manifest_path: Path,
    destination: Path,
    policy: ArchivePolicy = DEFAULT_POLICY,
) -> Path:
    """Restore verified evidence into a new or empty clean-staging directory."""
    verify_archive(
        project_root=project_root,
        archive_path=archive_path,
        manifest_path=manifest_path,
        policy=policy,
        require_workspace=False,
    )
    destination = destination.resolve()
    if destination.exists():
        if not destination.is_dir() or _is_link_or_reparse(destination):
            raise EvidenceArchiveError("Restore destination must be a normal directory")
        if any(destination.iterdir()):
            raise EvidenceArchiveError("Restore destination must be empty")
    else:
        destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                relative = safe_relative_path(member.filename)
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceArchiveError(f"Cannot restore evidence archive: {exc}") from exc
    verify_restored_tree(
        project_root=project_root,
        destination=destination,
        manifest_path=manifest_path,
        policy=policy,
    )
    return destination


def _rooted(root: Path, value: str | None, default: str) -> Path:
    chosen = Path(value) if value is not None else Path(default)
    return chosen if chosen.is_absolute() else root / chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--archive")
        command.add_argument("--manifest")
    restore = commands.add_parser("restore")
    restore.add_argument("--archive")
    restore.add_argument("--manifest")
    restore.add_argument("--destination", required=True)
    restored = commands.add_parser("verify-restored")
    restored.add_argument("--manifest")
    restored.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    archive_path = _rooted(root, getattr(args, "archive", None), DEFAULT_ARCHIVE_REL)
    manifest_path = _rooted(root, getattr(args, "manifest", None), DEFAULT_MANIFEST_REL)
    try:
        if args.command == "build":
            report = build_archive(
                project_root=root, archive_path=archive_path, manifest_path=manifest_path
            )
            print(json.dumps(report["archive"], indent=2, sort_keys=True))
        elif args.command == "verify":
            report = verify_archive(
                project_root=root, archive_path=archive_path, manifest_path=manifest_path
            )
            print(json.dumps(report["archive"], indent=2, sort_keys=True))
        elif args.command == "restore":
            path = restore_archive(
                project_root=root,
                archive_path=archive_path,
                manifest_path=manifest_path,
                destination=Path(args.destination),
            )
            print(f"Restored verified Week 7 evidence to {path}")
        else:
            verify_restored_tree(
                project_root=root,
                destination=Path(args.destination),
                manifest_path=manifest_path,
            )
            print(f"Verified restored Week 7 evidence in {Path(args.destination).resolve()}")
    except EvidenceArchiveError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
