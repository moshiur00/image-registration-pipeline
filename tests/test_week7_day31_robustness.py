"""Day 31 design-only and pilot integration regressions."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from image_registration.benchmark_runner import enumerate_benchmark_tasks
from image_registration.config import load_config
from image_registration.week7_robustness import (
    SCHEMA_VERSION, design_pairs, make_manifest, method_specs, validate_design,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/week07_day01_robustness_grid.yaml"
METHODS = ROOT / "configs/week07_day01_frozen_methods.yaml"


@lru_cache(maxsize=1)
def pilot_script() -> ModuleType:
    """Load the standalone CLI by file path, without requiring scripts on sys.path.

    The project installs packages from src/, and the root pytest pythonpath is
    deliberately limited to src/. Direct ``from scripts...`` imports depend on
    the test runner placing the repository root on sys.path, which the Windows
    pytest entry point is not required to do.
    """
    path = ROOT / "scripts/week07_day01_robustness_design.py"
    spec = spec_from_file_location("week07_day01_robustness_design", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load the Day 31 CLI module: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration():
    return load_config(CONFIG)


def frozen_methods():
    return method_specs(load_config(METHODS), "a" * 64)


def test_design_schema_is_v1() -> None:
    assert configuration()["schema_version"] == SCHEMA_VERSION
    validate_design(configuration())


def test_design_is_stable_independent_of_source_bytes() -> None:
    config = configuration()
    a = design_pairs(config, "a" * 64)
    b = design_pairs(config, "a" * 64)
    assert [p.pair_id for p in a] == [p.pair_id for p in b]
    assert [p.metadata for p in a] == [p.metadata for p in b]
    assert len(a) == len({p.pair_id for p in a})


def test_distinct_holdout_required() -> None:
    config = configuration()
    config["sources"]["final_holdout"] = config["sources"]["development"]
    with pytest.raises(ValueError, match="differ"):
        validate_design(config)


def test_invalid_seed_and_duplicate_severity_rejected() -> None:
    config = configuration()
    config["grid"]["seeds"] = [7, 7]
    with pytest.raises(ValueError, match="duplicates"):
        validate_design(config)
    config = configuration()
    config["grid"]["conditions"]["gaussian_blur"].append({"sigma": 0.8})
    with pytest.raises(ValueError, match="duplicates"):
        validate_design(config)


def test_unimplemented_pilot_degradation_rejected() -> None:
    config = configuration()
    config["pilot"][0]["condition"] = "partial_overlap"
    with pytest.raises(ValueError, match="unimplemented"):
        validate_design(config)


def test_grid_never_includes_holdout_split() -> None:
    pairs = design_pairs(configuration(), "a" * 64)
    assert pairs and all(p.metadata["split"] == "development" for p in pairs)
    assert all(p.reference.exact_transform for p in pairs)


def test_all_model_families_covered_with_frozen_catalog() -> None:
    methods = frozen_methods()
    assert {model for item in methods for model in item.supported_transform_models} == {
        "translation", "rigid", "similarity", "affine"
    }
    assert len({method.method_id for method in methods}) == len(methods) == 10


def test_manifest_skips_incompatible_pairs_explicitly() -> None:
    config = configuration()
    manifest, tasks = make_manifest(config, frozen_methods(), {"development": "a" * 64, "final_holdout": "b" * 64})
    assert manifest["study_state"] == "planned_not_executed"
    assert manifest["held_out_source_not_used"] is True
    assert manifest["unsupported_pair_count"] > 0
    assert manifest["pair_count"] == len({t.pair_id for t in tasks})
    assert len(tasks) == manifest["planned_compatible_attempts"]
    assert len(tasks) == len({t.experiment_id for t in tasks})
    for t in tasks:
        assert t.pair_metadata["split"] == "development"
        assert t.reference.exact_transform


def test_identity_changes_with_condition_and_source() -> None:
    config = configuration()
    methods = frozen_methods()
    m1, t1 = make_manifest(config, methods, {"development": "a" * 64, "final_holdout": "b" * 64})
    m2, t2 = make_manifest(config, methods, {"development": "c" * 64, "final_holdout": "b" * 64})
    assert m1["plan_fingerprint"] != m2["plan_fingerprint"]
    assert {t.experiment_id for t in t1} != {t.experiment_id for t in t2}
    clean = next(t for t in t1 if t.degradation == "none")
    blur = next(t for t in t1 if t.degradation == "gaussian_blur")
    assert clean.experiment_id != blur.experiment_id


def test_same_geometric_seed_is_shared_across_modalities() -> None:
    pairs = design_pairs(configuration(), "a" * 64)
    names = {(p.transform_model, p.modality_class, p.degradation, p.metadata["geometry_seed"],
              json.dumps(p.metadata["condition_parameters"], sort_keys=True)): p for p in pairs}
    key = ("affine", "monomodal", "gaussian_blur", 42, json.dumps({"sigma": 1.5}))
    other_key = ("affine", "simulated_multimodal", "gaussian_blur", 42, json.dumps({"sigma": 1.5}))
    assert key in names and other_key in names
    assert names[key].metadata["geometry_seed"] == names[other_key].metadata["geometry_seed"]


def test_full_pilot_catalog_has_no_empty_compatibility() -> None:
    config = configuration()
    config["_day31_source_hash"] = "a" * 64
    methods = frozen_methods()
    _pilot_pairs = pilot_script()._pilot_pairs
    fixed = np.arange(96 * 96, dtype=np.uint8).reshape(96, 96)
    pilot_pairs, prepared = _pilot_pairs(config, fixed)
    tasks = enumerate_benchmark_tasks(pilot_pairs, methods, [None])
    assert len(tasks) == 11
    assert len(prepared) == len(pilot_pairs) == 5
    assert {t.method_id for t in tasks} == {m.method_id for m in methods}
    for case in pilot_pairs:
        reference = prepared[case.pair_id][2]
        assert reference.moving_to_fixed.shape == (3, 3)
        assert case.reference.exact_transform


def test_service_firewall_and_gt_offline_only(monkeypatch) -> None:
    script = pilot_script()
    _pilot_executor, _pilot_pairs = script._pilot_executor, script._pilot_pairs
    from image_registration.evaluation_contracts import ExecutionStatus
    from ui.core.enums import GroundTruthStatus, RunStatus
    from ui.core.contracts import RegistrationRun, MetricSummary, DiagnosticSummary, ProvenanceSummary

    fixed = np.tile(np.arange(96, dtype=np.uint8), (96, 1))
    config = configuration()
    config["_day31_source_hash"] = "a" * 64
    pairs, prepared = _pilot_pairs(config, fixed)
    methods = frozen_methods()
    task = next(t for t in enumerate_benchmark_tasks(pairs, methods, [None]) if t.method_id == "phase_translation")
    seen = []

    class Service:
        def run(self, request):
            seen.append(request.evaluation)
            return RegistrationRun(
                request_id=request.request_id, run_status=RunStatus.FAILED,
                method_success=False, transform=None, metrics=MetricSummary(),
                diagnostics=DiagnosticSummary(), runtime_seconds=0.001,
                warnings=(), provenance=ProvenanceSummary(None, None, task.method_id, {}, {}),
                failure_reason="controlled_failure",
            )

    monkeypatch.setattr(script, "build_default_registration_service", lambda: Service())
    record = _pilot_executor(config, methods, prepared)(task)
    assert record.execution_status == ExecutionStatus.FAILED
    assert record.failure_reason == "controlled_failure"
    assert record.reference.exact_transform  # offline evaluation contract knows GT
    assert len(seen) == 1
    assert seen[0].ground_truth_status == GroundTruthStatus.UNAVAILABLE
    assert seen[0].ground_truth_transform is None
    assert seen[0].fixed_landmarks is None
    assert seen[0].moving_landmarks is None
