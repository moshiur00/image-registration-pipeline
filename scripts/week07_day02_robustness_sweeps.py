"""Week 7 Day 32: controlled severity sweeps with an explicit dry-run gate.

Default executes a small stratified dry run, NOT the 1,026-attempt Day31 grid.
Pass --full only after examining the dry run and resource costs on Windows.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for path in (str(ROOT / 'src'), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from image_registration.benchmark_runner import (  # noqa: E402
    BenchmarkPairSpec, ResumableBenchmarkRunner, enumerate_benchmark_tasks,
)
from image_registration.config import load_config  # noqa: E402
from image_registration.evaluation_contracts import (  # noqa: E402
    ExecutionStatus, UnifiedEvaluationRecord,
)
from image_registration.io import load_image  # noqa: E402
from image_registration.overlap import overlap_mask_in_fixed_space  # noqa: E402
from image_registration.preprocessing import resize_image  # noqa: E402
from image_registration.unified_metrics import (  # noqa: E402
    transform_tre, model_aware_parameter_errors, overlap_aware_descriptive_metrics,
)
from image_registration.week7_robustness import (  # noqa: E402
    content_hash, design_pairs, method_specs, validate_design,
)
from image_registration.week7_sweeps import (  # noqa: E402
    prepare_sweep_pair, stratified_dry_run_pairs, SEVERITY_VERSION,
)
from ui.adapters import build_default_registration_service  # noqa: E402
from ui.core.contracts import (  # noqa: E402
    ImageSource, PreprocessingSpec, RegistrationRequest, RegistrationSpec,
    EvaluationContext as UIEvaluationContext,
)
from ui.core.enums import (  # noqa: E402
    SourceType, GroundTruthStatus, TransformModel, TransformUnits,
)


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def valid_sweep_pairs(pairs):
    """Drop incompatible *geometric* factors, independent of method support."""
    accepted, excluded = [], []
    for pair in pairs:
        if pair.degradation == 'rotation' and pair.transform_model == 'translation':
            excluded.append({'pair_id': pair.pair_id, 'reason': 'rotation_requires_rigid_or_more_complex_model'})
        elif pair.degradation == 'scale' and pair.transform_model not in {'similarity', 'affine'}:
            excluded.append({'pair_id': pair.pair_id, 'reason': 'scale_requires_similarity_or_affine_model'})
        else:
            accepted.append(pair)
    return accepted, excluded


def execute_factory(config: dict[str, Any], methods, pair_specs, fixed: np.ndarray):
    """Registrations see images + known task context, never exact GT or TRE."""
    service = build_default_registration_service()
    by_config = {method.config_id: method for method in methods}
    pair_lookup = {pair.pair_id: pair for pair in pair_specs}
    cache = {}
    tolerance = float(config['runner']['pilot_tre_threshold_px'])
    mi_bins = int(config['runner']['pilot_mi_bins'])

    def execute(task):
        if task.pair_id not in cache:
            cache[task.pair_id] = prepare_sweep_pair(pair_lookup[task.pair_id], fixed)
        prepared = cache[task.pair_id]
        parameters = dict(by_config[task.config_id].metadata['parameters'])
        request = RegistrationRequest(
            fixed=ImageSource(SourceType.ARRAY, 'Day32 development fixed', array=prepared.fixed),
            moving=ImageSource(SourceType.ARRAY, 'Day32 development moving', array=prepared.moving),
            preprocessing=PreprocessingSpec(grayscale=True, resize_policy='none'),
            registration=RegistrationSpec(
                method_id=task.method_id,
                transform_model=TransformModel(task.transform_model),
                initialization=parameters.get('initialization'),
                parameters=parameters,
                interpolation=str(parameters.get('interpolation', 'bilinear')),
            ),
            evaluation=UIEvaluationContext(
                ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                units=TransformUnits.PIXELS,
            ),
            request_id=task.experiment_id,
        )
        start = perf_counter()
        run = service.run(request)
        runtime_ms = (perf_counter() - start) * 1000.0
        status = ExecutionStatus(run.run_status.value)
        estimated = None if run.transform is None else np.asarray(run.transform.matrix, dtype=np.float64)
        metrics: dict[str, float] = {'total_runtime_ms': runtime_ms}
        overlap = None
        is_correct = None
        warnings = list(run.warnings)
        if estimated is not None and status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}:
            # Offline evaluator has GT; never pass it to the service.
            tre = transform_tre(prepared.ground_truth, estimated, prepared.moving_points)['px']
            metrics.update(tre.to_metrics())
            param_err = model_aware_parameter_errors(
                prepared.ground_truth, estimated, transform_model=task.transform_model,
            )
            metrics.update(param_err)
            is_correct = bool(tre.mean <= tolerance and run.transform.plausible)
            if run.registered_array is not None:
                estimated_mask = overlap_mask_in_fixed_space(
                    prepared.valid_mask_moving, estimated, fixed_shape=prepared.fixed.shape,
                )
                if np.any(estimated_mask):
                    try:
                        descriptive = overlap_aware_descriptive_metrics(
                            prepared.fixed, run.registered_array, estimated_mask, mi_bins=mi_bins,
                        )
                        metrics.update(descriptive)
                        overlap = float(descriptive['valid_overlap_fraction'])
                    except ValueError as exc:
                        warnings.append(f'descriptive_metric_unavailable: {exc}')
        failure_reason = (run.failure_reason or 'registration_failed') if status in {
            ExecutionStatus.FAILED, ExecutionStatus.VALIDATION_ERROR,
        } else None
        return UnifiedEvaluationRecord(
            pair_id=task.pair_id, method_id=task.method_id,
            method_family=task.method_family, transform_model=task.transform_model,
            modality_class=task.modality_class, dimensions=2, execution_status=status,
            reference=task.reference, valid_overlap_fraction=overlap, seed=task.seed,
            estimated_transform=estimated, transform_plausible=None if run.transform is None else run.transform.plausible,
            geometric_within_tolerance=is_correct, metrics=metrics,
            timings_ms={'total': runtime_ms},
            method_diagnostics={'raw': run.diagnostics.values,
                                'offline_reference_overlap_fraction': prepared.metadata['reference_valid_overlap_fraction'],
                                'severity_version': SEVERITY_VERSION},
            warnings=warnings, failure_reason=failure_reason,
        )
    return execute


def aggregate_records(envelopes):
    """Report attempt-denominator success, including failure and CHECK records."""
    groups = defaultdict(list)
    for envelope in envelopes:
        task, record = envelope['task'], envelope['record']
        metadata = task['pair_metadata']
        group_key = (task['modality_class'], task['transform_model'], task['degradation'],
                     json.dumps(metadata.get('condition_parameters', {}), sort_keys=True),
                     task['method_id'])
        groups[group_key].append(record)
    summaries = []
    for key, records in sorted(groups.items()):
        n = len(records)
        geometric_success = sum(r['geometric_within_tolerance'] is True for r in records)
        execution_success = sum(r['execution_status'] in {'completed', 'check'} for r in records)
        tre_values = [float(r['metrics']['tre_mean_px']) for r in records if 'tre_mean_px' in r['metrics']]
        timing_values = [float(r['timings_ms']['total']) for r in records if 'total' in r['timings_ms']]
        summaries.append({
            'modality_class': key[0], 'transform_model': key[1], 'condition': key[2],
            'severity_json': key[3], 'method_id': key[4], 'attempts': n,
            'completed_or_check': execution_success, 'failed_or_validation_error': n - execution_success,
            'execution_rate': round(execution_success / n, 6),
            'geometric_successes': geometric_success, 'geometric_success_rate': round(geometric_success / n, 6),
            'tre_observed_count': len(tre_values),
            'median_tre_px_on_estimated': None if not tre_values else round(float(np.median(tre_values)), 6),
            'median_runtime_ms_on_recorded': None if not timing_values else round(float(np.median(timing_values)), 3),
        })
    return summaries


def _write_summary_csv(path, rows):
    if not rows:
        raise ValueError('Cannot export empty robustness aggregate.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/week07_day01_robustness_grid.yaml')
    parser.add_argument('--full', action='store_true', help='Execute all physically meaningful planned severity cases. Potentially costly.')
    parser.add_argument('--output', default=None, help='Optional dedicated output directory; plan changes are rejected on resume.')
    args = parser.parse_args()
    config_path = _path(args.config)
    config = load_config(config_path)
    validate_design(config)
    source_path = _path(config['sources']['development'])
    holdout_path = _path(config['sources']['final_holdout'])
    catalog_path = _path(config['frozen_method_catalog'])
    # Hash the held-out file without decoding/loading its pixels.
    hashes = {'development': content_hash(source_path), 'final_holdout': content_hash(holdout_path)}
    if hashes['development'] == hashes['final_holdout']:
        raise ValueError('Development and holdout data hashes are equal.')
    methods = method_specs(load_config(catalog_path), content_hash(catalog_path))
    planned = design_pairs(config, hashes['development'])
    compatible = [pair for pair in planned if any(method.supports(pair) for method in methods)]
    runnable, geometry_excluded = valid_sweep_pairs(compatible)
    if not args.full:
        runnable = stratified_dry_run_pairs(runnable)
    # Generator implementation and severity semantics are part of experiment
    # identity, so resume cannot silently reuse stale synthesized image pairs.
    generator_hash = content_hash(ROOT / 'src/image_registration/week7_sweeps.py')
    runnable = [BenchmarkPairSpec(
        pair_id=p.pair_id, modality_class=p.modality_class,
        transform_model=p.transform_model, degradation=p.degradation,
        dimensions=p.dimensions, reference=p.reference,
        metadata={**p.metadata, 'severity_version': SEVERITY_VERSION,
                  'generator_sha256': generator_hash},
    ) for p in runnable]
    tasks = enumerate_benchmark_tasks(runnable, methods, [None])
    fixed_source = load_image(source_path, color_mode='grayscale').array
    fixed = np.asarray(resize_image(fixed_source, tuple(config['runner']['resize_shape']), interpolation='area'))
    if fixed.dtype != np.uint8:
        raise ValueError('Development image must decode to uint8 for frozen Day32 processing.')
    # Preflight every selected pair before writing any benchmark evidence.
    preflight = {pair.pair_id: prepare_sweep_pair(pair, fixed).metadata for pair in runnable}
    mode = 'full' if args.full else 'dry_run'
    output = _path(args.output or f'outputs/week07_day02_{mode}')
    runner = ResumableBenchmarkRunner(output)
    result = runner.run(tasks, execute_factory(config, methods, runnable, fixed), resume=True)
    aggregate = aggregate_records(runner.records())
    _write_summary_csv(output / 'severity_summary.csv', aggregate)
    _write_json(output / 'severity_summary.json', aggregate)
    report = {
        'week': 7, 'day': 32, 'mode': mode, 'state': 'local_run_needs_target_windows_validation',
        'source_sha256': hashes['development'], 'holdout_sha256_provenance_only': hashes['final_holdout'],
        'heldout_pixels_loaded': False, 'config_sha256': content_hash(config_path),
        'method_catalog_sha256': content_hash(catalog_path), 'severity_version': SEVERITY_VERSION,
        'generator_sha256': generator_hash,
        'day31_compatible_pairs': len(compatible), 'geometry_excluded_pairs': len(geometry_excluded),
        'geometry_exclusion_reasons': sorted(set(item['reason'] for item in geometry_excluded)),
        'selected_pairs': len(runnable), 'selected_tasks': len(tasks),
        'preflight_max_round_trip_px': max(float(item['reference_control_point_round_trip_max_px']) for item in preflight.values()),
        'preflight_overlaps': {pair_id: round(float(item['reference_valid_overlap_fraction']), 6)
                               for pair_id, item in sorted(preflight.items())},
        'runner': result.to_dict(), 'environment': {'python': platform.python_version(), 'platform': platform.platform()},
        'interpretation': 'development-only synthetic evidence; no confidence or final method selection; success denominator includes failures',
    }
    _write_json(output / 'day32_manifest.json', report)
    print(f'Day32 {mode}: {len(runnable)} pairs, {len(tasks)} attempts')
    print(f'Executed {result.executed_count}; resumed {result.skipped_count}; status {result.to_dict()["status_counts"]}')
    print(f'Excluded incompatible geometry conditions: {len(geometry_excluded)}')
    print(f'Results: {runner.long_form_path}; summary: {output / "severity_summary.csv"}')


if __name__ == '__main__':
    main()
