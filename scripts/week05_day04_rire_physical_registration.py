"""Week 5 Day 24: real RIRE CT/MR-T1 rigid registration in physical space."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from image_registration.config import load_config
from image_registration.datasets import sha256_file
from image_registration.medical import read_medical_image_metadata
from image_registration.medical_mutual_information import (
    MedicalMutualInformationConfig,
    MutualInformationRigidRegistration3D,
    homogeneous_3d_to_sitk_affine,
    physical_domain_overlap_3d,
    resample_to_reference_3d,
    rigid_transform_diagnostics_3d,
)
from image_registration.visualization import save_metric_trace

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_pair_record(config: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    manifest_path = _resolve(str(config["dataset"]["manifest"]))
    if not manifest_path.exists():
        raise FileNotFoundError(f"RIRE manifest does not exist: {manifest_path}")
    manifest = _read_json(manifest_path)
    pair_id = str(config["dataset"]["pair_id"])
    matches = [item for item in manifest.get("records", []) if str(item.get("pair_id")) == pair_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one RIRE manifest record for pair_id={pair_id}.")
    record = dict(matches[0])
    if str(record.get("fixed_modality")) != str(config["dataset"]["expected_fixed_modality"]):
        raise ValueError("RIRE fixed modality does not match the Day 24 configuration.")
    if str(record.get("moving_modality")) != str(config["dataset"]["expected_moving_modality"]):
        raise ValueError("RIRE moving modality does not match the Day 24 configuration.")
    return record, manifest_path


def _metadata_match(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    return {
        "dimension": int(actual["dimension"]) == int(expected["dimension"]),
        "size_xyz": list(actual["size_xyz"]) == list(expected["size_xyz"]),
        "spacing_xyz_mm": bool(
            np.allclose(actual["spacing_xyz_mm"], expected["spacing_xyz_mm"], atol=1e-8, rtol=0.0)
        ),
        "origin_xyz_mm": bool(
            np.allclose(actual["origin_xyz_mm"], expected["origin_xyz_mm"], atol=1e-8, rtol=0.0)
        ),
        "direction": bool(np.allclose(actual["direction"], expected["direction"], atol=1e-8, rtol=0.0)),
        "components_per_pixel": int(actual["components_per_pixel"])
        == int(expected["components_per_pixel"]),
        "pixel_type": str(actual["pixel_type"]) == str(expected["pixel_type"]),
    }


def _validate_dataset_files(
    config: dict[str, Any],
    record: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    fixed_path = _resolve(str(record["fixed_image"]))
    moving_path = _resolve(str(record["moving_image"]))
    missing = [str(path) for path in (fixed_path, moving_path) if not path.exists()]
    if missing:
        expected_layout = PROJECT_ROOT / "data" / "raw" / "rire" / "training_001" / "mha"
        raise FileNotFoundError(
            "Day 24 requires the prepared local RIRE MHA files. Missing: "
            + ", ".join(missing)
            + f". Expected local directory: {expected_layout}"
        )

    fixed_metadata = read_medical_image_metadata(fixed_path).as_dict()
    moving_metadata = read_medical_image_metadata(moving_path).as_dict()
    fixed_checks = _metadata_match(fixed_metadata, dict(record["fixed_metadata"]))
    moving_checks = _metadata_match(moving_metadata, dict(record["moving_metadata"]))
    if not all(fixed_checks.values()):
        failed = [name for name, value in fixed_checks.items() if not value]
        raise ValueError(f"Fixed RIRE metadata differs from the prepared manifest: {failed}")
    if not all(moving_checks.values()):
        failed = [name for name, value in moving_checks.items() if not value]
        raise ValueError(f"Moving RIRE metadata differs from the prepared manifest: {failed}")

    verify_hashes = bool(config["dataset"].get("verify_sha256", True))
    fixed_hash = sha256_file(fixed_path) if verify_hashes else None
    moving_hash = sha256_file(moving_path) if verify_hashes else None
    if verify_hashes and fixed_hash != str(record["fixed_sha256"]):
        raise ValueError("Fixed RIRE SHA-256 does not match the prepared manifest.")
    if verify_hashes and moving_hash != str(record["moving_sha256"]):
        raise ValueError("Moving RIRE SHA-256 does not match the prepared manifest.")

    return fixed_path, moving_path, {
        "fixed_metadata": fixed_metadata,
        "moving_metadata": moving_metadata,
        "fixed_metadata_checks": fixed_checks,
        "moving_metadata_checks": moving_checks,
        "sha256_verified": verify_hashes,
        "fixed_sha256": fixed_hash,
        "moving_sha256": moving_hash,
        "all_metadata_checks_passed": bool(all(fixed_checks.values()) and all(moving_checks.values())),
    }


def _mi_config(base: dict[str, Any], initialization: str) -> MedicalMutualInformationConfig:
    return MedicalMutualInformationConfig(
        histogram_bins=int(base["histogram_bins"]),
        sampling_strategy=str(base["sampling_strategy"]),
        sampling_percentage=float(base["sampling_percentage"]),
        sampling_seed=int(base["sampling_seed"]),
        learning_rate=float(base["learning_rate"]),
        minimum_step=float(base["minimum_step"]),
        number_of_iterations=int(base["number_of_iterations"]),
        relaxation_factor=float(base["relaxation_factor"]),
        gradient_magnitude_tolerance=float(base["gradient_magnitude_tolerance"]),
        shrink_factors=tuple(int(value) for value in base["shrink_factors"]),
        smoothing_sigmas=tuple(float(value) for value in base["smoothing_sigmas"]),
        initialization=initialization,  # type: ignore[arg-type]
        preprocessing_sigma_mm=float(base["preprocessing_sigma_mm"]),
    )


def _support_on_fixed(fixed: Any, moving: Any, fixed_to_moving: Any) -> np.ndarray:
    import SimpleITK as sitk

    support = sitk.GetImageFromArray(
        np.ones(tuple(reversed(moving.GetSize())), dtype=np.uint8)
    )
    support.CopyInformation(moving)
    output = sitk.Resample(
        support,
        fixed,
        fixed_to_moving,
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )
    return sitk.GetArrayFromImage(output).astype(bool)


def _robust_display(image: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    values = np.asarray(image, dtype=np.float32)
    selected = values if mask is None else values[np.asarray(mask, dtype=bool)]
    selected = selected[np.isfinite(selected)]
    if selected.size == 0:
        return np.zeros_like(values, dtype=np.float32)
    low, high = np.percentile(selected, [1.0, 99.0])
    if not np.isfinite(low) or not np.isfinite(high) or np.isclose(high, low):
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def _orthogonal_slices(volume: np.ndarray) -> dict[str, np.ndarray]:
    values = np.asarray(volume)
    if values.ndim != 3:
        raise ValueError("Expected a 3D NumPy volume.")
    z, y, x = (int(size // 2) for size in values.shape)
    return {
        "z_center": values[z, :, :],
        "y_center": values[:, y, :],
        "x_center": values[:, :, x],
    }


def _save_orthogonal_comparison(
    fixed: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
    output_path: Path,
    *,
    title: str,
) -> None:
    fixed_slices = _orthogonal_slices(_robust_display(fixed))
    before_slices = _orthogonal_slices(_robust_display(before))
    after_slices = _orthogonal_slices(_robust_display(after))
    columns = ["z_center", "y_center", "x_center"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(11.0, 8.0))
    FigureCanvasAgg(fig)
    axes = fig.subplots(3, 3)
    for row, (label, slices) in enumerate(
        [("Fixed CT", fixed_slices), ("Moving MR-T1 before", before_slices), ("Registered MR-T1", after_slices)]
    ):
        for column, plane in enumerate(columns):
            axes[row, column].imshow(slices[plane], cmap="gray", origin="lower")
            axes[row, column].set_title(f"{label}: {plane}")
            axes[row, column].axis("off")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    fig.clear()


def _save_orthogonal_overlays(
    fixed: np.ndarray,
    comparison: np.ndarray,
    output_path: Path,
    *,
    title: str,
) -> None:
    fixed_norm = _robust_display(fixed)
    comparison_norm = _robust_display(comparison)
    fixed_slices = _orthogonal_slices(fixed_norm)
    comparison_slices = _orthogonal_slices(comparison_norm)
    columns = ["z_center", "y_center", "x_center"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(11.0, 3.8))
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, 3)
    for column, plane in enumerate(columns):
        fixed_slice = fixed_slices[plane]
        moving_slice = comparison_slices[plane]
        rgb = np.stack(
            [fixed_slice, moving_slice, np.zeros_like(fixed_slice)],
            axis=-1,
        )
        axes[column].imshow(rgb, origin="lower")
        axes[column].set_title(plane)
        axes[column].axis("off")
    fig.suptitle(title + " (red=fixed CT, green=MR-T1)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    fig.clear()


def _save_volume_joint_histogram(
    fixed: np.ndarray,
    comparison: np.ndarray,
    mask: np.ndarray,
    output_path: Path,
    *,
    bins: int,
    max_points: int,
    title: str,
) -> None:
    selector = np.asarray(mask, dtype=bool)
    if fixed.shape != comparison.shape or fixed.shape != selector.shape:
        raise ValueError("Volume joint histogram inputs must have the same shape.")
    fixed_values = np.asarray(fixed, dtype=np.float32)[selector]
    comparison_values = np.asarray(comparison, dtype=np.float32)[selector]
    finite = np.isfinite(fixed_values) & np.isfinite(comparison_values)
    fixed_values = fixed_values[finite]
    comparison_values = comparison_values[finite]
    if fixed_values.size == 0:
        raise ValueError("Volume joint histogram requires at least one valid voxel.")
    if fixed_values.size > max_points:
        indices = np.linspace(0, fixed_values.size - 1, max_points, dtype=np.int64)
        fixed_values = fixed_values[indices]
        comparison_values = comparison_values[indices]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(5.5, 5.0))
    FigureCanvasAgg(fig)
    axis = fig.subplots(1, 1)
    histogram = axis.hist2d(fixed_values, comparison_values, bins=bins)
    axis.set_title(title)
    axis.set_xlabel("Fixed CT intensity")
    axis.set_ylabel("MR-T1 intensity")
    fig.colorbar(histogram[3], ax=axis, label="Voxel count")
    fig.tight_layout()
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    fig.clear()


def _record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    runtimes = [float(item["runtime_ms"]) for item in records if item.get("runtime_ms") is not None]
    return {
        "variant_count": len(records),
        "method_success_count": sum(bool(item.get("method_success")) for item in records),
        "technical_validation_pass_count": sum(
            bool(item.get("technical_validation_pass")) for item in records
        ),
        "plausible_transform_count": sum(bool(item.get("plausible_transform")) for item in records),
        "metadata_integrity_count": sum(bool(item.get("metadata_integrity")) for item in records),
        "mean_runtime_ms": None if not runtimes else float(np.mean(runtimes)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/week05_day04_rire_physical_registration.yaml",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        import SimpleITK as sitk
    except ImportError as exc:
        raise RuntimeError("SimpleITK is required for the Day 24 RIRE experiment.") from exc

    config_path = _resolve(args.config)
    config = load_config(config_path)
    record, manifest_path = _load_pair_record(config)
    fixed_path, moving_path, dataset_integrity = _validate_dataset_files(config, record)

    output_root = _resolve(str(config["output"]["directory"]))
    if output_root.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output directory already exists: {output_root}. Use --overwrite to replace Day 24 evidence."
        )
    output_root.mkdir(parents=True, exist_ok=True)

    fixed = sitk.ReadImage(str(fixed_path))
    moving = sitk.ReadImage(str(moving_path))
    if int(fixed.GetDimension()) != 3 or int(moving.GetDimension()) != 3:
        raise ValueError("Day 24 requires 3D CT and MR-T1 volumes.")

    fixed_array = sitk.GetArrayFromImage(sitk.Cast(fixed, sitk.sitkFloat32)).astype(np.float32)
    identity = sitk.Transform(3, sitk.sitkIdentity)
    moving_before = resample_to_reference_3d(
        sitk.Cast(moving, sitk.sitkFloat32),
        sitk.Cast(fixed, sitk.sitkFloat32),
        identity,
    )
    moving_before_array = sitk.GetArrayFromImage(moving_before).astype(np.float32)
    overlap_before = physical_domain_overlap_3d(fixed, moving, identity)
    support_before = _support_on_fixed(fixed, moving, identity)

    frozen = dict(config["frozen_mutual_information"])
    plausibility_config = dict(config["plausibility"])
    visualization = dict(config["visualization"])
    records: list[dict[str, Any]] = []

    print("Week 5 Day 24: real RIRE CT/MR-T1 physical-space registration")
    print(f"Pair: {record['pair_id']} fixed={record['fixed_modality']} moving={record['moving_modality']}")
    print("Ground truth landmarks/masks are not integrated. TRE, Dice, and anatomical correctness are not reported.")
    print(f"Initial physical FOV coverage (fixed by moving): {overlap_before['fixed_domain_covered_by_moving_fraction']:.3f}")

    for variant_name, variant in config["variants"].items():
        initialization = str(variant["initialization"])
        registration = MutualInformationRigidRegistration3D(_mi_config(frozen, initialization))
        result = registration.register_sitk(fixed, moving)
        convergence = result.convergence_info

        if result.success:
            fixed_to_moving_matrix = np.asarray(
                convergence["fixed_to_moving_physical_matrix"], dtype=np.float64
            )
            fixed_to_moving_transform = homogeneous_3d_to_sitk_affine(fixed_to_moving_matrix)
            overlap_after = physical_domain_overlap_3d(fixed, moving, fixed_to_moving_transform)
            support_after = _support_on_fixed(fixed, moving, fixed_to_moving_transform)
            diagnostics = rigid_transform_diagnostics_3d(
                np.asarray(result.transform, dtype=np.float64),
                fixed_size_xyz=tuple(int(value) for value in fixed.GetSize()),
                fixed_spacing_xyz_mm=tuple(float(value) for value in fixed.GetSpacing()),
                max_rotation_degrees=float(plausibility_config["max_rotation_degrees"]),
                max_translation_fraction_of_diagonal=float(
                    plausibility_config["max_translation_fraction_of_fixed_diagonal"]
                ),
                determinant_tolerance=float(plausibility_config["determinant_tolerance"]),
                orthogonality_tolerance=float(plausibility_config["orthogonality_tolerance"]),
            )
        else:
            overlap_after = None
            support_after = support_before
            diagnostics = {
                "plausible": False,
                "rejection_reasons": ["registration_method_failed"],
            }

        metadata_integrity = bool(convergence.get("registered_geometry_matches_fixed", False))
        plausible = bool(diagnostics.get("plausible", False))
        technical_pass = bool(result.success and plausible and metadata_integrity)

        variant_dir = output_root / str(variant_name)
        variant_dir.mkdir(parents=True, exist_ok=True)
        comparison_path = variant_dir / "orthogonal_slices.png"
        overlay_before_path = variant_dir / "overlay_before.png"
        overlay_after_path = variant_dir / "overlay_after.png"
        joint_before_path = variant_dir / "joint_histogram_before.png"
        joint_after_path = variant_dir / "joint_histogram_after.png"
        trace_path = variant_dir / "metric_trace.png"

        _save_orthogonal_comparison(
            fixed_array,
            moving_before_array,
            np.asarray(result.registered_image, dtype=np.float32),
            comparison_path,
            title=f"{variant_name}: central physical-grid slices",
        )
        _save_orthogonal_overlays(
            fixed_array,
            moving_before_array,
            overlay_before_path,
            title=f"{variant_name}: before registration",
        )
        _save_orthogonal_overlays(
            fixed_array,
            np.asarray(result.registered_image, dtype=np.float32),
            overlay_after_path,
            title=f"{variant_name}: after registration",
        )
        _save_volume_joint_histogram(
            fixed_array,
            moving_before_array,
            support_before,
            joint_before_path,
            bins=int(visualization["joint_histogram_bins"]),
            max_points=int(visualization["joint_histogram_max_points"]),
            title=f"{variant_name}: before registration",
        )
        _save_volume_joint_histogram(
            fixed_array,
            np.asarray(result.registered_image, dtype=np.float32),
            support_after,
            joint_after_path,
            bins=int(visualization["joint_histogram_bins"]),
            max_points=int(visualization["joint_histogram_max_points"]),
            title=f"{variant_name}: after registration",
        )
        save_metric_trace(
            list(convergence.get("metric_trace", [])),
            trace_path,
            title=f"{variant_name}: 3D Mattes MI convergence",
        )

        output_record = {
            "variant": str(variant_name),
            "role": str(variant.get("role", "")),
            "pair_id": str(record["pair_id"]),
            "fixed_modality": str(record["fixed_modality"]),
            "moving_modality": str(record["moving_modality"]),
            "coordinate_system": "physical",
            "transform_model": "rigid_3d",
            "transform_direction": "Moving -> Fixed",
            "initialization": initialization,
            "method_success": bool(result.success),
            "technical_validation_pass": technical_pass,
            "plausible_transform": plausible,
            "transform_plausibility": diagnostics,
            "metadata_integrity": metadata_integrity,
            "estimated_moving_to_fixed_physical_matrix": np.asarray(result.transform).tolist(),
            "fixed_to_moving_physical_matrix": convergence.get("fixed_to_moving_physical_matrix"),
            "initial_fixed_to_moving_physical_matrix": convergence.get(
                "initial_fixed_to_moving_physical_matrix"
            ),
            "overlap_before_registration": overlap_before,
            "overlap_after_registration": overlap_after,
            "runtime_ms": float(result.runtime_seconds * 1000.0),
            "final_metric_value": convergence.get("final_metric_value"),
            "optimizer_iteration": convergence.get("optimizer_iteration"),
            "optimizer_stop_condition": convergence.get("optimizer_stop_condition"),
            "valid_metric_points": convergence.get("valid_metric_points"),
            "metric_trace": convergence.get("metric_trace", []),
            "failure_reason": result.failure_reason,
            "fixed_geometry": convergence.get("fixed_geometry"),
            "moving_geometry": convergence.get("moving_geometry"),
            "registered_geometry": convergence.get("registered_geometry"),
            "ground_truth_status": str(record.get("ground_truth_status")),
            "tre_mm": None,
            "dice": None,
            "anatomical_correctness": "not_assessed_without_verified_reference",
            "figures": {
                "orthogonal_slices": _relative(comparison_path),
                "overlay_before": _relative(overlay_before_path),
                "overlay_after": _relative(overlay_after_path),
                "joint_histogram_before": _relative(joint_before_path),
                "joint_histogram_after": _relative(joint_after_path),
                "metric_trace": _relative(trace_path),
            },
        }
        _write_json(variant_dir / "result.json", output_record)
        records.append(output_record)

        overlap_text = (
            "n/a"
            if overlap_after is None
            else f"{overlap_after['fixed_domain_covered_by_moving_fraction']:.3f}"
        )
        print(
            f"{variant_name:30s} method_success={result.success} "
            f"technical_pass={technical_pass} plausible={plausible} "
            f"metadata={metadata_integrity} overlap_fixed={overlap_text} "
            f"runtime={result.runtime_seconds * 1000.0:.2f} ms"
        )

    report = {
        "week": 5,
        "day": 24,
        "status": "target_run_complete_review_required",
        "purpose": (
            "Run the prepared real RIRE CT/MR-T1 pair through 3D rigid Mattes Mutual Information "
            "in physical coordinates while preserving metadata and strict evidence limits."
        ),
        "configuration": _relative(config_path),
        "dataset_manifest": _relative(manifest_path),
        "dataset": {
            "pair_id": str(record["pair_id"]),
            "fixed_image": _relative(fixed_path),
            "moving_image": _relative(moving_path),
            "fixed_modality": str(record["fixed_modality"]),
            "moving_modality": str(record["moving_modality"]),
            "ground_truth_status": str(record.get("ground_truth_status")),
            "integrity": dataset_integrity,
        },
        "frozen_day22_metric_optimizer_choices": frozen,
        "real_data_change": (
            "Day 24 keeps the frozen metric and optimizer settings but uses geometry initialization "
            "as the primary 3D physical-space path. Identity is a diagnostic comparator."
        ),
        "evaluation_policy": {
            "landmark_tre_enabled": False,
            "dice_enabled": False,
            "anatomical_correctness_claim_allowed": False,
            "technical_evidence": [
                "method execution",
                "physical transform plausibility",
                "metadata integrity",
                "physical field-of-view overlap",
                "optimizer trace and stop condition",
                "joint histogram diagnostics",
                "central slice and overlay diagnostics",
            ],
        },
        "records": records,
        "summary": _record_summary(records),
        "limitations": [
            "Verified RIRE landmarks or masks are not integrated for this pair, so Day 24 does not report TRE, Dice, or anatomical correctness.",
            "Physical field-of-view overlap measures geometric domain coverage, not anatomical alignment quality.",
            "Joint histograms and overlays are descriptive diagnostics and are not independent geometric ground truth.",
            "The identity-initialized run is a diagnostic comparator. Day 24 does not select a winner from visual appearance alone.",
            "Only rigid 3D registration is evaluated on Day 24. Affine 3D is intentionally deferred until the rigid path is reviewed.",
        ],
        "next_step": "Review the target Windows Day 24 evidence before starting Day 25 or adding any 3D affine extension.",
    }
    report_path = _resolve(str(config["output"]["report_snapshot"]))
    _write_json(report_path, report)
    _write_json(output_root / "report.json", report)

    summary = report["summary"]
    print("\nDay 24 target run summary")
    print(f"Method success: {summary['method_success_count']}/{summary['variant_count']}")
    print(
        "Technical validation pass: "
        f"{summary['technical_validation_pass_count']}/{summary['variant_count']}"
    )
    print(f"Tracked report: {_relative(report_path)}")
    print("No TRE, Dice, or anatomical correctness claim is made without verified reference data.")
    print("Do not start Day 25 until the target Windows Day 24 evidence is reviewed.")


if __name__ == "__main__":
    main()
