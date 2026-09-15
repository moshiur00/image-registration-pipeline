"""Generate deterministic Week 2 Day 1 synthetic pairs with exact ground truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_registration.io import load_image  # noqa: E402
from image_registration.synthetic import (  # noqa: E402
    control_point_round_trip_error,
    generate_synthetic_pair,
    sample_ground_truth_transform,
)
from image_registration.transforms import apply_transform  # noqa: E402
from image_registration.visualization import save_grayscale_image  # noqa: E402
from image_registration.warping import warp_image  # noqa: E402


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a YAML mapping.")
    return config


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/week02_day01_synthetic_ground_truth.yaml",
        help="Configuration path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    config = _load_yaml(config_path)

    seed = int(config["experiment"].get("seed", 42))
    rng = np.random.default_rng(seed)

    source_cfg = config["source"]
    loaded = load_image(
        _resolve(str(source_cfg["image"])),
        color_mode=str(source_cfg.get("color_mode", "grayscale")),
    )
    fixed = loaded.array
    if fixed.ndim != 2:
        raise ValueError("Week 2 Day 1 demo expects a 2D grayscale source image.")

    synthetic_cfg = config["synthetic"]
    interpolation = str(synthetic_cfg.get("interpolation", "linear"))
    border_value = float(synthetic_cfg.get("border_value", 0.0))
    transform_families = synthetic_cfg.get("transform_families", [])
    if not isinstance(transform_families, list) or not transform_families:
        raise ValueError("synthetic.transform_families must be a non-empty list.")

    output_dir = _resolve(str(config["output"]["directory"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_grayscale_image(output_dir / "fixed.png", fixed, normalize=False)

    manifest: dict[str, Any] = {
        "experiment": str(config["experiment"]["name"]),
        "seed": seed,
        "source_image": str(loaded.path.relative_to(PROJECT_ROOT)),
        "transform_direction": "moving_to_fixed",
        "pairs": [],
    }

    print("Week 2 Day 1 synthetic ground-truth demonstration")
    print("---------------------------------------------------")
    print(f"Seed: {seed}")

    for index, family_cfg in enumerate(transform_families, start=1):
        if not isinstance(family_cfg, dict):
            raise ValueError("Each transform family entry must be a mapping.")
        transform_type = str(family_cfg.get("type", "")).strip().lower()
        ranges = family_cfg.get("ranges", {})

        ground_truth = sample_ground_truth_transform(
            transform_type,
            rng,
            fixed.shape,
            ranges,
        )
        pair = generate_synthetic_pair(
            fixed,
            ground_truth,
            interpolation=interpolation,
            border_value=border_value,
        )

        recovered = warp_image(
            pair.moving,
            ground_truth.moving_to_fixed,
            output_shape=fixed.shape,
            interpolation=interpolation,
            border_value=border_value,
        )
        point_errors = control_point_round_trip_error(pair)
        direct_recovery = apply_transform(
            pair.control_points_moving,
            ground_truth.moving_to_fixed,
        )

        pair_id = f"{index:02d}_{transform_type}"
        pair_dir = output_dir / pair_id
        pair_dir.mkdir(parents=True, exist_ok=True)
        save_grayscale_image(pair_dir / "moving.png", pair.moving, normalize=False)
        save_grayscale_image(pair_dir / "ground_truth_registered.png", recovered, normalize=False)

        ground_truth_payload = ground_truth.as_dict()
        ground_truth_payload["control_points_moving"] = pair.control_points_moving.tolist()
        ground_truth_payload["control_points_fixed"] = pair.control_points_fixed.tolist()
        ground_truth_payload["control_point_round_trip_error_px"] = point_errors.tolist()
        ground_truth_payload["max_control_point_error_px"] = float(np.max(point_errors))
        ground_truth_payload["direct_recovery_matches_stored_fixed_points"] = bool(
            np.allclose(direct_recovery, pair.control_points_fixed, atol=1e-10)
        )
        _json_dump(pair_dir / "ground_truth.json", ground_truth_payload)

        manifest["pairs"].append(
            {
                "pair_id": pair_id,
                "transform_type": transform_type,
                "ground_truth": ground_truth.as_dict(),
                "max_control_point_error_px": float(np.max(point_errors)),
            }
        )

        print(
            f"{pair_id:<18} max control-point error: "
            f"{float(np.max(point_errors)):.3e} px"
        )

    _json_dump(output_dir / "manifest.json", manifest)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    print(f"Output: {output_dir.relative_to(PROJECT_ROOT)}")
    print("Day 1 complete: deterministic synthetic pairs and exact ground truth generated.")


if __name__ == "__main__":
    main()
