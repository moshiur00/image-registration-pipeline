"""Automatic comparison research page, including Stage 6.5 export and QA.

The frozen Stage 6.1 service supplies the candidate and transform-agreement
contracts. Stage 6.4 renders that evidence and allows inspection of individual
candidates without ranking them or recalibrating scientific thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from ui.automatic import (
    AutomaticComparisonRequest,
    AutomaticComparisonService,
    AutomaticComparisonView,
    CompatibilityPreviewView,
)
from ui.automatic.automatic_presenter import (
    COMMON_EVIDENCE_EXPLANATION,
    candidate_evidence_rows,
    comparison_signature,
    execution_summary,
    recommendation_state_label,
)
from ui.automatic.agreement_presenter import (
    AGREEMENT_EXPLANATION,
    ANCHOR_EXPLANATION,
    agreement_exclusion_rows,
    agreement_overview,
    candidate_agreement_rows,
    disagreement_matrix_rows,
    pairwise_disagreement_rows,
)
from ui.automatic.automatic_export import build_automatic_analysis_export
from ui.automatic.candidate_summary import execution_issues, reference_limitations, diagnostic_highlights
from ui.automatic.candidate_inspection import (
    VISUAL_EXPLANATION,
    can_inspect_image,
    candidate_detail,
    reconstruct_visual_inspection,
)
from ui.streamlit.components.image_comparison import (
    render_input_triplet,
    render_visual_diagnostics,
)
from ui.core.contracts import ImageSource, PreprocessingSpec
from ui.core.enums import SourceType, TransformModel
from ui.core.image_inputs import decode_image_source
from ui.core.result_presenter import to_json_safe
from ui.streamlit.components.visuals import to_display_uint8
from ui.streamlit.view_model import build_upload_source


TRANSFORM_OPTIONS: Final[tuple[tuple[str, TransformModel], ...]] = (
    ("Translation", TransformModel.TRANSLATION),
    ("Rigid", TransformModel.RIGID),
    ("Similarity", TransformModel.SIMILARITY),
    ("Affine", TransformModel.AFFINE),
)

MODALITY_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Unknown", "unknown"),
    ("Monomodal", "monomodal"),
    ("Multimodal", "multimodal"),
)

_REASON_LABELS: Final[dict[str, str]] = {
    "dimension_mismatch": "Method does not support the pair dimensionality.",
    "transform_model_not_requested": "Method does not support the requested transform model.",
    "modality_class_not_supported": "Method is not compatible with the selected modality class.",
    "shape_mismatch": "Method requires fixed and moving images with matching raster shape.",
    "optional_method_disabled": "Optional methods are disabled for this comparison.",
}


@dataclass(frozen=True, slots=True)
class UploadedPair:
    """Decoded upload pair used by the Streamlit presentation shell."""

    fixed_source: ImageSource
    moving_source: ImageSource
    fixed_preview: np.ndarray
    moving_preview: np.ndarray


def format_compatibility_reason(reason: str) -> str:
    """Convert a backend compatibility code into research-facing text."""
    normalized = str(reason).strip()
    return _REASON_LABELS.get(normalized, normalized.replace("_", " ").capitalize() + ".")


def _decode_upload(*, display_name: str, content_bytes: bytes) -> tuple[ImageSource, np.ndarray]:
    temporary = ImageSource(
        source_type=SourceType.UPLOADED_BYTES,
        display_name=display_name,
        content_bytes=content_bytes,
    )
    preview, _metadata = decode_image_source(temporary, name=display_name)
    source = build_upload_source(
        display_name=display_name,
        content_bytes=content_bytes,
        decoded_array=np.asarray(preview),
    )
    return source, np.asarray(preview)


def build_uploaded_pair(
    *,
    fixed_name: str,
    fixed_bytes: bytes,
    moving_name: str,
    moving_bytes: bytes,
) -> UploadedPair:
    """Decode uploaded images without writing them into the research repository."""
    fixed_source, fixed_preview = _decode_upload(
        display_name=fixed_name,
        content_bytes=fixed_bytes,
    )
    moving_source, moving_preview = _decode_upload(
        display_name=moving_name,
        content_bytes=moving_bytes,
    )
    return UploadedPair(
        fixed_source=fixed_source,
        moving_source=moving_source,
        fixed_preview=fixed_preview,
        moving_preview=moving_preview,
    )


def _render_preprocessing_controls() -> PreprocessingSpec:
    import streamlit as st

    st.caption(
        "Preprocessing is applied equally to all candidate methods and is included in the pair specification."
    )
    normalization = st.selectbox(
        "Normalization",
        options=["None", "Robust 0-1"],
        key="ui_auto_normalization",
        help="Robust normalization uses percentile scaling. No histogram matching is applied.",
    )
    use_clipping = st.checkbox(
        "Percentile clipping",
        value=False,
        key="ui_auto_use_clipping",
    )
    clipping = None
    if use_clipping:
        clip_columns = st.columns(2)
        lower = clip_columns[0].number_input(
            "Lower percentile",
            min_value=0.0,
            max_value=49.0,
            value=1.0,
            step=0.5,
            key="ui_auto_clip_low",
        )
        upper = clip_columns[1].number_input(
            "Upper percentile",
            min_value=51.0,
            max_value=100.0,
            value=99.0,
            step=0.5,
            key="ui_auto_clip_high",
        )
        clipping = (float(lower), float(upper))

    sigma = st.number_input(
        "Gaussian smoothing sigma",
        min_value=0.0,
        max_value=8.0,
        value=0.0,
        step=0.25,
        key="ui_auto_gaussian_sigma",
        help="0 disables smoothing.",
    )
    return PreprocessingSpec(
        grayscale=True,
        clipping_percentiles=clipping,
        normalization="robust" if normalization == "Robust 0-1" else None,
        gaussian_sigma=float(sigma),
        resize_policy="none",
    )


def _compatibility_rows(preview: CompatibilityPreviewView) -> list[dict[str, str]]:
    return [
        {
            "Method": item.display_name,
            "Family": item.method_family.replace("_", " ").title(),
            "Transform": item.transform_model.title(),
            "Optional": "Yes" if item.optional else "No",
        }
        for item in preview.compatible
    ]


def _excluded_rows(preview: CompatibilityPreviewView) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in preview.excluded:
        rows.append(
            {
                "Method": item.display_name,
                "Reason": " ".join(format_compatibility_reason(reason) for reason in item.reasons),
            }
        )
    return rows


def _render_compatibility(preview: CompatibilityPreviewView, *, executed: bool = False) -> None:
    import streamlit as st

    st.markdown("### Method compatibility")
    st.caption(
        "Compatibility is derived from the frozen backend capability rules. "
        + ("Candidate execution results are shown below." if executed else "No registration method has been executed.")
    )

    summary_columns = st.columns(3)
    summary_columns[0].metric("Compatible", preview.compatible_count)
    summary_columns[1].metric("Excluded", preview.excluded_count)
    summary_columns[2].metric(
        "Ground truth",
        preview.ground_truth_status.replace("_", " ").title(),
    )

    if preview.compatible:
        st.markdown("#### Compatible methods")
        st.dataframe(
            _compatibility_rows(preview),
            hide_index=True,
            width="stretch",
        )
    else:
        st.warning("No methods are compatible with the current pair specification.")

    with st.expander(
        f"Excluded methods ({preview.excluded_count})",
        expanded=False,
    ):
        if preview.excluded:
            st.dataframe(
                _excluded_rows(preview),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("No methods were excluded by the current compatibility policy.")

    shape_text = f"{preview.image_shape[1]} x {preview.image_shape[0]} px"
    shape_state = "matching shapes" if preview.same_shape else "different shapes"
    st.caption(
        f"Pair profile: {shape_text} fixed raster | {shape_state} | "
        f"{preview.transform_model} | {preview.modality_class}"
    )



def _render_transform_agreement(result: AutomaticComparisonView) -> None:
    """Present the existing service agreement, with no invented thresholds."""
    import streamlit as st

    overview = agreement_overview(result)
    st.markdown("### Transform agreement")
    st.caption(AGREEMENT_EXPLANATION)

    columns = st.columns(3)
    columns[0].metric("Eligible transforms", overview["eligible"])
    columns[1].metric("Agreement exclusions", overview["excluded"])
    columns[2].metric("Pairwise comparisons", overview["pairwise_comparisons"])

    exclusions = agreement_exclusion_rows(result)
    if exclusions:
        with st.expander(f"Candidates excluded from agreement ({len(exclusions)})"):
            st.dataframe(exclusions, hide_index=True, width="stretch")

    if overview["status"] != "available" or overview["eligible"] < 2:
        st.info(
            "Insufficient eligible transforms for pairwise agreement. "
            "No consensus anchor is assigned. This does not mean registration failed."
        )
        return

    st.markdown("#### Pairwise RMS disagreement (pixels)")
    matrix_rows = disagreement_matrix_rows(result)
    if matrix_rows:
        st.dataframe(matrix_rows, hide_index=True, width="stretch")
        st.caption(
            "Rows and columns are eligible candidates. Diagonal values are zero; "
            "blank cells indicate missing pairwise evidence, not zero disagreement."
        )
    else:
        st.warning("Agreement was reported as available but no matrix could be constructed.")

    with st.expander("Pairwise disagreement statistics and candidate centrality"):
        pairwise_rows = pairwise_disagreement_rows(result)
        if pairwise_rows:
            st.dataframe(pairwise_rows, hide_index=True, width="stretch")
        centrality = candidate_agreement_rows(result)
        if centrality:
            st.markdown("##### Candidate centrality (descriptive)")
            st.dataframe(centrality, hide_index=True, width="stretch")
        st.caption("Normalized RMS values are relative to the fixed-image diagonal.")

    st.markdown("#### Descriptive consensus anchor")
    if overview["anchor"]:
        st.write(overview["anchor"])
        st.caption(ANCHOR_EXPLANATION)
    else:
        st.info(overview["anchor_explanation"])
    if overview["median_rms_px"] is not None:
        st.caption(
            f"Median pairwise RMS: {overview['median_rms_px']:.3f} px. "
            "No universal agreement threshold is applied."
        )


def _render_candidate_inspection(
    result: AutomaticComparisonView,
    request: AutomaticComparisonRequest,
) -> None:
    """Inspect every candidate status and view one reconstructed registration."""
    import streamlit as st

    st.markdown("### Candidate inspection")
    st.caption(
        "Execution state, estimated Moving -> Fixed transform, raw method-specific "
        "diagnostics, and failure reasons are shown separately from common evidence."
    )
    for candidate in result.candidates:
        detail = candidate_detail(candidate)
        with st.expander(f"{detail['method']} | {detail['execution']}", expanded=False):
            info_columns = st.columns(3)
            info_columns[0].metric("Execution", detail["execution"])
            info_columns[1].metric("Plausibility", detail["plausibility"])
            info_columns[2].metric("Transform model", detail["transform_model"])
            st.caption(f"Family: {detail['family']} | Direction: {detail['transform_direction']}")
            if detail["failure_reason"]:
                st.error(f"Failure reason: {detail['failure_reason']}")
            actionable = [warning for warning in detail["warnings"] if not
                ("ground truth" in str(warning).lower() and "unavailable" in str(warning).lower())]
            for warning in actionable:
                st.warning(str(warning))
            if detail["estimated_transform"] is not None:
                st.markdown("##### Estimated transform")
                st.code(
                    "\n".join(
                        "  ".join(f"{value: .6f}" for value in row)
                        for row in detail["estimated_transform"]
                    ),
                    language="text",
                )
            else:
                st.caption("No estimated transform is available for this candidate.")
            st.markdown("##### Method-specific diagnostics")
            highlights = diagnostic_highlights(candidate)
            if highlights:
                st.dataframe(highlights, hide_index=True, width="stretch")
            if detail["diagnostics"]:
                st.caption("Raw method diagnostics (expand individual JSON fields)")
                st.json(to_json_safe(detail["diagnostics"]), expanded=False)
            else:
                st.caption("No method-specific diagnostics were returned.")
            if detail["timings_ms"]:
                st.caption(f"Recorded timings (ms): {detail['timings_ms']}")

    available = [candidate for candidate in result.candidates if can_inspect_image(candidate)]
    st.markdown("#### Visual inspection")
    if not available:
        st.info("No candidate with an estimated transform and registered output is available.")
        return

    by_id = {candidate.candidate_id: candidate for candidate in available}
    selected = st.selectbox(
        "Candidate to inspect",
        options=list(by_id),
        format_func=lambda cid: f"{by_id[cid].display_name} | {by_id[cid].execution_status.upper()}",
        key="ui_auto_visual_candidate",
        help="Selecting a candidate is for inspection only, not a method recommendation.",
    )
    try:
        fixed, moving, reconstructed, valid_mask = reconstruct_visual_inspection(request, by_id[selected])
    except ValueError as exc:
        st.warning(f"Inspection preview unavailable: {exc}")
        return
    st.caption(VISUAL_EXPLANATION)
    render_input_triplet(fixed=fixed, moving=moving, registered=reconstructed)
    render_visual_diagnostics(fixed=fixed, registered=reconstructed, valid_mask=valid_mask)


def _render_execution_result(
    result: AutomaticComparisonView,
    request: AutomaticComparisonRequest,
) -> None:
    """Render Stage 6.3 evidence plus Stage 6.4 agreement and inspection."""
    import streamlit as st

    st.markdown("### Candidate results")
    summary = execution_summary(result)
    summary_columns = st.columns(4)
    summary_columns[0].metric("Compatible", summary["compatible"])
    summary_columns[1].metric("Completed", summary["completed"])
    summary_columns[2].metric("CHECK", summary["check"])
    summary_columns[3].metric("Failed", summary["failed"])

    if summary["validation_error"]:
        st.error(
            f"{summary['validation_error']} candidate result(s) failed identity or contract validation."
        )

    st.caption(
        "Ground truth is unavailable. TRE, parameter error, and geometric correctness are not reported."
    )
    st.caption(
        "Recommendation state: "
        + recommendation_state_label(result.recommendation_status)
        + "."
    )

    st.markdown("#### Common comparison evidence")
    rows = candidate_evidence_rows(result)
    if rows:
        st.dataframe(
            rows, hide_index=True, width="stretch",
            column_config={
                "Method": st.column_config.TextColumn("Method", help="Registration candidate; no ranking implied.", width="medium"),
                "Execution": st.column_config.TextColumn("Execution", help="Completion and review status, not geometric accuracy."),
                "Transform": st.column_config.TextColumn("Plausibility", help="Transform plausibility is not correctness."),
                "MAE": st.column_config.NumberColumn("MAE", format="%.4f", help="Mean absolute intensity error; lower is not universally more accurate."),
                "MSE": st.column_config.NumberColumn("MSE", format="%.4f", help="Mean squared intensity error."),
                "NCC": st.column_config.NumberColumn("NCC", format="%.4f", help="Normalized cross-correlation, descriptive only."),
                "SSIM": st.column_config.NumberColumn("SSIM", format="%.4f", help="Structural similarity, not geometric ground truth."),
                "Evaluation MI": st.column_config.NumberColumn("MI (nats)", format="%.4f", help="Evaluation mutual information; not optimizer objective values."),
                "Valid overlap": st.column_config.NumberColumn("Overlap (0-1)", format="%.4f", help="Fraction of valid overlap; values from 0 to 1."),
                "Runtime (ms)": st.column_config.NumberColumn("Time (ms)", format="%.2f"),
            },
        )
    else:
        st.info("No candidate records were returned.")

    st.caption(COMMON_EVIDENCE_EXPLANATION)

    issues = execution_issues(result)
    st.caption(f"Execution issues requiring review: {len(issues)}.")
    if issues:
        with st.expander(f"Execution issues ({len(issues)})", expanded=False):
            st.dataframe(issues, hide_index=True, width="stretch")
    limitations = reference_limitations(result)
    if limitations:
        with st.expander("Evaluation limitations", expanded=False):
            for limitation in limitations:
                st.caption(limitation)

    st.divider()
    _render_transform_agreement(result)
    st.divider()
    _render_candidate_inspection(result, request)
    st.divider()
    st.markdown("### Export automatic analysis")
    st.caption(
        "Exports include every candidate, excluded methods, descriptive agreement, "
        "input hashes, raw method diagnostics, and clearly labeled inspection-only images. "
        "Uploaded original image bytes are not included."
    )
    if st.button("Prepare automatic analysis ZIP", key="ui_auto_prepare_bundle"):
        with st.spinner("Preparing analysis evidence and inspection artifacts..."):
            try:
                payload = build_automatic_analysis_export(request=request, view=result)
            except (ValueError, RuntimeError) as exc:
                st.error(f"Automatic analysis export unavailable: {exc}")
                st.session_state.pop("ui_auto_export_payload", None)
            else:
                st.session_state["ui_auto_export_payload"] = payload
    payload = st.session_state.get("ui_auto_export_payload")
    if payload is not None:
        st.download_button(
            "Download automatic analysis ZIP", data=payload.data,
            file_name=payload.filename, mime=payload.media_type,
            key="ui_auto_download_bundle", width="stretch",
        )


def clear_automatic_run_state(state: dict | object) -> None:
    """Clear previous result, identity, export and selection on invalid input.

    Works with Streamlit session state or an ordinary mutable mapping in tests.
    No widget values or current uploads are modified.
    """
    for key in (
        "ui_auto_result", "ui_auto_result_signature", "ui_auto_export_payload",
        "ui_auto_visual_candidate",
    ):
        state.pop(key, None)


def ensure_current_comparison_state(state: dict | object, signature: str) -> bool:
    """Invalidate stale run/export if the requested pair or method policy changed."""
    if state.get("ui_auto_result_signature") != signature:
        clear_automatic_run_state(state)
        return False
    return state.get("ui_auto_result") is not None


def render_automatic_comparison(service: AutomaticComparisonService) -> None:
    """Render compatibility, execution, agreement, and inspection without ranking."""
    import streamlit as st

    st.markdown("# Automatic Registration Comparison")
    st.caption(
        "Inspect compatible registration methods for one image pair without requiring ground truth."
    )
    st.info(
        "Experimental decision-support workflow. Final method recommendation and confidence calibration are not enabled."
    )

    left, right = st.columns([0.36, 0.64], gap="large")
    with left:
        st.markdown("### Input pair")
        fixed_upload = st.file_uploader(
            "Fixed image",
            type=["png", "jpg", "jpeg", "bmp", "tif", "tiff"],
            key="ui_auto_fixed_upload",
        )
        moving_upload = st.file_uploader(
            "Moving image",
            type=["png", "jpg", "jpeg", "bmp", "tif", "tiff"],
            key="ui_auto_moving_upload",
        )

        st.markdown("#### Pair specification")
        transform_by_label = dict(TRANSFORM_OPTIONS)
        transform_label = st.selectbox(
            "Requested transform model",
            options=[label for label, _value in TRANSFORM_OPTIONS],
            index=3,
            key="ui_auto_transform_model",
        )

        modality_by_label = dict(MODALITY_OPTIONS)
        modality_label = st.selectbox(
            "Image class",
            options=[label for label, _value in MODALITY_OPTIONS],
            index=0,
            key="ui_auto_modality_class",
            help=(
                "Unknown keeps discovery permissive. Monomodal and multimodal selections allow the compatibility layer "
                "to exclude methods whose modality assumptions are not satisfied."
            ),
        )
        include_optional = st.checkbox(
            "Include optional methods",
            value=True,
            key="ui_auto_include_optional",
            help="Optional complementary methods can have higher runtime than core baselines.",
        )

        with st.expander("Preprocessing", expanded=False):
            preprocessing = _render_preprocessing_controls()

    with right:
        st.markdown("### Input preview")
        if fixed_upload is None or moving_upload is None:
            clear_automatic_run_state(st.session_state)
            st.info("Upload both fixed and moving images to inspect method compatibility.")
            return

        try:
            pair = build_uploaded_pair(
                fixed_name=fixed_upload.name,
                fixed_bytes=fixed_upload.getvalue(),
                moving_name=moving_upload.name,
                moving_bytes=moving_upload.getvalue(),
            )
        except ValueError as exc:
            clear_automatic_run_state(st.session_state)
            st.error(str(exc))
            return

        image_columns = st.columns(2)
        image_columns[0].image(
            to_display_uint8(pair.fixed_preview),
            caption="Fixed",
            width="stretch",
        )
        image_columns[1].image(
            to_display_uint8(pair.moving_preview),
            caption="Moving",
            width="stretch",
        )

        request = AutomaticComparisonRequest(
            fixed=pair.fixed_source,
            moving=pair.moving_source,
            transform_model=transform_by_label[transform_label],
            modality_class=modality_by_label[modality_label],
            preprocessing=preprocessing,
            include_optional_methods=bool(include_optional),
        )

        try:
            preview = service.preview(request)
        except ValueError as exc:
            clear_automatic_run_state(st.session_state)
            st.error(str(exc))
            return

        st.divider()
        signature = comparison_signature(
            preview, include_optional_methods=request.include_optional_methods
        )
        ensure_current_comparison_state(st.session_state, signature)
        compatibility_placeholder = st.empty()

        run_disabled = preview.compatible_count == 0
        run_clicked = st.button(
            "Run automatic comparison",
            type="primary",
            width="stretch",
            disabled=run_disabled,
            key="ui_auto_run_comparison",
        )

        if run_clicked:
            clear_automatic_run_state(st.session_state)
            with st.spinner(
                f"Running {preview.compatible_count} compatible registration candidate(s)..."
            ):
                try:
                    result = service.run(request)
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
                    return
            st.session_state["ui_auto_result"] = result
            st.session_state["ui_auto_result_signature"] = signature
            st.session_state.pop("ui_auto_export_payload", None)

        with compatibility_placeholder.container():
            _render_compatibility(preview, executed=(
                st.session_state.get("ui_auto_result") is not None
                and st.session_state.get("ui_auto_result_signature") == signature
            ))

        result = st.session_state.get("ui_auto_result")
        result_signature = st.session_state.get("ui_auto_result_signature")
        if result is None or result_signature != signature:
            if preview.compatible_count:
                st.caption(
                    "Run the compatible candidates to compare normalized execution evidence."
                )
            return

        st.divider()
        _render_execution_result(result, request)
