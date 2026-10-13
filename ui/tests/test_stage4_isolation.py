from __future__ import annotations

from pathlib import Path


def test_streamlit_layer_does_not_import_research_backend_directly() -> None:
    root = Path(__file__).resolve().parents[1] / "streamlit"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from image_registration" in text or "import image_registration" in text:
            offenders.append(path.name)
    assert offenders == []


def test_stage4_files_are_inside_ui_package() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / "streamlit_app.py",
        root / "streamlit" / "pages" / "workbench.py",
        root / "streamlit" / "pages" / "benchmark_explorer.py",
        root / "streamlit" / "pages" / "method_reference.py",
        root / "assets" / "research.css",
    ]
    assert all(path.is_file() for path in expected)


def test_stage4_main_content_keeps_clearance_below_streamlit_toolbar() -> None:
    css_path = Path(__file__).resolve().parents[1] / "assets" / "research.css"
    css = css_path.read_text(encoding="utf-8")
    assert '[data-testid="stMainBlockContainer"]' in css
    assert 'padding-top: 4.5rem !important;' in css
