"""Focused controlled-combination, offline policy and Week 7 handoff tests."""
from __future__ import annotations
import copy
from importlib.util import spec_from_file_location, module_from_spec
import json
from pathlib import Path

import numpy as np
import pytest

from image_registration.week7_integration import (
    COMBINATIONS, GEOMETRY_SEEDS, MONO, MULTI, MODELS, VERSION,
    specifications, prepare_combined_pair, combined_summary, failure_review,
    evaluate_frozen_gate, recommendations,
)
from image_registration.week7_calibration import Gate, select_pair, project_observables

ROOT=Path(__file__).resolve().parents[1]


def fixed():
    y,x=np.indices((96,96));a=(np.sin(x/3.0)*36+np.cos(y/5.0)*40+100).clip(0,255).astype(np.uint8)
    a[15:40,12:32]=220;a[54:75,53:83]=10
    return a


def pairs():return specifications('a'*64)


def script():
    p=ROOT/'scripts/week07_day05_integrated_validation.py'
    spec=spec_from_file_location('day35_runner',p)
    assert spec and spec.loader
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_grid_complete_unique_and_seeds_not_tuned():
    out=pairs(); assert len(out)==40 and len({x.pair_id for x in out})==40
    assert not set(GEOMETRY_SEEDS)&{7,42,101}
    assert len([x for x in out if x.modality_class=='simulated_multimodal'])==8


def test_specs_never_contain_heldout():
    for p in pairs():
        assert p.metadata['split']=='development'
        assert 'heldout' not in json.dumps(p.metadata).lower()
        assert p.degradation=='combined_stress' and p.reference.exact_transform
        assert len(p.metadata['combined_factors'])==2


@pytest.mark.parametrize('label',list(COMBINATIONS))
def test_each_combination_prepared_and_same_shape(label):
    pair=next(p for p in pairs() if p.metadata['combined_label']==label)
    result=prepare_combined_pair(pair,fixed())
    assert result.fixed.shape==result.moving.shape==(96,96)
    assert result.fixed.dtype==result.moving.dtype==np.uint8
    assert result.metadata['heldout_pixels_loaded'] is False
    assert 0<result.metadata['reference_valid_overlap_fraction']<=1


def test_deterministic_repeats_bitwise_identical():
    p=next(x for x in pairs() if x.metadata['combined_label']=='blur_occlusion')
    a=prepare_combined_pair(p,fixed());b=prepare_combined_pair(p,fixed())
    assert np.array_equal(a.moving,b.moving)
    assert np.array_equal(a.ground_truth,b.ground_truth)
    assert np.array_equal(a.valid_mask_moving,b.valid_mask_moving)


def test_different_seed_changes_geometry():
    group=[p for p in pairs() if p.metadata['combined_label']=='noise_blur' and p.transform_model=='affine']
    a,b=[prepare_combined_pair(p,fixed()) for p in group]
    assert not np.allclose(a.ground_truth,b.ground_truth)


def test_same_seed_different_conditions_identical_geometry():
    group=[p for p in pairs() if p.metadata['geometry_seed']==202 and p.transform_model=='affine' and p.modality_class=='monomodal']
    matrices=[prepare_combined_pair(x,fixed()).ground_truth for x in group]
    assert all(np.allclose(matrices[0],x) for x in matrices[1:])


def test_overlap_is_measured_not_black_pixel_estimate():
    p=next(x for x in pairs() if x.metadata['combined_label']=='overlap_illumination')
    prep=prepare_combined_pair(p,fixed());assert abs(prep.metadata['reference_valid_overlap_fraction']-.65)<.04
    assert prep.valid_mask_moving.dtype==np.uint8


def test_tampered_combination_rejected():
    p=pairs()[0];from image_registration.benchmark_runner import BenchmarkPairSpec
    v=BenchmarkPairSpec(pair_id=p.pair_id,modality_class=p.modality_class,transform_model=p.transform_model,
        degradation=p.degradation,reference=p.reference,metadata={**p.metadata,'combined_factors':['none','none']})
    with pytest.raises(ValueError):prepare_combined_pair(v,fixed())


