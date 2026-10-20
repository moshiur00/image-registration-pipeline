from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from image_registration.benchmark_runner import (
    BenchmarkMethodSpec,
    BenchmarkPairSpec,
    BenchmarkTask,
    ResumableBenchmarkRunner,
    benchmark_plan_fingerprint,
    enumerate_benchmark_tasks,
)
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)
from image_registration.transforms import identity_matrix


def _pairs() -> list[BenchmarkPairSpec]:
    return [
        BenchmarkPairSpec(
            pair_id="mono_a",
            modality_class="monomodal",
            transform_model="translation",
            degradation="none",
            reference=ReferenceEvidence(exact_transform=True),
            metadata={"difficulty": "easy", "b": 2, "a": 1},
        ),
        BenchmarkPairSpec(
            pair_id="multi_b",
            modality_class="simulated_multimodal",
            transform_model="translation",
            degradation="intensity_inversion",
            reference=ReferenceEvidence(exact_transform=True),
        ),
    ]


def _methods() -> list[BenchmarkMethodSpec]:
    return [
        BenchmarkMethodSpec(
            method_id="phase_translation",
            config_id="phase_v1",
            method_family="frequency_domain",
            supported_transform_models=("translation",),
        ),
        BenchmarkMethodSpec(
            method_id="ecc_translation",
            config_id="ecc_v1",
            method_family="intensity_based",
            supported_transform_models=("translation",),
        ),
    ]


def _success(task: BenchmarkTask) -> UnifiedEvaluationRecord:
    return UnifiedEvaluationRecord(
        pair_id=task.pair_id,
        method_id=task.method_id,
        method_family=task.method_family,
        transform_model=task.transform_model,
        modality_class=task.modality_class,
        dimensions=task.dimensions,
        execution_status=ExecutionStatus.COMPLETED,
        reference=task.reference,
        valid_overlap_fraction=1.0,
        seed=task.seed,
        estimated_transform=identity_matrix(),
        transform_plausible=True,
        geometric_within_tolerance=True,
        metrics={
            "translation_error_px": 0.0,
            "tre_mean_px": 0.0,
            "valid_overlap_fraction": 1.0,
            "mae": 0.0,
            "mse": 0.0,
            "ncc": 1.0,
            "ssim": 1.0,
            "evaluation_mi": 0.5,
        },
        timings_ms={"registration": 1.0, "total": 1.5},
        method_diagnostics={"probe": True},
    )


def test_experiment_id_is_stable_across_metadata_order() -> None:
    reference = ReferenceEvidence(exact_transform=True)
    first = BenchmarkTask(
        pair_id="pair",
        method_id="method",
        config_id="config",
        method_family="family",
        transform_model="translation",
        modality_class="monomodal",
        degradation="none",
        dimensions=2,
        reference=reference,
        seed=42,
        pair_metadata={"b": 2, "a": 1},
    )
    second = BenchmarkTask(
        pair_id="pair",
        method_id="method",
        config_id="config",
        method_family="family",
        transform_model="translation",
        modality_class="monomodal",
        degradation="none",
        dimensions=2,
        reference=reference,
        seed=42,
        pair_metadata={"a": 1, "b": 2},
    )
    assert first.experiment_id == second.experiment_id


def test_experiment_id_changes_when_seed_changes() -> None:
    tasks = enumerate_benchmark_tasks(_pairs()[:1], _methods()[:1], [7, 42])
    assert len(tasks) == 2
    assert tasks[0].experiment_id != tasks[1].experiment_id


def test_enumeration_filters_incompatible_models() -> None:
    methods = _methods() + [
        BenchmarkMethodSpec(
            method_id="affine_only",
            config_id="affine_v1",
            method_family="feature_based",
            supported_transform_models=("affine",),
        )
    ]
    tasks = enumerate_benchmark_tasks(_pairs(), methods, [42])
    assert len(tasks) == 4
    assert {task.method_id for task in tasks} == {"phase_translation", "ecc_translation"}


def test_pair_without_compatible_method_is_rejected() -> None:
    pair = BenchmarkPairSpec(
        pair_id="affine_pair",
        modality_class="monomodal",
        transform_model="affine",
        reference=ReferenceEvidence(exact_transform=True),
    )
    with pytest.raises(ValueError, match="no compatible method"):
        enumerate_benchmark_tasks([pair], _methods(), [42])


def test_plan_fingerprint_is_stable() -> None:
    tasks = enumerate_benchmark_tasks(_pairs(), _methods(), [7, 42])
    assert benchmark_plan_fingerprint(tasks) == benchmark_plan_fingerprint(list(reversed(tasks)))


def test_runner_executes_all_tasks_and_writes_outputs(tmp_path: Path) -> None:
    tasks = enumerate_benchmark_tasks(_pairs(), _methods(), [42])
    runner = ResumableBenchmarkRunner(tmp_path / "run")
    summary = runner.run(tasks, _success)

    assert summary.planned_count == 4
    assert summary.executed_count == 4
    assert summary.skipped_count == 0
    assert summary.completed_count == 4
    assert summary.terminal_count == 4
    assert runner.plan_path.exists()
    assert runner.journal_path.exists()
    assert runner.long_form_path.exists()
    assert runner.summary_path.exists()
    assert len(runner.records()) == 4


