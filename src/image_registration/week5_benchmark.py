"""Utilities for the frozen Week 5 integrated multimodal benchmark."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import numpy as np


def _finite_values(records: Iterable[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        number = float(value)
        if np.isfinite(number):
            values.append(number)
    return values


def summarize_benchmark_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize attempts without removing failed or CHECK registrations."""
    tre = _finite_values(records, "tre_pixels")
    runtime = _finite_values(records, "runtime_ms")
    parameter_error = _finite_values(records, "parameter_error")
    summary: dict[str, Any] = {
        "registration_count": len(records),
        "method_success_count": sum(bool(item.get("method_success")) for item in records),
        "within_tolerance_count": sum(bool(item.get("within_tolerance")) for item in records),
        "within_tolerance_rate": (
            None
            if not records
            else sum(bool(item.get("within_tolerance")) for item in records) / len(records)
        ),
        "median_tre_pixels": None if not tre else float(np.median(tre)),
        "maximum_tre_pixels": None if not tre else float(np.max(tre)),
        "median_parameter_error": None if not parameter_error else float(np.median(parameter_error)),
        "mean_runtime_ms": None if not runtime else float(np.mean(runtime)),
        "median_runtime_ms": None if not runtime else float(np.median(runtime)),
    }
    if any("plausible_transform" in item for item in records):
        summary["plausible_transform_count"] = sum(
            bool(item.get("plausible_transform")) for item in records
        )
    return summary


def group_summaries(
    records: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return stable grouped summaries for selected record fields."""
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        group_key = tuple(str(record.get(key, "")) for key in keys)
        grouped[group_key].append(record)

    output: list[dict[str, Any]] = []
    for group_key in sorted(grouped):
        entry = {key: value for key, value in zip(keys, group_key, strict=True)}
        entry.update(summarize_benchmark_records(grouped[group_key]))
        output.append(entry)
    return output


def paired_method_outcomes(
    records: list[dict[str, Any]],
    *,
    method_a: str = "mutual_information",
    method_b: str = "ecc",
) -> dict[str, Any]:
    """Compare two methods only on shared cases, retaining all pass/CHECK outcomes."""
    by_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        by_case[str(record["case_id"])][str(record["method"])] = record

    paired: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        methods = by_case[case_id]
        if method_a not in methods or method_b not in methods:
            continue
        a = methods[method_a]
        b = methods[method_b]
        paired.append(
            {
                "case_id": case_id,
                "motion_model": a.get("motion_model"),
                "condition": a.get("condition"),
                f"{method_a}_within_tolerance": bool(a.get("within_tolerance")),
                f"{method_b}_within_tolerance": bool(b.get("within_tolerance")),
                f"{method_a}_tre_pixels": a.get("tre_pixels"),
                f"{method_b}_tre_pixels": b.get("tre_pixels"),
            }
        )

    return {
        "shared_case_count": len(paired),
        "both_pass": sum(
            item[f"{method_a}_within_tolerance"] and item[f"{method_b}_within_tolerance"]
            for item in paired
        ),
        f"{method_a}_only_pass": sum(
            item[f"{method_a}_within_tolerance"] and not item[f"{method_b}_within_tolerance"]
            for item in paired
        ),
        f"{method_b}_only_pass": sum(
            not item[f"{method_a}_within_tolerance"] and item[f"{method_b}_within_tolerance"]
            for item in paired
        ),
        "both_check": sum(
            not item[f"{method_a}_within_tolerance"] and not item[f"{method_b}_within_tolerance"]
            for item in paired
        ),
        "paired_cases": paired,
    }


def compact_seed_variability(day22_report: dict[str, Any]) -> dict[str, Any]:
    """Extract only the tracked stochastic evidence needed for the Week 5 closure."""
    study = dict(day22_report.get("studies", {}).get("random_seed_variability", {}))
    return {
        "source_report": "reports/week05_day02_mi_rigid_study.json",
        "sampling_strategy": study.get("sampling_strategy"),
        "sampling_percentage": study.get("sampling_percentage"),
        "selection_rule": study.get("selection_rule"),
        "per_case_variability": study.get("per_case_variability", []),
        "note": (
            "The frozen Day 25 MI configuration uses full sampling, so no stochastic seed is "
            "selected or rerun for final-test accuracy. Day 22 seed evidence is carried forward "
            "as the documented variability study."
        ),
    }
