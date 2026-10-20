"""Stage 6.5 export, support masking, and UI pre-freeze regression checks."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from ui.automatic.automatic_export import build_automatic_analysis_export
from ui.automatic.candidate_inspection import reconstruct_visual_inspection
from ui.automatic.candidate_summary import diagnostic_highlights, execution_issues, reference_limitations
from ui.streamlit.components.visuals import alpha_overlay, absolute_difference, edge_overlay
from ui.tests.test_stage6_agreement_inspection import _candidate, _request, _view


UI_ROOT = Path(__file__).resolve().parents[1]


def _bundle(view=None, request=None):
    return build_automatic_analysis_export(request=request or _request(), view=view or _view())


def _files(bundle):
    with ZipFile(BytesIO(bundle.data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_export_payload_has_correct_media_type_and_name():
    payload = _bundle()
    assert payload.media_type == "application/zip"
    assert payload.filename.endswith("_automatic_analysis.zip")
    assert payload.data[:2] == b"PK"


def test_export_contains_complete_evidence_and_manifest():
    content = _files(_bundle())
    assert {"README.txt", "manifest.json", "analysis.json", "candidate_comparison.csv", "candidate_execution_issues.csv", "pairwise_agreement.csv"} <= content.keys()
    report = json.loads(content["analysis.json"])
    manifest = json.loads(content["manifest.json"])
    assert report["recommendation"]["selected_candidate_id"] is None
    assert len(report["candidates"]) == 2
    assert manifest["transform_direction"] == "Moving -> Fixed"
    assert manifest["ground_truth"] == "unavailable"
    assert len(manifest["fixed_sha256"]) == 64
    assert len(manifest["moving_sha256"]) == 64
    assert manifest["source_image_bytes_included"] is False
    assert manifest["preview_warp_interpolation"] == "linear"


def test_export_keeps_all_candidate_evidence_and_diagnostics():
    content = _files(_bundle())
    candidates = [name for name in content if name.endswith("/evidence.json")]
    assert len(candidates) == 2
    first = json.loads(content[candidates[0]])
    assert first["method_diagnostics"]["ecc_objective"] == 0.91
    assert first["estimated_transform"][0][2] == 2.0
    assert b"ECC" in content["candidate_comparison.csv"]
    assert b"ORB" in content["candidate_comparison.csv"]
    assert b"2.5" in content["pairwise_agreement.csv"]


def test_export_labels_reconstructed_images_and_masks():
    content = _files(_bundle())
    assert len([name for name in content if name.endswith("/registered_INSPECTION_ONLY.png")]) == 2
    assert len([name for name in content if name.endswith("/registered_INSPECTION_ONLY.npy")]) == 2
    assert len([name for name in content if name.endswith("/geometric_source_support.png")]) == 2
    assert b"NOT adapter-native outputs" in content["README.txt"]
    assert b"inspection-only reconstruction" in content["manifest.json"]


def test_export_is_deterministic_for_identical_request_and_view():
    assert _bundle().data == _bundle().data


def test_export_with_single_candidate_does_not_invent_consensus():
    content = _files(_bundle(view=_view(single=True)))
    analysis = json.loads(content["analysis.json"])
    assert analysis["agreement"]["status"] == "insufficient_candidates"
    assert analysis["agreement"]["consensus_anchor"]["candidate_id"] is None
    assert len(analysis["candidates"]) == 1


def test_export_preserves_failed_candidate_without_registered_image():
    view = _view(single=True)
    failed = replace(_candidate("failed", status="failed"),
        failure_reason="no valid matches", estimated_transform=None,
        registered_output_available=False)
    view = replace(view, candidates=view.candidates + (failed,))
    content = _files(_bundle(view=view))
    analysis = json.loads(content["analysis.json"])
    assert analysis["candidates"][1]["failure_reason"] == "no valid matches"
    failed_folder = next(path.rsplit("/", 1)[0] for path in content if path.endswith("/evidence.json") and "failed" in path)
    assert not any(path.startswith(failed_folder + "/") and "INSPECTION_ONLY" in path for path in content)


def test_unknown_ground_truth_firewall_rejects_geometric_metrics():
    view = _view(single=True)
    altered = replace(view.candidates[0], geometric_metrics={"tre_mean": 1.0})
    with pytest.raises(ValueError, match="reference metrics"):
        _bundle(view=replace(view, candidates=(altered,)))


def test_ground_truth_firewall_rejects_premature_recommendation():
    with pytest.raises(ValueError, match="recommendation"):
        _bundle(view=replace(_view(), recommendation_status="selected"))


def test_reference_only_notices_are_not_execution_issues():
    view = _view(single=True)
    completed = replace(view.candidates[0], warnings=("Ground truth is unavailable; TRE and geometric PASS are not reported.",))
    view = replace(view, candidates=(completed,))
    assert execution_issues(view) == []
    assert len(reference_limitations(view)) == 1


def test_check_and_failed_candidates_remain_execution_issues():
    view = _view()
    checked = replace(view.candidates[1], execution_status="check", transform_plausible=False)
    rows = execution_issues(replace(view, candidates=(view.candidates[0], checked)))
    assert len(rows) == 1
    assert rows[0]["Method"] == "ORB"


def test_method_diagnostic_highlights_use_recorded_values_only():
    candidate = replace(_candidate("orb"), method_diagnostics={"match_count": 29, "inlier_ratio": 0.8, "confidence_guess": 1.0})
    rows = diagnostic_highlights(candidate)
    assert any(row["Recorded value"] == "29" for row in rows)
    assert any(row["Recorded value"] == "0.8" for row in rows)
    assert all("confidence" not in row["Diagnostic"] for row in rows)


def test_geometric_mask_does_not_invalidate_true_black_pixels():
    request = _request()
    candidate = replace(_candidate("ecc"), estimated_transform=((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)))
    fixed, moving, registered, support = reconstruct_visual_inspection(request, candidate)
    assert support.shape == (16, 20)
    assert support.all()
    assert registered[0, 0] == 0
    overlay = alpha_overlay(fixed, registered, valid_mask=support)
    assert not np.all(overlay[0, 0] == 96)


def test_geometric_mask_excludes_outside_but_not_dark_interior():
    request = _request()
    candidate = _candidate("ecc")
    fixed, moving, registered, support = reconstruct_visual_inspection(request, candidate)
    assert support[0, 0] is np.bool_(False) or not support[0, 0]
    assert support[4, 6]
    overlay = alpha_overlay(fixed, registered, valid_mask=support)
    assert np.all(overlay[0, 0] == 96)
    assert not np.all(overlay[4, 6] == 96)
    assert absolute_difference(fixed, registered, valid_mask=support).shape == fixed.shape
    assert edge_overlay(fixed, registered, valid_mask=support).shape[:2] == fixed.shape


def test_geometric_mask_rejects_incorrect_dimensions():
    array = np.zeros((8, 8), dtype=np.float32)
    with pytest.raises(ValueError, match="mask"):
        alpha_overlay(array, array, valid_mask=np.ones((5, 5), dtype=bool))


def test_export_has_no_streamlit_import():
    source = (UI_ROOT / "automatic" / "automatic_export.py").read_text(encoding="utf-8")
    assert "import streamlit" not in source


def test_page_has_export_action_and_frozen_recommendation_boundary():
    source = (UI_ROOT / "streamlit" / "pages" / "automatic_comparison.py").read_text(encoding="utf-8")
    assert "build_automatic_analysis_export" in source
    assert "ui_auto_prepare_bundle" in source
    assert "ui_auto_download_bundle" in source
    assert "valid_mask=valid_mask" in source
    assert "confidence calibration are not enabled" in source
    assert '"ui_auto_export_payload", None' in source
    assert 'with st.expander("Raw method diagnostics"' not in source
    assert "compatibility_placeholder.container()" in source
