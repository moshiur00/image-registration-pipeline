"""Curated examples and local dataset discovery for the UI workbench."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from image_registration.io import load_image
from image_registration.multimodal import (
    edge_emphasized_representation,
    intensity_inversion,
)
from image_registration.synthetic import GroundTruthTransform, generate_synthetic_pair, image_center
from image_registration.transforms import (
    affine_matrix,
    invert_transform,
    rigid_matrix,
    similarity_matrix,
    translation_matrix,
)

from .contracts import EvaluationContext, ImageSource
from .enums import GroundTruthStatus, SourceType, TransformModel, TransformUnits


@dataclass(frozen=True, slots=True)
class ExampleDescriptor:
    """JSON-friendly description of one curated UI example."""

    id: str
    title: str
    category: str
    description: str
    transform_model: TransformModel
    ground_truth_status: GroundTruthStatus
    modality_class: str
    recommended_method_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExampleBundle:
    """Prepared fixed/moving sources plus their evidence context."""

    descriptor: ExampleDescriptor
    fixed: ImageSource
    moving: ImageSource
    evaluation: EvaluationContext


class DatasetCatalog:
    """Small read-only catalog for tracked examples and deterministic presets."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self._descriptors = {
            item.id: item
            for item in (
                ExampleDescriptor(
                    id="tracked_week01_pair",
                    title="Week 1 tracked pair",
                    category="tracked",
                    description="Tracked fixed and moving sample pair used by the Week 1 smoke workflow.",
                    transform_model=TransformModel.SIMILARITY,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="monomodal",
                    recommended_method_ids=("orb_similarity", "sift_similarity"),
                ),
                ExampleDescriptor(
                    id="synthetic_translation",
                    title="Translation",
                    category="synthetic",
                    description="Known translation generated deterministically from the tracked camera image.",
                    transform_model=TransformModel.TRANSLATION,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="monomodal",
                    recommended_method_ids=("phase_translation", "ecc_translation"),
                ),
                ExampleDescriptor(
                    id="synthetic_rigid",
                    title="Rigid rotation",
                    category="synthetic",
                    description="Known rigid rotation and translation generated deterministically from the tracked camera image.",
                    transform_model=TransformModel.RIGID,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="monomodal",
                    recommended_method_ids=("ecc_rigid", "mi_rigid_2d"),
                ),
                ExampleDescriptor(
                    id="synthetic_similarity",
                    title="Similarity transform",
                    category="synthetic",
                    description="Known rotation, scale, and translation for feature-based registration.",
                    transform_model=TransformModel.SIMILARITY,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="monomodal",
                    recommended_method_ids=("orb_similarity", "sift_similarity"),
                ),
                ExampleDescriptor(
                    id="synthetic_affine",
                    title="Affine transform",
                    category="synthetic",
                    description="Known affine deformation for ECC, feature-based, and Mutual Information registration.",
                    transform_model=TransformModel.AFFINE,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="monomodal",
                    recommended_method_ids=("ecc_affine", "orb_affine", "sift_affine", "mi_affine_2d"),
                ),
                ExampleDescriptor(
                    id="synthetic_inversion_rigid",
                    title="Intensity inversion",
                    category="synthetic_multimodal",
                    description="Rigid geometry with an intensity-inverted moving image for multimodal registration.",
                    transform_model=TransformModel.RIGID,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="simulated_multimodal",
                    recommended_method_ids=("mi_rigid_2d",),
                ),
                ExampleDescriptor(
                    id="synthetic_edge_affine",
                    title="Edge-emphasized multimodal",
                    category="synthetic_multimodal",
                    description="Affine geometry with an edge-emphasized moving-image representation for a difficult multimodal case.",
                    transform_model=TransformModel.AFFINE,
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    modality_class="simulated_multimodal",
                    recommended_method_ids=("mi_affine_2d",),
                ),
            )
        }

    def list_examples(self) -> list[ExampleDescriptor]:
        """Return public-facing research examples for the workbench.

        Internal development fixtures remain buildable by ID but are intentionally
        omitted from the portfolio-facing catalog.
        """
        return [
            self._descriptors[key]
            for key in sorted(self._descriptors)
            if key != "tracked_week01_pair"
        ]

    def list_internal_examples(self) -> list[ExampleDescriptor]:
        """Return every catalog entry, including internal development fixtures."""
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def get(self, example_id: str) -> ExampleDescriptor:
        try:
            return self._descriptors[example_id]
        except KeyError as exc:
            raise KeyError(f"Unknown UI example: {example_id}") from exc

    def _camera(self) -> np.ndarray:
        path = self.project_root / "data" / "samples" / "week02_real_general" / "camera.png"
        return np.asarray(load_image(path, color_mode="grayscale").array)

    @staticmethod
    def _ground_truth(transform_type: str, matrix: np.ndarray, parameters: dict[str, Any]) -> GroundTruthTransform:
        return GroundTruthTransform(
            transform_type=transform_type,
            parameters=parameters,
            moving_to_fixed=np.asarray(matrix, dtype=np.float64),
            fixed_to_moving=invert_transform(matrix),
        )

    def _synthetic_bundle(self, descriptor: ExampleDescriptor) -> ExampleBundle:
        fixed = self._camera()
        center = image_center(fixed.shape)
        mapping = "none"
        if descriptor.id == "synthetic_translation":
            matrix = translation_matrix(14.0, -9.0)
            parameters = {"tx": 14.0, "ty": -9.0}
        elif descriptor.id in {"synthetic_rigid", "synthetic_inversion_rigid"}:
            matrix = rigid_matrix(8.0, tx=10.0, ty=-6.0, center=center)
            parameters = {"angle_degrees": 8.0, "tx": 10.0, "ty": -6.0, "center": center.tolist()}
            if descriptor.id == "synthetic_inversion_rigid":
                mapping = "intensity_inversion"
        elif descriptor.id == "synthetic_similarity":
            matrix = similarity_matrix(1.05, angle_degrees=6.0, tx=8.0, ty=-5.0, center=center)
            parameters = {"scale": 1.05, "angle_degrees": 6.0, "tx": 8.0, "ty": -5.0, "center": center.tolist()}
        elif descriptor.id in {"synthetic_affine", "synthetic_edge_affine"}:
            linear = np.array([[1.04, 0.05], [-0.03, 0.97]], dtype=np.float64)
            matrix = affine_matrix(linear, tx=8.0, ty=-5.0, center=center)
            parameters = {"linear": linear.tolist(), "tx": 8.0, "ty": -5.0, "center": center.tolist()}
            if descriptor.id == "synthetic_edge_affine":
                mapping = "edge_emphasized"
        else:  # pragma: no cover - guarded by descriptor registry
            raise KeyError(descriptor.id)

        truth = self._ground_truth(descriptor.transform_model.value, matrix, parameters)
        pair = generate_synthetic_pair(fixed, truth, interpolation="linear", border_value=0.0)
        moving = pair.moving
        if mapping == "intensity_inversion":
            moving = intensity_inversion(moving)
        elif mapping == "edge_emphasized":
            moving = edge_emphasized_representation(moving)

        common_metadata = {
            "ndim": 2,
            "shape": list(fixed.shape),
            "example_id": descriptor.id,
            "modality_class": descriptor.modality_class,
            "mapping": mapping,
        }
        return ExampleBundle(
            descriptor=descriptor,
            fixed=ImageSource(
                source_type=SourceType.SYNTHETIC_PRESET,
                display_name=f"{descriptor.title} - fixed",
                modality="visible",
                array=np.asarray(pair.fixed),
                metadata=dict(common_metadata),
            ),
            moving=ImageSource(
                source_type=SourceType.SYNTHETIC_PRESET,
                display_name=f"{descriptor.title} - moving",
                modality="visible" if mapping == "none" else "simulated_multimodal",
                array=np.asarray(moving),
                metadata=dict(common_metadata),
            ),
            evaluation=EvaluationContext(
                ground_truth_status=GroundTruthStatus.KNOWN,
                ground_truth_transform=truth.moving_to_fixed,
                fixed_landmarks=pair.control_points_fixed,
                moving_landmarks=pair.control_points_moving,
                units=TransformUnits.PIXELS,
            ),
        )

    def build(self, example_id: str) -> ExampleBundle:
        descriptor = self.get(example_id)
        if example_id == "tracked_week01_pair":
            fixed_path = self.project_root / "data" / "samples" / "week01" / "fixed.png"
            moving_path = self.project_root / "data" / "samples" / "week01" / "moving.png"
            config_path = self.project_root / "configs" / "day05_week01_smoke_test.yaml"
            # Ground truth is duplicated from the tracked Week 1 configuration only to expose
            # the already documented example through the UI catalog.
            center = np.array([110.0, 80.0], dtype=np.float64)
            transform = similarity_matrix(0.97, angle_degrees=5.0, tx=12.0, ty=-7.0, center=center)
            return ExampleBundle(
                descriptor=descriptor,
                fixed=ImageSource(
                    SourceType.EXAMPLE,
                    "Week 1 fixed",
                    path=fixed_path,
                    metadata={"ndim": 2, "shape": [160, 220], "source_config": str(config_path)},
                ),
                moving=ImageSource(
                    SourceType.EXAMPLE,
                    "Week 1 moving",
                    path=moving_path,
                    metadata={"ndim": 2, "shape": [160, 220], "source_config": str(config_path)},
                ),
                evaluation=EvaluationContext(
                    ground_truth_status=GroundTruthStatus.KNOWN,
                    ground_truth_transform=transform,
                    units=TransformUnits.PIXELS,
                ),
            )
        return self._synthetic_bundle(descriptor)

    def rire_status(self) -> dict[str, Any]:
        manifest_path = self.project_root / "data" / "manifests" / "rire_training001.json"
        if not manifest_path.is_file():
            return {"available": False, "reason": "manifest_missing", "manifest": str(manifest_path)}
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = payload["records"][0]
        fixed_path = self.project_root / record["fixed_image"]
        moving_path = self.project_root / record["moving_image"]
        available = fixed_path.is_file() and moving_path.is_file()
        return {
            "available": available,
            "pair_id": record["pair_id"],
            "fixed_modality": record["fixed_modality"],
            "moving_modality": record["moving_modality"],
            "fixed_path": str(fixed_path),
            "moving_path": str(moving_path),
            "ground_truth_status": record["ground_truth_status"],
            "manifest": str(manifest_path),
            "reason": None if available else "local_volume_files_missing",
        }
