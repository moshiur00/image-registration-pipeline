"""Generate sanitized Week 8 Phase 9.2 tables, figures, and manifest.

The generator reads only sealed Phase 8 metadata/results and the tracked Phase
9.1 closure.  It never opens source images, prepared arrays, or sealed labels,
and it never runs registration or evaluation.  Outputs are aggregate and do
not contain source, pair, or attempt identifiers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
FINAL_ROOT = ROOT / "outputs" / "week08_final"
RELEASE_MANIFEST = ROOT / "reports" / "pre_week08_release_manifest.json"
PHASE91_REPORT = ROOT / "reports" / "week08_phase9_data_quality_closure.json"
TABLE_DIR = ROOT / "reports" / "week08_phase9_tables"
FIGURE_DIR = ROOT / "docs" / "figures" / "week08_phase9"
ANALYSIS_MANIFEST = ROOT / "reports" / "week08_phase9_final_analysis.json"
SCHEMA_VERSION = "week08_phase9_final_analysis_v1"

TABLE_FILES = (
    "track_a_overall.csv",
    "track_a_by_modality.csv",
    "track_a_by_condition.csv",
    "track_a_runtime_by_method.csv",
    "repeated_pattern_by_method.csv",
    "similarity_geometry_availability.csv",
    "track_b_policy.csv",
)

FIGURE_FILES = (
    "track_a_overall_rates.svg",
    "track_a_modality_rates.svg",
    "track_a_condition_rates.svg",
    "track_a_runtime_by_method.svg",
    "repeated_pattern_outcomes.svg",
    "similarity_geometry_availability.svg",
    "track_b_policy.svg",
)

PROHIBITED_CLAIMS = [
    "anatomical_generalization",
    "clinical_recommendation",
    "external_validity",
    "modality_wide_generalization",
    "population_generalization",
]

METHOD_ORDER = [
    "phase_translation",
    "ecc_translation",
    "ecc_rigid",
    "ecc_affine",
    "orb_similarity",
    "sift_similarity",
    "orb_affine",
    "sift_affine",
    "mi_rigid_2d",
    "mi_affine_2d",
]

CONDITION_ORDER = [
    "none",
    "gaussian_noise",
    "gaussian_blur",
    "illumination",
    "occlusion",
    "partial_overlap",
    "low_texture",
    "repeated_pattern",
    "multimodal_mapping",
]

COLORS = {
    "blue": "#2F6690",
    "green": "#3A7D44",
    "orange": "#D08C2E",
    "red": "#B84A4A",
    "gray": "#6B7280",
    "light_gray": "#D8DEE6",
    "navy": "#17324D",
}

PRIVATE_PATTERNS = (
    re.compile(r"w8-[0-9a-f]+", re.IGNORECASE),
    re.compile(r"final-[0-9a-f]+", re.IGNORECASE),
    re.compile(r"\bpia\d{4,}\b", re.IGNORECASE),
    re.compile(r"nasa_pia", re.IGNORECASE),
    re.compile(r"sealed_labels", re.IGNORECASE),
    re.compile(r"labels\.json", re.IGNORECASE),
    re.compile(r"\.npy", re.IGNORECASE),
)


class AnalysisError(ValueError):
    """Raised when sealed inputs or sanitized outputs fail validation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisError(message)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AnalysisError(f"Expected a JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AnalysisError(f"Expected an object at {path}:{number}")
        rows.append(value)
    return rows


def verify_payload_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    payload = dict(value)
    recorded = payload.pop(field, None)
    require(isinstance(recorded, str), f"{label} lacks {field}")
    require(canonical_sha256(payload) == recorded, f"{label} self-hash mismatch")
    return recorded


def _format_csv(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        require(math.isfinite(value), "CSV contains a non-finite number")
        return f"{value:.6f}"
    return str(value)


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    require(bool(rows), f"Refusing to write an empty table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            require(set(row) == set(columns), f"Unexpected columns in {path.name}")
            writer.writerow({column: _format_csv(row[column]) for column in columns})
    os.replace(temporary, path)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _rate_fields(prefix: str, rate: Mapping[str, Any], uncertainty: Mapping[str, Any]) -> dict[str, Any]:
    return {
        f"{prefix}_numerator": rate["numerator"],
        f"{prefix}_denominator": rate["denominator"],
        f"{prefix}_value": rate["value"],
        f"{prefix}_ci_lower": uncertainty["lower"],
        f"{prefix}_ci_upper": uncertainty["upper"],
        f"{prefix}_ci_method": uncertainty["method"],
    }


def _status(row: Mapping[str, Any], name: str) -> int:
    counts = row.get("status_counts", {})
    return int(counts.get(name, 0)) if isinstance(counts, Mapping) else 0


def _track_a_row(
    scope: str,
    row: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    uncertainty = row["uncertainty"]
    result: dict[str, Any] = {
        "scope": scope,
        "attempts": row.get("attempts", row.get("planned_attempts")),
        "completed": _status(row, "completed"),
        "check": _status(row, "CHECK"),
        "failed": _status(row, "failed"),
        "valid_gt_attempts": row["valid_gt_attempts"],
        "geometric_successes": row["geometric_successes"],
        "runtime_count": runtime["count"],
        "runtime_min_ms": runtime["minimum"],
        "runtime_median_ms": runtime["median"],
        "runtime_mean_ms": runtime["mean"],
        "runtime_p95_ms": runtime["p95"],
        "runtime_max_ms": runtime["maximum"],
        "runtime_scope": "total_runtime_ms",
        "interpretation": row.get("interpretation", "preregistered_overall"),
    }
    result.update(
        _rate_fields(
            "completion",
            row["execution_completion_rate"],
            uncertainty["execution_completion_rate"],
        )
    )
    result.update(
        _rate_fields(
            "geometric_success",
            row["geometric_success_rate"],
            uncertainty["geometric_success_rate"],
        )
    )
    result.update(
        _rate_fields(
            "conditional_accuracy",
            row["conditional_accuracy"],
            uncertainty["conditional_accuracy"],
        )
    )
    return result


TRACK_A_COLUMNS = (
    "scope",
    "attempts",
    "completed",
    "check",
    "failed",
    "valid_gt_attempts",
    "geometric_successes",
    "completion_numerator",
    "completion_denominator",
    "completion_value",
    "completion_ci_lower",
    "completion_ci_upper",
    "completion_ci_method",
    "geometric_success_numerator",
    "geometric_success_denominator",
    "geometric_success_value",
    "geometric_success_ci_lower",
    "geometric_success_ci_upper",
    "geometric_success_ci_method",
    "conditional_accuracy_numerator",
    "conditional_accuracy_denominator",
    "conditional_accuracy_value",
    "conditional_accuracy_ci_lower",
    "conditional_accuracy_ci_upper",
    "conditional_accuracy_ci_method",
    "runtime_count",
    "runtime_min_ms",
    "runtime_median_ms",
    "runtime_mean_ms",
    "runtime_p95_ms",
    "runtime_max_ms",
    "runtime_scope",
    "interpretation",
)


def _sort_by_order(rows: Sequence[Mapping[str, Any]], key: str, order: Sequence[str]) -> list[Mapping[str, Any]]:
    positions = {name: index for index, name in enumerate(order)}
    return sorted(rows, key=lambda row: (positions.get(str(row[key]), len(positions)), str(row[key])))


def build_tables(summary: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]]:
    track_a = summary["track_a"]
    track_b = summary["track_b"]
    overall = dict(track_a["overall"])
    overall["attempts"] = overall["planned_attempts"]
    overall["uncertainty"] = summary["uncertainty"]
    overall_rows = [
        _track_a_row(
            "overall",
            overall,
            track_a["runtime"]["overall_total_runtime_ms"],
        )
    ]

    modality_rows = []
    for row in _sort_by_order(track_a["strata"]["modality_class"], "modality_class", ["monomodal", "simulated_multimodal"]):
        modality_rows.append(_track_a_row(str(row["modality_class"]), row, row["total_runtime_ms"]))

    condition_rows = []
    for row in _sort_by_order(track_a["strata"]["condition"], "condition", CONDITION_ORDER):
        condition_rows.append(_track_a_row(str(row["condition"]), row, row["total_runtime_ms"]))

    runtime_columns = (
        "method_id",
        "attempts",
        "runtime_min_ms",
        "runtime_median_ms",
        "runtime_mean_ms",
        "runtime_p95_ms",
        "runtime_max_ms",
        "runtime_scope",
        "uncertainty_note",
    )
    runtime_rows: list[dict[str, Any]] = []
    runtime_all = track_a["runtime"]
    overall_runtime = runtime_all["overall_total_runtime_ms"]
    runtime_rows.append(
        {
            "method_id": "overall",
            "attempts": overall_runtime["count"],
            "runtime_min_ms": overall_runtime["minimum"],
            "runtime_median_ms": overall_runtime["median"],
            "runtime_mean_ms": overall_runtime["mean"],
            "runtime_p95_ms": overall_runtime["p95"],
            "runtime_max_ms": overall_runtime["maximum"],
            "runtime_scope": "total_runtime_ms",
            "uncertainty_note": "distribution_summary_not_confidence_interval",
        }
    )
    runtime_by_method = {row["method_id"]: row for row in runtime_all["by_method"]}
    for method_id in METHOD_ORDER:
        entry = runtime_by_method[method_id]["total_runtime_ms"]
        runtime_rows.append(
            {
                "method_id": method_id,
                "attempts": entry["count"],
                "runtime_min_ms": entry["minimum"],
                "runtime_median_ms": entry["median"],
                "runtime_mean_ms": entry["mean"],
                "runtime_p95_ms": entry["p95"],
                "runtime_max_ms": entry["maximum"],
                "runtime_scope": "total_runtime_ms",
                "uncertainty_note": "distribution_summary_not_confidence_interval",
            }
        )

    failure_reasons: dict[str, Counter[str]] = defaultdict(Counter)
    for envelope in records:
        task = envelope["task"]
        record = envelope["record"]
        if task.get("condition") != "repeated_pattern" or record.get("execution_status") != "failed":
            continue
        failure_reasons[str(task["method_id"])][str(record.get("failure_reason") or "unrecorded")] += 1

    repeated_attempts = [
        row for row in track_a["attempts"] if row.get("condition") == "repeated_pattern"
    ]
    repeated_grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in repeated_attempts:
        repeated_grouped[str(row["method_id"])].append(row)
    repeated_columns = (
        "method_id",
        "attempts",
        "completed",
        "geometric_successes",
        "completed_geometric_failures",
        "execution_failures",
        "insufficient_filtered_matches",
        "insufficient_ransac_inliers",
        "interpretation",
    )
    repeated_rows: list[dict[str, Any]] = []
    for method_id in METHOD_ORDER:
        rows = repeated_grouped.get(method_id, [])
        if not rows:
            continue
        completed = sum(row["execution_status"] == "completed" for row in rows)
        success = sum(row.get("geometric_within_tolerance") is True for row in rows)
        failures = len(rows) - completed
        repeated_rows.append(
            {
                "method_id": method_id,
                "attempts": len(rows),
                "completed": completed,
                "geometric_successes": success,
                "completed_geometric_failures": completed - success,
                "execution_failures": failures,
                "insufficient_filtered_matches": failure_reasons[method_id]["insufficient_filtered_matches"],
                "insufficient_ransac_inliers": failure_reasons[method_id]["insufficient_ransac_inliers"],
                "interpretation": "descriptive_low_count",
            }
        )

    attempts = track_a["attempts"]
    denominator = len(attempts)
    common_fields = [
        ("mae", "common_image_similarity", "not_recorded"),
        ("mse", "common_image_similarity", "not_recorded"),
        ("ncc", "common_image_similarity", "not_recorded"),
        ("ssim", "common_image_similarity", "not_recorded"),
        ("mi_nats", "common_image_similarity", "not_recorded"),
        ("valid_overlap_fraction", "common_support", "not_recorded"),
    ]
    availability_columns = (
        "evidence_field",
        "category",
        "available_count",
        "denominator",
        "availability_fraction",
        "comparison_status",
        "interpretation",
    )
    availability_rows: list[dict[str, Any]] = []
    for field, category, state in common_fields:
        count = sum(row.get(field) is not None for row in attempts)
        require(count == 0, f"Unexpected common evidence became available: {field}")
        availability_rows.append(
            {
                "evidence_field": field,
                "category": category,
                "available_count": count,
                "denominator": denominator,
                "availability_fraction": count / denominator,
                "comparison_status": "NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS",
                "interpretation": state,
            }
        )
    valid_geometry = sum(row.get("geometric_reference_valid") is True for row in attempts)
    numeric_tre = sum(row.get("tre_mean_px") is not None for row in attempts)
    availability_rows.extend(
        [
            {
                "evidence_field": "valid_geometric_reference",
                "category": "geometric_reference",
                "available_count": valid_geometry,
                "denominator": denominator,
                "availability_fraction": valid_geometry / denominator,
                "comparison_status": "available",
                "interpretation": "known_synthetic_after_freeze_reference",
            },
            {
                "evidence_field": "tre_mean_px",
                "category": "geometric_outcome",
                "available_count": numeric_tre,
                "denominator": denominator,
                "availability_fraction": numeric_tre / denominator,
                "comparison_status": "available_for_completed_attempts",
                "interpretation": "failed_executions_have_no_numeric_tre",
            },
        ]
    )

    raw_counts = Counter()
    family_attempts = Counter()
    for envelope in records:
        family = str(envelope["record"]["method_family"])
        raw = envelope["record"].get("method_diagnostics", {}).get("raw", {})
        if not isinstance(raw, Mapping):
            raw = {}
        family_attempts[family] += 1
        if family == "intensity_based" and raw.get("final_ecc") is not None:
            raw_counts["ecc_final_ecc"] += 1
        elif family == "mutual_information" and raw.get("final_metric_value") is not None:
            raw_counts["mi_final_metric_value"] += 1
        elif family == "frequency_domain" and raw.get("response") is not None:
            raw_counts["phase_response"] += 1
        elif family == "feature_based" and raw.get("ransac_inlier_ratio") is not None:
            raw_counts["feature_ransac_inlier_ratio"] += 1
    raw_specs = [
        ("ecc_final_ecc", "intensity_based"),
        ("mi_final_metric_value", "mutual_information"),
        ("phase_response", "frequency_domain"),
        ("feature_ransac_inlier_ratio", "feature_based"),
    ]
    for field, family in raw_specs:
        availability_rows.append(
            {
                "evidence_field": field,
                "category": "family_specific_raw_diagnostic",
                "available_count": raw_counts[field],
                "denominator": family_attempts[family],
                "availability_fraction": raw_counts[field] / family_attempts[family],
                "comparison_status": "NONCOMMENSURATE_NOT_COMPARED",
                "interpretation": "method_family_native_units_no_cross_family_ranking",
            }
        )

    policy_columns = (
        "scope",
        "eligible_pairs",
        "selected_pairs",
        "abstained_pairs",
        "invalid_pairs",
        "missing_decision_pairs",
        "coverage_numerator",
        "coverage_denominator",
        "coverage_value",
        "coverage_ci_lower",
        "coverage_ci_upper",
        "coverage_ci_method",
        "abstention_numerator",
        "abstention_denominator",
        "abstention_value",
        "abstention_ci_lower",
        "abstention_ci_upper",
        "abstention_ci_method",
        "selective_correctness_value",
        "interpretation",
    )

    def policy_row(scope: str, row: Mapping[str, Any], uncertainty: Mapping[str, Any], interpretation: str) -> dict[str, Any]:
        result = {
            "scope": scope,
            "eligible_pairs": row["eligible_pairs"],
            "selected_pairs": row["selected_pairs"],
            "abstained_pairs": row["abstained_pairs"],
            "invalid_pairs": row["invalid_pairs"],
            "missing_decision_pairs": row["missing_decision_pairs"],
            "selective_correctness_value": row["selective_correctness"]["value"],
            "interpretation": interpretation,
        }
        result.update(_rate_fields("coverage", row["coverage"], uncertainty["coverage"]))
        result.update(_rate_fields("abstention", row["abstention_rate"], uncertainty["abstention_rate"]))
        result.pop("coverage_ci_method", None)
        result["coverage_ci_method"] = uncertainty["coverage"]["method"]
        result.pop("abstention_ci_method", None)
        result["abstention_ci_method"] = uncertainty["abstention_rate"]["method"]
        return result

    overall_b = track_b["overall"]
    overall_b_uncertainty = {
        "coverage": summary["uncertainty"]["policy_coverage"],
        "abstention_rate": summary["uncertainty"]["policy_abstention_rate"],
        "selective_correctness": summary["uncertainty"]["policy_selective_correctness"],
    }
    policy_rows = [
        policy_row("overall", overall_b, overall_b_uncertainty, "preregistered_overall")
    ]
    for row in _sort_by_order(track_b["strata"]["condition"], "condition", CONDITION_ORDER):
        policy_rows.append(
            policy_row(str(row["condition"]), row, row["uncertainty"], str(row["interpretation"]))
        )

    return {
        "track_a_overall.csv": (TRACK_A_COLUMNS, overall_rows),
        "track_a_by_modality.csv": (TRACK_A_COLUMNS, modality_rows),
        "track_a_by_condition.csv": (TRACK_A_COLUMNS, condition_rows),
        "track_a_runtime_by_method.csv": (runtime_columns, runtime_rows),
        "repeated_pattern_by_method.csv": (repeated_columns, repeated_rows),
        "similarity_geometry_availability.csv": (availability_columns, availability_rows),
        "track_b_policy.csv": (policy_columns, policy_rows),
    }


def _configure_matplotlib() -> None:
    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.alpha": 0.22,
            "grid.linewidth": 0.7,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.hashsalt": "week08-phase9-final-analysis-v1",
            "svg.fonttype": "none",
        }
    )


def _save_figure(fig: plt.Figure, path: Path, preview_dir: Path | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.svg")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    fig.savefig(
        temporary,
        format="svg",
        metadata={"Date": None, "Creator": "Image Registration Pipeline Phase 9.2"},
    )
    normalized_svg = "\n".join(
        line.rstrip() for line in temporary.read_text(encoding="utf-8").splitlines()
    ) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(normalized_svg)
    os.replace(temporary, path)
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            preview_dir / path.with_suffix(".png").name,
            format="png",
            dpi=170,
            metadata={"Software": "Image Registration Pipeline Phase 9.2"},
        )
    plt.close(fig)


