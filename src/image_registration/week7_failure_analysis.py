"""Week 7 Day 33 read-only analysis of frozen Day 32 terminal evidence.

No registration or method selection occurs here. Geometric labels are known only
for development synthetic cases; diagnostic categories are descriptive and are
not inferred causal explanations or calibrated recommendation thresholds.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

import numpy as np

ANALYSIS_VERSION = "week07_day33_failure_analysis_v1"
GEOMETRIC_TOLERANCE_PX = 2.0
# Gallery-only severity tier, NOT a validity or recommendation threshold.
GALLERY_LARGE_ERROR_PX = 20.0


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_evidence(directory: Path, *, expected_attempts: int | None = None) -> tuple[list[dict], dict]:
    """Validate record integrity and manifest counts; refuse partial evidence."""
    directory = Path(directory)
    manifest_path = directory / "day32_manifest.json"
    records_path = directory / "benchmark_records.jsonl"
    if not manifest_path.is_file() or not records_path.is_file():
        raise FileNotFoundError("Day 33 requires Day 32 day32_manifest.json and benchmark_records.jsonl")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mode") != "full" or manifest.get("heldout_pixels_loaded") is not False:
        raise ValueError("Day 33 accepts full development-only evidence with untouched held-out pixels")
    planned_count = manifest.get("selected_tasks")
    if type(planned_count) is not int or planned_count <= 0:
        raise ValueError("Invalid selected_tasks in Day 32 manifest")
    if expected_attempts is not None and planned_count != expected_attempts:
        raise ValueError("Unexpected Day 32 attempt count")
    records: list[dict] = []
    seen: set[str] = set()
    with records_path.open(encoding="utf-8") as handle:
        for i, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            run_id = item.get("experiment_id")
            task, record = item.get("task"), item.get("record")
            if not isinstance(task, dict) or not isinstance(record, dict) or not isinstance(run_id, str):
                raise ValueError(f"Invalid benchmark envelope at line {i}")
            if run_id in seen or run_id != task.get("experiment_id"):
                raise ValueError(f"Duplicate or mismatched experiment ID at line {i}")
            if task.get("pair_metadata", {}).get("split") != "development":
                raise ValueError("Held-out/unknown split found in Day 32 record")
            if record.get("pair_id") != task.get("pair_id") or record.get("method_id") != task.get("method_id"):
                raise ValueError("Task/record identity mismatch")
            if record.get("execution_status") not in {"completed", "check", "failed", "validation_error"}:
                raise ValueError("Unknown execution status")
            seen.add(run_id)
            records.append(item)
    if len(records) != planned_count:
        raise ValueError(f"Incomplete evidence: {len(records)} of {planned_count} attempts")
    plan_path = directory / "benchmark_plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        task_ids = [x.get("experiment_id") for x in plan.get("tasks", [])]
        if len(task_ids) != planned_count or set(task_ids) != seen:
            raise ValueError("Day 32 plan IDs disagree with terminal records")
    csv_path = directory / "benchmark_results.csv"
    if csv_path.exists():
        flat: dict[str, str] = {}
        with csv_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                run_id = row.get("experiment_id")
                if not run_id or run_id in flat:
                    raise ValueError("Duplicate/blank experiment ID in Day 32 CSV")
                flat[run_id] = row.get("execution_status", "")
        if flat != {item["experiment_id"]: item["record"]["execution_status"] for item in records}:
            raise ValueError("Day 32 CSV identities/statuses disagree with journal")
    counters = Counter(item["record"]["execution_status"] for item in records)
    previous = manifest.get("runner", {}).get("status_counts")
    if isinstance(previous, dict) and {k: v for k, v in previous.items() if v} != dict(counters):
        raise ValueError("Manifest status counts disagree with terminal journal")
    if any(item["record"].get("geometric_within_tolerance") is True and
           item["record"]["execution_status"] in {"failed", "validation_error"} for item in records):
        raise ValueError("Execution failure cannot be a geometric success")
    return sorted(records, key=lambda r: r["experiment_id"]), manifest


def tre_of(envelope: Mapping[str, Any]) -> float | None:
    value = envelope["record"].get("metrics", {}).get("tre_mean_px")
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) and v >= 0 else None


def classify(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Use verified outcomes; condition labels are associated stresses, not causes."""
    record, task = envelope["record"], envelope["task"]
    status = record["execution_status"]
    tre = tre_of(envelope)
    reason = record.get("failure_reason")
    if status in {"failed", "validation_error"}:
        if reason in {"insufficient_filtered_matches", "insufficient_ransac_inliers"}:
            category = "feature_correspondence_failure"
        elif reason and "ecc" in reason.lower():
            category = "optimizer_execution_failure"
        else:
            category = "other_execution_failure"
    elif record.get("transform_plausible") is False:
        category = "implausible_transform"
    elif tre is not None and tre > GALLERY_LARGE_ERROR_PX and record.get("geometric_within_tolerance") is False:
        category = "large_geometric_error"
    elif record.get("geometric_within_tolerance") is False:
        category = "geometric_threshold_failure"
    elif record.get("geometric_within_tolerance") is True:
        category = "geometrically_successful"
    else:
        category = "unassessed_geometry"
    return {
        "experiment_id": envelope["experiment_id"], "pair_id": task["pair_id"],
        "method_id": task["method_id"], "method_family": task["method_family"],
        "transform_model": task["transform_model"], "modality_class": task["modality_class"],
        "condition": task["degradation"], "severity": task["pair_metadata"].get("condition_parameters", {}),
        "geometry_seed": task["pair_metadata"].get("geometry_seed"),
        "status": status, "geometrically_successful": record.get("geometric_within_tolerance") is True,
        "tre_mean_px": tre, "runtime_ms": record.get("timings_ms", {}).get("total"),
        "failure_reason": reason, "category": category,
        "associated_stress_not_proven_cause": task["degradation"],
    }


