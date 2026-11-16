"""Record and reproduce the Week 8 Phase 9 scientific-review finding.

This is a reporting-only audit.  It reads the frozen configuration, frozen
evaluator source, tracked Phase 9 manifests, and the aggregate sealed
evaluation summary.  It does not decode source images, prepared arrays, or
label payloads, and it never executes registration or evaluation.

The generated supplement is deliberately versioned beside, rather than over,
the immutable Phase 8, Phase 9.1, and Phase 9.2 evidence.
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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs/week08_final/evaluation_summary.json"
FINDING = ROOT / "reports/week08_phase9_scientific_review_finding.json"
TABLE_DIR = ROOT / "reports/week08_phase9_review_tables"
SCHEMA_VERSION = "week08_phase9_scientific_review_finding_v1"
REVIEWED_COMMIT = "8bbe782247dec025a95e34cbae9b4ff075e66d0f"

TABLE_FILES = (
    "wilson_interval_erratum.csv",
    "track_a_mandatory_strata.csv",
    "track_b_mandatory_strata.csv",
    "track_a_endpoint_distributions.csv",
    "pairwise_exact_mcnemar.csv",
)

EXPECTED_HASHES = {
    "configs/week08_final_evaluation.yaml": "a2327b09c6896c4a8c7a8d8c03e10690d9d8b71efdd28b391ce00bf2fa0e0893",
    "src/image_registration/week8_evaluation.py": "9f1846bda8d7835cb510ed9b88b315b7449d5239de06b0d08cb8d2e7d56e5b31",
    "src/image_registration/week7_calibration.py": "44fec86c2acde61c0f908871fe532440d67a364cc524a76782d576a19218ee5c",
    "scripts/week08_final_evaluation.py": "6e2168d453f8bd5867c19e1e650b8a40c5fa60c4b2baa673f60a251bfb6ba2fe",
    "reports/pre_week08_release_manifest.json": "93eecca7de8fc4eee43d02d33a0f9bbfe921fbd5fb52f34164d5ef51bc3e7db7",
    "reports/week08_phase9_data_quality_closure.json": "04cb0faa2ecbc9baab5d119564b4c503ac54a2681eb513654b7e50b0ec98c4d8",
    "reports/week08_phase9_final_analysis.json": "af254c646c8cfde6d37904173ff0b1cf74454e895b51d9c552e5371e8bd807a7",
    "outputs/week08_final/evaluation_summary.json": "d83e1a23ccae29d7e40d090384d2ba8b2eff24c6d25fe1d234bffacc5bd88fd4",
}

EXPECTED_PAYLOAD_HASHES = {
    "phase9_1": "e1ebf2d2e7fec780e61048c1d19dc7f7ddad966f65057efd7a920acdc3b8f77f",
    "phase9_2": "c604685fe41686f303d330bd58febfd36363af1b6f81eb3b48e368c6eb44d0bb",
}

MANDATORY_STRATA = (
    "modality_class",
    "transform_model",
    "condition",
    "severity",
    "source_role",
    "source_id",
)

TRACK_A_RATES = (
    "execution_completion_rate",
    "geometric_success_rate",
    "conditional_accuracy",
    "infrastructure_incident_rate",
)

TRACK_B_RATES = (
    "coverage",
    "abstention_rate",
    "invalid_rate",
    "missing_decision_rate",
    "selective_correctness",
)

PROHIBITED_CLAIMS = (
    "anatomical_generalization",
    "calibrated_confidence",
    "clinical_recommendation",
    "cross_source_generalization",
    "external_validity",
    "modality_wide_generalization",
    "population_generalization",
)

PRIVATE_PATTERNS = (
    re.compile(r"\bw8-[0-9a-f]+\b", re.IGNORECASE),
    re.compile(r"\bfinal-[0-9a-f]+\b", re.IGNORECASE),
    re.compile(r"\bpia\d{4,}\b", re.IGNORECASE),
    re.compile(r"nasa_pia", re.IGNORECASE),
    re.compile(r"sealed_labels", re.IGNORECASE),
    re.compile(r"labels\.json", re.IGNORECASE),
    re.compile(r"\.npy", re.IGNORECASE),
)


class ScientificReviewError(ValueError):
    """Raised when the finding cannot be reproduced safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScientificReviewError(message)


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
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def verify_payload_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    payload = dict(value)
    recorded = payload.pop(field, None)
    require(isinstance(recorded, str), f"{label} lacks {field}")
    require(canonical_sha256(payload) == recorded, f"{label} self-hash mismatch")
    return recorded


