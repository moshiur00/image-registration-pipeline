"""Day 34 firewall, 3-family agreement, abstention and audit-isolation tests."""
from __future__ import annotations

import copy
from dataclasses import asdict
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import numpy as np
import pytest

from image_registration.week7_calibration import (
    VERSION, OBSERVABLE_KEYS, Gate, eligible, project_observables, transfer_distance,
    select_pair, offline_evaluate, records_by_pair, summarize_decisions,
    signal_table, wilson_interval,
)

ROOT = Path(__file__).resolve().parents[1]


def example(method: str, family: str, tx: float = 1., *, true: bool = True,
            seed: int = 7, status: str = 'completed', pair_id: str = 'p1') -> dict:
    raw = {'preparation': {'fixed_source': {'shape': [192, 192]}}}
    if family == 'feature_based':
        raw.update(ransac_inlier_ratio=.9, fixed_match_coverage=.6,
                   moving_match_coverage=.5, ransac_inliers=20)
    if family == 'intensity_based':
        raw.update(final_ecc=.93, levels_completed=3)
    if family == 'mutual_information':
        raw.update(final_metric_value=-1.3, optimizer_stop_condition='Step too small',
                   valid_metric_points=20000)
    if family == 'frequency_domain':
        raw.update(response=.75)
    return {
        'experiment_id': method,
        'task': {'experiment_id': method, 'pair_id': pair_id, 'method_id': method,
                 'method_family': family, 'modality_class': 'monomodal',
                 'transform_model': 'affine', 'degradation': 'occlusion',
                 'pair_metadata': {'split': 'development', 'geometry_seed': seed,
                                   'condition_parameters': {'area_fraction': .4}}},
        'record': {'pair_id': pair_id, 'method_id': method, 'method_family': family,
                   'modality_class': 'monomodal', 'transform_model': 'affine',
                   'execution_status': status, 'transform_plausible': True,
                   'estimated_transform': [[1,0,tx],[0,1,0],[0,0,1]],
                   'valid_overlap_fraction': .9, 'method_diagnostics': {
                       'raw': raw, 'offline_reference_overlap_fraction': .91},
                   'geometric_within_tolerance': true,
                   'metrics': {'tre_mean_px': 0.1 if true else 100},
                   'reference': {'exact_transform': True}},
    }


def examples(tx=1., *, true=True):
    return [example('ecc_affine','intensity_based',tx,true=true),
            example('mi_affine','mutual_information',tx,true=true),
            example('orb_affine','feature_based',tx,true=true)]


def script():
    p=ROOT/'scripts/week07_day04_offline_calibration.py'
    spec=spec_from_file_location('day34_calibration_cli',p)
    assert spec and spec.loader
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_explicit_allowlist_never_includes_reference():
    o=project_observables(example('orb_affine','feature_based'))
    assert set(o) == OBSERVABLE_KEYS
    assert not {'metrics','tre','truth','severity','degradation','seed','offline_reference_overlap_fraction'} & set(o)
    assert o['shape_hw'] == [192,192]


def test_changing_ground_truth_and_synthetic_severity_cannot_change_gate():
    a=examples()
    b=copy.deepcopy(a)
    for v in b:
        v['record']['geometric_within_tolerance']=False
        v['record']['metrics']['tre_mean_px']=99999
        v['record']['reference']={'secret': {'ground_truth_transform': [1,2,3]}}
        v['record']['method_diagnostics']['offline_reference_overlap_fraction']=0
        v['task']['degradation']='repeated_pattern'
        v['task']['pair_metadata']['condition_parameters']={'secret_truth': 100}
    oa=[project_observables(x) for x in a]
    ob=[project_observables(x) for x in b]
    assert oa == ob
    assert select_pair(oa,Gate()) == select_pair(ob,Gate())


def test_three_distinct_families_agree_then_tentative_support():
    out=select_pair([project_observables(x) for x in examples()],Gate())
    assert out['decision']=='tentative_supported'
    assert len(set(out['support_families']))==3
    assert out['selected_id']=='ecc_affine'  # deterministic tie break


def test_one_method_always_abstains():
    out=select_pair([project_observables(examples()[0])], Gate())
    assert out['decision']=='abstain'


def test_two_different_families_always_abstain_even_when_identical():
    out=select_pair([project_observables(x) for x in examples()[:2]], Gate())
    assert out['decision']=='abstain'


def test_three_feature_methods_do_not_fake_three_family_support():
    out=select_pair([project_observables(example(f'orb{i}','feature_based')) for i in range(3)], Gate())
    assert out['decision']=='abstain'


def test_jointly_wrong_consensus_does_not_mean_true_geometry():
    records=examples(tx=60.,true=False)
    decisions, summary=offline_evaluate(records,Gate())
    assert decisions[0]['decision']=='tentative_supported'
    assert decisions[0]['selected_geometrically_correct_offline'] is False
    assert summary['incorrect_selected']==1


def test_disagreeing_independent_families_abstain():
    x=examples()
    x[2]['record']['estimated_transform'][0][2]=40
    assert select_pair([project_observables(v) for v in x],Gate())['decision']=='abstain'


def test_failed_and_check_are_excluded_not_false_consensus():
    x=examples()
    x[1]['record']['execution_status']='check'
    x[2]['record']['execution_status']='failed'
    dec, stats=offline_evaluate(x,Gate())
    assert dec[0]['decision']=='abstain' and stats['pairs']==1


