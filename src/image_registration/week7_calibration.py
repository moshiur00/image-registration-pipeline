"""Week 7 Day 34: offline, development-only evidence and abstention study.

This module never imports registration execution or UI selectors. Observable projections
are strict allowlists, and known synthetic TRE is used ONLY in offline evaluation.
No policy here represents deployed or held-out calibrated confidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
import math
from typing import Any, Mapping

import numpy as np

VERSION = "week07_day34_offline_calibration_v1"
ALLOWED_FAMILIES = frozenset({"frequency_domain", "intensity_based", "feature_based", "mutual_information"})
OBSERVABLE_KEYS = frozenset({
    "experiment_id", "pair_id", "method_id", "family", "model", "modality",
    "execution_status", "plausible", "transform", "shape_hw", "overlap",
    "inlier_ratio", "match_coverage", "inliers", "ecc_final", "ecc_levels",
    "mi_stop", "mi_metric", "mi_valid_points", "phase_response",
})


def finite_number(x: Any) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        f = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _safe_matrix(raw: Any) -> list[list[float]] | None:
    try:
        m = np.asarray(raw, dtype=np.float64)
        if m.shape != (3, 3) or not np.isfinite(m).all() or not np.allclose(m[2], (0, 0, 1), atol=1e-7):
            return None
        if abs(float(np.linalg.det(m[:2, :2]))) < 1e-9:
            return None
        return m.tolist()
    except (TypeError, ValueError, OverflowError, np.linalg.LinAlgError):
        return None


def project_observables(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Explicit, auditable observable-only firewall. No metrics or reference read.

    Prohibited inputs include offline_reference_overlap_fraction, TRE, synthetic
    geometry truth, success label, degradation, severity, geometry_seed and split.
    """
    record, task = envelope["record"], envelope["task"]
    raw = record.get("method_diagnostics", {}).get("raw", {})
    if not isinstance(raw, dict):
        raw = {}
    preparation = raw.get("preparation", {})
    if not isinstance(preparation, dict):
        preparation = {}
    fixed = preparation.get("fixed_source", {})
    shape = fixed.get("shape") if isinstance(fixed, dict) else None
    shape_hw = None
    if isinstance(shape, (list, tuple)) and len(shape) >= 2:
        try:
            h, w = int(shape[0]), int(shape[1])
            if 8 <= h <= 100_000 and 8 <= w <= 100_000:
                shape_hw = [h, w]
        except (TypeError, ValueError, OverflowError):
            pass
    coverage = [finite_number(raw.get(k)) for k in ("fixed_match_coverage", "moving_match_coverage")]
    coverage = [v for v in coverage if v is not None]
    return {
        "experiment_id": str(envelope["experiment_id"]),
        "pair_id": str(record["pair_id"]),
        "method_id": str(record["method_id"]),
        "family": str(record["method_family"]),
        "model": str(record["transform_model"]),
        "modality": str(record["modality_class"]),
        "execution_status": str(record["execution_status"]),
        "plausible": record.get("transform_plausible") is True,
        "transform": _safe_matrix(record.get("estimated_transform")),
        "shape_hw": shape_hw,
        "overlap": finite_number(record.get("valid_overlap_fraction")),
        "inlier_ratio": finite_number(raw.get("ransac_inlier_ratio")),
        "match_coverage": min(coverage) if coverage else None,
        "inliers": finite_number(raw.get("ransac_inliers")),
        "ecc_final": finite_number(raw.get("final_ecc")),
        "ecc_levels": finite_number(raw.get("levels_completed")),
        "mi_stop": str(raw.get("optimizer_stop_condition") or "")[:200],
        "mi_metric": finite_number(raw.get("final_metric_value")),
        "mi_valid_points": finite_number(raw.get("valid_metric_points")),
        "phase_response": finite_number(raw.get("response")),
    }


def reference_points(hw: list[int]) -> np.ndarray:
    h, w = hw
    return np.array([[0., 0.], [w-1., 0.], [0., h-1.], [w-1., h-1.],
                     [(w-1.)/2, (h-1.)/2]], dtype=np.float64)


def transfer_distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> float | None:
    """Mean five-point displacement (px) of Moving->Fixed transforms; GT-free."""
    if a["shape_hw"] is None or a["shape_hw"] != b["shape_hw"]:
        return None
    ma, mb = _safe_matrix(a["transform"]), _safe_matrix(b["transform"])
    if ma is None or mb is None:
        return None
    p = reference_points(a["shape_hw"])
    v = np.c_[p, np.ones(len(p))]
    aa, bb = tuple(v @ np.asarray(m).T for m in (ma, mb))
    if np.any(np.abs(aa[:, 2]) < 1e-9) or np.any(np.abs(bb[:, 2]) < 1e-9):
        return None
    axy, bxy = aa[:, :2] / aa[:, 2:3], bb[:, :2] / bb[:, 2:3]
    d = float(np.linalg.norm(axy - bxy, axis=1).mean())
    return round(d, 9) if math.isfinite(d) else None


