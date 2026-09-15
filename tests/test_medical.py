from pathlib import Path

import pytest

from image_registration.datasets import validate_dataset_manifest, write_dataset_manifest
from image_registration.medical import read_medical_image_metadata


def _write_mha(path: Path, *, size: tuple[int, int, int], spacing: tuple[float, float, float]) -> None:
    sitk = pytest.importorskip("SimpleITK")
    path.parent.mkdir(parents=True, exist_ok=True)
    image = sitk.Image(size[0], size[1], size[2], sitk.sitkInt16)
    image.SetSpacing(spacing)
    image.SetOrigin((1.0, 2.0, 3.0))
    image.SetDirection((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    sitk.WriteImage(image, str(path))


def test_read_medical_image_metadata_preserves_geometry(tmp_path: Path) -> None:
    path = tmp_path / "volume.mha"
    _write_mha(path, size=(4, 5, 6), spacing=(0.8, 0.9, 2.5))
    metadata = read_medical_image_metadata(path)
    assert metadata.dimension == 3
    assert metadata.size_xyz == (4, 5, 6)
    assert metadata.spacing_xyz_mm == pytest.approx((0.8, 0.9, 2.5))
    assert metadata.origin_xyz_mm == pytest.approx((1.0, 2.0, 3.0))
    assert len(metadata.direction) == 9


def test_medical_volume_pair_manifest_validates_different_geometries(tmp_path: Path) -> None:
    fixed = tmp_path / "ct.mha"
    moving = tmp_path / "mr.mha"
    _write_mha(fixed, size=(4, 5, 6), spacing=(1.0, 1.0, 2.0))
    _write_mha(moving, size=(6, 7, 5), spacing=(0.8, 0.8, 3.0))

    fixed_metadata = read_medical_image_metadata(fixed)
    moving_metadata = read_medical_image_metadata(moving)
    manifest_path = write_dataset_manifest(
        {
            "schema_version": 2,
            "dataset_id": "medical_test",
            "record_type": "medical_volume_pairs",
            "records": [
                {
                    "pair_id": "mr_to_ct",
                    "fixed_image": "ct.mha",
                    "moving_image": "mr.mha",
                    "fixed_modality": "CT",
                    "moving_modality": "MR-T1",
                    "fixed_metadata": fixed_metadata.as_dict(),
                    "moving_metadata": moving_metadata.as_dict(),
                }
            ],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert report.ok
    assert report.checked_records == 1


def test_medical_volume_pair_metadata_change_is_reported(tmp_path: Path) -> None:
    fixed = tmp_path / "ct.mha"
    moving = tmp_path / "mr.mha"
    _write_mha(fixed, size=(4, 5, 6), spacing=(1.0, 1.0, 2.0))
    _write_mha(moving, size=(4, 5, 6), spacing=(1.0, 1.0, 2.0))

    fixed_metadata = read_medical_image_metadata(fixed).as_dict()
    moving_metadata = read_medical_image_metadata(moving).as_dict()
    fixed_metadata["spacing_xyz_mm"] = [9.0, 9.0, 9.0]

    manifest_path = write_dataset_manifest(
        {
            "schema_version": 2,
            "dataset_id": "medical_test",
            "record_type": "medical_volume_pairs",
            "records": [
                {
                    "pair_id": "mr_to_ct",
                    "fixed_image": "ct.mha",
                    "moving_image": "mr.mha",
                    "fixed_modality": "CT",
                    "moving_modality": "MR-T1",
                    "fixed_metadata": fixed_metadata,
                    "moving_metadata": moving_metadata,
                }
            ],
        },
        tmp_path / "manifest.json",
    )
    report = validate_dataset_manifest(manifest_path, project_root=tmp_path)
    assert not report.ok
    assert any("fixed metadata" in error for error in report.errors)
