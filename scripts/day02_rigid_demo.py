"""Day 2 numerical demo for 2D rotation and rigid transformation mathematics."""

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
    ANGLE_UNIT,
    COORDINATE_ORDER,
    POSITIVE_ROTATION_DIRECTION,
    STORED_TRANSFORM_DIRECTION,
)
from image_registration.transforms import (  # noqa: E402
    apply_transform,
    invert_transform,
    rigid_matrix,
    rotation_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/day02_rigid_demo.yaml",
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

    convention = config["convention"]
    if convention["transform_direction"] != STORED_TRANSFORM_DIRECTION:
        raise ValueError("Configuration transform direction conflicts with project convention.")
    if convention["coordinate_order"] != COORDINATE_ORDER:
        raise ValueError("Configuration coordinate order conflicts with project convention.")
    if convention["positive_rotation"] != POSITIVE_ROTATION_DIRECTION:
        raise ValueError("Configuration rotation direction conflicts with project convention.")
    if convention["angle_unit"] != ANGLE_UNIT:
        raise ValueError("Configuration angle unit conflicts with project convention.")

    moving_point = np.array(
        [config["point"]["moving_x"], config["point"]["moving_y"]],
        dtype=np.float64,
    )

    rigid_cfg = config["rigid_transform"]
    angle = float(rigid_cfg["angle_degrees"])
    tx = float(rigid_cfg["tx"])
    ty = float(rigid_cfg["ty"])
    center = np.array(
        [rigid_cfg["center_x"], rigid_cfg["center_y"]],
        dtype=np.float64,
    )

    rotation = rotation_matrix(angle)
    transform_mf = rigid_matrix(angle, tx=tx, ty=ty, center=center)
    fixed_point = apply_transform(moving_point, transform_mf)
    recovered_moving_point = apply_transform(fixed_point, invert_transform(transform_mf))

    expected_fixed = np.array(
        [config["expected"]["fixed_x"], config["expected"]["fixed_y"]],
        dtype=np.float64,
    )

    if not np.allclose(fixed_point, expected_fixed, atol=1e-12):
        raise RuntimeError(
            f"Known rigid-transform check failed: got {fixed_point}, expected {expected_fixed}."
        )
    if not np.allclose(recovered_moving_point, moving_point, atol=1e-12):
        raise RuntimeError("Rigid inverse recovery failed.")

    linear = transform_mf[:2, :2]
    orthogonality_error = float(np.linalg.norm(linear.T @ linear - np.eye(2)))
    determinant = float(np.linalg.det(linear))

    output_path = resolve_path(config["output"]["path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "experiment": config["experiment"]["name"],
        "seed": config["experiment"]["seed"],
        "transform_direction": STORED_TRANSFORM_DIRECTION,
        "coordinate_order": COORDINATE_ORDER,
        "positive_rotation": POSITIVE_ROTATION_DIRECTION,
        "angle_unit": ANGLE_UNIT,
        "moving_point_xy": moving_point.tolist(),
        "rotation_center_xy": center.tolist(),
        "angle_degrees": angle,
        "translation_xy": [tx, ty],
        "expected_fixed_point_xy": expected_fixed.tolist(),
        "fixed_point_xy": fixed_point.tolist(),
        "recovered_moving_point_xy": recovered_moving_point.tolist(),
        "rotation_about_origin": rotation.tolist(),
        "rigid_transform_moving_to_fixed": transform_mf.tolist(),
        "inverse_fixed_to_moving": invert_transform(transform_mf).tolist(),
        "rotation_determinant": determinant,
        "orthogonality_error": orthogonality_error,
        "known_point_check_passed": True,
        "inverse_recovery_passed": True,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print("Day 2 rigid-transform demonstration")
    print("------------------------------------")
    print(f"Moving point:      {tuple(map(float, moving_point))}")
    print(f"Rotation center:   {tuple(map(float, center))}")
    print(f"Angle:             {angle:+g} deg (counterclockwise in display)")
    print(f"Translation:       ({tx:+g}, {ty:+g})")
    print(f"Fixed point:       {tuple(map(float, fixed_point))}")
    print(f"Expected point:    {tuple(map(float, expected_fixed))}")
    print(f"Recovered moving:  {tuple(map(float, recovered_moving_point))}")
    print(f"det(R):            {determinant:.12f}")
    print(f"||R^T R - I||:     {orthogonality_error:.3e}")
    print(f"Saved:             {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
