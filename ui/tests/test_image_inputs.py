from __future__ import annotations

import cv2
import numpy as np
import pytest

from ui.core import ImageSource, PreprocessingSpec, SourceType
from ui.core.image_inputs import apply_preprocessing, decode_image_source


def test_uploaded_png_decodes_without_writing_file() -> None:
    source_array = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64)
    ok, encoded = cv2.imencode(".png", source_array)
    assert ok
    source = ImageSource(SourceType.UPLOADED_BYTES, "upload.png", content_bytes=encoded.tobytes())
    decoded, metadata = decode_image_source(source, name="Fixed")
    assert np.array_equal(decoded, source_array)
    assert metadata["shape"] == [64, 64]


def test_constant_upload_is_rejected_by_method_backend_not_hidden_preprocessing() -> None:
    array = np.ones((32, 32), dtype=np.uint8)
    prepared, report = apply_preprocessing(array, PreprocessingSpec(), name="Fixed")
    assert prepared.shape == (32, 32)
    assert report["normalization"] is None


def test_unknown_normalization_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported UI normalization"):
        apply_preprocessing(
            np.arange(64, dtype=np.float32).reshape(8, 8),
            PreprocessingSpec(normalization="mystery"),
            name="Fixed",
        )
