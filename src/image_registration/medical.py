"""Medical-image metadata utilities used by dataset validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MedicalImageMetadata:
    """Geometry and pixel metadata for one medical image volume."""

    dimension: int
    size_xyz: tuple[int, ...]
    spacing_xyz_mm: tuple[float, ...]
    origin_xyz_mm: tuple[float, ...]
    direction: tuple[float, ...]
    pixel_type: str
    components_per_pixel: int

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly metadata."""
        return {
            "dimension": self.dimension,
            "size_xyz": list(self.size_xyz),
            "spacing_xyz_mm": list(self.spacing_xyz_mm),
            "origin_xyz_mm": list(self.origin_xyz_mm),
            "direction": list(self.direction),
            "pixel_type": self.pixel_type,
            "components_per_pixel": self.components_per_pixel,
        }


def read_medical_image_metadata(path: str | Path) -> MedicalImageMetadata:
    """Read medical-image geometry and pixel metadata with SimpleITK."""
    image_path = Path(path).expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Medical image does not exist: {image_path}")
    if not image_path.is_file():
        raise ValueError(f"Medical image path is not a file: {image_path}")

    try:
        import SimpleITK as sitk
    except ImportError as exc:
        raise RuntimeError(
            "SimpleITK is required to validate medical image volumes. "
            "Install the project requirements first."
        ) from exc

    image = sitk.ReadImage(str(image_path))
    dimension = int(image.GetDimension())
    size = tuple(int(value) for value in image.GetSize())
    spacing = tuple(float(value) for value in image.GetSpacing())
    origin = tuple(float(value) for value in image.GetOrigin())
    direction = tuple(float(value) for value in image.GetDirection())
    components = int(image.GetNumberOfComponentsPerPixel())

    if dimension <= 0 or len(size) != dimension:
        raise ValueError(f"Invalid medical-image dimensionality for {image_path}.")
    if any(value <= 0 for value in size):
        raise ValueError(f"Medical image contains a non-positive size: {size}.")
    if any(value <= 0.0 for value in spacing):
        raise ValueError(f"Medical image contains a non-positive spacing: {spacing}.")

    return MedicalImageMetadata(
        dimension=dimension,
        size_xyz=size,
        spacing_xyz_mm=spacing,
        origin_xyz_mm=origin,
        direction=direction,
        pixel_type=image.GetPixelIDTypeAsString(),
        components_per_pixel=components,
    )
