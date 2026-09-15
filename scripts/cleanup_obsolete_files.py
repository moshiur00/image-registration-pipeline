"""Remove project files that have been retired by later updates."""

from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OBSOLETE_PATHS = [
    Path("scripts/scripts.txt"),
    Path("src/image_registration_pipeline.egg-info"),
]


def main() -> None:
    removed = 0
    for relative_path in OBSOLETE_PATHS:
        path = PROJECT_ROOT / relative_path
        if path.is_file() or path.is_symlink():
            path.unlink()
            print(f"Removed file: {relative_path}")
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path)
            print(f"Removed directory: {relative_path}")
            removed += 1
        else:
            print(f"Already absent: {relative_path}")

    print(f"Cleanup complete. Removed {removed} obsolete path(s).")


if __name__ == "__main__":
    main()
