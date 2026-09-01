"""Configuration loading and transform construction utilities."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

from .transforms import (
    affine_matrix,
    identity_matrix,
    rigid_matrix,
    similarity_matrix,
    translation_matrix,
)


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file and return a mutable dictionary."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {config_path}")
    if not config_path.is_file():
        raise ValueError(f"Configuration path is not a file: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)

    if not isinstance(loaded, dict):
        raise ValueError("Configuration root must be a YAML mapping.")
    return loaded


def validate_experiment_config(config: Mapping[str, Any]) -> None:
    """Validate the minimum fields required by the experiment runner."""
    required_sections = {"experiment", "data", "preprocessing", "transform", "warp", "output"}
    missing = sorted(required_sections.difference(config))
    if missing:
        raise ValueError(f"Missing configuration sections: {', '.join(missing)}")

    experiment = config["experiment"]
    if not isinstance(experiment, Mapping) or not str(experiment.get("name", "")).strip():
        raise ValueError("experiment.name must be a non-empty string.")

    data = config["data"]
    if not isinstance(data, Mapping):
        raise ValueError("data must be a mapping.")
    for key in ("fixed", "moving"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"data.{key} must be a non-empty path.")

    transform = config["transform"]
    if not isinstance(transform, Mapping) or not str(transform.get("type", "")).strip():
        raise ValueError("transform.type must be provided.")

    warp = config["warp"]
    if not isinstance(warp, Mapping):
        raise ValueError("warp must be a mapping.")
    interpolation = str(warp.get("interpolation", "linear"))
    if interpolation not in {"nearest", "linear", "cubic"}:
        raise ValueError("warp.interpolation must be nearest, linear, or cubic.")

    output = config["output"]
    if not isinstance(output, Mapping) or not str(output.get("root", "")).strip():
        raise ValueError("output.root must be a non-empty path.")


def with_defaults(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of the configuration with runner defaults filled in."""
    resolved = deepcopy(dict(config))
    validate_experiment_config(resolved)

    resolved["experiment"].setdefault("seed", 42)
    resolved["data"].setdefault("color_mode", "grayscale")
    resolved["data"].setdefault("require_same_shape", True)
    resolved["data"].setdefault("require_same_ndim", True)
    resolved["warp"].setdefault("interpolation", "linear")
    resolved["warp"].setdefault("border_value", 0.0)
    resolved.setdefault("evaluation", {})
    resolved["evaluation"].setdefault("enabled", True)
    resolved.setdefault("visualization", {})
    resolved["visualization"].setdefault("enabled", True)
    resolved["visualization"].setdefault("alpha", 0.5)
    resolved["visualization"].setdefault("checkerboard_tile_size", 32)
    resolved["output"].setdefault("overwrite", False)
    return resolved


def canonical_config_json(config: Mapping[str, Any]) -> str:
    """Return a stable JSON representation used for experiment identifiers."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_hash(config: Mapping[str, Any], length: int = 12) -> str:
    """Return a short SHA-256 hash of a configuration mapping."""
    if length <= 0 or length > 64:
        raise ValueError("Hash length must be between 1 and 64.")
    digest = hashlib.sha256(canonical_config_json(config).encode("utf-8")).hexdigest()
    return digest[:length]


def resolve_project_path(project_root: str | Path, path_value: str | Path) -> Path:
    """Resolve a project-relative path without requiring the current working directory."""
    root = Path(project_root).expanduser().resolve()
    path = Path(path_value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _center_from_config(config: Mapping[str, Any]) -> list[float] | None:
    center = config.get("center")
    if center is None:
        return None
    array = np.asarray(center, dtype=np.float64)
    if array.shape != (2,):
        raise ValueError("transform.center must contain [x, y].")
    return [float(array[0]), float(array[1])]


def build_transform(config: Mapping[str, Any]) -> np.ndarray:
    """Construct a 3x3 transform from the configured transformation model."""
    transform_type = str(config.get("type", "")).strip().lower()
    params = config.get("parameters", {})
    if not isinstance(params, Mapping):
        raise ValueError("transform.parameters must be a mapping.")

    if transform_type == "identity":
        return identity_matrix()
    if transform_type == "translation":
        return translation_matrix(float(params.get("tx", 0.0)), float(params.get("ty", 0.0)))
    if transform_type == "rigid":
        return rigid_matrix(
            angle_degrees=float(params.get("angle_degrees", 0.0)),
            tx=float(params.get("tx", 0.0)),
            ty=float(params.get("ty", 0.0)),
            center=_center_from_config(params),
        )
    if transform_type == "similarity":
        return similarity_matrix(
            scale=float(params.get("scale", 1.0)),
            angle_degrees=float(params.get("angle_degrees", 0.0)),
            tx=float(params.get("tx", 0.0)),
            ty=float(params.get("ty", 0.0)),
            center=_center_from_config(params),
        )
    if transform_type == "affine":
        linear = params.get("linear")
        if linear is None:
            raise ValueError("Affine transform requires transform.parameters.linear.")
        return affine_matrix(
            linear=linear,
            tx=float(params.get("tx", 0.0)),
            ty=float(params.get("ty", 0.0)),
            center=_center_from_config(params),
        )

    raise ValueError(
        "Unsupported transform.type. Use identity, translation, rigid, similarity, or affine."
    )
