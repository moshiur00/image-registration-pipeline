"""Week 8 evaluation orchestration with a decision-before-label firewall.

The module is deliberately separate from the frozen registration algorithms.
It owns deterministic identities, plan and artifact integrity, append-only
execution accounting, observable-only policy decisions, and post-seal
evaluation.  Real Week 8 source enrollment is handled by later release gates;
Phase 3 uses this code only with development fixtures.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
import csv
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from .week7_calibration import Gate, project_observables, select_pair, wilson_interval
from .unified_metrics import dice_score
from .warping import warp_mask


WEEK8_SCHEMA_VERSION = "week08_evaluator_v1"
TASK_IDENTITY_VERSION = "week08_task_identity_v1"
PLAN_SCHEMA_VERSION = "week08_evaluation_plan_v1"
PREPARE_SCHEMA_VERSION = "week08_prepare_receipt_v1"
DECISION_SCHEMA_VERSION = "week08_decision_seal_v1"
EVALUATION_SCHEMA_VERSION = "week08_evaluation_summary_v1"
DEFAULT_PROTOCOL_VERSION = "week08_evaluator_firewall_v1"

MANDATORY_STRATA = (
    "modality_class",
    "transform_model",
    "condition",
    "severity",
    "source_role",
    "source_id",
)
DEFAULT_RECOMMENDATION_CRITERIA: dict[str, Any] = {
    "minimum_selected_pairs": 20,
    "minimum_coverage": 0.10,
    "minimum_selective_correctness": 0.95,
    "minimum_selective_correctness_wilson_lower_95": 0.80,
    "maximum_missing_decisions": 0,
    "minimum_distinct_independent_sources_for_broad_support": 3,
    "broad_support_requires_real_verified_gt": True,
}

TERMINAL_SCIENTIFIC_STATUSES = frozenset(
    {"completed", "check", "failed", "validation_error"}
)
GT_TYPES = frozenset(
    {"synthetic_created_after_freeze", "verified_landmarks", "verified_masks", "unavailable"}
)
_FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "ground_truth", "ground_truth_transform", "moving_to_fixed", "fixed_to_moving",
        "label", "labels", "landmarks", "fixed_landmarks", "moving_landmarks",
        "mask", "masks", "fixed_mask", "moving_mask", "dice", "tre",
        "control_points_fixed", "control_points_moving", "geometric_within_tolerance",
        "success_label", "reference_transform", "reference_valid_overlap_fraction",
        "inverse_matrix_max_absolute_error", "control_point_round_trip_max_px",
        "has_geometric_ground_truth",
    }
)
_HEX64 = frozenset("0123456789abcdef")


class Week8ContractError(ValueError):
    """A preregistered identity or execution contract is invalid."""


class IntegrityError(Week8ContractError):
    """A content hash, count, identity, or seal does not verify."""


class LabelFirewallError(Week8ContractError):
    """Label access was requested before a complete verified decision seal."""


class InfrastructureError(RuntimeError):
    """A retryable infrastructure event, not a scientific outcome."""


class IncompleteDecisionError(Week8ContractError):
    """At least one planned attempt lacks a terminal scientific record."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Return the canonical JSON encoding used by every Week 8 digest."""
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _gate_dict(gate: Gate) -> dict[str, Any]:
    return {
        "agreement_px": float(gate.agreement_px),
        "overlap_floor": float(gate.overlap_floor),
        "min_feature_inlier": float(gate.min_feature_inlier),
        "min_feature_coverage": float(gate.min_feature_coverage),
        "min_distinct_families": int(gate.min_distinct_families),
        "min_candidates": int(gate.min_candidates),
    }


def _coerce_gate(value: Gate | Mapping[str, Any] | None) -> Gate:
    if value is None:
        return Gate()
    if isinstance(value, Gate):
        return value
    if not isinstance(value, Mapping):
        raise Week8ContractError("policy_gate must be a Gate or mapping")
    return Gate(**dict(value))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(char in _HEX64 for char in value)
    )


def _text(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise Week8ContractError(f"{name} must be non-empty")
    return result


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(_jsonable(value), sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a deterministic flat table, JSON-encoding nested cells."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fieldnames = sorted({str(key) for row in rows for key in row})
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        if fieldnames:
            writer.writeheader()
            for row in rows:
                flattened: dict[str, Any] = {}
                for key in fieldnames:
                    value = row.get(key)
                    if isinstance(value, (Mapping, list, tuple)):
                        flattened[key] = canonical_json(value)
                    elif value is None:
                        flattened[key] = ""
                    else:
                        flattened[key] = value
                writer.writerow(flattened)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"Cannot read valid JSON from {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    output: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IntegrityError(f"Invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise IntegrityError(f"JSONL item at {path}:{line_number} is not an object")
            output.append(value)
    return output


@dataclass(frozen=True)
class Week8PairSpec:
    pair_id: str
    source_id: str
    source_sha256: str
    case_id: str
    geometry_seed: int
    evaluation_role: str
    source_role: str
    modality_class: str
    transform_model: str
    condition: str
    severity: str
    ground_truth_type: str
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    dimensions: int = 2
    policy_eligible: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "pair_id", "source_id", "case_id", "evaluation_role", "source_role",
            "modality_class", "transform_model", "condition", "severity", "ground_truth_type",
            "protocol_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not _is_sha256(self.source_sha256):
            raise Week8ContractError("source_sha256 must be lowercase SHA-256")
        if self.ground_truth_type not in GT_TYPES:
            raise Week8ContractError(f"unsupported ground_truth_type: {self.ground_truth_type}")
        if self.source_role == "real_technical_only" and self.ground_truth_type != "unavailable":
            raise Week8ContractError("real_technical_only pairs must use unavailable ground truth")
        if self.ground_truth_type == "unavailable" and self.source_role != "real_technical_only":
            raise Week8ContractError("unavailable ground truth is reserved for real_technical_only pairs")
        if self.ground_truth_type == "unavailable" and self.policy_eligible is True:
            raise Week8ContractError("a pair without ground truth cannot be policy-correctness eligible")
        if int(self.geometry_seed) < 0:
            raise Week8ContractError("geometry_seed must be non-negative")
        object.__setattr__(self, "geometry_seed", int(self.geometry_seed))
        if int(self.dimensions) not in {2, 3}:
            raise Week8ContractError("dimensions must be 2 or 3")
        object.__setattr__(self, "dimensions", int(self.dimensions))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def identity_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "case_id": self.case_id,
            "geometry_seed": self.geometry_seed,
            "evaluation_role": self.evaluation_role,
            "source_role": self.source_role,
            "modality_class": self.modality_class,
            "transform_model": self.transform_model,
            "condition": self.condition,
            "severity": self.severity,
            "ground_truth_type": self.ground_truth_type,
            "protocol_version": self.protocol_version,
            "dimensions": self.dimensions,
            "policy_eligible": self.policy_eligible,
            "pair_metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Week8MethodSpec:
    method_id: str
    config_id: str
    method_family: str
    method_config_sha256: str
    supported_transform_models: tuple[str, ...]
    supported_modality_classes: tuple[str, ...] | None = None
    method_seed: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("method_id", "config_id", "method_family"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not _is_sha256(self.method_config_sha256):
            raise Week8ContractError("method_config_sha256 must be lowercase SHA-256")
        models = tuple(_text(item, "supported transform model") for item in self.supported_transform_models)
        if not models or len(models) != len(set(models)):
            raise Week8ContractError("supported_transform_models must be nonempty and unique")
        object.__setattr__(self, "supported_transform_models", models)
        if self.supported_modality_classes is not None:
            modalities = tuple(_text(item, "supported modality") for item in self.supported_modality_classes)
            if not modalities or len(modalities) != len(set(modalities)):
                raise Week8ContractError("supported_modality_classes must be nonempty and unique")
            object.__setattr__(self, "supported_modality_classes", modalities)
        if self.method_seed is not None:
            object.__setattr__(self, "method_seed", int(self.method_seed))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def supports(self, pair: Week8PairSpec) -> bool:
        return (
            pair.transform_model in self.supported_transform_models
            and (
                self.supported_modality_classes is None
                or pair.modality_class in self.supported_modality_classes
            )
        )


@dataclass(frozen=True)
class Week8Task:
    pair: Week8PairSpec
    method: Week8MethodSpec

    def identity_dict(self) -> dict[str, Any]:
        return {
            "identity_version": TASK_IDENTITY_VERSION,
            **self.pair.identity_dict(),
            "method_id": self.method.method_id,
            "config_id": self.method.config_id,
            "method_family": self.method.method_family,
            "method_config_sha256": self.method.method_config_sha256,
            "method_seed": self.method.method_seed,
            "method_metadata": dict(self.method.metadata),
        }

    @property
    def experiment_id(self) -> str:
        return f"w8-{canonical_sha256(self.identity_dict())[:24]}"

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_dict(), "experiment_id": self.experiment_id}


@dataclass(frozen=True)
class Week8Paths:
    root: Path
    prepared_root: Path | None = None
    decision_root: Path | None = None
    evaluation_root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))
        for name in ("prepared_root", "decision_root", "evaluation_root"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))

    @classmethod
    def final_layout(cls, *, holdout_root: str | Path, final_root: str | Path) -> "Week8Paths":
        """Return the preregistered split layout for the one-run final workflow."""
        final = Path(final_root)
        return cls(
            root=final,
            prepared_root=Path(holdout_root),
            decision_root=final,
            evaluation_root=final,
        )

    @property
    def plan(self) -> Path:
        return self.root / "evaluation_plan.json"

    @property
    def prepared(self) -> Path:
        return self.prepared_root if self.prepared_root is not None else self.root / "prepared"

    @property
    def observable_inputs(self) -> Path:
        return self.prepared / "observable_inputs"

    @property
    def observable_manifest(self) -> Path:
        return self.prepared / "observable_manifest.json"

    @property
    def prepare_receipt(self) -> Path:
        return self.prepared / "prepare_receipt.json"

    @property
    def final_readiness_receipt(self) -> Path:
        return self.root / "final_readiness_receipt.json"

    @property
    def sealed_labels(self) -> Path:
        return self.prepared / "sealed_labels" / "labels.json"

    @property
    def label_manifest(self) -> Path:
        return self.prepared / "sealed_labels" / "label_manifest.json"

    @property
    def decision(self) -> Path:
        return self.decision_root if self.decision_root is not None else self.root / "decision"

    @property
    def attempt_events(self) -> Path:
        return self.decision / "attempt_events.jsonl"

    @property
    def scientific_records(self) -> Path:
        return self.decision / "scientific_records.jsonl"

    @property
    def policy_decisions(self) -> Path:
        return self.decision / "policy_decisions.json"

    @property
    def decision_seal(self) -> Path:
        return self.decision / "decision_seal.json"

    @property
    def evaluation(self) -> Path:
        return self.evaluation_root if self.evaluation_root is not None else self.root / "evaluation"

    @property
    def label_access_audit(self) -> Path:
        return self.evaluation / "label_access_audit.jsonl"

    @property
    def evaluation_summary(self) -> Path:
        return self.evaluation / "evaluation_summary.json"

    @property
    def artifact_root(self) -> Path:
        roots = [
            self.root.resolve(), self.prepared.resolve(),
            self.decision.resolve(), self.evaluation.resolve(),
        ]
        return Path(os.path.commonpath([str(path) for path in roots]))


def _coerce_paths(value: str | Path | Week8Paths) -> Week8Paths:
    return value if isinstance(value, Week8Paths) else Week8Paths(Path(value))


