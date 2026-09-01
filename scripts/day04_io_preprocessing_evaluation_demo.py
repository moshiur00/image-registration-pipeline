"""Day 4 demo for loading, preprocessing, evaluation, and visualization."""

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

from image_registration.evaluation import evaluate_pair  # noqa: E402
from image_registration.io import load_image, validate_image_pair  # noqa: E402
from image_registration.preprocessing import preprocess_image  # noqa: E402
from image_registration.transforms import invert_transform, similarity_matrix  # noqa: E402
from image_registration.visualization import (  # noqa: E402
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
)
from image_registration.warping import warp_image  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/day04_io_preprocessing_evaluation_demo.yaml",
        help="Path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def create_fixed_image(height: int, width: int) -> np.ndarray:
    """Create a deterministic grayscale image with varied structures."""
    image = np.zeros((height, width), dtype=np.float32)
    gradient = np.linspace(15.0, 85.0, width, dtype=np.float32)
    image += gradient[None, :]

    cv2.rectangle(image, (30, 35), (125, 105), 160.0, thickness=-1)
    cv2.circle(image, (230, 72), 36, 225.0, thickness=-1)
    cv2.line(image, (55, 190), (275, 145), 125.0, thickness=8)
    cv2.putText(
        image,
        "D4",
        (135, 205),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.4,
        245.0,
        3,
        cv2.LINE_AA,
    )
    return np.clip(image, 0, 255).astype(np.uint8)


def save_uint8(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    converted = np.clip(image, 0, 255).astype(np.uint8)
    if not cv2.imwrite(str(path), converted):
        raise RuntimeError(f"Could not write image: {path}")


def save_float_visual(path: Path, image: np.ndarray) -> None:
    array = np.asarray(image, dtype=np.float32)
    lo = float(np.min(array))
    hi = float(np.max(array))
    if np.isclose(hi, lo):
        display = np.zeros_like(array, dtype=np.uint8)
    else:
        display = np.clip((array - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    save_uint8(path, display)


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    seed = int(config["experiment"]["seed"])
    rng = np.random.default_rng(seed)
    height = int(config["image"]["height"])
    width = int(config["image"]["width"])
    output_dir = resolve_path(config["output"]["directory"])
    input_dir = output_dir / "inputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    fixed_raw = create_fixed_image(height, width)
    transform_cfg = config["known_transform"]
    transform_mf = similarity_matrix(
        scale=float(transform_cfg["scale"]),
        angle_degrees=float(transform_cfg["angle_degrees"]),
        tx=float(transform_cfg["tx"]),
        ty=float(transform_cfg["ty"]),
        center=[float(transform_cfg["center_x"]), float(transform_cfg["center_y"])],
    )

    moving_raw = warp_image(
        fixed_raw,
        invert_transform(transform_mf),
        output_shape=(height, width),
        interpolation="linear",
    ).astype(np.float32)

    degradation = config["synthetic_degradation"]
    moving_raw = (
        moving_raw * float(degradation["brightness_gain"])
        + float(degradation["brightness_offset"])
        + rng.normal(0.0, float(degradation["gaussian_noise_sigma"]), moving_raw.shape)
    )
    moving_raw = np.clip(moving_raw, 0, 255).astype(np.uint8)

    fixed_path = input_dir / "fixed_raw.png"
    moving_path = input_dir / "moving_raw.png"
    save_uint8(fixed_path, fixed_raw)
    save_uint8(moving_path, moving_raw)

    fixed_loaded = load_image(fixed_path, color_mode="grayscale")
    moving_loaded = load_image(moving_path, color_mode="grayscale")
    validate_image_pair(fixed_loaded, moving_loaded)

    fixed_pre, fixed_report = preprocess_image(fixed_loaded.array, config["preprocessing"])
    moving_pre, moving_report = preprocess_image(moving_loaded.array, config["preprocessing"])

    registered = warp_image(
        moving_pre,
        transform_mf,
        output_shape=fixed_pre.shape,
        interpolation="linear",
    ).astype(np.float32)

    unregistered_metrics = evaluate_pair(fixed_pre, moving_pre)
    registered_metrics = evaluate_pair(fixed_pre, registered)

    save_float_visual(output_dir / "fixed_preprocessed.png", fixed_pre)
    save_float_visual(output_dir / "moving_preprocessed.png", moving_pre)
    save_float_visual(output_dir / "registered_known_transform.png", registered)
    save_float_visual(
        output_dir / "registered_difference.png",
        absolute_difference(fixed_pre, registered, normalize=True),
    )
    save_float_visual(
        output_dir / "registered_overlay.png",
        alpha_overlay(
            fixed_pre,
            registered,
            alpha=float(config["visualization"]["alpha"]),
        ),
    )
    save_float_visual(
        output_dir / "registered_checkerboard.png",
        checkerboard(
            fixed_pre,
            registered,
            tile_size=int(config["visualization"]["checkerboard_tile_size"]),
        ),
    )
    comparison_path = save_comparison_figure(
        fixed_pre,
        moving_pre,
        registered,
        output_dir / "comparison.png",
        title="Day 4 known-transform pipeline components",
    )

    result = {
        "experiment": config["experiment"]["name"],
        "seed": seed,
        "fixed_metadata": fixed_loaded.metadata_dict(),
        "moving_metadata": moving_loaded.metadata_dict(),
        "fixed_preprocessing": fixed_report,
        "moving_preprocessing": moving_report,
        "known_transform_moving_to_fixed": transform_mf.tolist(),
        "evaluation_note": (
            "Day 4 metrics are descriptive pipeline checks. They are not automatic proof "
            "of geometric or anatomical registration correctness."
        ),
        "unregistered_metrics": unregistered_metrics,
        "registered_metrics": registered_metrics,
        "comparison_figure": str(comparison_path.relative_to(PROJECT_ROOT)),
    }
    result_path = output_dir / "result.json"
    with result_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print("Day 4 loading, preprocessing, evaluation, and visualization demo")
    print("----------------------------------------------------------------")
    print(f"Fixed backend:       {fixed_loaded.backend}")
    print(f"Fixed shape:         {fixed_loaded.array.shape}")
    print(f"Fixed dtype:         {fixed_loaded.array.dtype}")
    print(f"Preprocessed range:  {fixed_pre.min():.3f} to {fixed_pre.max():.3f}")
    print(f"Unregistered MAE:    {unregistered_metrics['mae']:.4f}")
    print(f"Registered MAE:      {registered_metrics['mae']:.4f}")
    print(f"Unregistered NCC:    {unregistered_metrics['ncc']:.4f}")
    print(f"Registered NCC:      {registered_metrics['ncc']:.4f}")
    print(f"Unregistered SSIM:   {unregistered_metrics['ssim']:.4f}")
    print(f"Registered SSIM:     {registered_metrics['ssim']:.4f}")
    print(f"Saved:               {output_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
