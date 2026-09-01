from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from image_registration.pipeline import run_experiment
from image_registration.transforms import invert_transform, translation_matrix
from image_registration.warping import warp_image


def _write_test_inputs(root: Path) -> tuple[Path, Path]:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    fixed = np.zeros((80, 100), dtype=np.uint8)
    cv2.rectangle(fixed, (15, 18), (55, 50), 180, thickness=-1)
    cv2.circle(fixed, (72, 60), 10, 240, thickness=-1)

    transform = translation_matrix(6.0, -4.0)
    moving = warp_image(
        fixed,
        invert_transform(transform),
        output_shape=fixed.shape,
        interpolation="nearest",
    )

    fixed_path = data_dir / "fixed.png"
    moving_path = data_dir / "moving.png"
    assert cv2.imwrite(str(fixed_path), fixed)
    assert cv2.imwrite(str(moving_path), moving)
    return fixed_path, moving_path


def _write_config(root: Path, overwrite: bool = True) -> Path:
    config = {
        "experiment": {"name": "pipeline_test", "seed": 7},
        "data": {
            "fixed": "data/fixed.png",
            "moving": "data/moving.png",
            "color_mode": "grayscale",
            "require_same_shape": True,
            "require_same_ndim": True,
        },
        "preprocessing": {
            "grayscale": True,
            "clip_lower_percentile": 0.0,
            "clip_upper_percentile": 100.0,
            "normalize": True,
            "gaussian_sigma": 0.0,
            "resize": None,
        },
        "transform": {
            "source": "known",
            "type": "translation",
            "parameters": {"tx": 6.0, "ty": -4.0},
        },
        "warp": {"interpolation": "nearest", "border_value": 0.0},
        "evaluation": {"enabled": True},
        "visualization": {
            "enabled": True,
            "alpha": 0.5,
            "checkerboard_tile_size": 10,
            "title": "Pipeline test",
        },
        "output": {"root": "outputs", "overwrite": overwrite},
    }
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_pipeline_writes_structured_run_directory(tmp_path: Path) -> None:
    _write_test_inputs(tmp_path)
    config_path = _write_config(tmp_path)

    result = run_experiment(config_path, project_root=tmp_path)

    expected_files = {
        "resolved_config.yaml",
        "metrics.json",
        "metrics.csv",
        "transform.json",
        "timing.json",
        "metadata.json",
        "run_summary.json",
        "run.log",
    }
    assert expected_files.issubset({path.name for path in result.run_directory.iterdir()})
    assert (result.run_directory / "figures" / "comparison.png").exists()
    assert result.registered_metrics["mae"] < result.unregistered_metrics["mae"]
    assert result.registered_metrics["ncc"] > result.unregistered_metrics["ncc"]

    metadata = json.loads((result.run_directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == result.run_id
    assert len(metadata["inputs"]["fixed"]["sha256"]) == 64
    assert metadata["seed"] == 7


def test_pipeline_run_id_is_deterministic(tmp_path: Path) -> None:
    _write_test_inputs(tmp_path)
    config_path = _write_config(tmp_path, overwrite=True)
    first = run_experiment(config_path, project_root=tmp_path)
    second = run_experiment(config_path, project_root=tmp_path)
    assert first.run_id == second.run_id
    assert first.config_hash == second.config_hash


def test_pipeline_respects_overwrite_flag(tmp_path: Path) -> None:
    _write_test_inputs(tmp_path)
    config_path = _write_config(tmp_path, overwrite=False)
    run_experiment(config_path, project_root=tmp_path)
    with pytest.raises(FileExistsError):
        run_experiment(config_path, project_root=tmp_path)


def test_pipeline_releases_run_log_handler(tmp_path: Path) -> None:
    _write_test_inputs(tmp_path)
    config_path = _write_config(tmp_path, overwrite=True)

    result = run_experiment(config_path, project_root=tmp_path)

    import logging

    logger = logging.getLogger(f"image_registration.run.{result.run_id}")
    assert logger.handlers == []
