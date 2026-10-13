"""Source-selection helpers for the workbench sidebar."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ui.core.contracts import ImageSource
from ui.core.dataset_catalog import DatasetCatalog, ExampleBundle
from ui.core.image_inputs import decode_image_source
from ui.core.enums import SourceType
from ui.streamlit.view_model import build_upload_source


@dataclass(slots=True)
class SourceSelection:
    mode: str
    example_bundle: ExampleBundle | None = None
    fixed_source: ImageSource | None = None
    moving_source: ImageSource | None = None
    fixed_preview: np.ndarray | None = None
    moving_preview: np.ndarray | None = None
    ready: bool = False


def render_source_selector(catalog: DatasetCatalog) -> SourceSelection:
    import streamlit as st

    st.markdown("### Input")
    pending_example_id = st.session_state.pop("ui_pending_example_id", None)
    if pending_example_id is not None:
        st.session_state["ui_source_mode"] = "Research example"

    mode_options = ["Research example", "Upload images", "RIRE status"]
    current_mode = st.session_state.get("ui_source_mode")
    if current_mode not in mode_options:
        st.session_state["ui_source_mode"] = "Research example"
    mode = st.radio(
        "Source",
        mode_options,
        key="ui_source_mode",
        horizontal=False,
    )

    if mode == "Research example":
        descriptors = catalog.list_examples()
        labels = {descriptor.id: descriptor.title for descriptor in descriptors}
        example_ids = [descriptor.id for descriptor in descriptors]
        default_id = "synthetic_translation" if "synthetic_translation" in example_ids else example_ids[0]
        if pending_example_id in example_ids:
            st.session_state["ui_example_selector"] = pending_example_id
        if st.session_state.get("ui_example_selector") not in example_ids:
            st.session_state["ui_example_selector"] = default_id
        example_id = st.selectbox(
            "Example",
            options=example_ids,
            key="ui_example_selector",
            format_func=lambda value: labels[value],
        )
        bundle = catalog.build(example_id)
        descriptor = bundle.descriptor
        st.caption(descriptor.description)
        st.caption(
            f"Ground truth: {descriptor.ground_truth_status.value} | "
            f"Motion model: {descriptor.transform_model.value} | "
            f"Class: {descriptor.modality_class}"
        )
        fixed_preview, _ = decode_image_source(bundle.fixed, name="fixed")
        moving_preview, _ = decode_image_source(bundle.moving, name="moving")
        return SourceSelection(
            mode="example",
            example_bundle=bundle,
            fixed_source=bundle.fixed,
            moving_source=bundle.moving,
            fixed_preview=np.asarray(fixed_preview),
            moving_preview=np.asarray(moving_preview),
            ready=True,
        )

    if mode == "Upload images":
        fixed_upload = st.file_uploader(
            "Fixed image",
            type=["png", "jpg", "jpeg", "bmp", "tif", "tiff"],
            key="fixed_upload",
        )
        moving_upload = st.file_uploader(
            "Moving image",
            type=["png", "jpg", "jpeg", "bmp", "tif", "tiff"],
            key="moving_upload",
        )
        if fixed_upload is None or moving_upload is None:
            st.caption("Provide both images to enable registration controls.")
            return SourceSelection(mode="upload")
        try:
            fixed_bytes = fixed_upload.getvalue()
            moving_bytes = moving_upload.getvalue()
            temporary_fixed = ImageSource(
                source_type=SourceType.UPLOADED_BYTES,
                display_name=fixed_upload.name,
                content_bytes=fixed_bytes,
            )
            temporary_moving = ImageSource(
                source_type=SourceType.UPLOADED_BYTES,
                display_name=moving_upload.name,
                content_bytes=moving_bytes,
            )
            fixed_preview, _ = decode_image_source(temporary_fixed, name="fixed")
            moving_preview, _ = decode_image_source(temporary_moving, name="moving")
            fixed_source = build_upload_source(
                display_name=fixed_upload.name,
                content_bytes=fixed_bytes,
                decoded_array=np.asarray(fixed_preview),
            )
            moving_source = build_upload_source(
                display_name=moving_upload.name,
                content_bytes=moving_bytes,
                decoded_array=np.asarray(moving_preview),
            )
        except ValueError as exc:
            st.error(str(exc))
            return SourceSelection(mode="upload")
        return SourceSelection(
            mode="upload",
            fixed_source=fixed_source,
            moving_source=moving_source,
            fixed_preview=np.asarray(fixed_preview),
            moving_preview=np.asarray(moving_preview),
            ready=True,
        )

    status = catalog.rire_status()
    if status["available"]:
        st.success("Local RIRE CT/MR-T1 volumes detected.")
    else:
        st.info("Local RIRE volumes are not available in this checkout.")
    manifest_value = status.get("manifest")
    if manifest_value:
        from pathlib import Path
        manifest_path = Path(manifest_value)
        try:
            manifest_display = manifest_path.resolve().relative_to(catalog.project_root.resolve()).as_posix()
        except (ValueError, OSError):
            manifest_display = manifest_path.name
    else:
        manifest_display = "n/a"
    st.caption(f"Manifest: {manifest_display}")
    st.caption(
        "Stage 4 keeps the 3D RIRE path read-only. The current workbench release focuses on validated 2D interaction."
    )
    return SourceSelection(mode="rire")
