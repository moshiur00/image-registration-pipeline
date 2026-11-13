"""Stage B automated acceptance support, not substitutes for manual UI QA."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import cv2
import numpy as np
import pytest

from ui.qa.stage_b_acceptance import (
    SCENARIOS, SUPPLEMENTAL_CHECKS, RECORD, ROOT, SCHEMA_VERSION, VALIDATION_SCHEMA_VERSION,
    build_validation_report, load_record, prepare_fixtures, readiness,
    record_manual_result, record_supplemental_result,
)
from ui.automatic.automatic_service import AutomaticComparisonService
from ui.automatic.models import AutomaticComparisonRequest
from ui.core.contracts import PreprocessingSpec
from ui.core.enums import TransformModel
from ui.streamlit.pages.automatic_comparison import build_uploaded_pair, ensure_current_comparison_state
from ui.automatic.automatic_presenter import comparison_signature


def _git_commit(repository: Path, revision: str = "HEAD") -> str:
    result = subprocess.run(
        [
            "git", "-c", f"safe.directory={repository.resolve().as_posix()}",
            "-C", str(repository), "rev-parse", revision,
        ],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _test_repository(root: Path) -> Path:
    repository = root / "acceptance_git"
    if (repository / ".git").is_dir():
        return repository
    repository.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        )

    git("init")
    git("config", "user.email", "stage-b-test@example.invalid")
    git("config", "user.name", "Stage B Test")
    tracked = repository / "tracked.txt"
    tracked.write_text("initial\n")
    git("add", "tracked.txt")
    git("commit", "-m", "initial")
    tracked.write_text("tested UI\n")
    git("add", "tracked.txt")
    git("commit", "-m", "tested UI")
    return repository


def _readiness(root: Path) -> dict:
    return readiness(destination=root, repository_root=_test_repository(root))


def _load_record(root: Path) -> dict:
    return load_record(destination=root, repository_root=_test_repository(root))


@pytest.fixture
def qa(tmp_path):
    result = prepare_fixtures(destination=tmp_path)
    return tmp_path, result


def _evidence(root: Path, scenario: str, *, with_zip: bool = False) -> tuple[list[str], list[str]]:
    screenshot = root / f"{scenario}.png"
    screenshot_pixels = np.full((8, 8, 3), len(scenario), dtype=np.uint8)
    encoded, screenshot_bytes = cv2.imencode(".png", screenshot_pixels)
    assert encoded
    screenshot.write_bytes(screenshot_bytes.tobytes())
    zips: list[str] = []
    if with_zip:
        archive = root / f"{scenario}.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("analysis.json", "{}")
        zips.append(archive.name)
    return [screenshot.name], zips


def _record(
    root: Path,
    scenario: str,
    verdict: str = "pass",
    *,
    note: str | None = None,
    with_zip: bool | None = None,
    **overrides,
):
    screenshots, zips = _evidence(
        root,
        scenario,
        with_zip=scenario in {"single_candidate", "failed_check", "export_provenance"}
        if with_zip is None else with_zip,
    )
    repository_root = Path(overrides.pop("repository_root", _test_repository(root)))
    release_commit = overrides.pop("release_commit", _git_commit(repository_root))
    values = {
        "scenario": scenario,
        "verdict": verdict,
        "reviewer": "Windows QA Reviewer",
        "platform": "Windows 11 x64",
        "environment": "project .venv; Python 3.13; Streamlit",
        "release_commit": release_commit,
        "note": note if note is not None else f"Observed {scenario} in Streamlit",
        "screenshots": screenshots,
        "zips": zips,
        "destination": root,
        "repository_root": repository_root,
    }
    values.update(overrides)
    return record_manual_result(**values)


def _record_supplemental(
    root: Path,
    check: str,
    verdict: str = "pass",
    *,
    note: str | None = None,
    **overrides,
):
    screenshots, _ = _evidence(root, f"supplemental_{check}")
    repository_root = Path(overrides.pop("repository_root", _test_repository(root)))
    release_commit = overrides.pop("release_commit", _git_commit(repository_root))
    values = {
        "check": check,
        "verdict": verdict,
        "reviewer": "Windows QA Reviewer",
        "platform": "Windows 11 x64",
        "environment": "project .venv; Python 3.13; Streamlit",
        "release_commit": release_commit,
        "note": note if note is not None else f"Observed supplemental check {check}",
        "screenshots": screenshots,
        "destination": root,
        "repository_root": repository_root,
    }
    values.update(overrides)
    return record_supplemental_result(**values)


def test_fixtures_have_expected_raw_byte_hashes(qa):
    root, manifest = qa
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["purpose"] == "MANUAL_UI_QA_ONLY_NOT_WEEK08_HELDOUT_DATA"
    assert len(manifest["files"]) == 7
    for name, digest in manifest["files"].items():
        path = root / name
        assert digest == sha256(path.read_bytes()).hexdigest()
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        assert image is not None and image.shape == (192, 192)


def test_fixtures_reproducible_and_do_not_reset_manual_results(qa):
    root, manifest = qa
    _record(root, "multimodal")
    second = prepare_fixtures(destination=root)
    assert second["files"] == manifest["files"]
    assert _load_record(root)["results"]["multimodal"]["verdict"] == "pass"


def test_qa_pairs_are_development_fixtures_not_heldout(qa):
    root, manifest = qa
    assert "week02_real_general/camera.png" in manifest["development_source"]
    fixed = cv2.imread(str(root / "paired_fixed.png"), 0)
    moving = cv2.imread(str(root / "paired_moving.png"), 0)
    multi = cv2.imread(str(root / "multimodal_moving.png"), 0)
    assert not np.array_equal(fixed, moving)
    assert not np.array_equal(moving, multi)
    assert float(np.std(multi)) > 10.0


def test_flat_pair_exposes_low_texture_failure_fixture(qa):
    root, _ = qa
    for name in ("flat_fixed.png", "flat_moving.png"):
        arr = cv2.imread(str(root / name), 0)
        assert np.std(arr) == 0


def test_manual_status_starts_pending_even_when_fixtures_generated(qa):
    root, _ = qa
    r = _readiness(root)
    assert r["status"] == "PENDING_MANUAL_QA"
    assert r["passed"] == 0
    assert all(value == "pending" for value in r["scenarios"].values())
    assert r["supplemental_passed"] == 0
    assert all(value == "pending" for value in r["supplemental"].values())
    assert not (root / RECORD).exists()


@pytest.mark.parametrize("bad", ["", "  ", "\n"])
def test_manual_record_requires_specific_operator_observation(qa, bad):
    root, _ = qa
    with pytest.raises(ValueError, match="operator observation"):
        _record(root, "multimodal", note=bad)
    assert _readiness(root)["passed"] == 0


def test_manual_record_rejects_invented_scenarios_and_verdicts(qa):
    root, _ = qa
    with pytest.raises(ValueError, match="Unknown"):
        _record(root, "fake")
    with pytest.raises(ValueError, match="Verdict"):
        _record(root, "multimodal", verdict="skipped")


def test_manual_record_requires_prepared_fixtures(tmp_path):
    with pytest.raises(ValueError, match="Prepare"):
        _record(tmp_path, "multimodal")


def test_manual_acceptance_requires_all_scenarios_attested(qa):
    root, _ = qa
    for scenario in list(SCENARIOS)[:-1]:
        _record(root, scenario)
    assert _readiness(root)["status"] == "PENDING_MANUAL_QA"
    _record(root, "export_provenance", note="Checked manifest against uploaded PNG hashes")
    assert _readiness(root)["status"] == "PENDING_MANUAL_QA"
    for check in SUPPLEMENTAL_CHECKS:
        _record_supplemental(root, check)
    assert _readiness(root)["status"] == "MANUALLY_ACCEPTED"


def test_failure_or_blocked_prevents_manual_acceptance(qa):
    root, _ = qa
    _record(root, "multimodal", verdict="blocked", note="MI not installed")
    assert _readiness(root)["status"] == "BLOCKED"
    _record(root, "multimodal", verdict="fail", note="Unexpected missing diagnostic")
    assert _readiness(root)["status"] == "FAIL"


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("reviewer", " ", "Reviewer identity"),
        ("platform", "", "Windows/platform"),
        ("environment", "\n", "Environment"),
        ("release_commit", "ABC", "40 lowercase"),
    ],
)
def test_manual_record_requires_reviewer_environment_and_exact_commit(qa, field, value, match):
    root, _ = qa
    with pytest.raises(ValueError, match=match):
        _record(root, "multimodal", **{field: value})


def test_manual_record_binds_and_rechecks_local_evidence_hashes(qa):
    root, _ = qa
    result = _record(root, "multimodal")
    entry = result["results"]["multimodal"]
    assert entry["source"] == "human_windows_operator_assertion_not_automated_test"
    assert entry["release_commit"] == _git_commit(_test_repository(root))
    assert entry["fixture_manifest_sha256"] == sha256(
        (root / "fixtures_manifest.json").read_bytes()
    ).hexdigest()
    assert entry["screenshots"][0]["reference"] == "multimodal.png"
    assert entry["screenshots"][0]["sha256"] == sha256((root / "multimodal.png").read_bytes()).hexdigest()
    (root / "multimodal.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash/size"):
        _readiness(root)


def test_manifest_change_invalidates_scenario_and_supplemental_records(qa):
    root, _ = qa
    _record(root, "multimodal")
    _record_supplemental(root, "normal_monomodal")
    manifest_path = root / "fixtures_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["warning"] += " changed"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="current fixture manifest"):
        _readiness(root)


def test_new_record_requires_existing_exact_checked_out_head(qa):
    root, _ = qa
    repository = _test_repository(root)
    with pytest.raises(ValueError, match="does not exist"):
        _record(root, "multimodal", release_commit="f" * 40)
    with pytest.raises(ValueError, match="checked-out HEAD"):
        _record(root, "multimodal", release_commit=_git_commit(repository, "HEAD^"))
    with pytest.raises(ValueError, match="checked-out HEAD"):
        _record_supplemental(
            root,
            "normal_monomodal",
            release_commit=_git_commit(repository, "HEAD^"),
        )
    _record(root, "multimodal", release_commit=_git_commit(repository))
    assert _readiness(root)["scenarios"]["multimodal"] == "pass"


def test_existing_record_remains_valid_after_head_advances(qa, tmp_path):
    root, _ = qa
    repository = tmp_path / "recording_repo"
    repository.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.email", "stage-b-test@example.invalid")
    git("config", "user.name", "Stage B Test")
    tracked = repository / "tracked.txt"
    tracked.write_text("tested UI\n")
    git("add", "tracked.txt")
    git("commit", "-m", "tested UI")
    tested_head = git("rev-parse", "HEAD")
    _record(
        root,
        "multimodal",
        release_commit=tested_head,
        repository_root=repository,
    )
    tracked.write_text("later evidence commit\n")
    git("add", "tracked.txt")
    git("commit", "-m", "later evidence")
    assert git("rev-parse", "HEAD") != tested_head
    assert readiness(
        destination=root,
        repository_root=repository,
    )["scenarios"]["multimodal"] == "pass"


def test_recording_requires_clean_worktree_but_allows_ignored_runtime(tmp_path):
    repository = tmp_path / "clean_worktree_repo"
    repository.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.email", "stage-b-test@example.invalid")
    git("config", "user.name", "Stage B Test")
    (repository / ".gitignore").write_text("runtime/\n")
    protected = repository / "protected.py"
    protected.write_text("frozen = True\n")
    git("add", ".gitignore", "protected.py")
    git("commit", "-m", "tested UI")
    tested_head = git("rev-parse", "HEAD")
    runtime = repository / "runtime"
    prepare_fixtures(destination=runtime)

    _record(
        runtime,
        "multimodal",
        release_commit=tested_head,
        repository_root=repository,
    )
    _record_supplemental(
        runtime,
        "normal_monomodal",
        release_commit=tested_head,
        repository_root=repository,
    )
    assert git("status", "--porcelain", "--untracked-files=all") == ""

    protected.write_text("frozen = False\n")
    with pytest.raises(ValueError, match="worktree must be clean"):
        _record(
            runtime,
            "stale_state",
            release_commit=tested_head,
            repository_root=repository,
        )
    protected.write_text("frozen = True\n")

    untracked = repository / "untracked_protected.py"
    untracked.write_text("unreviewed = True\n")
    with pytest.raises(ValueError, match="worktree must be clean"):
        _record_supplemental(
            runtime,
            "candidate_inspection_labels",
            release_commit=tested_head,
            repository_root=repository,
        )
    untracked.unlink()


def test_manual_record_rejects_evidence_outside_runtime(qa, tmp_path):
    root, _ = qa
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="must remain under"):
        _record(root, "multimodal", screenshots=[outside])


def test_passed_export_scenarios_require_zip_evidence(qa):
    root, _ = qa
    with pytest.raises(ValueError, match="ZIP evidence"):
        _record(root, "export_provenance", with_zip=False)
    _record(root, "export_provenance", with_zip=True)
    assert _readiness(root)["scenarios"]["export_provenance"] == "pass"


def test_sanitized_validation_report_derives_freeze_and_exact_counts(qa):
    root, _ = qa
    for scenario in SCENARIOS:
        _record(root, scenario)
    for check in SUPPLEMENTAL_CHECKS:
        _record_supplemental(root, check)
    scope = {
        "stage_c_research_evidence": "DEFERRED",
        "interactive_rire_expansion": "DEFERRED",
        "recommendation_display_path": "DEFERRED",
    }
    report = build_validation_report(
        backend_passed=690,
        backend_skipped=3,
        backend_failed=0,
        ui_passed=180,
        ui_skipped=0,
        ui_failed=0,
        scope_decisions=scope,
        destination=root,
        repository_root=_test_repository(root),
    )
    assert report["schema_version"] == VALIDATION_SCHEMA_VERSION
    assert report["manual_cases_accepted"] == 5
    assert report["supplemental_checks_accepted"] == 5
    assert report["formal_ui_v02_frozen"] is True
    assert report["automated_validation"]["backend"] == {
        "passed": 690, "skipped": 3, "failed": 0,
    }
    serialized = json.dumps(report)
    assert str(root) not in serialized
    assert "screenshot:multimodal" not in serialized
    assert report["scenarios"]["multimodal"]["screenshots"][0]["sha256"]
    failed = build_validation_report(
        backend_passed=689,
        backend_skipped=3,
        backend_failed=1,
        ui_passed=180,
        ui_skipped=0,
        ui_failed=0,
        scope_decisions=scope,
        destination=root,
        repository_root=_test_repository(root),
    )
    assert failed["formal_ui_v02_frozen"] is False


def test_validation_report_rejects_mixed_commit_or_incomplete_scope(qa, tmp_path):
    root, _ = qa
    repository = tmp_path / "mixed_commit_repo"
    repository.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.email", "stage-b-test@example.invalid")
    git("config", "user.name", "Stage B Test")
    tracked = repository / "tracked.txt"
    tracked.write_text("first\n")
    git("add", "tracked.txt")
    git("commit", "-m", "first")
    first = git("rev-parse", "HEAD")
    _record(root, "multimodal", release_commit=first, repository_root=repository)
    tracked.write_text("second\n")
    git("add", "tracked.txt")
    git("commit", "-m", "second")
    second = git("rev-parse", "HEAD")
    _record(root, "single_candidate", release_commit=second, repository_root=repository)
    counts = {
        "backend_passed": 1, "backend_skipped": 0, "backend_failed": 0,
        "ui_passed": 1, "ui_skipped": 0, "ui_failed": 0,
    }
    with pytest.raises(ValueError, match="one commit"):
        build_validation_report(
            **counts,
            scope_decisions={
                "stage_c_research_evidence": "DEFERRED",
                "interactive_rire_expansion": "DEFERRED",
                "recommendation_display_path": "DEFERRED",
            },
            destination=root,
            repository_root=repository,
        )
    with pytest.raises(ValueError, match="exactly"):
        build_validation_report(
            **counts,
            scope_decisions={"stage_c_research_evidence": "DEFERRED"},
            destination=root,
            repository_root=repository,
        )


def test_tampered_record_schema_fails_closed(qa):
    root, _ = qa
    (root / RECORD).write_text(json.dumps({"schema_version": "unexpected", "results": {}}))
    with pytest.raises(ValueError, match="schema"):
        _readiness(root)


def test_multimodal_affine_single_candidate_compatibility(qa):
    root, _ = qa
    pair = build_uploaded_pair(
        fixed_name="multimodal_fixed.png", fixed_bytes=(root / "multimodal_fixed.png").read_bytes(),
        moving_name="multimodal_moving.png", moving_bytes=(root / "multimodal_moving.png").read_bytes(),
    )
    req = AutomaticComparisonRequest(
        fixed=pair.fixed_source, moving=pair.moving_source,
        transform_model=TransformModel.AFFINE, modality_class="multimodal",
        preprocessing=PreprocessingSpec(), include_optional_methods=True,
    )
    preview = AutomaticComparisonService().preview(req)
    assert preview.ground_truth_status == "unavailable"
    assert [candidate.method_id for candidate in preview.compatible] == ["mi_affine_2d"]
    assert any("modality_class_not_supported" in ex.reasons for ex in preview.excluded)
    changed = replace(req, preprocessing=PreprocessingSpec(gaussian_sigma=0.5))
    changed_preview = AutomaticComparisonService().preview(changed)
    assert preview.pair_id != changed_preview.pair_id
    assert comparison_signature(preview) != comparison_signature(changed_preview)


def test_stale_results_clear_selection_and_prepared_export():
    state = {
        "ui_auto_result_signature": "old", "ui_auto_result": object(),
        "ui_auto_export_payload": b"stale", "ui_auto_visual_candidate": "old",
        "ui_auto_fixed_upload": "preserve upload", "ui_auto_modality_class": "Multimodal",
    }
    assert not ensure_current_comparison_state(state, "changed")
    assert all(key not in state for key in (
        "ui_auto_result", "ui_auto_result_signature", "ui_auto_export_payload", "ui_auto_visual_candidate"
    ))
    assert state["ui_auto_fixed_upload"] == "preserve upload"


def test_qa_cli_help_runs_from_project_root():
    runner = ROOT / "scripts/pre_week08_stage_b_ui_qa.py"
    result = subprocess.run([sys.executable, str(runner), "--help"],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert all(command in result.stdout for command in ("prepare", "record", "record-supplemental", "report"))
    record_help = subprocess.run(
        [sys.executable, str(runner), "record-supplemental", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert record_help.returncode == 0
    assert "--reviewer" in record_help.stdout and "--screenshot" in record_help.stdout
    incomplete = subprocess.run(
        [sys.executable, str(runner), "record", "multimodal", "pass"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert incomplete.returncode == 2
    assert "--reviewer" in incomplete.stderr


def test_frozen_week7_code_is_not_imported_from_qa_module():
    source = (ROOT / "ui/qa/stage_b_acceptance.py").read_text(encoding="utf-8")
    assert "import streamlit" not in source
    assert "week08_final" not in source
    assert "RegistrationService" not in source
