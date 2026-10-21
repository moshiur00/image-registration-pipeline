"""Create a project archive or a deliberately selected benchmark evidence archive.

Generated outputs are excluded from the default project archive. A named folder
below outputs/ can be included explicitly, without archiving unrelated runs.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from datetime import datetime
from pathlib import Path


INCLUDE_FOLDERS = [
    "configs",
    "data/manifests",
    "data/samples",
    "docs",
    "reports",
    "scripts",
    "src",
    "tests",
    "ui",
]

INCLUDE_ROOT_FILES = [
    ".gitattributes",
    ".gitignore",
    "pyproject.toml",
    "README.md",
    "requirements.txt",
]

EXCLUDED_DIR_NAMES = {
    ".venv",
    "venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "__pycache__",
    "outputs",
    "build",
    "dist",
    "image_registration_pipeline.egg-info",
}

EXCLUDED_FILE_SUFFIXES = {
    ".pyc", ".pyo", ".log", ".tmp", ".zip", ".key", ".pem", ".p12", ".pfx",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "secrets.toml",
    ".env",
    "credentials.json",
    "token.json",
    "id_rsa",
    "id_ed25519",
}
EXCLUDED_RELATIVE_PATHS = {Path("scripts/scripts.txt")}

# Only evidence-oriented outputs are allowed in the opt-in export. This also
# avoids embedding large source datasets, virtual environments and raw dumps.
EVIDENCE_FILE_SUFFIXES = {
    ".csv", ".json", ".jsonl", ".txt", ".md", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".parquet",
}
EVIDENCE_EXCLUDED_DIR_NAMES = {
    "raw", "datasets", "source_images", "raw_images", "original_images",
}
BENCHMARK_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def should_exclude(relative_path: Path) -> bool:
    """Apply the original project exclusions plus sensitive file exclusions."""
    if relative_path.parts[:2] == ("ui", "runtime"):
        return relative_path.name != ".gitignore"
    if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts):
        return True
    if relative_path in EXCLUDED_RELATIVE_PATHS:
        return True
    if relative_path.name in EXCLUDED_FILE_NAMES:
        return True
    if relative_path.name.startswith(".env."):
        return True
    if relative_path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
        return True
    return False


def should_exclude_evidence(relative_path: Path) -> bool:
    """Exclude non-evidence files inside an explicitly selected output folder."""
    # relative_path starts with outputs/<benchmark-name>/; do not apply the
    # general outputs/ exclusion to the selected evidence itself.
    inner = Path(*relative_path.parts[2:])
    if not inner.parts:
        return True
    if any(part in EVIDENCE_EXCLUDED_DIR_NAMES for part in inner.parts[:-1]):
        return True
    if should_exclude(inner):
        return True
    if inner.suffix.lower() not in EVIDENCE_FILE_SUFFIXES:
        return True
    return False


def benchmark_folder(project_root: Path, name: str) -> Path:
    """Select exactly one direct child of outputs/, rejecting unsafe paths."""
    if not BENCHMARK_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError(
            "Benchmark name must be one directory name inside outputs/ "
            "(example: week07_day02_full); no paths or '..' are allowed."
        )

    outputs = project_root / "outputs"
    folder = outputs / name
    if outputs.is_symlink() or folder.is_symlink():
        raise ValueError("Symlinked output folders are not permitted.")
    if not folder.is_dir():
        raise ValueError(f"Benchmark evidence directory does not exist: {folder}")
    if not folder.resolve().is_relative_to(outputs.resolve()):
        raise ValueError("Selected benchmark folder is outside outputs/.")
    return folder


def add_file(
    archive: zipfile.ZipFile,
    file_path: Path,
    project_root: Path,
    *,
    evidence: bool = False,
) -> bool:
    """Add a safe project-relative file, returning whether it was included."""
    if file_path.is_symlink() or not file_path.is_file():
        return False
    if not file_path.resolve().is_relative_to(project_root.resolve()):
        return False
    relative_path = file_path.relative_to(project_root)
    if evidence:
        if should_exclude_evidence(relative_path):
            return False
    elif should_exclude(relative_path):
        return False
    archive.write(file_path, arcname=relative_path.as_posix())
    print(f"  + {relative_path.as_posix()}")
    return True


def add_folder(
    archive: zipfile.ZipFile,
    folder_path: Path,
    project_root: Path,
    *,
    evidence: bool = False,
) -> int:
    """Recursively add allowed files, without following symlink directories."""
    if not folder_path.exists():
        print(f"  ! Skipping missing folder: {folder_path.relative_to(project_root)}")
        return 0
    included = 0
    for file_path in sorted(folder_path.rglob("*")):
        if file_path.is_symlink():
            continue
        if file_path.is_file():
            included += int(add_file(archive, file_path, project_root, evidence=evidence))
    return included


def create_project_zip(
    *,
    project_root: Path | None = None,
    include_benchmark: str | None = None,
    evidence_only: str | None = None,
    output_path: Path | None = None,
) -> Path:
    """Create a default, full-with-evidence, or evidence-only ZIP.

    All selected evidence is stored at outputs/<benchmark>/<relative-file>.
    The default call remains a lightweight code, config, and documentation ZIP.
    """
    if include_benchmark is not None and evidence_only is not None:
        raise ValueError("Choose only one of include_benchmark or evidence_only.")

    project_root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    chosen_name = include_benchmark if include_benchmark is not None else evidence_only
    folder = benchmark_folder(project_root, chosen_name) if chosen_name is not None else None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    if evidence_only is not None:
        archive_name = f"{project_root.name}_evidence_{chosen_name}_{timestamp}.zip"
    elif include_benchmark is not None:
        archive_name = f"{project_root.name}_share_{chosen_name}_{timestamp}.zip"
    else:
        archive_name = f"{project_root.name}_share_{timestamp}.zip"
    output_path = output_path or project_root.parent / archive_name
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("IMAGE REGISTRATION PROJECT ARCHIVE")
    print("=" * 65)
    print(f"Project : {project_root}")
    print(f"Output  : {output_path}")
    print(f"Mode    : {'evidence-only' if evidence_only else 'project + evidence' if folder else 'project-only'}")
    if chosen_name is not None:
        print(f"Evidence: outputs/{chosen_name}/")
    print()

    with zipfile.ZipFile(
        output_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
    ) as archive:
        project_count = 0
        evidence_count = 0
        if evidence_only is None:
            print("Adding project folders:")
            for folder_name in INCLUDE_FOLDERS:
                project_count += add_folder(archive, project_root / folder_name, project_root)
            print("\nAdding root project files:")
            for filename in INCLUDE_ROOT_FILES:
                path = project_root / filename
                if path.exists():
                    project_count += int(add_file(archive, path, project_root))
                else:
                    print(f"  ! Skipping missing file: {filename}")
        if folder is not None:
            print("\nAdding selected benchmark evidence:")
            evidence_count = add_folder(archive, folder, project_root, evidence=True)
            if not evidence_count:
                # An empty evidence archive would be misleading. Remove it
                # rather than leaving an apparently successful ZIP behind.
                archive.close()
                output_path.unlink(missing_ok=True)
                raise ValueError(
                    f"No permitted evidence files found in outputs/{chosen_name}/. "
                    "Check the selected folder and its contents."
                )

    # All archives are tested for structural corruption before being returned.
    with zipfile.ZipFile(output_path) as archive:
        bad_file = archive.testzip()
    if bad_file is not None:
        raise OSError(f"Corrupt file in generated ZIP: {bad_file}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 65)
    print("ARCHIVE CREATED")
    print("=" * 65)
    print(f"File           : {output_path}")
    print(f"Size           : {size_mb:.2f} MB")
    print(f"Project files  : {project_count}")
    print(f"Evidence files : {evidence_count}")
    print()
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Share the project and optionally one selected benchmark run."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--include-benchmark", metavar="NAME",
        help="Include outputs/NAME/ in the normal project ZIP.",
    )
    selection.add_argument(
        "--evidence-only", metavar="NAME",
        help="Archive only selected evidence under outputs/NAME/.",
    )
    args = parser.parse_args()
    try:
        create_project_zip(
            include_benchmark=args.include_benchmark,
            evidence_only=args.evidence_only,
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
