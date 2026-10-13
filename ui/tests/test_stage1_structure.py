from __future__ import annotations

from pathlib import Path
import tomllib


UI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = UI_ROOT.parent


def test_stage1_required_structure_exists() -> None:
    required_paths = [
        UI_ROOT / "README.md",
        UI_ROOT / "DEVELOPMENT_STAGES.md",
        UI_ROOT / "requirements.txt",
        UI_ROOT / "pytest.ini",
        UI_ROOT / "streamlit_app.py",
        UI_ROOT / ".streamlit" / "config.toml",
        UI_ROOT / "core",
        UI_ROOT / "adapters",
        UI_ROOT / "streamlit" / "pages",
        UI_ROOT / "streamlit" / "components",
        UI_ROOT / "assets",
        UI_ROOT / "runtime" / ".gitignore",
        UI_ROOT / "evidence",
        UI_ROOT / "tests",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in required_paths if not path.exists()]
    assert not missing, f"Missing Stage 1 UI paths: {missing}"


def test_runtime_directory_is_session_artifact_only() -> None:
    ignore_text = (UI_ROOT / "runtime" / ".gitignore").read_text(encoding="utf-8")
    assert "*" in ignore_text.splitlines()
    assert "!.gitignore" in ignore_text.splitlines()


def test_root_test_discovery_remains_isolated() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = pyproject["tool"]["pytest"]["ini_options"]
    assert pytest_options["testpaths"] == ["tests"]


def test_streamlit_is_not_added_to_root_requirements() -> None:
    root_requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" not in root_requirements
    ui_requirements = (UI_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" in ui_requirements
