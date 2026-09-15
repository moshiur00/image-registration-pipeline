"""Generate controlled degradations and partial-overlap benchmark examples."""

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

from image_registration.degradations import apply_degradation  # noqa: E402
from image_registration.io import load_image  # noqa: E402
from image_registration.overlap import (  # noqa: E402
    apply_field_of_view,
    combine_valid_masks,
    overlap_fraction,
    overlap_mask_in_fixed_space,
    rectangular_field_of_view_mask,
    transformed_support_mask,
)
from image_registration.synthetic import (  # noqa: E402
    generate_synthetic_pair,
    sample_ground_truth_transform,
)
from image_registration.visualization import save_grayscale_image  # noqa: E402
from image_registration.warping import warp_image  # noqa: E402


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a YAML mapping.")
    return config


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/week02_day02_degradations_overlap.yaml",
        help="Configuration path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    config = _load_yaml(config_path)

    seed = int(config["experiment"].get("seed", 42))
    geometry_rng = np.random.default_rng(seed)

    loaded = load_image(
        _resolve(str(config["source"]["image"])),
        color_mode=str(config["source"].get("color_mode", "grayscale")),
    )
    fixed = loaded.array
    if fixed.ndim != 2:
        raise ValueError("Week 2 Day 2 demo expects a 2D grayscale source image.")

    geometry_cfg = config["geometry"]
    ground_truth = sample_ground_truth_transform(
        str(geometry_cfg["type"]),
        geometry_rng,
        fixed.shape,
        geometry_cfg.get("ranges", {}),
    )
    pair = generate_synthetic_pair(
        fixed,
        ground_truth,
        interpolation=str(geometry_cfg.get("interpolation", "linear")),
        border_value=float(geometry_cfg.get("border_value", 0.0)),
    )

    output_dir = _resolve(str(config["output"]["directory"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_grayscale_image(output_dir / "fixed.png", fixed, normalize=False)
    save_grayscale_image(output_dir / "base_moving.png", pair.moving, normalize=False)

    recovered = warp_image(
        pair.moving,
        ground_truth.moving_to_fixed,
        output_shape=fixed.shape,
        interpolation=str(geometry_cfg.get("interpolation", "linear")),
        border_value=float(geometry_cfg.get("border_value", 0.0)),
    )
    save_grayscale_image(output_dir / "ground_truth_registered.png", recovered, normalize=False)

    moving_support = transformed_support_mask(
        fixed.shape,
        ground_truth.fixed_to_moving,
        destination_shape=fixed.shape,
    )
    base_overlap = overlap_mask_in_fixed_space(
        moving_support,
        ground_truth.moving_to_fixed,
        fixed_shape=fixed.shape,
    )
    save_grayscale_image(output_dir / "base_moving_support.png", moving_support * 255, normalize=False)
    save_grayscale_image(output_dir / "base_overlap_fixed.png", base_overlap * 255, normalize=False)

    manifest: dict[str, Any] = {
        "experiment": str(config["experiment"]["name"]),
        "seed": seed,
        "source_image": str(loaded.path.relative_to(PROJECT_ROOT)),
        "ground_truth": ground_truth.as_dict(),
        "base_overlap_fraction": overlap_fraction(base_overlap),
        "degradation_cases": [],
    }

    print("Week 2 Day 2 controlled-degradation demonstration")
    print("----------------------------------------------------")
    print(f"Seed: {seed}")
    print(f"Base geometric overlap: {manifest['base_overlap_fraction']:.3f}")

    cases = config.get("degradation_cases", [])
    if not isinstance(cases, list):
        raise ValueError("degradation_cases must be a list.")

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError("Each degradation case must be a mapping.")
        case_id = str(case.get("id", f"case_{index:02d}"))
        case_rng = np.random.default_rng(seed + index * 1009)
        result = apply_degradation(pair.moving, case, rng=case_rng)

        case_dir = output_dir / f"{index:02d}_{case_id}"
        case_dir.mkdir(parents=True, exist_ok=True)
        save_grayscale_image(case_dir / "moving_degraded.png", result.image, normalize=False)
        save_grayscale_image(
            case_dir / "visibility_mask_moving.png",
            result.visibility_mask * 255,
            normalize=False,
        )
        save_grayscale_image(
            case_dir / "valid_overlap_fixed.png",
            base_overlap * 255,
            normalize=False,
        )

        payload = {
            "case_id": case_id,
            "metadata": result.metadata,
            "geometric_overlap_fraction": overlap_fraction(base_overlap),
            "visible_fraction_moving": float(np.mean(result.visibility_mask)),
        }
        _write_json(case_dir / "metadata.json", payload)
        manifest["degradation_cases"].append(payload)
        print(
            f"{case_id:<24} overlap={payload['geometric_overlap_fraction']:.3f} "
            f"visible={payload['visible_fraction_moving']:.3f}"
        )

    partial_cfg = config["partial_overlap"]
    fov_mask = rectangular_field_of_view_mask(
        fixed.shape,
        width_fraction=float(partial_cfg["width_fraction"]),
        height_fraction=float(partial_cfg["height_fraction"]),
        center_x_fraction=float(partial_cfg.get("center_x_fraction", 0.5)),
        center_y_fraction=float(partial_cfg.get("center_y_fraction", 0.5)),
    )
    moving_valid = combine_valid_masks(moving_support, fov_mask)
    restricted_moving = apply_field_of_view(
        pair.moving,
        fov_mask,
        fill_value=float(partial_cfg.get("fill_value", 0.0)),
    )
    restricted_overlap = overlap_mask_in_fixed_space(
        moving_valid,
        ground_truth.moving_to_fixed,
        fixed_shape=fixed.shape,
    )

    partial_id = str(partial_cfg.get("id", "restricted_fov"))
    partial_dir = output_dir / f"{len(cases) + 1:02d}_{partial_id}"
    partial_dir.mkdir(parents=True, exist_ok=True)
    save_grayscale_image(partial_dir / "moving_restricted_fov.png", restricted_moving, normalize=False)
    save_grayscale_image(partial_dir / "field_of_view_mask_moving.png", fov_mask * 255, normalize=False)
    save_grayscale_image(partial_dir / "moving_valid_mask.png", moving_valid * 255, normalize=False)
    save_grayscale_image(partial_dir / "valid_overlap_fixed.png", restricted_overlap * 255, normalize=False)

    partial_payload = {
        "case_id": partial_id,
        "width_fraction": float(partial_cfg["width_fraction"]),
        "height_fraction": float(partial_cfg["height_fraction"]),
        "center_x_fraction": float(partial_cfg.get("center_x_fraction", 0.5)),
        "center_y_fraction": float(partial_cfg.get("center_y_fraction", 0.5)),
        "moving_valid_fraction": overlap_fraction(moving_valid),
        "fixed_overlap_fraction": overlap_fraction(restricted_overlap),
    }
    _write_json(partial_dir / "metadata.json", partial_payload)
    manifest["partial_overlap"] = partial_payload

    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    print(
        f"{partial_id:<24} overlap={partial_payload['fixed_overlap_fraction']:.3f} "
        f"moving-valid={partial_payload['moving_valid_fraction']:.3f}"
    )
    print(f"Output: {output_dir.relative_to(PROJECT_ROOT)}")
    print("Day 2 complete: controlled appearance changes and partial overlap generated.")


if __name__ == "__main__":
    main()
