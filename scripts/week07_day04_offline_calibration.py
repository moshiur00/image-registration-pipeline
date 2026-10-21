"""Week 7 Day 34. Read-only offline, development-only evidence calibration.

Usage from root:
 python scripts/week07_day04_offline_calibration.py
 python scripts/week07_day04_offline_calibration.py --input outputs/week07_day02_full

Does not execute registration, touch Week 8 holdout, update UI, or publish policy.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from image_registration.week7_failure_analysis import read_evidence, file_sha256  # noqa: E402
from image_registration.week7_calibration import (  # noqa: E402
    VERSION, Gate, offline_evaluate, signal_table, grouped_summary,
    summarize_decisions,
)

TRAIN_SEEDS = (7, 42)
AUDIT_SEEDS = (101,)
# A small, declared exploratory grid. Unlike Week 8, this is NOT an independent set.
AGREEMENT_GRID_PX = (0.5, 1., 2., 3., 5., 8.)
OVERLAP_GRID = (0.35, 0.50, 0.65)
TUNING_RULE = {
    'selection': 'narrowest threshold meeting the predeclared internal-development criteria',
    'minimum_train_coverage': 0.10,
    'minimum_train_selected': 20,
    'minimum_train_conditional_precision': 0.95,
    'minimum_train_wilson_lower_95': 0.80,
    'tie_break': 'lower agreement_px, higher overlap_floor, higher train precision',
    'fallback': 'no provisional gate; abstain all pairs',
}


def path_from_root(p: str) -> Path:
    value = Path(p)
    return value if value.is_absolute() else ROOT / value


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        raise ValueError(f'Expected nonempty table: {path}')
    fields = sorted({k for x in items for k in x.keys()})
    with path.open('w', encoding='utf-8', newline='') as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader()
        for item in items:
            w.writerow({k: json.dumps(item[k], sort_keys=True) if isinstance(item.get(k), (list, dict))
                        else item.get(k) for k in fields})


def sweep(records: list[dict]) -> tuple[list[dict], Gate | None]:
    rows = []
    for width in AGREEMENT_GRID_PX:
        for overlap in OVERLAP_GRID:
            gate = Gate(agreement_px=width, overlap_floor=overlap)
            decisions, _ = offline_evaluate(records, gate)
            dev = summarize_decisions([x for x in decisions if x['seed'] in TRAIN_SEEDS])
            audit = summarize_decisions([x for x in decisions if x['seed'] in AUDIT_SEEDS])
            rows.append({'agreement_px': width, 'overlap_floor': overlap,
                         'train_pairs': dev['pairs'], 'train_supported': dev['tentatively_supported'],
                         'train_coverage': dev['coverage'], 'train_correct': dev['correct_selected'],
                         'train_conditional_precision': dev['conditional_precision'],
                         'train_wilson_lower_95': dev['precision_wilson_95_exploratory'][0],
                         'audit_pairs_descriptive_only': audit['pairs'],
                         'audit_supported_descriptive_only': audit['tentatively_supported'],
                         'audit_precision_descriptive_only': audit['conditional_precision']})
    # Only DEVELOPMENT train columns affect policy choice. Audit figures are never consulted.
    qualified = [x for x in rows
                 if x['train_supported'] >= TUNING_RULE['minimum_train_selected']
                 and x['train_coverage'] is not None and x['train_coverage'] >= TUNING_RULE['minimum_train_coverage']
                 and x['train_conditional_precision'] is not None
                 and x['train_conditional_precision'] >= TUNING_RULE['minimum_train_conditional_precision']
                 and x['train_wilson_lower_95'] is not None
                 and x['train_wilson_lower_95'] >= TUNING_RULE['minimum_train_wilson_lower_95']]
    if not qualified:
        return rows, None
    winner = min(qualified, key=lambda x: (x['agreement_px'], -x['overlap_floor'], -x['train_conditional_precision']))
    return rows, Gate(agreement_px=winner['agreement_px'], overlap_floor=winner['overlap_floor'])


def plot_results(rows: list[dict], decisions: list[dict], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    outputs = []
    plt.figure(figsize=(8.5, 5))
    for overlap in OVERLAP_GRID:
        group = [x for x in rows if x['overlap_floor'] == overlap]
        plt.plot([x['agreement_px'] for x in group],
                 [100*x['train_coverage'] for x in group], marker='o',
                 label=f'Observed overlap floor >= {overlap:.2f}')
    plt.xlabel('Three-family maximum disagreement allowed (px)')
    plt.ylabel('Training pairs receiving tentative support (%)')
    plt.title('Development-only coverage versus agreement threshold')
    plt.grid(alpha=.2);plt.legend();plt.tight_layout()
    p=out/'train_coverage_sensitivity.png';plt.savefig(p,dpi=145);plt.close();outputs.append(p)
    plt.figure(figsize=(8.5, 5))
    for overlap in OVERLAP_GRID:
        group = [x for x in rows if x['overlap_floor'] == overlap]
        plt.plot([x['agreement_px'] for x in group],
                 [100*x['train_conditional_precision'] if x['train_conditional_precision'] is not None else float('nan')
                  for x in group], marker='o',label=f'Overlap floor {overlap:.2f}')
    plt.xlabel('Maximum disagreement allowed (px)')
    plt.ylabel('Observed precision on supported training pairs (%)')
    plt.ylim(0, 105);plt.title('Selective precision; zero support appears as a gap')
    plt.grid(alpha=.2);plt.legend();plt.tight_layout()
    p=out/'train_selective_precision.png';plt.savefig(p,dpi=145);plt.close();outputs.append(p)
    counts = {}
    for row in decisions:
        counts[row['reason']] = counts.get(row['reason'], 0)+1
    labels=sorted(counts)
    plt.figure(figsize=(9, 4.8))
    plt.barh(labels, [counts[l] for l in labels]);plt.xlabel('Pairs')
    plt.title('Provisional gate decisions and abstention reasons')
    plt.tight_layout();p=out/'abstention_reasons.png';plt.savefig(p,dpi=145);plt.close();outputs.append(p)
    return outputs


def run(input_dir: Path, output_dir: Path) -> dict:
    if input_dir.resolve() == output_dir.resolve() or input_dir.resolve() in output_dir.resolve().parents:
        raise ValueError('Output must not overwrite or be placed inside the frozen input directory')
    if not input_dir.exists():
        raise FileNotFoundError(f'Frozen Day 32 evidence not found: {input_dir}')
    records, manifest = read_evidence(input_dir)
    if len(records) != 963:
        raise ValueError('Expected full frozen 963-attempt Week 7 development evidence')
    seeds = {int(item['task']['pair_metadata']['geometry_seed']) for item in records}
    if seeds != set(TRAIN_SEEDS + AUDIT_SEEDS):
        raise ValueError(f'Unexpected geometry seeds: {seeds}; do not silently repartition')
    # We read the source hashes BEFORE and AFTER writing to enforce read-only source evidence.
    immutable_sources = [input_dir / name for name in ('benchmark_records.jsonl','benchmark_results.csv','benchmark_plan.json','day32_manifest.json')]
    before = {p.name: file_sha256(p) for p in immutable_sources}
    grid, choice = sweep(records)
    if choice is None:
        # Conservative fallback: all pairs abstain. No unvalidated gate published.
        decisions = []
        for row in offline_evaluate(records, Gate())[0]:
            row.update(decision='abstain', reason='no_training_gate_qualified', selected_id=None,
                       support_ids=[],support_families=[],selected_geometrically_correct_offline=None)
            decisions.append(row)
    else:
        decisions, _ = offline_evaluate(records, choice)
    train_rows=[row for row in decisions if row['seed'] in TRAIN_SEEDS]
    audit_rows=[row for row in decisions if row['seed'] in AUDIT_SEEDS]
    if not (len(train_rows) == 324 and len(audit_rows) == 162):
        raise ValueError('Internal split is not pair grouped or has unexpected dimensions')
    signals=signal_table(records)
    stats={
        'analysis_version': VERSION, 'scope': 'offline_development_only_not_a_deployed_policy',
        'source_journal_sha256': before['benchmark_records.jsonl'],
        'source_attempts': len(records), 'source_pairs': len(decisions),
        'split': {'training_geometry_seeds': list(TRAIN_SEEDS), 'audit_geometry_seeds': list(AUDIT_SEEDS),
                  'disclaimer': 'internal development-seed audit, not a Week 8 independent holdout'},
        'tuning_rule': TUNING_RULE, 'chosen_tentative_gate': asdict(choice) if choice else None,
        'train': summarize_decisions(train_rows), 'internal_audit': summarize_decisions(audit_rows),
        'all_development_descriptive': summarize_decisions(decisions),
        'by_modality': grouped_summary(decisions, ('modality',)),
        'by_model': grouped_summary(decisions, ('model',)),
        'by_condition': grouped_summary(decisions, ('condition',)),
        'limitations': [
            'No production selector, confidence percentage, UI change, or method ranking.',
            'Selection uses observable-only whitelist and never synthetic TRE or reference labels.',
            'Pairing and tuning use repeated synthetic conditions; Wilson intervals assume independence and are descriptive, potentially optimistic.',
            'Only affine monomodal pairs typically have three method families in this dataset; all other models largely abstain by design.',
            'Perfect or near-perfect selected precision may reflect selective easy-case coverage, not broad robustness.',
            'Matching transformations can be jointly wrong; agreement is not ground-truth geometric validity.',
            'No Week 8 held-out images or outcomes used; final policy must face independent testing.',
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir/'calibration_report.json', stats)
    write_json(output_dir/'tentative_policy_not_for_ui.json', {
        'version': VERSION, 'status': 'exploratory_not_deployed', 'gate': asdict(choice) if choice else None,
        'rule': TUNING_RULE, 'source_sha256': before['benchmark_records.jsonl'],
        'independent_validation': False,
    })
    write_csv(output_dir/'threshold_sensitivity.csv',grid)
    write_csv(output_dir/'pair_decisions_offline.csv',decisions)
    write_csv(output_dir/'observable_signal_bins.csv',signals)
    write_csv(output_dir/'condition_summary.csv',stats['by_condition'])
    write_csv(output_dir/'model_summary.csv',stats['by_model'])
    figures=plot_results(grid, decisions, output_dir/'plots')
    after={p.name: file_sha256(p) for p in immutable_sources}
    if before != after:
        raise RuntimeError('Day 32 source evidence changed during offline analysis!')
    write_json(output_dir/'day34_manifest.json',{
        'version': VERSION, 'status': 'local_calibration_generated_review_pending',
        'source_hashes_sha256': before, 'source_file_count': len(before),
        'source_frozen_method_catalog_sha256': manifest.get('catalog_sha256'),
        'outputs': sorted(str(p.relative_to(output_dir)).replace('\\','/') for p in output_dir.rglob('*') if p.is_file()),
        'training_only_gate_selection': True, 'audit_is_internal_not_week8': True,
        'heldout_loaded': False, 'registration_rerun': False,
    })
    return stats


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',default='outputs/week07_day02_full',help='Frozen full Day 32 evidence directory')
    parser.add_argument('--output',default='outputs/week07_day04_calibration',help='New calibration output directory')
    args=parser.parse_args()
    stats=run(path_from_root(args.input),path_from_root(args.output))
    print('Day 34 offline development calibration:',stats['source_attempts'],'attempts,',stats['source_pairs'],'pairs')
    print('Chosen exploratory gate:',stats['chosen_tentative_gate'])
    print('Training:',stats['train'])
    print('Internal-seed audit (NOT Week 8):',stats['internal_audit'])
    print('Output:',path_from_root(args.output))
    print('No registration reruns, UI changes or held-out data access.')

if __name__=='__main__':
    main()
