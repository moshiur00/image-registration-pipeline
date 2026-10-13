"""Evidence-aware result summary components."""

from __future__ import annotations

from typing import Any

from ui.core.contracts import RegistrationRun
from ui.core.enums import GroundTruthStatus
from ui.streamlit.view_model import evidence_status_label


_PARAMETER_LABELS = {
    "matrix_offset_tx": "Translation X",
    "matrix_offset_ty": "Translation Y",
    "determinant": "Determinant",
    "rotation_degrees": "Rotation",
    "scale": "Scale",
}

_GROUND_TRUTH_LABELS = {
    "mean_tre_pixels": "Mean TRE (px)",
    "matrix_offset_error_pixels": "Translation error (px)",
    "rotation_error_degrees": "Rotation error (deg)",
    "affine_linear_error": "Affine linear error",
}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return str(value)


def humanize_transform_direction(value: str) -> str:
    """Convert the stored machine direction into concise display text."""
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"moving_to_fixed", "moving_→_fixed"}:
        return "Moving → Fixed"
    if normalized in {"fixed_to_moving", "fixed_→_moving"}:
        return "Fixed → Moving"
    return str(value).replace("_", " ").title()


def humanize_transform_parameter(name: str) -> str:
    """Return a research-facing transform parameter label."""
    return _PARAMETER_LABELS.get(name, str(name).replace("_", " ").title())


def humanize_ground_truth_metric(name: str) -> str:
    """Return a research-facing ground-truth metric label."""
    return _GROUND_TRUTH_LABELS.get(name, str(name).replace("_", " ").title())


def render_run_header(run: RegistrationRun) -> None:
    import streamlit as st

    known = run.provenance.ground_truth_status is GroundTruthStatus.KNOWN
    label = evidence_status_label(
        ground_truth_known=known,
        run_status=run.run_status.value,
        within_tolerance=run.metrics.within_tolerance,
    )
    columns = st.columns(4)
    columns[0].metric("Run status", label)
    columns[1].metric("Runtime", f"{run.runtime_seconds * 1000.0:.2f} ms")
    columns[2].metric("Method execution", "Success" if run.method_success else "Failed")
    if run.transform is None or run.transform.plausible is None:
        plausibility = "n/a"
    else:
        plausibility = "Plausible" if run.transform.plausible else "CHECK"
    columns[3].metric("Transform", plausibility)


def render_metrics(run: RegistrationRun) -> None:
    import streamlit as st

    st.markdown("#### Metrics")
    metric_names = sorted(set(run.metrics.before) | set(run.metrics.after))
    if metric_names:
        rows = [
            {
                "Metric": name.upper(),
                "Before": _fmt(run.metrics.before.get(name)),
                "After": _fmt(run.metrics.after.get(name)),
            }
            for name in metric_names
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption(
            "NCC, SSIM, MAE, and MSE are descriptive image metrics. They do not by themselves establish geometric correctness."
        )
    else:
        st.caption("No descriptive metrics were available for this run.")

    if run.metrics.ground_truth:
        st.markdown("##### Ground-truth evaluation")
        rows = [
            {"Metric": humanize_ground_truth_metric(key), "Value": _fmt(value)}
            for key, value in sorted(run.metrics.ground_truth.items())
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
        if run.metrics.within_tolerance is not None:
            st.caption(
                "Tolerance state uses the existing method-specific development threshold carried into the curated UI example."
            )
    else:
        st.info("Ground truth unavailable. TRE and geometric correctness are not reported.")


def render_transform(run: RegistrationRun) -> None:
    import streamlit as st
    import numpy as np

    st.markdown("#### Estimated transform")
    if run.transform is None:
        st.caption("No transform was returned.")
        return
    direction = humanize_transform_direction(run.transform.direction)
    model = run.transform.motion_model.value.replace("_", " ").title()
    st.caption(f"Direction: {direction} | Model: {model}")
    matrix_text = np.array2string(
        run.transform.matrix,
        precision=6,
        suppress_small=False,
        floatmode="fixed",
    )
    st.code(matrix_text, language="text")
    if run.transform.parameters:
        st.dataframe(
            [
                {"Parameter": humanize_transform_parameter(key), "Value": _fmt(value, 6)}
                for key, value in run.transform.parameters.items()
            ],
            hide_index=True,
            width="stretch",
        )
    if run.transform.plausibility_reasons:
        st.warning("Transform plausibility notes: " + ", ".join(run.transform.plausibility_reasons))
