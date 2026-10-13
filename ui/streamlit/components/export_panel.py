"""Session-local export controls for a completed registration run."""

from __future__ import annotations

import numpy as np

from ui.core.contracts import RegistrationRun
from ui.core.export_service import build_run_exports


def render_exports(*, run: RegistrationRun, fixed: np.ndarray, moving: np.ndarray) -> None:
    import streamlit as st

    st.markdown("#### Export run")
    st.caption(
        "Exports are generated in memory for this session. They are not written to tracked research reports, configurations, or datasets."
    )
    if run.registered_array is None:
        st.caption("Registered output is unavailable, so run exports cannot be created.")
        return

    try:
        exports = build_run_exports(run=run, fixed=fixed, moving=moving)
    except ValueError as exc:
        st.warning(str(exc))
        return

    first = st.columns(3)
    first[0].download_button(
        "Registered PNG",
        data=exports["registered_png"].data,
        file_name=exports["registered_png"].filename,
        mime=exports["registered_png"].media_type,
        width="stretch",
    )
    first[1].download_button(
        "Transform JSON",
        data=exports["transform_json"].data,
        file_name=exports["transform_json"].filename,
        mime=exports["transform_json"].media_type,
        width="stretch",
    )
    first[2].download_button(
        "Summary JSON",
        data=exports["summary_json"].data,
        file_name=exports["summary_json"].filename,
        mime=exports["summary_json"].media_type,
        width="stretch",
    )

    second = st.columns(2)
    second[0].download_button(
        "Comparison PNG",
        data=exports["comparison_png"].data,
        file_name=exports["comparison_png"].filename,
        mime=exports["comparison_png"].media_type,
        width="stretch",
    )
    second[1].download_button(
        "Run bundle ZIP",
        data=exports["bundle_zip"].data,
        file_name=exports["bundle_zip"].filename,
        mime=exports["bundle_zip"].media_type,
        width="stretch",
        type="primary",
    )
    st.caption("The ZIP bundle also contains the full-precision registered array as NumPy `.npy` data.")
