"""Final UI v0.2 edge-case acceptance: medoid ties, invalidation, and exports."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from io import BytesIO
import json
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import numpy as np
import pytest

from ui.automatic.agreement_presenter import agreement_overview, descriptive_anchor_interpretation
from ui.automatic.automatic_export import build_automatic_analysis_export
from ui.automatic.automatic_presenter import comparison_signature
from ui.automatic.automatic_service import AutomaticComparisonService, _pair_id
from ui.automatic.models import CandidateAgreementView, CompatibilityPreviewView
from ui.core.contracts import ImageSource, PreprocessingSpec
from ui.core.enums import SourceType, TransformModel
from ui.streamlit.pages.automatic_comparison import (
    clear_automatic_run_state,
    ensure_current_comparison_state,
    render_automatic_comparison,
)
from ui.tests.test_stage6_agreement_inspection import _candidate, _request, _view


def export(view=None, request=None):
    return build_automatic_analysis_export(request=request or _request(), view=view or _view())


def archive_data(view=None, request=None):
    with ZipFile(BytesIO(export(view, request).data)) as archive:
        return {path: archive.read(path) for path in archive.namelist()}


def test_two_candidate_tie_is_not_reported_as_unique():
    view = _view()
    interpretation = descriptive_anchor_interpretation(view)
    assert interpretation["status"] == "two_candidate_tie"
    assert interpretation["unique_anchor"] is None
    assert "No unique" in interpretation["explanation"]
    assert interpretation["backend_medoid_candidate_id"] == view.agreement.consensus_anchor_candidate_id
    assert agreement_overview(view)["anchor"] is None


def test_three_candidate_unique_descriptive_anchor_without_ranking():
    base = _view()
    third = _candidate("mi")
    third_summary = CandidateAgreementView(third.candidate_id, "mi", "MI", 2, 9.0, 12.0, 0.06)
    a, b = base.agreement.candidate_summaries
    a = replace(a, comparisons=2, median_pairwise_rms_px=1.0)
    b = replace(b, comparisons=2, median_pairwise_rms_px=4.0)
    agreement = replace(base.agreement,
        eligible_candidate_ids=(base.candidates[0].candidate_id, base.candidates[1].candidate_id, third.candidate_id),
        candidate_summaries=(a, b, third_summary),
    )
    view = replace(base, candidates=base.candidates + (third,), agreement=agreement)
    interpretation = descriptive_anchor_interpretation(view)
    assert interpretation["status"] == "unique_descriptive_anchor"
    assert interpretation["unique_anchor"] == "ECC"
    assert "not a method recommendation" in interpretation["explanation"]


def test_three_candidate_equal_median_tie_displays_no_unique_anchor():
    base = _view()
    third = _candidate("mi")
    a, b = base.agreement.candidate_summaries
    b = replace(b, comparisons=2, median_pairwise_rms_px=a.median_pairwise_rms_px)
    third_summary = CandidateAgreementView(third.candidate_id, "mi", "MI", 2, 5.0, 8.0, 0.06)
    agreement = replace(base.agreement,
        eligible_candidate_ids=(base.candidates[0].candidate_id, base.candidates[1].candidate_id, third.candidate_id),
        candidate_summaries=(replace(a, comparisons=2), b, third_summary),
    )
    view = replace(base, candidates=base.candidates + (third,), agreement=agreement)
    assert descriptive_anchor_interpretation(view)["status"] == "centrality_tie"
    assert agreement_overview(view)["anchor"] is None


def test_single_candidate_has_explicitly_insufficient_evidence():
    interpretation = descriptive_anchor_interpretation(_view(single=True))
    assert interpretation["status"] == "insufficient_candidates"
    assert interpretation["backend_medoid_candidate_id"] is None
    assert interpretation["unique_anchor"] is None
    assert agreement_overview(_view(single=True))["anchor"] is None


def test_export_preserves_backend_medoid_and_marks_no_unique_anchor():
    data = archive_data()
    analysis = json.loads(data["analysis.json"])
    manifest = json.loads(data["manifest.json"])
    assert analysis["agreement"]["consensus_anchor"]["candidate_id"] is not None
    assert analysis["agreement_presentation"]["status"] == "two_candidate_tie"
    assert analysis["agreement_presentation"]["unique_anchor"] is None
    assert manifest["consensus_presentation"] == analysis["agreement_presentation"]
    assert b"deterministic backend medoid" in data["README.txt"]


def test_export_single_candidate_preserves_agreement_limit():
    data = archive_data(view=_view(single=True))
    interpretation = json.loads(data["analysis.json"])["agreement_presentation"]
    assert interpretation["status"] == "insufficient_candidates"
    assert interpretation["unique_anchor"] is None


def test_export_does_not_accept_stale_input_or_preprocessing():
    view = _view()
    request = _request()
    changed = replace(request, preprocessing=PreprocessingSpec(gaussian_sigma=0.5))
    with pytest.raises(ValueError, match="pair identity"):
        export(view, changed)
    modified_arr = np.array(request.fixed.array, copy=True)
    modified_arr[5, 5] = 900
    changed = replace(request, fixed=replace(request.fixed, array=modified_arr))
    with pytest.raises(ValueError, match="pair identity"):
        export(view, changed)
    with pytest.raises(ValueError, match="pair identity"):
        export(view, replace(request, modality_class="multimodal"))
    with pytest.raises(ValueError, match="pair identity"):
        export(view, replace(request, transform_model=TransformModel.AFFINE))


def test_export_optional_method_policy_guard():
    view = _view()
    changed = replace(view.preview.compatible[0], optional=True)
    view = replace(view, preview=replace(view.preview, compatible=(changed,) + view.preview.compatible[1:]))
    with pytest.raises(ValueError, match="optional-method policy"):
        export(view, replace(_request(), include_optional_methods=False))
    # Only one policy may be active for one completed run.
    excluded = replace(changed, compatible=False, reasons=("optional_method_disabled",))
    view = replace(view, preview=replace(view.preview, compatible=view.preview.compatible[1:], excluded=(excluded,)))
    with pytest.raises(ValueError, match="optional-method policy"):
        export(view, _request())


def test_result_signature_changes_for_every_relevant_pair_setting():
    req = _request()
    base = _pair_id(req)
    assert _pair_id(replace(req, preprocessing=PreprocessingSpec(normalization="robust"))) != base
    assert _pair_id(replace(req, modality_class="multimodal")) != base
    assert _pair_id(replace(req, transform_model=TransformModel.RIGID)) != base
    new_array = np.array(req.moving.array, copy=True)
    new_array[0, 0] = 13.5
    assert _pair_id(replace(req, moving=replace(req.moving, array=new_array))) != base
    preview = _view().preview
    assert comparison_signature(replace(preview, pair_id="different")) != comparison_signature(preview)
    optional = replace(preview.compatible[0], compatible=False, reasons=("optional_method_disabled",))
    changed_preview = replace(preview, compatible=preview.compatible[1:], excluded=preview.excluded + (optional,))
    assert comparison_signature(changed_preview) != comparison_signature(preview)
    assert comparison_signature(preview, include_optional_methods=True) != comparison_signature(
        preview, include_optional_methods=False
    )


def test_stale_result_and_prepared_export_are_cleared_together():
    state = {
        "ui_auto_result_signature": "previous", "ui_auto_result": object(),
        "ui_auto_export_payload": b"old", "ui_auto_visual_candidate": "old",
        "ui_auto_fixed_upload": "retain user input", "ui_auto_transform_model": "Affine",
    }
    assert not ensure_current_comparison_state(state, "new")
    assert not any(k in state for k in (
        "ui_auto_result_signature", "ui_auto_result", "ui_auto_export_payload", "ui_auto_visual_candidate"))
    assert state["ui_auto_fixed_upload"] == "retain user input"
    state.update(ui_auto_result_signature="same", ui_auto_result="current", ui_auto_export_payload=b"current")
    assert ensure_current_comparison_state(state, "same")
    assert state["ui_auto_export_payload"] == b"current"


class FakePageUI:
    """Small fake for early upload/validation branches; no real Streamlit needed."""
    def __init__(self, *, fixed=None, moving=None):
        self.session_state = {
            "ui_auto_result_signature": "stale", "ui_auto_result": object(),
            "ui_auto_export_payload": b"stale", "ui_auto_visual_candidate": "stale",
        }
        self.fixed = fixed
        self.moving = moving
        self.messages = []

    def markdown(self, *a, **kw): return None
    def caption(self, *a, **kw): return None
    def info(self, *a, **kw): self.messages.append(("info", str(a[0])))
    def error(self, *a, **kw): self.messages.append(("error", str(a[0])))
    def columns(self, *a, **kw): return [self, self]
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def image(self, *a, **kw): return None
    def file_uploader(self, label, **kw): return self.fixed if label == "Fixed image" else self.moving
    def selectbox(self, label, options, **kw): return options[kw.get("index", 0)]
    def checkbox(self, *a, **kw): return kw.get("value", False)
    def expander(self, *a, **kw): return nullcontext()


@pytest.mark.parametrize("which", ["none", "only_fixed", "only_moving", "corrupt_pair"])
def test_page_clears_stale_state_when_upload_absent_or_invalid(monkeypatch, which):
    upload = SimpleNamespace(name="bad.png", getvalue=lambda: b"not a valid image")
    ui = FakePageUI(
        fixed=upload if which in {"only_fixed", "corrupt_pair"} else None,
        moving=upload if which in {"only_moving", "corrupt_pair"} else None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", ui)
    monkeypatch.setattr("ui.streamlit.pages.automatic_comparison._render_preprocessing_controls", lambda: PreprocessingSpec())
    render_automatic_comparison(SimpleNamespace(preview=lambda request: None))
    assert "ui_auto_export_payload" not in ui.session_state
    assert "ui_auto_result" not in ui.session_state
    assert "ui_auto_result_signature" not in ui.session_state
    assert "ui_auto_visual_candidate" not in ui.session_state
    assert ui.messages


def test_page_clears_stale_state_on_preview_error(monkeypatch):
    upload = SimpleNamespace(name="valid.png", getvalue=lambda: b"valid")
    ui = FakePageUI(fixed=upload, moving=upload)
    monkeypatch.setitem(sys.modules, "streamlit", ui)
    monkeypatch.setattr("ui.streamlit.pages.automatic_comparison._render_preprocessing_controls", lambda: PreprocessingSpec())
    req = _request()
    pair = SimpleNamespace(fixed_source=req.fixed, moving_source=req.moving,
                           fixed_preview=np.asarray(req.fixed.array), moving_preview=np.asarray(req.moving.array))
    monkeypatch.setattr("ui.streamlit.pages.automatic_comparison.build_uploaded_pair", lambda **kw: pair)
    monkeypatch.setattr("ui.streamlit.pages.automatic_comparison.to_display_uint8", lambda x: x)
    ui.image = lambda *a, **kw: None
    ui.divider = lambda *a, **kw: None
    def broken(request):
        raise ValueError("invalid request")
    render_automatic_comparison(SimpleNamespace(preview=broken))
    assert ui.messages[-1] == ("error", "invalid request")
    assert "ui_auto_result" not in ui.session_state
    assert "ui_auto_export_payload" not in ui.session_state
