"""Image comparison panels for the Streamlit workbench."""

from __future__ import annotations

import numpy as np

from .visuals import absolute_difference, alpha_overlay, checkerboard, edge_overlay, to_display_uint8


def render_input_triplet(
    *,
    fixed: np.ndarray,
    moving: np.ndarray,
    registered: np.ndarray | None,
) -> None:
    import streamlit as st

    columns = st.columns(3)
    columns[0].image(to_display_uint8(fixed), caption="Fixed", width="stretch")
    columns[1].image(to_display_uint8(moving), caption="Moving", width="stretch")
    if registered is None:
        columns[2].empty()
        columns[2].caption("Registered image unavailable")
    else:
        columns[2].image(to_display_uint8(registered), caption="Registered", width="stretch")


def _render_centered_image(image: np.ndarray) -> None:
    import streamlit as st

    left, center, right = st.columns([0.14, 0.72, 0.14])
    del left, right
    with center:
        st.image(image, width="stretch")


def render_visual_diagnostics(*, fixed: np.ndarray, registered: np.ndarray) -> None:
    import streamlit as st

    tabs = st.tabs(["Overlay", "Checkerboard", "Difference", "Edges"])
    with tabs[0]:
        _render_centered_image(alpha_overlay(fixed, registered))
        st.caption(
            "Equal-weight fixed/registered overlay. Neutral gray marks estimated regions outside valid overlap."
        )
    with tabs[1]:
        _render_centered_image(checkerboard(fixed, registered))
        st.caption(
            "Alternating fixed and registered tiles for local alignment inspection. Neutral gray marks estimated regions outside valid overlap."
        )
    with tabs[2]:
        _render_centered_image(absolute_difference(fixed, registered))
        st.caption(
            "Display-normalized absolute intensity difference. Neutral gray marks estimated regions outside valid overlap; display scaling does not affect evaluation metrics."
        )
    with tabs[3]:
        _render_centered_image(edge_overlay(fixed, registered))
        st.caption(
            "Fixed and registered edge locations shown together for structural inspection. Neutral gray marks estimated regions outside valid overlap."
        )
