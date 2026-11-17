"""Prepare isolated observable inputs and labels for the Week 8 protocol.

``--development-fixture`` runs the non-evidentiary Phase 3 rehearsal.  Without
that flag, the command runs the preregistered final path only after strict
readiness is PASS, then verifies enrolled hashes before the first decode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT, ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from image_registration.degradations import (  # noqa: E402
    adjust_gamma,
    gaussian_blur,
    gaussian_noise,
    rectangular_occlusion,
)
from image_registration.io import load_image  # noqa: E402
from image_registration.multimodal import histogram_remap, intensity_inversion  # noqa: E402
from image_registration.overlap import (  # noqa: E402
    apply_field_of_view,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
)
from image_registration.preprocessing import resize_image, to_grayscale  # noqa: E402
from image_registration.synthetic import generate_synthetic_pair, sample_ground_truth_transform  # noqa: E402
from image_registration.transforms import apply_transform  # noqa: E402
from image_registration.week8_evaluation import (  # noqa: E402
    canonical_sha256,
    prepare_artifacts,
    sha256_file,
    write_week8_plan,
)
from week08_final_evaluation import (  # noqa: E402
    DEFAULT_CONFIG,
    FINAL_READINESS_RECEIPT_VERSION,
    R3_CONFIG,
    build_development_plan,
    build_final_plan,
    canonical_config_path,
    development_output_root,
    final_paths,
    load_final_enrollment,
    load_protocol,
    resolve_path,
    runner_code_sha256,
    verify_final_readiness_receipt,
    write_development_plan,
)


def transform_ranges(config: Mapping[str, Any], model: str) -> dict[str, Any]:
    raw = dict(config["transforms"]["models"][model])
    result: dict[str, Any] = {}
    for key, value in raw.items():
        result[{"tx_px": "tx", "ty_px": "ty"}.get(key, key)] = value
    return result


def appearance_rng(pair_id: str) -> np.random.Generator:
    seed = int(hashlib.sha256(f"{pair_id}/appearance".encode("utf-8")).hexdigest()[:16], 16)
    return np.random.default_rng(seed)


def prepare_synthetic_case(pair, fixed: np.ndarray, config: Mapping[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Generate and independently validate one preregistered synthetic case."""
    ground_truth = sample_ground_truth_transform(
        pair.transform_model,
        np.random.default_rng(pair.geometry_seed),
        fixed.shape,
        transform_ranges(config, pair.transform_model),
    )
    synthetic = generate_synthetic_pair(
        fixed,
        ground_truth,
        interpolation=str(config["task_matrix"]["known_gt_synthetic_cross_product"]["transform_interpolation"]),
        border_value=float(config["task_matrix"]["known_gt_synthetic_cross_product"]["border_value"]),
    )
    moving = np.asarray(synthetic.moving).copy()
    valid = np.ones(moving.shape[:2], dtype=np.uint8)
    parameters = dict(pair.metadata.get("condition_parameters", {}))
    rng = appearance_rng(pair.pair_id)

    if pair.condition == "multimodal_mapping":
        if parameters.get("mapping") != "histogram_remap" or set(parameters) != {"mapping"}:
            raise ValueError("Unsupported preregistered multimodal mapping.")
        moving = histogram_remap(
            moving,
            input_knots=[0.0, 0.25, 0.5, 0.75, 1.0],
            output_knots=[0.0, 0.08, 0.56, 0.92, 1.0],
        )
    else:
        if pair.modality_class == "simulated_multimodal":
            moving = intensity_inversion(moving)
        elif pair.modality_class != "monomodal":
            raise ValueError(f"Unsupported modality class: {pair.modality_class}")
        if pair.condition == "none":
            if parameters:
                raise ValueError("Clean case must not define condition parameters.")
        elif pair.condition == "gaussian_noise":
            moving = gaussian_noise(moving, sigma_fraction=float(parameters["sigma_fraction"]), rng=rng)
        elif pair.condition == "gaussian_blur":
            moving = gaussian_blur(moving, sigma=float(parameters["sigma"]))
        elif pair.condition == "illumination":
            moving = adjust_gamma(moving, gamma=float(parameters["gamma"]))
        elif pair.condition == "occlusion":
            moving, valid, _ = rectangular_occlusion(
                moving,
                area_fraction=float(parameters["area_fraction"]),
                rng=rng,
            )
        elif pair.condition == "partial_overlap":
            target = float(parameters["target_overlap"])
            maximum = float(np.mean(overlap_mask_in_fixed_space(
                valid, ground_truth.moving_to_fixed, fixed_shape=fixed.shape,
            )))
            if target > maximum + 0.02:
                raise ValueError("Requested overlap exceeds geometric maximum.")
            low, high = 0.01, 1.0
            for _ in range(18):
                middle = (low + high) / 2.0
                trial = rectangular_field_of_view_mask(
                    moving.shape, width_fraction=middle, height_fraction=1.0,
                    center_x_fraction=0.5,
                )
                actual = float(np.mean(overlap_mask_in_fixed_space(
                    trial, ground_truth.moving_to_fixed, fixed_shape=fixed.shape,
                )))
                if actual < target:
                    low = middle
                else:
                    high = middle
            valid = rectangular_field_of_view_mask(
                moving.shape, width_fraction=(low + high) / 2.0,
                height_fraction=1.0, center_x_fraction=0.5,
            )
            moving = apply_field_of_view(moving, valid)
        elif pair.condition == "low_texture":
            strength = float(parameters["texture_strength"])
            moving = np.rint(
                strength * moving.astype(float)
                + (1.0 - strength) * float(np.mean(moving))
            ).clip(0, 255).astype(np.uint8)
        elif pair.condition == "repeated_pattern":
            fraction = float(parameters["repeat_fraction"])
            _, xx = np.indices(moving.shape)
            stripe = ((xx // 10) % 2) * 180.0 + 35.0
            moving = np.rint(
                (1.0 - fraction) * moving.astype(float) + fraction * stripe
            ).clip(0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unimplemented preregistered condition: {pair.condition}")

    validation = config["transforms"]["synthetic_label_validation"]
    recovered = apply_transform(synthetic.control_points_moving, ground_truth.moving_to_fixed)
    round_trip_error = float(np.max(np.linalg.norm(
        recovered - synthetic.control_points_fixed, axis=1,
    )))
    inverse_error = float(np.max(np.abs(
        ground_truth.moving_to_fixed @ ground_truth.fixed_to_moving - np.eye(3)
    )))
    reference_overlap = overlap_mask_in_fixed_space(
        valid, ground_truth.moving_to_fixed, fixed_shape=fixed.shape,
    )
    overlap_fraction = float(np.mean(reference_overlap))
    if inverse_error > float(validation["inverse_matrix_max_absolute_error"]):
        raise ValueError("Synthetic transform inverse validation failed.")
    if round_trip_error > float(validation["control_point_round_trip_max_px"]):
        raise ValueError("Synthetic control-point validation failed.")
    if overlap_fraction < float(validation["minimum_valid_overlap_fraction"]):
        raise ValueError("Synthetic valid overlap is below the preregistered minimum.")
    if pair.condition == "partial_overlap":
        expected = float(parameters["target_overlap"])
        template = next(
            item for item in config["conditions"]["templates"]
            if item["id"] == pair.metadata["case_template_id"]
        )
        if abs(overlap_fraction - expected) > float(template["actual_overlap_tolerance"]):
            raise ValueError("Synthetic partial-overlap validation failed.")
    label = {
        "pair_id": pair.pair_id,
        "evaluation_role": pair.evaluation_role,
        "source_role": pair.source_role,
        "ground_truth_type": pair.ground_truth_type,
        "has_geometric_ground_truth": True,
        "ground_truth_transform": ground_truth.moving_to_fixed.tolist(),
        "control_points_moving": synthetic.control_points_moving.tolist(),
        "control_points_fixed": synthetic.control_points_fixed.tolist(),
        "reference_valid_overlap_fraction": overlap_fraction,
        "inverse_matrix_max_absolute_error": inverse_error,
        "control_point_round_trip_max_px": round_trip_error,
        "coordinate_units": "pixels",
        "transform_direction": "moving_to_fixed",
    }
    return moving, label


def make_development_artifacts(config_path: Path, output_root: Path | None) -> dict[str, Any]:
    _, config, plan, pairs, _ = build_development_plan(config_path)
    profile = config["development_rehearsal"]
    source = profile["source"]
    source_path = (ROOT / source["path"]).resolve()
    if sha256_file(source_path) != source["sha256"]:
        raise ValueError("Development source hash mismatch before decode.")

    loaded = load_image(source_path, color_mode="grayscale")
    image = to_grayscale(loaded.array)
    shape = tuple(int(value) for value in config["task_matrix"]["known_gt_synthetic_cross_product"]["image_shape"])
    fixed = resize_image(image, shape, interpolation="area")
    observable_pairs: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        moving, label = prepare_synthetic_case(pair, fixed, config)

        observable_pairs[pair.pair_id] = {
            "fixed": np.asarray(fixed),
            "moving": np.asarray(moving),
            "metadata": {
                "source_id": pair.source_id,
                "source_sha256": pair.source_sha256,
                "case_id": pair.case_id,
                "condition": pair.condition,
                "severity": pair.severity,
                "geometry_seed": pair.geometry_seed,
                "modality_class": pair.modality_class,
                "transform_model": pair.transform_model,
                "evaluation_role": pair.evaluation_role,
                "source_role": pair.source_role,
                "ground_truth_type": pair.ground_truth_type,
                "development_fixture": True,
                "final_evidence": False,
            },
        }
        labels[pair.pair_id] = label

    root = development_output_root(config, output_root)
    write_development_plan(config_path, output_root=root)
    receipt = prepare_artifacts(
        root,
        plan,
        observable_pairs,
        labels,
        development_only=True,
    )
    return {"output_root": str(root), "pairs": len(pairs), "receipt": receipt,
            "final_evidence": False, "week08_source_accessed": False}


def require_strict_final_readiness(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Re-run the authoritative strict gate immediately before first decode."""
    resolved = resolve_path(config_path).resolve()
    if resolved not in {DEFAULT_CONFIG.resolve(), R3_CONFIG.resolve()}:
        raise ValueError("Final preparation requires the canonical preregistered config path.")
    if resolved == DEFAULT_CONFIG.resolve():
        raise ValueError("The exposed R2 holdout is closed and cannot be prepared again.")
    # Keep the R2 verifier immutable.  R3 has a separate fail-closed verifier
    # whose final mode requires the reviewed G5 tag, renewed G6 enrollment,
    # and one-run G7 authorization.  It performs metadata and byte-hash checks
    # only; no image or label decoder is reachable from this call.
    from week08_r3_preflight import run_preflight

    report = run_preflight(ROOT, require_g7=True)
    if report.get("readiness") != "PASS":
        blocking = [
            str(item.get("check"))
            for item in report.get("checks", [])
            if isinstance(item, Mapping) and item.get("status") == "BLOCK"
        ]
        raise ValueError(
            "R3 strict final readiness did not pass; no final source was decoded. "
            "Blocking checks: " + ", ".join(blocking)
        )
    return report


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _final_readiness_receipt(
    config: Mapping[str, Any], readiness: Mapping[str, Any],
) -> dict[str, Any]:
    authorization_contract = config["safety"]["phase7_authorization"]
    release_manifest_path = resolve_path(authorization_contract["release_manifest_path"])
    authorization_path = resolve_path(authorization_contract["authorization_path"])
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    if not isinstance(authorization, dict):
        raise ValueError("Phase 7 authorization must be a JSON object.")
    release_binding = (
        authorization.get("release")
        if isinstance(authorization.get("release"), dict)
        else {}
    )
    payload: dict[str, Any] = {
        "schema_version": FINAL_READINESS_RECEIPT_VERSION,
        "readiness": "PASS",
        "config_sha256": sha256_file(canonical_config_path(config)),
        "runner_code_sha256": runner_code_sha256(config),
        "release_manifest_sha256": sha256_file(release_manifest_path),
        "phase7_authorization_sha256": sha256_file(authorization_path),
        "phase7_authorization_id": authorization.get("authorization_id"),
        "release_commit": release_binding.get("release_commit"),
        "release_tag": release_binding.get("release_tag"),
        "source_ledger_sha256": sha256_file(resolve_path(config["sources"]["ledger_path"])),
        "enrollment_manifest_sha256": sha256_file(
            resolve_path(config["sources"]["enrollment_manifest_path"])
        ),
        "source_registration_sha256": sha256_file(resolve_path(
            authorization_contract.get(
                "source_registration_path", "reports/pre_week08_source_registration.json"
            )
        )),
        "method_catalog_sha256": str(config["frozen_assets"]["method_catalog"]["sha256"]),
        "policy_sha256": str(config["frozen_assets"]["policy"]["sha256"]),
        "preflight_report": dict(readiness),
        "preflight_report_sha256": canonical_sha256(readiness),
        "week08_evaluation_executed": False,
        "real_week08_source_or_label_decoded": False,
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return payload


def _verified_file(path_value: str, expected_sha256: str) -> Path:
    if (
        not isinstance(path_value, str)
        or not path_value
        or "\\" in path_value
        or ":" in path_value
        or path_value.startswith("/")
    ):
        raise ValueError(f"Final artifact path is not project-relative POSIX: {path_value}")
    windows = PureWindowsPath(path_value)
    posix = PurePosixPath(path_value)
    if windows.drive or windows.root or any(part in {"", ".", ".."} for part in posix.parts):
        raise ValueError(f"Final artifact path is unsafe: {path_value}")
    path = (ROOT / Path(*posix.parts)).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Final artifact path escapes the project root: {path_value}") from exc
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError(f"Final artifact hash mismatch: {path_value}")
    return path


def prevalidate_final_inputs(
    config: Mapping[str, Any],
    ledger: Mapping[str, Any],
    manifest: Mapping[str, Any],
    pairs: Sequence[Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Hash every final source/label artifact before the first content decode."""
    sources = {str(item["source_id"]): dict(item) for item in ledger["week08_sources"]}
    rows = {str(item["pair_id"]): dict(item) for item in manifest["pairs"]}
    for source_id, source in sources.items():
        _verified_file(str(source["path"]), str(source["sha256"]))
        components = source.get("components", [])
        if source.get("format") == "mhd" and not components:
            raise ValueError(f"MHD source lacks hashed components: {source_id}")
        for component in components:
            if not isinstance(component, dict):
                raise ValueError(f"Malformed component descriptor: {source_id}")
            _verified_file(str(component["path"]), str(component["sha256"]))
        evidence = source["ground_truth"]
        if evidence["type"] == "synthetic_created_after_freeze":
            for prefix in ("config", "case_spec", "manifest"):
                _verified_file(
                    str(evidence[f"{prefix}_path"]),
                    str(evidence[f"{prefix}_sha256"]),
                )
        elif evidence["type"] in {"verified_landmarks", "verified_masks"}:
            _verified_file(str(evidence["manifest_path"]), str(evidence["manifest_sha256"]))
            for label_file in evidence["label_files"]:
                _verified_file(str(label_file["path"]), str(label_file["sha256"]))
    for row in rows.values():
        descriptor = row.get("label")
        if isinstance(descriptor, dict):
            for prefix in ("fixed", "moving"):
                _verified_file(
                    str(descriptor[f"{prefix}_path"]),
                    str(descriptor[f"{prefix}_sha256"]),
                )
    for pair in pairs:
        source = sources[pair.source_id]
        if pair.metadata.get("source_record_sha256") != canonical_sha256(source):
            raise ValueError(f"Plan/source enrollment binding mismatch: {pair.source_id}")
        if pair.ground_truth_type != "synthetic_created_after_freeze":
            row = rows.get(pair.pair_id)
            if row is None or pair.metadata.get("enrollment_pair_sha256") != canonical_sha256(row):
                raise ValueError(f"Plan/pair enrollment binding mismatch: {pair.pair_id}")
    return sources, rows


def _load_landmarks(path: Path) -> list[list[float]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        points = value.get("points") if isinstance(value, dict) else value
        array = np.asarray(points, dtype=np.float64)
    else:
        delimiter = "\t" if suffix == ".tsv" else ","
        try:
            array = np.loadtxt(path, delimiter=delimiter, dtype=np.float64)
        except ValueError:
            array = np.loadtxt(path, delimiter=delimiter, dtype=np.float64, skiprows=1)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != 2 or not np.isfinite(array).all():
        raise ValueError(f"Landmark file must contain finite x,y rows: {path}")
    return array.tolist()


def _real_case_label(pair, descriptor: Mapping[str, Any] | None) -> dict[str, Any]:
    if pair.ground_truth_type == "unavailable":
        return {
            "pair_id": pair.pair_id,
            "evaluation_role": pair.evaluation_role,
            "source_role": pair.source_role,
            "ground_truth_type": "unavailable",
            "has_geometric_ground_truth": False,
        }
    if not isinstance(descriptor, Mapping):
        raise ValueError("Verified final pair has no authorized label descriptor.")
    descriptor = dict(descriptor)
    base = {
        "pair_id": pair.pair_id,
        "evaluation_role": pair.evaluation_role,
        "source_role": pair.source_role,
        "ground_truth_type": pair.ground_truth_type,
        "has_geometric_ground_truth": True,
        "coordinate_units": str(descriptor["units"]),
        "transform_direction": str(descriptor["direction"]),
    }
    if pair.ground_truth_type == "verified_landmarks":
        fixed_path = _verified_file(
            str(descriptor["fixed_path"]), str(descriptor["fixed_sha256"]),
        )
        moving_path = _verified_file(
            str(descriptor["moving_path"]), str(descriptor["moving_sha256"]),
        )
        base["fixed_landmarks"] = _load_landmarks(fixed_path)
        base["moving_landmarks"] = _load_landmarks(moving_path)
        if len(base["fixed_landmarks"]) != len(base["moving_landmarks"]):
            raise ValueError("Fixed and moving landmark counts differ.")
    elif pair.ground_truth_type == "verified_masks":
        fixed_path = _verified_file(
            str(descriptor["fixed_path"]), str(descriptor["fixed_sha256"]),
        )
        moving_path = _verified_file(
            str(descriptor["moving_path"]), str(descriptor["moving_sha256"]),
        )
        fixed_mask = load_image(fixed_path, color_mode="grayscale").array
        moving_mask = load_image(moving_path, color_mode="grayscale").array
        base["fixed_mask"] = (np.asarray(fixed_mask) != 0).astype(np.uint8).tolist()
        base["moving_mask"] = (np.asarray(moving_mask) != 0).astype(np.uint8).tolist()
    else:
        raise ValueError(f"Unsupported final ground-truth type: {pair.ground_truth_type}")
    return base


def make_final_artifacts(config_path: Path) -> dict[str, Any]:
    """Prepare the final enrolled matrix only after strict G7 readiness passes."""
    canonical_config, config = load_protocol(config_path, development=False)
    readiness = require_strict_final_readiness(canonical_config)
    run_paths = final_paths(config)
    if run_paths.root.exists() and any(run_paths.root.iterdir()):
        raise ValueError("Final decision output must be absent or empty before preparation.")
    if run_paths.prepared.exists() and any(run_paths.prepared.iterdir()):
        raise ValueError("Final holdout output must be absent or empty before preparation.")

    # Persist the exact passing gate and complete frozen plan before any source
    # or label decoder is called.  A later failure intentionally leaves these
    # artifacts behind so the one-run boundary cannot be silently reset.
    load_final_enrollment(config)
    gate_receipt = _final_readiness_receipt(config, readiness)
    _atomic_json(run_paths.final_readiness_receipt, gate_receipt)
    verify_final_readiness_receipt(config, run_paths.final_readiness_receipt)
    gate_receipt_file_sha256 = sha256_file(run_paths.final_readiness_receipt)
    _, config, plan, pairs, _ = build_final_plan(
        canonical_config,
        final_readiness_receipt_sha256=gate_receipt_file_sha256,
    )
    write_week8_plan(run_paths.plan, plan)

    ledger, manifest = load_final_enrollment(config)
    sources, rows = prevalidate_final_inputs(config, ledger, manifest, pairs)

    shape = tuple(int(value) for value in config["task_matrix"]["known_gt_synthetic_cross_product"]["image_shape"])
    fixed_cache: dict[str, np.ndarray] = {}
    observable_pairs: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        if pair.ground_truth_type == "synthetic_created_after_freeze":
            if pair.source_id not in fixed_cache:
                source = sources[pair.source_id]
                source_path = _verified_file(
                    str(source["path"]), str(source["sha256"]),
                )
                image = to_grayscale(load_image(source_path, color_mode="grayscale").array)
                fixed_cache[pair.source_id] = resize_image(image, shape, interpolation="area")
            fixed = fixed_cache[pair.source_id]
            moving, label = prepare_synthetic_case(pair, fixed, config)
        else:
            fixed_descriptor = sources[str(pair.metadata["fixed_source_id"])]
            moving_descriptor = sources[str(pair.metadata["moving_source_id"])]
            fixed_path = _verified_file(
                str(fixed_descriptor["path"]), str(fixed_descriptor["sha256"]),
            )
            moving_path = _verified_file(
                str(moving_descriptor["path"]), str(moving_descriptor["sha256"]),
            )
            fixed = to_grayscale(load_image(fixed_path, color_mode="grayscale").array)
            moving = to_grayscale(load_image(moving_path, color_mode="grayscale").array)
            label_descriptor = rows[pair.pair_id].get("label")
            label = _real_case_label(pair, label_descriptor)
            if pair.ground_truth_type == "verified_masks":
                fixed_mask = np.asarray(label["fixed_mask"], dtype=np.uint8)
                moving_mask = np.asarray(label["moving_mask"], dtype=np.uint8)
                if fixed_mask.shape != np.asarray(fixed).shape[:2]:
                    raise ValueError("Verified fixed-mask shape differs from the fixed image.")
                if moving_mask.shape != np.asarray(moving).shape[:2]:
                    raise ValueError("Verified moving-mask shape differs from the moving image.")
                if not np.any(fixed_mask) or not np.any(moving_mask):
                    raise ValueError("Verified masks must each contain foreground.")
        observable_pairs[pair.pair_id] = {
            "fixed": np.asarray(fixed),
            "moving": np.asarray(moving),
            "metadata": {
                "source_id": pair.source_id,
                "case_id": pair.case_id,
                "modality_class": pair.modality_class,
                "transform_model": pair.transform_model,
                "evaluation_role": pair.evaluation_role,
                "source_role": pair.source_role,
                "ground_truth_type": pair.ground_truth_type,
                "final_evidence": True,
            },
        }
        labels[pair.pair_id] = label

    receipt = prepare_artifacts(
        run_paths,
        plan,
        observable_pairs,
        labels,
        development_only=False,
    )
    return {
        "output_root": str(run_paths.root),
        "holdout_root": str(run_paths.prepared),
        "pairs": len(pairs),
        "receipt": receipt,
        "final_evidence": True,
        "strict_preflight_readiness": readiness["readiness"],
        "final_readiness_receipt_sha256": gate_receipt_file_sha256,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--development-fixture", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.development_fixture:
            result = make_development_artifacts(args.config, args.output_root)
        else:
            if args.output_root is not None:
                raise ValueError("Final artifact roots are frozen in the preregistration config.")
            result = make_final_artifacts(args.config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
