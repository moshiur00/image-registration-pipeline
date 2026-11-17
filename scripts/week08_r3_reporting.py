"""Build and verify the sanitized R3 confirmatory reporting bundle.

This module is deliberately data driven.  It derives every denominator,
interval, stratum, endpoint distribution, and McNemar comparison from the
sealed evaluation rows.  Serialized aggregates are treated as reconciliation
evidence, never as the source of truth.  The module never opens image, array,
or label files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "week08_r3_reporting_manifest_v1"
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
ENDPOINT_METRICS = (
    "tre_mean_px",
    "tre_median_px",
    "tre_p95_px",
    "valid_overlap_fraction",
    "method_runtime_ms",
    "total_runtime_ms",
)
TABLE_FILES = (
    "track_a_overall.csv",
    "track_a_mandatory_strata.csv",
    "track_a_endpoint_distributions.csv",
    "pairwise_exact_mcnemar.csv",
    "track_b_overall.csv",
    "track_b_mandatory_strata.csv",
    "runtime_failure_similarity.csv",
)
SIMILARITY_KEYS = ("mae", "mse", "ncc", "ssim", "mi_nats")
PRIVATE_PATTERNS = (
    re.compile(r"\bw8-[0-9a-f]+\b", re.IGNORECASE),
    re.compile(r"\bfinal-[0-9a-f]+\b", re.IGNORECASE),
    re.compile(r"\bpia\d{4,}\b", re.IGNORECASE),
    re.compile(r"nasa_pia", re.IGNORECASE),
    re.compile(r"sealed_labels", re.IGNORECASE),
    re.compile(r"labels\.json", re.IGNORECASE),
    re.compile(r"\.npy", re.IGNORECASE),
)


class ReportingError(ValueError):
    """Raised when sealed evidence cannot satisfy the R3 report contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportingError(message)


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


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    require(not isinstance(value, bool) and isinstance(value, (int, float)), f"{label} is not numeric")
    number = float(value)
    require(math.isfinite(number), f"{label} is not finite")
    if minimum is not None:
        require(number >= minimum, f"{label} is below {minimum}")
    return number


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    require(not isinstance(value, bool) and isinstance(value, int), f"{label} is not an integer")
    require(value >= minimum, f"{label} is below {minimum}")
    return value


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    require(0 <= numerator <= denominator, f"Invalid rate {numerator}/{denominator}")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
    }


