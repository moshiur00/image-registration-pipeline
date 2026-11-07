"""Stage A preflight: integrity/leakage and holdout source audit tests."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/week08_preflight.py'
spec = importlib.util.spec_from_file_location('week08_preflight_script', SCRIPT)
assert spec and spec.loader
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)

ARCHIVE_SCRIPT = ROOT / 'scripts/week07_evidence_archive.py'
archive_spec = importlib.util.spec_from_file_location('week07_evidence_archive_preflight_test', ARCHIVE_SCRIPT)
assert archive_spec and archive_spec.loader
archive_tool = importlib.util.module_from_spec(archive_spec)
sys.modules[archive_spec.name] = archive_tool
archive_spec.loader.exec_module(archive_tool)


def stage(tmp_path: Path, *, evidence=True) -> Path:
    paths = [*list(pre.REQUIRED_EVIDENCE.values()), str(pre.FROZEN_REL), str(pre.LEDGER_REL),
             str(pre.INTEGRITY_ANCHOR_REL), str(pre.EVIDENCE_ARCHIVE_MANIFEST_REL),
             str(pre.HANDOFF_REL), str(pre.CLOSURE_REL),
             'data/manifests/general_real_sources.json',
             'data/manifests/rire_training001.json',
             'src/image_registration/week7_calibration.py',
             'tests/test_week7_day34_offline_calibration.py']
    # Keep the full immutable-file set to make missing files an explicit blocker.
    freeze = json.loads((ROOT / pre.FROZEN_REL).read_text())
    paths += list(freeze['frozen_files'])
    if evidence:
        paths += list(freeze['week7_evidence_files'])
    if evidence:
        paths += ['outputs/week07_day02_full/benchmark_plan.json',
                  'outputs/week07_day05_integration/benchmark_plan.json']
    else:
        paths = [x for x in paths if not x.startswith('outputs/')]
    ledger = json.loads((ROOT / pre.LEDGER_REL).read_text())
    known_source_paths = {entry['path'] for entry in ledger['known_prior_sources']}
    paths += list(known_source_paths)
    paths += [entry['lineage_evidence']['manifest_path'] for entry in ledger['known_prior_sources']]
    archive_manifest = ROOT / pre.EVIDENCE_ARCHIVE_MANIFEST_REL
    if archive_manifest.is_file():
        package = json.loads(archive_manifest.read_text())
        paths += [entry['closure_reference'] for entry in package.get('files', [])]
    for rel in set(paths):
        source = ROOT / rel
        if not source.exists():
            pytest.skip(f'Full Week 7 evidence missing from local test fixture: {source}')
        dest = tmp_path / rel; dest.parent.mkdir(parents=True, exist_ok=True)
        if rel in known_source_paths:
            try:
                os.link(source, dest)
            except OSError:
                shutil.copyfile(source, dest)
        else:
            shutil.copyfile(source,dest)
    return tmp_path


def stage_from_evidence_archive(tmp_path: Path) -> Path:
    """Create a preflight root whose Week 7 outputs come only from the archive."""
    root = tmp_path / 'clean_staging'
    archive_tool.restore_archive(
        project_root=ROOT,
        archive_path=ROOT / archive_tool.DEFAULT_ARCHIVE_REL,
        manifest_path=ROOT / archive_tool.DEFAULT_MANIFEST_REL,
        destination=root,
    )
    freeze = json.loads((ROOT / pre.FROZEN_REL).read_text())
    ledger = json.loads((ROOT / pre.LEDGER_REL).read_text())
    package = json.loads((ROOT / pre.EVIDENCE_ARCHIVE_MANIFEST_REL).read_text())
    paths = {
        str(pre.FROZEN_REL), str(pre.LEDGER_REL), str(pre.INTEGRITY_ANCHOR_REL),
        str(pre.EVIDENCE_ARCHIVE_MANIFEST_REL), str(pre.HANDOFF_REL), str(pre.CLOSURE_REL),
        'data/manifests/general_real_sources.json', 'data/manifests/rire_training001.json',
        'src/image_registration/week7_calibration.py',
        'tests/test_week7_day34_offline_calibration.py',
        *freeze['frozen_files'],
        *(entry['path'] for entry in ledger['known_prior_sources']),
        *(entry['lineage_evidence']['manifest_path'] for entry in ledger['known_prior_sources']),
        *(entry['closure_reference'] for entry in package['files']),
    }
    for rel in paths:
        assert not rel.startswith('outputs/'), f'evidence must be restored, not copied: {rel}'
        source = ROOT / rel
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return root


@pytest.fixture(scope='module')
def source_bundle_available():
    assert (ROOT / pre.REQUIRED_EVIDENCE['day34_policy']).exists(), 'Stage A package must contain frozen evidence'


def inspect(root: Path, *, final_readiness=False):
    return pre.Audit(root, final_readiness=final_readiness).run()


def status(report, code):
    """Report the upstream gate reason rather than hiding it with StopIteration."""
    for check in report["checks"]:
        if check["check"] == code:
            return check["status"]
    observed = [(c["check"], c["status"], c.get("details")) for c in report["checks"]]
    pytest.fail(f"Expected preflight check {code!r} was not emitted. Observed checks: {observed}")


def write_fixture(root: Path, rel: str, content: bytes) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def synthetic_ground_truth(root: Path) -> dict:
    records = {}
    for name, rel in {
        'config': 'configs/test_week08_generation.json',
        'case_spec': 'configs/test_week08_case_specification.json',
        'manifest': 'data/holdout/week08/test_case_manifest.json',
    }.items():
        records[f'{name}_path'] = rel
        records[f'{name}_sha256'] = write_fixture(root, rel, (name + '-metadata').encode())
    return {
        'type': 'synthetic_created_after_freeze',
        'generator_id': 'test_week08_generator',
        'generator_version': 'test-v1',
        'seeds': [7001, 7002],
        'interpolation': 'linear',
        'border_overlap_policy': 'predeclared minimum overlap',
        'coordinate_convention': 'moving_to_fixed',
        'release_freeze_id': 'test-release-freeze-v1',
        **records,
    }


def register_independent(root, *, reuse=False, gt='synthetic_created_after_freeze', alter_sha=False):
    ledger = json.loads((root / pre.LEDGER_REL).read_text())
    src = root / 'data/holdout/week08/new_source.png'
    if reuse:
        original = ROOT / 'data/samples/week02_real_general/moon.png'
        src.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(original,src)
    else:
        src.parent.mkdir(parents=True, exist_ok=True);src.write_bytes(b'new independent raw source fixture bytes')
    h = hashlib.sha256(src.read_bytes()).hexdigest()
    lineage_rel = 'data/holdout/week08/test_lineage.json'
    lineage_hash = write_fixture(root, lineage_rel, b'test canonical lineage metadata')
    ground_truth = (
        synthetic_ground_truth(root) if gt == 'synthetic_created_after_freeze'
        else {'type': 'unavailable', 'reason': 'No verified labels in test fixture'}
    )
    ledger['week08_sources']=[{
        'source_id':'test_new', 'path':src.relative_to(root).as_posix(),
        'sha256':'0'*64 if alter_sha else h, 'format':'png',
        'role':'full_project_independent','previously_used':False,
        'prior_usage':[],
        'modality':'visible','reference_or_license':'Test fixture, not real data',
        'canonical_dataset_id':'test:independent', 'canonical_subject_id':'subject_new',
        'canonical_case_id':'case_new', 'canonical_acquisition_id':'visible_01',
        'canonical_source_id':'test:independent:subject_new:case_new:visible_01',
        'lineage_ancestors':['test:independent:subject_new'],
        'lineage_evidence':{'manifest_path':lineage_rel,'manifest_sha256':lineage_hash},
        'lineage_status':'test_fixture_attested', 'ground_truth':ground_truth,
    }]
    (root / pre.LEDGER_REL).write_text(json.dumps(ledger))


def test_missing_independent_source_blocks(tmp_path, source_bundle_available):
    r=inspect(stage(tmp_path)); assert r['readiness']=='BLOCK'
    assert status(r,'heldout_source_independence')=='BLOCK'
    assert status(r,'frozen_sources')=='PASS'
    assert status(r,'evidence_hashes')=='PASS'
    assert status(r,'day34_gt_firewall_contract')=='PASS'


def test_genuinely_new_source_allows_preflight_with_runner_warning(tmp_path):
    root=stage(tmp_path);register_independent(root)
    r=inspect(root)
    assert r['readiness']=='WARN', [(c['check'],c['status'],c.get('details')) for c in r['checks']]
    assert status(r,'heldout_source_independence')=='PASS'
    assert status(r,'week08_runner_identity_contract')=='WARN'


def test_policy_tamper_blocks(tmp_path):
    root=stage(tmp_path);p=root/pre.REQUIRED_EVIDENCE['day34_policy']
    policy=json.loads(p.read_text());policy['gate']['agreement_px']=999;p.write_text(json.dumps(policy))
    assert status(inspect(root),'evidence_hashes')=='BLOCK'


def test_missing_evidence_blocks_and_gives_restoration(tmp_path):
    root=stage(tmp_path);(root/pre.REQUIRED_EVIDENCE['day32_journal']).unlink()
    r=inspect(root)
    assert status(r,'evidence_hashes')=='BLOCK'
    assert status(r,'evidence_restoration')=='BLOCK'


def test_source_code_tamper_blocks(tmp_path):
    root=stage(tmp_path)
    f=next(x for x in json.loads((root/pre.FROZEN_REL).read_text())['frozen_files'] if x.endswith('phase_correlation.py'))
    with (root/f).open('a') as out: out.write('\n# changed test\n')
    assert status(inspect(root),'frozen_sources')=='BLOCK'


def test_duplicate_benchmark_id_blocks(tmp_path):
    root=stage(tmp_path)
    p=root/pre.REQUIRED_EVIDENCE['day32_journal'];lines=p.read_text().splitlines();lines[1]=lines[0]
    p.write_text('\n'.join(lines)+'\n')
    assert status(inspect(root),'evidence_hashes')=='BLOCK'
    a=pre.Audit(root); a.verify_journals()
    assert status({'checks':a.checks},'day32_journal_integrity')=='BLOCK'


def test_stale_heldout_path_rejected(tmp_path):
    root=stage(tmp_path);register_independent(root,reuse=True)
    r=inspect(root); assert status(r,'heldout_source_independence')=='BLOCK'
    assert any('Previously used' in x for c in r['checks'] if c['check']=='heldout_source_independence' for x in c['errors'])


def test_heldout_file_hash_failure_blocks(tmp_path):
    root=stage(tmp_path);register_independent(root,alter_sha=True)
    assert status(inspect(root),'heldout_source_independence')=='BLOCK'


def test_unknown_ground_truth_cannot_authorize_geometric_final(tmp_path):
    root=stage(tmp_path);register_independent(root,gt='unavailable')
    assert status(inspect(root),'heldout_source_independence')=='BLOCK'


def test_duplicate_source_ids_block(tmp_path):
    root=stage(tmp_path);register_independent(root)
    p=root/pre.LEDGER_REL;led=json.loads(p.read_text());led['week08_sources'].append(dict(led['week08_sources'][0]))
    p.write_text(json.dumps(led))
    assert status(inspect(root),'heldout_source_independence')=='BLOCK'


def test_path_traversal_and_abs_paths_forbidden(tmp_path):
    assert pre.safe_file(tmp_path,'../../etc/passwd') is None
    assert pre.safe_file(tmp_path,'/etc/passwd') is None
    assert pre.safe_file(tmp_path,'data\\etc') is None


def test_temp_directory_ancestor_link_does_not_block_safe_file(tmp_path, monkeypatch):
    """Only project members may be lstat'ed, not ancestors of the root."""
    root = tmp_path / "staged_repo"
    target = root / "configs" / "manifest.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    original_lstat = Path.lstat

    def check_stat(path):
        if path == tmp_path:
            raise AssertionError("inspected filesystem ancestor outside project root")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", check_stat)
    assert pre.safe_file(root, "configs/manifest.json") == target


