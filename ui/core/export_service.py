"""Framework-neutral in-memory export helpers for one registration run.

The export layer never writes to tracked research directories. It produces byte
payloads that presentation layers can offer for download or API transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np

from .contracts import RegistrationRun
from .result_presenter import registration_run_summary, to_json_safe


@dataclass(frozen=True, slots=True)
class ExportPayload:
    """One in-memory downloadable artifact."""

    filename: str
    media_type: str
    data: bytes


def _display_uint8(image: np.ndarray) -> np.ndarray:
    """Convert numeric image data to a robust 8-bit display representation."""
    values = np.asarray(image)
    if values.ndim == 3 and values.shape[2] in {3, 4}:
        if values.dtype == np.uint8:
            return values[..., :3].copy()
        values = values[..., :3].astype(np.float32)
    elif values.ndim == 3:
        values = values[..., 0].astype(np.float32)
    else:
        values = values.astype(np.float32)

    if values.dtype == np.uint8:
        return values.copy()

    low = float(np.nanpercentile(values, 1.0))
    high = float(np.nanpercentile(values, 99.0))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(np.nanmin(values))
        high = float(np.nanmax(values))
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    return np.rint(scaled * 255.0).astype(np.uint8)


def _png_bytes(image: np.ndarray) -> bytes:
    display = _display_uint8(image)
    encoded_input = display
    if display.ndim == 3 and display.shape[2] == 3:
        encoded_input = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".png", encoded_input)
    if not ok:
        raise ValueError("Could not encode image as PNG.")
    return encoded.tobytes()


def _json_bytes(payload: object) -> bytes:
    return json.dumps(to_json_safe(payload), indent=2, sort_keys=True).encode("utf-8")


def transform_payload(run: RegistrationRun) -> dict[str, object]:
    """Return the project-direction transform as a standalone JSON-safe payload."""
    transform = run.transform
    if transform is None:
        return {
            "request_id": run.request_id,
            "transform": None,
            "reason": "No transform was returned for this run.",
        }
    return {
        "request_id": run.request_id,
        "direction": transform.direction,
        "motion_model": transform.motion_model.value,
        "matrix": transform.matrix,
        "parameters": transform.parameters,
        "plausible": transform.plausible,
        "plausibility_reasons": transform.plausibility_reasons,
    }


def _as_rgb(image: np.ndarray) -> np.ndarray:
    display = _display_uint8(image)
    if display.ndim == 2:
        return cv2.cvtColor(display, cv2.COLOR_GRAY2RGB)
    return display[..., :3].copy()


def comparison_figure(fixed: np.ndarray, moving: np.ndarray, registered: np.ndarray) -> np.ndarray:
    """Create a compact fixed/moving/registered comparison image for export."""
    images = [_as_rgb(fixed), _as_rgb(moving), _as_rgb(registered)]
    target_h = min(image.shape[0] for image in images)
    resized: list[np.ndarray] = []
    for image in images:
        if image.shape[0] != target_h:
            scale = target_h / float(image.shape[0])
            width = max(1, int(round(image.shape[1] * scale)))
            image = cv2.resize(image, (width, target_h), interpolation=cv2.INTER_AREA)
        resized.append(image)

    label_height = 42
    gap = 12
    widths = [image.shape[1] for image in resized]
    canvas_w = sum(widths) + gap * (len(resized) - 1)
    canvas = np.full((target_h + label_height, canvas_w, 3), 255, dtype=np.uint8)
    labels = ("Fixed", "Moving", "Registered")
    x = 0
    for label, image in zip(labels, resized, strict=True):
        width = image.shape[1]
        canvas[label_height:, x : x + width] = image
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.58, 1)[0]
        text_x = x + max(6, (width - text_size[0]) // 2)
        cv2.putText(
            canvas,
            label,
            (text_x, 27),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (31, 41, 51),
            1,
            cv2.LINE_AA,
        )
        x += width + gap
    return canvas


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    np.save(buffer, np.asarray(array), allow_pickle=False)
    return buffer.getvalue()


def build_run_exports(
    *,
    run: RegistrationRun,
    fixed: np.ndarray,
    moving: np.ndarray,
) -> dict[str, ExportPayload]:
    """Build all session-local export payloads for a completed registration run."""
    if run.registered_array is None:
        raise ValueError("Registered output is unavailable; run exports cannot be built.")

    prefix = run.request_id or "registration_run"
    registered_png = _png_bytes(run.registered_array)
    transform_json = _json_bytes(transform_payload(run))
    summary_json = _json_bytes(registration_run_summary(run))
    comparison_png = _png_bytes(comparison_figure(fixed, moving, run.registered_array))
    registered_npy = _npy_bytes(run.registered_array)

    standalone = {
        "registered_png": ExportPayload(
            filename=f"{prefix}_registered.png",
            media_type="image/png",
            data=registered_png,
        ),
        "transform_json": ExportPayload(
            filename=f"{prefix}_transform.json",
            media_type="application/json",
            data=transform_json,
        ),
        "summary_json": ExportPayload(
            filename=f"{prefix}_summary.json",
            media_type="application/json",
            data=summary_json,
        ),
        "comparison_png": ExportPayload(
            filename=f"{prefix}_comparison.png",
            media_type="image/png",
            data=comparison_png,
        ),
    }

    bundle_buffer = BytesIO()
    with ZipFile(bundle_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("registered.png", registered_png)
        archive.writestr("registered_array.npy", registered_npy)
        archive.writestr("transform.json", transform_json)
        archive.writestr("summary.json", summary_json)
        archive.writestr("comparison.png", comparison_png)
        archive.writestr(
            "README.txt",
            (
                "Image Registration Pipeline UI run bundle\n\n"
                "registered.png: display-ready registered result\n"
                "registered_array.npy: full-precision registered array\n"
                "transform.json: Moving -> Fixed transform and plausibility metadata\n"
                "summary.json: normalized run summary, diagnostics, warnings, and provenance\n"
                "comparison.png: fixed/moving/registered comparison figure\n\n"
                "Exports are session-local convenience artifacts and are not written to tracked research reports.\n"
            ).encode("utf-8"),
        )

    standalone["bundle_zip"] = ExportPayload(
        filename=f"{prefix}_bundle.zip",
        media_type="application/zip",
        data=bundle_buffer.getvalue(),
    )
    return standalone