def _percent_label(value: float) -> str:
    return f"{100 * value:.1f}%"


def _rate_error(value: float, lower: float, upper: float) -> list[list[float]]:
    return [[max(0.0, value - lower)], [max(0.0, upper - value)]]


def build_figures(
    tables: Mapping[str, tuple[tuple[str, ...], list[dict[str, Any]]]],
    destination: Path,
    preview_dir: Path | None = None,
) -> None:
    _configure_matplotlib()
    note = "Source-specific software evidence; one source; no deployment claim"

    overall = tables["track_a_overall.csv"][1][0]
    metrics = [
        ("Completion", "completion", COLORS["blue"]),
        ("Geometric success", "geometric_success", COLORS["green"]),
        ("Conditional accuracy", "conditional_accuracy", COLORS["orange"]),
    ]
    fig, ax = plt.subplots(figsize=(7.6, 4.7))
    for index, (label, prefix, color) in enumerate(metrics):
        value = float(overall[f"{prefix}_value"])
        lower = float(overall[f"{prefix}_ci_lower"])
        upper = float(overall[f"{prefix}_ci_upper"])
        ax.bar(index, value, width=0.62, color=color)
        ax.errorbar(index, value, yerr=_rate_error(value, lower, upper), color=COLORS["navy"], capsize=5, lw=1.4)
        ax.text(index, min(1.075, upper + 0.035), _percent_label(value), ha="center", weight="bold")
        ax.text(index, 0.045, f"{overall[f'{prefix}_numerator']}/{overall[f'{prefix}_denominator']}", ha="center", color="white", weight="bold")
    ax.set_xticks(range(len(metrics)), [item[0] for item in metrics])
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("Rate with Wilson 95% interval")
    ax.set_title("Track A: completion and geometric performance")
    fig.text(0.5, 0.017, note, ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "track_a_overall_rates.svg", preview_dir)

    modality = tables["track_a_by_modality.csv"][1]
    fig, ax = plt.subplots(figsize=(10.2, 5.0))
    width = 0.24
    x = list(range(len(modality)))
    for offset, (label, prefix, color) in zip((-width, 0.0, width), metrics):
        values = [float(row[f"{prefix}_value"]) for row in modality]
        lower = [values[i] - float(modality[i][f"{prefix}_ci_lower"]) for i in range(len(modality))]
        upper = [float(modality[i][f"{prefix}_ci_upper"]) - values[i] for i in range(len(modality))]
        positions = [item + offset for item in x]
        ax.bar(positions, values, width=width, label=label, color=color)
        ax.errorbar(positions, values, yerr=[lower, upper], fmt="none", ecolor=COLORS["navy"], capsize=3, lw=1)
    labels = ["Monomodal\n(n=240)", "Simulated multimodal\n(n=54)"]
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("Rate with Wilson 95% interval")
    ax.set_title("Track A by modality class")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    fig.text(0.5, 0.017, note, ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "track_a_modality_rates.svg", preview_dir)

    conditions = tables["track_a_by_condition.csv"][1]
    labels = [str(row["scope"]).replace("_", " ") for row in conditions]
    fig, ax = plt.subplots(figsize=(11.7, 6.2))
    y = list(range(len(conditions)))
    completion = [float(row["completion_value"]) for row in conditions]
    success = [float(row["geometric_success_value"]) for row in conditions]
    height = 0.34
    ax.barh([item - height / 2 for item in y], completion, height=height, color=COLORS["blue"], label="Completion")
    ax.barh([item + height / 2 for item in y], success, height=height, color=COLORS["green"], label="Geometric success")
    for index, row in enumerate(conditions):
        ax.errorbar(
            completion[index],
            y[index] - height / 2,
            xerr=[[completion[index] - float(row["completion_ci_lower"])], [float(row["completion_ci_upper"]) - completion[index]]],
            fmt="none",
            ecolor=COLORS["navy"],
            capsize=2,
            lw=0.9,
        )
        ax.errorbar(
            success[index],
            y[index] + height / 2,
            xerr=[[success[index] - float(row["geometric_success_ci_lower"])], [float(row["geometric_success_ci_upper"]) - success[index]]],
            fmt="none",
            ecolor=COLORS["navy"],
            capsize=2,
            lw=0.9,
        )
        if row["scope"] == "repeated_pattern":
            ax.axhspan(index - 0.46, index + 0.46, color=COLORS["red"], alpha=0.08)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Rate with Wilson 95% interval")
    ax.set_title("Track A by condition (failures retained in denominators)")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    fig.text(0.5, 0.017, note, ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "track_a_condition_rates.svg", preview_dir)

    runtime = [row for row in tables["track_a_runtime_by_method.csv"][1] if row["method_id"] != "overall"]
    fig, ax = plt.subplots(figsize=(9.3, 6.1))
    y = list(range(len(runtime)))
    medians = [float(row["runtime_median_ms"]) for row in runtime]
    p95 = [float(row["runtime_p95_ms"]) for row in runtime]
    for index, (median, upper) in enumerate(zip(medians, p95)):
        ax.hlines(index, median, upper, color=COLORS["light_gray"], lw=5)
        ax.plot(median, index, "o", color=COLORS["blue"], ms=6)
        ax.plot(upper, index, "|", color=COLORS["red"], ms=11, mew=2)
    ax.set_yticks(y, [str(row["method_id"]) for row in runtime])
    ax.invert_yaxis()
    ax.set_xlabel("Recorded total runtime (ms)")
    ax.set_title("Track A runtime by method: median to p95")
    ax.text(0.99, 0.98, "● median    | p95\nDistribution summaries, not confidence intervals", transform=ax.transAxes, ha="right", va="top", color=COLORS["gray"], fontsize=8)
    fig.text(0.5, 0.017, note + "; single recorded environment", ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "track_a_runtime_by_method.svg", preview_dir)

    repeated = tables["repeated_pattern_by_method.csv"][1]
    fig, ax = plt.subplots(figsize=(11.0, 6.0))
    y = list(range(len(repeated)))
    success = [int(row["geometric_successes"]) for row in repeated]
    geometric_failure = [int(row["completed_geometric_failures"]) for row in repeated]
    execution_failure = [int(row["execution_failures"]) for row in repeated]
    ax.barh(y, success, color=COLORS["green"], label="Geometric success")
    ax.barh(y, geometric_failure, left=success, color=COLORS["orange"], label="Completed, geometric failure")
    left = [success[i] + geometric_failure[i] for i in range(len(y))]
    ax.barh(y, execution_failure, left=left, color=COLORS["red"], label="Execution failure")
    ax.set_yticks(y, [str(row["method_id"]) for row in repeated])
    ax.invert_yaxis()
    ax.set_xlabel("Attempts (raw counts)")
    ax.set_title("Repeated-pattern outcomes by method")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    fig.text(0.5, 0.017, "36 attempts: 25 successes, 1 completed geometric failure, 10 execution failures; descriptive low counts", ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "repeated_pattern_outcomes.svg", preview_dir)

    availability = tables["similarity_geometry_availability.csv"][1]
    display_fields = [
        "mae",
        "mse",
        "ncc",
        "ssim",
        "mi_nats",
        "valid_overlap_fraction",
        "valid_geometric_reference",
        "tre_mean_px",
    ]
    rows = [next(row for row in availability if row["evidence_field"] == field) for field in display_fields]
    fig, ax = plt.subplots(figsize=(9.4, 5.8))
    y = list(range(len(rows)))
    values = [float(row["availability_fraction"]) for row in rows]
    colors = [COLORS["light_gray"]] * 6 + [COLORS["green"], COLORS["blue"]]
    ax.barh(y, values, color=colors)
    for index, row in enumerate(rows):
        ax.text(min(1.02, values[index] + 0.025), index, f"{row['available_count']}/{row['denominator']}", va="center", fontsize=8.5)
    ax.set_yticks(y, [str(row["evidence_field"]).replace("_", " ") for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Recorded availability")
    ax.set_title("Similarity–geometry disagreement audit: not estimable from sealed final records")
    ax.text(0.01, 0.02, "Common image-similarity fields: 0/294. Family-native objectives are noncommensurate and were not compared.", transform=ax.transAxes, fontsize=8, color=COLORS["gray"])
    _save_figure(fig, destination / "similarity_geometry_availability.svg", preview_dir)

    policy = tables["track_b_policy.csv"][1][0]
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    labels = ["Coverage", "Abstention"]
    prefixes = ["coverage", "abstention"]
    values = [float(policy[f"{prefix}_value"]) for prefix in prefixes]
    colors = [COLORS["blue"], COLORS["orange"]]
    for index, (label, prefix, value, color) in enumerate(zip(labels, prefixes, values, colors)):
        lower = float(policy[f"{prefix}_ci_lower"])
        upper = float(policy[f"{prefix}_ci_upper"])
        ax.bar(index, value, width=0.62, color=color)
        ax.errorbar(index, value, yerr=_rate_error(value, lower, upper), color=COLORS["navy"], capsize=5, lw=1.4)
        ax.text(index, min(1.075, upper + 0.04), _percent_label(value), ha="center", weight="bold")
        ax.text(index, 0.045 if value else 0.02, f"{policy[f'{prefix}_numerator']}/{policy[f'{prefix}_denominator']}", ha="center", color="white" if value else COLORS["navy"], weight="bold")
    ax.set_xticks(range(2), labels)
    ax.set_ylim(0, 1.13)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("Rate with Wilson 95% interval")
    ax.set_title("Track B: 24/24 abstentions and 0% coverage")
    ax.text(0.5, 0.50, "Selective correctness: N/A\n(0 selected pairs)", transform=ax.transAxes, ha="center", va="center", color=COLORS["gray"], fontsize=9)
    fig.text(0.5, 0.017, "Frozen policy remains non-deployed", ha="center", color=COLORS["gray"], fontsize=8)
    _save_figure(fig, destination / "track_b_policy.svg", preview_dir)


def verify_inputs(root: Path) -> dict[str, Any]:
    final_root = root / "outputs" / "week08_final"
    release_path = root / "reports" / "pre_week08_release_manifest.json"
    phase91_path = root / "reports" / "week08_phase9_data_quality_closure.json"
    summary_path = final_root / "evaluation_summary.json"
    records_path = final_root / "scientific_records.jsonl"
    seal_path = final_root / "decision_seal.json"
    audit_path = final_root / "label_access_audit.jsonl"

    release = load_json(release_path)
    phase91 = load_json(phase91_path)
    summary = load_json(summary_path)
    records = load_jsonl(records_path)
    seal = load_json(seal_path)
    audit = load_jsonl(audit_path)

    phase91_payload_hash = verify_payload_hash(phase91, "report_payload_sha256", "Phase 9.1 closure")
    seal_hash = verify_payload_hash(seal, "seal_sha256", "decision seal")
    require(phase91["status"] == "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW", "Phase 9.1 is not technically closed")
    require(release["status"] == "PHASE8_COMPLETED_ARCHIVED", "Phase 8 release is not closed")
    require(summary["final_evidence"] is True, "Summary is not final evidence")
    require(summary["no_post_label_change_attested"] is True, "Post-label change attestation failed")
    require(summary["decision_seal_sha256"] == seal_hash, "Summary/seal mismatch")
    require(len(audit) == 1, "Exactly one label-access event is required")

    expected_hashes = release["phase8_run"]["integrity"]["file_hashes"]
    input_paths = {
        "evaluation_summary": summary_path,
        "scientific_records": records_path,
        "decision_seal": seal_path,
        "label_access_audit": audit_path,
    }
    for semantic, path in input_paths.items():
        relative = path.relative_to(root).as_posix()
        require(expected_hashes.get(relative) == sha256_file(path), f"Sealed input hash mismatch: {semantic}")

    attempts = summary["track_a"]["attempts"]
    pairs = summary["track_b"]["pairs"]
    require(len(attempts) == 294 and len(records) == 294, "Track A count mismatch")
    require(len(pairs) == 24, "Track B count mismatch")
    require(summary["track_a"]["overall"]["geometric_successes"] == 278, "Track A success mismatch")
    require(summary["track_b"]["overall"]["abstained_pairs"] == 24, "Track B abstention mismatch")
    require(summary["recommendation_validation"]["outcome"] == "preserve_results_keep_policy_non_deployed", "Unexpected recommendation outcome")

    return {
        "release": release,
        "phase91": phase91,
        "phase91_payload_hash": phase91_payload_hash,
        "summary": summary,
        "records": records,
        "input_hashes": {
            "phase9_1_report_file_sha256": sha256_file(phase91_path),
            "phase9_1_report_payload_sha256": phase91_payload_hash,
            "release_manifest_file_sha256": sha256_file(release_path),
            "evaluation_summary_file_sha256": sha256_file(summary_path),
            "scientific_records_file_sha256": sha256_file(records_path),
            "decision_seal_file_sha256": sha256_file(seal_path),
            "label_access_audit_file_sha256": sha256_file(audit_path),
            "phase9_2_generator_sha256": sha256_file(Path(__file__)),
        },
    }


def validate_sanitized_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="strict")
    for pattern in PRIVATE_PATTERNS:
        require(pattern.search(text) is None, f"Private identifier/path leaked into {path.name}")
    if path.suffix.lower() == ".svg":
        require("<image" not in text.lower(), f"SVG embeds raster content: {path.name}")


def artifact_records(table_dir: Path, figure_dir: Path) -> list[dict[str, Any]]:
    roles = {
        "track_a_overall.csv": "track_a_completion_geometric_uncertainty_table",
        "track_a_by_modality.csv": "track_a_modality_comparison_table",
        "track_a_by_condition.csv": "track_a_condition_table",
        "track_a_runtime_by_method.csv": "track_a_runtime_distribution_table",
        "repeated_pattern_by_method.csv": "repeated_pattern_failure_table",
        "similarity_geometry_availability.csv": "similarity_geometry_availability_audit_table",
        "track_b_policy.csv": "track_b_policy_outcome_table",
        "track_a_overall_rates.svg": "track_a_completion_geometric_uncertainty_figure",
        "track_a_modality_rates.svg": "track_a_modality_comparison_figure",
        "track_a_condition_rates.svg": "track_a_condition_figure",
        "track_a_runtime_by_method.svg": "track_a_runtime_distribution_figure",
        "repeated_pattern_outcomes.svg": "repeated_pattern_failure_figure",
        "similarity_geometry_availability.svg": "similarity_geometry_availability_audit_figure",
        "track_b_policy.svg": "track_b_policy_outcome_figure",
    }
    records: list[dict[str, Any]] = []
    for name in TABLE_FILES:
        path = table_dir / name
        validate_sanitized_file(path)
        records.append(
            {
                "path": f"reports/week08_phase9_tables/{name}",
                "format": "csv",
                "role": roles[name],
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    for name in FIGURE_FILES:
        path = figure_dir / name
        validate_sanitized_file(path)
        records.append(
            {
                "path": f"docs/figures/week08_phase9/{name}",
                "format": "svg",
                "role": roles[name],
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def build_manifest(
    context: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    generated_utc: str,
) -> dict[str, Any]:
    datetime.fromisoformat(generated_utc.replace("Z", "+00:00"))
    release = context["release"]
    summary = context["summary"]
    overall_a = summary["track_a"]["overall"]
    overall_b = summary["track_b"]["overall"]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS_PENDING_SCIENTIFIC_AND_RELEASE_REVIEW",
        "identity": {
            "phase": "9.2",
            "work_package": "final_analysis",
            "generated_utc": generated_utc,
            "run_id": release["phase8_run"]["run_id"],
            "release_id": release["release_id"],
            "phase9_1_report_payload_sha256": context["phase91_payload_hash"],
        },
        "inputs": context["input_hashes"],
        "outputs": list(artifacts),
        "coverage": {
            "track_a_completion_and_geometric_success": [
                "reports/week08_phase9_tables/track_a_overall.csv",
                "docs/figures/week08_phase9/track_a_overall_rates.svg",
            ],
            "runtime_and_uncertainty": [
                "reports/week08_phase9_tables/track_a_runtime_by_method.csv",
                "docs/figures/week08_phase9/track_a_runtime_by_method.svg",
            ],
            "modality_comparison": [
                "reports/week08_phase9_tables/track_a_by_modality.csv",
                "docs/figures/week08_phase9/track_a_modality_rates.svg",
            ],
            "condition_behavior": [
                "reports/week08_phase9_tables/track_a_by_condition.csv",
                "docs/figures/week08_phase9/track_a_condition_rates.svg",
            ],
            "repeated_pattern_failures": [
                "reports/week08_phase9_tables/repeated_pattern_by_method.csv",
                "docs/figures/week08_phase9/repeated_pattern_outcomes.svg",
            ],
            "similarity_versus_geometry": [
                "reports/week08_phase9_tables/similarity_geometry_availability.csv",
                "docs/figures/week08_phase9/similarity_geometry_availability.svg",
            ],
            "track_b_policy": [
                "reports/week08_phase9_tables/track_b_policy.csv",
                "docs/figures/week08_phase9/track_b_policy.svg",
            ],
        },
        "findings": {
            "track_a": {
                "attempts": overall_a["planned_attempts"],
                "completed": overall_a["status_counts"]["completed"],
                "failed": overall_a["status_counts"]["failed"],
                "geometric_successes": overall_a["geometric_successes"],
                "execution_completion_rate": overall_a["execution_completion_rate"],
                "geometric_success_rate": overall_a["geometric_success_rate"],
                "conditional_accuracy": overall_a["conditional_accuracy"],
            },
            "repeated_pattern": {
                "attempts": 36,
                "completed": 26,
                "execution_failures": 10,
                "geometric_successes": 25,
                "completed_geometric_failures": 1,
            },
            "similarity_geometry_disagreement": {
                "status": "NOT_EVALUABLE_FROM_SEALED_FINAL_RECORDS",
                "common_similarity_fields_available": 0,
                "attempt_denominator": 294,
                "reason": "common MAE, MSE, NCC, SSIM, MI, and overlap were not recorded; family-native objectives are noncommensurate",
            },
            "track_b": {
                "eligible_pairs": overall_b["eligible_pairs"],
                "selected_pairs": overall_b["selected_pairs"],
                "abstained_pairs": overall_b["abstained_pairs"],
                "coverage": overall_b["coverage"],
                "abstention_rate": overall_b["abstention_rate"],
                "selective_correctness": overall_b["selective_correctness"],
                "recommendation_disposition": summary["recommendation_validation"]["outcome"],
            },
        },
        "analysis_contract": {
            "registration_or_evaluation_rerun": False,
            "source_pixels_or_prepared_arrays_opened": False,
            "sealed_label_content_opened": False,
            "post_label_threshold_or_policy_change": False,
            "raw_method_objectives_compared_across_families": False,
            "wilson_intervals_reused_from_sealed_summary": True,
            "runtime_scope": "recorded_total_runtime_ms_single_environment",
            "runtime_intervals_are_distribution_summaries_not_confidence_intervals": True,
        },
        "privacy": {
            "classification": "tracked_sanitized_aggregate",
            "contains_source_pair_or_attempt_identifiers": False,
            "contains_pixels_arrays_labels_transforms_or_diagnostic_traces": False,
            "contains_private_archive_inventory": False,
        },
        "claim_scope": {
            "scope": "source_specific_software_evidence_only",
            "prohibited_claims": PROHIBITED_CLAIMS,
            "policy_status": "non_deployed",
        },
        "review": {
            "developer_analyst": {"status": "COMPLETE"},
            "scientific_reviewer": {"status": "PENDING"},
            "release_reviewer": {"status": "PENDING"},
        },
        "limitations": [
            "One independent source does not provide independent source replication or external validity.",
            "Synthetic-after-freeze ground truth supports source-specific software evaluation, not anatomical or clinical claims.",
            "The 294 attempts are correlated cases from one source and must not be treated as 294 independent source samples.",
            "Runtime is descriptive for one recorded environment; median and p95 are distribution summaries, not confidence intervals.",
            "Common post-registration similarity evidence was not sealed, so similarity-versus-geometry disagreement is not estimable rather than zero.",
            "Track B selected no pairs; selective correctness is undefined, not zero.",
        ],
        "next": "Phase 9.3 documentation: update README, reproduction guide, maintained gate register, and progress registry without changing frozen methods or policy.",
    }
    manifest["manifest_payload_sha256"] = canonical_sha256(manifest)
    return manifest


def generate_bundle(
    root: Path,
    table_dir: Path,
    figure_dir: Path,
    *,
    generated_utc: str,
    preview_dir: Path | None = None,
) -> dict[str, Any]:
    context = verify_inputs(root)
    tables = build_tables(context["summary"], context["records"])
    require(set(tables) == set(TABLE_FILES), "Unexpected table set")
    for name in TABLE_FILES:
        columns, rows = tables[name]
        write_csv(table_dir / name, columns, rows)
    build_figures(tables, figure_dir, preview_dir)
    artifacts = artifact_records(table_dir, figure_dir)
    require(len(artifacts) == len(TABLE_FILES) + len(FIGURE_FILES), "Artifact count mismatch")
    return build_manifest(context, artifacts, generated_utc)


def verify_bundle(root: Path, manifest_path: Path) -> dict[str, Any]:
    recorded = load_json(manifest_path)
    validate_sanitized_file(manifest_path)
    verify_payload_hash(recorded, "manifest_payload_sha256", "Phase 9.2 manifest")
    generated_utc = recorded["identity"]["generated_utc"]
    with tempfile.TemporaryDirectory(prefix="week08-phase9-check-") as temporary:
        temp = Path(temporary)
        table_dir = temp / "tables"
        figure_dir = temp / "figures"
        expected = generate_bundle(
            root,
            table_dir,
            figure_dir,
            generated_utc=generated_utc,
        )
        require(recorded == expected, "Tracked Phase 9.2 manifest differs from sealed evidence")
        for name in TABLE_FILES:
            require((root / "reports/week08_phase9_tables" / name).read_bytes() == (table_dir / name).read_bytes(), f"Table is not reproducible: {name}")
        for name in FIGURE_FILES:
            require((root / "docs/figures/week08_phase9" / name).read_bytes() == (figure_dir / name).read_bytes(), f"Figure is not reproducible: {name}")
    return recorded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="Write tracked tables, figures, and manifest")
    parser.add_argument("--check", action="store_true", help="Rebuild privately and verify every tracked byte")
    parser.add_argument("--generated-utc", help="UTC timestamp for initial generation")
    parser.add_argument("--preview-dir", type=Path, help="Optional ignored PNG preview directory")
    args = parser.parse_args(argv)
    if args.write and args.check:
        parser.error("--write and --check are mutually exclusive")
    if not args.write and not args.check:
        parser.error("choose exactly one of --write or --check")
    root = args.root.resolve()
    manifest_path = root / "reports/week08_phase9_final_analysis.json"
    if args.check:
        manifest = verify_bundle(root, manifest_path)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "manifest_payload_sha256": manifest["manifest_payload_sha256"],
                    "artifact_count": len(manifest["outputs"]),
                },
                indent=2,
            )
        )
        return 0
    generated_utc = args.generated_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    table_dir = root / "reports/week08_phase9_tables"
    figure_dir = root / "docs/figures/week08_phase9"
    preview_dir = None if args.preview_dir is None else (
        args.preview_dir if args.preview_dir.is_absolute() else root / args.preview_dir
    )
    manifest = generate_bundle(
        root,
        table_dir,
        figure_dir,
        generated_utc=generated_utc,
        preview_dir=preview_dir,
    )
    if args.write:
        write_json(manifest_path, manifest)
        validate_sanitized_file(manifest_path)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "artifact_count": len(manifest["outputs"]),
                "write": bool(args.write),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
