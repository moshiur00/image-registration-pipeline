from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from image_registration.config import build_transform, config_hash, load_config, with_defaults
from image_registration.transforms import apply_transform


def minimal_config() -> dict:
    return {
        "experiment": {"name": "test"},
        "data": {"fixed": "fixed.png", "moving": "moving.png"},
        "preprocessing": {},
        "transform": {"type": "translation", "parameters": {"tx": 3.0, "ty": -2.0}},
        "warp": {},
        "output": {"root": "outputs"},
    }


def test_load_config_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(minimal_config()), encoding="utf-8")
    loaded = load_config(path)
    assert loaded["experiment"]["name"] == "test"


def test_with_defaults_fills_runner_defaults() -> None:
    config = with_defaults(minimal_config())
    assert config["experiment"]["seed"] == 42
    assert config["data"]["color_mode"] == "grayscale"
    assert config["warp"]["interpolation"] == "linear"
    assert config["output"]["overwrite"] is False


def test_config_hash_is_order_independent() -> None:
    a = {"a": 1, "b": {"x": 2, "y": 3}}
    b = {"b": {"y": 3, "x": 2}, "a": 1}
    assert config_hash(a) == config_hash(b)


def test_build_translation_transform() -> None:
    matrix = build_transform(
        {"type": "translation", "parameters": {"tx": 5.0, "ty": -4.0}}
    )
    point = apply_transform([10.0, 20.0], matrix)
    np.testing.assert_allclose(point, [15.0, 16.0])


def test_build_similarity_transform() -> None:
    matrix = build_transform(
        {
            "type": "similarity",
            "parameters": {
                "scale": 1.0,
                "angle_degrees": 0.0,
                "tx": 2.0,
                "ty": 3.0,
                "center": [5.0, 5.0],
            },
        }
    )
    point = apply_transform([1.0, 1.0], matrix)
    np.testing.assert_allclose(point, [3.0, 4.0])


def test_build_affine_requires_linear_component() -> None:
    with pytest.raises(ValueError, match="linear"):
        build_transform({"type": "affine", "parameters": {}})
