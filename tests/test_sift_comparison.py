from __future__ import annotations

import pytest

from image_registration.feature_comparison import (
    build_paired_case_summary,
    summarize_frontend,
    summarize_paired_outcomes,
)


def _record(
    case_id: str,
    frontend: str,
    *,
    within: bool,
    tre: float | None,
    runtime: float,
    matches: int = 20,
    inliers: int = 18,
    inlier_ratio: float | None = 0.9,
) -> dict:
    return {
        "case_id": case_id,
        "frontend": frontend,
        "model": "similarity",
        "scope": "normal",
        "fixed_features": {"keypoint_count": 100},
        "moving_features": {"keypoint_count": 90},
        "matching": {"success": matches >= 8, "filtered_match_count": matches},
        "ransac": {
            "success": within,
            "inlier_count": inliers,
            "inlier_ratio": inlier_ratio,
            "failure_reason": None if within else "test_failure",
        },
        "evaluation": {"tre_pixels": tre, "within_tolerance": within},
        "total_runtime_ms": runtime,
    }


def test_frontend_summary_keeps_failed_cases_in_denominator() -> None:
    records = [
        _record("a", "orb", within=True, tre=0.2, runtime=10.0),
        _record("b", "orb", within=False, tre=None, runtime=12.0, matches=0, inliers=0, inlier_ratio=None),
    ]
    summary = summarize_frontend(records, "orb")
    assert summary["case_count"] == 2
    assert summary["matching_success_count"] == 1
    assert summary["within_tolerance_count"] == 1
    assert summary["median_tre_pixels"] == pytest.approx(0.2)


def test_paired_summary_classifies_method_specific_recovery() -> None:
    records = [
        _record("case", "orb", within=False, tre=8.0, runtime=10.0),
        _record("case", "sift", within=True, tre=0.4, runtime=40.0),
    ]
    paired = build_paired_case_summary(records)
    assert paired[0]["outcome"] == "sift_only_within_tolerance"
    assert paired[0]["sift_minus_orb_tre_pixels"] == pytest.approx(-7.6)
    assert paired[0]["sift_to_orb_runtime_ratio"] == pytest.approx(4.0)


def test_paired_outcome_counts_are_explicit() -> None:
    records = [
        _record("a", "orb", within=True, tre=0.2, runtime=10.0),
        _record("a", "sift", within=True, tre=0.1, runtime=20.0),
        _record("b", "orb", within=True, tre=0.3, runtime=10.0),
        _record("b", "sift", within=False, tre=None, runtime=20.0),
    ]
    counts = summarize_paired_outcomes(build_paired_case_summary(records))
    assert counts["both_within_tolerance"] == 1
    assert counts["orb_only_within_tolerance"] == 1
    assert counts["sift_only_within_tolerance"] == 0
    assert counts["neither_within_tolerance"] == 0


def test_paired_summary_requires_both_frontends() -> None:
    with pytest.raises(ValueError, match="exactly one ORB and one SIFT"):
        build_paired_case_summary([
            _record("a", "orb", within=True, tre=0.2, runtime=10.0)
        ])
