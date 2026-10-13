"""Curated benchmark-example browser for the research workbench."""

from __future__ import annotations

from html import escape
from pathlib import Path

from ui.core.dataset_catalog import DatasetCatalog, ExampleDescriptor
from ui.core.method_registry import MethodDescriptor
from ui.core.registration_service import RegistrationService


_CATEGORY_LABELS = {
    "synthetic": "Synthetic",
    "synthetic_multimodal": "Synthetic",
}

_MODALITY_LABELS = {
    "monomodal": "Monomodal",
    "simulated_multimodal": "Multimodal",
}

_METHOD_FAMILY_LABELS = {
    "phase_translation": "Phase Correlation",
    "ecc_translation": "ECC",
    "ecc_rigid": "ECC",
    "ecc_affine": "ECC",
    "orb_similarity": "ORB + RANSAC",
    "orb_affine": "ORB + RANSAC",
    "sift_similarity": "SIFT + RANSAC",
    "sift_affine": "SIFT + RANSAC",
    "mi_rigid_2d": "Mattes MI",
    "mi_affine_2d": "Mattes MI",
}


def _category_label(category: str) -> str:
    """Return a portfolio-facing category label without internal IDs."""
    return _CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def _modality_label(modality_class: str) -> str:
    """Return a human-readable modality-class label."""
    return _MODALITY_LABELS.get(modality_class, modality_class.replace("_", " ").title())


def _ground_truth_label(value: str) -> str:
    return "Known ground truth" if value == "known" else value.replace("_", " ").title()


def _motion_label(descriptor: ExampleDescriptor) -> str:
    return descriptor.transform_model.value.replace("_", " ").title()


def _method_family_label(descriptor: MethodDescriptor) -> str:
    return _METHOD_FAMILY_LABELS.get(descriptor.id, descriptor.display_name)


def _method_family_labels(
    service: RegistrationService,
    method_ids: tuple[str, ...],
) -> list[str]:
    """Return stable, de-duplicated method-family labels for one example."""
    descriptors = {item.id: item for item in service.list_methods()}
    labels: list[str] = []
    for method_id in method_ids:
        descriptor = descriptors.get(method_id)
        label = _method_family_label(descriptor) if descriptor is not None else method_id.replace("_", " ").title()
        if label not in labels:
            labels.append(label)
    return labels


def _project_relative_path(value: str | None, project_root: Path) -> str:
    """Return a public-safe project-relative path when possible."""
    if not value:
        return "n/a"
    path = Path(value)
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def _render_tags(*labels: str) -> None:
    import streamlit as st

    tags = "".join(f'<span class="research-tag">{escape(label)}</span>' for label in labels if label)
    st.markdown(f'<div class="research-tag-row">{tags}</div>', unsafe_allow_html=True)


def _open_in_workbench(example_id: str) -> None:
    """Prepare a curated example for the next Workbench render."""
    import streamlit as st

    st.session_state["ui_page"] = "Workbench"
    st.session_state["ui_pending_example_id"] = example_id
    st.session_state["ui_source_mode"] = "Research example"


def _render_example_card(
    descriptor: ExampleDescriptor,
    *,
    service: RegistrationService,
) -> None:
    import streamlit as st

    methods = _method_family_labels(service, descriptor.recommended_method_ids)
    with st.container(border=True):
        st.markdown(f"#### {descriptor.title}")
        _render_tags(
            _category_label(descriptor.category),
            _motion_label(descriptor),
            _modality_label(descriptor.modality_class),
            _ground_truth_label(descriptor.ground_truth_status.value),
        )
        st.write(descriptor.description)
        st.markdown("**Methods**")
        st.write(", ".join(methods))
        action_cols = st.columns([0.58, 0.42])
        with action_cols[1]:
            st.button(
                "Open in Workbench",
                key=f"open_example_{descriptor.id}",
                width="stretch",
                on_click=_open_in_workbench,
                args=(descriptor.id,),
            )


