"""Method and preprocessing controls for the Streamlit workbench."""

from __future__ import annotations

from typing import Any

from ui.core.contracts import PreprocessingSpec
from ui.core.method_registry import MethodDescriptor
from ui.streamlit.view_model import default_method_configuration, default_preprocessing


def render_preprocessing_controls(method_id: str) -> PreprocessingSpec:
    import streamlit as st

    defaults = default_preprocessing(method_id)
    st.markdown("#### Preprocessing")
    st.caption("All preprocessing applied by the workbench is explicit and included in the run summary.")

    normalization = st.selectbox(
        "Normalization",
        options=["None", "Robust 0-1"],
        index=1 if defaults.normalization else 0,
        help="Robust normalization uses percentile scaling. No histogram matching is applied.",
    )
    use_clipping = st.checkbox("Percentile clipping", value=False)
    clipping = None
    if use_clipping:
        clip_cols = st.columns(2)
        low = clip_cols[0].number_input("Lower percentile", 0.0, 49.0, 1.0, 0.5)
        high = clip_cols[1].number_input("Upper percentile", 51.0, 100.0, 99.0, 0.5)
        clipping = (float(low), float(high))

    sigma = st.number_input(
        "Gaussian smoothing sigma",
        min_value=0.0,
        max_value=8.0,
        value=float(defaults.gaussian_sigma or 0.0),
        step=0.25,
        help="0 disables smoothing.",
    )
    return PreprocessingSpec(
        grayscale=True,
        clipping_percentiles=clipping,
        normalization="robust" if normalization == "Robust 0-1" else None,
        gaussian_sigma=float(sigma),
        resize_policy="none",
    )


def render_method_controls(method: MethodDescriptor) -> tuple[str | None, dict[str, Any]]:
    import streamlit as st

    initialization, defaults = default_method_configuration(method.id)
    params: dict[str, Any] = dict(defaults)

    st.markdown("#### Method settings")
    st.caption(method.modality_guidance)
    st.text_input("Transform model", value=next(iter(method.motion_models)).value, disabled=True)

    if method.id == "phase_translation":
        params["use_hanning_window"] = st.checkbox(
            "Hanning window", value=bool(defaults["use_hanning_window"])
        )
        params["subtract_mean"] = st.checkbox(
            "Subtract mean", value=bool(defaults["subtract_mean"])
        )

    elif method.id.startswith("ecc_"):
        init_options = ["identity", "phase_correlation"]
        initialization = st.selectbox(
            "Initialization",
            init_options,
            index=init_options.index(initialization or "identity"),
        )
        params["max_iterations"] = int(
            st.number_input("Maximum iterations", 20, 1000, int(defaults["max_iterations"]), 10)
        )
        params["epsilon"] = float(
            st.number_input(
                "Termination epsilon",
                min_value=1e-9,
                max_value=1e-2,
                value=float(defaults["epsilon"]),
                format="%.8f",
            )
        )
        params["gauss_filt_size"] = int(
            st.selectbox("ECC Gaussian filter size", [1, 3, 5, 7, 9], index=2)
        )
        params["multiresolution"] = st.checkbox(
            "Multiresolution",
            value=bool(defaults["multiresolution"]),
            help="Uses the validated coarse-to-fine ECC path.",
        )

    elif method.id.startswith(("orb_", "sift_")):
        params["n_features"] = int(st.number_input("Maximum features", 100, 5000, 800, 100))
        params["ratio_threshold"] = float(
            st.slider("KNN ratio threshold", 0.50, 0.95, float(defaults["ratio_threshold"]), 0.05)
        )
        params["reprojection_threshold"] = float(
            st.number_input(
                "RANSAC reprojection threshold (px)",
                min_value=0.5,
                max_value=20.0,
                value=float(defaults["reprojection_threshold"]),
                step=0.5,
            )
        )
        with st.expander("Advanced RANSAC settings", expanded=False):
            params["confidence"] = float(
                st.number_input("Confidence", 0.50, 0.9999, float(defaults["confidence"]), 0.01)
            )
            params["random_seed"] = int(
                st.number_input("Random seed", 0, 1_000_000, int(defaults["random_seed"]), 1)
            )

    elif method.id.startswith("mi_"):
        init_options = ["identity", "geometry", "moments"]
        initialization = st.selectbox(
            "Initialization",
            init_options,
            index=init_options.index(initialization or "identity"),
        )
        params["histogram_bins"] = int(
            st.number_input("Mattes MI histogram bins", 8, 256, int(defaults["histogram_bins"]), 8)
        )
        sampling_label = st.selectbox("Metric sampling", ["Full", "Random"], index=0)
        if sampling_label == "Full":
            params["sampling_strategy"] = "none"
            params["sampling_percentage"] = 1.0
        else:
            params["sampling_strategy"] = "random"
            params["sampling_percentage"] = float(
                st.slider("Sampling percentage", 0.05, 1.0, 0.20, 0.05)
            )
        with st.expander("Advanced MI optimizer settings", expanded=False):
            params["number_of_iterations"] = int(
                st.number_input("Maximum iterations", 20, 1000, int(defaults["number_of_iterations"]), 10)
            )
            params["learning_rate"] = float(
                st.number_input("Learning rate", 0.01, 20.0, float(defaults["learning_rate"]), 0.25)
            )
            params["minimum_step"] = float(
                st.number_input(
                    "Minimum step",
                    min_value=1e-6,
                    max_value=1.0,
                    value=float(defaults["minimum_step"]),
                    format="%.6f",
                )
            )
            params["sampling_seed"] = int(
                st.number_input("Sampling seed", 0, 1_000_000, int(defaults["sampling_seed"]), 1)
            )
            st.caption("Pyramid: shrink factors 4, 2, 1 with smoothing sigmas 2, 1, 0.")

    return initialization, params
