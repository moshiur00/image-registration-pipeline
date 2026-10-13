"""Transport-independent method metadata for the registration workbench."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import TransformModel


@dataclass(frozen=True, slots=True)
class MethodDescriptor:
    """Capabilities and UI guidance for one callable registration method."""

    id: str
    display_name: str
    dimensions: frozenset[int]
    motion_models: frozenset[TransformModel]
    modality_guidance: str
    requires_same_shape: bool
    diagnostics: tuple[str, ...]
    adapter_id: str
    optional: bool = False


class MethodRegistry:
    """Validated collection of method descriptors."""

    def __init__(self, descriptors: tuple[MethodDescriptor, ...]) -> None:
        ids = [descriptor.id for descriptor in descriptors]
        if len(ids) != len(set(ids)):
            raise ValueError("Method registry contains duplicate method IDs.")
        self._descriptors = {descriptor.id: descriptor for descriptor in descriptors}

    def list(self) -> list[MethodDescriptor]:
        """Return descriptors in stable ID order."""
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def get(self, method_id: str) -> MethodDescriptor | None:
        """Return a descriptor when the ID is registered."""
        return self._descriptors.get(method_id)

    def require(self, method_id: str) -> MethodDescriptor:
        """Return a descriptor or raise a clear error."""
        descriptor = self.get(method_id)
        if descriptor is None:
            raise KeyError(f"Unknown registration method: {method_id}")
        return descriptor


DEFAULT_METHODS: tuple[MethodDescriptor, ...] = (
    MethodDescriptor(
        id="phase_translation",
        display_name="Phase Correlation",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.TRANSLATION}),
        modality_guidance="monomodal translation baseline",
        requires_same_shape=True,
        diagnostics=("phase_response", "estimated_shift", "runtime"),
        adapter_id="phase_correlation",
    ),
    MethodDescriptor(
        id="ecc_translation",
        display_name="ECC Translation",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.TRANSLATION}),
        modality_guidance="monomodal intensity registration",
        requires_same_shape=True,
        diagnostics=("ecc_value", "initialization", "termination", "runtime"),
        adapter_id="ecc",
    ),
    MethodDescriptor(
        id="ecc_rigid",
        display_name="ECC Rigid",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.RIGID}),
        modality_guidance="monomodal intensity registration",
        requires_same_shape=True,
        diagnostics=("ecc_value", "initialization", "termination", "runtime"),
        adapter_id="ecc",
    ),
    MethodDescriptor(
        id="ecc_affine",
        display_name="ECC Affine",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.AFFINE}),
        modality_guidance="monomodal affine intensity registration",
        requires_same_shape=True,
        diagnostics=("ecc_value", "initialization", "termination", "runtime"),
        adapter_id="ecc",
    ),
    MethodDescriptor(
        id="orb_similarity",
        display_name="ORB + RANSAC Similarity",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.SIMILARITY}),
        modality_guidance="textured appearance-similar images",
        requires_same_shape=False,
        diagnostics=("keypoints", "matches", "inliers", "coverage", "residuals"),
        adapter_id="feature",
    ),
    MethodDescriptor(
        id="orb_affine",
        display_name="ORB + RANSAC Affine",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.AFFINE}),
        modality_guidance="textured appearance-similar images",
        requires_same_shape=False,
        diagnostics=("keypoints", "matches", "inliers", "coverage", "residuals"),
        adapter_id="feature",
    ),
    MethodDescriptor(
        id="sift_similarity",
        display_name="SIFT + RANSAC Similarity",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.SIMILARITY}),
        modality_guidance="optional higher-cost feature complement",
        requires_same_shape=False,
        diagnostics=("keypoints", "matches", "inliers", "coverage", "residuals"),
        adapter_id="feature",
        optional=True,
    ),
    MethodDescriptor(
        id="sift_affine",
        display_name="SIFT + RANSAC Affine",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.AFFINE}),
        modality_guidance="optional higher-cost feature complement",
        requires_same_shape=False,
        diagnostics=("keypoints", "matches", "inliers", "coverage", "residuals"),
        adapter_id="feature",
        optional=True,
    ),
    MethodDescriptor(
        id="mi_rigid_2d",
        display_name="Mattes MI Rigid 2D",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.RIGID}),
        modality_guidance="multimodal or intensity-remapped registration",
        requires_same_shape=True,
        diagnostics=("mi_value", "metric_trace", "stop_condition", "valid_points", "runtime"),
        adapter_id="mutual_information",
    ),
    MethodDescriptor(
        id="mi_affine_2d",
        display_name="Mattes MI Affine 2D",
        dimensions=frozenset({2}),
        motion_models=frozenset({TransformModel.AFFINE}),
        modality_guidance="multimodal or intensity-remapped affine registration",
        requires_same_shape=True,
        diagnostics=("mi_value", "metric_trace", "stop_condition", "valid_points", "runtime"),
        adapter_id="mutual_information",
    ),
    MethodDescriptor(
        id="mi_rigid_3d_rire",
        display_name="Mattes MI Rigid 3D RIRE",
        dimensions=frozenset({3}),
        motion_models=frozenset({TransformModel.RIGID}),
        modality_guidance="advanced RIRE CT/MR technical demonstration",
        requires_same_shape=False,
        diagnostics=("physical_transform", "metadata_integrity", "coverage", "convergence", "runtime"),
        adapter_id="medical_mi",
        optional=True,
    ),
)

DEFAULT_METHOD_REGISTRY = MethodRegistry(DEFAULT_METHODS)
