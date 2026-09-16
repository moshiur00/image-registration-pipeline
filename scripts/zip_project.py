from __future__ import annotations

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

EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
EXCLUDED_FILE_NAMES = {".DS_Store", "Thumbs.db"}
EXCLUDED_RELATIVE_PATHS = {Path("scripts/scripts.txt")}


def should_exclude(relative_path: Path) -> bool:
    """Return True when a path should not be included in the project archive."""
    if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts):
        return True
    if relative_path in EXCLUDED_RELATIVE_PATHS:
        return True
    if relative_path.name in EXCLUDED_FILE_NAMES:
        return True
    if relative_path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
        return True
    return False


def add_file(
    archive: zipfile.ZipFile,
    file_path: Path,
    project_root: Path,
) -> None:
    """Add one file while preserving its project-relative path."""
    relative_path = file_path.relative_to(project_root)
    if should_exclude(relative_path):
        return
    archive.write(file_path, arcname=relative_path.as_posix())
    print(f"  + {relative_path}")


def add_folder(
    archive: zipfile.ZipFile,
    folder_path: Path,
    project_root: Path,
) -> None:
    """Recursively add files from a project folder."""
    if not folder_path.exists():
        print(f"  ! Skipping missing folder: {folder_path.relative_to(project_root)}")
        return

    for file_path in sorted(folder_path.rglob("*")):
        if file_path.is_file():
            add_file(archive, file_path, project_root)


def create_project_zip() -> Path:
    """Create a lightweight archive containing source, tests, configs, docs, and samples."""
    project_root = Path(__file__).resolve().parent.parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = project_root.parent / f"{project_root.name}_share_{timestamp}.zip"

    print()
    print("=" * 65)
    print("IMAGE REGISTRATION PROJECT ARCHIVE")
    print("=" * 65)
    print(f"Project : {project_root}")
    print(f"Output  : {output_path}")
    print()

    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        print("Adding project folders:")
        for folder_name in INCLUDE_FOLDERS:
            add_folder(archive, project_root / folder_name, project_root)

        print()
        print("Adding root project files:")
        for filename in INCLUDE_ROOT_FILES:
            file_path = project_root / filename
            if file_path.exists():
                add_file(archive, file_path, project_root)
            else:
                print(f"  ! Skipping missing file: {filename}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print()
    print("=" * 65)
    print("ARCHIVE CREATED")
    print("=" * 65)
    print(f"File : {output_path}")
    print(f"Size : {size_mb:.2f} MB")
    print()
    return output_path


if __name__ == "__main__":
    create_project_zip()
