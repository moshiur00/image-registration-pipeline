from __future__ import annotations

from pathlib import Path

from ui.automatic.automatic_presenter import (
    COMMON_EVIDENCE_EXPLANATION,
    candidate_evidence_rows,
    candidate_issue_rows,
    comparison_signature,
    execution_status_label,
    execution_summary,
    recommendation_state_label,
    transform_state_label,
)
from ui.automatic.models import (
    AgreementComparisonView,
    AutomaticComparisonView,
    CandidateComparisonView,
    CompatibilityPreviewView,
    MethodCompatibilityView,
)


UI_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = UI_ROOT / "streamlit" / "pages" / "automatic_comparison.py"
PRESENTER_PATH = UI_ROOT / "automatic" / "automatic_presenter.py"


def _method(method_id: str, display: str) -> MethodCompatibilityView:
    return MethodCompatibilityView(
        method_id=method_id,
        display_name=display,
        method_family="test_family",
        transform_model="affine",
        optional=False,
        compatible=True,
    )


def _preview(*, include_second: bool = True) -> CompatibilityPreviewView:
    compatible = [_method("ecc_affine", "ECC Affine")]
    if include_second:
        compatible.append(_method("orb_affine", "ORB + RANSAC Affine"))
    return CompatibilityPreviewView(
        pair_id="ui-auto-stage63",
        image_shape=(64, 96),
        same_shape=True,
        modality_class="monomodal",
        transform_model="affine",
        ground_truth_status="unavailable",
        compatible=tuple(compatible),
        excluded=(),
    )


def _candidate(
    method_id: str,
    display_name: str,
    *,
    status: str = "completed",
    plausible: bool | None = True,
    failure_reason: str | None = None,
    warnings: tuple[str, ...] = (),
) -> CandidateComparisonView:
    metrics = {
        "mae": 4.123456,
        "mse": 25.987654,
        "ncc": 0.812345,
        "ssim": 0.923456,
        "evaluation_mi": 1.234567,
    }
    if status in {"failed", "validation_error"}:
        metrics = {}
    return CandidateComparisonView(
        candidate_id=f"candidate-{method_id}",
        method_id=method_id,
        display_name=display_name,
        method_family="test_family",
        transform_model="affine",
        execution_status=status,
        transform_plausible=plausible,
        estimated_transform=((1.0, 0.0, 1.0), (0.0, 1.0, 2.0), (0.0, 0.0, 1.0))
        if status in {"completed", "check"}
        else None,
        geometric_metrics={},
        anatomical_metrics={},
        descriptive_metrics=metrics,
        overlap_metrics={"valid_overlap_fraction": 0.875} if metrics else {},
        runtime_metrics={"total_runtime_ms": 18.456} if metrics else {},
        timings_ms={"registration_ms": 17.0} if metrics else {},
        method_diagnostics={"raw_objective": 99.0},
        warnings=warnings,
        failure_reason=failure_reason,
        registered_output_available=status in {"completed", "check"},
    )


def _view() -> AutomaticComparisonView:
    agreement = AgreementComparisonView(
        status="available",
        eligible_candidate_ids=("candidate-ecc_affine", "candidate-orb_affine"),
        excluded_candidates={},
        pairwise=(),
        candidate_summaries=(),
        consensus_anchor_candidate_id=None,
        consensus_anchor_method_id=None,
        consensus_anchor_display_name=None,
        median_pairwise_rms_px=None,
        max_pairwise_rms_px=None,
        median_pairwise_normalized_rms=None,
        interpretation="descriptive only",
    )
    return AutomaticComparisonView(
        preview=_preview(),
        candidates=(
            _candidate("ecc_affine", "ECC Affine"),
            _candidate(
                "orb_affine",
                "ORB + RANSAC Affine",
                status="check",
                plausible=False,
                warnings=("Transform plausibility requires review.",),
            ),
        ),
        status_counts={"completed": 1, "check": 1, "failed": 0, "validation_error": 0},
        agreement=agreement,
        recommendation_status="deferred_until_robustness_calibration",
        ground_truth_status="unavailable",
    )