def test_resume_skips_existing_without_calling_executor(tmp_path: Path) -> None:
    tasks = enumerate_benchmark_tasks(_pairs(), _methods(), [42])
    runner = ResumableBenchmarkRunner(tmp_path / "run")
    runner.run(tasks, _success)

    calls = 0

    def should_not_run(task: BenchmarkTask) -> UnifiedEvaluationRecord:
        nonlocal calls
        calls += 1
        return _success(task)

    summary = runner.run(tasks, should_not_run, resume=True)
    assert calls == 0
    assert summary.preexisting_count == 4
    assert summary.executed_count == 0
    assert summary.skipped_count == 4
    assert len(runner.records()) == 4


def test_resume_executes_only_missing_tasks(tmp_path: Path) -> None:
    tasks = enumerate_benchmark_tasks(_pairs(), _methods(), [42])
    runner = ResumableBenchmarkRunner(tmp_path / "run")
    runner.run(tasks[:2], _success)

    # A frozen plan cannot silently expand. Use a second runner directory to
    # prove partial journal resume against the complete plan.
    full_runner = ResumableBenchmarkRunner(tmp_path / "full")
    fingerprint = benchmark_plan_fingerprint(tasks)
    full_runner.output_directory.mkdir(parents=True)
    full_runner.plan_path.write_text(
        json.dumps(
            {
                "runner_schema_version": "week06_benchmark_runner_v1",
                "plan_fingerprint": fingerprint,
                "task_count": len(tasks),
                "tasks": [task.to_dict() for task in tasks],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # Copy two complete evidence lines into the full frozen plan.
    lines = runner.journal_path.read_text(encoding="utf-8").splitlines()
    full_runner.journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    calls: list[str] = []

    def tracked(task: BenchmarkTask) -> UnifiedEvaluationRecord:
        calls.append(task.experiment_id)
        return _success(task)

    summary = full_runner.run(tasks, tracked, resume=True)
    assert summary.preexisting_count == 2
    assert summary.executed_count == 2
    assert summary.skipped_count == 2
    assert len(calls) == 2
    assert len(full_runner.records()) == 4


def test_plan_mismatch_is_rejected(tmp_path: Path) -> None:
    runner = ResumableBenchmarkRunner(tmp_path / "run")
    first = enumerate_benchmark_tasks(_pairs()[:1], _methods()[:1], [42])
    runner.run(first, _success)
    second = enumerate_benchmark_tasks(_pairs(), _methods(), [42])
    with pytest.raises(ValueError, match="does not match"):
        runner.run(second, _success, resume=True)


def test_executor_exception_is_retained_as_failed_record(tmp_path: Path) -> None:
    task = enumerate_benchmark_tasks(_pairs()[:1], _methods()[:1], [42])[0]
    runner = ResumableBenchmarkRunner(tmp_path / "run")

    def explode(_: BenchmarkTask) -> UnifiedEvaluationRecord:
        raise RuntimeError("intentional probe")

    summary = runner.run([task], explode)
    record = runner.records()[0]["record"]
    assert summary.failed_count == 1
    assert record["execution_status"] == "failed"
    assert "intentional probe" in record["failure_reason"]


def test_identity_mismatch_is_retained_as_validation_error(tmp_path: Path) -> None:
    task = enumerate_benchmark_tasks(_pairs()[:1], _methods()[:1], [42])[0]
    runner = ResumableBenchmarkRunner(tmp_path / "run")

    def wrong_identity(original: BenchmarkTask) -> UnifiedEvaluationRecord:
        record = _success(original)
        record.method_id = "wrong_method"
        return record

    summary = runner.run([task], wrong_identity)
    record = runner.records()[0]["record"]
    assert summary.validation_error_count == 1
    assert record["execution_status"] == "validation_error"
    assert "identity mismatch" in record["failure_reason"]


def test_long_form_csv_preserves_modality_and_failure_rows(tmp_path: Path) -> None:
    tasks = enumerate_benchmark_tasks(_pairs(), _methods()[:1], [42])
    runner = ResumableBenchmarkRunner(tmp_path / "run")

    def mixed(task: BenchmarkTask) -> UnifiedEvaluationRecord:
        if task.modality_class == "simulated_multimodal":
            raise RuntimeError("multimodal failure probe")
        return _success(task)

    runner.run(tasks, mixed)
    with runner.long_form_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert {row["modality_class"] for row in rows} == {"monomodal", "simulated_multimodal"}
    assert {row["execution_status"] for row in rows} == {"completed", "failed"}
    assert {row["degradation"] for row in rows} == {"none", "intensity_inversion"}


def test_resume_false_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    tasks = enumerate_benchmark_tasks(_pairs()[:1], _methods()[:1], [42])
    runner = ResumableBenchmarkRunner(tmp_path / "run")
    runner.run(tasks, _success)
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run(tasks, _success, resume=False)
