"""Stage A preflight: integrity/leakage and holdout source audit tests."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/week08_preflight.py'
spec = importlib.util.spec_from_file_location('week08_preflight_script', SCRIPT)
assert spec and spec.loader
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)


def stage(tmp_path: Path, *, evidence=True) -> Path:
    paths = [*list(pre.REQUIRED_EVIDENCE.values()), str(pre.FROZEN_REL), str(pre.LEDGER_REL),
             str(pre.HANDOFF_REL), str(pre.CLOSURE_REL),
             'data/manifests/general_real_sources.json',
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
    for rel in set(paths):
        source = ROOT / rel
        if not source.exists():
            pytest.skip(f'Full Week 7 evidence missing from local test fixture: {source}')
        dest = tmp_path / rel; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source,dest)
    return tmp_path


@pytest.fixture(scope='module')
def source_bundle_available():
    assert (ROOT / pre.REQUIRED_EVIDENCE['day34_policy']).exists(), 'Stage A package must contain frozen evidence'


def inspect(root: Path):
    return pre.Audit(root).run()


def status(report, code):
    """Report the upstream gate reason rather than hiding it with StopIteration."""
    for check in report["checks"]:
        if check["check"] == code:
            return check["status"]
    observed = [(c["check"], c["status"], c.get("details")) for c in report["checks"]]
    pytest.fail(f"Expected preflight check {code!r} was not emitted. Observed checks: {observed}")


def register_independent(root, *, reuse=False, gt='synthetic_created_after_freeze', alter_sha=False):
    ledger = json.loads((root / pre.LEDGER_REL).read_text())
    src = root / ('data/samples/week02_real_general/moon.png' if reuse else 'data/holdout/week08/new_source.png')
    if reuse:
        original = ROOT / 'data/samples/week02_real_general/moon.png'
        src.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(original,src)
    else:
        src.parent.mkdir(parents=True, exist_ok=True);src.write_bytes(b'new independent raw source fixture bytes')
    h = hashlib.sha256(src.read_bytes()).hexdigest()
    ledger['week08_sources']=[{'source_id':'test_new', 'path':src.relative_to(root).as_posix(),
                              'sha256':'0'*64 if alter_sha else h,
                              'role':'full_project_independent','previously_used':False,
                              'modality':'visible','reference_or_license':'Test fixture, not real data',
                              'ground_truth_status':gt}]
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
    assert {"frozen_sources", "evidence_hashes", "heldout_source_independence"} <= names
    assert status(report, "frozen_sources") == "PASS"
    assert status(report, "evidence_hashes") == "PASS"
    assert status(report, "heldout_source_independence") == "BLOCK"


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
