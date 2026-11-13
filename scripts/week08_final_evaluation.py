"""Plan, decide, and evaluate the preregistered Week 8 protocol.

``plan`` builds the non-evidentiary Phase 3 matrix without decoding inputs.
``decide`` and ``evaluate`` use the final enrolled-source layout by default;
``--development-fixture`` selects the isolated rehearsal.  The final prepare
command is separately guarded by strict preflight before its first decode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from image_registration.week8_evaluation import (  # noqa: E402
    Week8DecisionRunner,
    Week8MethodSpec,
    Week8PairSpec,
    Week8Paths,
    build_week8_plan,
    canonical_sha256,
    enumerate_week8_tasks,
    evaluate_sealed_run,
    gate_from_policy,
    sha256_file,
    verify_week8_plan,
    write_week8_plan,
)

DEFAULT_CONFIG = ROOT / "configs/week08_final_evaluation.yaml"
FINAL_READINESS_RECEIPT_VERSION = "week08_final_readiness_receipt_v1"


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _unique_yaml_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _unique_yaml_mapping,
)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueSafeLoader)
    if not isinstance(value, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def require_phase3_development(config: Mapping[str, Any]) -> None:
    safety = config.get("safety", {})
    rehearsal = config.get("development_rehearsal", {})
    if config.get("state") != "phase3_preregistered_development_rehearsal_only":
        raise ValueError("This Phase 3 command only accepts the preregistered development state.")
    if safety.get("phase3_allows_real_week08_pixel_access") is not False:
        raise ValueError("Phase 3 pixel-access guard is not fail-closed.")
    if safety.get("phase3_allows_real_week08_label_access") is not False:
        raise ValueError("Phase 3 label-access guard is not fail-closed.")
    if rehearsal.get("enabled") is not True or rehearsal.get("final_evidence") is not False:
        raise ValueError("Development rehearsal must be enabled and non-evidentiary.")
    source = rehearsal.get("source", {})
    if (
        source.get("source_id") != "phase3_camera_fixture"
        or source.get("ledger_role") != "development"
        or source.get("path") != "data/samples/week02_real_general/camera.png"
        or source.get("sha256") != "b779d2c8e2a7098a0182c26227c3b516fb2d9d15f14ed99940c6196ba4a2c4e2"
    ):
        raise ValueError("Phase 3 permits only the preregistered camera development fixture.")
    if rehearsal.get("real_week08_source_or_label_paths_allowed") is not False:
        raise ValueError("Real Week 8 paths must remain forbidden during Phase 3.")


def load_protocol(
    config_path: str | Path, *, development: bool = True,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_path(config_path).resolve()
    if not development and path != DEFAULT_CONFIG.resolve():
        raise ValueError(
            "Final execution requires the canonical preregistered config path; "
            "alternate --config files are development-only."
        )
    config = load_yaml(path)
    if config.get("schema_version") != "week08_final_evaluation_v1":
        raise ValueError("Unsupported Week 8 evaluation schema.")
    if development:
        require_phase3_development(config)
    for key in ("method_catalog", "policy", "observable_projection", "frozen_baseline"):
        asset = config["frozen_assets"][key]
        asset_path = asset.get("path", asset.get("implementation_file"))
        if not asset_path or sha256_file(resolve_path(asset_path)) != asset["sha256"]:
            raise ValueError(f"Frozen asset hash mismatch: {asset_path}")
    if development:
        ledger = config["frozen_assets"]["source_ledger"]
        if sha256_file(resolve_path(ledger["path"])) != ledger["phase3_reference_sha256"]:
            raise ValueError("Phase 3 source-ledger hash mismatch.")
    return path, config


def prior_experiment_ids(config: Mapping[str, Any]) -> set[str]:
    """Read Week 7 journal metadata only; never touch an image or label."""
    result: set[str] = set()
    for value in config["execution_contract"]["prior_id_journals"]:
        path = resolve_path(value)
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line, object_pairs_hook=_unique_json_object)
                if not isinstance(value, dict):
                    raise ValueError(f"Prior journal row is not an object: {path}:{line_number}")
                experiment_id = str(value.get("experiment_id", "")).strip()
                if not experiment_id:
                    raise ValueError(f"Missing experiment_id in {path}:{line_number}")
                if experiment_id in result:
                    raise ValueError(f"Duplicate prior experiment ID: {experiment_id}")
                result.add(experiment_id)
    return result


def development_pairs(config: Mapping[str, Any]) -> list[Week8PairSpec]:
    profile = config["development_rehearsal"]
    subset, source = profile["subset"], profile["source"]
    templates = {str(item["id"]): item for item in config["conditions"]["templates"]}
    pairs: list[Week8PairSpec] = []
    for seed in subset["geometry_seeds"]:
        for model in subset["transform_models"]:
            for modality in subset["modality_classes"]:
                for template_id in subset["case_template_ids"]:
                    template = templates[str(template_id)]
                    if modality not in template["modality_classes"]:
                        continue
                    case_id = f"phase3_{model}_{modality}_{template_id}_s{int(seed)}"
                    pairs.append(Week8PairSpec(
                        pair_id=case_id,
                        source_id=str(source["source_id"]),
                        source_sha256=str(source["sha256"]),
                        case_id=case_id,
                        evaluation_role="development_rehearsal_known_gt",
                        source_role="development",
                        modality_class=str(modality),
                        transform_model=str(model),
                        condition=str(template["condition"]),
                        severity=str(template["severity"]),
                        ground_truth_type="synthetic_created_after_freeze",
                        protocol_version=str(config["protocol_version"]),
                        geometry_seed=int(seed),
                        dimensions=2,
                        policy_eligible=(modality == "monomodal" and model == "affine"),
                        metadata={"split": "development", "development_fixture": True,
                                  "final_evidence": False, "case_template_id": str(template_id),
                                  "condition_parameters": dict(template["parameters"])},
                    ))
    return pairs


def development_methods(config: Mapping[str, Any]) -> list[Week8MethodSpec]:
    path = resolve_path(config["frozen_assets"]["method_catalog"]["path"])
    catalog, catalog_hash = load_yaml(path), sha256_file(path)
    methods: list[Week8MethodSpec] = []
    for item in catalog.get("methods", []):
        parameters = dict(item.get("parameters", {}))
        config_hash = canonical_sha256(item)
        methods.append(Week8MethodSpec(
            method_id=str(item["method_id"]),
            config_id=f"week07_frozen_{item['method_id']}_{catalog_hash[:12]}",
            method_family=str(item["method_family"]),
            method_config_sha256=config_hash,
            supported_transform_models=(str(item["transform_model"]),),
            supported_modality_classes=tuple(str(v) for v in item["supported_modality_classes"]),
            method_seed=int(config["seeds"]["method_random_seed"]),
            metadata={"parameters": parameters,
                      "frozen_catalog_sha256": catalog_hash,
                      "optional": bool(item.get("optional", False))},
        ))
    return methods


def runner_code_sha256(config: Mapping[str, Any]) -> str:
    """Bind every frozen backend file plus orchestration and adapter code."""
    baseline = load_json(resolve_path(config["frozen_assets"]["frozen_baseline"]["path"]))
    frozen = baseline.get("frozen_files")
    if not isinstance(frozen, dict) or not frozen:
        raise ValueError("Frozen baseline does not contain a file inventory.")
    relative_paths = set(str(path) for path in frozen)
    relative_paths.update({
        "src/image_registration/week8_evaluation.py",
        "scripts/week08_final_evaluation.py",
        "scripts/week08_prepare_holdout.py",
    })
    relative_paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "ui/adapters").glob("*.py")
    )
    observed = {}
    for relative in sorted(relative_paths):
        path = resolve_path(relative)
        if not path.is_file():
            raise ValueError(f"Outcome-affecting code/config file is missing: {relative}")
        observed[relative] = sha256_file(path)
    return canonical_sha256(observed)


def build_development_plan(
    config_path: str | Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[Week8PairSpec], list[Week8MethodSpec]]:
    """Build the rehearsal plan using declared metadata, never source bytes."""
    path, config = load_protocol(config_path)
    pairs, methods = development_pairs(config), development_methods(config)
    tasks = enumerate_week8_tasks(
        pairs, methods, prior_experiment_ids=prior_experiment_ids(config),
    )
    policy = load_json(resolve_path(config["frozen_assets"]["policy"]["path"]))
    plan = build_week8_plan(
        tasks,
        config_sha256=sha256_file(path),
        method_catalog_sha256=config["frozen_assets"]["method_catalog"]["sha256"],
        policy_sha256=config["frozen_assets"]["policy"]["sha256"],
        code_sha256=runner_code_sha256(config),
        mode="development_rehearsal",
        policy_gate=gate_from_policy(policy),
        tolerance_px=float(config["endpoints"]["primary_geometric_endpoint"]["tolerance_px"]),
        mask_dice_threshold=float(config["endpoints"]["verified_mask_endpoint"]["tolerance"]),
    )
    return path, config, plan, pairs, methods


def final_paths(config: Mapping[str, Any]) -> Week8Paths:
    artifact_config = config.get("artifact_paths")
    if not isinstance(artifact_config, Mapping):
        raise ValueError("artifact_paths must be an object.")
    holdout = resolve_path(artifact_config["final_prepare_root"]).resolve()
    final = resolve_path(artifact_config["final_decision_root"]).resolve()
    outputs = (ROOT / "outputs").resolve()
    for name, candidate in (("final_prepare_root", holdout), ("final_decision_root", final)):
        try:
            candidate.relative_to(outputs)
        except ValueError as exc:
            raise ValueError(f"{name} must remain under the project outputs directory.") from exc
    if holdout == final or holdout in final.parents or final in holdout.parents:
        raise ValueError("Final holdout and decision roots must be disjoint and non-nested.")
    paths = Week8Paths.final_layout(holdout_root=holdout, final_root=final)
    declared = artifact_config.get("final")
    if not isinstance(declared, Mapping):
        raise ValueError("artifact_paths.final must be an object.")
    expected = {
        "plan": paths.plan,
        "final_readiness_receipt": paths.final_readiness_receipt,
        "observable_inputs": paths.observable_inputs,
        "observable_manifest": paths.observable_manifest,
        "prepare_receipt": paths.prepare_receipt,
        "sealed_label_artifact": paths.sealed_labels,
        "sealed_label_manifest": paths.label_manifest,
        "attempt_events": paths.attempt_events,
        "scientific_records": paths.scientific_records,
        "policy_decisions": paths.policy_decisions,
        "decision_seal": paths.decision_seal,
        "label_access_audit": paths.label_access_audit,
        "evaluation_summary": paths.evaluation_summary,
        "track_a_table": final / "track_a_attempts.csv",
        "track_b_table": final / "track_b_pairs.csv",
    }
    if set(declared) != set(expected):
        missing = sorted(set(expected) - set(declared))
        extra = sorted(set(declared) - set(expected))
        raise ValueError(f"Final artifact-path keys differ from the contract: missing={missing}, extra={extra}")
    for name, expected_path in expected.items():
        if resolve_path(declared[name]).resolve() != expected_path.resolve():
            raise ValueError(f"Final artifact path does not match derived layout: {name}")
    return paths


def verify_final_readiness_receipt(
    config: Mapping[str, Any], path: Path | None = None,
) -> dict[str, Any]:
    """Verify the persisted strict-gate receipt without opening source content."""
    receipt_path = final_paths(config).final_readiness_receipt if path is None else Path(path)
    receipt = load_json(receipt_path)
    received_hash = receipt.pop("receipt_sha256", None)
    if not _is_sha256(received_hash) or canonical_sha256(receipt) != received_hash:
        raise ValueError("Final readiness receipt self-hash mismatch.")
    expected = {
        "schema_version": FINAL_READINESS_RECEIPT_VERSION,
        "readiness": "PASS",
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "runner_code_sha256": runner_code_sha256(config),
        "source_ledger_sha256": sha256_file(resolve_path(config["sources"]["ledger_path"])),
        "enrollment_manifest_sha256": sha256_file(
            resolve_path(config["sources"]["enrollment_manifest_path"])
        ),
        "method_catalog_sha256": str(config["frozen_assets"]["method_catalog"]["sha256"]),
        "policy_sha256": str(config["frozen_assets"]["policy"]["sha256"]),
    }
    for name, value in expected.items():
        if receipt.get(name) != value:
            raise ValueError(f"Final readiness receipt {name} mismatch.")
    if receipt.get("week08_evaluation_executed") is not False:
        raise ValueError("Final readiness receipt must predate Week 8 evaluation.")
    report = receipt.get("preflight_report")
    if not isinstance(report, dict) or report.get("readiness") != "PASS" or report.get("mode") != "final_readiness":
        raise ValueError("Final readiness receipt does not contain the passing strict report.")
    if receipt.get("preflight_report_sha256") != canonical_sha256(report):
        raise ValueError("Final readiness receipt preflight report hash mismatch.")
    receipt["receipt_sha256"] = received_hash
    return receipt


def _evaluation_role(source_role: str, ground_truth_type: str) -> str:
    if source_role == "real_technical_only" or ground_truth_type == "unavailable":
        return "real_technical_only"
    if source_role == "policy_transfer_check":
        return "policy_transfer_check"
    if ground_truth_type in {"verified_landmarks", "verified_masks"}:
        return "independent_real_verified_gt"
    return "independent_known_gt"


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _allowed_gt_by_role(config: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for value in config["sources"]["roles"].values():
        role = str(value["ledger_role"])
        allowed = value.get("allowed_ground_truth_types")
        if allowed is None:
            allowed = [value.get("allowed_ground_truth_type")]
        result.setdefault(role, set()).update(str(item) for item in allowed if item)
    return result


def _validate_verified_label_descriptor(
    row: Mapping[str, Any], evidence: Mapping[str, Any], ground_truth_type: str,
) -> None:
    label = row.get("label")
    required = {
        "type", "units", "direction", "fixed_path", "fixed_sha256",
        "moving_path", "moving_sha256",
    }
    if not isinstance(label, dict) or set(label) != required:
        raise ValueError("Verified pair label descriptor has missing or extra fields.")
    if label["type"] != ground_truth_type:
        raise ValueError("Verified pair label type differs from the source ledger.")
    if label["units"] != "pixels" or label["direction"] != "moving_to_fixed":
        raise ValueError("Verified pair labels must use pixel units and Moving -> Fixed direction.")
    for prefix in ("fixed", "moving"):
        if not _nonempty_text(label[f"{prefix}_path"]) or not _is_sha256(label[f"{prefix}_sha256"]):
            raise ValueError("Verified pair label paths and SHA-256 values are required.")
    expected_manifest_id = evidence.get("manifest_id", evidence.get("manifest_sha256"))
    if not _nonempty_text(row.get("label_manifest_id")) or row["label_manifest_id"] != expected_manifest_id:
        raise ValueError("Verified pair label_manifest_id does not match ledger evidence.")
    files = evidence.get("label_files")
    if not isinstance(files, list):
        raise ValueError("Verified source ledger evidence has no label-file inventory.")
    for prefix in ("fixed", "moving"):
        matches = [
            item for item in files
            if isinstance(item, dict)
            and item.get("path") == label[f"{prefix}_path"]
            and item.get("sha256") == label[f"{prefix}_sha256"]
        ]
        if len(matches) != 1:
            raise ValueError(f"{prefix.title()} label descriptor is not uniquely ledger-authorized.")
        role = str(matches[0].get("role", "")).lower()
        if prefix not in role:
            raise ValueError(f"{prefix.title()} label file has the wrong ledger role.")


def load_final_enrollment(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load metadata-only enrollment records; never decode a source or label."""
    ledger_path = resolve_path(config["sources"]["ledger_path"])
    manifest_path = resolve_path(config["sources"]["enrollment_manifest_path"])
    ledger = load_json(ledger_path)
    manifest = load_json(manifest_path)
    if ledger.get("schema_version") != config["sources"]["required_ledger_schema_version"]:
        raise ValueError("Unsupported final source ledger schema.")
    sources = ledger.get("week08_sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("No Week 8 sources are enrolled; final planning is blocked.")
    if manifest.get("schema_version") != config["sources"]["enrollment_manifest_schema_version"]:
        raise ValueError("Unsupported Week 8 holdout-source manifest schema.")
    contract = config["sources"]["enrollment_manifest_contract"]
    required_top = set(contract["required_top_level_fields"])
    if set(manifest) != required_top:
        raise ValueError("Holdout-source manifest has missing or unregistered top-level fields.")
    if not _nonempty_text(manifest.get("release_id")):
        raise ValueError("Holdout-source manifest release_id must be nonempty.")
    if manifest.get("ledger_sha256") != sha256_file(ledger_path):
        raise ValueError("Holdout-source manifest is not bound to the current source ledger.")
    required_source_fields = set(config["sources"]["enrollment_lock"]["bind_fields"])
    source_ids: list[str] = []
    allowed_gt = _allowed_gt_by_role(config)
    for item in sources:
        if not isinstance(item, dict) or not required_source_fields.issubset(item):
            raise ValueError("Final source ledger record is malformed or incomplete.")
        source_id = item.get("source_id")
        evidence = item.get("ground_truth")
        if not _nonempty_text(source_id) or not _is_sha256(item.get("sha256")):
            raise ValueError("Final source ledger has an invalid source ID or hash.")
        if not isinstance(evidence, dict) or evidence.get("type") not in allowed_gt.get(str(item.get("role")), set()):
            raise ValueError(f"Source role/ground-truth contract is invalid: {source_id}")
        source_ids.append(str(source_id))
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Final source ledger has missing or duplicate source IDs.")
    manifest_source_ids = manifest.get("source_ids")
    if (
        not isinstance(manifest_source_ids, list)
        or any(not _nonempty_text(value) for value in manifest_source_ids)
        or len(manifest_source_ids) != len(set(manifest_source_ids))
        or sorted(manifest_source_ids) != sorted(source_ids)
    ):
        raise ValueError("Holdout-source manifest source IDs differ from the source ledger.")
    rows = manifest.get("pairs")
    if not isinstance(rows, list):
        raise ValueError("Holdout-source manifest pairs must be a list.")
    by_source = {str(item["source_id"]): item for item in sources}
    required_base = set(contract["non_synthetic_pair_required_fields"])
    required_verified = set(contract["verified_pair_additional_required_fields"])
    optional = {"condition", "severity"}
    pair_ids: set[str] = set()
    referenced_sources = {
        source_id for source_id, item in by_source.items()
        if item["ground_truth"]["type"] == "synthetic_created_after_freeze"
    }
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Holdout-source pair record must be an object.")
        if not required_base.issubset(row):
            raise ValueError("Holdout-source pair is missing required fields.")
        source_id = str(row.get("source_id", ""))
        fixed_source_id = str(row.get("fixed_source_id", ""))
        moving_source_id = str(row.get("moving_source_id", ""))
        if any(value not in by_source for value in (source_id, fixed_source_id, moving_source_id)):
            raise ValueError("Holdout-source pair references an unknown enrolled source.")
        source = by_source[source_id]
        evidence = source["ground_truth"]
        ground_truth_type = str(evidence["type"])
        if row.get("ground_truth_type") != ground_truth_type:
            raise ValueError("Manifest pair ground-truth type differs from the source ledger.")
        if ground_truth_type == "synthetic_created_after_freeze":
            raise ValueError("Synthetic sources are matrix-expanded and must not appear in manifest pairs.")
        if row.get("dimensions") != 2 or isinstance(row.get("dimensions"), bool):
            raise ValueError("Final non-synthetic pairs must be exactly two-dimensional.")
        if not all(_nonempty_text(row.get(name)) for name in (
            "pair_id", "case_id", "modality_class", "transform_model",
        )):
            raise ValueError("Final pair identifiers, modality, and model must be nonempty.")
        pair_id = str(row["pair_id"])
        if pair_id in pair_ids:
            raise ValueError(f"Duplicate final pair_id: {pair_id}")
        pair_ids.add(pair_id)
        referenced_sources.update((source_id, fixed_source_id, moving_source_id))
        if "policy_eligible" in row or "geometry_seed" in row:
            raise ValueError("Manifest may not supply policy eligibility or a geometry seed.")
        row_keys = frozenset(row)
        if ground_truth_type in {"verified_landmarks", "verified_masks"}:
            if row_keys not in {
                frozenset(required_base | required_verified),
                frozenset(required_base | required_verified | optional),
            }:
                raise ValueError("Verified pair has missing or unregistered fields.")
            if evidence.get("units") != "pixels" or evidence.get("coordinate_convention") != "moving_to_fixed":
                raise ValueError("Verified ledger evidence must use pixel units and Moving -> Fixed direction.")
            _validate_verified_label_descriptor(row, evidence, ground_truth_type)
        elif ground_truth_type == "unavailable":
            if row_keys not in {frozenset(required_base), frozenset(required_base | optional)}:
                raise ValueError("Technical-only pair must not contain a label descriptor or extra fields.")
        else:
            raise ValueError(f"Unsupported non-synthetic ground-truth type: {ground_truth_type}")
    if referenced_sources != set(source_ids):
        raise ValueError("Every enrolled source must be represented by the frozen final matrix.")
    return ledger, manifest


def _compatible_methods(
    methods: Sequence[Week8MethodSpec], *, modality: str, model: str,
) -> list[Week8MethodSpec]:
    return [
        method for method in methods
        if model in method.supported_transform_models
        and (
            method.supported_modality_classes is None
            or modality in method.supported_modality_classes
        )
    ]


def _derived_policy_eligibility(
    config: Mapping[str, Any], methods: Sequence[Week8MethodSpec], *,
    source_role: str, ground_truth_type: str, modality: str, model: str, dimensions: int,
) -> bool:
    rule = config["policy"]["eligibility"]
    compatible = _compatible_methods(methods, modality=modality, model=model)
    return (
        source_role in rule["source_roles"]
        and ground_truth_type in rule["ground_truth_types_for_correctness"]
        and dimensions in rule["dimensions"]
        and modality in rule["modality_classes"]
        and model in rule["transform_models"]
        and len(compatible) >= int(rule["minimum_planned_compatible_candidates"])
        and len({method.method_family for method in compatible})
        >= int(rule["minimum_planned_distinct_method_families"])
    )


def _source_plan_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return plan-visible provenance without source or label locators."""
    return {
        "source_record_sha256": canonical_sha256(source),
        "canonical_source_id": str(source["canonical_source_id"]),
        "canonical_dataset_id": str(source["canonical_dataset_id"]),
        "canonical_subject_id": str(source["canonical_subject_id"]),
        "canonical_case_id": str(source["canonical_case_id"]),
        "canonical_acquisition_id": str(source["canonical_acquisition_id"]),
        "source_modality": str(source["modality"]),
        "source_format": str(source["format"]),
        "ground_truth_record_sha256": canonical_sha256(source["ground_truth"]),
    }


def final_pairs(
    config: Mapping[str, Any],
    ledger: Mapping[str, Any],
    manifest: Mapping[str, Any],
    methods: Sequence[Week8MethodSpec],
) -> list[Week8PairSpec]:
    """Enumerate the frozen final matrix from enrolled metadata only."""
    sources = {str(item["source_id"]): item for item in ledger["week08_sources"]}
    templates = {str(item["id"]): item for item in config["conditions"]["templates"]}
    pairs: list[Week8PairSpec] = []
    for source_id, source in sorted(sources.items()):
        evidence = source.get("ground_truth")
        if not isinstance(evidence, dict):
            raise ValueError(f"Enrolled source lacks structured ground truth: {source_id}")
        ground_truth_type = str(evidence.get("type", ""))
        if ground_truth_type != "synthetic_created_after_freeze":
            continue
        configured_seeds = [int(value) for value in config["seeds"]["geometry"]]
        if sorted(int(value) for value in evidence.get("seeds", [])) != sorted(configured_seeds):
            raise ValueError(f"Synthetic seed contract differs from preregistration: {source_id}")
        for model in config["task_matrix"]["known_gt_synthetic_cross_product"]["transform_models"]:
            for modality in config["task_matrix"]["known_gt_synthetic_cross_product"]["modality_classes"]:
                if not _compatible_methods(methods, modality=str(modality), model=str(model)):
                    continue
                for seed in configured_seeds:
                    for template_id, template in templates.items():
                        if modality not in template["modality_classes"]:
                            continue
                        case_identity = {
                            "source_id": source_id,
                            "source_sha256": source["sha256"],
                            "model": model,
                            "modality": modality,
                            "seed": seed,
                            "template": template_id,
                        }
                        case_id = f"final-{canonical_sha256(case_identity)[:24]}"
                        pairs.append(Week8PairSpec(
                            pair_id=case_id,
                            source_id=source_id,
                            source_sha256=str(source["sha256"]),
                            case_id=case_id,
                            geometry_seed=seed,
                            evaluation_role=_evaluation_role(str(source["role"]), ground_truth_type),
                            source_role=str(source["role"]),
                            modality_class=str(modality),
                            transform_model=str(model),
                            condition=str(template["condition"]),
                            severity=str(template["severity"]),
                            ground_truth_type=ground_truth_type,
                            protocol_version=str(config["protocol_version"]),
                            dimensions=2,
                            policy_eligible=_derived_policy_eligibility(
                                config,
                                methods,
                                source_role=str(source["role"]),
                                ground_truth_type=ground_truth_type,
                                modality=str(modality),
                                model=str(model),
                                dimensions=2,
                            ),
                            metadata={
                                "split": "final_holdout",
                                **_source_plan_metadata(source),
                                "case_template_id": template_id,
                                "condition_parameters": dict(template["parameters"]),
                                "release_id": str(manifest["release_id"]),
                                "final_evidence": True,
                            },
                        ))

    manifest_pairs = manifest.get("pairs", [])
    if not isinstance(manifest_pairs, list):
        raise ValueError("Holdout-source manifest pairs must be a list.")
    for row in manifest_pairs:
        if not isinstance(row, dict):
            raise ValueError("Holdout-source pair record must be an object.")
        source_id = str(row.get("source_id", ""))
        if source_id not in sources:
            raise ValueError(f"Manifest pair references an unknown source: {source_id}")
        source = sources[source_id]
        evidence = source["ground_truth"]
        ground_truth_type = str(evidence["type"])
        pair_id = str(row.get("pair_id", ""))
        case_id = str(row["case_id"])
        modality = str(row["modality_class"])
        model = str(row["transform_model"])
        dimensions = int(row["dimensions"])
        pairs.append(Week8PairSpec(
            pair_id=pair_id,
            source_id=source_id,
            source_sha256=str(source["sha256"]),
            case_id=case_id,
            geometry_seed=int(row.get("geometry_seed", 0)),
            evaluation_role=_evaluation_role(str(source["role"]), ground_truth_type),
            source_role=str(source["role"]),
            modality_class=modality,
            transform_model=model,
            condition=str(row.get("condition", "real_observed")),
            severity=str(row.get("severity", "observed")),
            ground_truth_type=ground_truth_type,
            protocol_version=str(config["protocol_version"]),
            dimensions=dimensions,
            policy_eligible=_derived_policy_eligibility(
                config,
                methods,
                source_role=str(source["role"]),
                ground_truth_type=ground_truth_type,
                modality=modality,
                model=model,
                dimensions=dimensions,
            ),
            metadata={
                "split": "final_holdout",
                **_source_plan_metadata(source),
                "fixed_source_id": str(row["fixed_source_id"]),
                "moving_source_id": str(row["moving_source_id"]),
                "enrollment_pair_sha256": canonical_sha256(row),
                "release_id": str(manifest["release_id"]),
                "final_evidence": True,
                "geometry_seed_applicable": False,
            },
        ))
    if not pairs:
        raise ValueError("Enrollment metadata produces no final evaluation pairs.")
    return pairs


def build_final_plan(
    config_path: str | Path,
    *,
    final_readiness_receipt_sha256: str | None = None,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[Week8PairSpec], list[Week8MethodSpec]]:
    """Build the final metadata plan; this function never opens pixels or labels."""
    path, config = load_protocol(config_path, development=False)
    ledger, manifest = load_final_enrollment(config)
    methods = development_methods(config)
    pairs = final_pairs(config, ledger, manifest, methods)
    tasks = enumerate_week8_tasks(
        pairs,
        methods,
        prior_experiment_ids=prior_experiment_ids(config),
    )
    policy = load_json(resolve_path(config["frozen_assets"]["policy"]["path"]))
    if final_readiness_receipt_sha256 is None:
        receipt_path = final_paths(config).final_readiness_receipt
        if not receipt_path.is_file():
            raise ValueError("Final readiness receipt is missing; final preparation must run first.")
        verify_final_readiness_receipt(config, receipt_path)
        final_readiness_receipt_sha256 = sha256_file(receipt_path)
    plan = build_week8_plan(
        tasks,
        config_sha256=sha256_file(path),
        method_catalog_sha256=config["frozen_assets"]["method_catalog"]["sha256"],
        policy_sha256=config["frozen_assets"]["policy"]["sha256"],
        code_sha256=runner_code_sha256(config),
        mode="final",
        policy_gate=gate_from_policy(policy),
        tolerance_px=float(config["endpoints"]["primary_geometric_endpoint"]["tolerance_px"]),
        mask_dice_threshold=float(config["endpoints"]["verified_mask_endpoint"]["tolerance"]),
        source_ledger_sha256=sha256_file(resolve_path(config["sources"]["ledger_path"])),
        enrollment_manifest_sha256=sha256_file(
            resolve_path(config["sources"]["enrollment_manifest_path"])
        ),
        final_readiness_receipt_sha256=final_readiness_receipt_sha256,
    )
    return path, config, plan, pairs, methods


def development_output_root(config: Mapping[str, Any], override: Path | None = None) -> Path:
    path = override if override is not None else resolve_path(config["development_rehearsal"]["output_root"])
    candidate = path.resolve()
    outputs_root = (ROOT / "outputs").resolve()
    try:
        candidate.relative_to(outputs_root)
    except ValueError as exc:
        raise ValueError("Development output must remain under the project outputs directory.") from exc
    final_roots = {
        resolve_path(config["artifact_paths"]["final_prepare_root"]).resolve(),
        resolve_path(config["artifact_paths"]["final_decision_root"]).resolve(),
    }
    if any(
        candidate == final_root
        or candidate in final_root.parents
        or final_root in candidate.parents
        for final_root in final_roots
    ):
        raise ValueError("Development output must not overlap final holdout or decision roots.")
    return candidate


def write_development_plan(
    config_path: str | Path, *, output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    _, config, plan, _, _ = build_development_plan(config_path)
    destination = development_output_root(config, output_root) / "evaluation_plan.json"
    write_week8_plan(destination, plan)
    return plan, destination


def command_plan(args: argparse.Namespace) -> int:
    plan, path = write_development_plan(args.config, output_root=args.output_root)
    print(f"Development-only plan: {path}")
    print(f"Pairs: {plan['expected_counts']['pairs']}")
    print(f"Compatible attempts: {plan['expected_counts']['attempts']}")
    print(f"Policy-eligible pairs: {plan['expected_counts']['policy_eligible_pairs']}")
    print("No image pixels or labels were read.")
    return 0


def _disambiguate_estimated_diagnostics(value: Any) -> Any:
    """Rename adapter-owned estimated transforms before firewall validation.

    Some lower-level diagnostics historically call an estimated intermediate
    transform ``moving_to_fixed``.  The Week 8 wire contract reserves that
    unqualified name for sealed labels, so estimated diagnostics receive an
    explicit prefix.  Other prohibited keys, especially ground-truth fields,
    are intentionally left untouched and will fail the core firewall.
    """
    if isinstance(value, Mapping):
        renamed: dict[str, Any] = {}
        for key, item in value.items():
            name = {
                "moving_to_fixed": "estimated_moving_to_fixed",
                "fixed_to_moving": "estimated_fixed_to_moving",
            }.get(str(key), str(key))
            if name in renamed:
                raise ValueError(f"Adapter diagnostic key collision after disambiguation: {name}")
            renamed[name] = _disambiguate_estimated_diagnostics(item)
        return renamed
    if isinstance(value, (list, tuple)):
        return [_disambiguate_estimated_diagnostics(item) for item in value]
    return value


def observable_executor(methods: Sequence[Week8MethodSpec]):
    """Build the real adapter executor with ground truth explicitly unavailable."""
    from ui.adapters import build_default_registration_service
    from ui.core.contracts import (
        EvaluationContext, ImageSource, PreprocessingSpec, RegistrationRequest, RegistrationSpec,
    )
    from ui.core.enums import GroundTruthStatus, SourceType, TransformModel, TransformUnits

    service = build_default_registration_service()
    by_config = {item.config_id: item for item in methods}

    def execute(task, observable):
        fixed = np.asarray(observable["fixed"])
        moving = np.asarray(observable["moving"])
        parameters = dict(by_config[task["config_id"]].metadata.get("parameters", {}))
        request = RegistrationRequest(
            fixed=ImageSource(SourceType.ARRAY, "Week8 observable fixed", array=fixed),
            moving=ImageSource(SourceType.ARRAY, "Week8 observable moving", array=moving),
            preprocessing=PreprocessingSpec(grayscale=True, resize_policy="none"),
            registration=RegistrationSpec(
                method_id=task["method_id"],
                transform_model=TransformModel(task["transform_model"]),
                initialization=parameters.get("initialization"),
                parameters=parameters,
                interpolation=str(parameters.get("interpolation", "bilinear")),
            ),
            evaluation=EvaluationContext(
                ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                units=TransformUnits.PIXELS,
            ),
            request_id=task["experiment_id"],
        )
        started = perf_counter()
        run = service.run(request)
        elapsed_ms = (perf_counter() - started) * 1000.0
        raw = _disambiguate_estimated_diagnostics(dict(run.diagnostics.values))
        raw.setdefault("preparation", {
            "fixed_source": {"shape": list(fixed.shape)},
            "moving_source": {"shape": list(moving.shape)},
        })
        return {
            "pair_id": task["pair_id"],
            "method_id": task["method_id"],
            "method_family": task["method_family"],
            "transform_model": task["transform_model"],
            "modality_class": task["modality_class"],
            "dimensions": task["dimensions"],
            "seed": task["method_seed"],
            "execution_status": run.run_status.value,
            "estimated_transform": None if run.transform is None else run.transform.matrix.tolist(),
            "transform_plausible": None if run.transform is None else run.transform.plausible,
            "valid_overlap_fraction": run.metrics.after.get("valid_overlap_fraction"),
            "timings_ms": {"total": elapsed_ms},
            "method_diagnostics": {"raw": raw},
            "warnings": list(run.warnings),
            "failure_reason": run.failure_reason,
        }

    return execute


def recommendation_criteria(config: Mapping[str, Any]) -> dict[str, Any]:
    validation = config["recommendation_validation"]
    limited = validation["limited_independent_support_requires_all"]
    broad = validation["broad_cross_source_support_additionally_requires"]
    if limited.get("source_role") != "full_project_independent":
        raise ValueError("Recommendation validation source role differs from the frozen evaluator.")
    return {
        "minimum_selected_pairs": int(limited["minimum_selected_pairs"]),
        "minimum_coverage": float(limited["minimum_coverage"]),
        "minimum_selective_correctness": float(limited["minimum_selective_correctness"]),
        "minimum_selective_correctness_wilson_lower_95": float(
            limited["minimum_selective_correctness_wilson_lower_95"]
        ),
        "maximum_missing_decisions": int(limited["maximum_missing_decisions"]),
        "minimum_distinct_independent_sources_for_broad_support": int(
            broad["minimum_distinct_independent_source_identities"]
        ),
        "broad_support_requires_real_verified_gt": bool(
            broad["required_real_verified_gt_subset"]
        ),
    }


def command_decide(args: argparse.Namespace) -> int:
    if args.development_fixture:
        _, config, current_plan, _, methods = build_development_plan(args.config)
        run_paths: Week8Paths | Path = development_output_root(config, args.output_root)
    else:
        if args.output_root is not None:
            raise ValueError("Final artifact roots are frozen in the preregistration config.")
        _, config, current_plan, _, methods = build_final_plan(args.config)
        run_paths = final_paths(config)
    frozen_plan = verify_week8_plan(
        run_paths.plan if isinstance(run_paths, Week8Paths) else run_paths / "evaluation_plan.json"
    )
    if frozen_plan["plan_sha256"] != current_plan["plan_sha256"]:
        raise ValueError("Current code/config/method/policy contract differs from prepared plan.")
    policy = load_json(resolve_path(config["frozen_assets"]["policy"]["path"]))
    runner = Week8DecisionRunner(run_paths, gate_from_policy(policy))
    result = runner.run(
        observable_executor(methods),
        resume=bool(args.resume),
        retry_infrastructure=bool(args.retry_infrastructure),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("sealed") is True else 3


def command_evaluate(args: argparse.Namespace) -> int:
    if args.development_fixture:
        _, config, current_plan, _, _ = build_development_plan(args.config)
        run_paths: Week8Paths | Path = development_output_root(config, args.output_root)
    else:
        if args.output_root is not None:
            raise ValueError("Final artifact roots are frozen in the preregistration config.")
        _, config, current_plan, _, _ = build_final_plan(args.config)
        run_paths = final_paths(config)
    frozen_plan = verify_week8_plan(
        run_paths.plan if isinstance(run_paths, Week8Paths) else run_paths / "evaluation_plan.json"
    )
    if frozen_plan["plan_sha256"] != current_plan["plan_sha256"]:
        raise ValueError("Current code/config/method/policy contract differs from sealed plan.")
    if isinstance(run_paths, Week8Paths):
        track_a_table = resolve_path(config["artifact_paths"]["final"]["track_a_table"])
        track_b_table = resolve_path(config["artifact_paths"]["final"]["track_b_table"])
    else:
        development_paths = Week8Paths(Path(run_paths))
        track_a_table = development_paths.evaluation / "track_a_attempts.csv"
        track_b_table = development_paths.evaluation / "track_b_pairs.csv"
    result = evaluate_sealed_run(
        run_paths,
        tolerance_px=float(config["endpoints"]["primary_geometric_endpoint"]["tolerance_px"]),
        recommendation_criteria=recommendation_criteria(config),
        no_post_label_change_attested=True,
        track_a_table=track_a_table,
        track_b_table=track_b_table,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    common.add_argument("--output-root", type=Path)

    plan = subparsers.add_parser("plan", parents=[common], help="metadata-only development plan")
    plan.set_defaults(func=command_plan)

    decide = subparsers.add_parser("decide", parents=[common], help="observable-only execution")
    decide.add_argument("--development-fixture", action="store_true")
    decide.add_argument("--resume", action="store_true")
    decide.add_argument("--retry-infrastructure", action="store_true")
    decide.set_defaults(func=command_decide)

    evaluate = subparsers.add_parser("evaluate", parents=[common], help="sealed evaluation")
    evaluate.add_argument("--development-fixture", action="store_true")
    evaluate.set_defaults(func=command_evaluate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
