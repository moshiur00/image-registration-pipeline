"""Integrated benchmark utilities for controlled Week 2 dataset generation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .difficulty import validate_difficulty_tiers
from .synthetic import GroundTruthTransform, image_center
from .transforms import affine_matrix, invert_transform, rigid_matrix, similarity_matrix, translation_matrix

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class BenchmarkCasePlan:
    """Deterministic plan for one integrated benchmark case."""

    case_id: str
    tier: str
    source_id: str
    transform_family: str
    modality_class: str
    degradation_id: str
    multimodal_id: str | None
    restricted_fov: bool
    seed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "tier": self.tier,
            "source_id": self.source_id,
            "transform_family": self.transform_family,
            "modality_class": self.modality_class,
            "degradation_id": self.degradation_id,
            "multimodal_id": self.multimodal_id,
            "restricted_fov": self.restricted_fov,
            "seed": self.seed,
        }


def _interval(specification: Mapping[str, Any], key: str) -> tuple[float, float]:
    values = np.asarray(specification.get(key), dtype=np.float64)
    if values.shape != (2,):
        raise ValueError(f"Difficulty field '{key}' must contain [minimum, maximum].")
    low, high = float(values[0]), float(values[1])
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError(f"Difficulty field '{key}' must contain finite values.")
    if low < 0.0 or low > high:
        raise ValueError(f"Difficulty field '{key}' must satisfy 0 <= minimum <= maximum.")
    return low, high


def _sample_magnitude(rng: np.random.Generator, interval: tuple[float, float]) -> float:
    low, high = interval
    if np.isclose(low, high):
        return low
    return float(rng.uniform(low, high))


def _sample_signed(rng: np.random.Generator, interval: tuple[float, float]) -> float:
    magnitude = _sample_magnitude(rng, interval)
    if np.isclose(magnitude, 0.0):
        return 0.0
    return magnitude if int(rng.integers(0, 2)) else -magnitude


def _sample_scale(rng: np.random.Generator, interval: tuple[float, float]) -> float:
    deviation = _sample_magnitude(rng, interval)
    sign = 1.0 if int(rng.integers(0, 2)) else -1.0
    scale = 1.0 + sign * deviation
    if scale <= 0.0:
        raise ValueError("Sampled scale must remain greater than zero.")
    return scale


def sample_benchmark_ground_truth(
    transform_family: str,
    tier_specification: Mapping[str, Any],
    rng: np.random.Generator,
    image_shape: tuple[int, ...],
) -> GroundTruthTransform:
    """Sample a benchmark transform using the configured tier severity ranges."""
    family = str(transform_family).strip().lower()
    translation_range = _interval(tier_specification, "translation_abs_px")
    rotation_range = _interval(tier_specification, "rotation_abs_degrees")
    scale_range = _interval(tier_specification, "scale_deviation_abs")
    shear_range = _interval(tier_specification, "affine_shear_abs")

    tx = _sample_signed(rng, translation_range)
    ty = _sample_signed(rng, translation_range)
    center = image_center(image_shape)

    if family == "translation":
        matrix = translation_matrix(tx, ty)
        parameters: dict[str, Any] = {"tx": tx, "ty": ty}

    elif family == "rigid":
        angle = _sample_signed(rng, rotation_range)
        matrix = rigid_matrix(angle, tx=tx, ty=ty, center=center)
        parameters = {
            "tx": tx,
            "ty": ty,
            "angle_degrees": angle,
            "center": center.tolist(),
        }

    elif family == "similarity":
        angle = _sample_signed(rng, rotation_range)
        scale = _sample_scale(rng, scale_range)
        matrix = similarity_matrix(scale, angle, tx=tx, ty=ty, center=center)
        parameters = {
            "tx": tx,
            "ty": ty,
            "angle_degrees": angle,
            "scale": scale,
            "center": center.tolist(),
        }

    elif family == "affine":
        angle = _sample_signed(rng, rotation_range)
        scale_x = _sample_scale(rng, scale_range)
        scale_y = _sample_scale(rng, scale_range)
        shear_x = _sample_signed(rng, shear_range)
        theta = np.deg2rad(angle)
        rotation = np.array(
            [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
            dtype=np.float64,
        )
        scale = np.array([[scale_x, 0.0], [0.0, scale_y]], dtype=np.float64)
        shear = np.array([[1.0, shear_x], [0.0, 1.0]], dtype=np.float64)
        linear = rotation @ shear @ scale
        matrix = affine_matrix(linear, tx=tx, ty=ty, center=center)
        parameters = {
            "tx": tx,
            "ty": ty,
            "angle_degrees": angle,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "shear_x": shear_x,
            "center": center.tolist(),
            "linear": linear.tolist(),
        }

    else:
        raise ValueError("transform_family must be translation, rigid, similarity, or affine.")

    return GroundTruthTransform(
        transform_type=family,
        parameters=parameters,
        moving_to_fixed=matrix,
        fixed_to_moving=invert_transform(matrix),
    )


def build_case_plan(
    *,
    base_seed: int,
    samples_per_tier: int,
    tiers: Sequence[str],
    source_ids: Sequence[str],
    transform_families: Sequence[str],
    degradation_ids: Sequence[str],
    multimodal_ids: Sequence[str],
    restricted_fov_every: int = 4,
) -> list[BenchmarkCasePlan]:
    """Build a deterministic case plan with balanced coverage across factors."""
    if samples_per_tier < 1:
        raise ValueError("samples_per_tier must be at least 1.")
    if not tiers or not source_ids or not transform_families or not degradation_ids:
        raise ValueError("tiers, source_ids, transform_families, and degradation_ids must be non-empty.")
    if not multimodal_ids:
        raise ValueError("multimodal_ids must be non-empty.")
    if restricted_fov_every < 1:
        raise ValueError("restricted_fov_every must be at least 1.")

    plans: list[BenchmarkCasePlan] = []
    for tier_index, tier in enumerate(tiers):
        for case_index in range(samples_per_tier):
            modality_class = "monomodal" if case_index % 2 == 0 else "simulated_multimodal"
            multimodal_id = None
            if modality_class == "simulated_multimodal":
                multimodal_id = multimodal_ids[(case_index // 2) % len(multimodal_ids)]

            case_number = case_index + 1
            plans.append(
                BenchmarkCasePlan(
                    case_id=f"{tier}_{case_number:03d}",
                    tier=str(tier),
                    source_id=str(source_ids[case_index % len(source_ids)]),
                    transform_family=str(transform_families[case_index % len(transform_families)]),
                    modality_class=modality_class,
                    degradation_id=str(degradation_ids[case_index % len(degradation_ids)]),
                    multimodal_id=multimodal_id,
                    restricted_fov=(case_number % restricted_fov_every == 0),
                    seed=int(base_seed + (tier_index + 1) * 100_003 + case_number * 1_009),
                )
            )
    return plans


def validate_integrated_benchmark_config(config: Mapping[str, Any]) -> None:
    """Validate the fields needed by the integrated Week 2 generator."""
    benchmark = config.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise ValueError("benchmark must be a mapping.")
    samples_per_tier = int(benchmark.get("samples_per_tier", 0))
    if samples_per_tier < 20:
        raise ValueError("benchmark.samples_per_tier must be at least 20.")

    tiers = config.get("difficulty_tiers")
    if not isinstance(tiers, Mapping):
        raise ValueError("difficulty_tiers must be a mapping.")
    validate_difficulty_tiers(tiers)
    for name in ("easy", "moderate", "hard"):
        _interval(tiers[name], "affine_shear_abs")

    families = benchmark.get("transform_families")
    if not isinstance(families, list) or len(set(map(str, families))) < 3:
        raise ValueError("At least three transform families are required.")

    degradation_cases = config.get("degradation_cases")
    if not isinstance(degradation_cases, list) or len(degradation_cases) < 4:
        raise ValueError("At least four degradation cases are required.")

    multimodal_cases = config.get("multimodal_cases")
    if not isinstance(multimodal_cases, list) or not multimodal_cases:
        raise ValueError("multimodal_cases must be a non-empty list.")


def benchmark_manifest_fingerprint(records: Sequence[Mapping[str, Any]]) -> str:
    """Return a stable SHA-256 fingerprint for benchmark records."""
    canonical = json.dumps(list(records), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_benchmark_records(
    records: Sequence[Mapping[str, Any]],
    *,
    samples_per_tier: int,
    tiers: Sequence[str] = ("easy", "moderate", "hard"),
) -> dict[str, Any]:
    """Validate final benchmark coverage and return a compact summary."""
    if not records:
        raise ValueError("Benchmark records must not be empty.")

    ids = [str(record.get("case_id", "")) for record in records]
    if any(not value for value in ids):
        raise ValueError("Every benchmark record must have a non-empty case_id.")
    if len(ids) != len(set(ids)):
        raise ValueError("Benchmark case IDs must be unique.")

    counts_by_tier = {tier: 0 for tier in tiers}
    modality_counts = {"monomodal": 0, "simulated_multimodal": 0}
    transform_families: set[str] = set()
    degradation_types: set[str] = set()
    overlap_count = 0

    for record in records:
        tier = str(record.get("tier", ""))
        if tier not in counts_by_tier:
            raise ValueError(f"Unexpected benchmark tier: {tier}")
        counts_by_tier[tier] += 1

        modality = str(record.get("modality_class", ""))
        if modality not in modality_counts:
            raise ValueError(f"Unexpected modality class: {modality}")
        modality_counts[modality] += 1

        transform_families.add(str(record.get("transform_family", "")))
        degradation_types.add(str(record.get("degradation", {}).get("type", "none")))
        overlap_fraction_value = float(record.get("fixed_overlap_fraction", 0.0))
        if not 0.0 < overlap_fraction_value <= 1.0:
            raise ValueError("fixed_overlap_fraction must be in the range (0, 1].")
        if bool(record.get("restricted_fov", False)):
            overlap_count += 1

        error = float(record.get("control_point_max_error_px", np.inf))
        if not np.isfinite(error) or error > 1e-8:
            raise ValueError("Control-point ground-truth verification failed.")

    for tier, count in counts_by_tier.items():
        if count < samples_per_tier:
            raise ValueError(f"Tier '{tier}' contains fewer than {samples_per_tier} records.")
    if len(transform_families) < 3:
        raise ValueError("Benchmark must contain at least three transform families.")
    if len(degradation_types.difference({"none"})) < 4:
        raise ValueError("Benchmark must contain at least four non-empty degradation types.")
    if any(count == 0 for count in modality_counts.values()):
        raise ValueError("Benchmark must contain both monomodal and simulated multimodal cases.")

    return {
        "total_records": len(records),
        "counts_by_tier": counts_by_tier,
        "modality_counts": modality_counts,
        "transform_families": sorted(transform_families),
        "degradation_types": sorted(degradation_types),
        "restricted_fov_cases": overlap_count,
    }