@dataclass(frozen=True)
class Gate:
    agreement_px: float = 2.0
    overlap_floor: float = 0.35
    min_feature_inlier: float = 0.25
    min_feature_coverage: float = 0.125
    min_distinct_families: int = 3
    min_candidates: int = 3

    def __post_init__(self) -> None:
        if not (0 < self.agreement_px <= 100 and 0 <= self.overlap_floor <= 1
                and 0 <= self.min_feature_inlier <= 1 and 0 <= self.min_feature_coverage <= 1
                and self.min_distinct_families >= 3 and self.min_candidates >= 3):
            raise ValueError("Invalid exploratory calibration gate")


def eligible(o: Mapping[str, Any], gate: Gate) -> bool:
    if (o["execution_status"] != "completed" or not o["plausible"]
            or o["transform"] is None or o["shape_hw"] is None
            or o["family"] not in ALLOWED_FAMILIES
            or o["overlap"] is None or o["overlap"] < gate.overlap_floor):
        return False
    if o["family"] == "feature_based":
        return (o["inlier_ratio"] is not None and o["inlier_ratio"] >= gate.min_feature_inlier
                and o["match_coverage"] is not None and o["match_coverage"] >= gate.min_feature_coverage)
    if o["family"] == "intensity_based":
        return o["ecc_final"] is not None and o["ecc_levels"] is not None and o["ecc_levels"] > 0
    if o["family"] == "mutual_information":
        return (o["mi_metric"] is not None and bool(o["mi_stop"])
                and o["mi_valid_points"] is not None and o["mi_valid_points"] > 0)
    return o["phase_response"] is not None


def select_pair(observables: list[Mapping[str, Any]], gate: Gate) -> dict[str, Any]:
    """Tentative abstention study: never a final selector or UI policy.

    Require a mutually agreeing 3-family triangle, not a 2-method medoid.
    Within a triangle choose its deterministic observable geometric medoid.
    """
    if not observables:
        return {"decision": "abstain", "reason": "no_candidates", "selected_id": None,
                "support_ids": [], "support_families": [], "max_cross_family_displacement_px": None}
    pair_ids = {o["pair_id"] for o in observables}
    if len(pair_ids) != 1 or len({o["model"] for o in observables}) != 1:
        raise ValueError("Cannot compare different pair IDs or models")
    candidates = sorted((o for o in observables if eligible(o, gate)), key=lambda o: o["experiment_id"])
    families = {o["family"] for o in candidates}
    reason = "insufficient_eligible_candidates" if len(candidates) < gate.min_candidates else "insufficient_distinct_method_families"
    if len(candidates) >= gate.min_candidates and len(families) >= gate.min_distinct_families:
        feasible = []
        for triple in combinations(candidates, 3):
            if len({o["family"] for o in triple}) != 3:
                continue
            distances = [transfer_distance(a, b) for a, b in combinations(triple, 2)]
            if any(d is None for d in distances) or max(distances) > gate.agreement_px:
                continue
            total = sum(distances)
            # Choose a geometric medoid from three DIFFERENT families.
            medoids = [(sum(transfer_distance(o, other) for other in triple if o is not other), o["experiment_id"])
                       for o in triple]
            medoid_id = min(medoids)[1]
            feasible.append((max(distances), total, tuple(sorted(o["experiment_id"] for o in triple)), medoid_id, triple))
        if feasible:
            max_disp, _, ids, selected, triple = min(feasible, key=lambda x: x[:4])
            return {"decision": "tentative_supported", "reason": "three_family_agreement",
                    "selected_id": selected, "support_ids": list(ids),
                    "support_families": sorted(o["family"] for o in triple),
                    "max_cross_family_displacement_px": round(max_disp, 6)}
        reason = "no_consistent_three_family_triangle"
    return {"decision": "abstain", "reason": reason, "selected_id": None,
            "support_ids": [], "support_families": [], "max_cross_family_displacement_px": None}


