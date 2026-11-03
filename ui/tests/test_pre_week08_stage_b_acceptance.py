"""Stage B automated acceptance support, not substitutes for manual UI QA."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import pytest

from ui.qa.stage_b_acceptance import (
    SCENARIOS, RECORD, ROOT, SCHEMA_VERSION, load_record, prepare_fixtures,
    readiness, record_manual_result,
)
from ui.automatic.automatic_service import AutomaticComparisonService
from ui.automatic.models import AutomaticComparisonRequest
from ui.core.contracts import PreprocessingSpec
from ui.core.enums import TransformModel
from ui.streamlit.pages.automatic_comparison import build_uploaded_pair, ensure_current_comparison_state
from ui.automatic.automatic_presenter import comparison_signature


@pytest.fixture
def qa(tmp_path):
    result = prepare_fixtures(destination=tmp_path)
    return tmp_path, result


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
    record_manual_result(scenario="multimodal", verdict="pass", note="Observed multimodal filtering in Streamlit", destination=root)
    second = prepare_fixtures(destination=root)
    assert second["files"] == manifest["files"]
    assert load_record(destination=root)["results"]["multimodal"]["verdict"] == "pass"


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
    r = readiness(destination=root)
    assert r["status"] == "PENDING_MANUAL_QA"
    assert r["passed"] == 0
    assert all(value == "pending" for value in r["scenarios"].values())
    assert not (root / RECORD).exists()


@pytest.mark.parametrize("bad", ["", "  ", "\n"])
def test_manual_record_requires_specific_operator_observation(qa, bad):
    root, _ = qa
    with pytest.raises(ValueError, match="operator observation"):
        record_manual_result(scenario="multimodal", verdict="pass", note=bad, destination=root)
    assert readiness(destination=root)["passed"] == 0


def test_manual_record_rejects_invented_scenarios_and_verdicts(qa):
    root, _ = qa
    with pytest.raises(ValueError, match="Unknown"):
        record_manual_result(scenario="fake", verdict="pass", note="observed", destination=root)
    with pytest.raises(ValueError, match="Verdict"):
        record_manual_result(scenario="multimodal", verdict="skipped", note="observed", destination=root)


def test_manual_record_requires_prepared_fixtures(tmp_path):
    with pytest.raises(ValueError, match="Prepare"):
        record_manual_result(scenario="multimodal", verdict="pass", note="observed", destination=tmp_path)


def test_manual_acceptance_requires_all_scenarios_attested(qa):
    root, _ = qa
    for scenario in list(SCENARIOS)[:-1]:
        record_manual_result(scenario=scenario, verdict="pass", note=f"Verified {scenario} manually", destination=root)
    assert readiness(destination=root)["status"] == "PENDING_MANUAL_QA"
    record_manual_result(scenario="export_provenance", verdict="pass", note="Checked manifest against uploaded PNG hashes", destination=root)
    assert readiness(destination=root)["status"] == "MANUALLY_ACCEPTED"


def test_failure_or_blocked_prevents_manual_acceptance(qa):
    root, _ = qa
    record_manual_result(scenario="multimodal", verdict="blocked", note="MI not installed", destination=root)
    assert readiness(destination=root)["status"] == "BLOCKED"
    record_manual_result(scenario="multimodal", verdict="fail", note="Unexpected missing diagnostic", destination=root)
    assert readiness(destination=root)["status"] == "FAIL"


def test_tampered_record_schema_fails_closed(qa):
    root, _ = qa
    (root / RECORD).write_text(json.dumps({"schema_version": "unexpected", "results": {}}))
    with pytest.raises(ValueError, match="schema"):
        readiness(destination=root)


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
    assert "prepare" in result.stdout and "record" in result.stdout


def test_frozen_week7_code_is_not_imported_from_qa_module():
    source = (ROOT / "ui/qa/stage_b_acceptance.py").read_text(encoding="utf-8")
    assert "import streamlit" not in source
    assert "week08_final" not in source
    assert "RegistrationService" not in source
