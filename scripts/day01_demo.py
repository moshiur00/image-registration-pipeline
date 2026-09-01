"""Day 1 numerical smoke test for transform direction and inverse recovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_registration.conventions import (  # noqa: E402
    COORDINATE_ORDER,
    STORED_TRANSFORM_DIRECTION,
)
from image_registration.transforms import (  # noqa: E402
    apply_transform,
    invert_transform,
    translation_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/day01_translation_demo.yaml",
        help="Path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    expected_direction = config["convention"]["transform_direction"]
    expected_order = config["convention"]["coordinate_order"]
    if expected_direction != STORED_TRANSFORM_DIRECTION:
        raise ValueError("Configuration transform direction conflicts with project convention.")
    if expected_order != COORDINATE_ORDER:
        raise ValueError("Configuration coordinate order conflicts with project convention.")

    moving_point = np.array(
        [config["point"]["moving_x"], config["point"]["moving_y"]],
        dtype=np.float64,
    )
    tx = float(config["translation"]["tx"])
    ty = float(config["translation"]["ty"])

    transform_mf = translation_matrix(tx, ty)
    fixed_point = apply_transform(moving_point, transform_mf)
    recovered_moving_point = apply_transform(fixed_point, invert_transform(transform_mf))

    if not np.allclose(recovered_moving_point, moving_point, atol=1e-12):
        raise RuntimeError("Inverse recovery failed.")

    output_path = resolve_path(config["output"]["path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "experiment": config["experiment"]["name"],
        "seed": config["experiment"]["seed"],
        "transform_direction": STORED_TRANSFORM_DIRECTION,
        "coordinate_order": COORDINATE_ORDER,
        "moving_point_xy": moving_point.tolist(),
        "translation_xy": [tx, ty],
        "fixed_point_xy": fixed_point.tolist(),
        "recovered_moving_point_xy": recovered_moving_point.tolist(),
        "transform_moving_to_fixed": transform_mf.tolist(),
        "inverse_fixed_to_moving": invert_transform(transform_mf).tolist(),
        "inverse_recovery_passed": True,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print(f"Moving point: {tuple(moving_point)}")
    print(f"Translation:  ({tx:+g}, {ty:+g})")
    print(f"Fixed point:  {tuple(fixed_point)}")
    print(f"Recovered:    {tuple(recovered_moving_point)}")
    print(f"Saved:        {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
