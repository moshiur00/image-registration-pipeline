from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/week08_r3_g3_remediation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("week08_r3_g3_remediation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r3_g3_remediation_report_is_self_hashed_bound_and_zero_access() -> None:
    result = load_module().validate()
    assert result["status"] == "PASS"
    assert result["fresh_sources"] == 0
    assert result["r3_evaluation_runs"] == 0
    assert result["next_gate"] == "G5_DISTINCT_RELEASE_REVIEW"
