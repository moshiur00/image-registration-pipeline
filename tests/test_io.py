from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from image_registration.io import load_image, validate_image_pair


def test_load_grayscale_raster(tmp_path: Path) -> None:
    image = np.arange(100, dtype=np.uint8).reshape(10, 10)
    path = tmp_path / "gray.png"
    assert cv2.imwrite(str(path), image)

    loaded = load_image(path, color_mode="grayscale")
    assert loaded.backend == "opencv"
    assert loaded.axis_order == "y_x"
    assert loaded.array.shape == (10, 10)
    assert loaded.array.dtype == np.uint8
    assert np.array_equal(loaded.array, image)
    assert loaded.spacing is None


def test_load_color_raster_converts_bgr_to_rgb(tmp_path: Path) -> None:
    bgr = np.zeros((3, 4, 3), dtype=np.uint8)
    bgr[:, :] = [0, 0, 255]
    path = tmp_path / "red.png"
    assert cv2.imwrite(str(path), bgr)

    loaded = load_image(path, color_mode="rgb")
    assert loaded.array.shape == (3, 4, 3)
    assert np.array_equal(loaded.array[0, 0], [255, 0, 0])
    assert loaded.axis_order == "y_x_channel"


def test_load_medical_image_preserves_geometry(tmp_path: Path) -> None:
    sitk = pytest.importorskip("SimpleITK")
    array = np.arange(60, dtype=np.float32).reshape(5, 12)
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((0.7, 1.3))
    image.SetOrigin((12.0, -5.0))
    image.SetDirection((1.0, 0.0, 0.0, 1.0))
    path = tmp_path / "image.mha"
    sitk.WriteImage(image, str(path))

    loaded = load_image(path)
    assert loaded.backend == "simpleitk"
    assert loaded.axis_order == "y_x"
    assert np.allclose(loaded.array, array)
    assert loaded.spacing == pytest.approx((0.7, 1.3))
    assert loaded.origin == pytest.approx((12.0, -5.0))
    assert loaded.direction == pytest.approx((1.0, 0.0, 0.0, 1.0))


def test_load_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_image(tmp_path / "missing.png")


def test_validate_image_pair_rejects_shape_mismatch(tmp_path: Path) -> None:
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.zeros((11, 10), dtype=np.uint8)
    path_a = tmp_path / "a.png"
    path_b = tmp_path / "b.png"
    assert cv2.imwrite(str(path_a), a)
    assert cv2.imwrite(str(path_b), b)

    fixed = load_image(path_a, color_mode="grayscale")
    moving = load_image(path_b, color_mode="grayscale")
    with pytest.raises(ValueError, match="shape mismatch"):
        validate_image_pair(fixed, moving)
