from __future__ import annotations

from pathlib import Path

import numpy as np

from ui.streamlit.components.metrics_panel import (
    humanize_ground_truth_metric,
    humanize_transform_direction,
    humanize_transform_parameter,
)
from ui.streamlit.components.visuals import absolute_difference, estimated_valid_warp_mask


def test_transform_display_labels_are_human_readable() -> None:
    assert humanize_transform_direction("moving_to_fixed") == "Moving → Fixed"
    assert humanize_transform_parameter("matrix_offset_tx") == "Translation X"
    assert humanize_transform_parameter("matrix_offset_ty") == "Translation Y"
    assert humanize_transform_parameter("determinant") == "Determinant"
    assert humanize_ground_truth_metric("mean_tre_pixels") == "Mean TRE (px)"


def test_estimated_valid_warp_mask_marks_border_connected_zero_fill() -> None:
    registered = np.zeros((12, 14), dtype=np.float32)
    registered[2:10, 3:11] = 1.0
    valid = estimated_valid_warp_mask(registered)
    assert valid.dtype == np.bool_
    assert not bool(valid[0, 0])
    assert bool(valid[5, 6])


def test_difference_display_normalizes_valid_residuals_and_masks_border() -> None:
    fixed = np.zeros((12, 14), dtype=np.float32)
    registered = np.zeros((12, 14), dtype=np.float32)
    fixed[2:10, 3:9] = 1.0
    registered[2:10, 4:10] = 1.0
    display = absolute_difference(fixed, registered)
    assert display.dtype == np.uint8
    assert display[0, 0] == 96
    assert display[5, 9] == 255


def test_unknown_ground_truth_notice_is_rendered_once_in_workbench_path() -> None:
    root = Path(__file__).resolve().parents[1]
    workbench = (root / "streamlit" / "pages" / "workbench.py").read_text(encoding="utf-8")
    metrics = (root / "streamlit" / "components" / "metrics_panel.py").read_text(encoding="utf-8")
    assert "Unknown-image mode reports" not in workbench
    assert metrics.count("Ground truth unavailable. TRE and geometric correctness are not reported.") == 1


def test_primary_button_text_contrast_is_protected() -> None:
    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "research.css").read_text(encoding="utf-8")
    assert '.stButton > button[kind="primary"] p' in css
    assert "color: #ffffff !important;" in css


def test_diagnostics_and_provenance_are_human_facing_by_default() -> None:
    root = Path(__file__).resolve().parents[1]
    diagnostics = (root / "streamlit" / "components" / "diagnostics_panel.py").read_text(encoding="utf-8")
    provenance = (root / "streamlit" / "components" / "provenance_panel.py").read_text(encoding="utf-8")
    assert "Final ECC score" in diagnostics
    assert "Raw diagnostic record" in diagnostics
    assert "SHA-256 recorded" in provenance
    assert "Raw provenance" in provenance


def test_workbench_suppresses_redundant_ground_truth_warning_and_renders_exports() -> None:
    root = Path(__file__).resolve().parents[1]
    workbench = (root / "streamlit" / "pages" / "workbench.py").read_text(encoding="utf-8")
    assert 'if "ground truth" in normalized_warning' in workbench
    assert "render_exports" in workbench
    assert "render_provenance" in workbench
