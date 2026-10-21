"""Day 32 deterministic one-factor sweeps and reference-firewall regression tests."""
from __future__ import annotations

from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

from image_registration.benchmark_runner import BenchmarkPairSpec
from image_registration.config import load_config
from image_registration.evaluation_contracts import ReferenceEvidence
from image_registration.io import load_image
from image_registration.preprocessing import resize_image
from image_registration.week7_robustness import design_pairs, method_specs
from image_registration.week7_sweeps import prepare_sweep_pair, stratified_dry_run_pairs

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / 'configs/week07_day01_robustness_grid.yaml')
METHODS = method_specs(load_config(ROOT / 'configs/week07_day01_frozen_methods.yaml'), 'a' * 64)
SOURCE = np.asarray(resize_image(load_image(ROOT / CONFIG['sources']['development'], color_mode='grayscale').array,
                                 (96, 96), interpolation='area'))


def script():
    path = ROOT / 'scripts/week07_day02_robustness_sweeps.py'
    spec = spec_from_file_location('week07_day02_robustness_sweeps', path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_compatible():
    planned = design_pairs(CONFIG, 'a' * 64)
    return [p for p in planned if any(m.supports(p) for m in METHODS)]


def selected():
    return script().valid_sweep_pairs(all_compatible())[0]


def test_geometry_incompatible_conditions_are_explicitly_excluded():
    included, excluded = script().valid_sweep_pairs(all_compatible())
    assert len(all_compatible()) == 522
    assert len(excluded) == 36
    assert len(included) + len(excluded) == 522
    assert {x['reason'] for x in excluded} == {
        'rotation_requires_rigid_or_more_complex_model',
        'scale_requires_similarity_or_affine_model',
    }


def test_dry_run_covers_all_planned_condition_families_and_models():
    chosen = stratified_dry_run_pairs(selected())
    assert len(chosen) == 16
    assert {p.degradation for p in chosen} == {'none', *CONFIG['grid']['conditions']}
    assert {p.transform_model for p in chosen} == set(CONFIG['grid']['transform_models'])
    assert {p.modality_class for p in chosen} == set(CONFIG['grid']['modality_classes'])
    assert chosen == stratified_dry_run_pairs(list(reversed(selected())))


@pytest.mark.parametrize('condition', ['gaussian_noise', 'gaussian_blur', 'rotation', 'scale',
                                    'illumination', 'occlusion', 'partial_overlap',
                                    'low_texture', 'repeated_pattern', 'multimodal_mapping', 'none'])
def test_preparation_preserves_exact_correspondence(condition):
    pair = next(p for p in selected() if p.degradation == condition)
    prepared = prepare_sweep_pair(pair, SOURCE)
    assert prepared.fixed.shape == SOURCE.shape == prepared.moving.shape
    assert prepared.reference_overlap_fixed.shape == SOURCE.shape
    assert np.all(np.isfinite(prepared.ground_truth))
    assert prepared.metadata['reference_control_point_round_trip_max_px'] < 1e-8
    assert prepared.metadata['reference_matrix_inverse_max_error'] < 1e-10
    assert 0 < prepared.metadata['reference_valid_overlap_fraction'] <= 1


def test_deterministic_degradation_independent_of_global_rng():
    pair = next(p for p in selected() if p.degradation == 'gaussian_noise')
    np.random.seed(101)
    left = prepare_sweep_pair(pair, SOURCE)
    np.random.seed(23)
    right = prepare_sweep_pair(pair, SOURCE)
    assert np.array_equal(left.moving, right.moving)
    assert np.array_equal(left.ground_truth, right.ground_truth)
    assert left.metadata == right.metadata


def test_individual_severity_levels_generate_distinct_data():
    cases = [p for p in selected() if p.degradation == 'gaussian_noise' and p.modality_class == 'monomodal']
    # distinct severity should not collapse to identical image data
    a = next(p for p in cases if p.metadata['condition_parameters']['sigma_fraction'] == .008)
    b = next(p for p in cases if p.metadata['condition_parameters']['sigma_fraction'] == .055)
    assert not np.array_equal(prepare_sweep_pair(a, SOURCE).moving, prepare_sweep_pair(b, SOURCE).moving)


@pytest.mark.parametrize('fraction', [.80, .65, .50])
def test_partial_overlap_matches_requested_geometric_fraction(fraction):
    pair = next(p for p in selected() if p.degradation == 'partial_overlap'
                and p.modality_class == 'monomodal'
                and p.transform_model == 'affine'
                and p.metadata['condition_parameters']['target_overlap'] == fraction)
    prepared = prepare_sweep_pair(pair, SOURCE)
    actual = float(np.mean(prepared.reference_overlap_fixed))
    assert abs(actual - fraction) < .03
    assert np.sum(prepared.valid_mask_moving == 0) > 0


def test_invalid_condition_level_is_rejected():
    pair = next(p for p in selected() if p.degradation == 'gaussian_noise')
    replacement = BenchmarkPairSpec(
        pair_id='negative', modality_class=pair.modality_class,
        transform_model=pair.transform_model, degradation=pair.degradation,
        reference=ReferenceEvidence(exact_transform=True),
        metadata={**pair.metadata, 'condition_parameters': {'sigma_fraction': float('nan')}},
    )
    with pytest.raises(ValueError, match='sigma_fraction'):
        prepare_sweep_pair(replacement, SOURCE)


def test_holdout_split_cannot_be_synthesized():
    pair = next(iter(selected()))
    replacement = BenchmarkPairSpec(
        pair_id='holdout', modality_class=pair.modality_class,
        transform_model=pair.transform_model, degradation=pair.degradation,
        reference=ReferenceEvidence(exact_transform=True),
        metadata={**pair.metadata, 'split': 'final_holdout'},
    )
    with pytest.raises(ValueError, match='development'):
        prepare_sweep_pair(replacement, SOURCE)


def test_aggregate_denominator_includes_failures_and_threshold_failures():
    def wrap(status, correct, tre):
        return {'task': {'modality_class': 'monomodal', 'transform_model': 'translation',
                         'degradation': 'gaussian_noise', 'method_id': 'ecc_translation',
                         'pair_metadata': {'condition_parameters': {'sigma_fraction': .008}}},
                'record': {'execution_status': status, 'geometric_within_tolerance': correct,
                           'metrics': {} if tre is None else {'tre_mean_px': tre},
                           'timings_ms': {'total': 25.0}}}
    rows = [wrap('completed', True, .5), wrap('failed', None, None), wrap('completed', False, 7.5)]
    result = script().aggregate_records(rows)
    assert len(result) == 1
    row = result[0]
    assert row['attempts'] == 3
    assert row['completed_or_check'] == 2
    assert row['failed_or_validation_error'] == 1
    assert row['geometric_successes'] == 1
    assert row['geometric_success_rate'] == pytest.approx(1 / 3, abs=1e-6)
    assert row['median_tre_px_on_estimated'] == 4.0


def test_attempt_identity_preserves_pair_method_and_seed_context():
    from image_registration.benchmark_runner import enumerate_benchmark_tasks
    chosen = stratified_dry_run_pairs(selected())
    tasks = enumerate_benchmark_tasks(chosen, METHODS, [None])
    assert len(tasks) == 49
    assert len({t.experiment_id for t in tasks}) == len(tasks)
    assert all(t.reference.exact_transform for t in tasks)
    counts = Counter(t.pair_id for t in tasks)
    assert max(counts.values()) >= 2


def test_registration_service_receives_no_offline_ground_truth(monkeypatch):
    from types import SimpleNamespace
    mod = script()
    pair = next(p for p in selected() if p.degradation == 'gaussian_noise' and p.transform_model == 'translation')
    from image_registration.benchmark_runner import enumerate_benchmark_tasks
    method = next(m for m in METHODS if m.method_id == 'ecc_translation')
    task = enumerate_benchmark_tasks([pair], [method], [None])[0]
    observed = []
    class Service:
        def run(self, request):
            observed.append(request)
            assert request.evaluation.ground_truth_status.value == 'unavailable'
            assert request.evaluation.ground_truth_transform is None
            return SimpleNamespace(run_status=SimpleNamespace(value='failed'), transform=None,
                                   registered_array=None, diagnostics=SimpleNamespace(values={}),
                                   warnings=[], failure_reason='intentional_test_failure')
    monkeypatch.setattr(mod, 'build_default_registration_service', lambda: Service())
    record = mod.execute_factory(CONFIG, [method], [pair], SOURCE)(task)
    assert len(observed) == 1
    assert record.execution_status.value == 'failed'
    assert record.failure_reason == 'intentional_test_failure'
    assert record.geometric_within_tolerance is None


def test_geometry_seed_changes_ground_truth_but_matched_conditions_reuse_geometry():
    candidates = [p for p in selected() if p.transform_model == 'affine' and p.modality_class == 'monomodal']
    noise_seed7 = next(p for p in candidates if p.degradation == 'gaussian_noise' and p.metadata['geometry_seed'] == 7)
    blur_seed7 = next(p for p in candidates if p.degradation == 'gaussian_blur' and p.metadata['geometry_seed'] == 7)
    noise_seed42 = next(p for p in candidates if p.degradation == 'gaussian_noise' and p.metadata['geometry_seed'] == 42)
    g7 = prepare_sweep_pair(noise_seed7, SOURCE).ground_truth
    assert np.array_equal(g7, prepare_sweep_pair(blur_seed7, SOURCE).ground_truth)
    assert not np.array_equal(g7, prepare_sweep_pair(noise_seed42, SOURCE).ground_truth)
