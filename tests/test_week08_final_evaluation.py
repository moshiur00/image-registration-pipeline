"""Phase 3 Week 8 evaluator contract and ground-truth firewall tests.

All data in this module are synthetic development fixtures.  No Week 8 source
pixel or label artifact is opened by this test suite.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

import numpy as np
import pytest

from image_registration.week8_evaluation import (
    IncompleteDecisionError,
    InfrastructureError,
    IntegrityError,
    LabelFirewallError,
    Week8ContractError,
    Week8DecisionRunner,
    Week8MethodSpec,
    Week8PairSpec,
    Week8Paths,
    build_week8_plan,
    canonical_sha256,
    enumerate_week8_tasks,
    evaluate_sealed_run,
    prepare_artifacts,
    sha256_file,
    verify_week8_plan,
    write_week8_plan,
)


SHA_SOURCE = "1" * 64
SHA_CONFIG = "2" * 64
SHA_METHODS = "3" * 64
SHA_POLICY = "4" * 64
SHA_CODE = "5" * 64


def pair(**changes) -> Week8PairSpec:
    values = {
        "pair_id": "dev-pair-a",
        "source_id": "development-source-a",
        "source_sha256": SHA_SOURCE,
        "case_id": "case-a",
        "evaluation_role": "independent_known_gt",
        "source_role": "full_project_independent",
        "modality_class": "monomodal",
        "transform_model": "affine",
        "condition": "none",
        "severity": "baseline",
        "ground_truth_type": "synthetic_created_after_freeze",
        "geometry_seed": 81103,
        "dimensions": 2,
        "policy_eligible": True,
        "metadata": {"split": "development"},
    }
    values.update(changes)
    return Week8PairSpec(**values)


def method(**changes) -> Week8MethodSpec:
    values = {
        "method_id": "ecc_affine_2d",
        "config_id": "ecc-affine-v1",
        "method_family": "intensity_based",
        "method_config_sha256": "6" * 64,
        "supported_transform_models": ("affine",),
        "supported_modality_classes": ("monomodal",),
        "method_seed": 42,
    }
    values.update(changes)
    return Week8MethodSpec(**values)


def methods() -> list[Week8MethodSpec]:
    return [
        method(),
        method(
            method_id="phase_affine_2d",
            config_id="phase-affine-v1",
            method_family="frequency_domain",
        ),
        method(
            method_id="orb_affine_2d",
            config_id="orb-affine-v1",
            method_family="feature_based",
        ),
    ]


def tasks(*, pairs=None, methods=None, prior=()):
    return enumerate_week8_tasks(
        pairs or [pair()],
        methods or [method()],
        prior_experiment_ids=set(prior),
    )


def plan(*, task_list=None):
    return build_week8_plan(
        task_list or tasks(),
        config_sha256=SHA_CONFIG,
        method_catalog_sha256=SHA_METHODS,
        policy_sha256=SHA_POLICY,
        code_sha256=SHA_CODE,
        mode="development_rehearsal",
    )


def observable(pair_id: str = "dev-pair-a") -> dict:
    """Small deterministic development-only observable arrays."""
    y, x = np.indices((64, 64))
    fixed = ((3 * x + 5 * y) % 251).astype(np.uint8)
    return {
        "fixed": fixed,
        "moving": fixed.copy(),
        "metadata": {"pair_id": pair_id, "split": "development"},
    }


def label(
    pair_id: str = "dev-pair-a",
    *,
    tx: float = 0.0,
    has_geometric_ground_truth: bool = True,
) -> dict:
    value = {
        "pair_id": pair_id,
        "has_geometric_ground_truth": has_geometric_ground_truth,
        "evaluation_role": (
            "independent_known_gt" if has_geometric_ground_truth else "real_technical_only"
        ),
        "source_role": (
            "full_project_independent" if has_geometric_ground_truth else "real_technical_only"
        ),
        "ground_truth_type": (
            "synthetic_created_after_freeze" if has_geometric_ground_truth else "unavailable"
        ),
    }
    if has_geometric_ground_truth:
        value["coordinate_units"] = "pixels"
        value["transform_direction"] = "moving_to_fixed"
        value["ground_truth_transform"] = [
            [1.0, 0.0, tx],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    return value


def prepare(
    root: Path,
    *,
    pair_specs: list[Week8PairSpec] | None = None,
    method_specs: list[Week8MethodSpec] | None = None,
    labels: dict[str, dict] | None = None,
):
    pair_specs = pair_specs or [pair()]
    method_specs = method_specs or methods()
    task_list = tasks(pairs=pair_specs, methods=method_specs)
    value = plan(task_list=task_list)
    observable_pairs = {item.pair_id: observable(item.pair_id) for item in pair_specs}
    if labels is None:
        labels = {
            item.pair_id: label(
                item.pair_id,
                has_geometric_ground_truth=item.ground_truth_type != "unavailable",
            )
            for item in pair_specs
        }
    prepare_artifacts(
        root,
        value,
        observable_pairs,
        labels,
        development_only=True,
    )
    return value, task_list


def view_value(view, name: str):
    return view[name] if isinstance(view, dict) else getattr(view, name)


def completed(view: dict, _observable: dict, *, tx: float = 0.0) -> dict:
    """Observable-only executor result accepted by the Week 8 runner."""
    family = view_value(view, "method_family")
    raw = {"preparation": {"fixed_source": {"shape": [64, 64]}}}
    if family == "frequency_domain":
        raw["response"] = 0.9
    elif family == "intensity_based":
        raw.update(final_ecc=0.95, levels_completed=3)
    elif family == "feature_based":
        raw.update(
            ransac_inlier_ratio=0.9,
            fixed_match_coverage=0.7,
            moving_match_coverage=0.65,
            ransac_inliers=30,
        )
    elif family == "mutual_information":
        raw.update(
            final_metric_value=-1.25,
            optimizer_stop_condition="Step too small",
            valid_metric_points=3000,
        )
    return {
        "pair_id": view_value(view, "pair_id"),
        "method_id": view_value(view, "method_id"),
        "method_family": family,
        "transform_model": view_value(view, "transform_model"),
        "modality_class": view_value(view, "modality_class"),
        "execution_status": "completed",
        "estimated_transform": [
            [1.0, 0.0, tx],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "transform_plausible": True,
        "valid_overlap_fraction": 0.9,
        "timings_ms": {"registration": 1.0, "total": 1.5},
        "method_diagnostics": {"raw": raw},
    }


def jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def artifact(root: Path, name: str) -> Path:
    return getattr(Week8Paths(root), name)


def test_canonical_hash_ignores_mapping_order_but_not_values() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})


def test_w8_id_is_deterministic_and_disjoint_from_week7_ids() -> None:
    first = tasks()[0]
    second = tasks()[0]
    assert first.experiment_id == second.experiment_id
    assert first.experiment_id.startswith("w8-")
    assert first.experiment_id not in {"w6-day32-example", "w6-day35-example"}


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("pair", "source_id", "development-source-b"),
        ("pair", "source_sha256", "a" * 64),
        ("pair", "case_id", "case-b"),
        ("pair", "geometry_seed", 81117),
        ("pair", "evaluation_role", "policy_transfer_check"),
        ("pair", "protocol_version", "week08_evaluator_firewall_v2"),
        ("pair", "transform_model", "similarity"),
        ("method", "method_id", "orb_affine"),
        ("method", "config_id", "orb-affine-v1"),
        ("method", "method_config_sha256", "b" * 64),
        ("method", "method_seed", 43),
    ],
)
def test_task_id_binds_every_outcome_affecting_identity_field(target, field, value) -> None:
    baseline_pair = pair()
    baseline_method = method()
    baseline = tasks(pairs=[baseline_pair], methods=[baseline_method])[0].experiment_id
    if target == "pair":
        changed_pair = replace(baseline_pair, **{field: value})
        if field == "transform_model":
            changed_method = replace(
                baseline_method,
                supported_transform_models=("affine", "similarity"),
            )
        else:
            changed_method = baseline_method
    else:
        changed_pair = baseline_pair
        changed_method = replace(baseline_method, **{field: value})
    changed = tasks(pairs=[changed_pair], methods=[changed_method])[0]
    assert changed.experiment_id != baseline


def test_duplicate_week8_identity_and_prior_id_collision_fail_closed() -> None:
    original = tasks()[0]
    with pytest.raises(Week8ContractError, match="duplicate|collision|overlap"):
        enumerate_week8_tasks([pair(), pair()], [method()])
    with pytest.raises(Week8ContractError, match="collision|overlap|prior"):
        tasks(prior={original.experiment_id})


def test_plan_binds_expected_counts_and_hashes(tmp_path: Path) -> None:
    value = plan()
    path = tmp_path / "plan.json"
    write_week8_plan(path, value)
    verified = verify_week8_plan(path)
    assert verified["expected_counts"]["attempts"] == 1
    assert verified["plan_sha256"] == value["plan_sha256"]
    assert verified["expected_counts_sha256"] == value["expected_counts_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["tasks"][0].__setitem__("source_sha256", "f" * 64),
        lambda value: value.__setitem__("config_sha256", "f" * 64),
        lambda value: value.__setitem__("policy_sha256", "f" * 64),
        lambda value: value["expected_counts"].__setitem__("attempts", 99),
    ],
)
def test_plan_or_contract_tampering_blocks_before_execution(tmp_path: Path, mutation) -> None:
    value = json.loads(json.dumps(plan()))
    mutation(value)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(IntegrityError):
        verify_week8_plan(path)


def test_build_plan_is_metadata_only_and_reads_no_pixels_or_labels(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("plan/dry-run tried to read a file")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    value = plan()
    assert value["mode"] == "development_rehearsal"


def test_evaluation_before_complete_decision_fails_before_label_loader(tmp_path: Path) -> None:
    prepare(tmp_path)
    label_reads = 0

    def forbidden_loader(_path: Path):
        nonlocal label_reads
        label_reads += 1
        raise AssertionError("labels opened before decision seal")

    with pytest.raises((LabelFirewallError, IncompleteDecisionError, IntegrityError)):
        evaluate_sealed_run(tmp_path, tolerance_px=2.0, label_loader=forbidden_loader)
    assert label_reads == 0


def test_decide_succeeds_when_label_artifact_is_unavailable(tmp_path: Path) -> None:
    prepare(tmp_path)
    label_path = Week8Paths(tmp_path).sealed_labels
    assert label_path.is_file(), "prepare must keep labels in a separate artifact"
    hidden = label_path.with_name("labels.unavailable-during-decide")
    label_path.rename(hidden)
    try:
        summary = Week8DecisionRunner(tmp_path).run(completed)
    finally:
        hidden.rename(label_path)
    assert summary["sealed"] is True


def test_changing_labels_cannot_change_execution_or_policy_decisions(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    prepare(first, labels={"dev-pair-a": label(tx=0.0)})
    prepare(second, labels={"dev-pair-a": label(tx=50.0)})

    Week8DecisionRunner(first).run(completed)
    Week8DecisionRunner(second).run(completed)

    assert jsonl(Week8Paths(first).scientific_records) == jsonl(
        Week8Paths(second).scientific_records
    )
    assert json.loads(Week8Paths(first).policy_decisions.read_text()) == json.loads(
        Week8Paths(second).policy_decisions.read_text()
    )


def test_every_planned_attempt_has_exactly_one_final_scientific_record(tmp_path: Path) -> None:
    value, task_list = prepare(tmp_path)
    result = Week8DecisionRunner(tmp_path).run(completed)
    records = jsonl(Week8Paths(tmp_path).scientific_records)
    ids = [row["experiment_id"] for row in records]
    assert result["sealed"] is True
    assert len(records) == len(task_list) == value["expected_counts"]["attempts"]
    assert len(ids) == len(set(ids))


def test_terminal_scientific_outcomes_are_never_reexecuted(tmp_path: Path) -> None:
    prepare(tmp_path)
    Week8DecisionRunner(tmp_path).run(completed)
    calls = 0

    def forbidden(_view, _observable):
        nonlocal calls
        calls += 1
        raise AssertionError("terminal attempt was reexecuted")

    result = Week8DecisionRunner(tmp_path).run(
        forbidden,
        resume=True,
        retry_infrastructure=True,
    )
    assert calls == 0
    assert result["preexisting_terminal"] == 3
    assert len(jsonl(Week8Paths(tmp_path).scientific_records)) == 3


def test_only_infrastructure_errors_can_be_retried_and_events_are_preserved(
    tmp_path: Path,
) -> None:
    prepare(tmp_path, method_specs=[method()])
    calls = 0

    def flaky(view, item):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InfrastructureError("transient development fixture outage")
        return completed(view, item)

    first = Week8DecisionRunner(tmp_path).run(flaky)
    assert first["sealed"] is False
    assert not Week8Paths(tmp_path).decision_seal.exists()
    assert jsonl(Week8Paths(tmp_path).scientific_records) == []

    second = Week8DecisionRunner(tmp_path).run(
        flaky,
        resume=True,
        retry_infrastructure=True,
    )
    assert second["sealed"] is True
    events = jsonl(Week8Paths(tmp_path).attempt_events)
    records = jsonl(Week8Paths(tmp_path).scientific_records)
    assert [event["event"] for event in events] == [
        "attempt_started",
        "infrastructure_error",
        "attempt_started",
        "scientific_outcome",
    ]
    assert len(records) == 1
    report = evaluate_sealed_run(tmp_path)
    assert len(report["track_a"]["infrastructure_events"]) == 1
    assert report["track_a"]["infrastructure_events"][0]["error_type"] == "InfrastructureError"


@pytest.mark.parametrize(
    "retry_kwargs",
    [
        {"resume": False, "retry_infrastructure": True},
        {"resume": True, "retry_infrastructure": False},
    ],
)
def test_infrastructure_retry_requires_both_explicit_flags(tmp_path: Path, retry_kwargs) -> None:
    prepare(tmp_path, method_specs=[method()])

    def outage(_view, _observable):
        raise InfrastructureError("fixture outage")

    Week8DecisionRunner(tmp_path).run(outage)
    calls = 0

    def would_succeed(view, item):
        nonlocal calls
        calls += 1
        return completed(view, item)

    result = Week8DecisionRunner(tmp_path).run(would_succeed, **retry_kwargs)
    assert result["sealed"] is False
    assert calls == 0


def test_unexpected_executor_exception_is_journaled_as_infrastructure(tmp_path: Path) -> None:
    prepare(tmp_path, method_specs=[method()])

    def unexpected(_view, _observable):
        raise RuntimeError("adapter process disappeared")

    first = Week8DecisionRunner(tmp_path).run(unexpected)
    assert first["sealed"] is False
    events = jsonl(Week8Paths(tmp_path).attempt_events)
    assert [item["event"] for item in events] == ["attempt_started", "infrastructure_error"]
    assert events[-1]["error_type"] == "RuntimeError"

    calls = 0

    def succeeds(view, observable):
        nonlocal calls
        calls += 1
        return completed(view, observable)

    no_retry = Week8DecisionRunner(tmp_path).run(succeeds, resume=True)
    assert no_retry["sealed"] is False
    assert calls == 0
    recovered = Week8DecisionRunner(tmp_path).run(
        succeeds, resume=True, retry_infrastructure=True,
    )
    assert recovered["sealed"] is True
    assert calls == 1


def test_interrupted_partial_run_requires_flags_for_started_and_unstarted_tasks(
    tmp_path: Path,
) -> None:
    prepare(tmp_path)
    calls = 0

    def interrupted(view, observable):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("simulated process interruption")
        return completed(view, observable)

    with pytest.raises(KeyboardInterrupt):
        Week8DecisionRunner(tmp_path).run(interrupted)

    resumed_calls = 0

    def succeeds(view, observable):
        nonlocal resumed_calls
        resumed_calls += 1
        return completed(view, observable)

    blocked = Week8DecisionRunner(tmp_path).run(succeeds, resume=True)
    assert blocked["sealed"] is False
    assert resumed_calls == 0
    recovered = Week8DecisionRunner(tmp_path).run(
        succeeds, resume=True, retry_infrastructure=True,
    )
    assert recovered["sealed"] is True
    assert resumed_calls == 2
    events = jsonl(Week8Paths(tmp_path).attempt_events)
    error_types = {
        item.get("error_type") for item in events if item["event"] == "infrastructure_error"
    }
    assert error_types == {"InterruptedAttempt", "RunInterruptedBeforeAttempt"}


def test_record_written_before_event_is_reconciled_without_reexecution(tmp_path: Path) -> None:
    prepare(tmp_path, method_specs=[method()])
    Week8DecisionRunner(tmp_path).run(completed)
    paths = Week8Paths(tmp_path)
    paths.decision_seal.unlink()
    paths.policy_decisions.unlink()
    started = [item for item in jsonl(paths.attempt_events) if item["event"] == "attempt_started"]
    paths.attempt_events.write_text(
        "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in started),
        encoding="utf-8",
    )
    calls = 0

    def forbidden(_view, _observable):
        nonlocal calls
        calls += 1
        raise AssertionError("persisted terminal record was reexecuted")

    recovered = Week8DecisionRunner(tmp_path).run(
        forbidden, resume=True, retry_infrastructure=True,
    )
    assert recovered["sealed"] is True
    assert calls == 0
    events = jsonl(paths.attempt_events)
    assert [item["event"] for item in events] == [
        "attempt_started", "infrastructure_error", "scientific_outcome",
    ]
    assert events[1]["error_type"] == "JournalInterruptionAfterRecord"


def test_decision_lock_blocks_concurrent_and_unapproved_stale_recovery(tmp_path: Path) -> None:
    prepare(tmp_path, method_specs=[method()])
    paths = Week8Paths(tmp_path)
    paths.decision.mkdir(parents=True, exist_ok=True)
    lock = paths.decision / "runner.lock"
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    with pytest.raises(InfrastructureError, match="another decision runner"):
        Week8DecisionRunner(tmp_path).run(completed)
    lock.write_text(json.dumps({"pid": 99_999_999}), encoding="utf-8")
    os.utime(lock, (0, 0))
    with pytest.raises(InfrastructureError, match="requires --resume"):
        Week8DecisionRunner(tmp_path).run(completed)
    result = Week8DecisionRunner(tmp_path).run(
        completed, resume=True, retry_infrastructure=True,
    )
    assert result["sealed"] is True
    assert not lock.exists()


@pytest.mark.parametrize(
    ("artifact_name", "mutate"),
    [
        (
            "plan",
            lambda value: value.__setitem__("code_sha256", "f" * 64),
        ),
        (
            "plan",
            lambda value: value.__setitem__("config_sha256", "e" * 64),
        ),
        (
            "observable_manifest",
            lambda value: value["pairs"]["dev-pair-a"].__setitem__(
                "fixed_sha256", "d" * 64
            ),
        ),
    ],
)
def test_resume_rejects_any_contract_change(tmp_path: Path, artifact_name, mutate) -> None:
    prepare(tmp_path, method_specs=[method()])

    def outage(_view, _observable):
        raise InfrastructureError("fixture outage")

    Week8DecisionRunner(tmp_path).run(outage)
    path = artifact(tmp_path, artifact_name)
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(IntegrityError):
        Week8DecisionRunner(tmp_path).run(
            completed,
            resume=True,
            retry_infrastructure=True,
        )


@pytest.mark.parametrize(
    ("artifact_name", "mutate"),
    [
        (
            "plan",
            lambda value: value.__setitem__("policy_sha256", "a" * 64),
        ),
        (
            "observable_manifest",
            lambda value: value["pairs"]["dev-pair-a"].__setitem__(
                "moving_sha256", "b" * 64
            ),
        ),
        (
            "decision_seal",
            lambda value: value.__setitem__("scientific_records_sha256", "c" * 64),
        ),
    ],
)
def test_source_policy_or_decision_seal_tamper_blocks_before_labels(
    tmp_path: Path,
    artifact_name,
    mutate,
) -> None:
    prepare(tmp_path)
    Week8DecisionRunner(tmp_path).run(completed)
    path = artifact(tmp_path, artifact_name)
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    label_reads = 0

    def guarded_loader(_path):
        nonlocal label_reads
        label_reads += 1
        raise AssertionError("integrity verification did not precede labels")

    with pytest.raises(IntegrityError):
        evaluate_sealed_run(tmp_path, tolerance_px=2.0, label_loader=guarded_loader)
    assert label_reads == 0


def test_track_a_success_and_conditional_accuracy_have_distinct_denominators(
    tmp_path: Path,
) -> None:
    prepare(tmp_path)

    def mixed(view, item):
        if view_value(view, "method_family") == "feature_based":
            return {
                "execution_status": "failed",
                "failure_reason": "development fixture failure",
                "timings_ms": {"total": 1.0},
                "method_diagnostics": {"raw": {}},
            }
        return completed(view, item)

    Week8DecisionRunner(tmp_path).run(mixed)
    report = evaluate_sealed_run(tmp_path, tolerance_px=2.0)
    overall = report["track_a"]["overall"]
    assert overall["geometric_success_rate"] == {
        "numerator": 2,
        "denominator": 3,
        "value": pytest.approx(2 / 3),
    }
    assert overall["conditional_accuracy"] == {
        "numerator": 2,
        "denominator": 2,
        "value": 1.0,
    }


def test_track_b_coverage_and_selective_correctness_have_distinct_denominators(
    tmp_path: Path,
) -> None:
    first = pair(pair_id="selected", case_id="selected")
    second = pair(pair_id="abstained", case_id="abstained")
    prepare(
        tmp_path,
        pair_specs=[first, second],
        labels={"selected": label("selected"), "abstained": label("abstained")},
    )

    def one_abstains(view, item):
        row = completed(view, item)
        if (view_value(view, "pair_id") == "abstained"
                and view_value(view, "method_family") == "feature_based"):
            row["execution_status"] = "check"
            row["failure_reason"] = "insufficient observable agreement"
        return row

    Week8DecisionRunner(tmp_path).run(one_abstains)
    report = evaluate_sealed_run(tmp_path, tolerance_px=2.0)
    overall = report["track_b"]["overall"]
    assert overall["coverage"] == {
        "numerator": 1,
        "denominator": 2,
        "value": 0.5,
    }
    assert overall["selective_correctness"] == {
        "numerator": 1,
        "denominator": 1,
        "value": 1.0,
    }
    assert overall["abstention_rate"] == {
        "numerator": 1,
        "denominator": 2,
        "value": 0.5,
    }


def test_technical_only_pair_never_receives_geometric_metrics(tmp_path: Path) -> None:
    technical = pair(
        pair_id="technical",
        case_id="technical",
        evaluation_role="real_technical_only",
        source_role="real_technical_only",
        ground_truth_type="unavailable",
        policy_eligible=False,
    )
    prepare(
        tmp_path,
        pair_specs=[technical],
        labels={"technical": label("technical", has_geometric_ground_truth=False)},
    )
    Week8DecisionRunner(tmp_path).run(completed)
    report = evaluate_sealed_run(tmp_path, tolerance_px=2.0)
    rows = report["track_a"]["attempts"]
    assert rows
    assert all(row.get("tre_mean_px") is None for row in rows)
    assert all(row.get("geometric_within_tolerance") is None for row in rows)
    assert report["track_a"]["overall"]["valid_gt_attempts"] == 0
    assert report["track_b"]["overall"]["eligible_pairs"] == 0


def test_preregistered_strata_runtime_diagnostics_uncertainty_and_recommendation_are_reported(
    tmp_path: Path,
) -> None:
    prepare(tmp_path)
    Week8DecisionRunner(tmp_path).run(completed)
    report = evaluate_sealed_run(tmp_path, tolerance_px=2.0)

    assert set(report["track_a"]["strata"]) == {
        "modality_class", "transform_model", "condition", "severity",
        "source_role", "source_id",
    }
    assert set(report["track_b"]["strata"]) == set(report["track_a"]["strata"])
    assert report["track_a"]["runtime"]["overall_total_runtime_ms"]["count"] == 3
    assert report["track_a"]["runtime"]["overall_method_runtime_ms"]["count"] == 3
    assert report["track_a"]["valid_overlap"]["overall"]["count"] == 3
    assert len(report["track_a"]["diagnostic_availability"]) == 3
    assert set(report["uncertainty"]) == {
        "geometric_success_rate",
        "conditional_accuracy",
        "execution_completion_rate",
        "infrastructure_incident_rate",
        "policy_coverage",
        "policy_selective_correctness",
        "policy_abstention_rate",
    }
    recommendation = report["recommendation_validation"]
    assert recommendation["development_fixture_cannot_validate_recommendation"] is True
    assert recommendation["outcome"] == "preserve_results_keep_policy_non_deployed"
    assert recommendation["checks"]["final_evidence_mode"] is False
    assert recommendation["checks"]["no_post_label_change"] is False


def test_pairwise_method_comparison_uses_explicit_common_denominator_and_mcnemar_counts(
    tmp_path: Path,
) -> None:
    first = pair(pair_id="pair-one", case_id="pair-one")
    second = pair(pair_id="pair-two", case_id="pair-two")
    prepare(
        tmp_path,
        pair_specs=[first, second],
        labels={"pair-one": label("pair-one"), "pair-two": label("pair-two")},
    )

    def one_incorrect(view, item):
        tx = 5.0 if (
            view_value(view, "pair_id") == "pair-two"
            and view_value(view, "method_family") == "feature_based"
        ) else 0.0
        return completed(view, item, tx=tx)

    Week8DecisionRunner(tmp_path).run(one_incorrect)
    report = evaluate_sealed_run(tmp_path, tolerance_px=2.0)
    comparisons = report["track_a"]["pairwise_method_comparisons"]
    comparison = next(
        item for item in comparisons
        if {item["method_a"].split("::")[0], item["method_b"].split("::")[0]}
        == {"ecc_affine_2d", "orb_affine_2d"}
    )
    assert comparison["common_denominator"] == 2
    assert comparison["method_a_only_success"] + comparison["method_b_only_success"] == 1
    assert comparison["both_success"] == 1
    assert comparison["mcnemar_exact_two_sided_p"] == 1.0


def test_pair_accounting_rejects_duplicate_ids_and_source_hash_aliases() -> None:
    duplicate_id = pair(
        source_id="different-source",
        source_sha256="a" * 64,
        case_id="different-case",
    )
    with pytest.raises(Week8ContractError, match="duplicate pair_id"):
        enumerate_week8_tasks([pair(), duplicate_id], [method()])

    aliased_source = pair(
        pair_id="different-pair",
        case_id="different-case",
        source_sha256="b" * 64,
    )
    with pytest.raises(Week8ContractError, match="multiple source hashes"):
        enumerate_week8_tasks([pair(), aliased_source], [method()])


def test_final_plan_binds_enrollment_and_readiness_hashes() -> None:
    value = build_week8_plan(
        tasks(),
        config_sha256=SHA_CONFIG,
        method_catalog_sha256=SHA_METHODS,
        policy_sha256=SHA_POLICY,
        code_sha256=SHA_CODE,
        mode="final",
        policy_gate={},
        source_ledger_sha256="7" * 64,
        enrollment_manifest_sha256="8" * 64,
        final_readiness_receipt_sha256="9" * 64,
    )
    verified = verify_week8_plan(value)
    assert verified["source_ledger_sha256"] == "7" * 64
    assert verified["enrollment_manifest_sha256"] == "8" * 64
    assert verified["final_readiness_receipt_sha256"] == "9" * 64
    assert verified["tasks"][0]["protocol_version"] == "week08_evaluator_firewall_v1"

    with pytest.raises(Week8ContractError, match="bind"):
        build_week8_plan(
            tasks(),
            config_sha256=SHA_CONFIG,
            method_catalog_sha256=SHA_METHODS,
            policy_sha256=SHA_POLICY,
            code_sha256=SHA_CODE,
            mode="final",
            policy_gate={},
        )


@pytest.mark.parametrize(
    "nested_payload",
    [
        {"ground_truth_transform": np.eye(3).tolist()},
        {"fixed_mask": [[1]]},
        {"control_points_moving": [[1.0, 1.0]]},
        {"reference_valid_overlap_fraction": 0.8},
        {"dice": 1.0},
    ],
)
def test_nested_label_payloads_are_blocked_from_executor_results(
    tmp_path: Path, nested_payload: dict,
) -> None:
    prepare(tmp_path, method_specs=[method()])

    def leaking(view, item):
        row = completed(view, item)
        row["method_diagnostics"]["raw"]["nested"] = nested_payload
        return row

    with pytest.raises(LabelFirewallError, match="prohibited label field"):
        Week8DecisionRunner(tmp_path).run(leaking)


def test_executor_view_excludes_plan_metadata(tmp_path: Path) -> None:
    pair_spec = pair(metadata={"label_descriptor_sha256": "a" * 64})
    prepare(tmp_path, pair_specs=[pair_spec], method_specs=[method()])
    observed = None

    def capture(view, item):
        nonlocal observed
        observed = dict(view)
        return completed(view, item)

    Week8DecisionRunner(tmp_path).run(capture)
    assert observed is not None
    assert "pair_metadata" not in observed
    assert "method_metadata" not in observed
    assert "label_descriptor_sha256" not in json.dumps(observed)


def test_runner_rejects_gate_different_from_frozen_plan_before_execution(tmp_path: Path) -> None:
    prepare(tmp_path, method_specs=[method()])
    calls = 0

    def should_not_run(view, item):
        nonlocal calls
        calls += 1
        return completed(view, item)

    from image_registration.week7_calibration import Gate

    with pytest.raises(IntegrityError, match="runner gate differs"):
        Week8DecisionRunner(tmp_path, Gate(agreement_px=99.0)).run(should_not_run)
    assert calls == 0


def test_split_final_layout_runs_without_exposing_holdout_paths(tmp_path: Path) -> None:
    paths = Week8Paths.final_layout(
        holdout_root=tmp_path / "week08_holdout",
        final_root=tmp_path / "week08_final",
    )
    paths.final_readiness_receipt.parent.mkdir(parents=True, exist_ok=True)
    paths.final_readiness_receipt.write_text(
        json.dumps({"schema_version": "test_final_readiness_receipt_v1"}),
        encoding="utf-8",
    )
    value = build_week8_plan(
        tasks(methods=[method()]),
        config_sha256=SHA_CONFIG,
        method_catalog_sha256=SHA_METHODS,
        policy_sha256=SHA_POLICY,
        code_sha256=SHA_CODE,
        mode="final",
        policy_gate={},
        source_ledger_sha256="7" * 64,
        enrollment_manifest_sha256="8" * 64,
        final_readiness_receipt_sha256=sha256_file(paths.final_readiness_receipt),
    )
    receipt = prepare_artifacts(
        paths,
        value,
        {"dev-pair-a": observable()},
        {"dev-pair-a": label()},
        development_only=False,
    )
    manifest = json.loads(paths.observable_manifest.read_text(encoding="utf-8"))
    manifest_item = manifest["pairs"]["dev-pair-a"]
    assert manifest_item["fixed_path"].startswith("observable_inputs/")
    assert "week08_holdout" not in manifest_item["fixed_path"]
    assert receipt["source_ledger_sha256"] == "7" * 64
    assert Week8DecisionRunner(paths).run(completed)["sealed"] is True
    seal = json.loads(paths.decision_seal.read_text(encoding="utf-8"))
    assert seal["source_ledger_sha256"] == "7" * 64
    assert seal["enrollment_manifest_sha256"] == "8" * 64
    assert seal["final_readiness_receipt_sha256"] == sha256_file(
        paths.final_readiness_receipt
    )
    track_a = paths.root / "track_a_attempts.csv"
    track_b = paths.root / "track_b_pairs.csv"
    report = evaluate_sealed_run(
        paths,
        no_post_label_change_attested=True,
        track_a_table=track_a,
        track_b_table=track_b,
    )
    assert report["final_evidence"] is True
    assert report["no_post_label_change_attested"] is True
    assert track_a.is_file() and "config_id" in track_a.read_text(encoding="utf-8").splitlines()[0]
    assert track_b.is_file()


def _verified_mask_label(pair_id: str, fixed: np.ndarray, moving: np.ndarray) -> dict:
    return {
        "pair_id": pair_id,
        "has_geometric_ground_truth": True,
        "evaluation_role": "independent_real_verified_gt",
        "source_role": "full_project_independent",
        "ground_truth_type": "verified_masks",
        "coordinate_units": "pixels",
        "transform_direction": "moving_to_fixed",
        "fixed_mask": fixed.tolist(),
        "moving_mask": moving.tolist(),
    }


def test_verified_mask_endpoint_reports_identity_dice(tmp_path: Path) -> None:
    mask_pair = pair(
        evaluation_role="independent_real_verified_gt",
        ground_truth_type="verified_masks",
    )
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[16:48, 18:46] = 1
    prepare(
        tmp_path,
        pair_specs=[mask_pair],
        method_specs=[method()],
        labels={mask_pair.pair_id: _verified_mask_label(mask_pair.pair_id, mask, mask)},
    )
    Week8DecisionRunner(tmp_path).run(completed)
    report = evaluate_sealed_run(tmp_path)
    row = report["track_a"]["attempts"][0]
    assert row["dice"] == 1.0
    assert row["tre_mean_px"] is None
    assert row["geometric_within_tolerance"] is True


@pytest.mark.parametrize("failure", ["shape", "empty"])
def test_verified_mask_endpoint_rejects_invalid_masks(tmp_path: Path, failure: str) -> None:
    mask_pair = pair(
        evaluation_role="independent_real_verified_gt",
        ground_truth_type="verified_masks",
    )
    fixed = np.zeros((64, 64), dtype=np.uint8)
    moving = np.zeros((64, 64), dtype=np.uint8)
    if failure == "shape":
        fixed = np.ones((32, 32), dtype=np.uint8)
        moving[2:4, 2:4] = 1
    prepare(
        tmp_path,
        pair_specs=[mask_pair],
        method_specs=[method()],
        labels={mask_pair.pair_id: _verified_mask_label(mask_pair.pair_id, fixed, moving)},
    )
    Week8DecisionRunner(tmp_path).run(completed)
    with pytest.raises(IntegrityError, match="shapes|foreground"):
        evaluate_sealed_run(tmp_path)


def test_verified_landmarks_require_pixel_units_and_direction(tmp_path: Path) -> None:
    landmark_pair = pair(
        evaluation_role="independent_real_verified_gt",
        ground_truth_type="verified_landmarks",
    )
    bad_label = {
        "pair_id": landmark_pair.pair_id,
        "has_geometric_ground_truth": True,
        "evaluation_role": landmark_pair.evaluation_role,
        "source_role": landmark_pair.source_role,
        "ground_truth_type": landmark_pair.ground_truth_type,
        "coordinate_units": "millimetres",
        "transform_direction": "moving_to_fixed",
        "fixed_landmarks": [[1.0, 1.0]],
        "moving_landmarks": [[1.0, 1.0]],
    }
    prepare(
        tmp_path,
        pair_specs=[landmark_pair],
        method_specs=[method()],
        labels={landmark_pair.pair_id: bad_label},
    )
    Week8DecisionRunner(tmp_path).run(completed)
    with pytest.raises(IntegrityError, match="pixel coordinates"):
        evaluate_sealed_run(tmp_path)