def test_stage63_signature_changes_when_compatible_set_changes() -> None:
    first = comparison_signature(_preview(include_second=True))
    second = comparison_signature(_preview(include_second=False))
    assert first != second
    assert first == comparison_signature(_preview(include_second=True))


def test_stage63_candidate_rows_contain_common_evidence_only() -> None:
    rows = candidate_evidence_rows(_view())
    assert len(rows) == 2
    assert rows[0]["Method"] == "ECC Affine"
    assert rows[0]["Execution"] == "Completed"
    assert rows[0]["Transform"] == "Plausible"
    assert rows[0]["MAE"] == 4.1235
    assert rows[0]["Runtime (ms)"] == 18.46
    assert "raw_objective" not in rows[0]
    assert "Diagnostics" not in rows[0]


def test_stage63_check_candidate_is_preserved_in_common_table() -> None:
    rows = candidate_evidence_rows(_view())
    assert rows[1]["Execution"] == "CHECK"
    assert rows[1]["Transform"] == "Implausible"


def test_stage63_failed_candidate_stays_visible_with_empty_metrics() -> None:
    view = _view()
    failed = _candidate(
        "mi_affine_2d",
        "Mattes MI Affine 2D",
        status="failed",
        plausible=None,
        failure_reason="optimizer_failed",
    )
    replaced = AutomaticComparisonView(
        preview=view.preview,
        candidates=view.candidates + (failed,),
        status_counts={"completed": 1, "check": 1, "failed": 1, "validation_error": 0},
        agreement=view.agreement,
        recommendation_status=view.recommendation_status,
        ground_truth_status=view.ground_truth_status,
    )
    rows = candidate_evidence_rows(replaced)
    assert rows[-1]["Execution"] == "Failed"
    assert rows[-1]["Transform"] == "Unavailable"
    assert rows[-1]["NCC"] is None
    issues = candidate_issue_rows(replaced)
    assert issues[-1]["Failure reason"] == "optimizer_failed"


def test_stage63_execution_summary_includes_zero_count_states() -> None:
    summary = execution_summary(_view())
    assert summary == {
        "compatible": 2,
        "completed": 1,
        "check": 1,
        "failed": 0,
        "validation_error": 0,
    }


def test_stage63_status_labels_are_research_facing() -> None:
    assert execution_status_label("validation_error") == "Validation error"
    assert transform_state_label(True) == "Plausible"
    assert transform_state_label(False) == "Implausible"
    assert transform_state_label(None) == "Unavailable"
    assert recommendation_state_label("deferred_until_robustness_calibration") == "Not calibrated"


def test_stage63_common_evidence_explanation_does_not_claim_correctness() -> None:
    assert "do not independently establish geometric correctness" in COMMON_EVIDENCE_EXPLANATION


def test_stage63_page_executes_service_only_after_explicit_button() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert '"Run automatic comparison"' in source
    assert "run_clicked = st.button(" in source
    assert "if run_clicked:" in source
    assert "result = service.run(request)" in source


def test_stage63_page_invalidates_stale_result_when_pair_signature_changes() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert 'st.session_state.get("ui_auto_result_signature")' in source
    assert 'ensure_current_comparison_state(st.session_state, signature)' in source
    assert 'clear_automatic_run_state(st.session_state)' in source
    assert 'st.session_state["ui_auto_result_signature"] = signature' in source


def test_stage63_page_does_not_render_agreement_or_best_method_yet() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert "result.agreement" not in source
    assert "consensus_anchor" not in source
    assert "Best method" not in source
    assert "Find best method" not in source
    assert "confidence" in source.lower()  # only the explicit not-enabled research notice


def test_stage63_presenter_has_no_streamlit_dependency() -> None:
    source = PRESENTER_PATH.read_text(encoding="utf-8")
    assert "import streamlit" not in source
    assert "from streamlit" not in source