def test_safe_file_rejects_internal_symlink_and_junction(tmp_path, monkeypatch):
    """Reject both POSIX-style links and Windows reparse-point metadata."""
    import stat
    from types import SimpleNamespace
    root = tmp_path / "project"
    internal = root / "redirect"
    internal.mkdir(parents=True)
    (internal / "result.txt").write_text("fixture")
    original_lstat = Path.lstat

    def fake_link(path):
        real = original_lstat(path)
        if path == internal:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        return real

    monkeypatch.setattr(Path, "lstat", fake_link)
    assert pre.safe_file(root, "redirect/result.txt") is None

    def fake_junction(path):
        real = original_lstat(path)
        if path == internal:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400)
        return real

    monkeypatch.setattr(Path, "lstat", fake_junction)
    assert pre.safe_file(root, "redirect/result.txt") is None


def test_safe_file_does_not_depend_on_path_resolution(tmp_path, monkeypatch):
    """Windows fixture path canonicalization must not block a safe file."""
    root = tmp_path / "staged_repo"
    target = root / "configs" / "baseline.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")

    def unexpected_resolve(path, *args, **kwargs):
        raise AssertionError("safe_file must not resolve paths outside its trust boundary")

    monkeypatch.setattr(Path, "resolve", unexpected_resolve)
    assert pre.safe_file(root, "configs/baseline.json") == target


