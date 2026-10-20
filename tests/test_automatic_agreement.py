from __future__ import annotations

import numpy as np
import pytest

from image_registration.automatic_agreement import (
    build_preliminary_consensus,
    control_grid_2d,
    robust_numeric_summary,
    summarize_methods,
    summarize_stage_runtimes,
    transform_disagreement_2d,
)
from image_registration.automatic_registration import (
    AutoPairProfile,
    AutomaticRunResult,
    NormalizedCandidateEvidence,
)
from image_registration.evaluation_contracts import ExecutionStatus, ReferenceEvidence


def _candidate(
    method_id: str,
    *,
    tx: float = 0.0,
    ty: float = 0.0,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    plausible: bool | None = True,
    modality_metrics: dict[str, float] | None = None,
    timings: dict[str, float] | None = None,
) -> NormalizedCandidateEvidence:
    transform = None
    if status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}:
        transform = np.array(
            [[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
    return NormalizedCandidateEvidence(
        candidate_id=f"candidate-{method_id}",
        pair_id="pair-1",
        method_id=method_id,
        display_name=method_id,
        method_family="test_family",
        transform_model="affine",
        execution_status=status,
        transform_plausible=plausible,
        geometric_within_tolerance=None,
        estimated_transform=transform,
        geometric_metrics={},
        anatomical_metrics={},
        descriptive_metrics=modality_metrics or {"ncc": 0.9},
        overlap_metrics={"valid_overlap_fraction": 0.8},
        runtime_metrics={"total_runtime_ms": 10.0},
        timings_ms=timings or {"total": 10.0},
        method_diagnostics={"raw_objective": 123.0},
        warnings=(),
        failure_reason=None if status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK} else "failed",
    )


def _run(*candidates: NormalizedCandidateEvidence, modality: str = "monomodal") -> AutomaticRunResult:
    pair = AutoPairProfile(
        pair_id="pair-1",
        dimensions=2,
        modality_class=modality,
        candidate_transform_models=("affine",),
        same_shape=True,
        reference=ReferenceEvidence(),
    )
    return AutomaticRunResult(
        pair=pair,
        candidates=tuple(candidates),
        compatibility=(),
    )


def test_control_grid_uses_xy_coordinates_and_expected_count() -> None:
    points = control_grid_2d((100, 200), rows=3, cols=4, margin_fraction=0.1)
    assert points.shape == (12, 2)
    assert points[0] == pytest.approx([19.9, 9.9])
    assert points[-1] == pytest.approx([179.1, 89.1])


def test_identity_transform_disagreement_is_zero() -> None:
    a = _candidate("a")
    b = _candidate("b")
    points = control_grid_2d((64, 64), rows=3, cols=3, margin_fraction=0.0)
    result = transform_disagreement_2d(
        a,
        b,
        control_points_xy=points,
        image_shape=(64, 64),
    )
    assert result.rms_px == pytest.approx(0.0)
    assert result.max_px == pytest.approx(0.0)


def test_known_translation_difference_has_exact_rms() -> None:
    a = _candidate("a", tx=0.0, ty=0.0)
    b = _candidate("b", tx=3.0, ty=4.0)
    points = control_grid_2d((64, 64), rows=3, cols=3, margin_fraction=0.0)
    result = transform_disagreement_2d(
        a,
        b,
        control_points_xy=points,
        image_shape=(64, 64),
    )
    assert result.rms_px == pytest.approx(5.0)
    assert result.median_px == pytest.approx(5.0)
    assert result.p95_px == pytest.approx(5.0)


def test_disagreement_is_normalized_by_image_diagonal() -> None:
    a = _candidate("a")
    b = _candidate("b", tx=3.0, ty=4.0)
    points = control_grid_2d((3, 4), rows=2, cols=2, margin_fraction=0.0)
    result = transform_disagreement_2d(
        a,
        b,
        control_points_xy=points,
        image_shape=(3, 4),
    )
    assert result.normalized_rms == pytest.approx(5.0 / np.hypot(3.0, 2.0))


def test_consensus_requires_at_least_two_eligible_candidates() -> None:
    run = _run(_candidate("only"))
    result = build_preliminary_consensus(run, image_shape=(64, 64))
    assert result.status == "insufficient_candidates"
    assert result.consensus_anchor_candidate_id is None
    assert result.to_dict()["final_recommendation"] is None


def test_consensus_excludes_failed_and_implausible_candidates() -> None:
    run = _run(
        _candidate("a"),
        _candidate("b", tx=1.0),
        _candidate("failed", status=ExecutionStatus.FAILED),
        _candidate("implausible", tx=2.0, plausible=False),
    )
    result = build_preliminary_consensus(run, image_shape=(64, 64))
    assert result.status == "available"
    assert len(result.eligible_candidate_ids) == 2
    excluded = result.excluded_candidates
    assert "terminal_status_failed" in excluded["candidate-failed"]
    assert "implausible_transform" in excluded["candidate-implausible"]


def test_consensus_anchor_is_transform_medoid_not_best_method() -> None:
    run = _run(
        _candidate("left", tx=0.0),
        _candidate("middle", tx=1.0),
        _candidate("right", tx=4.0),
    )
    result = build_preliminary_consensus(run, image_shape=(80, 80))
    assert result.consensus_anchor_method_id == "middle"
    payload = result.to_dict()
    assert payload["final_recommendation"] is None
    assert "not a best-method recommendation" in payload["consensus_anchor"]["interpretation"]


def test_pairwise_count_is_n_choose_two() -> None:
    run = _run(
        _candidate("a"),
        _candidate("b", tx=1.0),
        _candidate("c", tx=2.0),
        _candidate("d", tx=3.0),
    )
    result = build_preliminary_consensus(run, image_shape=(80, 80))
    assert len(result.pairwise) == 6


def test_robust_summary_uses_median_mad_and_p95() -> None:
    summary = robust_numeric_summary([1.0, 2.0, 3.0, 100.0])
    assert summary is not None
    assert summary["count"] == 4
    assert summary["median"] == pytest.approx(2.5)
    assert summary["mad"] == pytest.approx(1.0)
    assert summary["p95"] > 3.0


def test_robust_summary_returns_none_for_no_finite_values() -> None:
    assert robust_numeric_summary([np.nan, np.inf]) is None


def test_method_summary_preserves_terminal_status_rates() -> None:
    run = _run(
        _candidate("a"),
        _candidate("a", status=ExecutionStatus.CHECK),
        _candidate("a", status=ExecutionStatus.FAILED),
    )
    # Candidate IDs need not be unique for aggregation tests.
    rows = summarize_methods([run])
    assert len(rows) == 1
    row = rows[0]
    assert row["attempts"] == 3
    assert row["status_counts"]["completed"] == 1
    assert row["status_counts"]["check"] == 1
    assert row["status_counts"]["failed"] == 1
    assert row["terminal_success_rate"] == pytest.approx(2 / 3)


def test_method_summary_keeps_modality_classes_separate() -> None:
    run_a = _run(_candidate("mi"), modality="monomodal")
    run_b = _run(_candidate("mi"), modality="simulated_multimodal")
    rows = summarize_methods([run_a, run_b])
    assert len(rows) == 2
    assert {row["modality_class"] for row in rows} == {
        "monomodal",
        "simulated_multimodal",
    }


def test_method_summary_aggregates_only_common_evidence_not_diagnostics() -> None:
    run = _run(
        _candidate("a", modality_metrics={"ncc": 0.8}),
        _candidate("a", modality_metrics={"ncc": 1.0}),
    )
    row = summarize_methods([run])[0]
    assert row["common_metric_summaries"]["ncc"]["median"] == pytest.approx(0.9)
    assert "raw_objective" not in row["common_metric_summaries"]
    assert row["raw_optimizer_objectives_aggregated"] is False


def test_stage_runtime_summary_is_robust_across_candidates() -> None:
    run = _run(
        _candidate("a", timings={"registration": 10.0, "total": 12.0}),
        _candidate("b", timings={"registration": 20.0, "total": 25.0}),
        _candidate("c", timings={"registration": 30.0, "total": 35.0}),
    )
    summary = summarize_stage_runtimes([run])
    assert summary["registration"]["median"] == pytest.approx(20.0)
    assert summary["total"]["median"] == pytest.approx(25.0)
