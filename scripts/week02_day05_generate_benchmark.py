"""Generate and validate the integrated Week 2 registration benchmark."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

import cv2
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_registration.benchmark import (  # noqa: E402
    benchmark_manifest_fingerprint,
    build_case_plan,
    sample_benchmark_ground_truth,
    validate_benchmark_records,
    validate_integrated_benchmark_config,
)
from image_registration.degradations import apply_degradation  # noqa: E402
from image_registration.io import load_image  # noqa: E402
from image_registration.multimodal import apply_multimodal_mapping  # noqa: E402
from image_registration.overlap import (  # noqa: E402
    apply_field_of_view,
    combine_valid_masks,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
    transformed_support_mask,
)
from image_registration.preprocessing import resize_image  # noqa: E402
from image_registration.synthetic import control_point_round_trip_error, generate_synthetic_pair  # noqa: E402
from image_registration.visualization import save_grayscale_image  # noqa: E402
from image_registration.warping import warp_image  # noqa: E402


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _per_tier_specification(case: Mapping[str, Any], tier: str) -> dict[str, Any]:
    resolved = {key: value for key, value in case.items() if key not in {"id", "per_tier"}}
    per_tier = case.get("per_tier", {})
    if per_tier:
        if not isinstance(per_tier, Mapping):
            raise ValueError("per_tier must be a mapping.")
        tier_values = per_tier.get(tier, {})
        if not isinstance(tier_values, Mapping):
            raise ValueError(f"per_tier.{tier} must be a mapping.")
        resolved.update(tier_values)
    return resolved


def _sample_interval(rng: np.random.Generator, values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (2,):
        raise ValueError("Severity interval must contain [minimum, maximum].")
    low, high = float(array[0]), float(array[1])
    return low if np.isclose(low, high) else float(rng.uniform(low, high))


def _load_sources(manifest_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, np.ndarray]]:
    manifest = _read_json(manifest_path)
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("General real-source manifest must contain records.")

    metadata: dict[str, dict[str, Any]] = {}
    images: dict[str, np.ndarray] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("General source records must be objects.")
        source_id = str(record["image_id"])
        loaded = load_image(_resolve(str(record["path"])), color_mode="grayscale")
        if loaded.array.ndim != 2:
            raise ValueError("Integrated benchmark sources must be 2D grayscale images.")
        metadata[source_id] = record
        images[source_id] = loaded.array
    return metadata, images


def _save_case_gallery(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    selected: list[dict[str, Any]] = []
    for tier in ("easy", "moderate", "hard"):
        tier_records = [record for record in records if record["tier"] == tier]
        selected.append(next(record for record in tier_records if record["modality_class"] == "monomodal"))
        selected.append(
            next(record for record in tier_records if record["modality_class"] == "simulated_multimodal")
        )

    rows: list[np.ndarray] = []
    tile_size = (180, 180)
    for record in selected:
        case_dir = _resolve(record["case_directory"])
        panels = []
        for filename in ("fixed.png", "moving.png", "ground_truth_registered.png", "valid_overlap_fixed.png"):
            image = cv2.imread(str(case_dir / filename), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise RuntimeError(f"Could not read gallery image: {case_dir / filename}")
            panels.append(cv2.resize(image, tile_size, interpolation=cv2.INTER_AREA))
        row = np.hstack(panels)
        label = f"{record['tier']} | {record['modality_class']} | {record['transform_family']}"
        cv2.putText(row, label, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, 255, 1, cv2.LINE_AA)
        rows.append(row)

    gallery = np.vstack(rows)
    path = output_dir / "representative_gallery.png"
    if not cv2.imwrite(str(path), gallery):
        raise RuntimeError(f"Could not write representative gallery: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/week02_day05_integrated_benchmark.yaml",
        help="Configuration path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a YAML mapping.")
    validate_integrated_benchmark_config(config)

    benchmark_cfg = config["benchmark"]
    base_seed = int(config["experiment"].get("seed", 42))
    samples_per_tier = int(benchmark_cfg["samples_per_tier"])
    image_size_values = benchmark_cfg.get("image_size", [256, 256])
    image_size = (int(image_size_values[0]), int(image_size_values[1]))
    interpolation = str(benchmark_cfg.get("interpolation", "linear"))
    border_value = float(benchmark_cfg.get("border_value", 0.0))
    ordered_tiers = ("easy", "moderate", "hard")

    source_manifest_path = _resolve(str(config["sources"]["general_manifest"])).resolve()
    source_metadata, source_images = _load_sources(source_manifest_path)
    source_ids = list(source_images)

    degradation_cases = config["degradation_cases"]
    degradation_map = {str(case["id"]): case for case in degradation_cases}
    multimodal_cases = config["multimodal_cases"]
    multimodal_map = {str(case["id"]): case for case in multimodal_cases}

    plans = build_case_plan(
        base_seed=base_seed,
        samples_per_tier=samples_per_tier,
        tiers=ordered_tiers,
        source_ids=source_ids,
        transform_families=[str(value) for value in benchmark_cfg["transform_families"]],
        degradation_ids=[str(case["id"]) for case in degradation_cases],
        multimodal_ids=[str(case["id"]) for case in multimodal_cases],
        restricted_fov_every=int(benchmark_cfg.get("restricted_fov_every", 4)),
    )
    plan_fingerprint = benchmark_manifest_fingerprint([plan.as_dict() for plan in plans])

    output_dir = _resolve(str(config["output"]["directory"])).resolve()
    prior_fingerprint: str | None = None
    prior_summary_path = output_dir / "benchmark_summary.json"
    if prior_summary_path.exists():
        try:
            prior_summary = _read_json(prior_summary_path)
            prior_fingerprint = str(prior_summary.get("dataset_fingerprint", "")) or None
        except (OSError, ValueError, json.JSONDecodeError):
            prior_fingerprint = None
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    tiers = config["difficulty_tiers"]
    fov_cfg = config["partial_overlap"]

    print("Week 2 Day 5 integrated benchmark generation")
    print("--------------------------------------------")
    print(f"Seed: {base_seed}")
    print(f"Samples per tier: {samples_per_tier}")
    print(f"Total planned cases: {len(plans)}")

    for index, plan in enumerate(plans, start=1):
        rng = np.random.default_rng(plan.seed)
        fixed = resize_image(source_images[plan.source_id], image_size, interpolation="area")
        tier_spec = tiers[plan.tier]
        ground_truth = sample_benchmark_ground_truth(
            plan.transform_family,
            tier_spec,
            rng,
            fixed.shape,
        )
        pair = generate_synthetic_pair(
            fixed,
            ground_truth,
            interpolation=interpolation,
            border_value=border_value,
        )

        moving = pair.moving
        multimodal_metadata: dict[str, Any] | None = None
        if plan.modality_class == "simulated_multimodal":
            if plan.multimodal_id is None:
                raise RuntimeError("Simulated multimodal case is missing a mapping ID.")
            mapping_spec = _per_tier_specification(multimodal_map[plan.multimodal_id], plan.tier)
            mapping_spec["noise_base_sigma_fraction"] = _sample_interval(
                rng, tier_spec["noise_base_sigma_fraction"]
            )
            mapping_spec["noise_signal_sigma_fraction"] = _sample_interval(
                rng, tier_spec["noise_signal_sigma_fraction"]
            )
            mapped = apply_multimodal_mapping(moving, mapping_spec, rng=rng)
            moving = mapped.image
            multimodal_metadata = mapped.metadata

        degradation_case = degradation_map[plan.degradation_id]
        degradation_spec = _per_tier_specification(degradation_case, plan.tier)
        if str(degradation_spec.get("type", "")).lower() == "none":
            degraded = moving.copy()
            visibility_mask = np.ones(moving.shape[:2], dtype=np.uint8)
            degradation_metadata: dict[str, Any] = {"type": "none"}
        else:
            degradation = apply_degradation(moving, degradation_spec, rng=rng)
            degraded = degradation.image
            visibility_mask = degradation.visibility_mask
            degradation_metadata = degradation.metadata

        moving_support = transformed_support_mask(
            fixed.shape,
            ground_truth.fixed_to_moving,
            destination_shape=fixed.shape,
        )
        moving_valid = moving_support
        final_moving = degraded
        fov_metadata: dict[str, Any] | None = None
        if plan.restricted_fov:
            tier_fov = fov_cfg["per_tier"][plan.tier]
            fov_mask = rectangular_field_of_view_mask(
                fixed.shape,
                width_fraction=float(tier_fov["width_fraction"]),
                height_fraction=float(tier_fov["height_fraction"]),
                center_x_fraction=float(tier_fov.get("center_x_fraction", 0.5)),
                center_y_fraction=float(tier_fov.get("center_y_fraction", 0.5)),
            )
            moving_valid = combine_valid_masks(moving_support, fov_mask)
            final_moving = apply_field_of_view(
                degraded,
                fov_mask,
                fill_value=float(fov_cfg.get("fill_value", 0.0)),
            )
            fov_metadata = {
                "width_fraction": float(tier_fov["width_fraction"]),
                "height_fraction": float(tier_fov["height_fraction"]),
                "center_x_fraction": float(tier_fov.get("center_x_fraction", 0.5)),
                "center_y_fraction": float(tier_fov.get("center_y_fraction", 0.5)),
            }

        valid_overlap = overlap_mask_in_fixed_space(
            moving_valid,
            ground_truth.moving_to_fixed,
            fixed_shape=fixed.shape,
        )
        effective_moving = combine_valid_masks(moving_valid, visibility_mask)
        effective_fixed = overlap_mask_in_fixed_space(
            effective_moving,
            ground_truth.moving_to_fixed,
            fixed_shape=fixed.shape,
        )
        registered = warp_image(
            final_moving,
            ground_truth.moving_to_fixed,
            output_shape=fixed.shape,
            interpolation=interpolation,
            border_value=border_value,
        )
        control_error = float(np.max(control_point_round_trip_error(pair)))

        case_dir = output_dir / plan.tier / plan.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        fixed_path = save_grayscale_image(case_dir / "fixed.png", fixed, normalize=False)
        moving_path = save_grayscale_image(case_dir / "moving.png", final_moving, normalize=False)
        registered_path = save_grayscale_image(
            case_dir / "ground_truth_registered.png", registered, normalize=False
        )
        overlap_path = save_grayscale_image(
            case_dir / "valid_overlap_fixed.png", valid_overlap * 255, normalize=False
        )
        effective_path = save_grayscale_image(
            case_dir / "effective_evaluation_mask_fixed.png", effective_fixed * 255, normalize=False
        )

        record: dict[str, Any] = {
            **plan.as_dict(),
            "source": {
                "source_name": source_metadata[plan.source_id]["source_name"],
                "source_path": source_metadata[plan.source_id]["path"],
            },
            "transform_family": ground_truth.transform_type,
            "ground_truth": ground_truth.as_dict(),
            "degradation": degradation_metadata,
            "multimodal_mapping": multimodal_metadata,
            "restricted_fov_parameters": fov_metadata,
            "fixed_overlap_fraction": overlap_fraction(valid_overlap),
            "effective_evaluation_fraction": overlap_fraction(effective_fixed),
            "visible_fraction_moving": float(np.mean(visibility_mask, dtype=np.float64)),
            "control_point_max_error_px": control_error,
            "case_directory": str(case_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "files": {
                "fixed": str(fixed_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "moving": str(moving_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "ground_truth_registered": str(registered_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "valid_overlap_fixed": str(overlap_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "effective_evaluation_mask_fixed": str(effective_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            },
            "sha256": {
                "fixed": _sha256_file(fixed_path),
                "moving": _sha256_file(moving_path),
                "ground_truth_registered": _sha256_file(registered_path),
                "valid_overlap_fixed": _sha256_file(overlap_path),
                "effective_evaluation_mask_fixed": _sha256_file(effective_path),
            },
        }
        _write_json(case_dir / "metadata.json", record)
        records.append(record)

        if index % 10 == 0 or index == len(plans):
            print(f"Generated {index:>2}/{len(plans)} cases")

    coverage = validate_benchmark_records(records, samples_per_tier=samples_per_tier)
    dataset_fingerprint = benchmark_manifest_fingerprint(records)

    real_multimodal_reference: dict[str, Any] | None = None
    rire_manifest_path = _resolve(str(config["sources"]["real_multimodal_manifest"])).resolve()
    if rire_manifest_path.exists():
        rire_manifest = _read_json(rire_manifest_path)
        real_multimodal_reference = {
            "manifest": str(rire_manifest_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "dataset_id": rire_manifest.get("dataset_id"),
            "record_count": len(rire_manifest.get("records", [])),
            "ground_truth_note": (
                rire_manifest.get("records", [{}])[0].get("ground_truth_status")
                if rire_manifest.get("records")
                else None
            ),
        }

    manifest = {
        "schema_version": 1,
        "experiment": str(config["experiment"]["name"]),
        "seed": base_seed,
        "samples_per_tier": samples_per_tier,
        "total_cases": len(records),
        "plan_fingerprint": plan_fingerprint,
        "dataset_fingerprint": dataset_fingerprint,
        "general_source_manifest": str(source_manifest_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "real_multimodal_reference": real_multimodal_reference,
        "coverage": coverage,
        "records": records,
    }
    _write_json(output_dir / "benchmark_manifest.json", manifest)

    csv_path = output_dir / "benchmark_index.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "tier",
                "source_id",
                "transform_family",
                "modality_class",
                "degradation_id",
                "multimodal_id",
                "restricted_fov",
                "fixed_overlap_fraction",
                "effective_evaluation_fraction",
                "control_point_max_error_px",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in writer.fieldnames})

    gallery_path = _save_case_gallery(output_dir, records)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    reproduction_match = None if prior_fingerprint is None else prior_fingerprint == dataset_fingerprint
    summary = {
        "status": "complete",
        "coverage": coverage,
        "plan_fingerprint": plan_fingerprint,
        "dataset_fingerprint": dataset_fingerprint,
        "prior_dataset_fingerprint": prior_fingerprint,
        "reproduction_match_with_previous_run": reproduction_match,
        "representative_gallery": str(gallery_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    _write_json(output_dir / "benchmark_summary.json", summary)

    print()
    print("Benchmark coverage")
    print(f"  total cases:          {coverage['total_records']}")
    print(f"  easy/moderate/hard:   {coverage['counts_by_tier']}")
    print(f"  modality counts:      {coverage['modality_counts']}")
    print(f"  transform families:   {', '.join(coverage['transform_families'])}")
    print(f"  degradation types:    {', '.join(coverage['degradation_types'])}")
    print(f"  restricted FOV cases: {coverage['restricted_fov_cases']}")
    print(f"  dataset fingerprint:  {dataset_fingerprint}")
    if reproduction_match is None:
        print("  repeat check:         baseline stored for the next identical run")
    else:
        print(f"  repeat check:         {'MATCH' if reproduction_match else 'MISMATCH'}")
    print(f"Output: {output_dir.relative_to(PROJECT_ROOT)}")
    print("Week 2 Day 5 complete: integrated benchmark generated and validated.")


if __name__ == "__main__":
    main()
