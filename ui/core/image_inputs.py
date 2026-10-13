"""Input decoding and explicit preprocessing for the UI service layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from image_registration.io import load_image
from image_registration.preprocessing import (
    clip_percentiles,
    gaussian_smooth,
    robust_normalize,
    to_grayscale,
)

from .contracts import ImageSource, PreprocessingSpec

Array = NDArray[np.generic]

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_RASTER_PIXELS = 16_000_000


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """Decoded and explicitly preprocessed image plus a JSON-friendly report."""

    array: NDArray[np.float32]
    source_metadata: dict[str, Any]
    preprocessing_report: dict[str, Any]


def _validate_numeric_array(array: Array, *, name: str) -> Array:
    values = np.asarray(array)
    if values.size == 0:
        raise ValueError(f"{name} image must be non-empty.")
    if values.ndim not in {2, 3}:
        raise ValueError(f"{name} image must be 2D grayscale or 2D color before preprocessing.")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError(f"{name} image must contain numeric values.")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} image must contain only finite values.")
    height, width = int(values.shape[0]), int(values.shape[1])
    if height * width > MAX_RASTER_PIXELS:
        raise ValueError(f"{name} image exceeds the UI v0.1 pixel limit.")
    return values


def _decode_uploaded_raster(data: bytes, *, name: str) -> Array:
    if not data:
        raise ValueError(f"{name} upload is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{name} upload exceeds the UI v0.1 size limit.")
    encoded = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise ValueError(f"Could not decode {name} upload as PNG, JPEG, BMP, or TIFF.")
    if decoded.ndim == 3 and decoded.shape[2] == 3:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    elif decoded.ndim == 3 and decoded.shape[2] == 4:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGBA)
    return _validate_numeric_array(decoded, name=name)


def decode_image_source(source: ImageSource, *, name: str) -> tuple[Array, dict[str, Any]]:
    """Decode one UI source without writing it into tracked project directories."""
    if source.array is not None:
        array = _validate_numeric_array(np.asarray(source.array), name=name)
        metadata = dict(source.metadata)
        metadata.setdefault("shape", list(array.shape))
        metadata.setdefault("dtype", str(array.dtype))
        metadata.setdefault("source_type", source.source_type.value)
        return array.copy(), metadata

    if source.content_bytes is not None:
        array = _decode_uploaded_raster(source.content_bytes, name=name)
        metadata = dict(source.metadata)
        metadata.update(
            {
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "source_type": source.source_type.value,
            }
        )
        return array, metadata

    if source.path is not None:
        loaded = load_image(Path(source.path), color_mode="unchanged")
        array = _validate_numeric_array(loaded.array, name=name)
        metadata = loaded.metadata_dict()
        metadata.update(source.metadata)
        metadata["source_type"] = source.source_type.value
        return array, metadata

    raise ValueError(f"{name} source does not contain an array, bytes, or path.")


def apply_preprocessing(
    image: Array,
    spec: PreprocessingSpec,
    *,
    name: str,
) -> tuple[NDArray[np.float32], dict[str, Any]]:
    """Apply only preprocessing explicitly present in the request contract."""
    values = _validate_numeric_array(image, name=name)
    report: dict[str, Any] = {
        "input_shape": list(values.shape),
        "input_dtype": str(values.dtype),
        "grayscale": bool(spec.grayscale),
        "clipping_percentiles": list(spec.clipping_percentiles)
        if spec.clipping_percentiles is not None
        else None,
        "normalization": spec.normalization,
        "gaussian_sigma": spec.gaussian_sigma,
        "resize_policy": spec.resize_policy,
    }

    if spec.grayscale:
        values = to_grayscale(values)
    elif values.ndim != 2:
        raise ValueError("Registration UI v0.1 requires grayscale output for 2D methods.")

    if spec.clipping_percentiles is not None:
        low, high = spec.clipping_percentiles
        values = clip_percentiles(values, lower=float(low), upper=float(high))

    normalization = (spec.normalization or "none").lower()
    if normalization in {"none", "off"}:
        values = np.asarray(values, dtype=np.float32)
    elif normalization in {"robust", "robust_percentile", "robust_0_1"}:
        low, high = spec.clipping_percentiles or (1.0, 99.0)
        values = robust_normalize(values, lower=float(low), upper=float(high)).astype(np.float32)
    else:
        raise ValueError(f"Unsupported UI normalization mode: {spec.normalization}")

    sigma = 0.0 if spec.gaussian_sigma is None else float(spec.gaussian_sigma)
    if sigma > 0.0:
        values = gaussian_smooth(values, sigma=sigma).astype(np.float32)

    if spec.resize_policy != "none":
        raise ValueError("UI v0.1 does not silently resize images.")

    values = np.asarray(values, dtype=np.float32)
    report.update(
        {
            "output_shape": list(values.shape),
            "output_dtype": str(values.dtype),
            "output_min": float(np.min(values)),
            "output_max": float(np.max(values)),
        }
    )
    return values, report


def prepare_image_source(
    source: ImageSource,
    spec: PreprocessingSpec,
    *,
    name: str,
) -> PreparedImage:
    array, source_metadata = decode_image_source(source, name=name)
    prepared, preprocessing_report = apply_preprocessing(array, spec, name=name)
    return PreparedImage(
        array=prepared,
        source_metadata=source_metadata,
        preprocessing_report=preprocessing_report,
    )
