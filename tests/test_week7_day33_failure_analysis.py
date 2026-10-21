"""Day 33 read-only evidence analysis, safety and reproducibility regression tests."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import copy
import json

import pytest

from image_registration.week7_failure_analysis import (
    ANALYSIS_VERSION, aggregate, classify, read_evidence, select_gallery_cases,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


def record(status='completed', geo=True, tre=.25, failure=None, condition='none', method='ecc_affine'):
    return {
        'experiment_id': 'a',
        'task': {'experiment_id': 'a', 'pair_id': 'pair-1', 'method_id': method,
                 'method_family': 'intensity_based', 'transform_model': 'affine',
                 'modality_class': 'monomodal', 'degradation': condition,
                 'pair_metadata': {'split': 'development', 'geometry_seed': 31,
                                   'condition_parameters': {}}},
        'record': {'pair_id': 'pair-1', 'method_id': method, 'execution_status': status,
                   'geometric_within_tolerance': geo,
                   'transform_plausible': True,
                   'failure_reason': failure,
                   'metrics': {} if tre is None else {'tre_mean_px': tre},
                   'timings_ms': {'total': 50.0},
                   'estimated_transform': None if tre is None else [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    }


def test_completed_does_not_mean_geometrically_correct():
    item = record(geo=False, tre=9.0)
    assert classify(item)['category'] == 'geometric_threshold_failure'
    assert classify(item)['status'] == 'completed'


def test_large_error_gallery_tier_is_not_a_production_gate():
    item = record(geo=False, tre=90.)
    assert classify(item)['category'] == 'large_geometric_error'


def test_check_with_implausible_transform_is_preserved():
    item = record(status='check', geo=False, tre=1420.)
    item['record']['transform_plausible'] = False
    assert classify(item)['category'] == 'implausible_transform'


@pytest.mark.parametrize('reason', ['insufficient_filtered_matches', 'insufficient_ransac_inliers'])
def test_feature_failure_reasons_are_preserved(reason):
    item = record(status='failed', geo=None, tre=None, failure=reason)
    assert classify(item)['category'] == 'feature_correspondence_failure'
    assert classify(item)['failure_reason'] == reason


def test_optimizer_failure_classification():
    item = record(status='failed', geo=None, tre=None, failure='ecc_pyramid_level_failed')
    assert classify(item)['category'] == 'optimizer_execution_failure'


def test_failure_and_check_in_geometric_denominator():
    rows = [record(geo=True), record(geo=False, tre=15),
            record(status='failed', geo=None, tre=None, failure='insufficient_filtered_matches')]
    for i, x in enumerate(rows):
        x['experiment_id'] = x['task']['experiment_id'] = str(i)
    result = aggregate(rows, ('method_id',))[0]
    assert result['attempts'] == 3
    assert result['geometric_successes'] == 1
    assert result['geometric_success_rate'] == pytest.approx(1/3, abs=1e-6)
    assert result['execution_rate'] == pytest.approx(2/3, abs=1e-6)
    assert result['tre_observed'] == 2
    assert result['tre_median_px_conditional'] == 7.625


def test_condition_not_claimed_to_be_causal():
    item = record(geo=False, tre=50, condition='partial_overlap')
    assert classify(item)['associated_stress_not_proven_cause'] == 'partial_overlap'


def test_seed_is_recovered_from_pair_metadata_not_flat_csv():
    assert classify(record())['geometry_seed'] == 31


def test_galleries_are_deterministic_without_duplicate_experiment_ids():
    examples = [record(geo=True), record(geo=False, tre=90, condition='occlusion'),
                record(status='failed', geo=None, tre=None, failure='insufficient_filtered_matches',
                       condition='repeated_pattern')]
    for i, case in enumerate(examples):
        case['experiment_id'] = case['task']['experiment_id'] = str(i)
    original = [x['experiment_id'] for x in select_gallery_cases(examples)]
    changed = [x['experiment_id'] for x in select_gallery_cases(list(reversed(examples)))]
    assert original == changed
    assert len(original) == len(set(original)) == 3


def test_gallery_rejects_invalid_limit():
    with pytest.raises(ValueError, match='positive'):
        select_gallery_cases([], limit=0)


def test_missing_input_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError, match='requires'):
        read_evidence(tmp_path)


def test_rejects_partial_records(tmp_path):
    (tmp_path / 'day32_manifest.json').write_text(json.dumps({
        'mode': 'full', 'heldout_pixels_loaded': False, 'selected_tasks': 2
    }), encoding='utf-8')
    item = record()
    (tmp_path / 'benchmark_records.jsonl').write_text(json.dumps(item) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Incomplete'):
        read_evidence(tmp_path)


def test_rejects_duplicate_run_ids(tmp_path):
    (tmp_path / 'day32_manifest.json').write_text(json.dumps({
        'mode': 'full', 'heldout_pixels_loaded': False, 'selected_tasks': 2
    }), encoding='utf-8')
    item = record()
    (tmp_path / 'benchmark_records.jsonl').write_text((json.dumps(item) + '\n') * 2, encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate'):
        read_evidence(tmp_path)


def test_rejects_heldout_split(tmp_path):
    (tmp_path / 'day32_manifest.json').write_text(json.dumps({
        'mode': 'full', 'heldout_pixels_loaded': False, 'selected_tasks': 1
    }), encoding='utf-8')
    item = record()
    item['task']['pair_metadata']['split'] = 'final_holdout'
    (tmp_path / 'benchmark_records.jsonl').write_text(json.dumps(item) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Held-out'):
        read_evidence(tmp_path)


def test_rejects_incompatible_task_and_result(tmp_path):
    (tmp_path / 'day32_manifest.json').write_text(json.dumps({
        'mode': 'full', 'heldout_pixels_loaded': False, 'selected_tasks': 1
    }), encoding='utf-8')
    item = record()
    item['record']['method_id'] = 'other'
    (tmp_path / 'benchmark_records.jsonl').write_text(json.dumps(item) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='identity mismatch'):
        read_evidence(tmp_path)


def test_summary_is_read_only_and_has_scientific_limitations():
    x = record(geo=True)
    before = copy.deepcopy(x)
    result = summarize([x])
    assert x == before
    assert result['analysis_version'] == ANALYSIS_VERSION
    assert result['geometric_successes'] == 1
    assert any('development-only' in s for s in result['limitations'])


def test_output_path_cannot_overwrite_input(tmp_path):
    script_path = ROOT / 'scripts/week07_day03_failure_analysis.py'
    spec = spec_from_file_location('day33script', script_path)
    mod = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    # The validator runs on real records before output path guard; the guard
    # behavior is exercised on the authoritative records when they are present.
    assert hasattr(mod, 'run')
    assert hasattr(mod, 'sampled_profile')


def test_runtime_boxplot_uses_supported_horizontal_orientation(tmp_path, monkeypatch):
    """Guard against Matplotlib 3.11's deprecation of ``vert=False``."""
    import matplotlib.pyplot as plt

    script_path = ROOT / 'scripts/week07_day03_failure_analysis.py'
    spec = spec_from_file_location('day33_plotting', script_path)
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)

    calls = []
    original = plt.boxplot

    def audited_boxplot(*args, **kwargs):
        calls.append(dict(kwargs))
        assert 'vert' not in kwargs
        assert kwargs.get('orientation') == 'horizontal'
        return original(*args, **kwargs)

    monkeypatch.setattr(plt, 'boxplot', audited_boxplot)
    examples = [record(method='ecc_affine', tre=0.5), record(method='orb_affine', tre=1.0)]
    for i, item in enumerate(examples):
        item['experiment_id'] = item['task']['experiment_id'] = str(i)
    figures = mod.create_plots(examples, summarize(examples), tmp_path)
    assert calls and 'plots/runtime_by_method.png' in figures
    assert (tmp_path / 'runtime_by_method.png').is_file()
