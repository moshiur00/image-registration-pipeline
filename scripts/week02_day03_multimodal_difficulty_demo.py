"""Generate simulated multimodal pairs across easy, moderate, and hard tiers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_registration.difficulty import (  # noqa: E402
    sample_similarity_difficulty,
    validate_difficulty_tiers,
)
from image_registration.io import load_image  # noqa: E402
from image_registration.multimodal import apply_multimodal_mapping  # noqa: E402
from image_registration.overlap import (  # noqa: E402
    overlap_fraction,
    overlap_mask_in_fixed_space,
    transformed_support_mask,
)
from image_registration.synthetic import generate_synthetic_pair  # noqa: E402
from image_registration.visualization import (  # noqa: E402
    save_grayscale_image,
    save_intensity_histogram,
    save_joint_histogram,
)
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


def _tier_mapping_specification(case: Mapping[str, Any], tier: str) -> dict[str, Any]:
    resolved = {
        key: value
        for key, value in case.items()
        if key not in {"id", "per_tier"}
    }
    per_tier = case.get("per_tier", {})
    if per_tier:
        if not isinstance(per_tier, Mapping):
            raise ValueError("per_tier must be a mapping.")
        tier_values = per_tier.get(tier, {})
        if not isinstance(tier_values, Mapping):
            raise ValueError(f"per_tier.{tier} must be a mapping.")
        resolved.update(tier_values)
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/week02_day03_multimodal_difficulty.yaml",
        help="Configuration path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    config = _load_yaml(config_path)

    seed = int(config["experiment"].get("seed", 42))
    loaded = load_image(
        _resolve(str(config["source"]["image"])),
        color_mode=str(config["source"].get("color_mode", "grayscale")),
    )
    fixed = loaded.array
    if fixed.ndim != 2:
        raise ValueError("Week 2 Day 3 demo expects a 2D grayscale source image.")

    tiers = config.get("difficulty_tiers")
    if not isinstance(tiers, dict):
        raise ValueError("difficulty_tiers must be a mapping.")
    validate_difficulty_tiers(tiers)

    cases = config.get("multimodal_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("multimodal_cases must be a non-empty list.")

    geometry_cfg = config.get("geometry", {})
    interpolation = str(geometry_cfg.get("interpolation", "linear"))
    border_value = float(geometry_cfg.get("border_value", 0.0))
    bins = int(config.get("histograms", {}).get("bins", 48))

    output_dir = _resolve(str(config["output"]["directory"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_grayscale_image(output_dir / "fixed.png", fixed, normalize=False)

    manifest: dict[str, Any] = {
        "experiment": str(config["experiment"]["name"]),
        "seed": seed,
        "source_image": str(loaded.path.relative_to(PROJECT_ROOT)),
        "tiers": [],
    }

    print("Week 2 Day 3 simulated-multimodal difficulty demonstration")
    print("---------------------------------------------------------")
    print(f"Seed: {seed}")

    ordered_tiers = ("easy", "moderate", "hard")
    for tier_index, tier in enumerate(ordered_tiers, start=1):
        tier_rng = np.random.default_rng(seed + tier_index * 10007)
        difficulty = sample_similarity_difficulty(
            tier,
            tiers[tier],
            tier_rng,
            fixed.shape,
        )
        pair = generate_synthetic_pair(
            fixed,
            difficulty.ground_truth,
            interpolation=interpolation,
            border_value=border_value,
        )

        moving_support = transformed_support_mask(
            fixed.shape,
            difficulty.ground_truth.fixed_to_moving,
            destination_shape=fixed.shape,
        )
        valid_overlap = overlap_mask_in_fixed_space(
            moving_support,
            difficulty.ground_truth.moving_to_fixed,
            fixed_shape=fixed.shape,
        )
        overlap = overlap_fraction(valid_overlap)

        tier_dir = output_dir / tier
        tier_dir.mkdir(parents=True, exist_ok=True)
        save_grayscale_image(tier_dir / "moving_geometry.png", pair.moving, normalize=False)
        save_grayscale_image(tier_dir / "valid_overlap_fixed.png", valid_overlap * 255, normalize=False)

        registered_monomodal = warp_image(
            pair.moving,
            difficulty.ground_truth.moving_to_fixed,
            output_shape=fixed.shape,
            interpolation=interpolation,
            border_value=border_value,
        )
        save_grayscale_image(
            tier_dir / "registered_monomodal.png",
            registered_monomodal,
            normalize=False,
        )
        save_intensity_histogram(
            fixed,
            registered_monomodal,
            tier_dir / "monomodal_histogram.png",
            mask=valid_overlap,
            bins=bins,
            title=f"{tier.title()} monomodal intensity histograms",
        )
        save_joint_histogram(
            fixed,
            registered_monomodal,
            tier_dir / "monomodal_joint_histogram.png",
            mask=valid_overlap,
            bins=bins,
            title=f"{tier.title()} monomodal joint histogram",
        )

        tier_payload: dict[str, Any] = {
            "tier": tier,
            "difficulty": difficulty.as_dict(),
            "geometric_overlap_fraction": overlap,
            "multimodal_cases": [],
        }

        params = difficulty.ground_truth.parameters
        print(
            f"{tier:<9} | tx={params['tx']:+6.2f} px ty={params['ty']:+6.2f} px "
            f"rot={params['angle_degrees']:+6.2f} deg scale={params['scale']:.4f} "
            f"overlap={overlap:.3f}"
        )

        for case_index, case in enumerate(cases, start=1):
            if not isinstance(case, Mapping):
                raise ValueError("Each multimodal case must be a mapping.")
            case_id = str(case.get("id", f"case_{case_index:02d}"))
            specification = _tier_mapping_specification(case, tier)
            specification["noise_base_sigma_fraction"] = difficulty.severity[
                "noise_base_sigma_fraction"
            ]
            specification["noise_signal_sigma_fraction"] = difficulty.severity[
                "noise_signal_sigma_fraction"
            ]

            case_rng = np.random.default_rng(
                seed + tier_index * 10007 + case_index * 1009
            )
            mapped = apply_multimodal_mapping(
                pair.moving,
                specification,
                rng=case_rng,
            )
            registered = warp_image(
                mapped.image,
                difficulty.ground_truth.moving_to_fixed,
                output_shape=fixed.shape,
                interpolation=interpolation,
                border_value=border_value,
            )

            case_dir = tier_dir / f"{case_index:02d}_{case_id}"
            case_dir.mkdir(parents=True, exist_ok=True)
            save_grayscale_image(
                case_dir / "moving_multimodal.png",
                mapped.image,
                normalize=False,
            )
            save_grayscale_image(
                case_dir / "ground_truth_registered_multimodal.png",
                registered,
                normalize=False,
            )
            save_intensity_histogram(
                fixed,
                registered,
                case_dir / "intensity_histogram.png",
                mask=valid_overlap,
                bins=bins,
                title=f"{tier.title()} {case_id} intensity histograms",
            )
            save_joint_histogram(
                fixed,
                registered,
                case_dir / "joint_histogram.png",
                mask=valid_overlap,
                bins=bins,
                title=f"{tier.title()} {case_id} joint histogram",
            )

            payload = {
                "case_id": case_id,
                "modality_class": "simulated_multimodal",
                "mapping": mapped.metadata,
                "ground_truth_geometry_unchanged": True,
                "geometric_overlap_fraction": overlap,
            }
            _write_json(case_dir / "metadata.json", payload)
            tier_payload["multimodal_cases"].append(payload)

        _write_json(tier_dir / "tier_metadata.json", tier_payload)
        manifest["tiers"].append(tier_payload)

    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    print(f"Output: {output_dir.relative_to(PROJECT_ROOT)}")
    print("Day 3 complete: multimodal mappings and non-overlapping difficulty tiers generated.")


if __name__ == "__main__":
    main()
