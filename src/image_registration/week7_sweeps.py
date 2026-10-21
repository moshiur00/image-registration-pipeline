"""Week 7 Day 32 controlled synthetic severity experiments.

Generate development-only pairs. Ground truth stays in this offline module and
must never be supplied to RegistrationService or to candidate selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

import numpy as np

from .benchmark_runner import BenchmarkPairSpec
from .degradations import gaussian_noise, gaussian_blur, adjust_gamma, rectangular_occlusion
from .multimodal import (intensity_inversion, nonlinear_gamma_mapping,
                         histogram_remap, edge_emphasized_representation)
from .overlap import (apply_field_of_view, overlap_mask_in_fixed_space,
                      rectangular_field_of_view_mask, transformed_support_mask)
from .synthetic import sample_ground_truth_transform, generate_synthetic_pair
from .transforms import apply_transform
from .week7_robustness import CONDITIONS

SEVERITY_VERSION = 'week07_day32_severity_v1'


@dataclass(frozen=True)
class PreparedSweepPair:
    fixed: np.ndarray
    moving: np.ndarray
    ground_truth: np.ndarray
    moving_points: np.ndarray
    valid_mask_moving: np.ndarray
    reference_overlap_fixed: np.ndarray
    metadata: dict[str, Any]


def _rng(pair_id: str, domain: str) -> np.random.Generator:
    digest = sha256(f'{SEVERITY_VERSION}/{pair_id}/{domain}'.encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], 'big'))


def _param(spec: Mapping[str, Any], key: str, minimum: float, maximum: float) -> float:
    if set(spec) != {key}:
        raise ValueError(f'Expected exactly one severity parameter {key}.')
    value = spec[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{key} must be numeric.')
    number = float(value)
    if not np.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f'{key} must be within [{minimum}, {maximum}].')
    return number


def _geometry(model: str, condition: str, severity: Mapping[str, Any], image_shape: tuple[int, int], geometry_seed: int):
    """Hold non-swept motion parameters fixed across seeds/conditions."""
    rng = np.random.default_rng(geometry_seed)
    tx, ty = 4.0 + float(rng.uniform(-1.5, 1.5)), -3.0 + float(rng.uniform(-1.5, 1.5))
    angle = 3.0 + float(rng.uniform(-0.8, 0.8)) if model != 'translation' else 0.0
    scale = 1.02
    if condition == 'rotation':
        angle = _param(severity, 'angle_degrees', 0.0, 90.0)
        if model == 'translation':
            raise ValueError('Rotation severity is incompatible with translation geometry.')
    if condition == 'scale':
        change = _param(severity, 'deviation_fraction', 0.0, 0.8)
        scale = 1.0 + change
        if model not in {'similarity', 'affine'}:
            raise ValueError('Scale severity requires similarity or affine geometry.')
    parameters: dict[str, tuple[float, float]] = {'tx': (tx, tx), 'ty': (ty, ty)}
    if model != 'translation':
        parameters['angle_degrees'] = (angle, angle)
    if model == 'similarity':
        parameters['scale'] = (scale, scale)
    if model == 'affine':
        parameters.update(scale_x=(scale, scale), scale_y=(scale, scale), shear_x=(0.015, 0.015))
    return sample_ground_truth_transform(model, np.random.default_rng(1), image_shape, parameters)


def prepare_sweep_pair(pair: BenchmarkPairSpec, fixed_image: np.ndarray) -> PreparedSweepPair:
    """Construct controlled appearances without changing registered point geometry."""
    if pair.metadata.get('split') != 'development':
        raise ValueError('Day32 may only synthesize development-split cases.')
    if not pair.reference.exact_transform:
        raise ValueError('Synthetic sweep requires exact offline geometric reference.')
    image = np.asarray(fixed_image)
    if image.ndim != 2 or image.dtype != np.uint8 or min(image.shape) < 32:
        raise ValueError('Day32 expects a 2D uint8 development image of at least 32 pixels.')
    condition = pair.degradation
    if condition not in CONDITIONS and condition != 'none':
        raise ValueError(f'Unsupported severity condition: {condition}')
    severity = dict(pair.metadata.get('condition_parameters') or {})
    if condition == 'none' and severity:
        raise ValueError('Clean condition requires empty parameters.')
    seed = pair.metadata.get('geometry_seed')
    if type(seed) is not int or seed < 0:
        raise ValueError('Day32 pair requires a non-negative geometry_seed.')
    gt = _geometry(pair.transform_model, condition, severity, image.shape, seed)
    synthetic = generate_synthetic_pair(image, gt)
    moving = np.asarray(synthetic.moving).copy()
    valid = np.ones(moving.shape, dtype=np.uint8)
    metadata: dict[str, Any] = {
        'severity_version': SEVERITY_VERSION, 'condition': condition,
        'parameters': severity, 'modality_class': pair.modality_class,
        'transform_direction': 'moving_to_fixed', 'interpolation': 'linear',
    }
    if condition == 'multimodal_mapping':
        name = severity.get('mapping')
        if set(severity) != {'mapping'} or name not in {'inversion', 'histogram_remap', 'edge_emphasis'}:
            raise ValueError('Unsupported multimodal mapping severity.')
        if pair.modality_class != 'simulated_multimodal':
            raise ValueError('Multimodal mapping requires simulated_multimodal.')
        if name == 'inversion':
            moving = intensity_inversion(moving)
        elif name == 'histogram_remap':
            moving = histogram_remap(moving, input_knots=[0, .25, .5, .75, 1],
                                     output_knots=[0, .08, .56, .92, 1])
        else:
            moving = edge_emphasized_representation(moving, blend=1.0)
    else:
        if pair.modality_class == 'simulated_multimodal':
            moving = intensity_inversion(moving)
        elif pair.modality_class != 'monomodal':
            raise ValueError('Unknown modality class.')
        if condition == 'gaussian_noise':
            moving = gaussian_noise(moving, sigma_fraction=_param(severity, 'sigma_fraction', 0, .5),
                                    rng=_rng(pair.pair_id, 'noise'))
        elif condition == 'gaussian_blur':
            moving = gaussian_blur(moving, sigma=_param(severity, 'sigma', 0, 15))
        elif condition == 'illumination':
            moving = adjust_gamma(moving, gamma=_param(severity, 'gamma', .1, 5.0))
        elif condition == 'occlusion':
            moving, visible, box = rectangular_occlusion(
                moving, area_fraction=_param(severity, 'area_fraction', .001, .9),
                rng=_rng(pair.pair_id, 'occlusion'))
            valid = visible
            metadata['occlusion_box'] = box
        elif condition == 'partial_overlap':
            target = _param(severity, 'target_overlap', .05, 1.0)
            # Choose a centered restricted field of view of the moving image.
            # Binary search the *actual warped valid support*; exact geometric
            # correspondence is independent of this image visibility change.
            original_support = overlap_mask_in_fixed_space(valid, gt.moving_to_fixed, fixed_shape=image.shape)
            maximum = float(np.mean(original_support))
            if target > maximum + 0.02:
                raise ValueError('Requested overlap exceeds geometric maximum for this pair.')
            low, high = .01, 1.0
            for _ in range(18):
                middle = (low + high) / 2.0
                trial = rectangular_field_of_view_mask(moving.shape, width_fraction=middle,
                                                       height_fraction=1.0, center_x_fraction=.5)
                actual = float(np.mean(overlap_mask_in_fixed_space(trial, gt.moving_to_fixed,
                                                                    fixed_shape=image.shape)))
                if actual < target:
                    low = middle
                else:
                    high = middle
            valid = rectangular_field_of_view_mask(moving.shape, width_fraction=(low + high) / 2.0,
                                                   height_fraction=1.0, center_x_fraction=.5)
            moving = apply_field_of_view(moving, valid)
            metadata['target_overlap'] = target
        elif condition == 'low_texture':
            strength = _param(severity, 'texture_strength', 0.0, 1.0)
            moving = np.rint(strength * moving.astype(float) + (1 - strength) * float(np.mean(moving))).clip(0, 255).astype(np.uint8)
        elif condition == 'repeated_pattern':
            fraction = _param(severity, 'repeat_fraction', 0.0, 1.0)
            # Synthetic appearance-only ambiguity, not altered ground truth.
            yy, xx = np.indices(moving.shape)
            stripe = ((xx // 10) % 2) * 180.0 + 35.0
            moving = np.rint((1 - fraction) * moving.astype(float) + fraction * stripe).clip(0, 255).astype(np.uint8)
        elif condition not in {'none', 'rotation', 'scale'}:
            raise ValueError(f'Unhandled condition: {condition}')
    reference_mask = overlap_mask_in_fixed_space(valid, gt.moving_to_fixed, fixed_shape=image.shape)
    actual_overlap = float(np.mean(reference_mask))
    if actual_overlap <= 0:
        raise ValueError('No valid evaluation overlap.')
    # Independent matrix and point round trip, not computed by the evaluator.
    recovered = apply_transform(synthetic.control_points_moving, gt.moving_to_fixed)
    max_error = float(np.max(np.linalg.norm(recovered - synthetic.control_points_fixed, axis=1)))
    inversion_error = float(np.max(np.abs(gt.moving_to_fixed @ gt.fixed_to_moving - np.eye(3))))
    if max_error > 1e-8 or inversion_error > 1e-10:
        raise AssertionError('Independent synthetic geometry verification failed.')
    if condition == 'partial_overlap' and abs(actual_overlap - metadata['target_overlap']) > .03:
        raise ValueError('Actual support differs from requested overlap by more than 0.03.')
    metadata.update(reference_valid_overlap_fraction=actual_overlap,
                    reference_control_point_round_trip_max_px=max_error,
                    reference_matrix_inverse_max_error=inversion_error)
    return PreparedSweepPair(image.copy(), moving, gt.moving_to_fixed,
                             synthetic.control_points_moving.copy(), valid,
                             reference_mask, metadata)


def stratified_dry_run_pairs(pairs: list[BenchmarkPairSpec]) -> list[BenchmarkPairSpec]:
    """Small deterministic sample: every planned condition plus clean, models/modalities."""
    ordered = sorted(pairs, key=lambda p: p.pair_id)
    selected: dict[str, BenchmarkPairSpec] = {}
    for condition in ['none', *sorted(CONDITIONS)]:
        candidates = [p for p in ordered if p.degradation == condition]
        if candidates:
            chosen = candidates[0]
            selected[chosen.pair_id] = chosen
    for model in ['translation', 'rigid', 'similarity', 'affine']:
        for modality in ['monomodal', 'simulated_multimodal']:
            candidates = [p for p in ordered if p.transform_model == model and p.modality_class == modality]
            if candidates:
                chosen = candidates[0]
                selected[chosen.pair_id] = chosen
    return sorted(selected.values(), key=lambda p:p.pair_id)