def test_staged_fixture_has_all_expected_preflight_checks(tmp_path):
    """Every check stays visible, so a baseline problem cannot mask later gates."""
    report = inspect(stage(tmp_path))
    names = {c["check"] for c in report["checks"]}
    assert {"integrity_anchor", "week07_evidence_packaging", "frozen_sources",
            "evidence_hashes", "heldout_source_independence"} <= names
    assert status(report, "integrity_anchor") == "PASS"
    assert status(report, "week07_evidence_packaging") == "PASS"
    assert status(report, "frozen_sources") == "PASS"
    assert status(report, "evidence_hashes") == "PASS"
    assert status(report, "heldout_source_independence") == "BLOCK"


def test_archive_restoration_passes_preflight_in_clean_staging(tmp_path):
    report = inspect(stage_from_evidence_archive(tmp_path))
    for check in (
        'integrity_anchor', 'week07_evidence_packaging', 'frozen_sources',
        'week7_complete_evidence', 'evidence_hashes',
    ):
        assert status(report, check) == 'PASS'
    assert status(report, 'heldout_source_independence') == 'BLOCK'


def test_nonempty_final_folder_blocks(tmp_path):
    root=stage(tmp_path);p=root/'outputs/week08_final';p.mkdir(parents=True);(p/'old.json').write_text('x')
    assert status(inspect(root),'clean_week08_final')=='BLOCK'


