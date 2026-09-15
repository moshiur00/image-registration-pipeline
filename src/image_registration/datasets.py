"""Dataset manifest creation and integrity validation utilities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .io import load_image
from .medical import read_medical_image_metadata
from .rire import parse_rire_header, read_rire_volume


@dataclass(frozen=True)
class DatasetValidationReport:
    """Integrity-validation result for one dataset manifest."""

    dataset_id: str
    checked_records: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Return True when no integrity errors were found."""
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly report."""
        return {
            "dataset_id": self.dataset_id,
            "checked_records": self.checked_records,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of one file."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    """Load a JSON dataset manifest."""
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest does not exist: {manifest_path}")
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Dataset manifest root must be a JSON object.")
    return loaded


def write_dataset_manifest(manifest: Mapping[str, Any], path: str | Path) -> Path:
    """Write a dataset manifest with stable formatting."""
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_raster_source_record(
    image_id: str,
    path: str | Path,
    *,
    project_root: str | Path,
    modality: str = "visible",
    source_name: str,
) -> dict[str, Any]:
    """Build one manifest record for a real raster source image."""
    root = Path(project_root).expanduser().resolve()
    image_path = Path(path).expanduser().resolve()
    loaded = load_image(image_path, color_mode="grayscale")
    try:
        relative_path = image_path.relative_to(root).as_posix()
    except ValueError:
        relative_path = str(image_path)

    return {
        "image_id": image_id,
        "path": relative_path,
        "modality": modality,
        "modality_class": "monomodal_source",
        "source_name": source_name,
        "shape": list(loaded.array.shape),
        "dtype": str(loaded.array.dtype),
        "sha256": sha256_file(image_path),
        "ground_truth_status": "source_image_only",
        "preprocessing_requirements": [],
    }


def _resolve_record_path(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _validate_unique_ids(records: list[Mapping[str, Any]], id_field: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        value = str(record.get(id_field, "")).strip()
        if not value:
            errors.append(f"Record {index} is missing non-empty '{id_field}'.")
            continue
        if value in seen:
            errors.append(f"Duplicate {id_field}: {value}")
        seen.add(value)


def _validate_image_sources(
    records: list[Mapping[str, Any]],
    project_root: Path,
    errors: list[str],
    warnings: list[str],
    require_files: bool,
) -> None:
    _validate_unique_ids(records, "image_id", errors)
    for record in records:
        image_id = str(record.get("image_id", "<unknown>"))
        path_value = str(record.get("path", "")).strip()
        if not path_value:
            errors.append(f"Image source '{image_id}' is missing path.")
            continue
        image_path = _resolve_record_path(project_root, path_value)
        if not image_path.exists():
            message = f"Image source '{image_id}' is missing file: {image_path}"
            (errors if require_files else warnings).append(message)
            continue
        try:
            loaded = load_image(image_path, color_mode="grayscale")
        except Exception as exc:
            errors.append(f"Image source '{image_id}' could not be loaded: {exc}")
            continue

        expected_shape = record.get("shape")
        if expected_shape is not None and list(loaded.array.shape) != list(expected_shape):
            errors.append(
                f"Image source '{image_id}' shape mismatch: manifest={expected_shape}, "
                f"actual={list(loaded.array.shape)}."
            )
        expected_hash = str(record.get("sha256", "")).strip()
        if expected_hash and sha256_file(image_path) != expected_hash:
            errors.append(f"Image source '{image_id}' SHA-256 mismatch.")


def _validate_rire_pairs(
    records: list[Mapping[str, Any]],
    project_root: Path,
    errors: list[str],
    warnings: list[str],
    require_files: bool,
) -> None:
    _validate_unique_ids(records, "pair_id", errors)
    for record in records:
        pair_id = str(record.get("pair_id", "<unknown>"))
        required_paths = {
            "fixed_header": record.get("fixed_header"),
            "fixed_image": record.get("fixed_image"),
            "moving_header": record.get("moving_header"),
            "moving_image": record.get("moving_image"),
        }
        resolved: dict[str, Path] = {}
        missing = False
        for key, value in required_paths.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(f"RIRE pair '{pair_id}' is missing {key}.")
                missing = True
                continue
            path = _resolve_record_path(project_root, value)
            resolved[key] = path
            if not path.exists():
                message = f"RIRE pair '{pair_id}' is missing {key}: {path}"
                (errors if require_files else warnings).append(message)
                missing = True
        if missing:
            continue

        try:
            fixed_header = parse_rire_header(resolved["fixed_header"])
            moving_header = parse_rire_header(resolved["moving_header"])
            fixed_volume, _ = read_rire_volume(resolved["fixed_header"], resolved["fixed_image"])
            moving_volume, _ = read_rire_volume(resolved["moving_header"], resolved["moving_image"])
        except Exception as exc:
            errors.append(f"RIRE pair '{pair_id}' failed integrity loading: {exc}")
            continue

        expected_fixed_modality = str(record.get("fixed_modality", "")).upper()
        expected_moving_modality = str(record.get("moving_modality", "")).upper()
        if expected_fixed_modality and fixed_header.modality != expected_fixed_modality:
            errors.append(
                f"RIRE pair '{pair_id}' fixed modality mismatch: "
                f"manifest={expected_fixed_modality}, header={fixed_header.modality}."
            )
        if expected_moving_modality and moving_header.modality != expected_moving_modality:
            errors.append(
                f"RIRE pair '{pair_id}' moving modality mismatch: "
                f"manifest={expected_moving_modality}, header={moving_header.modality}."
            )
        if fixed_volume.size == 0 or moving_volume.size == 0:
            errors.append(f"RIRE pair '{pair_id}' contains an empty volume.")



def _metadata_matches(actual: dict[str, Any], expected: Mapping[str, Any]) -> bool:
    """Return True when stored geometry metadata matches current image metadata."""
    exact_fields = ("dimension", "size_xyz", "pixel_type", "components_per_pixel")
    for field in exact_fields:
        if field in expected and actual.get(field) != expected.get(field):
            return False

    numeric_fields = ("spacing_xyz_mm", "origin_xyz_mm", "direction")
    for field in numeric_fields:
        if field not in expected:
            continue
        actual_values = np.asarray(actual.get(field, []), dtype=np.float64)
        expected_values = np.asarray(expected.get(field, []), dtype=np.float64)
        if actual_values.shape != expected_values.shape:
            return False
        if not np.allclose(actual_values, expected_values, rtol=1e-7, atol=1e-7):
            return False
    return True


def _validate_medical_volume_pairs(
    records: list[Mapping[str, Any]],
    project_root: Path,
    errors: list[str],
    warnings: list[str],
    require_files: bool,
) -> None:
    _validate_unique_ids(records, "pair_id", errors)
    for record in records:
        pair_id = str(record.get("pair_id", "<unknown>"))
        required_paths = {
            "fixed_image": record.get("fixed_image"),
            "moving_image": record.get("moving_image"),
        }
        resolved: dict[str, Path] = {}
        missing = False
        for key, value in required_paths.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Medical pair '{pair_id}' is missing {key}.")
                missing = True
                continue
            path = _resolve_record_path(project_root, value)
            resolved[key] = path
            if not path.exists():
                message = f"Medical pair '{pair_id}' is missing {key}: {path}"
                (errors if require_files else warnings).append(message)
                missing = True
        if missing:
            continue

        try:
            fixed_metadata = read_medical_image_metadata(resolved["fixed_image"])
            moving_metadata = read_medical_image_metadata(resolved["moving_image"])
        except Exception as exc:
            errors.append(f"Medical pair '{pair_id}' failed integrity loading: {exc}")
            continue

        if fixed_metadata.dimension != 3 or moving_metadata.dimension != 3:
            errors.append(f"Medical pair '{pair_id}' must contain two 3D volumes.")

        fixed_modality = str(record.get("fixed_modality", "")).strip()
        moving_modality = str(record.get("moving_modality", "")).strip()
        if not fixed_modality:
            errors.append(f"Medical pair '{pair_id}' is missing fixed_modality.")
        if not moving_modality:
            errors.append(f"Medical pair '{pair_id}' is missing moving_modality.")

        expected_fixed = record.get("fixed_metadata")
        if isinstance(expected_fixed, Mapping) and not _metadata_matches(
            fixed_metadata.as_dict(), expected_fixed
        ):
            errors.append(f"Medical pair '{pair_id}' fixed metadata no longer matches the manifest.")

        expected_moving = record.get("moving_metadata")
        if isinstance(expected_moving, Mapping) and not _metadata_matches(
            moving_metadata.as_dict(), expected_moving
        ):
            errors.append(f"Medical pair '{pair_id}' moving metadata no longer matches the manifest.")

        expected_fixed_hash = str(record.get("fixed_sha256", "")).strip()
        if expected_fixed_hash and sha256_file(resolved["fixed_image"]) != expected_fixed_hash:
            errors.append(f"Medical pair '{pair_id}' fixed SHA-256 mismatch.")
        expected_moving_hash = str(record.get("moving_sha256", "")).strip()
        if expected_moving_hash and sha256_file(resolved["moving_image"]) != expected_moving_hash:
            errors.append(f"Medical pair '{pair_id}' moving SHA-256 mismatch.")

def validate_dataset_manifest(
    path: str | Path,
    *,
    project_root: str | Path,
    require_files: bool = True,
) -> DatasetValidationReport:
    """Validate supported dataset-manifest records and referenced files."""
    manifest = load_dataset_manifest(path)
    root = Path(project_root).expanduser().resolve()
    dataset_id = str(manifest.get("dataset_id", "")).strip()
    record_type = str(manifest.get("record_type", "")).strip()
    records = manifest.get("records")

    errors: list[str] = []
    warnings: list[str] = []
    if not dataset_id:
        errors.append("Manifest is missing non-empty dataset_id.")
    if not isinstance(records, list):
        errors.append("Manifest records must be a list.")
        records = []
    mapping_records = [record for record in records if isinstance(record, Mapping)]
    if len(mapping_records) != len(records):
        errors.append("Every manifest record must be a JSON object.")

    if record_type == "image_sources":
        _validate_image_sources(mapping_records, root, errors, warnings, require_files)
    elif record_type == "rire_volume_pairs":
        _validate_rire_pairs(mapping_records, root, errors, warnings, require_files)
    elif record_type == "medical_volume_pairs":
        _validate_medical_volume_pairs(mapping_records, root, errors, warnings, require_files)
    else:
        errors.append(
            "Unsupported manifest record_type. Use image_sources, rire_volume_pairs, "
            "or medical_volume_pairs."
        )

    return DatasetValidationReport(
        dataset_id=dataset_id or "<missing>",
        checked_records=len(mapping_records),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