def test_heldout_split_rejected_before_synthesis():
    p=pairs()[0];from image_registration.benchmark_runner import BenchmarkPairSpec
    v=BenchmarkPairSpec(pair_id=p.pair_id,modality_class=p.modality_class,transform_model=p.transform_model,
        degradation=p.degradation,reference=p.reference,metadata={**p.metadata,'split':'heldout'})
    with pytest.raises(ValueError):prepare_combined_pair(v,fixed())


def test_wrong_hash_rejected():
    with pytest.raises(ValueError):specifications('not_sha256')


def test_frozen_gate_rejects_pretend_validated_policy():
    with pytest.raises(ValueError):evaluate_frozen_gate([],{'status':'production','independent_validation':True})


def test_frozen_gate_rejects_partial_fields():
    with pytest.raises(ValueError):evaluate_frozen_gate([],
        {'status':'exploratory_not_deployed','independent_validation':False,'gate':{'agreement_px':2}})


def test_summary_all_statuses_counted():
    p=pairs()[0]
    records=[]
    for i,status in enumerate(('completed','check','failed')):
        records.append({'experiment_id':str(i),
            'task':{'pair_id':p.pair_id,'method_id':'mi_affine_2d','transform_model':p.transform_model,
                    'modality_class':p.modality_class,'pair_metadata':p.metadata},
            'record':{'execution_status':status,'geometric_within_tolerance':i==0,
                'metrics':{'tre_mean_px':.2} if i==0 else {},'timings_ms':{'total':23}}})
    summary=combined_summary(records)
    assert len(summary)==1 and summary[0]['attempts']==3
    assert (summary[0]['completed'],summary[0]['check'],summary[0]['failed'],summary[0]['correct'])==(1,1,1,1)


def test_failure_review_preserves_execution_failed():
    p=pairs()[0]
    row={'experiment_id':'x','task':{'pair_id':'p','method_id':'orb_affine','pair_metadata':p.metadata},
         'record':{'execution_status':'failed','failure_reason':'insufficient_filtered_matches',
                   'geometric_within_tolerance':None,'metrics':{}}}
    out=failure_review([row]);assert out and out[0]['review_category']=='execution_failure'


def test_four_or_more_specific_recommendations():
    rows=recommendations([])
    assert len(rows)>=4 and len({r['condition'] for r in rows})==len(rows)
    assert all('not a universal' in r['scope'] for r in rows)


def test_comparison_study_denominators_are_separate():
    s=script()
    def record(name, success):
        return {'task':{'transform_model':'affine','modality_class':'monomodal','method_id':'m'},
          'record':{'execution_status':'completed','geometric_within_tolerance':success,
                    'metrics':{},'timings_ms':{'total':5}}}
    r=s.comparison_matrices([record('a',True)],[record('b',False)])
    assert len(r)==2 and {x['study'] for x in r}=={'day32_one_factor','day35_combined'}


def test_source_evidence_and_policy_hashes_match_in_bundled_data():
    policy=ROOT/'outputs/week07_day04_calibration/tentative_policy_not_for_ui.json'
    journal=ROOT/'outputs/week07_day02_full/benchmark_records.jsonl'
    if not policy.exists() or not journal.exists():pytest.skip('Optional generated benchmark evidence not bundled')
    import hashlib
    assert json.loads(policy.read_text())['source_sha256']==hashlib.sha256(journal.read_bytes()).hexdigest()


def test_cli_reproducibility_after_resume_and_no_duplicate_ids():
    p=ROOT/'outputs/week07_day05_integration/benchmark_plan.json'
    journal=ROOT/'outputs/week07_day05_integration/benchmark_records.jsonl'
    if not p.exists() or not journal.exists():pytest.skip('Optional local Day 35 evidence not bundled')
    plan=json.loads(p.read_text());records=[json.loads(x) for x in journal.read_text().splitlines() if x.strip()]
    assert len(records)==len(plan['tasks'])
    assert {x['experiment_id'] for x in records}=={x['experiment_id'] for x in plan['tasks']}
