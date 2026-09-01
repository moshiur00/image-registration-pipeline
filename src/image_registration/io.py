"""Image loading and basic input validation utilities.

The project uses a small wrapper around raster and medical-image readers so
later registration methods receive image arrays together with useful metadata.
Raster color images are converted from OpenCV BGR ordering to RGB ordering at
the project boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
try:
    import SimpleITK as sitk
except ModuleNotFoundError:  # pragma: no cover - exercised only without optional runtime dependency
    sitk = None
from numpy.typing import NDArray

ColorMode = Literal["unchanged", "grayscale", "rgb"]

_RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
_MEDICAL_SUFFIXES = {".mha", ".mhd", ".nii", ".nii.gz", ".nrrd"}


@dataclass(frozen=True)
class LoadedImage:
    """Image array plus source and geometry metadata.

    Notes
    -----
    Raster files normally do not contain reliable physical geometry metadata,
    so ``spacing``, ``origin``, and ``direction`` are stored as ``None``.
    Medical formats read through SimpleITK preserve those values.
    """

    array: NDArray[np.generic]
    path: Path
    backend: str
    axis_order: str
    spacing: tuple[float, ...] | None = None
    origin: tuple[float, ...] | None = None
    direction: tuple[float, ...] | None = None

    def metadata_dict(self) -> dict[str, Any]:
        """Return JSON-friendly metadata describing the loaded image."""
        channels = int(self.array.shape[-1]) if self.axis_order == "y_x_channel" else 1
        return {
            "path": str(self.path),
            "backend": self.backend,
            "shape": list(self.array.shape),
            "dtype": str(self.array.dtype),
            "channels": channels,
            "axis_order": self.axis_order,
            "spacing": list(self.spacing) if self.spacing is not None else None,
            "origin": list(self.origin) if self.origin is not None else None,
            "direction": list(self.direction) if self.direction is not None else None,
        }


def _normalized_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower()


def _convert_raster_color(array: NDArray[np.generic], color_mode: ColorMode) -> NDArray[np.generic]:
    if color_mode not in {"unchanged", "grayscale", "rgb"}:
        raise ValueError("color_mode must be one of: unchanged, grayscale, rgb.")

    if array.ndim == 2:
        if color_mode == "rgb":
            return cv2.cvtColor(array, cv2.COLOR_GRAY2RGB)
        return array

    if array.ndim != 3 or array.shape[2] not in {3, 4}:
        raise ValueError(f"Unsupported raster array shape: {array.shape}.")

    if array.shape[2] == 3:
        rgb = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
    else:
        rgb = cv2.cvtColor(array, cv2.COLOR_BGRA2RGBA)

    if color_mode == "unchanged":
        return rgb
    if color_mode == "grayscale":
        code = cv2.COLOR_RGB2GRAY if rgb.shape[2] == 3 else cv2.COLOR_RGBA2GRAY
        return cv2.cvtColor(rgb, code)
    if rgb.shape[2] == 4:
        return cv2.cvtColor(rgb, cv2.COLOR_RGBA2RGB)
    return rgb


def _load_raster(path: Path, color_mode: ColorMode) -> LoadedImage:
    array = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if array is None:
        raise ValueError(f"Could not decode raster image: {path}")

    converted = _convert_raster_color(array, color_mode)
    axis_order = "y_x" if converted.ndim == 2 else "y_x_channel"
    return LoadedImage(
        array=converted,
        path=path,
        backend="opencv",
        axis_order=axis_order,
    )


def _load_medical(path: Path, color_mode: ColorMode) -> LoadedImage:
    if sitk is None:
        raise ImportError("SimpleITK is required to load medical-image formats.")
    image = sitk.ReadImage(str(path))
    array = sitk.GetArrayFromImage(image)

    if color_mode == "rgb":
        raise ValueError("rgb color_mode is not supported for medical-image loading.")

    if color_mode == "grayscale" and array.ndim not in {2, 3}:
        raise ValueError("Expected a scalar medical image for grayscale loading.")

    if image.GetDimension() == 2:
        axis_order = "y_x"
    elif image.GetDimension() == 3:
        axis_order = "z_y_x"
    else:
        axis_order = "numpy_reverse_of_physical_axes"

    return LoadedImage(
        array=array,
        path=path,
        backend="simpleitk",
        axis_order=axis_order,
        spacing=tuple(float(v) for v in image.GetSpacing()),
        origin=tuple(float(v) for v in image.GetOrigin()),
        direction=tuple(float(v) for v in image.GetDirection()),
    )


def load_image(path: str | Path, color_mode: ColorMode = "unchanged") -> LoadedImage:
    """Load a supported raster or medical image with metadata.

    Supported raster formats include PNG, JPEG, BMP, TIFF, and TIF. Supported
    medical formats include MHA, MHD, NIfTI, and NRRD.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Image file does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Image path is not a file: {resolved}")

    suffix = _normalized_suffix(resolved)
    if suffix in _RASTER_SUFFIXES:
        return _load_raster(resolved, color_mode)
    if suffix in _MEDICAL_SUFFIXES:
        return _load_medical(resolved, color_mode)

    supported = sorted(_RASTER_SUFFIXES | _MEDICAL_SUFFIXES)
    raise ValueError(f"Unsupported image format '{suffix}'. Supported: {', '.join(supported)}")


def validate_image_pair(
    fixed: LoadedImage,
    moving: LoadedImage,
    *,
    require_same_shape: bool = True,
    require_same_ndim: bool = True,
) -> None:
    """Validate basic fixed/moving compatibility before processing."""
    if fixed.array.size == 0 or moving.array.size == 0:
        raise ValueError("Fixed and moving images must be non-empty.")
    if require_same_ndim and fixed.array.ndim != moving.array.ndim:
        raise ValueError(
            f"Image dimensionality mismatch: fixed ndim={fixed.array.ndim}, "
            f"moving ndim={moving.array.ndim}."
        )
    if require_same_shape and fixed.array.shape != moving.array.shape:
        raise ValueError(
            f"Image shape mismatch: fixed={fixed.array.shape}, moving={moving.array.shape}."
        )
