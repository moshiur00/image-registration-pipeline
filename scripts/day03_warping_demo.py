"""Day 3 demo for similarity, affine transformation, and image resampling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
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
    affine_matrix,
    apply_transform,
    invert_transform,
    similarity_matrix,
)
from image_registration.warping import warp_image, warp_mask  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/day03_warping_demo.yaml",
        help="Path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def create_test_image(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Create a deterministic grayscale image and a matching binary mask."""
    image = np.zeros((height, width), dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)

    cv2.rectangle(image, (35, 40), (130, 105), 180, thickness=-1)
    cv2.circle(image, (225, 78), 38, 235, thickness=-1)
    cv2.line(image, (60, 185), (260, 145), 120, thickness=7)
    cv2.putText(
        image,
        "R",
        (145, 195),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        255,
        4,
        cv2.LINE_AA,
    )

    cv2.rectangle(mask, (35, 40), (130, 105), 1, thickness=-1)
    cv2.circle(mask, (225, 78), 38, 2, thickness=-1)
    cv2.line(mask, (60, 185), (260, 145), 3, thickness=7)

    return image, mask


def save_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not write image: {path}")


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

    height = int(config["image"]["height"])
    width = int(config["image"]["width"])
    fixed, fixed_mask = create_test_image(height, width)

    similarity_cfg = config["similarity_transform"]
    center = np.array(
        [similarity_cfg["center_x"], similarity_cfg["center_y"]],
        dtype=np.float64,
    )
    transform_mf = similarity_matrix(
        scale=float(similarity_cfg["scale"]),
        angle_degrees=float(similarity_cfg["angle_degrees"]),
        tx=float(similarity_cfg["tx"]),
        ty=float(similarity_cfg["ty"]),
        center=center,
    )
    transform_fm = invert_transform(transform_mf)

    # Create a synthetic moving image from the fixed image using the exact
    # inverse transform. Registering it back with T_MF should recover alignment.
    moving = warp_image(
        fixed,
        transform_fm,
        output_shape=(height, width),
        interpolation="linear",
    )
    moving_mask = warp_mask(fixed_mask, transform_fm, output_shape=(height, width))

    output_dir = resolve_path(config["output"]["directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    save_image(output_dir / "fixed.png", fixed)
    save_image(output_dir / "moving.png", moving)
    save_image(output_dir / "fixed_mask.png", fixed_mask * 80)
    save_image(output_dir / "moving_mask.png", moving_mask * 80)

    interpolation_results: dict[str, dict[str, float]] = {}
    for method in config["interpolation"]["methods"]:
        registered = warp_image(
            moving,
            transform_mf,
            output_shape=(height, width),
            interpolation=method,
        )
        save_image(output_dir / f"registered_{method}.png", registered)

        valid = (fixed > 0) | (registered > 0)
        if np.any(valid):
            mean_abs_error = float(
                np.mean(
                    np.abs(
                        fixed[valid].astype(np.float64)
                        - registered[valid].astype(np.float64)
                    )
                )
            )
        else:
            mean_abs_error = 0.0

        interpolation_results[method] = {
            "mean_absolute_error_on_nonzero_union": mean_abs_error,
        }

    registered_mask = warp_mask(moving_mask, transform_mf, output_shape=(height, width))
    save_image(output_dir / "registered_mask.png", registered_mask * 80)

    mask_labels_before = sorted(int(v) for v in np.unique(moving_mask))
    mask_labels_after = sorted(int(v) for v in np.unique(registered_mask))

    # Demonstrate a general affine transform on control points. This is kept
    # separate from the image round-trip so the effects of anisotropic scaling
    # and shear are explicit.
    affine_linear = np.array([[1.10, 0.18], [-0.08, 0.92]], dtype=np.float64)
    affine = affine_matrix(affine_linear, tx=8.0, ty=-6.0, center=center)
    control_points = np.array(
        [[80.0, 70.0], [160.0, 120.0], [240.0, 170.0]],
        dtype=np.float64,
    )
    affine_points = apply_transform(control_points, affine)
    recovered_points = apply_transform(affine_points, invert_transform(affine))
    affine_recovery_error = float(np.max(np.abs(recovered_points - control_points)))

    result = {
        "experiment": config["experiment"]["name"],
        "seed": config["experiment"]["seed"],
        "transform_direction": STORED_TRANSFORM_DIRECTION,
        "coordinate_order": COORDINATE_ORDER,
        "positive_rotation": POSITIVE_ROTATION_DIRECTION,
        "angle_unit": ANGLE_UNIT,
        "image_shape_hw": [height, width],
        "similarity_transform_moving_to_fixed": transform_mf.tolist(),
        "similarity_inverse_fixed_to_moving": transform_fm.tolist(),
        "similarity_scale": float(similarity_cfg["scale"]),
        "similarity_angle_degrees": float(similarity_cfg["angle_degrees"]),
        "interpolation_results": interpolation_results,
        "mask_labels_before": mask_labels_before,
        "mask_labels_after": mask_labels_after,
        "affine_linear_component": affine_linear.tolist(),
        "affine_transform": affine.tolist(),
        "affine_control_points": control_points.tolist(),
        "affine_transformed_points": affine_points.tolist(),
        "affine_inverse_recovery_max_abs_error": affine_recovery_error,
    }

    result_path = output_dir / "result.json"
    with result_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print("Day 3 similarity, affine, and warping demonstration")
    print("--------------------------------------------------")
    print(f"Image size:          {width} x {height}")
    print(f"Similarity scale:    {float(similarity_cfg['scale']):.3f}")
    print(f"Rotation:            {float(similarity_cfg['angle_degrees']):+.1f} degrees")
    print(
        "Translation:         "
        f"({float(similarity_cfg['tx']):+g}, {float(similarity_cfg['ty']):+g})"
    )
    for method, values in interpolation_results.items():
        print(
            f"{method:>8} MAE:       "
            f"{values['mean_absolute_error_on_nonzero_union']:.4f}"
        )
    print(f"Mask labels before:  {mask_labels_before}")
    print(f"Mask labels after:   {mask_labels_after}")
    print(f"Affine inverse error:{affine_recovery_error:.3e}")
    print(f"Saved:               {output_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
