from pathlib import Path

import numpy as np
import pytest

from image_registration.rire import (
    find_rire_volume_files,
    parse_rire_header,
    read_rire_volume,
)


def _write_rire_fixture(root: Path, *, modality: str = "CT") -> tuple[Path, Path, np.ndarray]:
    root.mkdir(parents=True, exist_ok=True)
    header = root / "header.ascii"
    image = root / "image.bin"
    header.write_text(
        "\n".join(
            [
                f"Modality := {modality}",
                "Slice thickness := 2.500000",
                "Patient Orientation := L : P : H",
                "Rows := 2",
                "Columns := 3",
                "Slices := 2",
                "Pixel size := 1.250000 : 1.500000",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    expected = np.array(
        [
            [[1, 2, 3], [4, 5, 6]],
            [[7, 8, 9], [10, 11, 12]],
        ],
        dtype=np.int16,
    )
    expected.astype(">i2").tofile(image)
    return header, image, expected


def test_parse_rire_header_extracts_geometry(tmp_path: Path) -> None:
    header_path, _, _ = _write_rire_fixture(tmp_path)
    header = parse_rire_header(header_path)
    assert header.modality == "CT"
    assert header.shape_zyx == (2, 2, 3)
    assert header.spacing_xyz == (1.25, 1.5, 2.5)
    assert header.patient_orientation == ("L", "P", "H")


def test_read_rire_volume_uses_big_endian_signed_int16(tmp_path: Path) -> None:
    header_path, image_path, expected = _write_rire_fixture(tmp_path)
    volume, header = read_rire_volume(header_path, image_path)
    assert header.modality == "CT"
    assert volume.dtype == np.int16
    assert np.array_equal(volume, expected)


def test_read_rire_volume_rejects_wrong_voxel_count(tmp_path: Path) -> None:
    header_path, image_path, _ = _write_rire_fixture(tmp_path)
    image_path.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="voxel count"):
        read_rire_volume(header_path, image_path)


def test_parse_rire_header_requires_pixel_size(tmp_path: Path) -> None:
    header_path = tmp_path / "header.ascii"
    header_path.write_text(
        "Modality := CT\nRows := 2\nColumns := 2\nSlices := 2\n"
        "Slice thickness := 1.0\nPatient Orientation := L : P : H\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="pixel size"):
        parse_rire_header(header_path)


def test_find_rire_volume_files_locates_nested_files(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "volume"
    header_path, image_path, _ = _write_rire_fixture(nested)
    found_header, found_image = find_rire_volume_files(tmp_path)
    assert found_header == header_path
    assert found_image == image_path


def test_find_rire_volume_files_rejects_missing_files(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="exactly one"):
        find_rire_volume_files(tmp_path)
