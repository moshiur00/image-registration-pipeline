"""Configuration-driven image-registration experiment runner."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import platform
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np
import yaml

from .config import build_transform, config_hash, load_config, resolve_project_path, with_defaults
from .conventions import COORDINATE_ORDER, STORED_TRANSFORM_DIRECTION
from .evaluation import evaluate_pair
from .io import load_image, validate_image_pair
from .preprocessing import preprocess_image
from .visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
    save_grayscale_image,
)
from .warping import warp_image


@dataclass(frozen=True)
class ExperimentResult:
    """Paths and summary values from one completed pipeline run."""

    run_id: str
    run_directory: Path
    config_hash: str
    unregistered_metrics: dict[str, float]
    registered_metrics: dict[str, float]
    timing_seconds: dict[str, float]


def _safe_name(name: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in name.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "experiment"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_versions() -> dict[str, str | None]:
    packages = [
        "numpy",
        "scipy",
        "opencv-python",
        "SimpleITK",
        "scikit-image",
        "pandas",
        "matplotlib",
        "seaborn",
        "PyYAML",
    ]
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_metrics_csv(
    path: Path,
    unregistered: Mapping[str, float],
    registered: Mapping[str, float],
) -> None:
    metric_names = sorted(set(unregistered) | set(registered))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["state", *metric_names])
        writer.writeheader()
        writer.writerow({"state": "unregistered", **unregistered})
        writer.writerow({"state": "registered", **registered})


def _close_logger_handlers(logger: logging.Logger) -> None:
    """Flush, close, and detach every handler owned by a run logger."""
    for handler in list(logger.handlers):
        try:
            handler.flush()
        finally:
            handler.close()
            logger.removeHandler(handler)


def _setup_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger(f"image_registration.run.{path.parent.name}")
    _close_logger_handlers(logger)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def run_experiment(
    config_path: str | Path,
    *,
    project_root: str | Path,
) -> ExperimentResult:
    """Run load -> preprocess -> warp -> evaluate -> save from one YAML file."""
    total_start = perf_counter()
    project_root_path = Path(project_root).expanduser().resolve()
    loaded_config = load_config(config_path)
    config = with_defaults(loaded_config)
    digest = config_hash(config)

    experiment_name = str(config["experiment"]["name"])
    run_id = f"{_safe_name(experiment_name)}_{digest}"
    output_root = resolve_project_path(project_root_path, config["output"]["root"])
    run_directory = output_root / run_id

    if run_directory.exists():
        if bool(config["output"].get("overwrite", False)):
            stale_logger = logging.getLogger(f"image_registration.run.{run_id}")
            _close_logger_handlers(stale_logger)
            shutil.rmtree(run_directory)
        else:
            raise FileExistsError(
                f"Run directory already exists: {run_directory}. "
                "Set output.overwrite: true to replace it."
            )

    figures_dir = run_directory / "figures"
    run_directory.mkdir(parents=True, exist_ok=False)
    figures_dir.mkdir(parents=True, exist_ok=True)
    logger = _setup_logger(run_directory / "run.log")

    seed = int(config["experiment"]["seed"])
    random.seed(seed)
    np.random.seed(seed)

    fixed_path = resolve_project_path(project_root_path, config["data"]["fixed"])
    moving_path = resolve_project_path(project_root_path, config["data"]["moving"])
    logger.info("Starting run %s", run_id)
    logger.info("Fixed image: %s", fixed_path)
    logger.info("Moving image: %s", moving_path)

    resolved_config = dict(config)
    resolved_config["data"] = dict(config["data"])
    resolved_config["data"]["fixed"] = str(fixed_path)
    resolved_config["data"]["moving"] = str(moving_path)
    resolved_config["output"] = dict(config["output"])
    resolved_config["output"]["run_directory"] = str(run_directory)
    with (run_directory / "resolved_config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(resolved_config, handle, sort_keys=False)

    timing: dict[str, float] = {}

    stage_start = perf_counter()
    color_mode = str(config["data"]["color_mode"])
    fixed_loaded = load_image(fixed_path, color_mode=color_mode)
    moving_loaded = load_image(moving_path, color_mode=color_mode)
    validate_image_pair(
        fixed_loaded,
        moving_loaded,
        require_same_shape=bool(config["data"]["require_same_shape"]),
        require_same_ndim=bool(config["data"]["require_same_ndim"]),
    )
    timing["load_and_validate"] = perf_counter() - stage_start

    stage_start = perf_counter()
    fixed_pre, fixed_report = preprocess_image(fixed_loaded.array, config["preprocessing"])
    moving_pre, moving_report = preprocess_image(moving_loaded.array, config["preprocessing"])
    timing["preprocessing"] = perf_counter() - stage_start

    transform = build_transform(config["transform"])

    stage_start = perf_counter()
    registered = warp_image(
        moving_pre,
        transform,
        output_shape=(int(fixed_pre.shape[0]), int(fixed_pre.shape[1])),
        interpolation=str(config["warp"]["interpolation"]),
        border_value=float(config["warp"]["border_value"]),
    ).astype(np.float32)
    timing["warping"] = perf_counter() - stage_start

    unregistered_metrics: dict[str, float] = {}
    registered_metrics: dict[str, float] = {}
    stage_start = perf_counter()
    if bool(config["evaluation"]["enabled"]):
        unregistered_metrics = evaluate_pair(fixed_pre, moving_pre)
        registered_metrics = evaluate_pair(fixed_pre, registered)
    timing["evaluation"] = perf_counter() - stage_start

    stage_start = perf_counter()
    save_grayscale_image(figures_dir / "fixed_preprocessed.png", fixed_pre)
    save_grayscale_image(figures_dir / "moving_preprocessed.png", moving_pre)
    save_grayscale_image(figures_dir / "registered.png", registered)

    if bool(config["visualization"]["enabled"]):
        save_grayscale_image(
            figures_dir / "difference.png",
            absolute_difference(fixed_pre, registered, normalize=True),
        )
        save_grayscale_image(
            figures_dir / "overlay.png",
            alpha_overlay(
                fixed_pre,
                registered,
                alpha=float(config["visualization"]["alpha"]),
            ),
        )
        save_grayscale_image(
            figures_dir / "checkerboard.png",
            checkerboard(
                fixed_pre,
                registered,
                tile_size=int(config["visualization"]["checkerboard_tile_size"]),
            ),
        )
        save_comparison_figure(
            fixed_pre,
            moving_pre,
            registered,
            figures_dir / "comparison.png",
            title=str(config["visualization"].get("title", experiment_name)),
        )
    timing["visualization"] = perf_counter() - stage_start

    metrics_payload = {
        "unregistered": unregistered_metrics,
        "registered": registered_metrics,
    }
    _write_json(run_directory / "metrics.json", metrics_payload)
    _write_metrics_csv(run_directory / "metrics.csv", unregistered_metrics, registered_metrics)
    _write_json(
        run_directory / "transform.json",
        {
            "type": str(config["transform"]["type"]),
            "source": str(config["transform"].get("source", "known")),
            "direction": STORED_TRANSFORM_DIRECTION,
            "coordinate_order": COORDINATE_ORDER,
            "parameters": config["transform"].get("parameters", {}),
            "matrix": transform.tolist(),
        },
    )

    timing["total"] = perf_counter() - total_start
    _write_json(run_directory / "timing.json", timing)

    metadata = {
        "experiment": experiment_name,
        "run_id": run_id,
        "config_hash": digest,
        "seed": seed,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "fixed": {
                **fixed_loaded.metadata_dict(),
                "sha256": _file_sha256(fixed_path),
            },
            "moving": {
                **moving_loaded.metadata_dict(),
                "sha256": _file_sha256(moving_path),
            },
        },
        "preprocessing": {
            "fixed": fixed_report,
            "moving": moving_report,
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "packages": _package_versions(),
        },
    }
    _write_json(run_directory / "metadata.json", metadata)

    summary = {
        "experiment": experiment_name,
        "run_id": run_id,
        "status": "complete",
        "config_hash": digest,
        "metrics_file": "metrics.json",
        "transform_file": "transform.json",
        "timing_file": "timing.json",
        "metadata_file": "metadata.json",
        "figures_directory": "figures",
    }
    _write_json(run_directory / "run_summary.json", summary)

    logger.info("Run completed successfully")
    logger.info("Run directory: %s", run_directory)
    _close_logger_handlers(logger)

    return ExperimentResult(
        run_id=run_id,
        run_directory=run_directory,
        config_hash=digest,
        unregistered_metrics=unregistered_metrics,
        registered_metrics=registered_metrics,
        timing_seconds=timing,
    )
