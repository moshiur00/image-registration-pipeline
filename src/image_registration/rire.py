"""Utilities for reading the original RIRE raw volume format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class RireHeader:
    """Parsed metadata required to interpret one RIRE volume."""

    modality: str
    rows: int
    columns: int
    slices: int
    pixel_size_xy: tuple[float, float]
    slice_thickness: float
    patient_orientation: tuple[str, str, str]
    raw_fields: dict[str, str]

    @property
    def shape_zyx(self) -> tuple[int, int, int]:
        """Return NumPy volume shape as slices, rows, columns."""
        return self.slices, self.rows, self.columns

    @property
    def spacing_xyz(self) -> tuple[float, float, float]:
        """Return voxel spacing in x, y, z order in millimeters."""
        return self.pixel_size_xy[0], self.pixel_size_xy[1], self.slice_thickness

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly metadata."""
        return {
            "modality": self.modality,
            "shape_zyx": list(self.shape_zyx),
            "spacing_xyz_mm": list(self.spacing_xyz),
            "patient_orientation": list(self.patient_orientation),
        }


def _parse_field_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":=" not in line:
            continue
        key, value = line.split(":=", 1)
        normalized_key = " ".join(key.strip().split()).lower()
        fields[normalized_key] = value.strip()
    return fields


def _required_field(fields: dict[str, str], name: str) -> str:
    key = name.lower()
    if key not in fields or not fields[key].strip():
        raise ValueError(f"RIRE header is missing required field: {name}")
    return fields[key].strip()


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"RIRE header field '{name}' must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"RIRE header field '{name}' must be positive.")
    return parsed


def _parse_positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"RIRE header field '{name}' must be numeric.") from exc
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"RIRE header field '{name}' must be a positive finite number.")
    return parsed


def parse_rire_header(path: str | Path) -> RireHeader:
    """Parse a RIRE ``header.ascii`` file."""
    header_path = Path(path).expanduser().resolve()
    if not header_path.exists():
        raise FileNotFoundError(f"RIRE header does not exist: {header_path}")
    if not header_path.is_file():
        raise ValueError(f"RIRE header path is not a file: {header_path}")

    fields = _parse_field_lines(header_path.read_text(encoding="ascii", errors="strict"))
    modality = _required_field(fields, "modality").upper()
    rows = _parse_positive_int(_required_field(fields, "rows"), "rows")
    columns = _parse_positive_int(_required_field(fields, "columns"), "columns")
    slices = _parse_positive_int(_required_field(fields, "slices"), "slices")
    slice_thickness = _parse_positive_float(
        _required_field(fields, "slice thickness"), "slice thickness"
    )

    pixel_parts = [part.strip() for part in _required_field(fields, "pixel size").split(":")]
    if len(pixel_parts) != 2:
        raise ValueError("RIRE header field 'pixel size' must contain two values separated by ':'.")
    pixel_size_xy = (
        _parse_positive_float(pixel_parts[0], "pixel size x"),
        _parse_positive_float(pixel_parts[1], "pixel size y"),
    )

    orientation_parts = [
        part.strip().upper() for part in _required_field(fields, "patient orientation").split(":")
    ]
    if len(orientation_parts) != 3 or any(len(part) != 1 for part in orientation_parts):
        raise ValueError("RIRE patient orientation must contain three one-letter directions.")

    return RireHeader(
        modality=modality,
        rows=rows,
        columns=columns,
        slices=slices,
        pixel_size_xy=pixel_size_xy,
        slice_thickness=slice_thickness,
        patient_orientation=(orientation_parts[0], orientation_parts[1], orientation_parts[2]),
        raw_fields=fields,
    )


def read_rire_volume(
    header_path: str | Path,
    image_path: str | Path,
) -> tuple[NDArray[np.int16], RireHeader]:
    """Read a RIRE big-endian signed 16-bit volume as a native NumPy array."""
    header = parse_rire_header(header_path)
    binary_path = Path(image_path).expanduser().resolve()
    if not binary_path.exists():
        raise FileNotFoundError(f"RIRE image file does not exist: {binary_path}")
    if not binary_path.is_file():
        raise ValueError(f"RIRE image path is not a file: {binary_path}")

    expected_count = int(np.prod(header.shape_zyx))
    raw = np.fromfile(binary_path, dtype=">i2")
    if raw.size != expected_count:
        raise ValueError(
            "RIRE voxel count does not match header dimensions: "
            f"expected {expected_count}, found {raw.size}."
        )

    volume = raw.reshape(header.shape_zyx).astype(np.int16, copy=False)
    return volume, header


def find_rire_volume_files(root: str | Path) -> tuple[Path, Path]:
    """Find exactly one ``header.ascii`` and ``image.bin`` below a modality directory."""
    directory = Path(root).expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(f"RIRE modality directory does not exist: {directory}")

    headers = sorted(directory.rglob("header.ascii"))
    images = sorted(directory.rglob("image.bin"))
    if len(headers) != 1 or len(images) != 1:
        raise ValueError(
            "Expected exactly one RIRE header.ascii and one image.bin below "
            f"{directory}; found {len(headers)} header(s) and {len(images)} image file(s)."
        )
    return headers[0], images[0]