def test_dry_run_does_not_write_report(tmp_path):
    root=stage(tmp_path)
    code=pre.main(['--root',str(root),'--dry-run'])
    assert code==1
    assert not (root/pre.REPORT_REL).exists()


def test_real_run_writes_blocked_report_without_loading_labels(tmp_path):
    root=stage(tmp_path)
    assert pre.main(['--root',str(root)])==1
    p=root/pre.REPORT_REL;assert p.is_file()
    report=json.loads(p.read_text())
    assert report['readiness']=='BLOCK' and report['week08_evaluation_executed'] is False


def test_frozen_policy_metadata_has_no_calibrated_confidence_claim():
    p=json.loads((ROOT/pre.REQUIRED_EVIDENCE['day34_policy']).read_text())
    assert p['independent_validation'] is False and p['status']=='exploratory_not_deployed'


def test_all_development_attempts_preserved_with_duplicate_detection():
    a=pre.Audit(ROOT);a.verify_journals()
    assert status({'checks':a.checks},'day32_journal_integrity')=='PASS'
    assert status({'checks':a.checks},'day35_journal_integrity')=='PASS'


def test_posix_manifest_paths_across_platforms(tmp_path):
    """WindowsPath.__str__ uses backslashes; the boundary must use as_posix()."""
    from pathlib import PureWindowsPath
    relative = PureWindowsPath("configs/week08_frozen_baseline.json")
    target = tmp_path / "configs" / "week08_frozen_baseline.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    assert "\\" in str(relative)
    assert pre.safe_file(tmp_path, str(relative)) is None
    assert pre.safe_file(tmp_path, relative.as_posix()) == target


def test_windows_rooted_drive_unc_paths_rejected_on_all_hosts(tmp_path):
    """Relative-to-drive paths must not become C:/... on Windows."""
    for rel in ("/etc/passwd", "C:/Windows/win.ini", "C:relative.txt",
                "//server/share/file", "dir/file:ads", "dir//file", "dir/./file"):
        assert pre.safe_file(tmp_path, rel) is None, rel


def test_frozen_inventory_requires_exact_101_and_81(tmp_path):
    root = stage(tmp_path)
    baseline = root / pre.FROZEN_REL
    value = json.loads(baseline.read_text())
    value['frozen_files'].pop(next(iter(value['frozen_files'])))
    value['week7_evidence_files']['outputs/week07_day02_full/unexpected.txt'] = '0' * 64
    baseline.write_text(json.dumps(value))
    report = inspect(root)
    assert status(report, 'frozen_sources') == 'BLOCK'
    assert status(report, 'week7_complete_evidence') == 'BLOCK'