def _render_rire_panel(catalog: DatasetCatalog) -> None:
    import streamlit as st

    status = catalog.rire_status()
    manifest_display = _project_relative_path(status.get("manifest"), catalog.project_root)

    with st.container(border=True):
        title_col, status_col = st.columns([0.78, 0.22], vertical_alignment="center")
        with title_col:
            st.markdown("#### RIRE CT / MR-T1")
        with status_col:
            label = "Available locally" if status["available"] else "Local volumes unavailable"
            css_class = "research-status research-status-ok" if status["available"] else "research-status"
            st.markdown(
                f'<div class="{css_class}">{escape(label)}</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="research-case-line">CT → MR-T1 · 3D rigid · Mattes MI · Physical coordinates</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Verified landmarks or masks are not integrated. This view reports technical physical-space validation only; "
            "TRE, Dice, and anatomical correctness are not claimed."
        )

        with st.expander("Technical details", expanded=False):
            technical_rows = [
                {"Field": "Pair ID", "Value": status.get("pair_id", "n/a")},
                {"Field": "Fixed modality", "Value": status.get("fixed_modality", "n/a")},
                {"Field": "Moving modality", "Value": status.get("moving_modality", "n/a")},
                {"Field": "Transform", "Value": "3D rigid"},
                {"Field": "Method", "Value": "Mattes Mutual Information"},
                {"Field": "Ground truth", "Value": "Reference landmarks not integrated"},
                {"Field": "Manifest", "Value": manifest_display},
            ]
            st.dataframe(technical_rows, hide_index=True, width="stretch")

            show_raw = st.checkbox(
                "Show raw metadata",
                value=False,
                key="ui_show_rire_raw_metadata",
            )
            if show_raw:
                st.json(
                    {
                        "pair_id": status.get("pair_id"),
                        "availability": "available" if status["available"] else "not_available",
                        "fixed_modality": status.get("fixed_modality"),
                        "moving_modality": status.get("moving_modality"),
                        "ground_truth_status": status.get("ground_truth_status"),
                        "manifest": manifest_display,
                        "reason": status.get("reason"),
                    },
                    expanded=False,
                )


def _render_benchmark_metadata(
    descriptors: list[ExampleDescriptor],
    service: RegistrationService,
) -> None:
    import streamlit as st

    method_descriptors = {item.id: item for item in service.list_methods()}
    rows = []
    id_rows = []
    for descriptor in descriptors:
        method_names = [
            _method_family_label(method_descriptors[method_id])
            if method_id in method_descriptors
            else method_id.replace("_", " ").title()
            for method_id in descriptor.recommended_method_ids
        ]
        rows.append(
            {
                "Example": descriptor.title,
                "Motion model": _motion_label(descriptor),
                "Modality": _modality_label(descriptor.modality_class),
                "Ground truth": _ground_truth_label(descriptor.ground_truth_status.value),
                "Methods": ", ".join(dict.fromkeys(method_names)),
            }
        )
        id_rows.append(
            {
                "Example ID": descriptor.id,
                "Method IDs": ", ".join(descriptor.recommended_method_ids),
            }
        )

    st.dataframe(rows, hide_index=True, width="stretch")
    show_ids = st.checkbox(
        "Show internal identifiers",
        value=False,
        key="ui_show_benchmark_internal_ids",
    )
    if show_ids:
        st.dataframe(id_rows, hide_index=True, width="stretch")


def render_benchmark_explorer(
    catalog: DatasetCatalog,
    service: RegistrationService,
) -> None:
    import streamlit as st

    descriptors = catalog.list_examples()

    st.markdown("# Benchmark Examples")
    st.caption("Curated cases covering supported motion models and modality conditions.")

    st.markdown(
        (
            '<div class="research-summary-line">'
            f'<span><strong>{len(descriptors)}</strong> curated cases</span>'
            '<span>·</span>'
            f'<span><strong>{len({descriptor.transform_model.value for descriptor in descriptors})}</strong> motion models</span>'
            '<span>·</span>'
            '<span>Monomodal + multimodal</span>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

    st.markdown("### Synthetic benchmark cases")
    card_columns = st.columns(3, gap="medium")
    for index, descriptor in enumerate(descriptors):
        with card_columns[index % 3]:
            _render_example_card(descriptor, service=service)

    st.markdown("### Real multimodal case")
    _render_rire_panel(catalog)

    with st.expander("View benchmark metadata", expanded=False):
        _render_benchmark_metadata(descriptors, service)
