from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(importlib.util.find_spec("streamlit") is None, reason="Streamlit not installed")
def test_streamlit_app_loads_without_exception() -> None:
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=20)
    assert not app.exception

    navigation = next(
        radio for radio in app.radio if getattr(radio, "key", None) == "ui_page"
    )
    assert navigation.options == ["Workbench", "Benchmark examples", "Method reference"]

    source_selector = next(
        radio for radio in app.radio if getattr(radio, "key", None) == "ui_source_mode"
    )
    assert source_selector.options == ["Research example", "Upload images", "RIRE status"]


def test_streamlit_entrypoint_bootstraps_project_root_for_cli_launch(tmp_path: Path) -> None:
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    project_root = app_path.parents[1]
    src_root = project_root / "src"
    probe = f"""
import importlib.util
from pathlib import Path
import sys

app_path = Path({str(app_path)!r})
project_root = Path({str(project_root)!r}).resolve()
src_root = Path({str(project_root / "src")!r}).resolve()
sys.path = [
    entry
    for entry in sys.path
    if not entry or Path(entry).resolve() not in {{project_root, src_root}}
]
sys.path.insert(0, str(app_path.parent))

spec = importlib.util.spec_from_file_location("streamlit_entrypoint_probe", app_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
assert str(project_root) in sys.path
assert str(src_root) in sys.path
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
