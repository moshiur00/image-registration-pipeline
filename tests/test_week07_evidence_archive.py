"""Deterministic Week 7 evidence-archive and clean-restore tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "week07_evidence_archive.py"
spec = importlib.util.spec_from_file_location("week07_evidence_archive_test", SCRIPT)
assert spec is not None and spec.loader is not None
archive_tool = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = archive_tool
spec.loader.exec_module(archive_tool)


TREE_NAMES = (
    "week07_day02_full",
    "week07_day03_analysis",
    "week07_day04_calibration",
    "week07_day05_integration",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_policy(root: Path, *, phase1_commit: str = "a" * 40):
    closures = {}
    for tree in TREE_NAMES:
        path = root / "reports" / f"{tree}_closure.json"
        write_json(path, {"tree": tree, "status": "closed"})
        closures[tree] = archive_tool.FileAnchor(
            path.relative_to(root).as_posix(), archive_tool.file_sha256(path)
        )
    week_closure = root / "reports/week07_week_closure.json"
    handoff = root / "reports/week07_day05_week08_handoff.json"
    write_json(week_closure, {"status": "complete_development_stage"})
    write_json(handoff, {"independent_validation_completed": False})
    baseline = root / "configs/week08_frozen_baseline.json"
    return archive_tool.ArchivePolicy(
        phase1_commit=phase1_commit,
        baseline=archive_tool.FileAnchor(
            baseline.relative_to(root).as_posix(), archive_tool.file_sha256(baseline)
        ),
        closure=archive_tool.FileAnchor(
            week_closure.relative_to(root).as_posix(), archive_tool.file_sha256(week_closure)
        ),
        handoff=archive_tool.FileAnchor(
            handoff.relative_to(root).as_posix(), archive_tool.file_sha256(handoff)
        ),
        closures=closures,
        tree_counts={tree: 1 for tree in TREE_NAMES},
    )


@pytest.fixture
def sample_project(tmp_path: Path):
    root = tmp_path / "project"
    evidence = {}
    for index, tree in enumerate(TREE_NAMES):
        path = root / "outputs" / tree / f"evidence_{index}.json"
        write_json(path, {"tree": tree, "index": index})
        evidence[path.relative_to(root).as_posix()] = archive_tool.file_sha256(path)
    write_json(
        root / "configs/week08_frozen_baseline.json",
        {"version": "test", "week7_evidence_files": evidence},
    )
    policy = make_policy(root)
    archive = root / "deliverables/week07_frozen_evidence.zip"
    manifest = root / "reports/week07_evidence_archive_manifest.json"
    return root, policy, archive, manifest


def build(sample_project):
    root, policy, archive, manifest = sample_project
    result = archive_tool.build_archive(
        project_root=root,
        archive_path=archive,
        manifest_path=manifest,
        policy=policy,
    )
    return result, root, policy, archive, manifest


def test_repeated_builds_are_byte_identical_and_fully_bound(sample_project) -> None:
    first, root, policy, archive, manifest = build(sample_project)
    first_archive = archive.read_bytes()
    first_manifest = manifest.read_bytes()
    second = archive_tool.build_archive(
        project_root=root,
        archive_path=archive,
        manifest_path=manifest,
        policy=policy,
    )
    assert archive.read_bytes() == first_archive
    assert manifest.read_bytes() == first_manifest
    assert first == second
    assert first["schema_version"] == "week07_evidence_archive_v1"
    assert first["phase1_commit"] == "a" * 40
    assert first["baseline"] == {
        "path": policy.baseline.path,
        "sha256": policy.baseline.sha256,
    }
    assert first["closure"]["path"] == policy.closure.path
    assert first["handoff"]["path"] == policy.handoff.path
    assert first["file_count"] == 4
    assert set(first["tree_counts"]) == set(TREE_NAMES)
    assert {record["closure_reference"] for record in first["files"]} == {
        anchor.path for anchor in policy.closures.values()
    }
    archive_tool.verify_archive(
        project_root=root,
        archive_path=archive,
        manifest_path=manifest,
        policy=policy,
    )
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        assert [item.filename for item in members] == sorted(item.filename for item in members)
        assert all(item.compress_type == zipfile.ZIP_STORED for item in members)
        assert all(item.date_time == archive_tool.FIXED_ZIP_TIMESTAMP for item in members)
        assert all(stat.S_IMODE(item.external_attr >> 16) == 0o644 for item in members)


@pytest.mark.parametrize("change", ["missing", "extra", "tampered"])
def test_workspace_file_set_and_hashes_fail_closed(sample_project, change: str) -> None:
    root, policy, archive, manifest = sample_project
    first = root / "outputs" / TREE_NAMES[0] / "evidence_0.json"
    if change == "missing":
        first.unlink()
    elif change == "extra":
        (first.parent / "unexpected.json").write_text("{}", encoding="utf-8")
    else:
        first.write_text("tampered", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError):
        archive_tool.build_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )


@pytest.mark.parametrize(
    "unsafe",
    [
        "../escape.json",
        "/absolute.json",
        "C:/drive.json",
        "outputs\\week07_day02_full\\bad.json",
        "outputs/week07_day02_full/../bad.json",
    ],
)
def test_unsafe_baseline_paths_fail_closed(sample_project, unsafe: str) -> None:
    root, _, archive, manifest = sample_project
    baseline = root / "configs/week08_frozen_baseline.json"
    write_json(baseline, {"week7_evidence_files": {unsafe: "0" * 64}})
    policy = make_policy(root)
    with pytest.raises(archive_tool.EvidenceArchiveError, match="path|tree"):
        archive_tool.build_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )


def test_duplicate_json_keys_fail_closed(sample_project) -> None:
    root, _, archive, manifest = sample_project
    baseline = root / "configs/week08_frozen_baseline.json"
    baseline.write_text(
        '{"week7_evidence_files":{"outputs/week07_day02_full/x.json":"'
        + "0" * 64
        + '","outputs/week07_day02_full/x.json":"'
        + "0" * 64
        + '"}}',
        encoding="utf-8",
    )
    policy = make_policy(root)
    with pytest.raises(archive_tool.EvidenceArchiveError, match="Duplicate JSON key"):
        archive_tool.build_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", -1),
        ("sha256", "0" * 64),
        ("closure_reference", "reports/wrong.json"),
    ],
)
def test_manifest_file_tampering_fails_closed(sample_project, field: str, value) -> None:
    _, root, policy, archive, manifest = build(sample_project)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["files"][0][field] = value
    write_json(manifest, document)
    with pytest.raises(archive_tool.EvidenceArchiveError):
        archive_tool.verify_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )


def test_closure_handoff_and_baseline_tampering_fail_closed(sample_project) -> None:
    _, root, policy, archive, manifest = build(sample_project)
    (root / policy.closure.path).write_text("tampered", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="closure hash mismatch"):
        archive_tool.verify_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )
    write_json(root / policy.closure.path, {"status": "complete_development_stage"})
    (root / policy.handoff.path).write_text("tampered", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="handoff hash mismatch"):
        archive_tool.verify_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )
    write_json(root / policy.handoff.path, {"independent_validation_completed": False})
    (root / policy.baseline.path).write_text("{}", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="baseline hash mismatch"):
        archive_tool.verify_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )


def test_archive_duplicate_member_fails_with_updated_outer_hash(sample_project) -> None:
    _, root, policy, _, manifest = build(sample_project)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    duplicate = root / "deliverables/duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w", compression=zipfile.ZIP_STORED) as zf:
            for record in document["files"] + [document["files"][0]]:
                content = (root / Path(*record["path"].split("/"))).read_bytes()
                info = zipfile.ZipInfo(record["path"], archive_tool.FIXED_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = archive_tool.FIXED_FILE_MODE << 16
                zf.writestr(info, content)
    document["archive"] = {
        "filename": duplicate.name,
        "size_bytes": duplicate.stat().st_size,
        "sha256": archive_tool.file_sha256(duplicate),
    }
    write_json(manifest, document)
    with pytest.raises(archive_tool.EvidenceArchiveError, match="duplicate"):
        archive_tool.verify_archive(
            project_root=root,
            archive_path=duplicate,
            manifest_path=manifest,
            policy=policy,
            require_workspace=False,
        )


def test_restore_requires_empty_target_and_verifies_clean_tree(
    sample_project, tmp_path: Path
) -> None:
    _, root, policy, archive, manifest = build(sample_project)
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="empty"):
        archive_tool.restore_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            destination=nonempty,
            policy=policy,
        )
    assert (nonempty / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"

    clean = tmp_path / "clean"
    archive_tool.restore_archive(
        project_root=root,
        archive_path=archive,
        manifest_path=manifest,
        destination=clean,
        policy=policy,
    )
    archive_tool.verify_restored_tree(
        project_root=root, destination=clean, manifest_path=manifest, policy=policy
    )
    restored = clean / "outputs" / TREE_NAMES[0] / "evidence_0.json"
    restored.write_text("tampered", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="mismatch"):
        archive_tool.verify_restored_tree(
            project_root=root, destination=clean, manifest_path=manifest, policy=policy
        )


def test_restored_tree_verification_rechecks_policy_anchors(sample_project, tmp_path: Path) -> None:
    _, root, policy, archive, manifest = build(sample_project)
    clean = tmp_path / "policy_bound_clean"
    archive_tool.restore_archive(
        project_root=root,
        archive_path=archive,
        manifest_path=manifest,
        destination=clean,
        policy=policy,
    )
    (root / policy.closure.path).write_text("tampered", encoding="utf-8")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="closure hash mismatch"):
        archive_tool.verify_restored_tree(
            project_root=root,
            destination=clean,
            manifest_path=manifest,
            policy=policy,
        )


def test_symlinked_evidence_is_rejected(sample_project) -> None:
    root, policy, archive, manifest = sample_project
    target = root / "outside.json"
    target.write_text("outside", encoding="utf-8")
    link = root / "outputs" / TREE_NAMES[0] / "linked.json"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks not supported in this environment")
    with pytest.raises(archive_tool.EvidenceArchiveError, match="Linked|link"):
        archive_tool.build_archive(
            project_root=root,
            archive_path=archive,
            manifest_path=manifest,
            policy=policy,
        )
