"""Paired summaries for the optional ORB versus SIFT comparison."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np


def summarize_frontend(records: list[dict[str, Any]], frontend: str) -> dict[str, Any]:
    """Summarize one feature front-end without hiding failed cases."""
    selected = [item for item in records if item["frontend"] == frontend]
    numeric_tre = [
        float(item["evaluation"]["tre_pixels"])
        for item in selected
        if item["evaluation"]["tre_pixels"] is not None
    ]
    inlier_ratios = [
        float(item["ransac"]["inlier_ratio"])
        for item in selected
        if item["ransac"]["inlier_ratio"] is not None
    ]
    runtimes = [float(item["total_runtime_ms"]) for item in selected]
    fixed_keypoints = [int(item["fixed_features"]["keypoint_count"]) for item in selected]
    moving_keypoints = [int(item["moving_features"]["keypoint_count"]) for item in selected]
    matches = [int(item["matching"]["filtered_match_count"]) for item in selected]

    return {
        "case_count": len(selected),
        "matching_success_count": sum(bool(item["matching"]["success"]) for item in selected),
        "ransac_success_count": sum(bool(item["ransac"]["success"]) for item in selected),
        "within_tolerance_count": sum(
            bool(item["evaluation"]["within_tolerance"]) for item in selected
        ),
        "median_tre_pixels": None if not numeric_tre else float(np.median(numeric_tre)),
        "maximum_tre_pixels": None if not numeric_tre else float(np.max(numeric_tre)),
        "mean_inlier_ratio": None if not inlier_ratios else float(np.mean(inlier_ratios)),
        "mean_total_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
        "mean_fixed_keypoints": None if not fixed_keypoints else float(np.mean(fixed_keypoints)),
        "mean_moving_keypoints": None if not moving_keypoints else float(np.mean(moving_keypoints)),
        "mean_filtered_matches": None if not matches else float(np.mean(matches)),
    }


def build_paired_case_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build case-level ORB and SIFT outcomes from a common experiment table."""
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in records:
        case_id = str(item["case_id"])
        frontend = str(item["frontend"])
        if frontend in grouped[case_id]:
            raise ValueError(f"Duplicate {frontend} record for case {case_id}.")
        grouped[case_id][frontend] = item

    paired: list[dict[str, Any]] = []
    for case_id in sorted(grouped):
        entries = grouped[case_id]
        if set(entries) != {"orb", "sift"}:
            raise ValueError(f"Case {case_id} must contain exactly one ORB and one SIFT record.")
        orb = entries["orb"]
        sift = entries["sift"]
        orb_within = bool(orb["evaluation"]["within_tolerance"])
        sift_within = bool(sift["evaluation"]["within_tolerance"])
        if orb_within and sift_within:
            outcome = "both_within_tolerance"
        elif orb_within:
            outcome = "orb_only_within_tolerance"
        elif sift_within:
            outcome = "sift_only_within_tolerance"
        else:
            outcome = "neither_within_tolerance"

        orb_tre = orb["evaluation"]["tre_pixels"]
        sift_tre = sift["evaluation"]["tre_pixels"]
        tre_delta = None
        if orb_tre is not None and sift_tre is not None:
            tre_delta = float(sift_tre) - float(orb_tre)

        paired.append(
            {
                "case_id": case_id,
                "model": orb["model"],
                "scope": orb["scope"],
                "outcome": outcome,
                "orb": {
                    "filtered_matches": orb["matching"]["filtered_match_count"],
                    "inlier_count": orb["ransac"]["inlier_count"],
                    "inlier_ratio": orb["ransac"]["inlier_ratio"],
                    "tre_pixels": orb_tre,
                    "within_tolerance": orb_within,
                    "total_runtime_ms": orb["total_runtime_ms"],
                    "failure_reason": orb["ransac"]["failure_reason"],
                },
                "sift": {
                    "filtered_matches": sift["matching"]["filtered_match_count"],
                    "inlier_count": sift["ransac"]["inlier_count"],
                    "inlier_ratio": sift["ransac"]["inlier_ratio"],
                    "tre_pixels": sift_tre,
                    "within_tolerance": sift_within,
                    "total_runtime_ms": sift["total_runtime_ms"],
                    "failure_reason": sift["ransac"]["failure_reason"],
                },
                "sift_minus_orb_tre_pixels": tre_delta,
                "sift_to_orb_runtime_ratio": (
                    None
                    if float(orb["total_runtime_ms"]) <= 0.0
                    else float(sift["total_runtime_ms"]) / float(orb["total_runtime_ms"])
                ),
            }
        )
    return paired


def summarize_paired_outcomes(paired: list[dict[str, Any]]) -> dict[str, int]:
    """Count paired geometric outcomes without converting them to a final method decision."""
    keys = (
        "both_within_tolerance",
        "orb_only_within_tolerance",
        "sift_only_within_tolerance",
        "neither_within_tolerance",
    )
    return {
        key: sum(item["outcome"] == key for item in paired)
        for key in keys
    }