def test_implausible_candidate_excluded():
    x=examples()
    x[0]['record']['transform_plausible']=False
    assert select_pair([project_observables(v) for v in x],Gate())['decision']=='abstain'


def test_overlap_is_observed_not_gt_and_absent_abstains():
    x=examples()
    x[0]['record']['valid_overlap_fraction']=None
    assert not eligible(project_observables(x[0]),Gate())
    assert select_pair([project_observables(v) for v in x],Gate())['decision']=='abstain'


def test_feature_inlier_or_coverage_gates():
    x=example('orb','feature_based')
    x['record']['method_diagnostics']['raw']['ransac_inlier_ratio']=.05
    assert not eligible(project_observables(x),Gate())
    x['record']['method_diagnostics']['raw']['ransac_inlier_ratio']=.8
    x['record']['method_diagnostics']['raw']['fixed_match_coverage']=.02
    assert not eligible(project_observables(x),Gate())


def test_mi_missing_termination_diagnostic_abstains():
    x=example('mi','mutual_information')
    x['record']['method_diagnostics']['raw'].pop('optimizer_stop_condition')
    assert not eligible(project_observables(x),Gate())


def test_normalized_difference_is_not_ground_truth_error():
    a,b=examples()[0],examples()[1]
    assert transfer_distance(project_observables(a),project_observables(b))==0.
    b['record']['estimated_transform'][0][2]+=3
    assert transfer_distance(project_observables(a),project_observables(b))==pytest.approx(3.)


def test_mismatched_image_dimensions_cannot_be_compared():
    x=examples()
    x[0]['record']['method_diagnostics']['raw']['preparation']['fixed_source']['shape']=[128,128]
    assert transfer_distance(project_observables(x[0]),project_observables(x[1])) is None
    assert select_pair([project_observables(v) for v in x],Gate())['decision']=='abstain'


def test_no_cross_pair_comparison_allowed():
    x=examples();x[-1]['record']['pair_id']='other'
    with pytest.raises(ValueError,match='pair IDs'):
        select_pair([project_observables(v) for v in x],Gate())


def test_no_final_holdout_inputs():
    x=examples(); x[1]['task']['pair_metadata']['split']='final_holdout'
    with pytest.raises(ValueError,match='Non-development'):
        records_by_pair(x)


def test_wilson_missing_or_too_small_sample():
    assert wilson_interval(0,0)==(None,None)
    lo,hi=wilson_interval(10,10)
    assert 0<lo<1 and hi==1
    with pytest.raises(ValueError):
        wilson_interval(5,4)


def test_summary_counts_abstentions_in_denominator():
    rows,summary=offline_evaluate(examples()+[example('alone','intensity_based',pair_id='p2')],Gate())
    assert summary['pairs']==2 and summary['tentatively_supported']==1
    assert summary['abstained']==1 and summary['coverage']==.5


def test_signal_table_is_family_specific():
    sig=signal_table(examples())
    assert any(x['signal']=='ecc_final_value' for x in sig)
    assert any(x['signal']=='mi_stop_reported' for x in sig)
    assert any(x['signal']=='feature_inlier_ratio' for x in sig)
    assert not any(x['signal']=='ecc_final_value' and x['method_family']=='mutual_information' for x in sig)


def test_gate_parameter_validation():
    for kwargs in ({'agreement_px':0},{'overlap_floor':1.1},{'min_distinct_families':2},{'min_candidates':2}):
        with pytest.raises(ValueError):
            Gate(**kwargs)


def test_sweep_choice_does_not_use_audit_precision(monkeypatch):
    module=script()
    fake=[]
    def mock_offline(records, gate):
        # 324 train rows all successful; audit rows change with marker; gates see same train.
        train=[{'seed':7,'decision':'tentative_supported','reason':'three_family_agreement',
                'selected_geometrically_correct_offline':True} for _ in range(33)]
        train += [{'seed':42,'decision':'abstain','reason':'no_support','selected_geometrically_correct_offline':None} for _ in range(291)]
        audit=[{'seed':101,'decision':'tentative_supported','reason':'three_family_agreement',
                'selected_geometrically_correct_offline': bool(records)} for _ in range(18)]
        return train+audit, {}
    monkeypatch.setattr(module,'offline_evaluate',mock_offline)
    _,a=module.sweep([]);_,b=module.sweep([1]);assert a==b


def test_outputs_document_non_deployed_policy():
    assert 'offline_calibration' in VERSION
    assert script().TUNING_RULE['fallback'].startswith('no provisional gate')


def test_script_rejects_output_inside_source(tmp_path):
    with pytest.raises(ValueError, match='Output must not overwrite'):
        script().run(tmp_path, tmp_path/'nested')


def test_invalid_transform_and_nonfinite_input_do_not_count_as_agreement():
    x=examples()
    x[0]['record']['estimated_transform'][0][0]=float('nan')
    o=project_observables(x[0])
    assert o['transform'] is None
    assert select_pair([project_observables(v) for v in x],Gate())['decision']=='abstain'


def test_offline_evaluation_does_not_mutate_source_records():
    records=examples()
    before=copy.deepcopy(records)
    offline_evaluate(records,Gate())
    assert records == before
