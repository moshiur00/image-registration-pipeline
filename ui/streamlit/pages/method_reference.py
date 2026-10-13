"""Research-facing method reference generated from the framework-neutral registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ui.core.enums import TransformModel
from ui.core.method_registry import MethodDescriptor
from ui.core.registration_service import RegistrationService


_DIAGNOSTIC_LABELS = {
    "phase_response": "Phase response",
    "estimated_shift": "Estimated shift",
    "runtime": "Runtime",
    "ecc_value": "ECC objective",
    "initialization": "Initialization",
    "termination": "Convergence",
    "keypoints": "Keypoints",
    "matches": "Matches",
    "inliers": "RANSAC inliers",
    "coverage": "Spatial coverage",
    "residuals": "Residuals",
    "mi_value": "MI value",
    "metric_trace": "Convergence trace",
    "stop_condition": "Stop condition",
    "valid_points": "Valid metric points",
    "physical_transform": "Physical transform",
    "metadata_integrity": "Metadata integrity",
    "convergence": "Convergence",
}

_MOTION_ORDER = (
    TransformModel.TRANSLATION,
    TransformModel.RIGID,
    TransformModel.SIMILARITY,
    TransformModel.AFFINE,
)


@dataclass(frozen=True, slots=True)
class MethodFamily:
    """One human-facing method family assembled from registry descriptors."""

    title: str
    subtitle: str
    method_ids: tuple[str, ...]
    best_suited_for: str
    status_label: str


_METHOD_FAMILIES: tuple[MethodFamily, ...] = (
    MethodFamily(
        title="Phase Correlation",
        subtitle="Frequency-domain translation registration",
        method_ids=("phase_translation",),
        best_suited_for="Fast 2D monomodal registration when translation is the dominant motion.",
        status_label="Core method",
    ),
    MethodFamily(
        title="ECC",
        subtitle="Intensity-based registration",
        method_ids=("ecc_translation", "ecc_rigid", "ecc_affine"),
        best_suited_for="Monomodal images with related intensity structure and translation, rigid, or affine motion.",
        status_label="Core method",
    ),
    MethodFamily(
        title="ORB + RANSAC",
        subtitle="Feature-based registration",
        method_ids=("orb_similarity", "orb_affine"),
        best_suited_for="Textured, appearance-similar image pairs where local feature correspondences are reliable.",
        status_label="Core method",
    ),
    MethodFamily(
        title="SIFT + RANSAC",
        subtitle="Feature-based registration",
        method_ids=("sift_similarity", "sift_affine"),
        best_suited_for="Feature-rich cases where a more expensive descriptor is useful as a complement to ORB.",
        status_label="Optional complement",
    ),
    MethodFamily(
        title="Mattes Mutual Information",
        subtitle="Multimodal intensity registration",
        method_ids=("mi_rigid_2d", "mi_affine_2d"),
        best_suited_for="2D multimodal or intensity-remapped registration with rigid or affine motion.",
        status_label="Core method",
    ),
)

_RIRE_METHOD_ID = "mi_rigid_3d_rire"


def _descriptor_map(service: RegistrationService) -> dict[str, MethodDescriptor]:
    return {descriptor.id: descriptor for descriptor in service.list_methods()}


def _family_descriptors(
    service: RegistrationService,
    family: MethodFamily,
) -> tuple[MethodDescriptor, ...]:
    descriptors = _descriptor_map(service)
    return tuple(descriptors[method_id] for method_id in family.method_ids if method_id in descriptors)


def _human_diagnostic(value: str) -> str:
    return _DIAGNOSTIC_LABELS.get(value, value.replace("_", " ").title())


def _stable_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _motion_models(descriptors: Iterable[MethodDescriptor]) -> list[str]:
    descriptor_list = tuple(descriptors)
    labels: list[str] = []
    for motion in _MOTION_ORDER:
        if any(motion in descriptor.motion_models for descriptor in descriptor_list):
            labels.append(motion.value.title())
    return labels


def _dimensions(descriptors: Iterable[MethodDescriptor]) -> list[str]:
    values = sorted({dimension for descriptor in descriptors for dimension in descriptor.dimensions})
    return [f"{value}D" for value in values]


def _diagnostics(descriptors: Iterable[MethodDescriptor]) -> list[str]:
    raw = _stable_unique(
        diagnostic
        for descriptor in descriptors
        for diagnostic in descriptor.diagnostics
    )
    return [_human_diagnostic(item) for item in raw]


def _render_tags(*labels: str) -> None:
    from html import escape

    import streamlit as st

    tags = "".join(f'<span class="research-tag">{escape(label)}</span>' for label in labels if label)
    st.markdown(f'<div class="research-tag-row">{tags}</div>', unsafe_allow_html=True)


def _render_method_card(
    service: RegistrationService,
    family: MethodFamily,
) -> None:
    import streamlit as st

    descriptors = _family_descriptors(service, family)
    with st.container(border=True):
        st.markdown(f"#### {family.title}")
        st.caption(family.subtitle)
        _render_tags(*_dimensions(descriptors), family.status_label)

        st.markdown("**Motion models**")
        st.write(" · ".join(_motion_models(descriptors)))

        st.markdown("**Best suited for**")
        st.write(family.best_suited_for)

        st.markdown("**Key diagnostics**")
        st.write(" · ".join(_diagnostics(descriptors)))


def _compatibility_rows(service: RegistrationService) -> list[dict[str, str]]:
    """Build a compact human-facing compatibility matrix from registry data."""
    rows: list[dict[str, str]] = []
    for family in _METHOD_FAMILIES:
        descriptors = _family_descriptors(service, family)
        motions = {motion for descriptor in descriptors for motion in descriptor.motion_models}
        rows.append(
            {
                "Method": family.title,
                "Dimension": ", ".join(_dimensions(descriptors)),
                "Translation": "✓" if TransformModel.TRANSLATION in motions else "",
                "Rigid": "✓" if TransformModel.RIGID in motions else "",
                "Similarity": "✓" if TransformModel.SIMILARITY in motions else "",
                "Affine": "✓" if TransformModel.AFFINE in motions else "",
                "Typical use": family.best_suited_for.split(".", maxsplit=1)[0],
            }
        )

    descriptor = _descriptor_map(service).get(_RIRE_METHOD_ID)
    if descriptor is not None:
        rows.append(
            {
                "Method": "RIRE CT / MR-T1",
                "Dimension": ", ".join(_dimensions((descriptor,))),
                "Translation": "",
                "Rigid": "✓",
                "Similarity": "",
                "Affine": "",
                "Typical use": "Real CT / MR technical validation in physical coordinates",
            }
        )
    return rows


def _render_rire_extension(service: RegistrationService) -> None:
    import streamlit as st

    descriptor = _descriptor_map(service).get(_RIRE_METHOD_ID)
    if descriptor is None:
        return

    with st.container(border=True):
        title_col, status_col = st.columns([0.78, 0.22], vertical_alignment="center")
        with title_col:
            st.markdown("#### RIRE CT / MR-T1")
            st.caption("Real-data extension")
        with status_col:
            st.markdown('<div class="research-status">Advanced path</div>', unsafe_allow_html=True)

        _render_tags("3D", "Rigid", "Mattes MI", "Physical coordinates")
        st.write("Technical physical-space registration of CT as fixed and MR-T1 as moving.")

        info_cols = st.columns(3)
        with info_cols[0]:
            st.markdown("**Fixed modality**")
            st.write("CT")
        with info_cols[1]:
            st.markdown("**Moving modality**")
            st.write("MR-T1")
        with info_cols[2]:
            st.markdown("**Reference status**")
            st.write("Verified landmarks not integrated")

        st.caption(
            "This path reports technical physical-space evidence only. TRE, Dice, and anatomical correctness are not claimed."
        )


def _render_evidence_principles() -> None:
    import streamlit as st

    st.markdown("### Evidence interpretation")
    columns = st.columns(3, gap="medium")
    items = (
        (
            "Execution",
            "A returned estimate means the method completed. It does not by itself establish geometric correctness.",
        ),
        (
            "Geometric correctness",
            "TRE and reference-transform errors are reported only when the reference geometry is known.",
        ),
        (
            "Unknown images",
            "Uploaded images receive descriptive metrics and plausibility diagnostics, but no TRE-based PASS claim.",
        ),
    )
    for column, (title, body) in zip(columns, items, strict=True):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(body)

    st.caption("Transform convention: Moving -> Fixed")


def _render_technical_registry(service: RegistrationService) -> None:
    import streamlit as st

    rows = []
    for descriptor in service.list_methods():
        rows.append(
            {
                "Method": descriptor.display_name,
                "ID": descriptor.id,
                "Dimensions": ", ".join(str(v) for v in sorted(descriptor.dimensions)),
                "Motion model": ", ".join(v.value for v in sorted(descriptor.motion_models, key=lambda x: x.value)),
                "Guidance": descriptor.modality_guidance,
                "Raw diagnostics": ", ".join(descriptor.diagnostics),
                "Adapter": descriptor.adapter_id,
                "Optional": "yes" if descriptor.optional else "no",
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def render_method_reference(service: RegistrationService) -> None:
    import streamlit as st

    st.markdown("# Method Reference")
    st.caption("Registration methods, supported transformations, and diagnostic outputs.")

    st.markdown("### Intensity-based methods")
    intensity_columns = st.columns(2, gap="medium")
    for column, family in zip(intensity_columns, _METHOD_FAMILIES[:2], strict=True):
        with column:
            _render_method_card(service, family)

    st.markdown("### Feature-based methods")
    feature_columns = st.columns(2, gap="medium")
    for column, family in zip(feature_columns, _METHOD_FAMILIES[2:4], strict=True):
        with column:
            _render_method_card(service, family)

    st.markdown("### Multimodal registration")
    multimodal_columns = st.columns([0.5, 0.5], gap="medium")
    with multimodal_columns[0]:
        _render_method_card(service, _METHOD_FAMILIES[4])

    st.markdown("### Real-data extension")
    _render_rire_extension(service)

    st.markdown("### Method compatibility")
    st.dataframe(_compatibility_rows(service), hide_index=True, width="stretch")

    _render_evidence_principles()

    with st.expander("View technical registry", expanded=False):
        st.caption("Implementation identifiers and raw diagnostic field names are shown here for reproducibility and debugging.")
        _render_technical_registry(service)
