"""Regression and safety checks for optional benchmark evidence sharing."""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "zip_project.py"
spec = importlib.util.spec_from_file_location("zip_project_benchmark_test", SCRIPT)
assert spec is not None and spec.loader is not None
zip_project = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = zip_project
spec.loader.exec_module(zip_project)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    root = tmp_path / "demo_registration"
    for folder in ("scripts", "src", "reports", "outputs/week07_day02_full", "outputs/unrelated"):
        (root / folder).mkdir(parents=True)
    (root / "README.md").write_text("source project", encoding="utf-8")
    (root / "scripts" / "main.py").write_text("print('ok')", encoding="utf-8")
    evidence = root / "outputs" / "week07_day02_full"
    (evidence / "benchmark_results.csv").write_text("method,status\nmi,completed\n", encoding="utf-8")
    (evidence / "severity_summary.json").write_text("{}", encoding="utf-8")
    (evidence / "day32_manifest.json").write_text("{}", encoding="utf-8")
    (evidence / "runner_records.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "outputs" / "unrelated" / "secret.csv").write_text("unrelated", encoding="utf-8")
    return root


def make_zip(root: Path, tmp_path: Path, **options: object) -> set[str]:
    with redirect_stdout(io.StringIO()):
        created = zip_project.create_project_zip(
            project_root=root, output_path=tmp_path / "artifact.zip", **options,
        )
    with zipfile.ZipFile(created) as archive:
        assert archive.testzip() is None
        return set(archive.namelist())


def test_default_archive_remains_lightweight(sample_project: Path, tmp_path: Path) -> None:
    names = make_zip(sample_project, tmp_path)
    assert "README.md" in names
    assert "scripts/main.py" in names
    assert all(not name.startswith("outputs/") for name in names)


def test_include_benchmark_adds_only_named_run(sample_project: Path, tmp_path: Path) -> None:
    names = make_zip(sample_project, tmp_path, include_benchmark="week07_day02_full")
    assert "README.md" in names
    assert "outputs/week07_day02_full/benchmark_results.csv" in names
    assert "outputs/week07_day02_full/severity_summary.json" in names
    assert "outputs/week07_day02_full/day32_manifest.json" in names
    assert "outputs/week07_day02_full/runner_records.jsonl" in names
    assert "outputs/unrelated/secret.csv" not in names


def test_evidence_only_omits_project(sample_project: Path, tmp_path: Path) -> None:
    names = make_zip(sample_project, tmp_path, evidence_only="week07_day02_full")
    assert len(names) == 4
    assert all(name.startswith("outputs/week07_day02_full/") for name in names)


@pytest.mark.parametrize("invalid", ["../unrelated", "..", ".", "", "a/b", "a\\b", "/tmp", "C:\\Windows", "./week07_day02_full"])
def test_invalid_folder_names_are_rejected(sample_project: Path, invalid: str) -> None:
    with pytest.raises(ValueError, match="Benchmark name"):
        zip_project.create_project_zip(project_root=sample_project, evidence_only=invalid)


def test_nonexistent_folder_is_rejected(sample_project: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        zip_project.create_project_zip(project_root=sample_project, evidence_only="absent")


def test_sensitive_and_unrelated_files_excluded(sample_project: Path, tmp_path: Path) -> None:
    evidence = sample_project / "outputs" / "week07_day02_full"
    (evidence / ".env").write_text("SECRET=1", encoding="utf-8")
    (evidence / ".env.production").write_text("SECRET=1", encoding="utf-8")
    (evidence / "credentials.json").write_text("SECRET", encoding="utf-8")
    (evidence / "key.pem").write_text("SECRET", encoding="utf-8")
    (evidence / "notes.log").write_text("log", encoding="utf-8")
    (evidence / "raw").mkdir()
    (evidence / "raw" / "image.png").write_bytes(b"fake")
    (evidence / "__pycache__").mkdir()
    (evidence / "__pycache__" / "cache.json").write_text("{}", encoding="utf-8")
    names = make_zip(sample_project, tmp_path, evidence_only="week07_day02_full")
    assert len(names) == 4
    assert "outputs/week07_day02_full/benchmark_results.csv" in names


def test_evidence_gallery_images_kept(sample_project: Path, tmp_path: Path) -> None:
    gallery = sample_project / "outputs/week07_day02_full/failure_gallery"
    gallery.mkdir()
    (gallery / "case.png").write_bytes(b"image")
    names = make_zip(sample_project, tmp_path, evidence_only="week07_day02_full")
    assert "outputs/week07_day02_full/failure_gallery/case.png" in names


def test_empty_evidence_folder_fails(sample_project: Path, tmp_path: Path) -> None:
    empty = sample_project / "outputs" / "empty"
    empty.mkdir()
    archive_path = tmp_path / "nothing.zip"
    with pytest.raises(ValueError, match="No permitted evidence"):
        with redirect_stdout(io.StringIO()):
            zip_project.create_project_zip(project_root=sample_project, evidence_only="empty", output_path=archive_path)
    assert not archive_path.exists()


def test_symlinked_benchmark_folder_rejected(sample_project: Path) -> None:
    target = sample_project / "outside"
    target.mkdir()
    shortcut = sample_project / "outputs" / "linked"
    try:
        shortcut.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks not supported in this environment")
    with pytest.raises(ValueError, match="Symlinked"):
        zip_project.create_project_zip(project_root=sample_project, evidence_only="linked")


def test_symlinked_evidence_file_not_included(sample_project: Path, tmp_path: Path) -> None:
    secret = sample_project / "outside_secret.csv"
    secret.write_text("secret", encoding="utf-8")
    link = sample_project / "outputs/week07_day02_full/external.csv"
    try:
        link.symlink_to(secret)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks not supported in this environment")
    names = make_zip(sample_project, tmp_path, evidence_only="week07_day02_full")
    assert "outputs/week07_day02_full/external.csv" not in names


def test_both_modes_rejected(sample_project: Path) -> None:
    with pytest.raises(ValueError, match="Choose only one"):
        zip_project.create_project_zip(
            project_root=sample_project, include_benchmark="week07_day02_full",
            evidence_only="week07_day02_full",
        )