def wilson_interval(successes: int, denominator: int, z: float) -> tuple[float | None, float | None]:
    if denominator == 0:
        return None, None
    require(0 <= successes <= denominator, f"Invalid rate {successes}/{denominator}")
    proportion = successes / denominator
    z2 = z * z
    centre = (proportion + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = z * math.sqrt(
        proportion * (1 - proportion) / denominator
        + z2 / (4 * denominator * denominator)
    ) / (1 + z2 / denominator)
    lower = 0.0 if successes == 0 else max(0.0, centre - half)
    upper = 1.0 if successes == denominator else min(1.0, centre + half)
    return lower, upper


def round6(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


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
    require(bool(rows), f"Refusing to write empty table: {path.name}")
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
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_sanitized_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern in PRIVATE_PATTERNS:
        require(pattern.search(text) is None, f"Private identifier in {path}: {pattern.pattern}")


def safe_stratum(dimension: str, row: Mapping[str, Any]) -> str:
    if dimension == "source_id":
        return "enrolled_source_1"
    return str(row[dimension])


def parse_frozen_z(path: Path) -> float:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*z_value:\s*([0-9.]+)\s*$", text)
    require(match is not None, "Frozen z_value is missing")
    return float(match.group(1))


def numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    numeric = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
    if not numeric:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "mean": None,
            "p95": None,
            "maximum": None,
        }

    def quantile(fraction: float) -> float:
        position = (len(numeric) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return numeric[lower]
        weight = position - lower
        return numeric[lower] * (1 - weight) + numeric[upper] * weight

    return {
        "count": len(numeric),
        "minimum": numeric[0],
        "median": quantile(0.5),
        "mean": sum(numeric) / len(numeric),
        "p95": quantile(0.95),
        "maximum": numeric[-1],
    }


def status_count(row: Mapping[str, Any], status: str) -> int:
    counts = row.get("status_counts", {})
    return int(counts.get(status, 0)) if isinstance(counts, Mapping) else 0


def exact_interval_fields(prefix: str, rate: Mapping[str, Any], z: float) -> dict[str, Any]:
    numerator = int(rate["numerator"])
    denominator = int(rate["denominator"])
    lower, upper = wilson_interval(numerator, denominator, z)
    return {
        f"{prefix}_numerator": numerator,
        f"{prefix}_denominator": denominator,
        f"{prefix}_value": rate["value"],
        f"{prefix}_ci_lower": round6(lower),
        f"{prefix}_ci_upper": round6(upper),
        f"{prefix}_ci_method": "wilson_95_z_1.959963984540054",
    }


def verify_context(root: Path) -> dict[str, Any]:
    for relative, expected in EXPECTED_HASHES.items():
        path = root / relative
        require(path.is_file(), f"Required evidence is unavailable: {relative}")
        require(sha256_file(path) == expected, f"Immutable binding changed: {relative}")

    phase91 = load_json(root / "reports/week08_phase9_data_quality_closure.json")
    phase92 = load_json(root / "reports/week08_phase9_final_analysis.json")
    require(
        verify_payload_hash(phase91, "report_payload_sha256", "Phase 9.1 report")
        == EXPECTED_PAYLOAD_HASHES["phase9_1"],
        "Unexpected Phase 9.1 payload",
    )
    require(
        verify_payload_hash(phase92, "manifest_payload_sha256", "Phase 9.2 manifest")
        == EXPECTED_PAYLOAD_HASHES["phase9_2"],
        "Unexpected Phase 9.2 payload",
    )
    for artifact in phase92["outputs"]:
        path = root / artifact["path"]
        require(path.is_file(), f"Historical Phase 9.2 artifact missing: {artifact['path']}")
        require(sha256_file(path) == artifact["sha256"], f"Historical artifact changed: {artifact['path']}")

    config = root / "configs/week08_final_evaluation.yaml"
    frozen_z = parse_frozen_z(config)
    require(frozen_z == 1.959963984540054, "Unexpected frozen Wilson quantile")

    evaluator = (root / "src/image_registration/week8_evaluation.py").read_text(encoding="utf-8")
    evaluator_lines = evaluator.splitlines()
    wilson_calls = [
        index for index, line in enumerate(evaluator_lines, 1) if "wilson_interval(" in line
    ]
    require(wilson_calls == [1739, 1900, 2379], "Wilson call-site audit changed")
    require(
        all("z=" not in evaluator_lines[index - 1] for index in wilson_calls),
        "A frozen z is now passed at an audited historical call site",
    )
    helper = (root / "src/image_registration/week7_calibration.py").read_text(encoding="utf-8")
    require(
        "def wilson_interval(successes: int, n: int, z: float = 1.96)" in helper,
        "Historical Wilson helper default changed",
    )
    require(
        '"no_firewall_or_integrity_incident": True' in evaluator,
        "Recommendation integrity finding no longer matches reviewed source",
    )
    cli = (root / "scripts/week08_final_evaluation.py").read_text(encoding="utf-8")
    require(
        "no_post_label_change_attested=True" in cli,
        "Post-label attestation finding no longer matches reviewed source",
    )

    summary = load_json(root / "outputs/week08_final/evaluation_summary.json")
    overall_a = summary["track_a"]["overall"]
    overall_b = summary["track_b"]["overall"]
    require(overall_a["planned_attempts"] == 294, "Unexpected Track A denominator")
    require(status_count(overall_a, "completed") == 284, "Unexpected completed count")
    require(status_count(overall_a, "failed") == 10, "Unexpected failed count")
    require(overall_a["geometric_successes"] == 278, "Unexpected geometric success count")
    require(overall_b["eligible_pairs"] == 24, "Unexpected Track B denominator")
    require(overall_b["selected_pairs"] == 0 and overall_b["abstained_pairs"] == 24, "Unexpected Track B decision counts")
    require(overall_b["invalid_pairs"] == 0 and overall_b["missing_decision_pairs"] == 0, "Unexpected Track B terminal counts")
    require(summary["recommendation_validation"]["outcome"] == "preserve_results_keep_policy_non_deployed", "Unexpected recommendation outcome")
    require(set(summary["track_a"]["strata"]) == set(MANDATORY_STRATA), "Track A sealed strata changed")
    require(set(summary["track_b"]["strata"]) == set(MANDATORY_STRATA), "Track B sealed strata changed")

    return {
        "summary": summary,
        "phase91": phase91,
        "phase92": phase92,
        "frozen_z": frozen_z,
        "wilson_call_lines": wilson_calls,
    }


def sealed_interval_records(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    top_rates = {
        "execution_completion_rate": summary["track_a"]["overall"]["execution_completion_rate"],
        "geometric_success_rate": summary["track_a"]["overall"]["geometric_success_rate"],
        "conditional_accuracy": summary["track_a"]["overall"]["conditional_accuracy"],
        "infrastructure_incident_rate": summary["track_a"]["overall"]["infrastructure_incident_rate"],
        "policy_coverage": summary["track_b"]["overall"]["coverage"],
        "policy_selective_correctness": summary["track_b"]["overall"]["selective_correctness"],
        "policy_abstention_rate": summary["track_b"]["overall"]["abstention_rate"],
    }
    for metric, rate in top_rates.items():
        output.append({"location": "overall", "metric": metric, "rate": rate, "stored": summary["uncertainty"][metric]})

    for dimension in MANDATORY_STRATA:
        for row in summary["track_a"]["strata"][dimension]:
            for metric in TRACK_A_RATES:
                output.append({
                    "location": f"track_a.{dimension}.{safe_stratum(dimension, row)}",
                    "metric": metric,
                    "rate": row[metric],
                    "stored": row["uncertainty"][metric],
                })
        for row in summary["track_b"]["strata"][dimension]:
            for metric in TRACK_B_RATES:
                output.append({
                    "location": f"track_b.{dimension}.{safe_stratum(dimension, row)}",
                    "metric": metric,
                    "rate": row[metric],
                    "stored": row["uncertainty"][metric],
                })
    return output


def interval_impact(summary: Mapping[str, Any], frozen_z: float) -> dict[str, int]:
    records = sealed_interval_records(summary)
    defined = 0
    undefined = 0
    mathematical_records = 0
    serialized_records = 0
    serialized_endpoints = 0
    for item in records:
        rate = item["rate"]
        denominator = int(rate["denominator"])
        if denominator == 0:
            undefined += 1
            continue
        defined += 1
        exact = wilson_interval(int(rate["numerator"]), denominator, frozen_z)
        used = wilson_interval(int(rate["numerator"]), denominator, 1.96)
        changed_math = [left != right for left, right in zip(exact, used)]
        mathematical_records += int(any(changed_math))
        stored = (item["stored"]["lower"], item["stored"]["upper"])
        changed_serialized = [round6(value) != old for value, old in zip(exact, stored)]
        serialized_endpoints += sum(changed_serialized)
        serialized_records += int(any(changed_serialized))

    result = {
        "total_interval_records": len(records),
        "defined_interval_records": defined,
        "undefined_zero_denominator_records": undefined,
        "mathematically_changed_records": mathematical_records,
        "changed_records_at_6_decimals": serialized_records,
        "changed_endpoints_at_6_decimals": serialized_endpoints,
    }
    require(result == {
        "total_interval_records": 157,
        "defined_interval_records": 142,
        "undefined_zero_denominator_records": 15,
        "mathematically_changed_records": 142,
        "changed_records_at_6_decimals": 132,
        "changed_endpoints_at_6_decimals": 141,
    }, f"Unexpected sealed interval impact: {result}")
    return result


def public_interval_rows(summary: Mapping[str, Any], frozen_z: float) -> list[dict[str, Any]]:
    sources: list[tuple[str, str, Mapping[str, Any], Sequence[str]]] = [
        ("track_a_overall.csv", "overall", summary["track_a"]["overall"], TRACK_A_RATES[:3]),
    ]
    for dimension, table in (
        ("modality_class", "track_a_by_modality.csv"),
        ("condition", "track_a_by_condition.csv"),
    ):
        for row in summary["track_a"]["strata"][dimension]:
            sources.append((table, safe_stratum(dimension, row), row, TRACK_A_RATES[:3]))
    sources.append(("track_b_policy.csv", "overall", summary["track_b"]["overall"], ("coverage", "abstention_rate")))
    for row in summary["track_b"]["strata"]["condition"]:
        sources.append(("track_b_policy.csv", safe_stratum("condition", row), row, ("coverage", "abstention_rate")))

    rows: list[dict[str, Any]] = []
    for table, scope, source, metrics in sources:
        for metric in metrics:
            rate = source[metric]
            stored = (
                summary["uncertainty"]["policy_" + metric]
                if table == "track_b_policy.csv" and scope == "overall"
                else summary["uncertainty"][metric]
                if table == "track_a_overall.csv"
                else source["uncertainty"][metric]
            )
            lower, upper = wilson_interval(int(rate["numerator"]), int(rate["denominator"]), frozen_z)
            corrected = (round6(lower), round6(upper))
            existing = (stored["lower"], stored["upper"])
            rows.append({
                "historical_table": table,
                "scope": scope,
                "metric": metric,
                "numerator": int(rate["numerator"]),
                "denominator": int(rate["denominator"]),
                "point_estimate": rate["value"],
                "historical_lower_z_1_96": existing[0],
                "historical_upper_z_1_96": existing[1],
                "corrected_lower_z_1_959963984540054": corrected[0],
                "corrected_upper_z_1_959963984540054": corrected[1],
                "changed_at_6_decimals": existing != corrected,
            })
    require(len(rows) == 54, "Unexpected public interval count")
    require(sum(row["changed_at_6_decimals"] for row in rows) == 52, "Unexpected changed public interval count")
    endpoint_changes = sum(
        int(row["historical_lower_z_1_96"] != row["corrected_lower_z_1_959963984540054"])
        + int(row["historical_upper_z_1_96"] != row["corrected_upper_z_1_959963984540054"])
        for row in rows
    )
    require(endpoint_changes == 57, "Unexpected public endpoint impact")
    return rows


def track_a_strata_rows(summary: Mapping[str, Any], frozen_z: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in MANDATORY_STRATA:
        for source in summary["track_a"]["strata"][dimension]:
            row: dict[str, Any] = {
                "dimension": "source_identity" if dimension == "source_id" else dimension,
                "stratum": safe_stratum(dimension, source),
                "interpretation": source["interpretation"],
                "attempts": source["attempts"],
                "completed": status_count(source, "completed"),
                "check": status_count(source, "CHECK"),
                "failed": status_count(source, "failed"),
                "valid_gt_attempts": source["valid_gt_attempts"],
                "geometric_successes": source["geometric_successes"],
                "total_runtime_count": source["total_runtime_ms"]["count"],
                "total_runtime_median_ms": source["total_runtime_ms"]["median"],
                "total_runtime_p95_ms": source["total_runtime_ms"]["p95"],
                "method_runtime_count": source["method_runtime_ms"]["count"],
                "valid_overlap_count": source["valid_overlap_fraction"]["count"],
            }
            for metric in TRACK_A_RATES:
                row.update(exact_interval_fields(metric, source[metric], frozen_z))
            rows.append(row)
    require(len(rows) == 20, "Unexpected Track A mandatory-stratum count")
    return rows


def track_b_strata_rows(summary: Mapping[str, Any], frozen_z: float) -> list[dict[str, Any]]:
    sources: list[tuple[str, str, Mapping[str, Any], str]] = [
        ("overall", "overall", summary["track_b"]["overall"], "preregistered_overall")
    ]
    for dimension in MANDATORY_STRATA:
        for row in summary["track_b"]["strata"][dimension]:
            sources.append((
                "source_identity" if dimension == "source_id" else dimension,
                safe_stratum(dimension, row),
                row,
                row["interpretation"],
            ))
    rows: list[dict[str, Any]] = []
    for dimension, stratum, source, interpretation in sources:
        row: dict[str, Any] = {
            "dimension": dimension,
            "stratum": stratum,
            "interpretation": interpretation,
            "eligible_pairs": source["eligible_pairs"],
            "selected_pairs": source["selected_pairs"],
            "abstained_pairs": source["abstained_pairs"],
            "invalid_pairs": source["invalid_pairs"],
            "missing_decision_pairs": source["missing_decision_pairs"],
            "correct_selected_pairs": source["correct_selected_pairs"],
        }
        for metric in TRACK_B_RATES:
            row.update(exact_interval_fields(metric, source[metric], frozen_z))
        rows.append(row)
    require(len(rows) == 15, "Unexpected Track B overall/mandatory-stratum count")
    return rows


def endpoint_distribution_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    attempts = summary["track_a"]["attempts"]
    groups: list[tuple[str, str, list[Mapping[str, Any]]]] = [("overall", "overall", list(attempts))]
    for dimension in MANDATORY_STRATA:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for attempt in attempts:
            grouped[safe_stratum(dimension, attempt)].append(attempt)
        groups.extend(
            ("source_identity" if dimension == "source_id" else dimension, stratum, grouped[stratum])
            for stratum in sorted(grouped)
        )

    endpoints = (
        "tre_mean_px",
        "tre_median_px",
        "tre_p95_px",
        "total_runtime_ms",
        "method_runtime_ms",
        "valid_overlap_fraction",
    )
    rows: list[dict[str, Any]] = []
    for dimension, stratum, group in groups:
        row: dict[str, Any] = {
            "dimension": dimension,
            "stratum": stratum,
            "attempts": len(group),
            "completed": sum(attempt["execution_status"] == "completed" for attempt in group),
        }
        for endpoint in endpoints:
            stats = numeric_summary(attempt.get(endpoint) for attempt in group)
            for name, value in stats.items():
                row[f"{endpoint}_{name}"] = value
        rows.append(row)
    require(len(rows) == 21, "Unexpected endpoint-distribution row count")
    overall = rows[0]
    require(overall["total_runtime_ms_count"] == 294, "Total runtime availability changed")
    require(overall["method_runtime_ms_count"] == 0, "Method runtime finding changed")
    require(overall["valid_overlap_fraction_count"] == 0, "Valid-overlap finding changed")
    require(overall["tre_mean_px_count"] == overall["tre_median_px_count"] == overall["tre_p95_px_count"] == 284, "TRE availability changed")
    return rows


def pairwise_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in summary["track_a"]["pairwise_method_comparisons"]:
        method_a = str(source["method_a"]).split("::", 1)[0]
        method_b = str(source["method_b"]).split("::", 1)[0]
        rows.append({
            "method_a": method_a,
            "method_b": method_b,
            "common_denominator": source["common_denominator"],
            "both_success": source["both_success"],
            "method_a_only_success": source["method_a_only_success"],
            "method_b_only_success": source["method_b_only_success"],
            "both_failure": source["both_failure"],
            "method_a_successes": source["method_a_successes"],
            "method_b_successes": source["method_b_successes"],
            "mcnemar_exact_two_sided_p": source["mcnemar_exact_two_sided_p"],
            "interpretation": "descriptive_paired_comparison_not_a_universal_ranking",
        })
    require(len(rows) == 9, "Unexpected exact-McNemar comparison count")
    require(sum(row["mcnemar_exact_two_sided_p"] == 0.25 for row in rows) == 3, "Unexpected p=0.25 count")
    require(sum(row["mcnemar_exact_two_sided_p"] == 1.0 for row in rows) == 6, "Unexpected p=1.0 count")
    return rows


def build_tables(context: Mapping[str, Any]) -> dict[str, tuple[list[str], list[dict[str, Any]]]]:
    summary = context["summary"]
    z = context["frozen_z"]
    interval_rows = public_interval_rows(summary, z)
    track_a_rows = track_a_strata_rows(summary, z)
    track_b_rows = track_b_strata_rows(summary, z)
    endpoint_rows = endpoint_distribution_rows(summary)
    mcnemar_rows = pairwise_rows(summary)
    return {
        "wilson_interval_erratum.csv": (list(interval_rows[0]), interval_rows),
        "track_a_mandatory_strata.csv": (list(track_a_rows[0]), track_a_rows),
        "track_b_mandatory_strata.csv": (list(track_b_rows[0]), track_b_rows),
        "track_a_endpoint_distributions.csv": (list(endpoint_rows[0]), endpoint_rows),
        "pairwise_exact_mcnemar.csv": (list(mcnemar_rows[0]), mcnemar_rows),
    }


def artifact_records(directory: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name in TABLE_FILES:
        path = directory / name
        with path.open(encoding="utf-8", newline="") as stream:
            rows = sum(1 for _ in csv.DictReader(stream))
        output.append({
            "path": f"reports/week08_phase9_review_tables/{name}",
            "format": "csv",
            "rows": rows,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return output


def build_finding(context: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]], recorded_utc: str) -> dict[str, Any]:
    summary = context["summary"]
    impact = interval_impact(summary, context["frozen_z"])
    attempts = summary["track_a"]["attempts"]
    endpoint_availability = {
        name: sum(
            isinstance(row.get(name), (int, float))
            and not isinstance(row.get(name), bool)
            and math.isfinite(float(row[name]))
            for row in attempts
        )
        for name in (
            "total_runtime_ms",
            "method_runtime_ms",
            "tre_mean_px",
            "tre_median_px",
            "tre_p95_px",
            "valid_overlap_fraction",
        )
    }
    finding: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "CONFIRMATORY_RUN_INVALID_IMPLEMENTATION_NONCONFORMANCE",
        "identity": {
            "finding_id": "week08-phase9-scientific-review-20261116",
            "recorded_utc": recorded_utc,
            "reviewed_commit": REVIEWED_COMMIT,
            "release_id": "pre-week08-g5r2-20261115",
            "run_id": "week08-final-r2-20261115T154035Z",
        },
        "immutable_bindings": {
            "files": dict(sorted(EXPECTED_HASHES.items())),
            "audit_generator_sha256": sha256_file(Path(__file__)),
            "phase9_1_payload_sha256": EXPECTED_PAYLOAD_HASHES["phase9_1"],
            "phase9_2_payload_sha256": EXPECTED_PAYLOAD_HASHES["phase9_2"],
            "historical_phase9_2_artifacts_verified": len(context["phase92"]["outputs"]),
            "historical_artifacts_modified": False,
        },
        "findings": {
            "frozen_wilson_quantile_not_used": {
                "severity": "confirmatory_blocker",
                "expected_z": context["frozen_z"],
                "observed_helper_default_z": 1.96,
                "evaluator_call_lines_omitting_z": context["wilson_call_lines"],
                "sealed_impact": impact,
                "public_phase9_2_impact": {
                    "displayed_intervals": 54,
                    "changed_intervals_at_6_decimals": 52,
                    "changed_endpoints_at_6_decimals": 57,
                    "affected_csv_files": 4,
                    "affected_svg_files": 4,
                    "markdown_percentages_changed_at_2_decimals": False,
                },
            },
            "frozen_secondary_endpoints_not_captured": {
                "severity": "preregistration_nonconformance",
                "attempt_denominator": 294,
                "availability": endpoint_availability,
                "retroactive_calculation_permitted": False,
            },
            "recommendation_integrity_checks_not_evidence_derived": {
                "severity": "latent_enforcement_defect",
                "no_firewall_or_integrity_incident": "hardcoded_true",
                "no_post_label_change": "cli_passed_true_unconditionally",
                "outcome_changed": False,
                "reason_outcome_unchanged": "minimum selected pairs, coverage, selective correctness, and selective-correctness lower-bound gates all failed",
            },
            "phase9_reporting_omissions": {
                "severity": "release_blocker",
                "missing_phase9_2_mandatory_stratum_rows": 15,
                "missing_phase9_1_strata": ["severity", "source_identity"],
                "missing_exact_mcnemar_comparisons": 9,
                "missing_tre_endpoint_distribution_reporting": True,
                "supplement_status": "COMPLETE_VERSIONED_REPORTING_ONLY",
            },
        },
        "unaffected_outcomes": {
            "track_a": {
                "planned_attempts": 294,
                "completed_attempts": 284,
                "failed_attempts": 10,
                "geometric_successes": 278,
            },
            "track_b": {
                "eligible_pairs": 24,
                "selected_pairs": 0,
                "abstained_pairs": 24,
                "invalid_pairs": 0,
                "missing_decision_pairs": 0,
                "coverage": 0.0,
                "selective_correctness": None,
            },
            "recommendation_disposition": "preserve_results_keep_policy_non_deployed",
            "policy_status": "non_deployed",
            "registration_transforms_or_terminal_classifications_changed": False,
            "pre_label_policy_decisions_changed": False,
        },
        "supplement": {
            "purpose": "versioned deterministic correction and completion of aggregate reporting from immutable sealed records",
            "artifacts": list(artifacts),
            "registration_or_evaluation_rerun": False,
            "source_pixels_or_prepared_arrays_opened": False,
            "sealed_label_payload_opened": False,
            "new_registration_or_geometric_endpoint_computation": False,
            "reporting_only_interval_recalculation": True,
            "restores_confirmatory_validity": False,
        },
        "disposition": {
            "phase8_execution_status": "completed_archived",
            "confirmatory_status": "invalid",
            "retained_evidence_scope": "source_specific_nonconfirmatory_software_evidence_only",
            "same_holdout_corrected_confirmatory_rerun_permitted": False,
            "fresh_unexposed_holdout_required_for_corrected_confirmatory_claim": True,
            "frozen_evaluator_and_enforcement_must_be_corrected_before_new_g5": True,
            "g8_status": "BLOCKED",
            "release_review_status": "BLOCKED_BY_SCIENTIFIC_AUDIT",
        },
        "review": {
            "automated_scientific_audit": "FAIL",
            "named_human_scientific_attestation": "NOT_RECORDED",
            "named_human_release_attestation": "NOT_RECORDED",
        },
        "privacy": {
            "classification": "tracked_sanitized_aggregate",
            "contains_source_pair_or_attempt_identifiers": False,
            "contains_pixels_arrays_labels_transforms_or_diagnostic_traces": False,
            "source_identity_stratum": "sanitized_as_enrolled_source_1",
        },
        "claim_scope": {
            "approved_scope": "source_specific_nonconfirmatory_software_evidence_only",
            "prohibited_claims": list(PROHIBITED_CLAIMS),
        },
        "protocol_basis": {
            "post_label_defect_rule": "docs/PRE_WEEK08_INTEGRATION_PLAN.md:760",
            "versioned_reporting_correction_rule": "docs/PRE_WEEK08_INTEGRATION_PLAN.md:878-880",
        },
        "next": "Correct and test the evaluator and evidence-derived recommendation gates before a new G5/G6/G7 cycle; reserve a new unexposed holdout before any corrected confirmatory run.",
    }
    finding["finding_payload_sha256"] = canonical_sha256(finding)
    return finding


def generate_bundle(root: Path, table_dir: Path, *, recorded_utc: str) -> dict[str, Any]:
    context = verify_context(root)
    tables = build_tables(context)
    require(set(tables) == set(TABLE_FILES), "Unexpected supplement table set")
    for name in TABLE_FILES:
        columns, rows = tables[name]
        write_csv(table_dir / name, columns, rows)
        validate_sanitized_file(table_dir / name)
    artifacts = artifact_records(table_dir)
    return build_finding(context, artifacts, recorded_utc)


def verify_bundle(root: Path, finding_path: Path) -> dict[str, Any]:
    recorded = load_json(finding_path)
    verify_payload_hash(recorded, "finding_payload_sha256", "scientific-review finding")
    validate_sanitized_file(finding_path)
    recorded_utc = recorded["identity"]["recorded_utc"]
    with tempfile.TemporaryDirectory(prefix="week08-phase9-review-") as temporary:
        temp_tables = Path(temporary) / "tables"
        expected = generate_bundle(root, temp_tables, recorded_utc=recorded_utc)
        require(recorded == expected, "Tracked scientific-review finding differs from immutable evidence")
        for name in TABLE_FILES:
            tracked = root / "reports/week08_phase9_review_tables" / name
            require(tracked.is_file(), f"Tracked supplement table is missing: {name}")
            require(tracked.read_bytes() == (temp_tables / name).read_bytes(), f"Supplement table is not reproducible: {name}")
            validate_sanitized_file(tracked)
    return recorded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="Write the finding and versioned supplement")
    parser.add_argument("--check", action="store_true", help="Rebuild privately and verify every tracked byte")
    parser.add_argument("--recorded-utc", help="UTC timestamp for initial generation")
    args = parser.parse_args(argv)
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    root = args.root.resolve()
    finding_path = root / "reports/week08_phase9_scientific_review_finding.json"
    if args.check:
        finding = verify_bundle(root, finding_path)
        print(json.dumps({
            "status": "PASS",
            "finding_status": finding["status"],
            "finding_payload_sha256": finding["finding_payload_sha256"],
            "artifact_count": len(finding["supplement"]["artifacts"]),
        }, indent=2))
        return 0

    recorded_utc = args.recorded_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    table_dir = root / "reports/week08_phase9_review_tables"
    finding = generate_bundle(root, table_dir, recorded_utc=recorded_utc)
    write_json(finding_path, finding)
    validate_sanitized_file(finding_path)
    print(json.dumps({
        "status": finding["status"],
        "finding_payload_sha256": finding["finding_payload_sha256"],
        "artifact_count": len(finding["supplement"]["artifacts"]),
        "write": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
