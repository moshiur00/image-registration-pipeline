"""Deterministic, resumable Week 6 benchmark execution.

The runner in this module is deliberately method agnostic. It enumerates a
frozen experiment matrix, assigns deterministic experiment identifiers, writes
one terminal record per attempted candidate, and can resume without rerunning
or overwriting existing evidence.

Registration algorithms remain responsible for producing a
``UnifiedEvaluationRecord``. The runner only owns orchestration, persistence,
identity validation, and standardized long-form export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from .evaluation_contracts import (
    METRIC_DEFINITIONS,
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)

RUNNER_SCHEMA_VERSION = "week06_benchmark_runner_v1"
TASK_IDENTITY_VERSION = "week06_benchmark_task_v1"


def _jsonable(value: Any) -> Any:
    """Convert supported scientific values into deterministic JSON values."""
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


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reference_dict(reference: ReferenceEvidence) -> dict[str, bool]:
    return {
        "exact_transform": bool(reference.exact_transform),
        "landmarks": bool(reference.landmarks),
        "masks": bool(reference.masks),
        "physical_spacing": bool(reference.physical_spacing),
    }


@dataclass(frozen=True)
class BenchmarkPairSpec:
    """Dataset-side information needed to enumerate benchmark tasks."""

    pair_id: str
    modality_class: str
    transform_model: str
    degradation: str = "none"
    dimensions: int = 2
    reference: ReferenceEvidence = field(default_factory=ReferenceEvidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("pair_id", "modality_class", "transform_model", "degradation"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty.")
            object.__setattr__(self, name, value)
        dimensions = int(self.dimensions)
        if dimensions not in {2, 3}:
            raise ValueError("dimensions must be 2 or 3.")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class BenchmarkMethodSpec:
    """One frozen registration configuration exposed to the benchmark runner."""

    method_id: str
    config_id: str
    method_family: str
    supported_transform_models: tuple[str, ...]
    supported_modality_classes: tuple[str, ...] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("method_id", "config_id", "method_family"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty.")
            object.__setattr__(self, name, value)
        models = tuple(str(value).strip() for value in self.supported_transform_models)
        if not models or any(not value for value in models):
            raise ValueError("supported_transform_models must contain non-empty values.")
        object.__setattr__(self, "supported_transform_models", models)
        if self.supported_modality_classes is not None:
            modalities = tuple(str(value).strip() for value in self.supported_modality_classes)
            if not modalities or any(not value for value in modalities):
                raise ValueError("supported_modality_classes must contain non-empty values.")
            object.__setattr__(self, "supported_modality_classes", modalities)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def supports(self, pair: BenchmarkPairSpec) -> bool:
        if pair.transform_model not in self.supported_transform_models:
            return False
        if self.supported_modality_classes is None:
            return True
        return pair.modality_class in self.supported_modality_classes


@dataclass(frozen=True)
class BenchmarkTask:
    """One deterministic pair x method x configuration x seed attempt."""

    pair_id: str
    method_id: str
    config_id: str
    method_family: str
    transform_model: str
    modality_class: str
    degradation: str
    dimensions: int
    reference: ReferenceEvidence
    seed: int | None = None
    pair_metadata: Mapping[str, Any] = field(default_factory=dict)
    method_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "pair_id",
            "method_id",
            "config_id",
            "method_family",
            "transform_model",
            "modality_class",
            "degradation",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty.")
            object.__setattr__(self, name, value)
        dimensions = int(self.dimensions)
        if dimensions not in {2, 3}:
            raise ValueError("dimensions must be 2 or 3.")
        object.__setattr__(self, "dimensions", dimensions)
        if self.seed is not None:
            object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "pair_metadata", dict(self.pair_metadata))
        object.__setattr__(self, "method_metadata", dict(self.method_metadata))

    def identity_dict(self) -> dict[str, Any]:
        """Return the complete scientific identity used to derive the run ID."""
        return {
            "identity_version": TASK_IDENTITY_VERSION,
            "pair_id": self.pair_id,
            "method_id": self.method_id,
            "config_id": self.config_id,
            "method_family": self.method_family,
            "transform_model": self.transform_model,
            "modality_class": self.modality_class,
            "degradation": self.degradation,
            "dimensions": self.dimensions,
            "seed": self.seed,
            "reference": _reference_dict(self.reference),
            "pair_metadata": dict(self.pair_metadata),
            "method_metadata": dict(self.method_metadata),
        }

    @property
    def experiment_id(self) -> str:
        """Return a stable SHA-256-derived experiment identifier."""
        digest = hashlib.sha256(_canonical_json(self.identity_dict()).encode("utf-8")).hexdigest()
        return f"w6-{digest[:20]}"

    def to_dict(self) -> dict[str, Any]:
        payload = self.identity_dict()
        payload["experiment_id"] = self.experiment_id
        return payload


def enumerate_benchmark_tasks(
    pairs: Sequence[BenchmarkPairSpec],
    methods: Sequence[BenchmarkMethodSpec],
    seeds: Sequence[int | None],
) -> list[BenchmarkTask]:
    """Build a stable compatible pair x method x seed experiment matrix."""
    if not pairs:
        raise ValueError("pairs must not be empty.")
    if not methods:
        raise ValueError("methods must not be empty.")
    if not seeds:
        raise ValueError("seeds must not be empty.")

    normalized_seeds = [None if seed is None else int(seed) for seed in seeds]
    tasks: list[BenchmarkTask] = []
    for pair in pairs:
        compatible_count = 0
        for method in methods:
            if not method.supports(pair):
                continue
            compatible_count += 1
            for seed in normalized_seeds:
                tasks.append(
                    BenchmarkTask(
                        pair_id=pair.pair_id,
                        method_id=method.method_id,
                        config_id=method.config_id,
                        method_family=method.method_family,
                        transform_model=pair.transform_model,
                        modality_class=pair.modality_class,
                        degradation=pair.degradation,
                        dimensions=pair.dimensions,
                        reference=pair.reference,
                        seed=seed,
                        pair_metadata=pair.metadata,
                        method_metadata=method.metadata,
                    )
                )
        if compatible_count == 0:
            raise ValueError(f"Pair '{pair.pair_id}' has no compatible method configuration.")

    by_id: dict[str, BenchmarkTask] = {}
    for task in tasks:
        if task.experiment_id in by_id:
            raise ValueError(
                "Benchmark matrix contains duplicate scientific identities: "
                f"{task.experiment_id}. Check pair/config/seed definitions."
            )
        by_id[task.experiment_id] = task
    return sorted(tasks, key=lambda item: item.experiment_id)


def benchmark_plan_fingerprint(tasks: Sequence[BenchmarkTask]) -> str:
    """Return a deterministic fingerprint for a frozen benchmark matrix."""
    if not tasks:
        raise ValueError("tasks must not be empty.")
    identities = [task.identity_dict() for task in sorted(tasks, key=lambda item: item.experiment_id)]
    payload = {"runner_schema_version": RUNNER_SCHEMA_VERSION, "tasks": identities}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _canonical_json(payload) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                envelope = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL record at line {line_number}: {exc}") from exc
            experiment_id = str(envelope.get("experiment_id", "")).strip()
            if not experiment_id:
                raise ValueError(f"Missing experiment_id at journal line {line_number}.")
            if experiment_id in records:
                raise ValueError(f"Duplicate experiment_id in journal: {experiment_id}")
            records[experiment_id] = envelope
    return records


def _validate_record_identity(task: BenchmarkTask, record: UnifiedEvaluationRecord) -> None:
    expected = {
        "pair_id": task.pair_id,
        "method_id": task.method_id,
        "method_family": task.method_family,
        "transform_model": task.transform_model,
        "modality_class": task.modality_class,
        "dimensions": task.dimensions,
        "seed": task.seed,
    }
    for name, expected_value in expected.items():
        actual = getattr(record, name)
        if actual != expected_value:
            raise ValueError(
                f"Executor result identity mismatch for {name}: "
                f"expected {expected_value!r}, got {actual!r}."
            )


def _failure_record(
    task: BenchmarkTask,
    *,
    status: ExecutionStatus,
    reason: str,
) -> UnifiedEvaluationRecord:
    return UnifiedEvaluationRecord(
        pair_id=task.pair_id,
        method_id=task.method_id,
        method_family=task.method_family,
        transform_model=task.transform_model,
        modality_class=task.modality_class,
        dimensions=task.dimensions,
        execution_status=status,
        reference=task.reference,
        valid_overlap_fraction=None,
        seed=task.seed,
        estimated_transform=None,
        transform_plausible=None,
        geometric_within_tolerance=None,
        metrics={},
        timings_ms={},
        method_diagnostics={},
        warnings=[],
        failure_reason=reason,
    )


def _envelope(task: BenchmarkTask, record: UnifiedEvaluationRecord) -> dict[str, Any]:
    return {
        "runner_schema_version": RUNNER_SCHEMA_VERSION,
        "experiment_id": task.experiment_id,
        "task": task.to_dict(),
        "record": record.to_dict(),
    }


def _long_form_columns() -> list[str]:
    return [
        "experiment_id",
        "pair_id",
        "modality_class",
        "degradation",
        "method_id",
        "method_family",
        "config_id",
        "transform_model",
        "dimensions",
        "seed",
        "execution_status",
        "failure_reason",
        "reference_label",
        "transform_plausible",
        "geometric_within_tolerance",
        "valid_overlap_fraction",
        *sorted(METRIC_DEFINITIONS),
        "timing_preprocessing_ms",
        "timing_registration_ms",
        "timing_warping_ms",
        "timing_evaluation_ms",
        "timing_total_ms",
        "estimated_transform_json",
        "method_diagnostics_json",
        "warnings_json",
        "pair_metadata_json",
        "method_metadata_json",
    ]


def _flatten_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    task = dict(envelope["task"])
    record = dict(envelope["record"])
    reference = dict(record.get("reference") or {})
    metrics = dict(record.get("metrics") or {})
    timings = dict(record.get("timings_ms") or {})

    row: dict[str, Any] = {
        "experiment_id": envelope["experiment_id"],
        "pair_id": record.get("pair_id"),
        "modality_class": record.get("modality_class"),
        "degradation": task.get("degradation"),
        "method_id": record.get("method_id"),
        "method_family": record.get("method_family"),
        "config_id": task.get("config_id"),
        "transform_model": record.get("transform_model"),
        "dimensions": record.get("dimensions"),
        "seed": record.get("seed"),
        "execution_status": record.get("execution_status"),
        "failure_reason": record.get("failure_reason"),
        "reference_label": reference.get("label"),
        "transform_plausible": record.get("transform_plausible"),
        "geometric_within_tolerance": record.get("geometric_within_tolerance"),
        "valid_overlap_fraction": record.get("valid_overlap_fraction"),
    }
    for key in sorted(METRIC_DEFINITIONS):
        row[key] = metrics.get(key)
    row.update(
        {
            "timing_preprocessing_ms": timings.get("preprocessing"),
            "timing_registration_ms": timings.get("registration"),
            "timing_warping_ms": timings.get("warping"),
            "timing_evaluation_ms": timings.get("evaluation"),
            "timing_total_ms": timings.get("total"),
            "estimated_transform_json": _canonical_json(record.get("estimated_transform")),
            "method_diagnostics_json": _canonical_json(record.get("method_diagnostics") or {}),
            "warnings_json": _canonical_json(record.get("warnings") or []),
            "pair_metadata_json": _canonical_json(task.get("pair_metadata") or {}),
            "method_metadata_json": _canonical_json(task.get("method_metadata") or {}),
        }
    )
    return row


def write_long_form_csv(path: str | Path, envelopes: Iterable[Mapping[str, Any]]) -> Path:
    """Write deterministic long-form benchmark results including failures."""
    output = Path(path)
    rows = [_flatten_envelope(item) for item in envelopes]
    rows.sort(key=lambda item: str(item["experiment_id"]))
    columns = _long_form_columns()

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, output)
    return output


@dataclass(frozen=True)
class BenchmarkRunSummary:
    """Compact execution summary returned by one runner invocation."""

    plan_fingerprint: str
    planned_count: int
    preexisting_count: int
    executed_count: int
    skipped_count: int
    completed_count: int
    check_count: int
    failed_count: int
    validation_error_count: int

    @property
    def terminal_count(self) -> int:
        return self.completed_count + self.check_count + self.failed_count + self.validation_error_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner_schema_version": RUNNER_SCHEMA_VERSION,
            "plan_fingerprint": self.plan_fingerprint,
            "planned_count": self.planned_count,
            "preexisting_count": self.preexisting_count,
            "executed_count": self.executed_count,
            "skipped_count": self.skipped_count,
            "terminal_count": self.terminal_count,
            "status_counts": {
                "completed": self.completed_count,
                "check": self.check_count,
                "failed": self.failed_count,
                "validation_error": self.validation_error_count,
            },
        }


BenchmarkExecutor = Callable[[BenchmarkTask], UnifiedEvaluationRecord]


class ResumableBenchmarkRunner:
    """Execute a frozen benchmark matrix with durable per-attempt records."""

    def __init__(self, output_directory: str | Path) -> None:
        self.output_directory = Path(output_directory)
        self.plan_path = self.output_directory / "benchmark_plan.json"
        self.journal_path = self.output_directory / "benchmark_records.jsonl"
        self.long_form_path = self.output_directory / "benchmark_results.csv"
        self.summary_path = self.output_directory / "benchmark_summary.json"

    def _prepare_plan(self, tasks: Sequence[BenchmarkTask], *, resume: bool) -> str:
        fingerprint = benchmark_plan_fingerprint(tasks)
        plan_payload = {
            "runner_schema_version": RUNNER_SCHEMA_VERSION,
            "plan_fingerprint": fingerprint,
            "task_count": len(tasks),
            "tasks": [task.to_dict() for task in sorted(tasks, key=lambda item: item.experiment_id)],
        }

        if self.plan_path.exists():
            existing = json.loads(self.plan_path.read_text(encoding="utf-8"))
            existing_fingerprint = str(existing.get("plan_fingerprint", ""))
            if existing_fingerprint != fingerprint:
                raise ValueError(
                    "Existing benchmark plan does not match the requested matrix. "
                    "Use a new output directory rather than mixing experiment plans."
                )
            if not resume and self.journal_path.exists() and self.journal_path.stat().st_size > 0:
                raise FileExistsError(
                    "Benchmark evidence already exists. Enable resume or use a new output directory."
                )
        else:
            self.output_directory.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(self.plan_path, json.dumps(plan_payload, indent=2, sort_keys=True) + "\n")
        return fingerprint

    def run(
        self,
        tasks: Sequence[BenchmarkTask],
        executor: BenchmarkExecutor,
        *,
        resume: bool = True,
    ) -> BenchmarkRunSummary:
        """Run missing tasks, persist every terminal outcome, and regenerate tables."""
        ordered_tasks = sorted(tasks, key=lambda item: item.experiment_id)
        if not ordered_tasks:
            raise ValueError("tasks must not be empty.")
        if len({task.experiment_id for task in ordered_tasks}) != len(ordered_tasks):
            raise ValueError("tasks contain duplicate experiment identifiers.")

        fingerprint = self._prepare_plan(ordered_tasks, resume=resume)
        existing = _read_jsonl(self.journal_path)
        unknown = set(existing) - {task.experiment_id for task in ordered_tasks}
        if unknown:
            raise ValueError(
                "Existing journal contains experiment IDs outside the frozen plan: "
                + ", ".join(sorted(unknown)[:5])
            )

        preexisting_count = len(existing)
        executed_count = 0
        skipped_count = 0

        for task in ordered_tasks:
            experiment_id = task.experiment_id
            if experiment_id in existing:
                skipped_count += 1
                continue

            try:
                record = executor(task)
                if not isinstance(record, UnifiedEvaluationRecord):
                    raise TypeError("Benchmark executor must return UnifiedEvaluationRecord.")
                _validate_record_identity(task, record)
            except (TypeError, ValueError) as exc:
                record = _failure_record(
                    task,
                    status=ExecutionStatus.VALIDATION_ERROR,
                    reason=f"runner_validation_error: {type(exc).__name__}: {exc}",
                )
            except Exception as exc:  # preserve algorithm/integration failures as evidence
                record = _failure_record(
                    task,
                    status=ExecutionStatus.FAILED,
                    reason=f"executor_exception: {type(exc).__name__}: {exc}",
                )

            envelope = _envelope(task, record)
            _append_jsonl(self.journal_path, envelope)
            existing[experiment_id] = envelope
            executed_count += 1

        envelopes = [existing[key] for key in sorted(existing)]
        write_long_form_csv(self.long_form_path, envelopes)

        status_counts = {status.value: 0 for status in ExecutionStatus}
        for envelope in envelopes:
            status = str(envelope["record"]["execution_status"])
            if status not in status_counts:
                raise ValueError(f"Unknown execution status in journal: {status}")
            status_counts[status] += 1

        summary = BenchmarkRunSummary(
            plan_fingerprint=fingerprint,
            planned_count=len(ordered_tasks),
            preexisting_count=preexisting_count,
            executed_count=executed_count,
            skipped_count=skipped_count,
            completed_count=status_counts[ExecutionStatus.COMPLETED.value],
            check_count=status_counts[ExecutionStatus.CHECK.value],
            failed_count=status_counts[ExecutionStatus.FAILED.value],
            validation_error_count=status_counts[ExecutionStatus.VALIDATION_ERROR.value],
        )
        _atomic_write_text(
            self.summary_path,
            json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        )
        return summary

    def records(self) -> list[dict[str, Any]]:
        """Return all persisted envelopes in deterministic experiment-ID order."""
        records = _read_jsonl(self.journal_path)
        return [records[key] for key in sorted(records)]