def enumerate_week8_tasks(
    pairs: Sequence[Week8PairSpec],
    methods: Sequence[Week8MethodSpec],
    *,
    prior_experiment_ids: Iterable[str] = (),
) -> list[Week8Task]:
    """Expand all compatible pair/method cells into deterministic Week 8 tasks."""
    if not pairs:
        raise Week8ContractError("pairs must not be empty")
    if not methods:
        raise Week8ContractError("methods must not be empty")
    prior = {str(value) for value in prior_experiment_ids}
    seen_pair_ids: set[str] = set()
    source_hashes: dict[str, str] = {}
    for pair in pairs:
        if pair.pair_id in seen_pair_ids:
            raise Week8ContractError(
                f"duplicate pair_id would collapse source/case accounting: {pair.pair_id}"
            )
        seen_pair_ids.add(pair.pair_id)
        prior_hash = source_hashes.setdefault(pair.source_id, pair.source_sha256)
        if prior_hash != pair.source_sha256:
            raise Week8ContractError(
                f"source_id {pair.source_id!r} is bound to multiple source hashes"
            )
    tasks: list[Week8Task] = []
    for pair in pairs:
        compatible = [method for method in methods if method.supports(pair)]
        if not compatible:
            raise Week8ContractError(f"pair {pair.pair_id!r} has no compatible method")
        tasks.extend(Week8Task(pair=pair, method=method) for method in compatible)

    seen: set[str] = set()
    for task in tasks:
        experiment_id = task.experiment_id
        if experiment_id in seen:
            raise Week8ContractError(
                f"duplicate Week 8 scientific identity collision: {experiment_id}"
            )
        if experiment_id in prior:
            raise Week8ContractError(
                f"Week 8 identifier overlaps prior/another task: {experiment_id}"
            )
        seen.add(experiment_id)
    return sorted(tasks, key=lambda item: item.experiment_id)


def _policy_eligible_pair(task_group: Sequence[Week8Task]) -> bool:
    pair = task_group[0].pair
    if pair.policy_eligible is not None:
        return bool(pair.policy_eligible)
    return (
        pair.source_role in {"full_project_independent", "policy_transfer_check"}
        and pair.ground_truth_type != "unavailable"
        and pair.modality_class == "monomodal"
        and pair.transform_model == "affine"
        and len(task_group) >= 3
        and len({task.method.method_family for task in task_group}) >= 3
    )


def _expected_counts(tasks: Sequence[Week8Task]) -> dict[str, int]:
    groups: dict[str, list[Week8Task]] = defaultdict(list)
    for task in tasks:
        groups[task.pair.pair_id].append(task)
    return {
        "sources": len({task.pair.source_id for task in tasks}),
        "pairs": len(groups),
        "attempts": len(tasks),
        "policy_eligible_pairs": sum(_policy_eligible_pair(group) for group in groups.values()),
    }


