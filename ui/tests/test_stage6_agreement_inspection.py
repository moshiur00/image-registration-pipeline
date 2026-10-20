"""Stage 6.4 agreement presentation, candidate diagnostics, and visual QA contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from ui.automatic.automatic_service import _pair_id
from ui.automatic.agreement_presenter import (
    AGREEMENT_EXPLANATION,
    ANCHOR_EXPLANATION,
    agreement_exclusion_rows,
    agreement_overview,
    descriptive_anchor_interpretation,
    candidate_agreement_rows,
    disagreement_matrix_rows,
    pairwise_disagreement_rows,
)
from ui.automatic.candidate_inspection import (
    VISUAL_EXPLANATION,
    can_inspect_image,
    candidate_detail,
    reconstruct_visual_preview,
)
from ui.automatic.models import (
    AgreementComparisonView,
    AutomaticComparisonRequest,
    AutomaticComparisonView,
    CandidateAgreementView,
    CandidateComparisonView,
    CompatibilityPreviewView,
    MethodCompatibilityView,
    PairwiseAgreementView,
)
from ui.core.contracts import ImageSource, PreprocessingSpec
from ui.core.enums import SourceType, TransformModel


PAGE = Path(__file__).resolve().parents[1] / "streamlit" / "pages" / "automatic_comparison.py"


def _candidate(name: str, *, status: str = "completed", plausible: bool | None = True):
    transform = ((1.0, 0.0, 2.0), (0.0, 1.0, 3.0), (0.0, 0.0, 1.0))
    return CandidateComparisonView(
        candidate_id=f"candidate-{name}", method_id=name, display_name=name.upper(),
        method_family="intensity_based", transform_model="translation",
        execution_status=status, transform_plausible=plausible,
        estimated_transform=transform if status in {"completed", "check"} else None,
        geometric_metrics={}, anatomical_metrics={}, descriptive_metrics={"ncc": 0.7},
        overlap_metrics={}, runtime_metrics={"total_runtime_ms": 12.0},
        timings_ms={"total": 12.0}, method_diagnostics={"ecc_objective": 0.91},
        warnings=(), failure_reason=None if status == "completed" else "check required",
        registered_output_available=status in {"completed", "check"},
    )


def _view(*, single: bool = False, excluded: bool = False) -> AutomaticComparisonView:
    a = _candidate("ecc")
    b = _candidate("orb", status="check", plausible=False) if excluded else _candidate("orb")
    candidates = (a,) if single else (a, b)
    eligible = (a.candidate_id,) if single or excluded else (a.candidate_id, b.candidate_id)
    pairs = () if len(eligible) < 2 else (
        PairwiseAgreementView(
            candidate_a=a.candidate_id, candidate_b=b.candidate_id,
            method_a="ecc", method_b="orb", display_name_a=a.display_name,
            display_name_b=b.display_name, rms_px=2.5, median_px=2.0,
            p95_px=4.1, max_px=4.5, normalized_rms=0.018,
        ),
    )
    summaries = () if len(eligible) < 2 else (
        CandidateAgreementView(a.candidate_id, "ecc", "ECC", 1, 2.5, 2.5, 0.018),
        CandidateAgreementView(b.candidate_id, "orb", "ORB", 1, 2.5, 2.5, 0.018),
    )
    agreement = AgreementComparisonView(
        status="available" if pairs else "insufficient_candidates",
        eligible_candidate_ids=eligible,
        excluded_candidates={b.candidate_id: ("implausible_transform",)} if excluded else {},
        pairwise=pairs, candidate_summaries=summaries,
        consensus_anchor_candidate_id=a.candidate_id if pairs else None,
        consensus_anchor_method_id="ecc" if pairs else None,
        consensus_anchor_display_name="ECC" if pairs else None,
        median_pairwise_rms_px=2.5 if pairs else None,
        max_pairwise_rms_px=2.5 if pairs else None,
        median_pairwise_normalized_rms=0.018 if pairs else None,
        interpretation="descriptive medoid, not a recommendation",
    )
    compatible = tuple(MethodCompatibilityView(
        method_id=c.method_id, display_name=c.display_name,
        method_family=c.method_family, transform_model="translation",
        optional=False, compatible=True,
    ) for c in candidates)
    return AutomaticComparisonView(
        preview=CompatibilityPreviewView(
            pair_id=_pair_id(_request()), image_shape=(16, 20), same_shape=True,
            modality_class="monomodal", transform_model="translation",
            ground_truth_status="unavailable", compatible=compatible, excluded=(),
        ), candidates=candidates,
        status_counts={"completed": len(candidates), "check": 0, "failed": 0, "validation_error": 0},
        agreement=agreement, recommendation_status="deferred_until_robustness_calibration",
    )


def _request() -> AutomaticComparisonRequest:
    arr = np.zeros((16, 20), dtype=np.float32)
    arr[4:10, 5:12] = 100.0
    return AutomaticComparisonRequest(
        fixed=ImageSource(source_type=SourceType.ARRAY, display_name="fixed", array=arr),
        moving=ImageSource(source_type=SourceType.ARRAY, display_name="moving", array=arr.copy()),
        transform_model=TransformModel.TRANSLATION, modality_class="monomodal",
        preprocessing=PreprocessingSpec(),
    )


def test_agreement_summary_has_no_selection_or_confidence() -> None:
    summary = agreement_overview(_view())
    assert summary["status"] == "available"
    assert summary["eligible"] == 2
    assert summary["pairwise_comparisons"] == 1
    assert summary["anchor"] is None
    assert summary["anchor_state"] == "two_candidate_tie"
    assert "score" not in summary and "confidence" not in summary


def test_two_candidates_make_symmetric_matrix_with_zero_diagonal() -> None:
    rows = disagreement_matrix_rows(_view())
    assert len(rows) == 2
    assert rows[0] == {"Candidate": "ECC", "ECC": 0.0, "ORB": 2.5}
    assert rows[1] == {"Candidate": "ORB", "ECC": 2.5, "ORB": 0.0}


def test_single_eligible_candidate_has_no_agreement_or_anchor() -> None:
    view = _view(single=True)
    assert disagreement_matrix_rows(view) == []
    assert pairwise_disagreement_rows(view) == []
    assert agreement_overview(view)["anchor"] is None


def test_implausible_candidate_is_excluded_and_explanation_preserved() -> None:
    view = _view(excluded=True)
    assert disagreement_matrix_rows(view) == []
    assert agreement_exclusion_rows(view) == [
        {"Method": "ORB", "Reason": "implausible_transform"}
    ]


def test_pairwise_stats_preserve_backend_values_and_units() -> None:
    rows = pairwise_disagreement_rows(_view())
    assert rows[0]["RMS (px)"] == 2.5
    assert rows[0]["p95 (px)"] == 4.1
    assert rows[0]["Normalized RMS"] == 0.018


def test_candidate_centrality_not_reordered_to_imply_winner() -> None:
    rows = candidate_agreement_rows(_view())
    assert [row["Method"] for row in rows] == ["ECC", "ORB"]
    assert all("Rank" not in row for row in rows)


def test_missing_pairwise_record_is_blank_not_zero() -> None:
    view = _view()
    changed = replace(view, agreement=replace(view.agreement, pairwise=()))
    rows = disagreement_matrix_rows(changed)
    assert rows[0]["ORB"] is None
    assert rows[1]["ECC"] is None


def test_duplicate_display_names_are_disambiguated() -> None:
    view = _view()
    duplicated = replace(view.candidates[1], display_name="ECC")
    rows = disagreement_matrix_rows(replace(view, candidates=(view.candidates[0], duplicated)))
    assert len(rows[0]) == 3
    assert rows[0]["Candidate"] == "ECC (ecc)"
    assert rows[1]["Candidate"] == "ECC (orb)"


def test_candidate_detail_preserves_raw_method_diagnostics_separately() -> None:
    detail = candidate_detail(_candidate("ecc"))
    assert detail["diagnostics"]["ecc_objective"] == 0.91
    assert detail["transform_direction"] == "Moving -> Fixed"
    assert detail["geometric_ground_truth"] == "unavailable"
    assert "best_method" not in detail


def test_inspection_refuses_reference_metrics_for_unknown_upload() -> None:
    candidate = replace(_candidate("ecc"), geometric_metrics={"tre_mean": 0.0})
    with pytest.raises(ValueError, match="reference metrics"):
        candidate_detail(candidate)


def test_failed_candidate_preserves_reason_and_has_no_image() -> None:
    candidate = _candidate("mi", status="failed", plausible=None)
    assert candidate_detail(candidate)["failure_reason"] == "check required"
    assert can_inspect_image(candidate) is False
    with pytest.raises(ValueError, match="registered output"):
        reconstruct_visual_preview(_request(), candidate)


def test_check_candidate_can_be_visually_inspected_with_warning_state() -> None:
    candidate = _candidate("ecc", status="check", plausible=False)
    assert can_inspect_image(candidate)
    assert candidate_detail(candidate)["plausibility"] == "Implausible"


def test_reconstructed_image_uses_validated_forward_warp() -> None:
    request = _request()
    candidate = replace(_candidate("ecc"), estimated_transform=(
        (1.0, 0.0, 2.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
    ))
    fixed, moving, registered = reconstruct_visual_preview(request, candidate)
    assert fixed.shape == moving.shape == registered.shape == (16, 20)
    assert np.array_equal(registered[4:10, 7:14], moving[4:10, 5:12])
    assert not np.any(registered[4:10, 5:7])


def test_visual_reconstruction_uses_explicit_preprocessing() -> None:
    request = replace(_request(), preprocessing=PreprocessingSpec(normalization="robust"))
    candidate = replace(_candidate("ecc"), estimated_transform=(
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
    ))
    fixed, moving, registered = reconstruct_visual_preview(request, candidate)
    assert fixed.max() <= 1.0 and moving.max() <= 1.0
    assert np.array_equal(registered, moving)


def test_invalid_transform_is_rejected_for_visual_reconstruction() -> None:
    candidate = replace(_candidate("ecc"), estimated_transform=((1.0, 0.0), (0.0, 1.0)))
    with pytest.raises(ValueError, match="finite 3x3"):
        reconstruct_visual_preview(_request(), candidate)


def test_page_reuses_agreement_service_results_and_existing_visual_components() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert "_render_transform_agreement(result)" in source
    assert "_render_candidate_inspection(result, request)" in source
    assert "render_visual_diagnostics(fixed=fixed, registered=reconstructed, valid_mask=valid_mask)" in source
    assert "service.run(request)" in source
    assert "_render_execution_result(result, request)" in source
    assert "best method" not in source.lower()


def test_ui_stage64_scientific_language_is_explicit() -> None:
    assert "not" in ANCHOR_EXPLANATION.lower()
    assert "descriptive" in AGREEMENT_EXPLANATION.lower()
    assert "not a new registration" in VISUAL_EXPLANATION