def records_by_pair(records: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    output: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in records:
        if item["task"].get("pair_metadata", {}).get("split") != "development":
            raise ValueError("Non-development record in offline calibration")
        output[item["record"]["pair_id"]].append(item)
    return dict(sorted(output.items()))


def labels_by_pair(records: list[Mapping[str, Any]]) -> dict[str, dict[str, bool]]:
    """Offline-only labels. MUST NOT be passed to project_observables/select_pair."""
    return {k: {x["experiment_id"]: x["record"].get("geometric_within_tolerance") is True
                for x in group} for k, group in records_by_pair(records).items()}


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    if not (0 <= successes <= n):
        raise ValueError("Invalid successes / trials")
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return round(max(0., center-half), 6), round(min(1., center+half), 6)


def offline_evaluate(records: list[Mapping[str, Any]], gate: Gate) -> tuple[list[dict], dict]:
    labels = labels_by_pair(records)
    out = []
    for pair_id, group in records_by_pair(records).items():
        obs = [project_observables(item) for item in group]
        decision = select_pair(obs, gate)
        selected_id = decision["selected_id"]
        meta = group[0]["task"]["pair_metadata"]
        out.append({"pair_id": pair_id, "seed": int(meta["geometry_seed"]),
                    "condition": group[0]["task"]["degradation"],
                    "model": group[0]["task"]["transform_model"],
                    "modality": group[0]["task"]["modality_class"],
                    "attempts": len(group), "eligible_candidates": sum(eligible(x,gate) for x in obs),
                    "decision": decision["decision"], "reason": decision["reason"],
                    "selected_id": selected_id, "support_ids": decision["support_ids"],
                    "support_families": decision["support_families"],
                    "max_cross_family_displacement_px": decision["max_cross_family_displacement_px"],
                    "selected_geometrically_correct_offline": labels[pair_id][selected_id] if selected_id else None,
                    "any_method_correct_offline": any(labels[pair_id].values()),
                    "all_methods_correct_offline": all(labels[pair_id].values())})
    return out, summarize_decisions(out)


def summarize_decisions(rows: list[Mapping[str, Any]]) -> dict:
    n = len(rows)
    supported = [x for x in rows if x["decision"] == "tentative_supported"]
    correct = sum(x["selected_geometrically_correct_offline"] is True for x in supported)
    low, high = wilson_interval(correct, len(supported))
    return {"pairs": n, "tentatively_supported": len(supported),
            "abstained": n - len(supported),
            "coverage": round(len(supported)/n, 6) if n else None,
            "correct_selected": correct,
            "incorrect_selected": len(supported)-correct,
            "conditional_precision": round(correct/len(supported), 6) if supported else None,
            "precision_wilson_95_exploratory": [low, high],
            "reason_counts": dict(sorted(Counter(x["reason"] for x in rows).items()))}


def bucket(value: float | None, thresholds: tuple[float, float]) -> str:
    if value is None:
        return "missing"
    return "low" if value < thresholds[0] else "medium" if value < thresholds[1] else "high"


def signal_table(records: list[Mapping[str, Any]]) -> list[dict]:
    """Descriptive signal-vs-GT associations, with explicit family-specific bins."""
    groups: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    for item in records:
        o = project_observables(item)
        truth = item["record"].get("geometric_within_tolerance") is True
        signals = {"estimated_overlap": (o["overlap"], (.4, .7))}
        if o["family"] == "feature_based":
            signals.update({"feature_inlier_ratio": (o["inlier_ratio"], (.4, .8)),
                            "feature_match_coverage": (o["match_coverage"], (.2, .5))})
        elif o["family"] == "intensity_based":
            signals["ecc_final_value"] = (o["ecc_final"], (.5, .85))
            signals["ecc_levels_completed"] = (o["ecc_levels"], (1., 3.))
        elif o["family"] == "mutual_information":
            # MI raw values are NOT comparable to ECC nor necessarily across MI configs.
            signals["mi_valid_metric_points"] = (o["mi_valid_points"], (1000., 10000.))
            groups[(o["family"], "mi_stop_reported", "yes" if o["mi_stop"] else "no")].append(truth)
        elif o["family"] == "frequency_domain":
            signals["phase_response"] = (o["phase_response"], (.15, .4))
        for name, (value, bounds) in signals.items():
            groups[(o["family"], name, bucket(value, bounds))].append(truth)
    return [{"method_family": family, "signal": signal, "bin": bn, "attempts": len(v),
             "geometric_successes": sum(v), "success_rate": round(sum(v)/len(v), 6)}
            for (family,signal,bn),v in sorted(groups.items())]


def grouped_summary(rows: list[Mapping[str, Any]], dimensions: tuple[str, ...]) -> list[dict]:
    groups: dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in dimensions)].append(row)
    return [{**dict(zip(dimensions,k)), **summarize_decisions(v)} for k,v in sorted(groups.items(), key=str)]
