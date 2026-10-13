"""Method-specific diagnostics for the research workbench."""

from __future__ import annotations

from typing import Any

from ui.core.contracts import RegistrationRun
from ui.core.result_presenter import to_json_safe


_DIAGNOSTIC_LABELS = {
    "fixed_keypoints": "Fixed keypoints",
    "moving_keypoints": "Moving keypoints",
    "accepted_matches": "Accepted matches",
    "ransac_inliers": "RANSAC inliers",
    "ransac_outliers": "RANSAC outliers",
    "ransac_inlier_ratio": "RANSAC inlier ratio",
    "minimum_match_coverage": "Minimum spatial coverage",
    "response": "Phase response",
    "phase_response": "Phase response",
    "ecc": "Final ECC score",
    "ecc_value": "Final ECC score",
    "final_ecc": "Final ECC score",
    "final_metric_value": "Final MI value",
    "optimizer_iteration": "Optimizer iterations",
    "optimizer_stop_condition": "Stop condition",
    "valid_metric_points": "Valid metric points",
    "sampling_strategy": "Sampling strategy",
    "histogram_bins": "Histogram bins",
    "initialization": "Initialization",
}


def humanize_diagnostic_label(name: str) -> str:
    """Return a concise research-facing label for a diagnostic key."""
    return _DIAGNOSTIC_LABELS.get(name, str(name).replace("_", " ").title())


def format_diagnostic_value(name: str, value: Any) -> str | int | float:
    """Format common diagnostic values without discarding the raw record."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if name == "ransac_inlier_ratio" and isinstance(value, (int, float)):
        return f"{float(value) * 100.0:.1f}%"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, str):
        return value.replace("_", " ").title() if name in {"initialization", "sampling_strategy"} else value
    return value


def _metric_trace_rows(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, float]] = []
    for item in value:
        if not isinstance(item, dict) or "metric_value" not in item:
            continue
        rows.append(
            {
                "step": float(len(rows)),
                "metric_value": float(item["metric_value"]),
                "level": float(item.get("level", 0)),
                "iteration": float(item.get("iteration", len(rows))),
            }
        )
    return rows


def _rows(values: dict[str, Any], keys: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    return [
        {
            "Diagnostic": humanize_diagnostic_label(key),
            "Value": format_diagnostic_value(key, values[key]),
        }
        for key in keys
        if key in values
    ]


def render_diagnostics(run: RegistrationRun) -> None:
    import streamlit as st

    values = run.diagnostics.values
    st.markdown("#### Method diagnostics")
    if not values:
        st.caption("No method-specific diagnostics were returned.")
        return

    feature_keys = (
        "fixed_keypoints",
        "moving_keypoints",
        "accepted_matches",
        "ransac_inliers",
        "ransac_outliers",
        "ransac_inlier_ratio",
        "minimum_match_coverage",
    )
    feature_rows = _rows(values, feature_keys)
    if feature_rows:
        st.dataframe(feature_rows, hide_index=True, width="stretch")

    trace = _metric_trace_rows(values.get("metric_trace"))
    if trace:
        st.markdown("##### MI convergence trace")
        st.line_chart({"Mattes MI": [row["metric_value"] for row in trace]})

    summary_keys = [
        "response",
        "phase_response",
        "ecc",
        "ecc_value",
        "final_ecc",
        "final_metric_value",
        "optimizer_iteration",
        "optimizer_stop_condition",
        "valid_metric_points",
        "sampling_strategy",
        "histogram_bins",
        "initialization",
    ]
    summary_rows = _rows(values, summary_keys)
    if summary_rows:
        st.dataframe(summary_rows, hide_index=True, width="stretch")

    with st.expander("Raw diagnostic record", expanded=False):
        st.json(to_json_safe(values), expanded=False)
