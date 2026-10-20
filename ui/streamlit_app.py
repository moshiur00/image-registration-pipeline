"""Streamlit entry point for the image-registration research workbench."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    import_root_text = str(import_root)
    if import_root_text not in sys.path:
        sys.path.insert(0, import_root_text)

from ui.adapters import build_default_registration_service
from ui.automatic import AutomaticComparisonService
from ui.core import DatasetCatalog
from ui.streamlit.pages.automatic_comparison import render_automatic_comparison
from ui.streamlit.pages.benchmark_explorer import render_benchmark_explorer
from ui.streamlit.pages.method_reference import render_method_reference
from ui.streamlit.pages.workbench import render_workbench


def _load_css() -> str:
    path = Path(__file__).resolve().parent / "assets" / "research.css"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - optional UI dependency
        raise RuntimeError(
            "Streamlit is not installed. Install ui/requirements.txt in the UI environment before launching the workbench."
        ) from exc

    st.set_page_config(
        page_title="Image Registration Workbench",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    css = _load_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    @st.cache_resource
    def application_objects():
        catalog = DatasetCatalog()
        service = build_default_registration_service(example_provider=catalog)
        automatic_service = AutomaticComparisonService(registration_service=service)
        return catalog, service, automatic_service

    catalog, service, automatic_service = application_objects()

    st.markdown('<div class="research-app-name">IMAGE REGISTRATION PIPELINE</div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("## Navigation")
        if "ui_page" not in st.session_state:
            st.session_state["ui_page"] = "Workbench"
        page = st.radio(
            "View",
            ["Workbench", "Automatic comparison", "Benchmark examples", "Method reference"],
            key="ui_page",
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("Image Registration Pipeline · UI v0.2 preview")

    if page == "Workbench":
        render_workbench(service, catalog)
    elif page == "Automatic comparison":
        render_automatic_comparison(automatic_service)
    elif page == "Benchmark examples":
        render_benchmark_explorer(catalog, service)
    else:
        render_method_reference(service)


if __name__ == "__main__":
    main()
