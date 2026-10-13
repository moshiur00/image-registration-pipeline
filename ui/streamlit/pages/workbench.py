"""Primary Stage 4 Streamlit research workbench."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ui.core.dataset_catalog import DatasetCatalog
from ui.core.image_inputs import prepare_image_source
from ui.core.method_registry import MethodDescriptor
from ui.core.registration_service import RegistrationService
from ui.streamlit.components.diagnostics_panel import render_diagnostics
from ui.streamlit.components.export_panel import render_exports
from ui.streamlit.components.image_comparison import render_input_triplet, render_visual_diagnostics
from ui.streamlit.components.method_controls import render_method_controls, render_preprocessing_controls
from ui.streamlit.components.metrics_panel import render_metrics, render_run_header, render_transform
from ui.streamlit.components.provenance_panel import render_provenance
from ui.streamlit.components.source_selector import SourceSelection, render_source_selector
from ui.streamlit.components.visuals import to_display_uint8
from ui.streamlit.view_model import (
    build_example_request,
    build_upload_request,
    method_descriptors_for_example,
    method_descriptors_for_upload,
)


def _method_select(
    *,
    service: RegistrationService,
    selection: SourceSelection,
) -> MethodDescriptor | None:
    import streamlit as st

    methods = service.list_methods()
    if selection.mode == "example" and selection.example_bundle is not None:
        available = method_descriptors_for_example(methods, selection.example_bundle)
        preferred = selection.example_bundle.descriptor.recommended_method_ids
        preferred_rank = {method_id: index for index, method_id in enumerate(preferred)}
        available.sort(key=lambda item: (item.id not in preferred_rank, preferred_rank.get(item.id, 999), item.display_name))
        if preferred:
            st.caption("Curated method guidance is based on the example's motion model and prior project evidence.")
    elif selection.mode == "upload":
        available = method_descriptors_for_upload(methods)
        available.sort(key=lambda item: item.display_name)
        st.caption("Choose the method manually. The workbench does not infer a globally best method.")
    else:
        return None

    if not available:
        st.warning("No compatible 2D methods are available for this source.")
        return None

    by_id = {item.id: item for item in available}
    selected_id = st.selectbox(
        "Registration method",
        options=[item.id for item in available],
        format_func=lambda value: by_id[value].display_name,
    )
    descriptor = by_id[selected_id]
    if descriptor.optional:
        st.caption("Optional complement method. Runtime can be higher than the core baseline.")
    return descriptor


def _render_request_summary(request) -> None:
    import streamlit as st

    with st.expander("Resolved run specification", expanded=False):
        st.json(
            {
                "request_id": request.request_id,
                "fixed": request.fixed.display_name,
                "moving": request.moving.display_name,
                "preprocessing": asdict(request.preprocessing),
                "registration": {
                    "method_id": request.registration.method_id,
                    "transform_model": request.registration.transform_model.value,
                    "initialization": request.registration.initialization,
                    "parameters": request.registration.parameters,
                    "interpolation": request.registration.interpolation,
                },
                "ground_truth_status": request.evaluation.ground_truth_status.value,
                "thresholds": request.evaluation.thresholds,
            },
            expanded=False,
        )


def _build_request(
    *,
    selection: SourceSelection,
    method: MethodDescriptor,
    preprocessing,
    initialization,
    parameters,
):
    if selection.mode == "example" and selection.example_bundle is not None:
        return build_example_request(
            bundle=selection.example_bundle,
            method=method,
            preprocessing=preprocessing,
            initialization=initialization,
            parameters=parameters,
        )
    if selection.mode == "upload" and selection.fixed_source is not None and selection.moving_source is not None:
        return build_upload_request(
            fixed=selection.fixed_source,
            moving=selection.moving_source,
            method=method,
            preprocessing=preprocessing,
            initialization=initialization,
            parameters=parameters,
        )
    return None


def render_workbench(service: RegistrationService, catalog: DatasetCatalog) -> None:
    import streamlit as st

    st.markdown("# Registration Workbench")
    st.caption("Configure, run, and inspect monomodal and multimodal image registration.")

    left, right = st.columns([0.34, 0.66], gap="large")
    with left:
        selection = render_source_selector(catalog)
        if not selection.ready:
            if selection.mode != "rire":
                st.info("Select a complete input pair to continue.")
            return

        st.divider()
        method = _method_select(service=service, selection=selection)
        if method is None:
            return
        initialization, parameters = render_method_controls(method)
        st.divider()
        preprocessing = render_preprocessing_controls(method.id)

        request = _build_request(
            selection=selection,
            method=method,
            preprocessing=preprocessing,
            initialization=initialization,
            parameters=parameters,
        )
        if request is None:
            return

        report = service.validate(request)
        for warning in report.warnings:
            st.warning(warning.message)
        for error in report.errors:
            st.error(error.message)

        run_disabled = not report.valid
        run_clicked = st.button(
            "Run registration",
            type="primary",
            width="stretch",
            disabled=run_disabled,
        )
        _render_request_summary(request)

    with right:
        st.markdown("### Input images")
        input_cols = st.columns(2)
        input_cols[0].image(to_display_uint8(selection.fixed_preview), caption="Fixed", width="stretch")
        input_cols[1].image(to_display_uint8(selection.moving_preview), caption="Moving", width="stretch")

        if run_clicked:
            with st.spinner("Running registration..."):
                run = service.run(request)
            st.session_state["ui_stage4_run"] = run
            st.session_state["ui_stage4_request_id"] = request.request_id

        run = st.session_state.get("ui_stage4_run")
        run_request_id = st.session_state.get("ui_stage4_request_id")
        if run is None or run_request_id != request.request_id:
            st.caption("Run the selected configuration to display registered output and diagnostics.")
            return

        st.divider()
        st.markdown("### Result")
        render_run_header(run)

        try:
            fixed_prepared = prepare_image_source(request.fixed, request.preprocessing, name="fixed").array
            moving_prepared = prepare_image_source(request.moving, request.preprocessing, name="moving").array
        except ValueError:
            fixed_prepared = np.asarray(selection.fixed_preview)
            moving_prepared = np.asarray(selection.moving_preview)

        render_input_triplet(
            fixed=fixed_prepared,
            moving=moving_prepared,
            registered=run.registered_array,
        )

        if run.failure_reason:
            st.error(run.failure_reason)
        for warning in run.warnings:
            normalized_warning = warning.lower()
            if "ground truth" in normalized_warning and ("tre" in normalized_warning or "geometric pass" in normalized_warning):
                continue
            st.warning(warning)

        details_left, details_right = st.columns(2, gap="large")
        with details_left:
            render_transform(run)
        with details_right:
            render_metrics(run)

        if run.registered_array is not None:
            st.markdown("#### Visual diagnostics")
            render_visual_diagnostics(fixed=fixed_prepared, registered=run.registered_array)

        render_diagnostics(run)
        render_provenance(run, method_name=method.display_name)
        render_exports(run=run, fixed=fixed_prepared, moving=moving_prepared)

