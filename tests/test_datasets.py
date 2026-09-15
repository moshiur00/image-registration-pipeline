import json
from pathlib import Path

import cv2
import numpy as np

from image_registration.datasets import (
    build_raster_source_record,
    validate_dataset_manifest,
    write_dataset_manifest,
)


def _write_image(path: Path, value: int = 100) -> None:
    array = np.full((20, 30), value, dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), array)


def _write_rire_fixture(root: Path, modality: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    header = root / "header.ascii"
    image = root / "image.bin"
    header.write_text(
        "\n".join(
            [
                f"Modality := {modality}",
                "Slice thickness := 2.0",
                "Patient Orientation := L : P : H",
                "Rows := 2",
                "Columns := 2",
                "Slices := 2",
                "Pixel size := 1.0 : 1.0",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    np.arange(8, dtype=np.int16).astype(">i2").tofile(image)
    return header, image


def test_raster_source_manifest_validates(tmp_path: Path) -> None:
    image_path = tmp_path / "data" / "sample.png"
    _write_image(image_path)
    record = build_raster_source_record(
        "sample",
        image_path,
        project_root=tmp_path,
        modality="visible",
        source_name="test",
    )
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "test_sources",
            "record_type": "image_sources",
            "records": [record],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert report.ok
    assert report.checked_records == 1


def test_duplicate_image_ids_are_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    _write_image(image_path)
    record = build_raster_source_record(
        "duplicate",
        image_path,
        project_root=tmp_path,
        source_name="test",
    )
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "duplicates",
            "record_type": "image_sources",
            "records": [record, record],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("Duplicate image_id" in error for error in report.errors)


def test_missing_raster_file_is_reported(tmp_path: Path) -> None:
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "missing",
            "record_type": "image_sources",
            "records": [
                {
                    "image_id": "missing",
                    "path": "does_not_exist.png",
                }
            ],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("missing file" in error for error in report.errors)


def test_shape_mismatch_is_reported(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    _write_image(image_path)
    record = build_raster_source_record(
        "sample",
        image_path,
        project_root=tmp_path,
        source_name="test",
    )
    record["shape"] = [999, 999]
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "shape_mismatch",
            "record_type": "image_sources",
            "records": [record],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("shape mismatch" in error for error in report.errors)


def test_hash_mismatch_is_reported(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    _write_image(image_path)
    record = build_raster_source_record(
        "sample",
        image_path,
        project_root=tmp_path,
        source_name="test",
    )
    record["sha256"] = "0" * 64
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "hash_mismatch",
            "record_type": "image_sources",
            "records": [record],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("SHA-256 mismatch" in error for error in report.errors)


def test_rire_pair_manifest_validates_without_same_shape_requirement(tmp_path: Path) -> None:
    fixed_header, fixed_image = _write_rire_fixture(tmp_path / "mr", "MR")
    moving_header, moving_image = _write_rire_fixture(tmp_path / "ct", "CT")
    manifest = {
        "dataset_id": "rire_test",
        "record_type": "rire_volume_pairs",
        "records": [
            {
                "pair_id": "pair_001",
                "fixed_header": str(fixed_header.relative_to(tmp_path)),
                "fixed_image": str(fixed_image.relative_to(tmp_path)),
                "moving_header": str(moving_header.relative_to(tmp_path)),
                "moving_image": str(moving_image.relative_to(tmp_path)),
                "fixed_modality": "MR",
                "moving_modality": "CT",
            }
        ],
    }
    manifest_path = write_dataset_manifest(manifest, tmp_path / "manifest.json")
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert report.ok


def test_rire_modality_mismatch_is_reported(tmp_path: Path) -> None:
    fixed_header, fixed_image = _write_rire_fixture(tmp_path / "mr", "MR")
    moving_header, moving_image = _write_rire_fixture(tmp_path / "ct", "CT")
    manifest_path = write_dataset_manifest(
        {
            "dataset_id": "rire_test",
            "record_type": "rire_volume_pairs",
            "records": [
                {
                    "pair_id": "pair_001",
                    "fixed_header": str(fixed_header.relative_to(tmp_path)),
                    "fixed_image": str(fixed_image.relative_to(tmp_path)),
                    "moving_header": str(moving_header.relative_to(tmp_path)),
                    "moving_image": str(moving_image.relative_to(tmp_path)),
                    "fixed_modality": "CT",
                    "moving_modality": "MR",
                }
            ],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("modality mismatch" in error for error in report.errors)


def test_manifest_writer_uses_stable_sorted_json(tmp_path: Path) -> None:
    path = write_dataset_manifest(
        {"record_type": "image_sources", "records": [], "dataset_id": "stable"},
        tmp_path / "manifest.json",
    )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["dataset_id"] == "stable"


def test_missing_medical_pair_file_is_reported(tmp_path: Path) -> None:
    manifest_path = write_dataset_manifest(
        {
            "schema_version": 2,
            "dataset_id": "medical_missing",
            "record_type": "medical_volume_pairs",
            "records": [
                {
                    "pair_id": "pair_001",
                    "fixed_image": "missing_ct.mha",
                    "moving_image": "missing_mr.mha",
                    "fixed_modality": "CT",
                    "moving_modality": "MR-T1",
                }
            ],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("missing fixed_image" in error for error in report.errors)
    assert any("missing moving_image" in error for error in report.errors)