def _percentile(values: Iterable[float], percentile: int) -> float | None:
    values = list(values)
    return None if not values else round(float(np.percentile(values, percentile)), 5)


def aggregate(envelopes: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> list[dict]:
    """Denominators include completed-wrong, CHECK and execution failures."""
    groups: dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for item in envelopes:
        rec = classify(item)
        key = tuple(json.dumps(rec[field], sort_keys=True) if isinstance(rec[field], dict)
                    else rec[field] for field in fields)
        groups[key].append(item)
    rows = []
    for key, members in sorted(groups.items(), key=lambda z: str(z[0])):
        labels = dict(zip(fields, key))
        successes = sum(x["record"].get("geometric_within_tolerance") is True for x in members)
        execution_successes = sum(x["record"]["execution_status"] in {"completed", "check"} for x in members)
        tres = [value for x in members if (value := tre_of(x)) is not None]
        runtimes = [float(x["record"]["timings_ms"]["total"]) for x in members
                    if x["record"].get("timings_ms", {}).get("total") is not None]
        rows.append({**labels, "attempts": len(members),
                     "geometric_successes": successes, "geometric_success_rate": round(successes / len(members), 6),
                     "executed_with_transform": execution_successes,
                     "execution_rate": round(execution_successes / len(members), 6),
                     "check_count": sum(x["record"]["execution_status"] == "check" for x in members),
                     "failure_count": len(members) - execution_successes,
                     "tre_observed": len(tres), "tre_median_px_conditional": _percentile(tres, 50),
                     "tre_p95_px_conditional": _percentile(tres, 95),
                     "runtime_median_ms": _percentile(runtimes, 50),
                     "runtime_p95_ms": _percentile(runtimes, 95)})
    return rows


def summarize(envelopes: list[dict]) -> dict:
    cases = [classify(x) for x in envelopes]
    return {
        "analysis_version": ANALYSIS_VERSION,
        "attempts": len(envelopes), "pairs": len({x["pair_id"] for x in cases}),
        "statuses": dict(sorted(Counter(x["status"] for x in cases).items())),
        "geometric_successes": sum(x["geometrically_successful"] for x in cases),
        "geometric_failures_including_execution": sum(not x["geometrically_successful"] for x in cases),
        "taxonomy": dict(sorted(Counter(x["category"] for x in cases).items())),
        "execution_failure_reasons": dict(sorted(Counter(x["failure_reason"] for x in cases if x["failure_reason"]).items())),
        "by_condition": aggregate(envelopes, ("condition",)),
        "by_method": aggregate(envelopes, ("modality_class", "transform_model", "method_id")),
        "by_condition_method": aggregate(envelopes, ("condition", "modality_class", "transform_model", "method_id")),
        "by_severity": aggregate(envelopes, ("condition", "severity", "method_id", "modality_class", "transform_model")),
        "limitations": ["development-only synthetic evidence; the Week 8 held-out data were not used",
                        "descriptive failure categories do not prove physical or algorithmic causes",
                        "runtime numbers are from recorded end-to-end calls on one Windows machine; they are not isolated CPU or peak-memory profiles",
                        "TRE summaries are conditional on estimated transforms; success rates include failed attempts",
                        "synthetic multimodal mapping and periodic pattern stress are not validated real-world domain shifts"],
    }


def select_gallery_cases(envelopes: list[dict], *, limit: int = 12) -> list[dict]:
    """Deterministic stratified selection of errors, CHECKs, failures and controls."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in envelopes:
        groups[classify(item)["category"]].append(item)
    chosen, seen = [], set()
    def add(item):
        if item["experiment_id"] not in seen and len(chosen) < limit:
            chosen.append(item)
            seen.add(item["experiment_id"])
    for category in ("feature_correspondence_failure", "optimizer_execution_failure",
                     "large_geometric_error", "implausible_transform", "geometric_threshold_failure",
                     "geometrically_successful"):
        cases = groups[category]
        # Cover distinct stress conditions before taking another of the same type.
        cases = sorted(cases, key=lambda x: (x["task"]["degradation"],
                                            -(tre_of(x) or 0), x["experiment_id"]))
        visited = set()
        for item in cases:
            condition = item["task"]["degradation"]
            if condition not in visited:
                add(item)
                visited.add(condition)
            if len(chosen) >= limit:
                return chosen
    return chosen