def wilson_interval(successes: int, denominator: int, z: float) -> tuple[float | None, float | None]:
    require(0 <= successes <= denominator, f"Invalid rate {successes}/{denominator}")
    if denominator == 0:
        return None, None
    proportion = successes / denominator
    z2 = z * z
    centre = (proportion + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = z * math.sqrt(
        proportion * (1 - proportion) / denominator
        + z2 / (4 * denominator * denominator)
    ) / (1 + z2 / denominator)
    lower = 0.0 if successes == 0 else max(0.0, centre - half)
    upper = 1.0 if successes == denominator else min(1.0, centre + half)
    return round(lower, 6), round(upper, 6)


def _rate_columns(prefix: str, rate: Mapping[str, Any], z: float) -> dict[str, Any]:
    numerator = _integer(rate.get("numerator"), f"{prefix}.numerator")
    denominator = _integer(rate.get("denominator"), f"{prefix}.denominator")
    require(numerator <= denominator, f"{prefix} numerator exceeds denominator")
    expected_value = None if denominator == 0 else numerator / denominator
    require(rate.get("value") == expected_value, f"{prefix} value is inconsistent")
    lower, upper = wilson_interval(numerator, denominator, z)
    return {
        f"{prefix}_numerator": numerator,
        f"{prefix}_denominator": denominator,
        f"{prefix}_value": expected_value,
        f"{prefix}_ci_lower": lower,
        f"{prefix}_ci_upper": upper,
        f"{prefix}_ci_method": "wilson_score",
        f"{prefix}_ci_z": z,
    }


def _numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    raw = list(values)
    numbers = sorted(
        _number(value, "endpoint value") for value in raw if value is not None
    )
    missing = len(raw) - len(numbers)
    if not numbers:
        return {
            "count": 0,
            "missing": missing,
            "minimum": None,
            "median": None,
            "mean": None,
            "p95": None,
            "maximum": None,
        }

    def quantile(fraction: float) -> float:
        position = (len(numbers) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return numbers[lower]
        weight = position - lower
        return numbers[lower] * (1 - weight) + numbers[upper] * weight

    return {
        "count": len(numbers),
        "missing": missing,
        "minimum": numbers[0],
        "median": quantile(0.5),
        "mean": sum(numbers) / len(numbers),
        "p95": quantile(0.95),
        "maximum": numbers[-1],
    }


def _extract_contract(plan: Mapping[str, Any]) -> tuple[float, Mapping[str, Any]]:
    uncertainty = plan.get("uncertainty")
    require(isinstance(uncertainty, Mapping), "Plan lacks the frozen uncertainty contract")
    require(uncertainty.get("confidence_level") == 0.95, "Only the frozen 95% confidence level is accepted")
    require(uncertainty.get("binomial_interval") == "wilson_score", "Plan does not freeze Wilson score intervals")
    z = _number(uncertainty.get("z_value"), "uncertainty.z_value", minimum=0.0)
    require(z > 0, "uncertainty.z_value must be positive")

    reporting = plan.get("reporting_contract")
    require(isinstance(reporting, Mapping), "Plan lacks reporting_contract")
    require(tuple(reporting.get("mandatory_strata", ())) == MANDATORY_STRATA, "Mandatory strata contract mismatch")
    require(tuple(reporting.get("required_tables", ())) == TABLE_FILES, "Required table contract mismatch")
    require(tuple(reporting.get("endpoint_metrics", ())) == ENDPOINT_METRICS, "Endpoint contract mismatch")
    require(reporting.get("source_alias_format") == "enrolled_source_{ordinal:03d}", "Source alias contract mismatch")
    return z, reporting


def _source_aliases(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    sources = sorted({str(row["source_id"]) for row in rows})
    require(bool(sources), "No source identities are present")
    return {source: f"enrolled_source_{index:03d}" for index, source in enumerate(sources, 1)}


def _validate_attempts(rows: Any) -> list[dict[str, Any]]:
    require(isinstance(rows, list) and rows, "Track A attempts are absent or empty")
    result: list[dict[str, Any]] = []
    required = {
        "pair_id", "method_id", "config_id", "execution_status", "geometric_reference_valid",
        "geometric_within_tolerance", "infrastructure_incident", "diagnostic_keys",
        "estimated_transform_present", *MANDATORY_STRATA,
        *ENDPOINT_METRICS, *SIMILARITY_KEYS,
    }
    for index, raw in enumerate(rows):
        require(isinstance(raw, Mapping), f"Track A row {index} is not an object")
        missing = required - set(raw)
        require(not missing, f"Track A row {index} lacks fields: {sorted(missing)}")
        status = raw["execution_status"]
        require(
            status in {"completed", "check", "failed", "validation_error"},
            f"Track A row {index} has invalid status",
        )
        require(isinstance(raw["diagnostic_keys"], list), f"Track A row {index} diagnostic_keys is not a list")
        _number(raw["method_runtime_ms"], f"Track A row {index} method runtime", minimum=0.0)
        _number(raw["total_runtime_ms"], f"Track A row {index} total runtime", minimum=0.0)
        overlap = raw["valid_overlap_fraction"]
        require(
            isinstance(raw["estimated_transform_present"], bool),
            f"Track A row {index} estimated_transform_present is not Boolean",
        )
        if raw["estimated_transform_present"]:
            overlap_value = _number(overlap, f"Track A row {index} overlap")
            require(0 <= overlap_value <= 1, f"Track A row {index} overlap is outside [0,1]")
        else:
            require(overlap is None, f"Track A row {index} without a transform has invented overlap")
        for metric in ("tre_mean_px", "tre_median_px", "tre_p95_px"):
            if raw[metric] is not None:
                _number(raw[metric], f"Track A row {index} {metric}", minimum=0.0)
        for metric in SIMILARITY_KEYS:
            if raw[metric] is not None:
                _number(raw[metric], f"Track A row {index} {metric}")
        for dimension in MANDATORY_STRATA:
            require(str(raw[dimension]).strip() != "", f"Track A row {index} has empty {dimension}")
        result.append(dict(raw))
    identities = [(str(row["pair_id"]), str(row["method_id"]), str(row["config_id"])) for row in result]
    require(len(identities) == len(set(identities)), "Track A has duplicate pair/method/config rows")
    return result


def _validate_pairs(rows: Any) -> list[dict[str, Any]]:
    require(isinstance(rows, list) and rows, "Track B pairs are absent or empty")
    result: list[dict[str, Any]] = []
    required = {"pair_id", "decision", "selected_geometrically_correct", *MANDATORY_STRATA}
    for index, raw in enumerate(rows):
        require(isinstance(raw, Mapping), f"Track B row {index} is not an object")
        missing = required - set(raw)
        require(not missing, f"Track B row {index} lacks fields: {sorted(missing)}")
        decision = raw["decision"]
        require(decision in {"selected", "abstained", "invalid", "missing_decision"}, f"Track B row {index} has invalid decision")
        if decision == "selected":
            require(isinstance(raw["selected_geometrically_correct"], bool), f"Selected Track B row {index} lacks correctness")
        else:
            require(raw["selected_geometrically_correct"] is None, f"Unselected Track B row {index} has correctness")
        for dimension in MANDATORY_STRATA:
            require(str(raw[dimension]).strip() != "", f"Track B row {index} has empty {dimension}")
        result.append(dict(raw))
    pair_ids = [str(row["pair_id"]) for row in result]
    require(len(pair_ids) == len(set(pair_ids)), "Track B has duplicate pair rows")
    return result


def _track_a_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    completed = sum(row["execution_status"] == "completed" for row in rows)
    valid_gt = sum(row["geometric_reference_valid"] is True for row in rows)
    evaluable = sum(row["geometric_within_tolerance"] is not None for row in rows)
    successes = sum(row["geometric_within_tolerance"] is True for row in rows)
    infrastructure = sum(row["infrastructure_incident"] is True for row in rows)
    return {
        "attempts": len(rows),
        "status_counts": dict(sorted(Counter(str(row["execution_status"]) for row in rows).items())),
        "valid_gt_attempts": valid_gt,
        "geometrically_evaluable_completed_attempts": evaluable,
        "geometric_successes": successes,
        "execution_completion_rate": _rate(completed, len(rows)),
        "geometric_success_rate": _rate(successes, valid_gt),
        "conditional_accuracy": _rate(successes, evaluable),
        "infrastructure_incident_rate": _rate(infrastructure, len(rows)),
    }


def _track_b_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = sum(row["decision"] == "selected" for row in rows)
    abstained = sum(row["decision"] == "abstained" for row in rows)
    invalid = sum(row["decision"] == "invalid" for row in rows)
    missing = sum(row["decision"] == "missing_decision" for row in rows)
    correct = sum(row["decision"] == "selected" and row["selected_geometrically_correct"] is True for row in rows)
    return {
        "eligible_pairs": len(rows),
        "selected_pairs": selected,
        "abstained_pairs": abstained,
        "invalid_pairs": invalid,
        "missing_decision_pairs": missing,
        "correct_selected_pairs": correct,
        "coverage": _rate(selected, len(rows)),
        "abstention_rate": _rate(abstained, len(rows)),
        "invalid_rate": _rate(invalid, len(rows)),
        "missing_decision_rate": _rate(missing, len(rows)),
        "selective_correctness": _rate(correct, selected),
    }


def _flat_summary(prefix: Mapping[str, Any], rate_names: Sequence[str], z: float) -> dict[str, Any]:
    row = {name: value for name, value in prefix.items() if name not in rate_names and name != "status_counts"}
    counts = prefix.get("status_counts", {})
    if isinstance(counts, Mapping):
        row.update({"completed": int(counts.get("completed", 0)), "check": int(counts.get("CHECK", 0)), "failed": int(counts.get("failed", 0))})
    for name in rate_names:
        row.update(_rate_columns(name, prefix[name], z))
    return row


def _sealed_categories(summary: Mapping[str, Any], track: str, rows: Sequence[Mapping[str, Any]]) -> None:
    track_value = summary.get(track)
    require(isinstance(track_value, Mapping), f"Summary lacks {track}")
    strata = track_value.get("strata")
    require(isinstance(strata, Mapping), f"Summary lacks {track}.strata")
    require(set(strata) == set(MANDATORY_STRATA), f"{track} strata are incomplete")
    for dimension in MANDATORY_STRATA:
        sealed = strata[dimension]
        require(isinstance(sealed, list) and sealed, f"{track}.{dimension} strata are empty")
        sealed_values = {str(item.get(dimension)) for item in sealed if isinstance(item, Mapping)}
        observed_values = {str(row[dimension]) for row in rows}
        require(sealed_values == observed_values, f"{track}.{dimension} categories do not reconcile")


def _exact_mcnemar(a_only: int, b_only: int) -> float:
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    tail = min(a_only, b_only)
    cumulative = sum(math.comb(discordant, k) for k in range(tail + 1)) / (2 ** discordant)
    return min(1.0, 2.0 * cumulative)


def _pairwise(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rows:
        outcome = row["geometric_within_tolerance"]
        if outcome is None:
            continue
        method = f"{row['method_id']}::{row['config_id']}"
        pair_id = str(row["pair_id"])
        require(pair_id not in outcomes[method], f"Duplicate pair outcome for {method}")
        outcomes[method][pair_id] = bool(outcome)
    methods = sorted(outcomes)
    result: list[dict[str, Any]] = []
    for index, method_a in enumerate(methods):
        for method_b in methods[index + 1:]:
            common = sorted(set(outcomes[method_a]) & set(outcomes[method_b]))
            if not common:
                continue
            both_success = both_failure = a_only = b_only = 0
            for pair_id in common:
                a = outcomes[method_a][pair_id]
                b = outcomes[method_b][pair_id]
                both_success += int(a and b)
                both_failure += int(not a and not b)
                a_only += int(a and not b)
                b_only += int(not a and b)
            result.append({
                "method_a": method_a,
                "method_b": method_b,
                "common_denominator": len(common),
                "both_success": both_success,
                "both_failure": both_failure,
                "method_a_only_success": a_only,
                "method_b_only_success": b_only,
                "method_a_successes": both_success + a_only,
                "method_b_successes": both_success + b_only,
                "mcnemar_exact_two_sided_p": _exact_mcnemar(a_only, b_only),
            })
    require(bool(result), "No pairwise comparisons can be derived")
    return result


def _reconcile_pairwise(summary: Mapping[str, Any], expected: Sequence[Mapping[str, Any]]) -> None:
    track_a = summary.get("track_a")
    require(isinstance(track_a, Mapping), "Summary lacks track_a")
    sealed = track_a.get("pairwise_method_comparisons")
    require(isinstance(sealed, list), "Summary lacks sealed pairwise comparisons")
    normalize = lambda rows: sorted((dict(row) for row in rows), key=lambda row: (str(row.get("method_a")), str(row.get("method_b"))))
    require(canonical_json(normalize(sealed)) == canonical_json(normalize(expected)), "Sealed McNemar comparisons do not reconcile")
    keys = [(row["method_a"], row["method_b"]) for row in sealed]
    require(len(keys) == len(set(keys)), "A sealed McNemar comparison is duplicated")


def _endpoint_rows(rows: Sequence[Mapping[str, Any]], aliases: Mapping[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scopes: list[tuple[str, str, Sequence[Mapping[str, Any]]]] = [("overall", "all", rows)]
    for dimension in MANDATORY_STRATA:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[dimension])].append(row)
        for value, group in sorted(groups.items()):
            display = aliases[value] if dimension == "source_id" else value
            scopes.append((dimension, display, group))
    for dimension, value, group in scopes:
        for metric in ENDPOINT_METRICS:
            output.append({"dimension": dimension, "stratum": value, "metric": metric, **_numeric_summary(row[metric] for row in group)})
    return output


def _runtime_failure_similarity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["method_id"])].append(row)
    output: list[dict[str, Any]] = []
    for method, group in sorted(groups.items()):
        method_runtime = _numeric_summary(row["method_runtime_ms"] for row in group)
        total_runtime = _numeric_summary(row["total_runtime_ms"] for row in group)
        similarity_available = sum(
            any(row.get(key) is not None for key in SIMILARITY_KEYS)
            for row in group
        )
        geometric_available = sum(row["geometric_within_tolerance"] is not None for row in group)
        explicit = [row.get("similarity_supports_alignment") for row in group]
        comparable = sum(isinstance(value, bool) for value in explicit)
        agreements = sum(
            isinstance(value, bool) and value == bool(row["geometric_within_tolerance"])
            for row, value in zip(group, explicit)
            if row["geometric_within_tolerance"] is not None
        )
        output.append({
            "method_id": method,
            "attempts": len(group),
            "completed": sum(row["execution_status"] == "completed" for row in group),
            "check": sum(row["execution_status"] == "check" for row in group),
            "failed": sum(row["execution_status"] == "failed" for row in group),
            "method_runtime_count": method_runtime["count"],
            "method_runtime_median_ms": method_runtime["median"],
            "method_runtime_p95_ms": method_runtime["p95"],
            "total_runtime_count": total_runtime["count"],
            "total_runtime_median_ms": total_runtime["median"],
            "total_runtime_p95_ms": total_runtime["p95"],
            "common_similarity_available": similarity_available,
            "geometric_outcome_available": geometric_available,
            "similarity_geometry_comparable": comparable,
            "similarity_geometry_agreements": agreements,
            "similarity_geometry_disagreements": comparable - agreements,
            "comparison_status": "evaluated" if comparable else "NOT_EVALUABLE_NO_COMMON_THRESHOLD",
        })
    return output


def build_tables(summary: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Derive every required table and reject incomplete or inconsistent evidence."""

    require(plan.get("schema_version") == "week08_evaluation_plan_v2", "Unsupported R3 plan schema")
    plan_payload = dict(plan)
    plan_hash = plan_payload.pop("plan_sha256", None)
    require(
        isinstance(plan_hash, str) and canonical_sha256(plan_payload) == plan_hash,
        "Evaluation plan self-hash mismatch",
    )
    require(
        summary.get("schema_version") == "week08_evaluation_summary_v2",
        "Unsupported R3 evaluation summary schema",
    )
    require(summary.get("mode") == "final", "R3 reporting accepts final evidence only")
    z, _ = _extract_contract(plan)
    require(summary.get("plan_sha256") == plan.get("plan_sha256"), "Summary is not bound to the supplied plan")
    require(summary.get("uncertainty_contract") == plan.get("uncertainty"), "Summary uncertainty contract mismatch")
    require(
        summary.get("endpoint_availability_contract") == plan.get("endpoint_availability"),
        "Summary endpoint availability contract mismatch",
    )
    require(summary.get("reporting_contract") == plan.get("reporting_contract"), "Summary reporting contract mismatch")
    require(
        summary.get("mandatory_reporting_strata") == list(MANDATORY_STRATA),
        "Summary mandatory strata contract mismatch",
    )
    integrity = summary.get("integrity_evidence")
    require(isinstance(integrity, Mapping), "Summary lacks integrity evidence")
    integrity_payload = dict(integrity)
    integrity_hash = integrity_payload.pop("evidence_sha256", None)
    require(
        isinstance(integrity_hash, str) and canonical_sha256(integrity_payload) == integrity_hash,
        "Integrity evidence self-hash mismatch",
    )
    require(
        integrity.get("no_firewall_or_integrity_incident") is True,
        "Firewall or integrity evidence did not pass",
    )
    require(integrity.get("no_post_label_change") is True, "No-post-label-change evidence did not pass")
    require(integrity.get("label_access_event_count") == 1, "Label-access event count mismatch")
    require(integrity.get("prior_label_access_event_count") == 0, "Prior label access was detected")
    require(integrity.get("prior_evaluation_output_count") == 0, "Prior evaluation output was detected")
    track_a = summary.get("track_a")
    track_b = summary.get("track_b")
    require(isinstance(track_a, Mapping) and isinstance(track_b, Mapping), "Summary lacks Track A or Track B")
    attempts = _validate_attempts(track_a.get("attempts"))
    pairs = _validate_pairs(track_b.get("pairs"))
    _sealed_categories(summary, "track_a", attempts)
    _sealed_categories(summary, "track_b", pairs)
    aliases = _source_aliases([*attempts, *pairs])

    overall_a = _track_a_summary(attempts)
    overall_b = _track_b_summary(pairs)
    require(isinstance(track_a.get("overall"), Mapping), "Summary lacks Track A overall")
    require(isinstance(track_b.get("overall"), Mapping), "Summary lacks Track B overall")
    for name in TRACK_A_RATES:
        require(track_a["overall"].get(name) == overall_a[name], f"Track A overall {name} does not reconcile")
    for name in TRACK_B_RATES:
        require(track_b["overall"].get(name) == overall_b[name], f"Track B overall {name} does not reconcile")

    strata_a: list[dict[str, Any]] = []
    strata_b: list[dict[str, Any]] = []
    for dimension in MANDATORY_STRATA:
        grouped_a: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        grouped_b: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in attempts:
            grouped_a[str(row[dimension])].append(row)
        for row in pairs:
            grouped_b[str(row[dimension])].append(row)
        for value, group in sorted(grouped_a.items()):
            display = aliases[value] if dimension == "source_id" else value
            strata_a.append({"dimension": dimension, "stratum": display, **_flat_summary(_track_a_summary(group), TRACK_A_RATES, z)})
        for value, group in sorted(grouped_b.items()):
            display = aliases[value] if dimension == "source_id" else value
            strata_b.append({"dimension": dimension, "stratum": display, **_flat_summary(_track_b_summary(group), TRACK_B_RATES, z)})

    pairwise = _pairwise(attempts)
    _reconcile_pairwise(summary, pairwise)
    tables = {
        "track_a_overall.csv": [{"scope": "overall", **_flat_summary(overall_a, TRACK_A_RATES, z)}],
        "track_a_mandatory_strata.csv": strata_a,
        "track_a_endpoint_distributions.csv": _endpoint_rows(attempts, aliases),
        "pairwise_exact_mcnemar.csv": pairwise,
        "track_b_overall.csv": [{"scope": "overall", **_flat_summary(overall_b, TRACK_B_RATES, z)}],
        "track_b_mandatory_strata.csv": strata_b,
        "runtime_failure_similarity.csv": _runtime_failure_similarity(attempts),
    }
    require(tuple(tables) == TABLE_FILES, "Generated table inventory mismatch")
    require(all(tables[name] for name in TABLE_FILES), "A required table is empty")
    return tables


def _format_csv(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        require(math.isfinite(value), "CSV contains a non-finite number")
        return f"{value:.6f}"
    return str(value)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    require(bool(rows), f"Refusing to write empty table {path.name}")
    columns = tuple(rows[0])
    require(all(tuple(row) == columns for row in rows), f"Inconsistent columns in {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _format_csv(row[column]) for column in columns})
    os.replace(temporary, path)


def _validate_sanitized(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern in PRIVATE_PATTERNS:
        require(pattern.search(text) is None, f"Private identifier leaked into {path.name}: {pattern.pattern}")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def generate_bundle(summary_path: Path, plan_path: Path, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    plan = load_json(plan_path)
    tables = build_tables(summary, plan)
    for name, rows in tables.items():
        _write_csv(output_dir / name, rows)
        _validate_sanitized(output_dir / name)
    z, reporting = _extract_contract(plan)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "inputs": {
            "evaluation_summary_sha256": sha256_file(summary_path),
            "evaluation_plan_sha256": sha256_file(plan_path),
            "bound_plan_sha256": plan.get("plan_sha256"),
        },
        "contract": {
            "confidence_level": 0.95,
            "binomial_interval": "wilson_score",
            "z_value": z,
            "mandatory_strata": list(MANDATORY_STRATA),
            "endpoint_metrics": list(ENDPOINT_METRICS),
            "source_alias_format": reporting["source_alias_format"],
        },
        "tables": {
            name: {"rows": len(tables[name]), "sha256": sha256_file(output_dir / name)}
            for name in TABLE_FILES
        },
        "sanitization": {
            "source_id_output": "deterministic_ordinal_alias_only",
            "raw_source_identifiers_emitted": False,
            "pair_or_attempt_identifiers_emitted": False,
        },
    }
    manifest["payload_sha256"] = canonical_sha256(manifest)
    _write_json(manifest_path, manifest)
    _validate_sanitized(manifest_path)
    return manifest


def check_bundle(summary_path: Path, plan_path: Path, output_dir: Path, manifest_path: Path) -> None:
    manifest = load_json(manifest_path)
    recorded = manifest.pop("payload_sha256", None)
    require(isinstance(recorded, str) and canonical_sha256(manifest) == recorded, "Reporting manifest self-hash mismatch")
    require(manifest.get("schema_version") == SCHEMA_VERSION and manifest.get("status") == "PASS", "Invalid reporting manifest")
    require(manifest.get("inputs", {}).get("evaluation_summary_sha256") == sha256_file(summary_path), "Summary hash changed")
    require(manifest.get("inputs", {}).get("evaluation_plan_sha256") == sha256_file(plan_path), "Plan hash changed")
    expected = build_tables(load_json(summary_path), load_json(plan_path))
    require(set(manifest.get("tables", {})) == set(TABLE_FILES), "Manifest table inventory mismatch")
    for name in TABLE_FILES:
        path = output_dir / name
        require(path.is_file(), f"Required table is absent: {name}")
        require(manifest["tables"][name]["sha256"] == sha256_file(path), f"Table hash mismatch: {name}")
        require(manifest["tables"][name]["rows"] == len(expected[name]), f"Table row count mismatch: {name}")
        _validate_sanitized(path)
    _validate_sanitized(manifest_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        check_bundle(args.summary, args.plan, args.output_dir, args.manifest)
    else:
        generate_bundle(args.summary, args.plan, args.output_dir, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
