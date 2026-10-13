"""Regression checks for the compact, consistent page header hierarchy."""

from __future__ import annotations

from pathlib import Path


UI_ROOT = Path(__file__).resolve().parents[1]


def test_global_header_has_only_pipeline_eyebrow() -> None:
    source = (UI_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "IMAGE REGISTRATION PIPELINE" in source
    assert "Research interface for the validated monomodal and multimodal registration pipeline" not in source


def test_pages_use_one_title_and_one_concise_subtitle() -> None:
    workbench = (UI_ROOT / "streamlit" / "pages" / "workbench.py").read_text(encoding="utf-8")
    benchmark = (UI_ROOT / "streamlit" / "pages" / "benchmark_explorer.py").read_text(encoding="utf-8")
    methods = (UI_ROOT / "streamlit" / "pages" / "method_reference.py").read_text(encoding="utf-8")

    assert 'st.markdown("# Registration Workbench")' in workbench
    assert 'st.caption("Configure, run, and inspect monomodal and multimodal image registration.")' in workbench
    assert 'st.markdown("### Input images")' in workbench

    assert 'st.markdown("# Benchmark Examples")' in benchmark
    assert 'st.caption("Curated cases covering supported motion models and modality conditions.")' in benchmark

    assert 'st.markdown("# Method Reference")' in methods
    assert 'st.caption("Registration methods, supported transformations, and diagnostic outputs.")' in methods
