"""Reproducible UI walkthrough fixtures and operator-attested acceptance log.

All generated artifacts are temporary UI QA files. The module never runs the
Week 8 evaluation or modifies frozen backend configuration and evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Final

import cv2
import numpy as np

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SOURCE: Final[Path] = ROOT / "data/samples/week02_real_general/camera.png"
RUNTIME: Final[Path] = ROOT / "ui/runtime/pre_week08_stage_b"
RECORD: Final[str] = "manual_acceptance.json"
SCHEMA_VERSION: Final[str] = "ui-stage-b-acceptance-v1"

SCENARIOS: Final[dict[str, str]] = {
    "multimodal": "Check multimodal method filtering and no ungrounded geometric claims",
    "single_candidate": "Check agreement abstains for exactly one eligible candidate",
    "failed_check": "Check failed/CHECK candidates and diagnostics remain visible and exportable",
    "stale_state": "Check changed inputs/settings invalidate existing result and prepared export",
    "export_provenance": "Check ZIP candidate records, statuses, raw-byte SHA256 and source exclusion",
}


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def prepare_fixtures(*, destination: Path = RUNTIME) -> dict:
    """Generate deterministic development-only UI fixtures outside frozen datasets."""
    source = cv2.imread(str(SOURCE), cv2.IMREAD_GRAYSCALE)
    if source is None:
        raise FileNotFoundError(f"Tracked development image unavailable: {SOURCE}")
    fixed = cv2.resize(source, (192, 192), interpolation=cv2.INTER_AREA)
    shift = np.float32([[1, 0, 5], [0, 1, -4]])
    moving = cv2.warpAffine(fixed, shift, (192, 192), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    simulated = np.uint8(255 - cv2.GaussianBlur(moving, (3, 3), 0.8))
    flat_fixed = np.full((192, 192), 112, dtype=np.uint8)
    flat_moving = np.full((192, 192), 136, dtype=np.uint8)
    altered_moving = np.uint8(np.clip(moving.astype(np.int16) + 22, 0, 255))
    images = {
        "paired_fixed.png": fixed,
        "paired_moving.png": moving,
        "multimodal_fixed.png": fixed,
        "multimodal_moving.png": simulated,
        "flat_fixed.png": flat_fixed,
        "flat_moving.png": flat_moving,
        "altered_moving.png": altered_moving,
    }
    destination.mkdir(parents=True, exist_ok=True)
    for name, array in images.items():
        success, content = cv2.imencode(".png", array)
        if not success:
            raise RuntimeError(f"Cannot encode UI QA image {name}")
        (destination / name).write_bytes(content.tobytes())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "MANUAL_UI_QA_ONLY_NOT_WEEK08_HELDOUT_DATA",
        "development_source": SOURCE.relative_to(ROOT).as_posix(),
        "geometry": "deterministic translation, display-only test fixtures",
        "files": {name: _sha(destination / name) for name in sorted(images)},
        "scenarios": SCENARIOS,
        "warning": "No scenario is marked passed by generating fixtures; real Streamlit checks require operator review.",
    }
    (destination / "fixtures_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_record(*, destination: Path = RUNTIME) -> dict:
    p = destination / RECORD
    if p.exists():
        value = json.loads(p.read_text(encoding="utf-8"))
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported UI acceptance record schema")
        if not isinstance(value.get("results"), dict):
            raise ValueError("Malformed acceptance results")
        return value
    return {"schema_version": SCHEMA_VERSION, "results": {}}


def record_manual_result(
    *, scenario: str, verdict: str, note: str, destination: Path = RUNTIME
) -> dict:
    """Record an explicit *human assertion*, not an automatically passed test."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown UI QA scenario: {scenario}")
    if verdict not in {"pass", "fail", "blocked"}:
        raise ValueError("Verdict must be pass, fail, or blocked")
    if not note.strip():
        raise ValueError("An operator observation is mandatory. Do not auto-pass manual checks.")
    if not (destination / "fixtures_manifest.json").is_file():
        raise ValueError("Prepare UI QA fixtures before recording acceptance")
    data = load_record(destination=destination)
    data["results"][scenario] = {
        "verdict": verdict,
        "note": note.strip(),
        "attested_utc": datetime.now(timezone.utc).isoformat(),
        "source": "manual_operator_assertion_not_automated_test",
    }
    (destination / RECORD).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def readiness(*, destination: Path = RUNTIME) -> dict:
    record = load_record(destination=destination)
    results = record["results"]
    unknown = set(results) - SCENARIOS.keys()
    if unknown:
        raise ValueError(f"Unexpected acceptance scenario(s): {sorted(unknown)}")
    statuses = {name: results.get(name, {}).get("verdict", "pending") for name in SCENARIOS}
    for value in statuses.values():
        if value not in {"pending", "pass", "fail", "blocked"}:
            raise ValueError("Invalid manual acceptance verdict")
    if any(value == "fail" for value in statuses.values()):
        state = "FAIL"
    elif any(value == "blocked" for value in statuses.values()):
        state = "BLOCKED"
    elif all(value == "pass" for value in statuses.values()):
        state = "MANUALLY_ACCEPTED"
    else:
        state = "PENDING_MANUAL_QA"
    return {
        "status": state,
        "scenarios": statuses,
        "passed": sum(value == "pass" for value in statuses.values()),
        "total": len(SCENARIOS),
        "limitations": "Manual acceptance alone does not establish Week 8 benchmark readiness or scientific calibration.",
    }
