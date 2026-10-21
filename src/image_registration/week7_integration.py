"""Week 7 Day 35 combined-stress *development-only* integration.

Synthetic truth is exclusively used for offline evaluation by the caller.
The exported offline policy may be evaluated but never trained or deployed here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

import numpy as np

from .benchmark_runner import BenchmarkPairSpec
from .degradations import adjust_gamma, gaussian_blur, gaussian_noise, rectangular_occlusion
from .multimodal import intensity_inversion, histogram_remap
from .overlap import apply_field_of_view, overlap_mask_in_fixed_space, rectangular_field_of_view_mask
from .evaluation_contracts import ReferenceEvidence
from .week7_sweeps import PreparedSweepPair, prepare_sweep_pair
from .week7_calibration import Gate, offline_evaluate, summarize_decisions

VERSION = 'week07_day35_combined_stress_v1'
GEOMETRY_SEEDS = (202, 303)  # separate from Day 34 tuning/audit seeds, NOT Week 8 data
COMBINATIONS = {
    'noise_blur': ('gaussian_noise', 'gaussian_blur'),
    'blur_occlusion': ('gaussian_blur', 'occlusion'),
    'overlap_illumination': ('partial_overlap', 'illumination'),
    'texture_repetition': ('low_texture', 'repeated_pattern'),
    'modality_noise': ('multimodal_mapping', 'gaussian_noise'),
    'modality_blur': ('multimodal_mapping', 'gaussian_blur'),
}
MONO = ('noise_blur', 'blur_occlusion', 'overlap_illumination', 'texture_repetition')
MULTI = ('modality_noise', 'modality_blur')
MODELS = ('translation', 'rigid', 'similarity', 'affine')


def specifications(source_sha256: str) -> list[BenchmarkPairSpec]:
    """Declare coverage without using any Day 32 outcomes or held-out pixels."""
    if len(source_sha256) != 64:
        raise ValueError('Development source SHA-256 required')
    pairs = []
    for seed in GEOMETRY_SEEDS:
        for model in MODELS:
            for label in MONO:
                pairs.append(_pair(seed, model, 'monomodal', label, source_sha256))
        for model in ('rigid', 'affine'):
            for label in MULTI:
                pairs.append(_pair(seed, model, 'simulated_multimodal', label, source_sha256))
    assert len({p.pair_id for p in pairs}) == len(pairs)
    return pairs


def _pair(seed: int, model: str, modality: str, label: str, source_hash: str) -> BenchmarkPairSpec:
    if label not in COMBINATIONS or model not in MODELS:
        raise ValueError('Unknown combined stress case')
    tag = sha256(f'{VERSION}/{seed}/{model}/{modality}/{label}/{source_hash}'.encode()).hexdigest()[:16]
    return BenchmarkPairSpec(
        pair_id=f'w7d35_{model}_{modality}_{label}_s{seed}_{tag}',
        modality_class=modality, transform_model=model, degradation='combined_stress',
        reference=ReferenceEvidence(exact_transform=True),
        metadata={'split': 'development', 'geometry_seed': seed,
                  'source_sha256': source_hash, 'combined_version': VERSION,
                  'combined_label': label, 'combined_factors': list(COMBINATIONS[label]),
                  'transform_direction': 'moving_to_fixed'},
    )


def _rng(pair_id: str, domain: str) -> np.random.Generator:
    digest = sha256(f'{VERSION}/{pair_id}/{domain}'.encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], 'big'))


def _restrict_overlap(moving: np.ndarray, gt: np.ndarray, target: float) -> tuple[np.ndarray, np.ndarray]:
    h, w = moving.shape
    lower, upper = 0.01, 1.0
    for _ in range(19):
        mid = (lower + upper) / 2
        trial = rectangular_field_of_view_mask((h, w), width_fraction=mid,
                                                height_fraction=1.0, center_x_fraction=.5)
        actual = float(np.mean(overlap_mask_in_fixed_space(trial, gt, fixed_shape=(h,w))))
        if actual < target:
            lower = mid
        else:
            upper = mid
    valid = rectangular_field_of_view_mask((h, w), width_fraction=(lower + upper)/2,
                                           height_fraction=1.0, center_x_fraction=.5)
    actual = float(np.mean(overlap_mask_in_fixed_space(valid, gt, fixed_shape=(h,w))))
    if abs(actual - target) > .04:
        raise ValueError(f'Combined overlap target not achieved: {actual:.4f} vs {target}')
    return apply_field_of_view(moving, valid), valid


def prepare_combined_pair(pair: BenchmarkPairSpec, fixed: np.ndarray) -> PreparedSweepPair:
    """Apply two appearance stresses to the same known geometry.

    Uses Day 32 clean synthetic generation, then a separately seeded appearance
    chain. No transform is altered by blur/noise/occlusion/texture/modality changes.
    """
    meta = pair.metadata
    if (meta.get('split') != 'development' or meta.get('combined_version') != VERSION
            or meta.get('geometry_seed') not in GEOMETRY_SEEDS
            or meta.get('transform_direction') != 'moving_to_fixed'):
        raise ValueError('Not a declared Day 35 development case')
    label = meta['combined_label']
    factors = tuple(meta['combined_factors'])
    if label not in COMBINATIONS or factors != COMBINATIONS[label]:
        raise ValueError('Combined stress labels/factors do not match frozen design')
    if (pair.modality_class == 'simulated_multimodal') != (label in MULTI):
        raise ValueError('Mismatch between modality and stress family')
    clean = BenchmarkPairSpec(pair_id=pair.pair_id + '_geometry_only',
        modality_class='monomodal', transform_model=pair.transform_model, degradation='none',
        reference=ReferenceEvidence(exact_transform=True),
        metadata={'split': 'development', 'geometry_seed': meta['geometry_seed'], 'condition_parameters': {}})
    base = prepare_sweep_pair(clean, fixed)
    moving = np.array(base.moving, copy=True)
    valid = np.ones(moving.shape, dtype=np.uint8)
    if label == 'noise_blur':
        moving = gaussian_noise(moving, sigma_fraction=.025, rng=_rng(pair.pair_id, 'noise'))
        moving = gaussian_blur(moving, sigma=1.5)
    elif label == 'blur_occlusion':
        moving = gaussian_blur(moving, sigma=1.5)
        moving, valid, _ = rectangular_occlusion(moving, area_fraction=.25, rng=_rng(pair.pair_id, 'occlusion'))
    elif label == 'overlap_illumination':
        moving, valid = _restrict_overlap(moving, base.ground_truth, .65)
        moving = adjust_gamma(moving, gamma=1.5)
        moving[valid == 0] = 0
    elif label == 'texture_repetition':
        moving = np.rint(.45 * moving.astype(float) + .55 * moving.mean()).clip(0,255).astype(np.uint8)
        yy, xx = np.indices(moving.shape)
        stripes = ((xx // 10) % 2) * 180.0 + 35.0
        moving = np.rint(.65 * moving.astype(float) + .35 * stripes).clip(0,255).astype(np.uint8)
    elif label == 'modality_noise':
        moving = intensity_inversion(moving)
        moving = gaussian_noise(moving, sigma_fraction=.025, rng=_rng(pair.pair_id, 'noise'))
    elif label == 'modality_blur':
        moving = histogram_remap(moving, input_knots=[0,.25,.5,.75,1],
                                 output_knots=[0,.08,.56,.92,1])
        moving = gaussian_blur(moving, sigma=1.5)
    else:
        raise AssertionError('Unhandled stress')
    if moving.shape != fixed.shape or moving.dtype != np.uint8 or not np.isfinite(moving).all():
        raise AssertionError('Invalid generated appearance')
    gt = base.ground_truth
    reference = overlap_mask_in_fixed_space(valid, gt, fixed_shape=fixed.shape)
    fraction = float(np.mean(reference))
    if fraction < 0.1:
        raise ValueError('Insufficient reference support for combined stress')
    # Explicit offline geometry identity check. Registration never receives this GT.
    if not np.allclose(gt @ np.linalg.inv(gt), np.eye(3), atol=1e-9):
        raise AssertionError('Inconsistent Moving -> Fixed geometry')
    return PreparedSweepPair(base.fixed, moving, gt, base.moving_points, valid, reference,
        {'combined_version': VERSION, 'combined_label': label, 'combined_factors': factors,
         'reference_valid_overlap_fraction': fraction,
         'geometry_seed': meta['geometry_seed'], 'heldout_pixels_loaded': False})


def combined_summary(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for e in records:
        task, r = e['task'], e['record']
        if task.get('pair_metadata', {}).get('split') != 'development':
            raise ValueError('Combined summary rejects non-development records')
        key = (task['pair_metadata']['combined_label'], task['transform_model'], task['modality_class'], task['method_id'])
        groups[key].append(r)
    rows=[]
    for (label, model, modality, method), results in sorted(groups.items()):
        t = [float(r['metrics']['tre_mean_px']) for r in results if r.get('metrics', {}).get('tre_mean_px') is not None]
        tm = [float(r['timings_ms']['total']) for r in results if r.get('timings_ms', {}).get('total') is not None]
        rows.append({'combined_label': label, 'model': model, 'modality': modality, 'method_id': method,
            'attempts':len(results),'correct':sum(r['geometric_within_tolerance'] is True for r in results),
            'completed':sum(r['execution_status']=='completed' for r in results),
            'check':sum(r['execution_status']=='check' for r in results),
            'failed':sum(r['execution_status'] in {'failed','validation_error'} for r in results),
            'median_tre_estimated_px': None if not t else round(float(np.median(t)),5),
            'median_runtime_ms': None if not tm else round(float(np.median(tm)),3)})
    return rows


def evaluate_frozen_gate(records: list[dict], frozen_policy: Mapping[str, Any]) -> tuple[list[dict], dict]:
    if (frozen_policy.get('status') != 'exploratory_not_deployed'
            or frozen_policy.get('independent_validation') is not False):
        raise ValueError('Only the original non-deployed Day 34 policy is admissible')
    values = frozen_policy.get('gate')
    if not isinstance(values, dict) or set(values) != set(Gate.__dataclass_fields__):
        raise ValueError('Expected the exact Day 34 frozen gate fields')
    gate = Gate(**values)
    decisions, stats = offline_evaluate(records, gate)
    if stats['pairs'] != len({e['task']['pair_id'] for e in records}):
        raise AssertionError('Pair count disagrees')
    return decisions, stats


def failure_review(records: list[dict], *, max_cases: int = 18) -> list[dict]:
    """Deterministic stratified review candidate list; these are NOT automatic diagnoses."""
    buckets=defaultdict(list)
    for e in records:
        task, record=e['task'],e['record']
        status=record['execution_status']
        if status in {'failed', 'validation_error'}:
            category='execution_failure'
        elif status=='check':
            category='check'
        elif record['geometric_within_tolerance'] is False:
            category='wrong_geometry'
        else:
            continue
        buckets[(task['pair_metadata']['combined_label'], category)].append(e)
    chosen=[]
    for key in sorted(buckets):
        for item in sorted(buckets[key], key=lambda x:x['experiment_id'])[:2]:
            r=item['record'];chosen.append({'experiment_id':item['experiment_id'], 'pair_id':item['task']['pair_id'],
                'combined_label':key[0], 'review_category':key[1], 'method':item['task']['method_id'],
                'reason':r.get('failure_reason'), 'tre_mean_px':r.get('metrics',{}).get('tre_mean_px'),
                'execution_status':r['execution_status']})
    return chosen[:max_cases]


def recommendations(records: list[dict]) -> list[dict]:
    """At least four evidence-informed handling rules, never universal rankings."""
    explanations = {
        'noise_blur': 'Report acquisition quality and inspect registration TRE on clean-reference synthetic data; do not infer robustness from execution alone.',
        'blur_occlusion': 'Inspect valid masks and reject implausible transforms; preserve optimizer and correspondence failures when occlusion accompanies blur.',
        'overlap_illumination': 'Explicitly record actual reference overlap and illumination changes; abstain when candidate evidence is insufficient.',
        'texture_repetition': 'Inspect feature-match count, spatial distribution and RANSAC inliers; repetitive/weak texture can create ambiguous matches.',
        'modality_noise': 'Treat simulated multimodal behavior as its own stratum; do not compare raw ECC and MI objectives or assume monomodal thresholds transfer.',
        'modality_blur': 'Evaluate MI termination and overlap for simulated multimodal blurred pairs; retain failures and avoid automatic cross-modality recommendations.',
    }
    rows=[]
    for label in sorted(explanations):
        sub=[x for x in records if x['task']['pair_metadata']['combined_label']==label]
        n=len(sub); correct=sum(x['record']['geometric_within_tolerance'] is True for x in sub)
        rows.append({'condition':label, 'attempts':n,'geometric_successes':correct,
                    'geometric_failure_count':n-correct, 'observed_success_rate':round(correct/n,6) if n else None,
                    'conservative_guidance':explanations[label],
                    'scope':'Day 35 small synthetic development subset; not a universal method recommendation'})
    return rows