def test_baseline_hash_syntax_fails_closed(tmp_path):
    root = stage(tmp_path)
    baseline = root / pre.FROZEN_REL
    value = json.loads(baseline.read_text())
    key = next(iter(value['frozen_files']))
    value['frozen_files'][key] = 'not-a-sha256'
    baseline.write_text(json.dumps(value))
    assert status(inspect(root), 'frozen_sources') == 'BLOCK'


def test_complete_evidence_immutability_depends_on_all_81_files(tmp_path):
    root = stage(tmp_path)
    baseline = json.loads((root / pre.FROZEN_REL).read_text())
    core = set(pre.REQUIRED_EVIDENCE.values())
    rel = next(path for path in baseline['week7_evidence_files'] if path not in core)
    with (root / rel).open('ab') as stream:
        stream.write(b'non-core tamper')
    report = inspect(root)
    assert status(report, 'evidence_hashes') == 'PASS'
    assert status(report, 'week7_complete_evidence') == 'BLOCK'
    assert report['development_evidence_immutable'] is False


def test_prior_inventory_requires_week1_and_rire_sources(tmp_path):
    required_ids = (
        'week01_fixed', 'week01_moving', 'rire_training001_ct', 'rire_training001_mr_t1',
    )
    for source_id in required_ids:
        root = stage(tmp_path / source_id)
        ledger_path = root / pre.LEDGER_REL
        ledger = json.loads(ledger_path.read_text())
        ledger['known_prior_sources'] = [
            entry for entry in ledger['known_prior_sources'] if entry['source_id'] != source_id
        ]
        ledger_path.write_text(json.dumps(ledger))
        assert status(inspect(root), 'prior_source_inventory') == 'BLOCK', source_id

    root = stage(tmp_path / 'week01_identity')
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    next(
        entry for entry in ledger['known_prior_sources'] if entry['source_id'] == 'week01_fixed'
    )['canonical_source_id'] = 'project:week01_smoke_pair:incorrect'
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'prior_source_inventory') == 'BLOCK'

    corruptions = (
        ('camera', 'canonical_source_id', 'scikit-image:data.not-camera'),
        ('rire_training001_ct', 'modality', 'arbitrary'),
        ('moon', 'role', 'development'),
    )
    for source_id, field, value in corruptions:
        root = stage(tmp_path / f'{source_id}_{field}')
        ledger_path = root / pre.LEDGER_REL
        ledger = json.loads(ledger_path.read_text())
        next(
            entry for entry in ledger['known_prior_sources'] if entry['source_id'] == source_id
        )[field] = value
        ledger_path.write_text(json.dumps(ledger))
        assert status(inspect(root), 'prior_source_inventory') == 'BLOCK', (source_id, field)


@pytest.mark.parametrize('change', ['missing', 'tampered'])
def test_known_prior_source_bytes_are_hashed_without_decoding(tmp_path, change):
    root = stage(tmp_path)
    ledger = json.loads((root / pre.LEDGER_REL).read_text())
    source = root / ledger['known_prior_sources'][0]['path']
    source.unlink()
    if change == 'tampered':
        source.write_bytes(b'tampered prior-source bytes')
    assert status(inspect(root), 'source_ledger_schema') == 'BLOCK'


@pytest.mark.parametrize('bad', [None, 0, 1, 'false'])
def test_previously_used_requires_a_real_boolean(tmp_path, bad):
    root = stage(tmp_path)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    ledger['known_prior_sources'][0]['previously_used'] = bad
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'source_ledger_schema') == 'BLOCK'


def test_modality_and_lineage_are_required(tmp_path):
    root = stage(tmp_path)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    ledger['known_prior_sources'][0].pop('modality')
    ledger['known_prior_sources'][1]['lineage_ancestors'] = []
    ledger['known_prior_sources'][2].pop('lineage_evidence')
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'source_ledger_schema') == 'BLOCK'


