from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np

from ui.automatic.models import CompatibilityPreviewView, MethodCompatibilityView
from ui.core.enums import SourceType, TransformModel
from ui.streamlit.pages.automatic_comparison import (
    MODALITY_OPTIONS,
    TRANSFORM_OPTIONS,
    _compatibility_rows,
    _excluded_rows,
    build_uploaded_pair,
    format_compatibility_reason,
)


UI_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = UI_ROOT / "streamlit" / "pages" / "automatic_comparison.py"
APP_PATH = UI_ROOT / "streamlit_app.py"


def _encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def _preview() -> CompatibilityPreviewView:
    return CompatibilityPreviewView(
        pair_id="ui-auto-test",
        image_shape=(64, 96),
        same_shape=True,
        modality_class="monomodal",
        transform_model="affine",
        ground_truth_status="unavailable",
        compatible=(
            MethodCompatibilityView(
                method_id="ecc_affine",
                display_name="ECC Affine",
                method_family="intensity_based",
                transform_model="affine",
                optional=False,
                compatible=True,
            ),
        ),
        excluded=(
            MethodCompatibilityView(
                method_id="phase_translation",
                display_name="Phase Correlation",
                method_family="frequency_domain",
                transform_model="translation",
                optional=False,
                compatible=False,
                reasons=("transform_model_not_requested",),
            ),
        ),
    )


def test_stage62_transform_options_cover_supported_2d_models() -> None:
    assert TRANSFORM_OPTIONS == (
        ("Translation", TransformModel.TRANSLATION),
        ("Rigid", TransformModel.RIGID),
        ("Similarity", TransformModel.SIMILARITY),
        ("Affine", TransformModel.AFFINE),
    )


def test_stage62_modality_options_are_user_facing() -> None:
    assert MODALITY_OPTIONS == (
        ("Unknown", "unknown"),
        ("Monomodal", "monomodal"),
        ("Multimodal", "multimodal"),
    )


def test_stage62_compatibility_reason_is_human_readable() -> None:
    assert format_compatibility_reason("transform_model_not_requested") == (
        "Method does not support the requested transform model."
    )
    assert format_compatibility_reason("optional_method_disabled") == (
        "Optional methods are disabled for this comparison."
    )
    assert "_" not in format_compatibility_reason("future_reason_code")


def test_stage62_upload_pair_stays_in_memory() -> None:
    fixed = np.arange(64, dtype=np.uint8).reshape(8, 8)
    moving = np.flipud(fixed)
    pair = build_uploaded_pair(
        fixed_name="fixed.png",
        fixed_bytes=_encode_png(fixed),
        moving_name="moving.png",
        moving_bytes=_encode_png(moving),
    )
    assert pair.fixed_source.source_type == SourceType.UPLOADED_BYTES
    assert pair.moving_source.source_type == SourceType.UPLOADED_BYTES
    assert pair.fixed_source.path is None
    assert pair.moving_source.path is None
    assert pair.fixed_preview.shape == (8, 8)
    assert pair.moving_preview.shape == (8, 8)


def test_stage62_compatibility_rows_do_not_require_hardcoded_method_ids() -> None:
    rows = _compatibility_rows(_preview())
    assert rows == [
        {
            "Method": "ECC Affine",
            "Family": "Intensity Based",
            "Transform": "Affine",
            "Optional": "No",
        }
    ]


def test_stage62_excluded_rows_preserve_backend_reason() -> None:
    rows = _excluded_rows(_preview())
    assert rows == [
        {
            "Method": "Phase Correlation",
            "Reason": "Method does not support the requested transform model.",
        }
    ]


def test_stage62_preview_contract_remains_part_of_the_page() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert "service.preview(request)" in source
    assert "_render_compatibility(preview, executed=" in source
    assert "Find best method" not in source


def test_stage62_page_does_not_hardcode_registration_method_ids() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    forbidden = {
        "phase_translation",
        "ecc_affine",
        "orb_affine",
        "sift_affine",
        "mi_affine_2d",
    }
    assert not {method_id for method_id in forbidden if method_id in source}


def test_stage62_navigation_and_page_header_are_wired() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    page_source = PAGE_PATH.read_text(encoding="utf-8")
    assert '"Automatic comparison"' in app_source
    assert 'st.markdown("# Automatic Registration Comparison")' in page_source
    assert "render_automatic_comparison" in app_source


def test_stage62_page_module_imports_without_streamlit_installed() -> None:
    # Streamlit remains a runtime presentation dependency, not a module-import dependency.
    assert importlib.util.find_spec("ui.streamlit.pages.automatic_comparison") is not None
    module = __import__("ui.streamlit.pages.automatic_comparison", fromlist=["*"])
    assert callable(module.render_automatic_comparison)
