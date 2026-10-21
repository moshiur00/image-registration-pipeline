"""Week 7 robustness study planning on top of the frozen Week 6 task schema.

No registration algorithms, metric definitions, or automatic-selection rules live here.
The manifest is a *plan*, not evidence that an experiment was executed.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .benchmark_runner import (
    BenchmarkMethodSpec,
    BenchmarkPairSpec,
    BenchmarkTask,
    benchmark_plan_fingerprint,
    enumerate_benchmark_tasks,
)
from .evaluation_contracts import ReferenceEvidence

SCHEMA_VERSION = "week07_robustness_grid_v1"
SUPPORTED_MODELS = {"translation", "rigid", "similarity", "affine"}
SUPPORTED_MODALITIES = {"monomodal", "simulated_multimodal"}
CONDITIONS = {
    "gaussian_noise", "gaussian_blur", "rotation", "scale", "illumination",
    "occlusion", "partial_overlap", "low_texture", "repeated_pattern",
    "multimodal_mapping",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _required(mapping: Mapping[str, Any], name: str, expected: type) -> Any:
    value = mapping.get(name)
    if not isinstance(value, expected):
        raise ValueError(f"{name} must be {expected.__name__}.")
    return value


def _unique(values: list[Any], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} contains duplicates.")


def validate_design(config: Mapping[str, Any]) -> None:
    """Reject ambiguous/unsupported grids before any expensive registration."""
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}.")
    sources = _required(config, "sources", dict)
    if not sources.get("development") or not sources.get("final_holdout"):
        raise ValueError("Distinct development and final_holdout source files are required.")
    if sources["development"] == sources["final_holdout"]:
        raise ValueError("Development and held-out sources must differ.")
    grid = _required(config, "grid", dict)
    models = _required(grid, "transform_models", list)
    modalities = _required(grid, "modality_classes", list)
    seeds = _required(grid, "seeds", list)
    if not models or set(models) - SUPPORTED_MODELS:
        raise ValueError("Unsupported or empty transform_models.")
    if not modalities or set(modalities) - SUPPORTED_MODALITIES:
        raise ValueError("Unsupported or empty modality_classes.")
    if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds):
        raise ValueError("seeds must contain non-negative integers.")
    _unique(models, "transform_models")
    _unique(modalities, "modality_classes")
    _unique(seeds, "seeds")
    conditions = _required(grid, "conditions", dict)
    if not conditions or set(conditions) - CONDITIONS:
        raise ValueError("Unexpected or empty robustness conditions.")
    for condition, levels in conditions.items():
        if not isinstance(levels, list) or not levels:
            raise ValueError(f"Condition {condition} must contain severity levels.")
        fingerprints: list[str] = []
        for level in levels:
            if not isinstance(level, dict) or not level:
                raise ValueError(f"Condition {condition} has a non-mapping severity.")
            for key, value in level.items():
                if not isinstance(key, str) or not key:
                    raise ValueError("Severity keys must be non-empty strings.")
                if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    raise ValueError("Severity values must be numeric or strings.")
                if isinstance(value, (int, float)) and not (-1e6 < float(value) < 1e6):
                    raise ValueError("Severity values must be finite and bounded.")
            fingerprints.append(canonical_json(level))
        _unique(fingerprints, f"{condition} severities")
    allowed_conditions = set(_required(config, "implemented_pilot_conditions", list))
    if not allowed_conditions.issubset({"none", "intensity_inversion", "gaussian_noise", "gaussian_blur"}):
        raise ValueError("The pilot condition list contains unimplemented conditions.")
    for item in _required(config, "pilot", list):
        if not isinstance(item, dict):
            raise ValueError("Pilot case must be a mapping.")
        if item.get("transform_model") not in models:
            raise ValueError("Pilot transform model is not in the grid.")
        if item.get("modality_class") not in modalities:
            raise ValueError("Pilot modality class is not in the grid.")
        if item.get("condition") not in allowed_conditions:
            raise ValueError("Pilot case uses an unimplemented condition.")
    pilot_ids = [str(item.get("id", "")) for item in config["pilot"]]
    if not pilot_ids or not all(pilot_ids):
        raise ValueError("Pilot cases require non-empty IDs.")
    _unique(pilot_ids, "pilot IDs")


def method_specs(frozen_catalog: Mapping[str, Any], catalog_hash: str) -> list[BenchmarkMethodSpec]:
    """Build capabilities from tracked Week 6 configs, preserving parameter provenance."""
    methods: list[BenchmarkMethodSpec] = []
    for item in _required(frozen_catalog, "methods", list):
        method_id = str(item["method_id"])
        model = str(item["transform_model"])
        supported = tuple(str(value) for value in item["supported_modality_classes"])
        parameters = dict(item["parameters"])
        methods.append(
            BenchmarkMethodSpec(
                method_id=method_id,
                config_id=f"week06_frozen_{method_id}_{catalog_hash[:12]}",
                method_family=str(item["method_family"]),
                supported_transform_models=(model,),
                supported_modality_classes=supported,
                metadata={
                    "frozen_catalog_sha256": catalog_hash,
                    "parameters": parameters,
                    "optional": bool(item.get("optional", False)),
                },
            )
        )
    _unique([method.method_id for method in methods], "method IDs")
    return methods


def design_pairs(config: Mapping[str, Any], development_hash: str) -> list[BenchmarkPairSpec]:
    """One-factor-at-a-time development-only design with known geometry.

    A separate held-out image is reserved for Week 8 and never enumerated here.
    All methods for one pair receive the same pair metadata and exact geometry.
    """
    validate_design(config)
    grid = config["grid"]
    conditions: list[tuple[str, dict[str, Any]]] = [("none", {})]
    conditions.extend(
        (condition, dict(level))
        for condition, levels in grid["conditions"].items()
        for level in levels
    )
    pairs: list[BenchmarkPairSpec] = []
    for model in grid["transform_models"]:
        for modality in grid["modality_classes"]:
            for seed in grid["seeds"]:
                for condition, severity in conditions:
                    # Multimodal intensity remapping is not a monomodal condition.
                    if condition == "multimodal_mapping" and modality == "monomodal":
                        continue
                    # Explicitly test a single additional appearance perturbation at a time.
                    severity_tag = sha256(canonical_json(severity).encode()).hexdigest()[:10]
                    name = f"w7_{model}_{modality}_{condition}_{severity_tag}_s{seed}"
                    pairs.append(
                        BenchmarkPairSpec(
                            pair_id=name,
                            modality_class=modality,
                            transform_model=model,
                            degradation=condition,
                            reference=ReferenceEvidence(exact_transform=True),
                            metadata={
                                "study_schema": SCHEMA_VERSION,
                                "split": "development",
                                "source_sha256": development_hash,
                                "geometry_seed": seed,
                                "condition_parameters": severity,
                                "condition_type": condition,
                                "coordinate_units": "pixels",
                                "transform_direction": "moving_to_fixed",
                            },
                        )
                    )
    _unique([pair.pair_id for pair in pairs], "pair IDs")
    return pairs


def make_manifest(
    config: Mapping[str, Any], methods: list[BenchmarkMethodSpec],
    source_hashes: Mapping[str, str],
) -> tuple[dict[str, Any], list[BenchmarkTask]]:
    candidate_pairs = design_pairs(config, source_hashes["development"])
    unsupported_pairs = [pair.pair_id for pair in candidate_pairs if not any(method.supports(pair) for method in methods)]
    pairs = [pair for pair in candidate_pairs if any(method.supports(pair) for method in methods)]
    if not pairs:
        raise ValueError("The frozen catalog covers none of the proposed grid.")
    # Per-pair seeds are already embedded in pair identity, do not multiply attempts.
    tasks = enumerate_benchmark_tasks(pairs, methods, [None])
    pair_counts = Counter(pair.modality_class for pair in pairs)
    method_counts = Counter(task.method_id for task in tasks)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "study_state": "planned_not_executed",
        "split": "development_only",
        "source_sha256": dict(source_hashes),
        "held_out_source_not_used": True,
        "condition_type_counts": dict(sorted(Counter(pair.degradation for pair in pairs).items())),
        "modality_pair_counts": dict(sorted(pair_counts.items())),
        "method_attempt_counts": dict(sorted(method_counts.items())),
        "pair_count": len(pairs),
        "unsupported_pair_count": len(unsupported_pairs),
        "unsupported_pair_ids": unsupported_pairs,
        "planned_compatible_attempts": len(tasks),
        "plan_fingerprint": benchmark_plan_fingerprint(tasks),
        "reference_evidence": "synthetic_known_offline_only",
        "excluded_method_pair_combinations": len(pairs) * len(methods) - len(tasks),
        "condition_implementation": "severity_grid_is_design_only; Day32 implements sweeps",
        "constraints": [
            "No ground truth is passed to the registration selector.",
            "The held-out source is reserved for Week 8.",
            "Do not compare incompatible method and motion-model combinations.",
            "Failure outcomes remain denominator members in later aggregate success rates.",
        ],
    }
    return manifest, tasks