def test_malformed_and_duplicate_key_json_fail_closed_without_crashing(tmp_path):
    root = stage(tmp_path)
    ledger_path = root / pre.LEDGER_REL
    ledger_path.write_text('[]', encoding='utf-8')
    assert status(inspect(root), 'source_ledger_schema') == 'BLOCK'

    root = stage(tmp_path / 'duplicate')
    ledger_path = root / pre.LEDGER_REL
    content = ledger_path.read_text(encoding='utf-8')
    content = content.replace('"schema_version": 2', '"schema_version": 2, "schema_version": 2', 1)
    ledger_path.write_text(content, encoding='utf-8')
    assert status(inspect(root), 'source_ledger_schema') == 'BLOCK'

    root = stage(tmp_path / 'anchor')
    (root / pre.INTEGRITY_ANCHOR_REL).write_text('[]', encoding='utf-8')
    report = inspect(root)
    assert status(report, 'integrity_anchor') == 'BLOCK'
    assert report['development_evidence_immutable'] is False


def test_canonical_lineage_collision_blocks_renamed_source(tmp_path):
    root = stage(tmp_path)
    register_independent(root)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    source = ledger['week08_sources'][0]
    source['canonical_dataset_id'] = 'scikit-image:data'
    source['canonical_subject_id'] = 'not_applicable'
    source['canonical_case_id'] = 'camera'
    source['canonical_source_id'] = 'renamed-camera'
    source['lineage_ancestors'] = ['scikit-image:data.camera']
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'BLOCK'


def test_generic_gz_rejected_but_project_medical_formats_are_known(tmp_path):
    assert pre.normalized_format('case.nii.gz') == 'nii.gz'
    assert pre.normalized_format('case.mha') == 'mha'
    assert pre.normalized_format('case.mhd') == 'mhd'
    assert pre.normalized_format('case.gz') == 'gz'
    assert 'gz' not in pre.SUPPORTED_IMAGE_FORMATS


def test_mhd_source_requires_hashed_components(tmp_path):
    root = stage(tmp_path)
    register_independent(root)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    source = ledger['week08_sources'][0]
    old = root / source['path']
    new = old.with_suffix('.mhd')
    new.write_bytes(old.read_bytes())
    old.unlink()
    source['path'] = new.relative_to(root).as_posix()
    source['format'] = 'mhd'
    source['sha256'] = hashlib.sha256(new.read_bytes()).hexdigest()
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'BLOCK'

    raw_rel = 'data/holdout/week08/new_source.raw'
    raw_hash = write_fixture(root, raw_rel, b'mhd raw component fixture')
    source['components'] = [{'path': raw_rel, 'sha256': raw_hash}]
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'PASS'


def test_ground_truth_status_string_without_evidence_is_rejected(tmp_path):
    root = stage(tmp_path)
    register_independent(root)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    source = ledger['week08_sources'][0]
    source.pop('ground_truth')
    source['ground_truth_status'] = 'synthetic_created_after_freeze'
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'BLOCK'


def test_synthetic_ground_truth_hash_and_required_fields_fail_closed(tmp_path):
    root = stage(tmp_path)
    register_independent(root)
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    evidence = ledger['week08_sources'][0]['ground_truth']
    evidence['manifest_sha256'] = 'f' * 64
    evidence.pop('border_overlap_policy')
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'BLOCK'


def test_verified_landmark_evidence_requires_metadata_and_hashes(tmp_path):
    root = stage(tmp_path)
    register_independent(root)
    label_rel = 'data/holdout/week08/verified_landmarks.csv'
    label_hash = write_fixture(root, label_rel, b'fixed_x,fixed_y,moving_x,moving_y\n1,2,3,4\n')
    manifest_rel = 'data/holdout/week08/verified_landmarks_manifest.json'
    manifest_hash = write_fixture(root, manifest_rel, b'{"fixture":"verified landmarks"}\n')
    ledger_path = root / pre.LEDGER_REL
    ledger = json.loads(ledger_path.read_text())
    source = ledger['week08_sources'][0]
    source['ground_truth'] = {
        'type': 'verified_landmarks',
        'provenance': 'Independent fixture annotation',
        'reference_or_license': 'Test-only fixture annotation',
        'units': 'pixels',
        'coordinate_convention': 'zero-based x,y in fixed and moving images',
        'validation_notes': 'Fixture reviewed for schema coverage',
        'manifest_path': manifest_rel,
        'manifest_sha256': manifest_hash,
        'label_files': [{
            'role': 'paired_landmarks', 'path': label_rel, 'format': 'csv', 'sha256': label_hash,
        }],
    }
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'PASS'

    source['ground_truth'].pop('units')
    ledger_path.write_text(json.dumps(ledger))
    assert status(inspect(root), 'heldout_source_independence') == 'BLOCK'


