from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

import cv2
import numpy as np

from ui.core.contracts import DiagnosticSummary, MetricSummary, ProvenanceSummary, RegistrationRun, TransformSummary
from ui.core.enums import GroundTruthStatus, RunStatus, TransformModel
from ui.core.export_service import build_run_exports, comparison_figure, transform_payload


def _run() -> RegistrationRun:
    registered = np.arange(64, dtype=np.float32).reshape(8, 8)
    return RegistrationRun(
        request_id="ui-test-run",
        run_status=RunStatus.COMPLETED,
        method_success=True,
        transform=TransformSummary(
            matrix=np.eye(3, dtype=np.float64),
            motion_model=TransformModel.AFFINE,
            direction="moving_to_fixed",
            parameters={"matrix_offset_tx": 1.25, "matrix_offset_ty": -2.5},
            plausible=True,
        ),
        metrics=MetricSummary(before={"ncc": 0.5}, after={"ncc": 0.9}),
        diagnostics=DiagnosticSummary(values={"final_ecc": 0.99}),
        runtime_seconds=0.02,
        warnings=("Ground truth is unavailable; TRE and geometric PASS are not reported.",),
        provenance=ProvenanceSummary(
            fixed_sha256="a" * 64,
            moving_sha256="b" * 64,
            method_id="ecc_affine",
            normalized_parameters={"iterations": 150},
            preprocessing={"normalization": None},
            transform_direction="moving_to_fixed",
            package_version="0.1.0",
            ground_truth_status=GroundTruthStatus.UNAVAILABLE,
        ),
        registered_array=registered,
    )


def test_transform_payload_preserves_project_direction_and_matrix() -> None:
    payload = transform_payload(_run())
    assert payload["direction"] == "moving_to_fixed"
    assert payload["motion_model"] == "affine"
    assert np.asarray(payload["matrix"]).shape == (3, 3)


def test_comparison_figure_contains_three_labeled_panels() -> None:
    fixed = np.zeros((20, 24), dtype=np.uint8)
    moving = np.full((20, 24), 80, dtype=np.uint8)
    registered = np.full((20, 24), 160, dtype=np.uint8)
    figure = comparison_figure(fixed, moving, registered)
    assert figure.dtype == np.uint8
    assert figure.ndim == 3 and figure.shape[2] == 3
    assert figure.shape[0] == 62
    assert figure.shape[1] > 72


def test_build_run_exports_creates_expected_payloads_and_bundle() -> None:
    run = _run()
    fixed = np.zeros((8, 8), dtype=np.float32)
    moving = np.ones((8, 8), dtype=np.float32)
    exports = build_run_exports(run=run, fixed=fixed, moving=moving)

    assert set(exports) == {
        "registered_png",
        "transform_json",
        "summary_json",
        "comparison_png",
        "bundle_zip",
    }

    decoded = cv2.imdecode(np.frombuffer(exports["registered_png"].data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert decoded is not None and decoded.shape == (8, 8)

    transform = json.loads(exports["transform_json"].data)
    assert transform["direction"] == "moving_to_fixed"
    summary = json.loads(exports["summary_json"].data)
    assert "registered_array" not in summary
    assert summary["provenance"]["method_id"] == "ecc_affine"

    with ZipFile(BytesIO(exports["bundle_zip"].data)) as archive:
        assert set(archive.namelist()) == {
            "registered.png",
            "registered_array.npy",
            "transform.json",
            "summary.json",
            "comparison.png",
            "README.txt",
        }
        full_precision = np.load(BytesIO(archive.read("registered_array.npy")), allow_pickle=False)
        np.testing.assert_array_equal(full_precision, run.registered_array)
        assert "tracked research reports" in archive.read("README.txt").decode("utf-8")
