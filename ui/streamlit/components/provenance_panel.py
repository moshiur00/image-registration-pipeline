"""Compact human-facing provenance with optional raw metadata."""

from __future__ import annotations

from ui.core.contracts import RegistrationRun
from ui.core.result_presenter import to_json_safe
from ui.streamlit.components.metrics_panel import humanize_transform_direction


def render_provenance(run: RegistrationRun, *, method_name: str) -> None:
    import streamlit as st

    with st.expander("Provenance", expanded=False):
        rows = [
            {"Field": "Method", "Value": method_name},
            {
                "Field": "Transform direction",
                "Value": humanize_transform_direction(run.provenance.transform_direction),
            },
            {
                "Field": "Ground truth",
                "Value": run.provenance.ground_truth_status.value.replace("_", " ").title(),
            },
            {"Field": "Package version", "Value": run.provenance.package_version},
            {
                "Field": "Input integrity",
                "Value": "SHA-256 recorded" if run.provenance.fixed_sha256 and run.provenance.moving_sha256 else "Not available",
            },
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("Input hashes and normalized parameters are retained for reproducibility.")
        with st.expander("Raw provenance", expanded=False):
            st.json(
                to_json_safe(
                    {
                        "fixed_sha256": run.provenance.fixed_sha256,
                        "moving_sha256": run.provenance.moving_sha256,
                        "method_id": run.provenance.method_id,
                        "transform_direction": run.provenance.transform_direction,
                        "package_version": run.provenance.package_version,
                        "ground_truth_status": run.provenance.ground_truth_status,
                        "normalized_parameters": run.provenance.normalized_parameters,
                        "preprocessing": run.provenance.preprocessing,
                    }
                ),
                expanded=False,
            )
