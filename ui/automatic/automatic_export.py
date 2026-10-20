"""In-memory Stage 6.5 analysis archive for the automatic comparison preview.

All result evidence comes from the frozen automatic service view model. Images
are explicitly labeled inspection-only reconstructions, never original adapter
outputs. No files are written to research directories or runtime storage.
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from io import BytesIO, StringIO
import json
import math
import platform
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import cv2
import numpy as np

from ui.core.export_service import ExportPayload, _npy_bytes, _png_bytes
from ui.core.registration_service import hash_image_source
from ui.core.result_presenter import to_json_safe
from ui.streamlit.components.visuals import alpha_overlay, checkerboard, absolute_difference, edge_overlay

from .automatic_presenter import candidate_evidence_rows
from .agreement_presenter import descriptive_anchor_interpretation
from .automatic_service import _automatic_method_configuration, _pair_id
from .candidate_summary import execution_issues
from .candidate_inspection import can_inspect_image, reconstruct_visual_inspection
from .models import AutomaticComparisonRequest, AutomaticComparisonView


SCHEMA_VERSION = "ui-auto-analysis-v0.2"
INTERPOLATION = "linear"
SUPPORT_INTERPOLATION = "nearest"
ARCHIVE_DESCRIPTION = (
    "These are candidate comparisons with unknown geometric ground truth. "
    "Neither the descriptive transform medoid nor image similarity provides "
    "a calibrated winner or guaranteed geometric accuracy."
)


def _json(data: object) -> bytes:
    """Serialize abnormal nonfinite diagnostics as null, never invalid JSON."""
    def clean(item: object) -> object:
        if isinstance(item, dict):
            return {str(key): clean(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(value) for value in item]
        if isinstance(item, float) and not math.isfinite(item):
            return None
        return item
    return json.dumps(clean(to_json_safe(data)), indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def _csv(rows: list[dict[str, object]], fields: list[str]) -> bytes:
    buf = StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def _safe_name(identifier: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", identifier).strip("_")
    return text[:96] or "candidate"


def _add(archive: ZipFile, path: str, contents: bytes) -> None:
    entry = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    entry.external_attr = 0o644 << 16
    archive.writestr(entry, contents)


def build_automatic_analysis_export(
    *, request: AutomaticComparisonRequest, view: AutomaticComparisonView
) -> ExportPayload:
    """Build a self-contained, source-traceable comparison evidence ZIP in memory.

    Upload bytes are deliberately not included. For unknown pairs, reject
    unexpected reference metrics or a selected recommendation before export.
    A failed candidate does not prevent other candidates from being exported.
    """
    if view.preview.pair_id != _pair_id(request):
        raise ValueError("Export request and comparison pair identity do not match.")
    if (not request.include_optional_methods and any(item.optional for item in view.preview.compatible)) or (
        request.include_optional_methods and any(
            "optional_method_disabled" in item.reasons for item in view.preview.excluded
        )
    ):
        raise ValueError("Export request and comparison optional-method policy do not match.")
    if view.ground_truth_status != "unavailable" or view.preview.ground_truth_status != "unavailable":
        raise ValueError("Automatic comparison export requires unavailable ground truth.")
    if view.recommendation_status != "deferred_until_robustness_calibration":
        raise ValueError("Unexpected recommendation policy for the uncalibrated UI.")
    for candidate in view.candidates:
        if candidate.geometric_metrics or candidate.anatomical_metrics:
            raise ValueError("Unknown-ground-truth export must not contain reference metrics.")

    anchor_interpretation = descriptive_anchor_interpretation(view)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pair_id": view.preview.pair_id,
        "fixed_sha256": hash_image_source(request.fixed),
        "moving_sha256": hash_image_source(request.moving),
        "fixed_filename": request.fixed.display_name,
        "moving_filename": request.moving.display_name,
        "preprocessing": asdict(request.preprocessing),
        "requested_transform_model": request.transform_model.value,
        "modality_class": request.modality_class,
        "include_optional_methods": request.include_optional_methods,
        "candidate_count": len(view.candidates),
        "candidate_method_settings": [
            {
                "candidate_id": candidate.candidate_id,
                "method_id": candidate.method_id,
                "initialization": _automatic_method_configuration(candidate.method_id)[0],
                "method_parameters": _automatic_method_configuration(candidate.method_id)[1],
            }
            for candidate in view.candidates
        ],
        "compatible_count": view.preview.compatible_count,
        "excluded_count": view.preview.excluded_count,
        "ground_truth": "unavailable",
        "recommendation_status": view.recommendation_status,
        "transform_direction": "Moving -> Fixed",
        "preview_warp_interpolation": INTERPOLATION,
        "preview_border_fill": 0,
        "support_mask_method": "all-ones source support warped with nearest-neighbor interpolation",
        "support_mask_interpolation": SUPPORT_INTERPOLATION,
        "preview_provenance": "inspection-only reconstruction; original adapter registered arrays are not retained in the view model",
        "source_image_bytes_included": False,
        "software": {"python": platform.python_version(), "opencv": cv2.__version__, "numpy": np.__version__},
        "inspection_artifacts": [],
        "inspection_failures": [],
        "interpretation": ARCHIVE_DESCRIPTION,
        "consensus_presentation": anchor_interpretation,
    }

    csv_rows = candidate_evidence_rows(view)
    common_columns = ["Method", "Execution", "Transform", "MAE", "MSE", "NCC", "SSIM", "Evaluation MI", "Valid overlap", "Runtime (ms)"]
    issues = execution_issues(view)
    pairwise_rows = [item.to_dict() for item in view.agreement.pairwise]

    buf = BytesIO()
    with ZipFile(buf, "w") as archive:
        analysis = view.to_dict()
        analysis["agreement_presentation"] = anchor_interpretation
        _add(archive, "analysis.json", _json(analysis))
        _add(archive, "candidate_comparison.csv", _csv(csv_rows, common_columns))
        _add(archive, "candidate_execution_issues.csv", _csv(issues, ["Method", "Execution", "Failure reason", "Warnings"]))
        _add(archive, "pairwise_agreement.csv", _csv(pairwise_rows, ["candidate_a", "candidate_b", "method_a", "method_b", "display_name_a", "display_name_b", "rms_px", "median_px", "p95_px", "max_px", "normalized_rms"]))
        for index, candidate in enumerate(view.candidates, start=1):
            name = f"candidates/{index:02d}_{_safe_name(candidate.candidate_id)}/"
            _add(archive, name + "evidence.json", _json(candidate.to_dict()))
            if not can_inspect_image(candidate):
                continue
            try:
                fixed, moving, registered, valid_mask = reconstruct_visual_inspection(request, candidate)
                _add(archive, name + "fixed_preprocessed.png", _png_bytes(fixed))
                _add(archive, name + "moving_preprocessed.png", _png_bytes(moving))
                _add(archive, name + "registered_INSPECTION_ONLY.png", _png_bytes(registered))
                _add(archive, name + "registered_INSPECTION_ONLY.npy", _npy_bytes(registered))
                _add(archive, name + "geometric_source_support.png", _png_bytes(valid_mask.astype(np.uint8) * 255))
                for label, image in {
                    "overlay": alpha_overlay(fixed, registered, valid_mask=valid_mask),
                    "checkerboard": checkerboard(fixed, registered, valid_mask=valid_mask),
                    "difference": absolute_difference(fixed, registered, valid_mask=valid_mask),
                    "edges": edge_overlay(fixed, registered, valid_mask=valid_mask),
                }.items():
                    _add(archive, name + f"{label}_INSPECTION_ONLY.png", _png_bytes(image))
                manifest["inspection_artifacts"].append(candidate.candidate_id)
            except (ValueError, TypeError, cv2.error) as exc:
                manifest["inspection_failures"].append({"candidate_id": candidate.candidate_id, "reason": str(exc)})
        _add(archive, "manifest.json", _json(manifest))
        _add(archive, "README.txt", (
            "Image Registration Pipeline: UI v0.2 automatic comparison preview\n\n"
            "analysis.json: all candidates, terminal statuses, excluded methods, descriptive agreement.\n"
            "candidate_comparison.csv: normalized descriptive metrics and runtime.\n"
            "candidate_execution_issues.csv: real execution issues (does not repeat missing-GT notices).\n"
            "pairwise_agreement.csv: transform disagreement, not geometric accuracy.\n"
            "candidates/*/evidence.json: candidate transform and full raw method diagnostics.\n"
            "candidates/*/*INSPECTION_ONLY*: reconstructed images, NOT adapter-native outputs.\n"
            "candidates/*/geometric_source_support.png: warped source support, independent of image intensity.\n"
            "manifest.json: request context, method parameters, SHA256 hashes, software versions, interpolation, and artifact status.\n\n"
            "Source upload bytes are NOT packaged. Images are explicitly preprocessed previews.\n"
            "The .npy files preserve numeric reconstruction values; PNGs are display-normalized.\n"
            "The automatic service has no access to ground truth, and no accuracy claim is made.\n"
            "Agreement interpretation is in agreement_presentation (analysis.json) and consensus_presentation (manifest.json).\n"
            "A deterministic backend medoid does not imply unique consensus if centrality is tied.\n"
            "Final ranking and confidence await Week 7 calibration.\n"
            "Exports are generated in memory and never written into tracked research directories.\n"
        ).encode("utf-8"))

    return ExportPayload(filename=f"{_safe_name(view.preview.pair_id)}_automatic_analysis.zip", media_type="application/zip", data=buf.getvalue())
