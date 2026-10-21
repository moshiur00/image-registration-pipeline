"""Day 35: combined stresses, reproducible Week 7 reports and offline policy handoff.

Run from repository root. No Week 8 data, policy tuning, backend changes or UI deployment.
The combined stress experiment is deliberately SMALL, deterministic and resumable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
for x in (str(ROOT/'src'),str(ROOT)):
    if x not in sys.path: sys.path.insert(0,x)

from image_registration.benchmark_runner import ResumableBenchmarkRunner, enumerate_benchmark_tasks  # noqa: E402
from image_registration.config import load_config  # noqa: E402
from image_registration.evaluation_contracts import ExecutionStatus, UnifiedEvaluationRecord  # noqa: E402
from image_registration.io import load_image  # noqa: E402
from image_registration.preprocessing import resize_image  # noqa: E402
from image_registration.overlap import overlap_mask_in_fixed_space  # noqa: E402
from image_registration.warping import warp_image  # noqa: E402
from image_registration.unified_metrics import (transform_tre, model_aware_parameter_errors,  # noqa: E402
    overlap_aware_descriptive_metrics)
from image_registration.week7_robustness import content_hash, method_specs, validate_design  # noqa: E402
from image_registration.week7_failure_analysis import read_evidence, classify  # noqa: E402
from image_registration.week7_integration import (VERSION, GEOMETRY_SEEDS, specifications,  # noqa: E402
    prepare_combined_pair, combined_summary, evaluate_frozen_gate, failure_review, recommendations)
from ui.adapters import build_default_registration_service  # noqa: E402
from ui.core.contracts import (ImageSource, PreprocessingSpec, RegistrationRequest, RegistrationSpec,  # noqa: E402
    EvaluationContext as UIEvaluationContext)
from ui.core.enums import SourceType, GroundTruthStatus, TransformModel, TransformUnits  # noqa: E402


def here(value: str) -> Path:
    p=Path(value)
    return p if p.is_absolute() else ROOT/p


def dump_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def dump_csv(p:Path, rows:list[dict]) -> None:
    p.parent.mkdir(parents=True,exist_ok=True)
    if not rows: raise ValueError(f'Empty table {p}')
    cols=sorted({k for row in rows for k in row})
    with p.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row[k],sort_keys=True) if isinstance(row.get(k),(dict,list)) else row.get(k)
                             for k in cols})


def executor_factory(pairs, methods, fixed, tolerance, bins):
    service=build_default_registration_service()
    by_pair={p.pair_id:p for p in pairs}
    by_config={m.config_id:m for m in methods}
    cache={}
    def execute(task):
        if task.pair_id not in cache:
            cache[task.pair_id]=prepare_combined_pair(by_pair[task.pair_id],fixed)
        prepared=cache[task.pair_id]
        parameters=dict(by_config[task.config_id].metadata['parameters'])
        request=RegistrationRequest(
            fixed=ImageSource(SourceType.ARRAY,'Day35 development fixed',array=prepared.fixed),
            moving=ImageSource(SourceType.ARRAY,'Day35 combined moving',array=prepared.moving),
            preprocessing=PreprocessingSpec(grayscale=True,resize_policy='none'),
            registration=RegistrationSpec(method_id=task.method_id,
                transform_model=TransformModel(task.transform_model),
                initialization=parameters.get('initialization'),parameters=parameters,
                interpolation=str(parameters.get('interpolation','bilinear'))),
            evaluation=UIEvaluationContext(ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                units=TransformUnits.PIXELS),request_id=task.experiment_id)
        start=perf_counter(); run=service.run(request);elapsed=(perf_counter()-start)*1000
        status=ExecutionStatus(run.run_status.value)
        estimated=None if run.transform is None else np.asarray(run.transform.matrix,dtype=np.float64)
        metrics={'total_runtime_ms':elapsed}
        warnings=list(run.warnings)
        overlap=None; success=None
        if estimated is not None and status in {ExecutionStatus.COMPLETED,ExecutionStatus.CHECK}:
            # Offline-only GT access occurs *after* the service call.
            tre=transform_tre(prepared.ground_truth,estimated,prepared.moving_points)['px']
            metrics.update(tre.to_metrics())
            metrics.update(model_aware_parameter_errors(prepared.ground_truth,estimated,
                                                         transform_model=task.transform_model))
            success=bool(tre.mean <= tolerance and run.transform.plausible)
            if run.registered_array is not None:
                estimated_mask=overlap_mask_in_fixed_space(prepared.valid_mask_moving,
                    estimated,fixed_shape=prepared.fixed.shape)
                if np.any(estimated_mask):
                    try:
                        desc=overlap_aware_descriptive_metrics(prepared.fixed,run.registered_array,
                            estimated_mask,mi_bins=bins)
                        metrics.update(desc);overlap=float(desc['valid_overlap_fraction'])
                    except ValueError as e:
                        warnings.append(f'descriptive_metric_unavailable: {e}')
        return UnifiedEvaluationRecord(
            pair_id=task.pair_id, method_id=task.method_id,method_family=task.method_family,
            transform_model=task.transform_model,modality_class=task.modality_class,
            dimensions=2,execution_status=status,reference=task.reference,
            valid_overlap_fraction=overlap,seed=task.seed,estimated_transform=estimated,
            transform_plausible=None if run.transform is None else run.transform.plausible,
            geometric_within_tolerance=success,metrics=metrics,timings_ms={'total':elapsed},
            method_diagnostics={'raw':run.diagnostics.values,
                'offline_reference_overlap_fraction':prepared.metadata['reference_valid_overlap_fraction'],
                'combined_version':VERSION},warnings=warnings,
            failure_reason=(run.failure_reason or 'registration_failed') if status in {
                ExecutionStatus.FAILED,ExecutionStatus.VALIDATION_ERROR} else None)
    return execute


def comparison_matrices(baseline:list[dict], combined:list[dict]) -> list[dict]:
    """Comparable experimental strata; combined stress has its own denominator."""
    by=defaultdict(list)
    for study,envs in [('day32_one_factor',baseline),('day35_combined',combined)]:
        for e in envs:
            t,r=e['task'],e['record']
            by[(study,t['transform_model'],t['modality_class'],t['method_id'])].append(r)
    out=[]
    for (study,model,modality,method),rs in sorted(by.items()):
        durations=[float(r['timings_ms']['total']) for r in rs if 'total' in r.get('timings_ms',{})]
        tr=[float(r['metrics']['tre_mean_px']) for r in rs if 'tre_mean_px' in r.get('metrics',{})]
        good=sum(r['geometric_within_tolerance'] is True for r in rs)
        out.append({'study':study,'model':model,'modality':modality,'method_id':method,
            'attempts':len(rs),'geometric_successes':good,
            'success_rate':round(good/len(rs),6),
            'median_runtime_ms':None if not durations else round(float(np.median(durations)),4),
            'median_tre_px_on_estimated':None if not tr else round(float(np.median(tr)),6),
            'failures_in_denominator':sum(r['execution_status'] in {'failed','validation_error'} for r in rs)})
    return out


def plots(out:Path,combined_rows:list[dict],baseline_rows:list[dict],decisions:list[dict]) -> list[str]:
    folder=out/'plots';folder.mkdir(exist_ok=True,parents=True)
    paths=[]
    def save(filename):
        plt.tight_layout();p=folder/filename;plt.savefig(p,dpi=145);plt.close();paths.append(str(p.relative_to(out)))
    by=defaultdict(list)
    for e in combined_rows:
        by[e['task']['pair_metadata']['combined_label']].append(e['record'])
    labels=sorted(by)
    n=[len(by[s]) for s in labels]
    rates=[100*sum(x['geometric_within_tolerance'] is True for x in by[s])/len(by[s]) for s in labels]
    plt.figure(figsize=(9,5));plt.barh(labels,rates)
    plt.xlim(0,105);plt.xlabel('Geometric success (%) including failures');plt.title('Day 35 combined-stress success by condition')
    for i,(r,k) in enumerate(zip(rates,n)):plt.text(min(98,r+1),i,str(k)+' attempts',fontsize=8,va='center')
    save('combined_condition_success.png')
    duration=defaultdict(list)
    for e in combined_rows:
        if 'total' in e['record'].get('timings_ms',{}):
            duration[e['task']['method_id']].append(float(e['record']['timings_ms']['total']))
    names=sorted(duration)
    plt.figure(figsize=(9,5));plt.boxplot([duration[x] for x in names],tick_labels=names,
                                          orientation='horizontal',showfliers=False)
    plt.xlabel('Runtime (ms)');plt.title('Day 35 combined stresses: algorithm runtime distribution')
    save('combined_runtime_by_method.png')
    groups=Counter(row['reason'] for row in decisions)
    labels=sorted(groups)
    plt.figure(figsize=(9,4));plt.barh(labels,[groups[x] for x in labels]);plt.xlabel('Image pairs')
    plt.title('Frozen Day 34 gate evaluated on NEW development stresses')
    save('frozen_policy_abstention.png')
    # Stratified one-factor vs combined comparison without conflating task populations.
    by_study=defaultdict(list)
    for label,envs in [('One-factor Day32',baseline_rows),('Combined Day35',combined_rows)]:
        for e in envs:by_study[label].append(e['record']['geometric_within_tolerance'] is True)
    plt.figure(figsize=(7,4));lbl=list(by_study); vals=[100*np.mean(by_study[x]) for x in lbl]
    plt.bar(lbl, vals);plt.ylabel('Geometric success (%)');plt.ylim(0,105)
    plt.title('Descriptive only: different development case distributions')
    save('development_study_comparison_not_matched.png')
    return paths


def combined_gallery(records:list[dict], pairs, fixed:np.ndarray, output:Path, *, limit:int=10) -> list[dict]:
    """Reconstruct images ONLY for visual review, never rerun registrations."""
    by_id={p.pair_id:p for p in pairs}
    index={e['experiment_id']:e for e in records}
    selected=failure_review(records,max_cases=limit)
    gallery_dir=output/'gallery';gallery_dir.mkdir(parents=True,exist_ok=True)
    out=[]
    for i,row in enumerate(selected,1):
        e=index[row['experiment_id']]; rec=e['record']
        prepared=prepare_combined_pair(by_id[e['task']['pair_id']],fixed)
        estimated=rec.get('estimated_transform')
        warped=None; mask=None
        if estimated is not None:
            mat=np.asarray(estimated,dtype=np.float64)
            warped=warp_image(prepared.moving,mat,output_shape=fixed.shape)
            mask=overlap_mask_in_fixed_space(prepared.valid_mask_moving,mat,fixed_shape=fixed.shape)
        fig,axs=plt.subplots(1,4,figsize=(12,3.5))
        axs[0].imshow(prepared.fixed,cmap='gray');axs[0].set_title('Fixed')
        axs[1].imshow(prepared.moving,cmap='gray');axs[1].set_title('Moving (combined stress)')
        axs[2].imshow(warped if warped is not None else np.zeros_like(fixed),cmap='gray')
        axs[2].set_title('Reconstructed' if warped is not None else 'No transform')
        if warped is None:
            axs[3].text(.5,.5,'No estimated transform',ha='center',va='center');axs[3].set_title('Not evaluated')
        else:
            diff=np.abs(prepared.fixed.astype(float)-warped.astype(float))
            diff[~np.asarray(mask,dtype=bool)]=np.nan
            axs[3].imshow(diff,cmap='magma');axs[3].set_title('Absolute difference (valid support)')
        for ax in axs:ax.axis('off')
        fig.suptitle(f"{e['task']['method_id']} | {row['combined_label']} | {rec['execution_status']} | TRE={row['tre_mean_px']}",fontsize=10)
        filename=f"{i:02d}_{e['experiment_id']}.png"
        fig.tight_layout();fig.savefig(gallery_dir/filename,dpi=125,bbox_inches='tight');plt.close(fig)
        out.append({**row,'image':f'gallery/{filename}',
                    'reconstructed_from_deterministic_synthetic_source':True,
                    'original_backend_registered_image_not_retained':True,
                    'visual_review':'pending human inspection'})
    dump_json(gallery_dir/'gallery_manifest.json',out)
    return out


def run(input32:Path,policy_path:Path,config_path:Path,out:Path) -> dict:
    input32=input32.resolve();policy_path=policy_path.resolve();out=out.resolve()
    if any(out==p or p in out.parents for p in (input32,policy_path.parent)):
        raise ValueError('Output must not overwrite source evidence or frozen policy folder')
    baseline,original_manifest=read_evidence(input32,expected_attempts=963)
    immutable=[input32/x for x in ('benchmark_plan.json','benchmark_records.jsonl',
             'benchmark_results.csv','day32_manifest.json')]+[policy_path]
    before={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):content_hash(p) for p in immutable}
    policy=json.loads(policy_path.read_text(encoding='utf-8'))
    if content_hash(input32/'benchmark_records.jsonl') != policy.get('source_sha256'):
        raise ValueError('Frozen policy is not linked to supplied Day 32 evidence')
    config=load_config(config_path);validate_design(config)
    development=here(config['sources']['development'])
    catalog=here(config['frozen_method_catalog'])
    dev_hash=content_hash(development)
    if dev_hash!=original_manifest['source_sha256']:
        raise ValueError('Development image changed since frozen Day 32 run')
    methods=method_specs(load_config(catalog),content_hash(catalog))
    pairs=specifications(dev_hash)
    # Source code hash in task identity ensures resume never silently mixes generators.
    generator_hash=content_hash(ROOT/'src/image_registration/week7_integration.py')
    from image_registration.benchmark_runner import BenchmarkPairSpec
    pairs=[BenchmarkPairSpec(pair_id=p.pair_id,modality_class=p.modality_class,
        transform_model=p.transform_model,degradation=p.degradation,dimensions=p.dimensions,
        reference=p.reference,metadata={**p.metadata,'generator_sha256':generator_hash}) for p in pairs]
    tasks=enumerate_benchmark_tasks(pairs,methods,[None])
    src=load_image(development,color_mode='grayscale').array
    fixed=np.asarray(resize_image(src,tuple(config['runner']['resize_shape']),interpolation='area'))
    # Preflight each combination before creating any output journal.
    prepared={p.pair_id:prepare_combined_pair(p,fixed).metadata for p in pairs}
    runner=ResumableBenchmarkRunner(out)
    result=runner.run(tasks,executor_factory(pairs,methods,fixed,
         float(config['runner']['pilot_tre_threshold_px']),int(config['runner']['pilot_mi_bins'])),resume=True)
    records=runner.records()
    if len(records)!=len(tasks) or len({e['experiment_id'] for e in records})!=len(tasks):
        raise ValueError('Partial or duplicated Day35 benchmark execution')
    policy_after=json.loads(policy_path.read_text(encoding='utf-8'))
    if policy!=policy_after:raise ValueError('Policy changed during run')
    decisions,gate_summary=evaluate_frozen_gate(records,policy)
    by_condition=combined_summary(records)
    matrices=comparison_matrices(baseline,records)
    candidate_gallery=failure_review(records)
    gallery_entries=combined_gallery(records,pairs,fixed,out)
    guidance=recommendations(records)
    baseline_categories=Counter(classify(x)['category'] for x in baseline)
    failure_types=[]
    interpretations={
        'feature_correspondence_failure': 'Correspondence matching / RANSAC support breakdown; inspect repeated-pattern and occlusion examples.',
        'large_geometric_error': 'Estimated transform exists but is severely wrong under synthetic reference; inspect ECC occlusion CHECK cases and other outliers.',
        'geometric_threshold_failure': 'Numerically plausible-looking estimate can exceed 2 px offline TRE; do not equate Completed with accurate.',
        'implausible_transform': 'Transforms flagged implausible need independent rejection; do not convert warnings to PASS.',
    }
    for category in ('feature_correspondence_failure','large_geometric_error','geometric_threshold_failure','implausible_transform'):
        failure_types.append({'failure_type':category,'day32_count':baseline_categories.get(category,0),
            'review_note':interpretations[category],
            'evidence':'Day 32 frozen journal classified with Day 33 taxonomy; associations, not proven causes',
            'human_visual_review':'review in Day 33 12-panel gallery and annotate Day 35 review queue before Week 8'})
    plot_paths=plots(out,records,baseline,decisions)
    dump_csv(out/'combined_stress_summary.csv',by_condition)
    dump_csv(out/'week07_comparison_matrix.csv',matrices)
    dump_csv(out/'stratified_failure_review.csv',candidate_gallery or [{
        'review_category':'none','reason':'No unsuccessful cases were observed in this small subset'}])
    dump_csv(out/'offline_policy_decisions.csv',decisions)
    dump_csv(out/'condition_specific_guidance.csv',guidance)
    dump_csv(out/'recurring_failure_types.csv',failure_types)
    counts=dict(sorted(Counter(e['record']['execution_status'] for e in records).items()))
    correct=sum(e['record']['geometric_within_tolerance'] is True for e in records)
    report={'version':VERSION,'week':7,'day':35,'status':'local_execution_windows_validation_pending',
        'combined_pairs':len(pairs),'combined_attempts':len(tasks),'successes':correct,
        'geometric_failures_including_execution_failures':len(tasks)-correct,
        'execution_status_counts':counts,'baseline_day32_attempts':len(baseline),
        'baseline_day32_geometric_successes':sum(e['record']['geometric_within_tolerance'] is True for e in baseline),
        'frozen_gate':policy['gate'],'frozen_gate_outcome':gate_summary,
        'geometry_seeds':list(GEOMETRY_SEEDS),'split':'development','week8_heldout_pixels_accessed':False,
        'policy_retrained_or_deployed':False, 'review_candidates':len(candidate_gallery),'reconstructed_gallery_panels':len(gallery_entries),
        'condition_specific_guidance_count':len(guidance),'recurring_failure_types':len(failure_types),
        'runner':result.to_dict(),'preflight_pair_count':len(prepared),
        'input_sha256':before,'frozen_methods_sha256':content_hash(catalog),
        'method_variants':len(methods), 'interpretation':
        'Small synthetic development integration; policy untouched; no cross-study causal ranking or calibrated confidence',
        'environment':{'platform':platform.platform(),'python':platform.python_version()}}
    dump_json(out/'day35_report.json',report)
    after={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):content_hash(p) for p in immutable}
    if before!=after:raise ValueError('Original source evidence or policy changed')
    manifest={'version':VERSION,'status':'target_windows_validation_pending',
        'plan_sha256':content_hash(runner.plan_path),'journal_sha256':content_hash(runner.journal_path),
        'source_sha256_unchanged':before==after,'heldout_pixels_accessed':False,
        'frozen_policy_sha256':content_hash(policy_path), 'plot_paths':plot_paths,
        'output_tables':['combined_stress_summary.csv','week07_comparison_matrix.csv',
            'stratified_failure_review.csv','offline_policy_decisions.csv','condition_specific_guidance.csv',
            'recurring_failure_types.csv'],
        'week8_evaluation':'not_started', 'gallery_panels':len(gallery_entries)}
    dump_json(out/'day35_manifest.json',manifest)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--day32',default='outputs/week07_day02_full')
    p.add_argument('--policy',default='outputs/week07_day04_calibration/tentative_policy_not_for_ui.json')
    p.add_argument('--config',default='configs/week07_day01_robustness_grid.yaml')
    p.add_argument('--output',default='outputs/week07_day05_integration')
    args=p.parse_args()
    report=run(here(args.day32),here(args.policy),here(args.config),here(args.output))
    print('Day35 combined:',report['combined_pairs'],'pairs,',report['combined_attempts'],'attempts')
    print('Executed',report['runner']['executed_count'],'resumed',report['runner']['skipped_count'],
          'status',report['execution_status_counts'])
    print('Geometric success:',report['successes'],'/',report['combined_attempts'])
    print('Frozen exploratory gate:',report['frozen_gate_outcome'])
    print('Reports:',here(args.output))
    print('No Week 8 holdout usage, algorithm/UI changes, or policy training')

if __name__=='__main__':main()