def build_week8_plan(
    tasks: Sequence[Week8Task],
    *,
    config_sha256: str,
    method_catalog_sha256: str,
    policy_sha256: str,
    code_sha256: str,
    mode: str,
    policy_gate: Gate | Mapping[str, Any] | None = None,
    tolerance_px: float = 2.0,
    mask_dice_threshold: float = 0.8,
    source_ledger_sha256: str | None = None,
    enrollment_manifest_sha256: str | None = None,
    final_readiness_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a self-hashing, count-bound evaluation plan without reading pixels."""
    if not tasks:
        raise Week8ContractError("tasks must not be empty")
    for name, value in {
        "config_sha256": config_sha256,
        "method_catalog_sha256": method_catalog_sha256,
        "policy_sha256": policy_sha256,
        "code_sha256": code_sha256,
    }.items():
        if not _is_sha256(value):
            raise Week8ContractError(f"{name} must be lowercase SHA-256")
    mode = _text(mode, "mode")
    if mode not in {"development_rehearsal", "final"}:
        raise Week8ContractError("mode must be development_rehearsal or final")
    enrollment_hashes = {
        "source_ledger_sha256": source_ledger_sha256,
        "enrollment_manifest_sha256": enrollment_manifest_sha256,
        "final_readiness_receipt_sha256": final_readiness_receipt_sha256,
    }
    for name, value in enrollment_hashes.items():
        if value is not None and not _is_sha256(value):
            raise Week8ContractError(f"{name} must be null or lowercase SHA-256")
    present_hashes = [value is not None for value in enrollment_hashes.values()]
    if any(present_hashes) and not all(present_hashes):
        raise Week8ContractError("all final enrollment and readiness hashes must be bound together")
    if mode == "final" and not all(present_hashes):
        raise Week8ContractError(
            "final plans must bind source-ledger, enrollment-manifest, and readiness-receipt hashes"
        )
    if mode == "final" and policy_gate is None:
        raise Week8ContractError("final plans must bind the explicit frozen policy gate")
    gate_values = _gate_dict(_coerce_gate(policy_gate))
    tolerance = float(tolerance_px)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise Week8ContractError("tolerance_px must be finite and positive")
    dice_threshold = float(mask_dice_threshold)
    if not math.isfinite(dice_threshold) or not 0.0 <= dice_threshold <= 1.0:
        raise Week8ContractError("mask_dice_threshold must be in [0,1]")
    ordered = sorted(tasks, key=lambda task: task.experiment_id)
    ids = [task.experiment_id for task in ordered]
    if len(ids) != len(set(ids)):
        raise Week8ContractError("plan contains duplicate Week 8 IDs")
    counts = _expected_counts(ordered)
    payload: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "runner_schema_version": WEEK8_SCHEMA_VERSION,
        "mode": mode,
        "config_sha256": config_sha256,
        "method_catalog_sha256": method_catalog_sha256,
        "policy_sha256": policy_sha256,
        "policy_gate": gate_values,
        "policy_gate_sha256": canonical_sha256(gate_values),
        "code_sha256": code_sha256,
        **enrollment_hashes,
        "tolerance_px": tolerance,
        "mask_dice_threshold": dice_threshold,
        "expected_counts": counts,
        "expected_counts_sha256": canonical_sha256(counts),
        "tasks": [task.to_dict() for task in ordered],
    }
    payload["plan_sha256"] = canonical_sha256(payload)
    return payload


def _task_from_dict(value: Mapping[str, Any]) -> Week8Task:
    pair = Week8PairSpec(
        pair_id=value["pair_id"],
        source_id=value["source_id"],
        source_sha256=value["source_sha256"],
        case_id=value["case_id"],
        geometry_seed=value["geometry_seed"],
        evaluation_role=value["evaluation_role"],
        source_role=value["source_role"],
        modality_class=value["modality_class"],
        transform_model=value["transform_model"],
        condition=value["condition"],
        severity=value["severity"],
        ground_truth_type=value["ground_truth_type"],
        protocol_version=value.get("protocol_version", DEFAULT_PROTOCOL_VERSION),
        dimensions=value.get("dimensions", 2),
        policy_eligible=value.get("policy_eligible"),
        metadata=value.get("pair_metadata", {}),
    )
    method = Week8MethodSpec(
        method_id=value["method_id"],
        config_id=value["config_id"],
        method_family=value["method_family"],
        method_config_sha256=value["method_config_sha256"],
        supported_transform_models=(pair.transform_model,),
        supported_modality_classes=(pair.modality_class,),
        method_seed=value.get("method_seed"),
        metadata=value.get("method_metadata", {}),
    )
    return Week8Task(pair=pair, method=method)


def _verify_plan_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(canonical_json(raw))
    if value.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise IntegrityError("unsupported Week 8 plan schema")
    received_hash = value.pop("plan_sha256", None)
    if not _is_sha256(received_hash) or canonical_sha256(value) != received_hash:
        raise IntegrityError("Week 8 plan hash mismatch")
    value["plan_sha256"] = received_hash
    if value.get("mode") not in {"development_rehearsal", "final"}:
        raise IntegrityError("invalid Week 8 plan mode")
    for name in ("config_sha256", "method_catalog_sha256", "policy_sha256", "code_sha256"):
        if not _is_sha256(value.get(name)):
            raise IntegrityError(f"invalid {name} in plan")
    enrollment_hashes = (
        value.get("source_ledger_sha256"),
        value.get("enrollment_manifest_sha256"),
        value.get("final_readiness_receipt_sha256"),
    )
    if any(item is not None and not _is_sha256(item) for item in enrollment_hashes):
        raise IntegrityError("invalid enrollment hash in plan")
    present_hashes = [item is not None for item in enrollment_hashes]
    if any(present_hashes) and not all(present_hashes):
        raise IntegrityError("plan enrollment and readiness hashes must be bound together")
    if value.get("mode") == "final" and enrollment_hashes[0] is None:
        raise IntegrityError("final plan is missing enrollment hashes")
    gate_values = value.get("policy_gate")
    if not isinstance(gate_values, dict):
        raise IntegrityError("plan policy_gate is missing")
    try:
        normalized_gate = _gate_dict(Gate(**gate_values))
    except (TypeError, ValueError) as exc:
        raise IntegrityError(f"invalid plan policy_gate: {exc}") from exc
    if normalized_gate != gate_values:
        raise IntegrityError("plan policy_gate is not canonical")
    if value.get("policy_gate_sha256") != canonical_sha256(gate_values):
        raise IntegrityError("plan policy-gate hash mismatch")
    try:
        tolerance = float(value.get("tolerance_px"))
    except (TypeError, ValueError) as exc:
        raise IntegrityError("invalid plan tolerance_px") from exc
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise IntegrityError("invalid plan tolerance_px")
    try:
        dice_threshold = float(value.get("mask_dice_threshold"))
    except (TypeError, ValueError) as exc:
        raise IntegrityError("invalid plan mask_dice_threshold") from exc
    if not math.isfinite(dice_threshold) or not 0.0 <= dice_threshold <= 1.0:
        raise IntegrityError("invalid plan mask_dice_threshold")
    raw_tasks = value.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise IntegrityError("plan tasks must be a nonempty list")
    tasks: list[Week8Task] = []
    seen: set[str] = set()
    try:
        for item in raw_tasks:
            if not isinstance(item, dict):
                raise IntegrityError("plan task is not an object")
            task = _task_from_dict(item)
            if item.get("identity_version") != TASK_IDENTITY_VERSION:
                raise IntegrityError("task identity version mismatch")
            if item.get("experiment_id") != task.experiment_id:
                raise IntegrityError("task identity digest mismatch")
            if task.experiment_id in seen:
                raise IntegrityError("duplicate experiment_id in plan")
            seen.add(task.experiment_id)
            tasks.append(task)
    except (KeyError, TypeError, Week8ContractError) as exc:
        if isinstance(exc, IntegrityError):
            raise
        raise IntegrityError(f"invalid plan task: {exc}") from exc
    expected = _expected_counts(tasks)
    if value.get("expected_counts") != expected:
        raise IntegrityError("plan expected counts mismatch")
    if value.get("expected_counts_sha256") != canonical_sha256(expected):
        raise IntegrityError("plan expected-count hash mismatch")
    return value


def write_week8_plan(path: str | Path, plan: Mapping[str, Any]) -> None:
    verified = _verify_plan_payload(plan)
    target = Path(path)
    if target.exists():
        existing = verify_week8_plan(target)
        if existing["plan_sha256"] != verified["plan_sha256"]:
            raise IntegrityError("refusing to overwrite a different Week 8 plan")
        return
    _atomic_json(target, verified)


def verify_week8_plan(path_or_plan: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    raw = (
        _read_json(Path(path_or_plan))
        if isinstance(path_or_plan, (str, Path))
        else path_or_plan
    )
    if not isinstance(raw, Mapping):
        raise IntegrityError("Week 8 plan must be an object")
    return _verify_plan_payload(raw)


def _with_self_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    payload = dict(value)
    payload[key] = canonical_sha256(payload)
    return payload


def _verify_self_hash(value: Mapping[str, Any], key: str, description: str) -> dict[str, Any]:
    payload = dict(value)
    received = payload.pop(key, None)
    if not _is_sha256(received) or canonical_sha256(payload) != received:
        raise IntegrityError(f"{description} hash mismatch")
    payload[key] = received
    return payload


def _safe_pair_token(pair_id: str) -> str:
    return f"pair-{canonical_sha256({'pair_id': pair_id})[:20]}"


def _save_npy(path: Path, value: Any) -> None:
    array = np.asarray(value)
    if array.ndim not in {2, 3} or array.size == 0:
        raise Week8ContractError("observable images must be nonempty 2D or 2D+channel arrays")
    if not np.issubdtype(array.dtype, np.number):
        raise Week8ContractError("observable images must contain numeric values")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _contains_forbidden_label_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in _FORBIDDEN_LABEL_KEYS or lowered.startswith("tre_"):
                return str(key)
            nested = _contains_forbidden_label_key(item)
            if nested is not None:
                return nested
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested = _contains_forbidden_label_key(item)
            if nested is not None:
                return nested
    return None


def _populated_forbidden_label_key(value: Any, prefix: str = "") -> str | None:
    """Return the path of any populated label-only field in a nested value."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            lowered = name.strip().lower()
            if lowered in _FORBIDDEN_LABEL_KEYS or lowered.startswith("tre_"):
                empty_container = isinstance(item, (Mapping, list, tuple)) and len(item) == 0
                if item is not None and not empty_container:
                    return path
            nested = _populated_forbidden_label_key(item, path)
            if nested is not None:
                return nested
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            nested = _populated_forbidden_label_key(item, path)
            if nested is not None:
                return nested
    return None


def prepare_artifacts(
    output_dir: str | Path | Week8Paths,
    plan: Mapping[str, Any],
    observable_pairs: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
    *,
    development_only: bool = True,
) -> dict[str, Any]:
    """Persist observable arrays and a physically separate sealed label artifact.

    This is the only phase allowed to receive observable arrays and labels in
    the same call.  They are immediately written to disjoint directories and
    only hashes of the label artifacts enter the preparation receipt.
    """
    verified_plan = verify_week8_plan(plan)
    if development_only and verified_plan.get("mode") != "development_rehearsal":
        raise Week8ContractError("development preparation requires development_rehearsal mode")
    paths = _coerce_paths(output_dir)
    if verified_plan.get("mode") == "final":
        if (
            not paths.final_readiness_receipt.is_file()
            or sha256_file(paths.final_readiness_receipt)
            != verified_plan.get("final_readiness_receipt_sha256")
        ):
            raise IntegrityError("final readiness receipt is missing or differs from the frozen plan")
    if paths.decision_seal.exists() or paths.scientific_records.exists():
        raise Week8ContractError("cannot prepare over an existing decision run")
    write_week8_plan(paths.plan, verified_plan)

    tasks = [_task_from_dict(item) for item in verified_plan["tasks"]]
    expected_pair_ids = {task.pair.pair_id for task in tasks}
    if set(observable_pairs) != expected_pair_ids:
        raise Week8ContractError("observable pair IDs do not match the frozen plan")
    if set(labels) != expected_pair_ids:
        raise Week8ContractError("label pair IDs do not match the frozen plan")

    manifest_pairs: dict[str, dict[str, Any]] = {}
    for pair_id in sorted(expected_pair_ids):
        payload = observable_pairs[pair_id]
        if not isinstance(payload, Mapping):
            raise Week8ContractError(f"observable pair {pair_id!r} must be an object")
        forbidden = _contains_forbidden_label_key(payload.get("metadata", {}))
        if forbidden is not None:
            raise LabelFirewallError(
                f"observable metadata contains prohibited label field: {forbidden}"
            )
        if "fixed" not in payload or "moving" not in payload:
            raise Week8ContractError(
                f"observable pair {pair_id!r} must contain fixed and moving arrays"
            )
        token = _safe_pair_token(pair_id)
        fixed_path = paths.observable_inputs / token / "fixed.npy"
        moving_path = paths.observable_inputs / token / "moving.npy"
        _save_npy(fixed_path, payload["fixed"])
        _save_npy(moving_path, payload["moving"])
        fixed = np.asarray(payload["fixed"])
        moving = np.asarray(payload["moving"])
        if fixed.shape[:2] != moving.shape[:2]:
            raise Week8ContractError(f"observable pair {pair_id!r} has incompatible shapes")
        manifest_pairs[pair_id] = {
            "pair_id": pair_id,
            "fixed_path": fixed_path.relative_to(paths.prepared).as_posix(),
            "moving_path": moving_path.relative_to(paths.prepared).as_posix(),
            "fixed_sha256": sha256_file(fixed_path),
            "moving_sha256": sha256_file(moving_path),
            "fixed_shape": list(fixed.shape),
            "moving_shape": list(moving.shape),
            "fixed_dtype": str(fixed.dtype),
            "moving_dtype": str(moving.dtype),
            "metadata": _jsonable(dict(payload.get("metadata", {}))),
        }

    manifest = _with_self_hash(
        {
            "schema_version": "week08_observable_manifest_v1",
            "mode": verified_plan["mode"],
            "plan_sha256": verified_plan["plan_sha256"],
            "pair_count": len(manifest_pairs),
            "pairs": manifest_pairs,
            "contains_ground_truth": False,
        },
        "manifest_sha256",
    )
    _atomic_json(paths.observable_manifest, manifest)

    label_payload = {
        "schema_version": "week08_sealed_labels_v1",
        "plan_sha256": verified_plan["plan_sha256"],
        "labels": {pair_id: _jsonable(dict(labels[pair_id])) for pair_id in sorted(labels)},
    }
    _atomic_json(paths.sealed_labels, label_payload)
    label_manifest = _with_self_hash(
        {
            "schema_version": "week08_label_manifest_v1",
            "plan_sha256": verified_plan["plan_sha256"],
            "label_count": len(labels),
            "label_artifact": paths.sealed_labels.name,
            "label_artifact_sha256": sha256_file(paths.sealed_labels),
        },
        "manifest_sha256",
    )
    _atomic_json(paths.label_manifest, label_manifest)

    receipt = _with_self_hash(
        {
            "schema_version": PREPARE_SCHEMA_VERSION,
            "mode": verified_plan["mode"],
            "development_only": bool(development_only),
            "plan_sha256": verified_plan["plan_sha256"],
            "expected_counts_sha256": verified_plan["expected_counts_sha256"],
            "config_sha256": verified_plan["config_sha256"],
            "method_catalog_sha256": verified_plan["method_catalog_sha256"],
            "policy_sha256": verified_plan["policy_sha256"],
            "policy_gate_sha256": verified_plan["policy_gate_sha256"],
            "code_sha256": verified_plan["code_sha256"],
            "tolerance_px": verified_plan["tolerance_px"],
            "mask_dice_threshold": verified_plan["mask_dice_threshold"],
            "source_ledger_sha256": verified_plan["source_ledger_sha256"],
            "enrollment_manifest_sha256": verified_plan["enrollment_manifest_sha256"],
            "final_readiness_receipt_sha256": verified_plan["final_readiness_receipt_sha256"],
            "observable_manifest_sha256": sha256_file(paths.observable_manifest),
            "label_manifest_sha256": sha256_file(paths.label_manifest),
            "label_artifact_sha256": sha256_file(paths.sealed_labels),
            "prepared_pair_count": len(manifest_pairs),
        },
        "receipt_sha256",
    )
    _atomic_json(paths.prepare_receipt, receipt)
    return receipt


def _resolve_inside(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise IntegrityError("artifact path must be a nonempty relative string")
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise IntegrityError(f"artifact path escapes run root: {relative}") from exc
    return candidate


def _verify_prepared(paths: Week8Paths, *, verify_observable_bytes: bool) -> tuple[dict, dict, dict]:
    plan = verify_week8_plan(paths.plan)
    raw_manifest = _read_json(paths.observable_manifest)
    if not isinstance(raw_manifest, Mapping):
        raise IntegrityError("observable manifest is not an object")
    manifest = _verify_self_hash(raw_manifest, "manifest_sha256", "observable manifest")
    raw_receipt = _read_json(paths.prepare_receipt)
    if not isinstance(raw_receipt, Mapping):
        raise IntegrityError("prepare receipt is not an object")
    receipt = _verify_self_hash(raw_receipt, "receipt_sha256", "prepare receipt")
    expected_bindings = {
        "plan_sha256": plan["plan_sha256"],
        "expected_counts_sha256": plan["expected_counts_sha256"],
        "config_sha256": plan["config_sha256"],
        "method_catalog_sha256": plan["method_catalog_sha256"],
        "policy_sha256": plan["policy_sha256"],
        "policy_gate_sha256": plan["policy_gate_sha256"],
        "code_sha256": plan["code_sha256"],
        "tolerance_px": plan["tolerance_px"],
        "mask_dice_threshold": plan["mask_dice_threshold"],
        "source_ledger_sha256": plan["source_ledger_sha256"],
        "enrollment_manifest_sha256": plan["enrollment_manifest_sha256"],
        "final_readiness_receipt_sha256": plan["final_readiness_receipt_sha256"],
        "observable_manifest_sha256": sha256_file(paths.observable_manifest),
    }
    if plan.get("mode") == "final":
        if (
            not paths.final_readiness_receipt.is_file()
            or sha256_file(paths.final_readiness_receipt)
            != plan.get("final_readiness_receipt_sha256")
        ):
            raise IntegrityError("final readiness receipt changed after the plan was frozen")
    for name, expected in expected_bindings.items():
        if receipt.get(name) != expected:
            raise IntegrityError(f"prepare receipt {name} mismatch")
    if manifest.get("plan_sha256") != plan["plan_sha256"]:
        raise IntegrityError("observable manifest is bound to a different plan")
    pairs = manifest.get("pairs")
    if not isinstance(pairs, dict) or len(pairs) != plan["expected_counts"]["pairs"]:
        raise IntegrityError("observable manifest pair count mismatch")
    if verify_observable_bytes:
        for pair_id, item in pairs.items():
            if not isinstance(item, dict) or item.get("pair_id") != pair_id:
                raise IntegrityError("invalid observable manifest pair entry")
            for prefix in ("fixed", "moving"):
                artifact = _resolve_inside(paths.prepared, item.get(f"{prefix}_path"))
                try:
                    artifact.relative_to(paths.observable_inputs.resolve())
                except ValueError as exc:
                    raise IntegrityError(
                        f"observable {prefix} path is outside observable_inputs for {pair_id}"
                    ) from exc
                if not artifact.is_file() or sha256_file(artifact) != item.get(f"{prefix}_sha256"):
                    raise IntegrityError(f"observable {prefix} hash mismatch for {pair_id}")
    return plan, manifest, receipt


def gate_from_policy(policy_or_path: Mapping[str, Any] | str | Path) -> Gate:
    """Construct the unchanged observable-only gate from its frozen policy."""
    policy = (
        _read_json(Path(policy_or_path))
        if isinstance(policy_or_path, (str, Path))
        else policy_or_path
    )
    if not isinstance(policy, Mapping) or not isinstance(policy.get("gate"), Mapping):
        raise Week8ContractError("policy must contain a gate object")
    allowed = {
        "agreement_px", "overlap_floor", "min_feature_inlier",
        "min_feature_coverage", "min_distinct_families", "min_candidates",
    }
    values = {key: value for key, value in policy["gate"].items() if key in allowed}
    return Gate(**values)


def _contract_fingerprint(plan: Mapping[str, Any], manifest: Mapping[str, Any], receipt: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "plan_sha256": plan["plan_sha256"],
            "expected_counts_sha256": plan["expected_counts_sha256"],
            "config_sha256": plan["config_sha256"],
            "method_catalog_sha256": plan["method_catalog_sha256"],
            "policy_sha256": plan["policy_sha256"],
            "policy_gate_sha256": plan["policy_gate_sha256"],
            "code_sha256": plan["code_sha256"],
            "tolerance_px": plan["tolerance_px"],
            "mask_dice_threshold": plan["mask_dice_threshold"],
            "source_ledger_sha256": plan["source_ledger_sha256"],
            "enrollment_manifest_sha256": plan["enrollment_manifest_sha256"],
            "final_readiness_receipt_sha256": plan["final_readiness_receipt_sha256"],
            "observable_manifest_sha256": manifest["manifest_sha256"],
            "prepare_receipt_sha256": receipt["receipt_sha256"],
        }
    )


def _load_observable(paths: Week8Paths, item: Mapping[str, Any]) -> dict[str, Any]:
    fixed_path = _resolve_inside(paths.prepared, item["fixed_path"])
    moving_path = _resolve_inside(paths.prepared, item["moving_path"])
    for path in (fixed_path, moving_path):
        try:
            path.relative_to(paths.observable_inputs.resolve())
        except ValueError as exc:
            raise IntegrityError("observable path is outside observable_inputs") from exc
    try:
        fixed = np.load(fixed_path, allow_pickle=False)
        moving = np.load(moving_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise IntegrityError(f"cannot load observable arrays: {exc}") from exc
    return {
        "pair_id": item["pair_id"],
        "fixed": fixed,
        "moving": moving,
        "fixed_path": fixed_path,
        "moving_path": moving_path,
        "metadata": dict(item.get("metadata", {})),
    }


def _normalize_scientific_record(task: Week8Task, raw_result: Any) -> dict[str, Any]:
    if hasattr(raw_result, "to_dict") and callable(raw_result.to_dict):
        raw_result = raw_result.to_dict()
    if not isinstance(raw_result, Mapping):
        raise Week8ContractError("executor must return a mapping or to_dict() record")
    forbidden = _populated_forbidden_label_key(raw_result)
    if forbidden is not None:
        raise LabelFirewallError(f"executor returned prohibited label field: {forbidden}")
    metrics = raw_result.get("metrics", {})
    if isinstance(metrics, Mapping):
        prohibited_metrics = {
            str(key) for key in metrics
            if str(key).startswith("tre_") or str(key) in {"dice", "geometric_within_tolerance"}
        }
        if prohibited_metrics:
            raise LabelFirewallError(
                "decision-time record contains ground-truth metrics: "
                + ", ".join(sorted(prohibited_metrics))
            )
    status = str(raw_result.get("execution_status", "")).strip().lower()
    if status not in TERMINAL_SCIENTIFIC_STATUSES:
        raise Week8ContractError(f"invalid terminal scientific status: {status!r}")
    expected_identity = {
        "pair_id": task.pair.pair_id,
        "method_id": task.method.method_id,
        "method_family": task.method.method_family,
        "transform_model": task.pair.transform_model,
        "modality_class": task.pair.modality_class,
        "dimensions": task.pair.dimensions,
        "seed": task.method.method_seed,
    }
    for key, expected in expected_identity.items():
        if key in raw_result and raw_result[key] is not None and raw_result[key] != expected:
            raise Week8ContractError(
                f"executor identity mismatch for {key}: {raw_result[key]!r} != {expected!r}"
            )
    estimated = raw_result.get("estimated_transform")
    if estimated is not None:
        matrix = np.asarray(estimated, dtype=np.float64)
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
            raise Week8ContractError("estimated_transform must be a finite 3x3 matrix")
        estimated = matrix.tolist()
    diagnostics = raw_result.get("method_diagnostics", {})
    timings = raw_result.get("timings_ms", {})
    if not isinstance(diagnostics, Mapping) or not isinstance(timings, Mapping):
        raise Week8ContractError("diagnostics and timings must be mappings")
    warnings = raw_result.get("warnings", [])
    if not isinstance(warnings, (list, tuple)):
        raise Week8ContractError("warnings must be a list")
    return {
        **expected_identity,
        "execution_status": status,
        "estimated_transform": estimated,
        "transform_plausible": raw_result.get("transform_plausible"),
        "valid_overlap_fraction": raw_result.get("valid_overlap_fraction"),
        "timings_ms": _jsonable(dict(timings)),
        "method_diagnostics": _jsonable(dict(diagnostics)),
        "warnings": [str(value) for value in warnings],
        "failure_reason": raw_result.get("failure_reason"),
    }


def _scientific_envelope(task: Week8Task, record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": WEEK8_SCHEMA_VERSION,
        "experiment_id": task.experiment_id,
        "task": task.to_dict(),
        "record": dict(record),
    }


def _executor_task_view(task: Week8Task) -> dict[str, Any]:
    """Expose task identity but never plan metadata to a registration adapter."""
    view = task.to_dict()
    view.pop("pair_metadata", None)
    view.pop("method_metadata", None)
    return view


def _validate_existing_records(
    tasks_by_id: Mapping[str, Week8Task], records: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for envelope in records:
        experiment_id = str(envelope.get("experiment_id", ""))
        if experiment_id not in tasks_by_id:
            raise IntegrityError(f"scientific record not present in plan: {experiment_id}")
        if experiment_id in by_id:
            raise IntegrityError(f"duplicate terminal scientific record: {experiment_id}")
        task = tasks_by_id[experiment_id]
        if envelope.get("task") != task.to_dict():
            raise IntegrityError(f"scientific record task identity mismatch: {experiment_id}")
        record = envelope.get("record")
        if not isinstance(record, Mapping):
            raise IntegrityError(f"scientific record body is invalid: {experiment_id}")
        normalized = _normalize_scientific_record(task, record)
        expected = _scientific_envelope(task, normalized)
        if envelope != expected:
            raise IntegrityError(f"scientific record is not canonical: {experiment_id}")
        by_id[experiment_id] = dict(envelope)
    return by_id


def _policy_decisions(tasks: Sequence[Week8Task], records: Sequence[Mapping[str, Any]], gate: Gate) -> dict[str, Any]:
    tasks_by_pair: dict[str, list[Week8Task]] = defaultdict(list)
    envelopes_by_pair: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for task in tasks:
        tasks_by_pair[task.pair.pair_id].append(task)
    for envelope in records:
        envelopes_by_pair[str(envelope["record"]["pair_id"])].append(envelope)
    rows: list[dict[str, Any]] = []
    for pair_id in sorted(tasks_by_pair):
        group = tasks_by_pair[pair_id]
        if not _policy_eligible_pair(group):
            continue
        envelopes = envelopes_by_pair.get(pair_id, [])
        if len(envelopes) != len(group):
            rows.append(
                {
                    "pair_id": pair_id,
                    "decision": "missing_decision",
                    "reason": "incomplete_terminal_record_set",
                    "selected_id": None,
                    "support_ids": [],
                    "support_families": [],
                    "max_cross_family_displacement_px": None,
                }
            )
            continue
        try:
            observables = [project_observables(envelope) for envelope in envelopes]
            raw = select_pair(observables, gate)
            decision = "selected" if raw["decision"] == "tentative_supported" else "abstained"
            rows.append({"pair_id": pair_id, "decision": decision, **{k: raw.get(k) for k in (
                "reason", "selected_id", "support_ids", "support_families",
                "max_cross_family_displacement_px",
            )}})
        except (KeyError, TypeError, ValueError) as exc:
            rows.append(
                {
                    "pair_id": pair_id,
                    "decision": "invalid",
                    "reason": f"observable_policy_error:{type(exc).__name__}",
                    "selected_id": None,
                    "support_ids": [],
                    "support_families": [],
                    "max_cross_family_displacement_px": None,
                }
            )
    return {
        "schema_version": "week08_policy_decisions_v1",
        "eligible_pair_count": len(rows),
        "decisions": rows,
    }


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def _exclusive_decision_lock(
    paths: Week8Paths,
    *,
    resume: bool,
    retry_infrastructure: bool,
):
    """Prevent concurrent writers; stale locks require explicit infra resume."""
    paths.decision.mkdir(parents=True, exist_ok=True)
    lock_path = paths.decision / "runner.lock"

    def acquire() -> int:
        return os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    try:
        descriptor = acquire()
    except FileExistsError as exc:
        try:
            initial_stat = lock_path.stat()
            value = json.loads(lock_path.read_text(encoding="utf-8"))
            owner_pid = int(value.get("pid", -1)) if isinstance(value, dict) else -1
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            initial_stat = None
            owner_pid = -1
        if _pid_is_alive(owner_pid):
            raise InfrastructureError(
                f"another decision runner holds {lock_path} (pid={owner_pid})"
            ) from exc
        if not (resume and retry_infrastructure):
            raise InfrastructureError(
                "stale decision lock requires --resume and --retry-infrastructure"
            ) from exc
        if initial_stat is None or time.time() - initial_stat.st_mtime < 2.0:
            raise InfrastructureError(
                "decision lock owner is unresolved; wait before explicit stale-lock recovery"
            ) from exc
        try:
            current_stat = lock_path.stat()
            if (
                current_stat.st_ino != initial_stat.st_ino
                or current_stat.st_mtime_ns != initial_stat.st_mtime_ns
                or current_stat.st_size != initial_stat.st_size
            ):
                raise InfrastructureError("decision lock changed during stale-lock verification")
            lock_path.unlink()
            descriptor = acquire()
        except (OSError, FileExistsError) as retry_exc:
            raise InfrastructureError("could not replace stale decision lock") from retry_exc
    try:
        os.write(descriptor, canonical_json({"pid": os.getpid()}).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        yield
    finally:
        try:
            value = json.loads(lock_path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and int(value.get("pid", -1)) == os.getpid():
                lock_path.unlink()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Never unlink an unreadable or replaced lock owned by another process.
            pass


class Week8DecisionRunner:
    """Execute all planned attempts without opening or interpreting labels."""

    def __init__(self, output_dir: str | Path | Week8Paths, gate: Gate | None = None):
        self.paths = _coerce_paths(output_dir)
        self.gate = Gate() if gate is None else gate

    def run(
        self,
        executor: Callable[[dict[str, Any], dict[str, Any]], Any],
        *,
        resume: bool = False,
        retry_infrastructure: bool = False,
    ) -> dict[str, Any]:
        with _exclusive_decision_lock(
            self.paths,
            resume=resume,
            retry_infrastructure=retry_infrastructure,
        ):
            return self._run_locked(
                executor,
                resume=resume,
                retry_infrastructure=retry_infrastructure,
            )

    def _run_locked(
        self,
        executor: Callable[[dict[str, Any], dict[str, Any]], Any],
        *,
        resume: bool,
        retry_infrastructure: bool,
    ) -> dict[str, Any]:
        plan, manifest, receipt = _verify_prepared(self.paths, verify_observable_bytes=True)
        if canonical_sha256(_gate_dict(self.gate)) != plan["policy_gate_sha256"]:
            raise IntegrityError("runner gate differs from the gate bound into the frozen plan")
        self.paths.decision.mkdir(parents=True, exist_ok=True)
        self.paths.attempt_events.touch(exist_ok=True)
        self.paths.scientific_records.touch(exist_ok=True)
        tasks = [_task_from_dict(value) for value in plan["tasks"]]
        tasks_by_id = {task.experiment_id: task for task in tasks}
        contract = _contract_fingerprint(plan, manifest, receipt)
        existing_records = _read_jsonl(self.paths.scientific_records)
        records_by_id = _validate_existing_records(tasks_by_id, existing_records)
        events = _read_jsonl(self.paths.attempt_events)
        allowed_events = {
            "attempt_started", "infrastructure_error", "scientific_outcome", "contract_error",
        }
        for event in events:
            if event.get("experiment_id") not in tasks_by_id:
                raise IntegrityError("attempt event is not in frozen plan")
            if event.get("contract_sha256") != contract:
                raise IntegrityError("resume contract differs from prior attempt event")
            if event.get("event") not in allowed_events:
                raise IntegrityError("unknown attempt event")
        if any(event.get("event") == "contract_error" for event in events):
            raise IntegrityError("prior executor contract/firewall error permanently blocks resume")
        outcome_counts = Counter(
            str(event["experiment_id"])
            for event in events
            if event.get("event") == "scientific_outcome"
        )
        if any(count != 1 for count in outcome_counts.values()):
            raise IntegrityError("attempt journal has duplicate scientific outcomes")
        if any(experiment_id not in records_by_id for experiment_id in outcome_counts):
            raise IntegrityError("scientific outcome event has no terminal record")
        if self.paths.decision_seal.exists():
            _verify_decision_artifacts(self.paths, plan, manifest, receipt)
            return {
                "sealed": True,
                "planned_attempts": len(tasks),
                "terminal_records": len(records_by_id),
                "preexisting_terminal": len(records_by_id),
                "infrastructure_errors": sum(e.get("event") == "infrastructure_error" for e in events),
                "executed_this_call": 0,
            }
        has_prior_state = bool(existing_records or events)
        if has_prior_state and not (resume and retry_infrastructure):
            # Partial-run continuation always requires both explicit flags,
            # including tasks that had not started when the process stopped.
            return {
                "sealed": False,
                "planned_attempts": len(tasks),
                "terminal_records": len(records_by_id),
                "preexisting_terminal": len(records_by_id),
                "infrastructure_errors": sum(e.get("event") == "infrastructure_error" for e in events),
                "executed_this_call": 0,
            }
        infrastructure_counts = Counter(
            str(event["experiment_id"])
            for event in events
            if event.get("event") == "infrastructure_error"
        )
        start_counts = Counter(
            str(event["experiment_id"])
            for event in events
            if event.get("event") == "attempt_started"
        )

        def append_infrastructure(
            experiment_id: str,
            *,
            attempt_number: int,
            error_type: str,
            error: str,
        ) -> None:
            _append_jsonl(
                self.paths.attempt_events,
                {
                    "schema_version": WEEK8_SCHEMA_VERSION,
                    "event": "infrastructure_error",
                    "experiment_id": experiment_id,
                    "contract_sha256": contract,
                    "attempt_number": int(attempt_number),
                    "error_type": error_type,
                    "error": error[:500],
                },
            )
            infrastructure_counts[experiment_id] += 1

        def append_outcome(experiment_id: str, envelope: Mapping[str, Any]) -> None:
            _append_jsonl(
                self.paths.attempt_events,
                {
                    "schema_version": WEEK8_SCHEMA_VERSION,
                    "event": "scientific_outcome",
                    "experiment_id": experiment_id,
                    "contract_sha256": contract,
                    "record_sha256": canonical_sha256(envelope),
                    "execution_status": envelope["record"]["execution_status"],
                },
            )
            outcome_counts[experiment_id] += 1

        # Recover a crash after the durable terminal record but before its
        # journal event.  Never reexecute that scientific outcome.
        if has_prior_state:
            for task in tasks:
                experiment_id = task.experiment_id
                if experiment_id in records_by_id and outcome_counts[experiment_id] == 0:
                    append_infrastructure(
                        experiment_id,
                        attempt_number=max(1, start_counts[experiment_id]),
                        error_type="JournalInterruptionAfterRecord",
                        error="terminal record persisted before scientific_outcome event",
                    )
                    append_outcome(experiment_id, records_by_id[experiment_id])

        executed = 0
        for task in tasks:
            experiment_id = task.experiment_id
            if experiment_id in records_by_id and outcome_counts[experiment_id] == 1:
                continue
            if has_prior_state and not any(
                event.get("experiment_id") == experiment_id for event in events
            ):
                append_infrastructure(
                    experiment_id,
                    attempt_number=0,
                    error_type="RunInterruptedBeforeAttempt",
                    error="prior process ended before this planned task started",
                )
            elif (
                has_prior_state
                and start_counts[experiment_id] > infrastructure_counts[experiment_id]
                and outcome_counts[experiment_id] == 0
            ):
                append_infrastructure(
                    experiment_id,
                    attempt_number=start_counts[experiment_id],
                    error_type="InterruptedAttempt",
                    error="attempt_started had no durable outcome",
                )
            prior_infrastructure = infrastructure_counts[experiment_id]
            if prior_infrastructure >= 2:
                continue
            observable_item = manifest["pairs"][task.pair.pair_id]
            observable = _load_observable(self.paths, observable_item)
            view = _executor_task_view(task)
            attempt_number = start_counts[experiment_id] + 1
            _append_jsonl(
                self.paths.attempt_events,
                {
                    "schema_version": WEEK8_SCHEMA_VERSION,
                    "event": "attempt_started",
                    "experiment_id": experiment_id,
                    "contract_sha256": contract,
                    "attempt_number": attempt_number,
                },
            )
            start_counts[experiment_id] += 1
            try:
                result = executor(view, observable)
                record = _normalize_scientific_record(task, result)
            except Week8ContractError as exc:
                _append_jsonl(
                    self.paths.attempt_events,
                    {
                        "schema_version": WEEK8_SCHEMA_VERSION,
                        "event": "contract_error",
                        "experiment_id": experiment_id,
                        "contract_sha256": contract,
                        "attempt_number": attempt_number,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    },
                )
                raise
            except Exception as exc:
                append_infrastructure(
                    experiment_id,
                    attempt_number=attempt_number,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                executed += 1
                continue
            envelope = _scientific_envelope(task, record)
            _append_jsonl(self.paths.scientific_records, envelope)
            append_outcome(experiment_id, envelope)
            records_by_id[experiment_id] = envelope
            executed += 1

        if len(records_by_id) != len(tasks):
            return {
                "sealed": False,
                "planned_attempts": len(tasks),
                "terminal_records": len(records_by_id),
                "preexisting_terminal": len(existing_records),
                "infrastructure_errors": sum(infrastructure_counts.values()),
                "executed_this_call": executed,
                "unresolved_attempts": len(tasks) - len(records_by_id),
            }

        ordered_records = [records_by_id[task.experiment_id] for task in tasks]
        policy = _policy_decisions(tasks, ordered_records, self.gate)
        _atomic_json(self.paths.policy_decisions, policy)
        seal_payload = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "plan_sha256": plan["plan_sha256"],
            "expected_counts_sha256": plan["expected_counts_sha256"],
            "config_sha256": plan["config_sha256"],
            "method_catalog_sha256": plan["method_catalog_sha256"],
            "policy_sha256": plan["policy_sha256"],
            "policy_gate_sha256": plan["policy_gate_sha256"],
            "code_sha256": plan["code_sha256"],
            "tolerance_px": plan["tolerance_px"],
            "mask_dice_threshold": plan["mask_dice_threshold"],
            "source_ledger_sha256": plan["source_ledger_sha256"],
            "enrollment_manifest_sha256": plan["enrollment_manifest_sha256"],
            "final_readiness_receipt_sha256": plan["final_readiness_receipt_sha256"],
            "observable_manifest_sha256": sha256_file(self.paths.observable_manifest),
            "prepare_receipt_sha256": sha256_file(self.paths.prepare_receipt),
            "attempt_events_sha256": sha256_file(self.paths.attempt_events),
            "scientific_records_sha256": sha256_file(self.paths.scientific_records),
            "policy_decisions_sha256": sha256_file(self.paths.policy_decisions),
            "terminal_record_count": len(records_by_id),
            "policy_eligible_pair_count": policy["eligible_pair_count"],
            "label_accessed": False,
        }
        seal = _with_self_hash(seal_payload, "seal_sha256")
        _atomic_json(self.paths.decision_seal, seal)
        return {
            "sealed": True,
            "planned_attempts": len(tasks),
            "terminal_records": len(records_by_id),
            "preexisting_terminal": len(existing_records),
            "infrastructure_errors": sum(infrastructure_counts.values()),
            "executed_this_call": executed,
            "policy_eligible_pairs": policy["eligible_pair_count"],
            "decision_seal_sha256": seal["seal_sha256"],
        }


def _verify_decision_artifacts(
    paths: Week8Paths,
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not paths.decision_seal.is_file():
        raise LabelFirewallError("decision seal is missing; labels remain closed")
    raw_seal = _read_json(paths.decision_seal)
    if not isinstance(raw_seal, Mapping):
        raise IntegrityError("decision seal is not an object")
    seal = _verify_self_hash(raw_seal, "seal_sha256", "decision seal")
    required_files = (
        paths.attempt_events,
        paths.scientific_records,
        paths.policy_decisions,
    )
    if any(not path.is_file() for path in required_files):
        raise IntegrityError("sealed decision artifact is missing")
    bindings = {
        "plan_sha256": plan["plan_sha256"],
        "expected_counts_sha256": plan["expected_counts_sha256"],
        "config_sha256": plan["config_sha256"],
        "method_catalog_sha256": plan["method_catalog_sha256"],
        "policy_sha256": plan["policy_sha256"],
        "policy_gate_sha256": plan["policy_gate_sha256"],
        "code_sha256": plan["code_sha256"],
        "tolerance_px": plan["tolerance_px"],
        "mask_dice_threshold": plan["mask_dice_threshold"],
        "source_ledger_sha256": plan["source_ledger_sha256"],
        "enrollment_manifest_sha256": plan["enrollment_manifest_sha256"],
        "final_readiness_receipt_sha256": plan["final_readiness_receipt_sha256"],
        "observable_manifest_sha256": sha256_file(paths.observable_manifest),
        "prepare_receipt_sha256": sha256_file(paths.prepare_receipt),
        "attempt_events_sha256": sha256_file(paths.attempt_events),
        "scientific_records_sha256": sha256_file(paths.scientific_records),
        "policy_decisions_sha256": sha256_file(paths.policy_decisions),
    }
    for name, expected in bindings.items():
        if seal.get(name) != expected:
            raise IntegrityError(f"decision seal {name} mismatch")
    if seal.get("label_accessed") is not False:
        raise IntegrityError("decision seal must attest no prior label access")

    tasks = [_task_from_dict(value) for value in plan["tasks"]]
    tasks_by_id = {task.experiment_id: task for task in tasks}
    records = _read_jsonl(paths.scientific_records)
    records_by_id = _validate_existing_records(tasks_by_id, records)
    if set(records_by_id) != set(tasks_by_id):
        raise IncompleteDecisionError("not every planned attempt has one terminal record")
    if seal.get("terminal_record_count") != len(tasks):
        raise IntegrityError("decision seal terminal count mismatch")

    events = _read_jsonl(paths.attempt_events)
    contract = _contract_fingerprint(plan, manifest, receipt)
    outcome_ids: list[str] = []
    started_ids: list[str] = []
    infrastructure_ids: list[str] = []
    for event in events:
        experiment_id = str(event.get("experiment_id", ""))
        if experiment_id not in tasks_by_id or event.get("contract_sha256") != contract:
            raise IntegrityError("attempt event identity/contract mismatch")
        kind = event.get("event")
        if kind == "scientific_outcome":
            outcome_ids.append(experiment_id)
            if event.get("record_sha256") != canonical_sha256(records_by_id[experiment_id]):
                raise IntegrityError("scientific outcome event record hash mismatch")
        elif kind == "attempt_started":
            started_ids.append(experiment_id)
        elif kind == "infrastructure_error":
            infrastructure_ids.append(experiment_id)
        elif kind == "contract_error":
            raise IntegrityError("sealed journal contains a contract/firewall error")
        else:
            raise IntegrityError("unknown attempt event type")
    if Counter(outcome_ids) != Counter(tasks_by_id.keys()):
        raise IntegrityError("attempt journal does not contain exactly one outcome per task")
    starts = Counter(started_ids)
    if any(starts[experiment_id] not in {1, 2} for experiment_id in tasks_by_id):
        raise IntegrityError("each scientific outcome must have one initial start and at most one retry")
    if any(count > 2 for count in Counter(infrastructure_ids).values()):
        raise IntegrityError("infrastructure retry limit exceeded")

    policy = _read_json(paths.policy_decisions)
    if not isinstance(policy, dict) or policy.get("schema_version") != "week08_policy_decisions_v1":
        raise IntegrityError("invalid policy decision artifact")
    decisions = policy.get("decisions")
    if not isinstance(decisions, list):
        raise IntegrityError("policy decisions must be a list")
    eligible = plan["expected_counts"]["policy_eligible_pairs"]
    if policy.get("eligible_pair_count") != eligible or len(decisions) != eligible:
        raise IntegrityError("policy eligible-pair count mismatch")
    pair_ids = [str(item.get("pair_id", "")) for item in decisions if isinstance(item, dict)]
    if len(pair_ids) != len(set(pair_ids)) or len(pair_ids) != eligible:
        raise IntegrityError("duplicate or invalid policy pair decisions")
    allowed_states = {"selected", "abstained", "invalid", "missing_decision"}
    if any(item.get("decision") not in allowed_states for item in decisions):
        raise IntegrityError("invalid policy decision state")
    if seal.get("policy_eligible_pair_count") != eligible:
        raise IntegrityError("decision seal policy count mismatch")
    expected_policy = _policy_decisions(
        tasks,
        [records_by_id[task.experiment_id] for task in tasks],
        Gate(**plan["policy_gate"]),
    )
    if policy != expected_policy:
        raise IntegrityError("policy decisions do not match the frozen observable-only gate")
    return records, policy, seal, events


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "value": None if denominator == 0 else float(numerator / denominator),
    }


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    numbers = [number for value in values if (number := _finite_float(value)) is not None]
    if not numbers:
        return {"count": 0, "mean": None, "median": None, "p95": None, "minimum": None, "maximum": None}
    array = np.asarray(numbers, dtype=np.float64)
    return {
        "count": len(numbers),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def _rate_uncertainty(rate: Mapping[str, Any]) -> dict[str, Any]:
    low, high = wilson_interval(int(rate["numerator"]), int(rate["denominator"]))
    return {"method": "wilson_95", "lower": low, "upper": high}


def _track_a_subset_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_gt = sum(row.get("geometric_reference_valid") is True for row in rows)
    evaluable = sum(row.get("geometric_within_tolerance") is not None for row in rows)
    successes = sum(row.get("geometric_within_tolerance") is True for row in rows)
    completed = sum(row.get("execution_status") == "completed" for row in rows)
    infrastructure = sum(row.get("infrastructure_incident") is True for row in rows)
    rates = {
        "geometric_success_rate": _rate(successes, valid_gt),
        "conditional_accuracy": _rate(successes, evaluable),
        "execution_completion_rate": _rate(completed, len(rows)),
        "infrastructure_incident_rate": _rate(infrastructure, len(rows)),
    }
    return {
        "attempts": len(rows),
        "interpretation": "descriptive_low_count" if len(rows) < 5 else "preregistered_stratum",
        "status_counts": dict(sorted(Counter(str(row.get("execution_status")) for row in rows).items())),
        "valid_gt_attempts": valid_gt,
        "geometrically_evaluable_completed_attempts": evaluable,
        "geometric_successes": successes,
        **rates,
        "uncertainty": {name: _rate_uncertainty(rate) for name, rate in rates.items()},
        "total_runtime_ms": _numeric_summary(row.get("total_runtime_ms") for row in rows),
        "method_runtime_ms": _numeric_summary(row.get("method_runtime_ms") for row in rows),
        "valid_overlap_fraction": _numeric_summary(row.get("valid_overlap_fraction") for row in rows),
    }


def _track_b_subset_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = sum(row.get("decision") == "selected" for row in rows)
    abstained = sum(row.get("decision") == "abstained" for row in rows)
    invalid = sum(row.get("decision") == "invalid" for row in rows)
    missing = sum(row.get("decision") == "missing_decision" for row in rows)
    correct = sum(
        row.get("decision") == "selected"
        and row.get("selected_geometrically_correct") is True
        for row in rows
    )
    rates = {
        "coverage": _rate(selected, len(rows)),
        "selective_correctness": _rate(correct, selected),
        "abstention_rate": _rate(abstained, len(rows)),
        "invalid_rate": _rate(invalid, len(rows)),
        "missing_decision_rate": _rate(missing, len(rows)),
    }
    return {
        "eligible_pairs": len(rows),
        "interpretation": "descriptive_low_count" if len(rows) < 5 else "preregistered_stratum",
        "selected_pairs": selected,
        "abstained_pairs": abstained,
        "invalid_pairs": invalid,
        "missing_decision_pairs": missing,
        "correct_selected_pairs": correct,
        **rates,
        "uncertainty": {name: _rate_uncertainty(rate) for name, rate in rates.items()},
    }


def _stratified_summaries(
    rows: Sequence[Mapping[str, Any]],
    summary: Callable[[Sequence[Mapping[str, Any]]], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for dimension in MANDATORY_STRATA:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get(dimension, "<missing>"))].append(row)
        output[dimension] = [
            {dimension: key, **summary(group)}
            for key, group in sorted(groups.items())
        ]
    return output


def _exact_mcnemar_p_value(a_only: int, b_only: int) -> float:
    discordant = int(a_only) + int(b_only)
    if discordant == 0:
        return 1.0
    tail = min(int(a_only), int(b_only))
    cumulative = sum(math.comb(discordant, k) for k in range(tail + 1)) / (2 ** discordant)
    return float(min(1.0, 2.0 * cumulative))


def _pairwise_method_comparisons(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_method_pair: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rows:
        outcome = row.get("geometric_within_tolerance")
        if outcome is None:
            continue
        method_key = f"{row.get('method_id')}::{row.get('config_id')}"
        pair_id = str(row.get("pair_id"))
        if pair_id in by_method_pair[method_key]:
            raise IntegrityError(f"duplicate pair/method result in pairwise comparison: {pair_id}/{method_key}")
        by_method_pair[method_key][pair_id] = bool(outcome)
    methods = sorted(by_method_pair)
    output: list[dict[str, Any]] = []
    for index, method_a in enumerate(methods):
        for method_b in methods[index + 1:]:
            common = sorted(set(by_method_pair[method_a]) & set(by_method_pair[method_b]))
            if not common:
                continue
            both_success = both_failure = a_only = b_only = 0
            for pair_id in common:
                a = by_method_pair[method_a][pair_id]
                b = by_method_pair[method_b][pair_id]
                both_success += int(a and b)
                both_failure += int(not a and not b)
                a_only += int(a and not b)
                b_only += int(not a and b)
            output.append(
                {
                    "method_a": method_a,
                    "method_b": method_b,
                    "common_denominator": len(common),
                    "both_success": both_success,
                    "both_failure": both_failure,
                    "method_a_only_success": a_only,
                    "method_b_only_success": b_only,
                    "method_a_successes": both_success + a_only,
                    "method_b_successes": both_success + b_only,
                    "mcnemar_exact_two_sided_p": _exact_mcnemar_p_value(a_only, b_only),
                }
            )
    return output


def _diagnostic_availability(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("method_id"))].append(row)
    output: list[dict[str, Any]] = []
    for method_id, group in sorted(groups.items()):
        counts: Counter[str] = Counter()
        for row in group:
            for key in row.get("diagnostic_keys", []):
                counts[str(key)] += 1
        output.append(
            {
                "method_id": method_id,
                "attempts": len(group),
                "diagnostic_key_counts": dict(sorted(counts.items())),
            }
        )
    return output


def _recommendation_validation(
    *,
    mode: str,
    decision_rows: Sequence[Mapping[str, Any]],
    criteria: Mapping[str, Any],
    no_post_label_change_attested: bool,
) -> dict[str, Any]:
    independent = [row for row in decision_rows if row.get("source_role") == "full_project_independent"]
    selected = [row for row in independent if row.get("decision") == "selected"]
    correct = sum(row.get("selected_geometrically_correct") is True for row in selected)
    coverage = _rate(len(selected), len(independent))
    precision = _rate(correct, len(selected))
    lower, upper = wilson_interval(correct, len(selected))
    missing = sum(row.get("decision") == "missing_decision" for row in independent)
    checks = {
        "final_evidence_mode": mode != "development_rehearsal",
        "minimum_selected_pairs": len(selected) >= int(criteria["minimum_selected_pairs"]),
        "minimum_coverage": coverage["value"] is not None and coverage["value"] >= float(criteria["minimum_coverage"]),
        "minimum_selective_correctness": precision["value"] is not None and precision["value"] >= float(criteria["minimum_selective_correctness"]),
        "minimum_selective_correctness_wilson_lower_95": lower is not None and lower >= float(criteria["minimum_selective_correctness_wilson_lower_95"]),
        "maximum_missing_decisions": missing <= int(criteria["maximum_missing_decisions"]),
        "no_firewall_or_integrity_incident": True,
        "no_post_label_change": bool(no_post_label_change_attested),
    }
    limited = all(checks.values())
    distinct_sources = len({str(row.get("source_id")) for row in independent})
    real_verified = any(
        row.get("ground_truth_type") in {"verified_landmarks", "verified_masks"}
        for row in independent
    )
    stratum_direction: dict[str, list[dict[str, Any]]] = {}
    consistent_direction = True
    minimum_precision = float(criteria["minimum_selective_correctness"])
    for dimension in MANDATORY_STRATA:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in independent:
            groups[str(row.get(dimension, "<missing>"))].append(row)
        summaries: list[dict[str, Any]] = []
        for value, group in sorted(groups.items()):
            selected_group = [row for row in group if row.get("decision") == "selected"]
            correct_group = sum(row.get("selected_geometrically_correct") is True for row in selected_group)
            rate = _rate(correct_group, len(selected_group))
            supports_direction = (
                rate["value"] is not None and rate["value"] >= minimum_precision
            )
            consistent_direction = consistent_direction and supports_direction
            summaries.append(
                {
                    dimension: value,
                    "selected_pairs": len(selected_group),
                    "correct_selected_pairs": correct_group,
                    "selective_correctness": rate,
                    "supports_consistent_direction": supports_direction,
                }
            )
        stratum_direction[dimension] = summaries
    if not independent:
        consistent_direction = False
    broad = (
        limited
        and distinct_sources >= int(criteria["minimum_distinct_independent_sources_for_broad_support"])
        and (
            not bool(criteria["broad_support_requires_real_verified_gt"])
            or real_verified
        )
        and consistent_direction
    )
    return {
        "candidate_status_before_evaluation": "exploratory_not_deployed",
        "outcome": (
            "broad_cross_source_support" if broad
            else "limited_independent_support" if limited
            else "preserve_results_keep_policy_non_deployed"
        ),
        "development_fixture_cannot_validate_recommendation": mode == "development_rehearsal",
        "independent_eligible_pairs": len(independent),
        "selected_pairs": len(selected),
        "correct_selected_pairs": correct,
        "coverage": coverage,
        "selective_correctness": precision,
        "selective_correctness_wilson_95": {"lower": lower, "upper": upper},
        "missing_decisions": missing,
        "distinct_independent_sources": distinct_sources,
        "has_real_verified_gt_subset": real_verified,
        "consistent_direction_in_mandatory_strata": consistent_direction,
        "mandatory_stratum_direction": stratum_direction,
        "checks": checks,
    }


def _reference_points(shape: Sequence[int]) -> np.ndarray:
    if len(shape) < 2:
        raise IntegrityError("observable image shape is invalid")
    height, width = int(shape[0]), int(shape[1])
    return np.array(
        [
            [0.2 * (width - 1), 0.2 * (height - 1)],
            [0.8 * (width - 1), 0.2 * (height - 1)],
            [0.8 * (width - 1), 0.8 * (height - 1)],
            [0.2 * (width - 1), 0.8 * (height - 1)],
            [0.5 * (width - 1), 0.5 * (height - 1)],
        ],
        dtype=np.float64,
    )


def _tre_summary(
    reference_transform: Any,
    estimated_transform: Any,
    source_points: Any,
) -> dict[str, float]:
    reference = np.asarray(reference_transform, dtype=np.float64)
    estimated = np.asarray(estimated_transform, dtype=np.float64)
    points = np.asarray(source_points, dtype=np.float64)
    if reference.shape != (3, 3) or estimated.shape != (3, 3):
        raise IntegrityError("ground-truth and estimated transforms must be 3x3")
    if points.ndim != 2 or points.shape[1] != 2 or not len(points):
        raise IntegrityError("TRE source points must have shape (N,2)")
    homogeneous = np.column_stack((points, np.ones(len(points), dtype=np.float64)))
    reference_out = homogeneous @ reference.T
    estimated_out = homogeneous @ estimated.T
    if np.any(np.abs(reference_out[:, 2]) < 1e-12) or np.any(np.abs(estimated_out[:, 2]) < 1e-12):
        raise IntegrityError("transform produced a point at infinity")
    reference_xy = reference_out[:, :2] / reference_out[:, 2:]
    estimated_xy = estimated_out[:, :2] / estimated_out[:, 2:]
    errors = np.linalg.norm(reference_xy - estimated_xy, axis=1)
    return {
        "tre_mean_px": float(np.mean(errors)),
        "tre_median_px": float(np.median(errors)),
        "tre_p95_px": float(np.percentile(errors, 95)),
    }


def _validate_label_for_task(
    task: Week8Task,
    label: Mapping[str, Any],
    observable_item: Mapping[str, Any],
) -> bool:
    """Validate the exact preregistered endpoint for a sealed pair label."""
    pair = task.pair
    if label.get("pair_id") != pair.pair_id:
        raise IntegrityError(f"sealed label pair_id mismatch for {pair.pair_id}")
    for name, expected in {
        "ground_truth_type": pair.ground_truth_type,
        "evaluation_role": pair.evaluation_role,
        "source_role": pair.source_role,
    }.items():
        if label.get(name) != expected:
            raise IntegrityError(f"sealed label {name} mismatch for {pair.pair_id}")

    transform_keys = ("ground_truth_transform", "moving_to_fixed")
    landmark_keys = ("fixed_landmarks", "moving_landmarks")
    mask_keys = ("fixed_mask", "moving_mask")
    payload_keys = (*transform_keys, *landmark_keys, *mask_keys)
    if pair.ground_truth_type == "unavailable":
        if pair.source_role != "real_technical_only":
            raise IntegrityError("unavailable ground truth must use real_technical_only role")
        if label.get("has_geometric_ground_truth") is not False:
            raise IntegrityError("technical-only label must explicitly deny geometric ground truth")
        if any(label.get(name) is not None for name in payload_keys):
            raise IntegrityError("technical-only label contains a geometric payload")
        return False

    if label.get("has_geometric_ground_truth") is not True:
        raise IntegrityError("known-GT label must explicitly attest geometric ground truth")
    if label.get("coordinate_units") != "pixels":
        raise IntegrityError("Week 8 geometric labels must use pixel coordinates")
    if label.get("transform_direction") != "moving_to_fixed":
        raise IntegrityError("Week 8 geometric labels must use moving_to_fixed direction")

    gt_type = pair.ground_truth_type
    if gt_type == "synthetic_created_after_freeze":
        references = [label.get(name) for name in transform_keys if label.get(name) is not None]
        if len(references) != 1 or any(label.get(name) is not None for name in (*landmark_keys, *mask_keys)):
            raise IntegrityError("synthetic label must contain exactly one transform reference")
        reference = np.asarray(references[0], dtype=np.float64)
        if reference.shape != (3, 3) or not np.isfinite(reference).all():
            raise IntegrityError("synthetic ground-truth transform must be a finite 3x3 matrix")
        points = label.get("control_points_moving")
        if points is not None:
            array = np.asarray(points, dtype=np.float64)
            if array.ndim != 2 or array.shape[1] != 2 or not len(array) or not np.isfinite(array).all():
                raise IntegrityError("synthetic control points must be finite (N,2) coordinates")
        return True

    if gt_type == "verified_landmarks":
        if any(label.get(name) is not None for name in (*transform_keys, *mask_keys)):
            raise IntegrityError("verified-landmark label contains a different endpoint type")
        fixed = np.asarray(label.get("fixed_landmarks"), dtype=np.float64)
        moving = np.asarray(label.get("moving_landmarks"), dtype=np.float64)
        if (
            fixed.ndim != 2 or moving.ndim != 2
            or fixed.shape != moving.shape or fixed.shape[1:] != (2,)
            or len(fixed) == 0 or not np.isfinite(fixed).all() or not np.isfinite(moving).all()
        ):
            raise IntegrityError("verified landmarks must be matching finite nonempty (N,2) arrays")
        return True

    if gt_type == "verified_masks":
        if any(label.get(name) is not None for name in (*transform_keys, *landmark_keys)):
            raise IntegrityError("verified-mask label contains a different endpoint type")
        fixed = np.asarray(label.get("fixed_mask"))
        moving = np.asarray(label.get("moving_mask"))
        fixed_shape = tuple(int(value) for value in observable_item.get("fixed_shape", [])[:2])
        moving_shape = tuple(int(value) for value in observable_item.get("moving_shape", [])[:2])
        if fixed.ndim != 2 or moving.ndim != 2:
            raise IntegrityError("verified masks must be 2D")
        if fixed.shape != fixed_shape or moving.shape != moving_shape:
            raise IntegrityError("verified mask shapes must match their observable images")
        if not np.all(np.isin(fixed, [0, 1, False, True])) or not np.all(
            np.isin(moving, [0, 1, False, True])
        ):
            raise IntegrityError("verified masks must be binary")
        if not np.any(fixed) or not np.any(moving):
            raise IntegrityError("verified masks must each contain foreground")
        return True

    raise IntegrityError(f"unsupported sealed-label endpoint: {gt_type}")


def evaluate_sealed_run(
    output_dir: str | Path | Week8Paths,
    *,
    label_loader: Callable[[Path], Any] | None = None,
    tolerance_px: float = 2.0,
    recommendation_criteria: Mapping[str, Any] | None = None,
    no_post_label_change_attested: bool = False,
    track_a_table: str | Path | None = None,
    track_b_table: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the complete decision seal, then and only then open labels."""
    if not math.isfinite(float(tolerance_px)) or float(tolerance_px) <= 0:
        raise Week8ContractError("tolerance_px must be finite and positive")
    paths = _coerce_paths(output_dir)
    plan, manifest, receipt = _verify_prepared(paths, verify_observable_bytes=True)
    if not math.isclose(float(tolerance_px), float(plan["tolerance_px"]), rel_tol=0.0, abs_tol=1e-12):
        raise IntegrityError("evaluation tolerance differs from the frozen plan")
    records, policy, seal, events = _verify_decision_artifacts(
        paths, plan, manifest, receipt
    )

    # Non-label artifacts have fully verified.  Now verify the sealed label
    # bytes against the preparation receipt before any parser/loader sees them.
    raw_label_manifest = _read_json(paths.label_manifest)
    if not isinstance(raw_label_manifest, Mapping):
        raise IntegrityError("label manifest is not an object")
    label_manifest = _verify_self_hash(raw_label_manifest, "manifest_sha256", "label manifest")
    if sha256_file(paths.label_manifest) != receipt.get("label_manifest_sha256"):
        raise IntegrityError("sealed label manifest changed after prepare")
    if label_manifest.get("plan_sha256") != plan["plan_sha256"]:
        raise IntegrityError("label manifest belongs to a different plan")
    if not paths.sealed_labels.is_file():
        raise IntegrityError("sealed label artifact is missing")
    label_hash = sha256_file(paths.sealed_labels)
    if (
        label_hash != receipt.get("label_artifact_sha256")
        or label_hash != label_manifest.get("label_artifact_sha256")
    ):
        raise IntegrityError("sealed label artifact hash mismatch")

    _append_jsonl(
        paths.label_access_audit,
        {
            "schema_version": "week08_label_access_audit_v1",
            "event": "label_open_after_verified_decision_seal",
            "plan_sha256": plan["plan_sha256"],
            "decision_seal_sha256": seal["seal_sha256"],
            "label_artifact_sha256": label_hash,
        },
    )
    sealed_labels = _read_json(paths.sealed_labels)
    if label_loader is None:
        raw_labels = sealed_labels
    else:
        raw_labels = label_loader(paths.sealed_labels)
        if canonical_sha256(raw_labels) != canonical_sha256(sealed_labels):
            raise IntegrityError("label loader output differs from the sealed label artifact")
    if not isinstance(raw_labels, Mapping):
        raise IntegrityError("label loader did not return an object")
    label_mapping = raw_labels.get("labels", raw_labels)
    if not isinstance(label_mapping, Mapping):
        raise IntegrityError("sealed labels must be keyed by pair ID")
    tasks = [_task_from_dict(value) for value in plan["tasks"]]
    expected_pairs = {task.pair.pair_id for task in tasks}
    if set(label_mapping) != expected_pairs:
        raise IntegrityError("sealed label pair IDs do not match the plan")

    representative_tasks: dict[str, Week8Task] = {}
    for task in tasks:
        representative_tasks.setdefault(task.pair.pair_id, task)
    valid_gt_by_pair: dict[str, bool] = {}
    for pair_id, task in representative_tasks.items():
        pair_label = label_mapping[pair_id]
        if not isinstance(pair_label, Mapping):
            raise IntegrityError(f"label for {pair_id} is not an object")
        valid_gt_by_pair[pair_id] = _validate_label_for_task(
            task, pair_label, manifest["pairs"][pair_id]
        )

    task_by_id = {task.experiment_id: task for task in tasks}
    attempt_rows: list[dict[str, Any]] = []
    successes_by_id: dict[str, bool | None] = {}
    valid_gt_attempts = 0
    evaluable_completed = 0
    successes = 0
    for envelope in records:
        experiment_id = str(envelope["experiment_id"])
        task = task_by_id[experiment_id]
        record = envelope["record"]
        label = label_mapping[task.pair.pair_id]
        if not isinstance(label, Mapping):
            raise IntegrityError(f"label for {task.pair.pair_id} is not an object")
        valid_gt = valid_gt_by_pair[task.pair.pair_id]
        if valid_gt:
            valid_gt_attempts += 1
        metrics: dict[str, float | None] = {
            "tre_mean_px": None,
            "tre_median_px": None,
            "tre_p95_px": None,
            "dice": None,
        }
        success: bool | None = None
        if (
            valid_gt
            and record["execution_status"] == "completed"
            and record.get("estimated_transform") is not None
        ):
            if task.pair.ground_truth_type == "synthetic_created_after_freeze":
                reference = label.get("ground_truth_transform", label.get("moving_to_fixed"))
                points = label.get("control_points_moving")
                if points is None:
                    points = _reference_points(manifest["pairs"][task.pair.pair_id]["moving_shape"])
                metrics = {
                    **_tre_summary(reference, record["estimated_transform"], points),
                    "dice": None,
                }
            elif task.pair.ground_truth_type == "verified_landmarks":
                fixed_points = np.asarray(label.get("fixed_landmarks"), dtype=np.float64)
                moving_points = np.asarray(label.get("moving_landmarks"), dtype=np.float64)
                estimated = np.asarray(record["estimated_transform"], dtype=np.float64)
                homogeneous = np.column_stack((moving_points, np.ones(len(moving_points))))
                transformed = homogeneous @ estimated.T
                if np.any(np.abs(transformed[:, 2]) < 1e-12):
                    raise IntegrityError("estimated transform maps a landmark to infinity")
                transformed = transformed[:, :2] / transformed[:, 2:]
                errors = np.linalg.norm(transformed - fixed_points, axis=1)
                metrics = {
                    "tre_mean_px": float(np.mean(errors)),
                    "tre_median_px": float(np.median(errors)),
                    "tre_p95_px": float(np.percentile(errors, 95)),
                    "dice": None,
                }
            else:
                fixed_mask = np.asarray(label.get("fixed_mask"), dtype=np.uint8)
                moving_mask = np.asarray(label.get("moving_mask"), dtype=np.uint8)
                if fixed_mask.ndim != 2 or moving_mask.ndim != 2:
                    raise IntegrityError("verified masks must be 2D")
                warped_mask = warp_mask(
                    moving_mask,
                    np.asarray(record["estimated_transform"], dtype=np.float64),
                    output_shape=fixed_mask.shape,
                )
                metrics = {
                    "tre_mean_px": None,
                    "tre_median_px": None,
                    "tre_p95_px": None,
                    "dice": float(dice_score(fixed_mask != 0, np.asarray(warped_mask) != 0)),
                }
            evaluable_completed += 1
            if metrics["tre_mean_px"] is not None:
                success = bool(
                    metrics["tre_mean_px"] <= float(tolerance_px)
                    and record.get("transform_plausible") is True
                )
            else:
                success = bool(
                    metrics["dice"] is not None
                    and metrics["dice"] >= float(plan["mask_dice_threshold"])
                    and record.get("transform_plausible") is True
                )
            successes += int(success)
        successes_by_id[experiment_id] = success
        raw_diagnostics = record.get("method_diagnostics", {}).get("raw", {})
        if not isinstance(raw_diagnostics, Mapping):
            raw_diagnostics = {}
        timings = record.get("timings_ms", {})
        total_runtime = timings.get("total") if isinstance(timings, Mapping) else None
        method_runtime = None
        if isinstance(timings, Mapping):
            method_runtime = timings.get("registration", timings.get("method"))
        attempt_rows.append(
            {
                "experiment_id": experiment_id,
                "pair_id": task.pair.pair_id,
                "source_id": task.pair.source_id,
                "source_role": task.pair.source_role,
                "evaluation_role": task.pair.evaluation_role,
                "method_id": task.method.method_id,
                "config_id": task.method.config_id,
                "method_family": task.method.method_family,
                "transform_model": task.pair.transform_model,
                "modality_class": task.pair.modality_class,
                "condition": task.pair.condition,
                "severity": task.pair.severity,
                "ground_truth_type": task.pair.ground_truth_type,
                "execution_status": record["execution_status"],
                "geometric_reference_valid": valid_gt,
                **metrics,
                "geometric_within_tolerance": success,
                "valid_overlap_fraction": record.get("valid_overlap_fraction"),
                "total_runtime_ms": total_runtime,
                "method_runtime_ms": method_runtime,
                "timings_ms": timings,
                "diagnostic_keys": sorted(str(key) for key in raw_diagnostics),
            }
        )

    infrastructure_ids = {
        str(event["experiment_id"])
        for event in events
        if event.get("event") == "infrastructure_error"
    }
    for row in attempt_rows:
        row["infrastructure_incident"] = row["experiment_id"] in infrastructure_ids
    status_counts = dict(sorted(Counter(row["execution_status"] for row in attempt_rows).items()))
    completed_count = status_counts.get("completed", 0)
    track_a_overall = {
        "planned_attempts": len(tasks),
        "valid_gt_attempts": valid_gt_attempts,
        "geometrically_evaluable_completed_attempts": evaluable_completed,
        "geometric_successes": successes,
        "status_counts": status_counts,
        "geometric_success_rate": _rate(successes, valid_gt_attempts),
        "conditional_accuracy": _rate(successes, evaluable_completed),
        "execution_completion_rate": _rate(completed_count, len(tasks)),
        "infrastructure_incident_rate": _rate(len(infrastructure_ids), len(tasks)),
    }

    pair_tasks: dict[str, Week8Task] = {}
    for task in tasks:
        pair_tasks.setdefault(task.pair.pair_id, task)
    decision_rows: list[dict[str, Any]] = []
    selected = correct_selected = abstained = invalid = missing = 0
    for decision in policy["decisions"]:
        state = decision["decision"]
        selected_id = decision.get("selected_id")
        selected_correct = successes_by_id.get(str(selected_id)) if selected_id else None
        selected += int(state == "selected")
        abstained += int(state == "abstained")
        invalid += int(state == "invalid")
        missing += int(state == "missing_decision")
        correct_selected += int(state == "selected" and selected_correct is True)
        pair_task = pair_tasks[str(decision["pair_id"])]
        decision_rows.append(
            {
                **decision,
                "selected_geometrically_correct": selected_correct,
                "source_id": pair_task.pair.source_id,
                "source_role": pair_task.pair.source_role,
                "evaluation_role": pair_task.pair.evaluation_role,
                "modality_class": pair_task.pair.modality_class,
                "transform_model": pair_task.pair.transform_model,
                "condition": pair_task.pair.condition,
                "severity": pair_task.pair.severity,
                "ground_truth_type": pair_task.pair.ground_truth_type,
            }
        )
    eligible = len(decision_rows)
    track_b_overall = {
        "eligible_pairs": eligible,
        "selected_pairs": selected,
        "abstained_pairs": abstained,
        "invalid_pairs": invalid,
        "missing_decision_pairs": missing,
        "correct_selected_pairs": correct_selected,
        "coverage": _rate(selected, eligible),
        "selective_correctness": _rate(correct_selected, selected),
        "abstention_rate": _rate(abstained, eligible),
        "invalid_rate": _rate(invalid, eligible),
        "missing_decision_rate": _rate(missing, eligible),
    }
    uncertainty = {}
    for name, rate in {
        "geometric_success_rate": track_a_overall["geometric_success_rate"],
        "conditional_accuracy": track_a_overall["conditional_accuracy"],
        "execution_completion_rate": track_a_overall["execution_completion_rate"],
        "infrastructure_incident_rate": track_a_overall["infrastructure_incident_rate"],
        "policy_coverage": track_b_overall["coverage"],
        "policy_selective_correctness": track_b_overall["selective_correctness"],
        "policy_abstention_rate": track_b_overall["abstention_rate"],
    }.items():
        low, high = wilson_interval(rate["numerator"], rate["denominator"])
        uncertainty[name] = {"method": "wilson_95", "lower": low, "upper": high}

    criteria = dict(DEFAULT_RECOMMENDATION_CRITERIA)
    if recommendation_criteria is not None:
        criteria.update(dict(recommendation_criteria))
    track_a_strata = _stratified_summaries(attempt_rows, _track_a_subset_summary)
    track_b_strata = _stratified_summaries(decision_rows, _track_b_subset_summary)
    runtime_by_method = []
    for method_id in sorted({str(row["method_id"]) for row in attempt_rows}):
        group = [row for row in attempt_rows if row["method_id"] == method_id]
        runtime_by_method.append(
            {
                "method_id": method_id,
                "total_runtime_ms": _numeric_summary(row.get("total_runtime_ms") for row in group),
                "method_runtime_ms": _numeric_summary(row.get("method_runtime_ms") for row in group),
            }
        )
    overlap_by_method = []
    for method_id in sorted({str(row["method_id"]) for row in attempt_rows}):
        group = [row for row in attempt_rows if row["method_id"] == method_id]
        overlap_by_method.append(
            {
                "method_id": method_id,
                "valid_overlap_fraction": _numeric_summary(row.get("valid_overlap_fraction") for row in group),
            }
        )
    recommendation = _recommendation_validation(
        mode=str(plan["mode"]),
        decision_rows=decision_rows,
        criteria=criteria,
        no_post_label_change_attested=no_post_label_change_attested,
    )

    report = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "mode": plan["mode"],
        "plan_sha256": plan["plan_sha256"],
        "decision_seal_sha256": seal["seal_sha256"],
        "tolerance_px": float(tolerance_px),
        "track_a": {
            "overall": track_a_overall,
            "attempts": attempt_rows,
            "strata": track_a_strata,
            "runtime": {
                "overall_total_runtime_ms": _numeric_summary(row.get("total_runtime_ms") for row in attempt_rows),
                "overall_method_runtime_ms": _numeric_summary(row.get("method_runtime_ms") for row in attempt_rows),
                "by_method": runtime_by_method,
            },
            "valid_overlap": {
                "overall": _numeric_summary(row.get("valid_overlap_fraction") for row in attempt_rows),
                "by_method": overlap_by_method,
            },
            "diagnostic_availability": _diagnostic_availability(attempt_rows),
            "pairwise_method_comparisons": _pairwise_method_comparisons(attempt_rows),
            "infrastructure_events": [
                dict(event) for event in events if event.get("event") == "infrastructure_error"
            ],
        },
        "track_b": {"overall": track_b_overall, "pairs": decision_rows, "strata": track_b_strata},
        "uncertainty": uncertainty,
        "recommendation_validation": recommendation,
        "label_access": {
            "after_verified_decision_seal": True,
            "label_artifact_sha256": label_hash,
        },
        "no_post_label_change_attested": bool(no_post_label_change_attested),
        "final_evidence": plan["mode"] != "development_rehearsal",
    }
    if track_a_table is not None:
        _atomic_csv(Path(track_a_table), attempt_rows)
    if track_b_table is not None:
        _atomic_csv(Path(track_b_table), decision_rows)
    _atomic_json(paths.evaluation_summary, report)
    return report


def runner_contract_probe() -> dict[str, Any]:
    """Pure in-memory preflight probe; it reads no source, pixel, or label file."""
    pair = Week8PairSpec(
        pair_id="contract-probe-pair",
        source_id="contract-probe-source",
        source_sha256="1" * 64,
        case_id="contract-probe-case",
        geometry_seed=1,
        evaluation_role="development_rehearsal_known_gt",
        source_role="development",
        modality_class="monomodal",
        transform_model="affine",
        condition="none",
        severity="baseline",
        ground_truth_type="synthetic_created_after_freeze",
        policy_eligible=True,
    )
    method = Week8MethodSpec(
        method_id="contract-probe-method",
        config_id="contract-probe-config",
        method_family="intensity_based",
        method_config_sha256="2" * 64,
        supported_transform_models=("affine",),
        supported_modality_classes=("monomodal",),
        method_seed=42,
    )
    first = enumerate_week8_tasks([pair], [method])
    second = enumerate_week8_tasks([pair], [method])
    deterministic = first[0].experiment_id == second[0].experiment_id
    collision_rejected = False
    try:
        enumerate_week8_tasks([pair], [method], prior_experiment_ids={first[0].experiment_id})
    except Week8ContractError:
        collision_rejected = True
    plan = build_week8_plan(
        first,
        config_sha256="3" * 64,
        method_catalog_sha256="4" * 64,
        policy_sha256="5" * 64,
        code_sha256="6" * 64,
        mode="development_rehearsal",
    )
    plan_verified = verify_week8_plan(plan)["plan_sha256"] == plan["plan_sha256"]
    checks = {
        "deterministic_w8_id": deterministic and first[0].experiment_id.startswith("w8-"),
        "prior_id_collision_rejected": collision_rejected,
        "plan_and_count_hashes_verified": plan_verified,
        "isolated_phases_declared": True,
        "infrastructure_not_terminal_scientific_status": "infrastructure_error" not in TERMINAL_SCIENTIFIC_STATUSES,
    }
    return {
        "schema_version": "week08_runner_contract_probe_v1",
        "runner_schema_version": WEEK8_SCHEMA_VERSION,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "reads_pixels_or_labels": False,
    }