def test_integrity_anchor_and_archive_manifest_tampering_block(tmp_path):
    root = stage(tmp_path)
    anchor = root / pre.INTEGRITY_ANCHOR_REL
    value = json.loads(anchor.read_text())
    value['expected_frozen_file_count'] = 100
    anchor.write_text(json.dumps(value))
    assert status(inspect(root), 'integrity_anchor') == 'BLOCK'

    root = stage(tmp_path / 'archive')
    package_path = root / pre.EVIDENCE_ARCHIVE_MANIFEST_REL
    package = json.loads(package_path.read_text())
    package['files'][0]['size_bytes'] += 1
    package_path.write_text(json.dumps(package))
    report = inspect(root)
    assert status(report, 'integrity_anchor') == 'BLOCK'
    assert status(report, 'week07_evidence_packaging') == 'BLOCK'


def test_final_readiness_explicitly_blocks_later_phase_artifacts(tmp_path):
    report = inspect(stage(tmp_path), final_readiness=True)
    assert report['readiness'] == 'BLOCK'
    assert report['mode'] == 'final_readiness'
    for code in (
        'week08_runner_identity_contract', 'strict_release_manifest',
        'strict_release_commit_tag', 'strict_policy_config_analysis_hashes',
        'strict_runner_validation', 'strict_clean_staging_restoration',
        'strict_stage_b_acceptance',
        'strict_release_signoffs', 'strict_dependency_environment',
        'strict_source_enrollment', 'strict_integrity_and_restoration',
    ):
        assert status(report, code) == 'BLOCK', code


def test_final_readiness_cli_dry_run_writes_nothing(tmp_path):
    root = stage(tmp_path)
    assert pre.main(['--root', str(root), '--dry-run', '--final-readiness']) == 1
    assert not (root / pre.REPORT_REL).exists()


def test_security_gates_do_not_use_optimizable_assert_statements():
    source = SCRIPT.read_text(encoding='utf-8')
    assert not any(line.lstrip().startswith('assert ') for line in source.splitlines())


def test_release_git_verification_checks_real_tag_ancestry_and_cleanliness(tmp_path):
    repository = tmp_path / 'release_git'
    repository.mkdir()

    def git(*args):
        return subprocess.run(
            ['git', '-C', str(repository), *args], check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    git('init')
    git('config', 'user.email', 'phase2-test@example.invalid')
    git('config', 'user.name', 'Phase 2 Test')
    (repository / 'release.txt').write_text('release\n', encoding='utf-8')
    git('add', 'release.txt')
    git('commit', '-m', 'release')
    release_commit = git('rev-parse', 'HEAD')
    git('tag', 'week08-release-test', release_commit)

    errors, _ = pre.verify_release_git(repository, release_commit, 'week08-release-test')
    assert errors == []

    enrollment = repository / pre.LEDGER_REL
    enrollment.parent.mkdir(parents=True)
    enrollment.write_text('{"schema_version":2,"week08_sources":[]}\n', encoding='utf-8')
    git('add', pre.LEDGER_REL.as_posix())
    git('commit', '-m', 'enrollment metadata')
    errors, observed = pre.verify_release_git(repository, release_commit, 'week08-release-test')
    assert errors == []
    assert observed['head'] != release_commit
    assert observed['post_release_changed_paths'] == [pre.LEDGER_REL.as_posix()]

    forbidden = repository / 'src/registration_algorithm.py'
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text('forbidden post-release change\n', encoding='utf-8')
    git('add', 'src/registration_algorithm.py')
    git('commit', '-m', 'forbidden code change')
    errors, _ = pre.verify_release_git(repository, release_commit, 'week08-release-test')
    assert any('Phase 6 metadata allowlist' in error for error in errors)

    (repository / 'dirty.txt').write_text('dirty\n', encoding='utf-8')
    errors, _ = pre.verify_release_git(repository, release_commit, 'week08-release-test')
    assert 'Git worktree is not clean' in errors
    errors, _ = pre.verify_release_git(repository, '0' * 40, 'week08-release-test')
    assert errors
