"""Week 7 Day 33: read-only failure, robustness and computational analysis.

Run from repository root:
  python scripts/week07_day03_failure_analysis.py
  python scripts/week07_day03_failure_analysis.py --profile

The Day 32 journal is NEVER modified. No registration is rerun unless the
explicit --profile option is supplied for separate representative cost samples.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from threading import Event, Thread
from time import perf_counter, process_time, sleep
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for path in (str(ROOT / 'src'), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from image_registration.config import load_config  # noqa: E402
from image_registration.benchmark_runner import BenchmarkPairSpec  # noqa: E402
from image_registration.evaluation_contracts import ReferenceEvidence  # noqa: E402
from image_registration.io import load_image  # noqa: E402
from image_registration.preprocessing import resize_image  # noqa: E402
from image_registration.week7_sweeps import prepare_sweep_pair  # noqa: E402
from image_registration.warping import warp_image  # noqa: E402
from image_registration.overlap import overlap_mask_in_fixed_space  # noqa: E402
from image_registration.week7_failure_analysis import (  # noqa: E402
    ANALYSIS_VERSION, classify, file_sha256, read_evidence, select_gallery_cases,
    summarize, tre_of,
)


def _path(value: str | Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def dump_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    names = sorted({key for row in rows for key in row})
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key], sort_keys=True) if isinstance(row.get(key), (list, dict))
                             else row.get(key) for key in names})


def _figure(path: Path):
    plt.tight_layout()
    plt.savefig(path, dpi=145, bbox_inches='tight')
    plt.close()


def create_plots(records: list[dict], summary: dict, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    def save(name: str):
        _figure(dest / name)
        paths.append(f'plots/{name}')

    cond = summary['by_condition']
    plt.figure(figsize=(11, 6))
    plt.barh([r['condition'] for r in cond], [100 * r['geometric_success_rate'] for r in cond])
    plt.xlim(0, 105); plt.xlabel('Geometric success, % of all attempts')
    plt.title('Day 32 synthetic development success by condition')
    plt.gca().invert_yaxis()
    save('condition_success_rate.png')

    taxonomy = summary['taxonomy']
    plt.figure(figsize=(11, 5))
    plt.barh(list(taxonomy), list(taxonomy.values()))
    plt.xlabel('Number of attempts'); plt.title('Observed outcomes, including incorrect completed runs')
    plt.gca().invert_yaxis()
    save('outcome_taxonomy.png')

    rows = [classify(x) for x in records]
    by_method = {}
    for row in rows:
        if row['runtime_ms'] is not None:
            by_method.setdefault(row['method_id'], []).append(float(row['runtime_ms']))
    if by_method:
        ids = sorted(by_method)
        plt.figure(figsize=(10, max(5, .5 * len(ids) + 1)))
        plt.boxplot([by_method[k] for k in ids], tick_labels=ids, orientation="horizontal", showfliers=False)
        plt.xlabel('Recorded end-to-end wall runtime, ms (outliers hidden in boxplot)')
        plt.title('Method runtime distribution on Day 32 hardware')
        save('runtime_by_method.png')

    estimated = [r for r in rows if r['tre_mean_px'] is not None and r['runtime_ms'] is not None]
    if estimated:
        colors = ['C0' if r['geometrically_successful'] else 'C3' for r in estimated]
        plt.figure(figsize=(9, 6))
        plt.scatter([r['runtime_ms'] for r in estimated], [r['tre_mean_px'] for r in estimated],
                    c=colors, alpha=.45, s=14)
        plt.yscale('symlog', linthresh=1.0)
        plt.xlabel('Recorded end-to-end wall runtime, ms')
        plt.ylabel('Ground-truth mean TRE, px (symlog)')
        plt.title('Runtime versus TRE, only runs that estimated a transform')
        save('runtime_vs_tre.png')

    # Severity-level curves preserve modality and model context; no false
    # comparison between heterogeneous severity units or categorical mappings.
    by_group = {}
    for row in summary['by_severity']:
        label = (row['condition'], row['method_id'], row['modality_class'], row['transform_model'])
        try:
            severity = json.loads(row['severity'])
        except (ValueError, TypeError):
            severity = {}
        if len(severity) == 1 and isinstance(next(iter(severity.values())), (int, float)):
            key = next(iter(severity))
            by_group.setdefault((label, key), []).append((float(severity[key]), row['geometric_success_rate'], row['attempts']))
    # One panel per condition, with several curves, limited to reasonably
    # repeatable comparable numeric severity groups.
    conditions = sorted({key[0][0] for key in by_group})
    for condition in conditions:
        plt.figure(figsize=(9, 5))
        drew = False
        for (label, severity_name), points in sorted(by_group.items()):
            if label[0] != condition or len(points) < 2:
                continue
            points = sorted(points)
            plt.plot([x[0] for x in points], [100 * x[1] for x in points], marker='o',
                     label=f'{label[1]} | {label[2]} | {label[3]}')
            drew = True
        if drew:
            plt.ylim(-2, 102)
            plt.xlabel(severity_name if len({k[1] for k in by_group if k[0][0] == condition}) == 1 else 'Severity (condition units)')
            plt.ylabel('Geometric success (% of attempts)')
            plt.title(f'{condition}: development success vs severity')
            plt.legend(loc='best', fontsize='x-small')
            save(f'severity_{condition}.png')
        else:
            plt.close()
    return paths


def build_gallery(records: list[dict], dest: Path, config: dict, limit: int = 12) -> list[dict]:
    """Regenerate synthetic pixels using task provenance, without registration."""
    dest.mkdir(parents=True, exist_ok=True)
    source = ROOT / config['sources']['development']
    img = load_image(source, color_mode='grayscale').array
    fixed = np.asarray(resize_image(img, tuple(config['runner']['resize_shape']), interpolation='area'))
    actual_source_hash = sha256(source.read_bytes()).hexdigest()
    selected = select_gallery_cases(records, limit=limit)
    gallery = []
    for number, item in enumerate(selected, 1):
        task, record = item['task'], item['record']
        meta = task['pair_metadata']
        if meta.get('source_sha256') != actual_source_hash:
            raise ValueError('Development source content changed, cannot reconstruct gallery')
        pair = BenchmarkPairSpec(
            pair_id=task['pair_id'], modality_class=task['modality_class'],
            transform_model=task['transform_model'], degradation=task['degradation'],
            dimensions=task['dimensions'], reference=ReferenceEvidence(exact_transform=True),
            metadata=meta,
        )
        prepared = prepare_sweep_pair(pair, fixed)
        estimated = record.get('estimated_transform')
        warped = None
        overlap = None
        if estimated is not None:
            warped = warp_image(prepared.moving, np.asarray(estimated), output_shape=prepared.fixed.shape)
            overlap = overlap_mask_in_fixed_space(prepared.valid_mask_moving, np.asarray(estimated),
                                                  fixed_shape=prepared.fixed.shape)
        fig, axes = plt.subplots(1, 4, figsize=(12, 3.6))
        axes[0].imshow(prepared.fixed, cmap='gray'); axes[0].set_title('Fixed')
        axes[1].imshow(prepared.moving, cmap='gray'); axes[1].set_title('Moving')
        axes[2].imshow(warped if warped is not None else np.zeros_like(prepared.fixed), cmap='gray')
        axes[2].set_title('Reconstructed' if warped is not None else 'No transform')
        if warped is not None:
            diff = np.abs(prepared.fixed.astype(float) - warped.astype(float))
            diff[~np.asarray(overlap, dtype=bool)] = np.nan
            axes[3].imshow(diff, cmap='magma')
            axes[3].set_title('Absolute difference\n(valid estimate support)')
        else:
            axes[3].text(.5, .5, 'No estimated geometry', ha='center', va='center')
            axes[3].set_title('No geometric comparison')
        for ax in axes:
            ax.axis('off')
        filename = f'{number:02d}_{item["experiment_id"]}.png'
        fig.suptitle(f'{task["method_id"]} | {task["degradation"]} | {record["execution_status"]} | TRE {tre_of(item)} px', fontsize=10)
        fig.tight_layout()
        fig.savefig(dest / filename, dpi=125, bbox_inches='tight')
        plt.close(fig)
        entry = {**classify(item), 'image': f'gallery/{filename}',
                 'display_image_is_reconstruction': True,
                 'original_algorithm_output_recovered': False,
                 'reference_geometry_used_only_for_offline_selection_and_labels': True,
                 'estimated_overlap_fraction': None if overlap is None else float(np.mean(overlap))}
        gallery.append(entry)
    dump_json(dest / 'gallery_manifest.json', gallery)
    return gallery


def sampled_profile(config: dict, output: Path) -> list[dict]:
    """Optional fresh CPU/RSS measurements, separate from frozen Day 32 records.

    Tests a small controlled source and two fast non-MI methods across sizes;
    memory is *sampled process RSS*, not an exact native allocation peak.
    """
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError('--profile requires psutil to measure sampled peak process RSS') from exc
    from ui.adapters import build_default_registration_service
    from ui.core.contracts import (ImageSource, PreprocessingSpec, RegistrationRequest,
                                   RegistrationSpec, EvaluationContext)
    from ui.core.enums import SourceType, GroundTruthStatus, TransformModel, TransformUnits
    from image_registration.synthetic import sample_ground_truth_transform, generate_synthetic_pair
    from image_registration.config import load_config

    method_catalog = load_config(ROOT / 'configs/week07_day01_frozen_methods.yaml')
    # Lookup the exact frozen method parameters; avoid ad hoc optimizer settings.
    from image_registration.week7_robustness import method_specs
    methods = {x.method_id: x for x in method_specs(method_catalog, 'profile-only')}
    source = np.asarray(load_image(ROOT / config['sources']['development'], color_mode='grayscale').array)
    service = build_default_registration_service()
    process = psutil.Process(os.getpid())
    measurements = []
    for size in (96, 192, 384):
        arr = np.asarray(resize_image(source, (size, size), interpolation='area'))
        for method_id, model in (('ecc_rigid', 'rigid'), ('orb_affine', 'affine')):
            spec = methods[method_id]
            truth = sample_ground_truth_transform(model, np.random.default_rng(31), arr.shape,
                                                  {'tx': (5, 5), 'ty': (-4, -4),
                                                   'angle_degrees': (3, 3),
                                                   **({'scale_x': (1.0, 1.0), 'scale_y': (1.0, 1.0), 'shear_x': (.015, .015)} if model == 'affine' else {})})
            pair = generate_synthetic_pair(arr, truth)
            params = dict(spec.metadata['parameters'])
            request = RegistrationRequest(
                fixed=ImageSource(SourceType.ARRAY, 'Day33 CPU profile fixed', array=arr),
                moving=ImageSource(SourceType.ARRAY, 'Day33 CPU profile moving', array=pair.moving),
                preprocessing=PreprocessingSpec(grayscale=True, resize_policy='none'),
                registration=RegistrationSpec(method_id=method_id, transform_model=TransformModel(model),
                                              initialization=params.get('initialization'), parameters=params,
                                              interpolation=str(params.get('interpolation', 'bilinear'))),
                evaluation=EvaluationContext(ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                                             units=TransformUnits.PIXELS),
                request_id=f'day33_profile_{size}_{method_id}',
            )
            done = Event()
            start_rss = process.memory_info().rss
            rss_samples = [start_rss]
            def observe():
                while not done.is_set():
                    rss_samples.append(process.memory_info().rss)
                    sleep(.005)
            thread = Thread(target=observe, daemon=True)
            thread.start()
            cpu_start = process_time(); wall_start = perf_counter()
            try:
                result = service.run(request)
                status = result.run_status.value
            finally:
                wall_ms = (perf_counter() - wall_start) * 1000
                cpu_ms = (process_time() - cpu_start) * 1000
                done.set(); thread.join(timeout=2)
            rss_samples.append(process.memory_info().rss)
            measurements.append({'size': size, 'method_id': method_id, 'status': status,
                                 'wall_ms': round(wall_ms, 3), 'process_cpu_ms': round(cpu_ms, 3),
                                 'baseline_rss_mib': round(start_rss / (1024**2), 3),
                                 'sampled_peak_process_rss_mib': round(max(rss_samples) / (1024**2), 3),
                                 'samples': len(rss_samples), 'memory_measurement': 'sampled_process_rss_5ms',
                                 'profile_not_part_of_day32_benchmark': True})
    dump_csv(output / 'representative_cpu_memory.csv', measurements)
    dump_json(output / 'representative_cpu_memory.json', measurements)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    for method in sorted({row['method_id'] for row in measurements}):
        selected = sorted((row for row in measurements if row['method_id'] == method),
                          key=lambda row: row['size'])
        ax1.plot([r['size'] for r in selected], [r['process_cpu_ms'] for r in selected],
                 marker='o', label=method)
        ax2.plot([r['size'] for r in selected], [r['sampled_peak_process_rss_mib'] for r in selected],
                 marker='o', label=method)
    ax1.set(xlabel='Image width / height, px', ylabel='Process CPU time, ms',
            title='Exploratory CPU time')
    ax2.set(xlabel='Image width / height, px', ylabel='Sampled process peak RSS, MiB',
            title='5-ms-sampled process memory')
    ax1.legend(fontsize='small'); ax2.legend(fontsize='small')
    _figure(output / 'representative_cpu_memory.png')
    return measurements


def run(input_dir: Path, output_dir: Path, *, profile: bool = False, gallery_limit: int = 12):
    records, manifest = read_evidence(input_dir, expected_attempts=963)
    config = load_config(ROOT / 'configs/week07_day01_robustness_grid.yaml')
    if manifest.get('source_sha256') != sha256((ROOT / config['sources']['development']).read_bytes()).hexdigest():
        raise ValueError('Development source differs from the frozen Day 32 evidence')
    if manifest.get('generator_sha256') != file_sha256(ROOT / 'src/image_registration/week7_sweeps.py'):
        raise ValueError('Day 32 source generator changed; refuse misleading reconstructed gallery')
    if output_dir.resolve() == input_dir.resolve() or input_dir.resolve() in output_dir.resolve().parents:
        raise ValueError('Day 33 output must not overwrite or nest within Day 32 records')
    output_dir.mkdir(parents=True, exist_ok=True)
    report = summarize(records)
    dump_json(output_dir / 'failure_summary.json', report)
    classified = [classify(x) for x in records]
    dump_csv(output_dir / 'classified_attempts.csv', classified)
    for filename, rows in (('condition_comparison.csv', report['by_condition']),
                           ('method_comparison.csv', report['by_method']),
                           ('condition_method_comparison.csv', report['by_condition_method']),
                           ('severity_curves.csv', report['by_severity'])):
        dump_csv(output_dir / filename, rows)
    figures = create_plots(records, report, output_dir / 'plots')
    gallery = build_gallery(records, output_dir / 'gallery', config, limit=gallery_limit)
    measured = sampled_profile(config, output_dir) if profile else []
    closure = {
        'week': 7, 'day': 33, 'state': 'analysis_generated_review_pending',
        'analysis_version': ANALYSIS_VERSION,
        'source_folder': str(input_dir.resolve()),
        'day32_records_sha256': file_sha256(input_dir / 'benchmark_records.jsonl'),
        'day32_manifest_sha256': file_sha256(input_dir / 'day32_manifest.json'),
        'day32_records_not_modified': True,
        'full_benchmark_attempts': len(records),
        'geometric_successes': report['geometric_successes'],
        'plot_files': figures, 'gallery_count': len(gallery),
        'profile_samples': len(measured), 'profile_not_part_of_day32': True,
        'python_version': platform.python_version(),
        'limitations': report['limitations'],
    }
    dump_json(output_dir / 'day33_manifest.json', closure)
    return closure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='outputs/week07_day02_full')
    parser.add_argument('--output', default='outputs/week07_day03_analysis')
    parser.add_argument('--profile', action='store_true', help='Separate CPU and sampled process RSS profiling; requires psutil')
    parser.add_argument('--gallery-limit', type=int, default=12)
    args = parser.parse_args()
    result = run(_path(args.input), _path(args.output), profile=args.profile, gallery_limit=args.gallery_limit)
    print(f"Day 33: {result['full_benchmark_attempts']} records, {result['geometric_successes']} geometric successes")
    print(f"Charts: {len(result['plot_files'])}, gallery: {result['gallery_count']}, CPU profiles: {result['profile_samples']}")
    print(f"Output: {_path(args.output)}")

if __name__ == '__main__':
    main()
