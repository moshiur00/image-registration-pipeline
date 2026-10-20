"""Stage 6.1 framework-neutral automatic comparison service.

This module adapts the frozen Week 6 automatic-registration backend to stable UI
view models. It contains no Streamlit dependency and does not implement a final
method ranking, confidence score, or best-method recommendation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

import numpy as np

from image_registration.automatic_agreement import build_preliminary_consensus
from image_registration.automatic_registration import (
    AutoMethodSpec,
    AutoPairProfile,
    AutomaticMultiMethodService,
    AutomaticRunResult,
    NormalizedCandidateEvidence,
)
from image_registration.evaluation_contracts import (
    ExecutionStatus,
    ReferenceEvidence,
    UnifiedEvaluationRecord,
)
from image_registration.overlap import transformed_support_mask
from image_registration.unified_metrics import overlap_aware_descriptive_metrics
from ui.adapters import build_default_registration_service
from ui.core.contracts import (
    EvaluationContext,
    ImageSource,
    PreprocessingSpec,
    RegistrationRequest,
    RegistrationSpec,
)
from ui.core.enums import GroundTruthStatus, TransformModel, TransformUnits
from ui.core.image_inputs import PreparedImage, prepare_image_source
from ui.core.registration_service import RegistrationService, hash_image_source

from .models import (
    AgreementComparisonView,
    AutomaticComparisonRequest,
    AutomaticComparisonView,
    CandidateAgreementView,
    CandidateComparisonView,
    CompatibilityPreviewView,
    MethodCompatibilityView,
    PairwiseAgreementView,
)

SUPPORTED_MODALITY_CLASSES = frozenset(
    {"monomodal", "multimodal", "simulated_multimodal", "unknown"}
)

CONSENSUS_INTERPRETATION = (
    "The consensus anchor is the candidate whose estimated transform is most central "
    "to the candidate set. It is not a validated best-method recommendation."
)


def _automatic_method_configuration(method_id: str) -> tuple[str | None, dict[str, Any]]:
    """Return the validated automatic-comparison defaults for one method."""
    if method_id == "phase_translation":
        return None, {
            "use_hanning_window": True,
            "subtract_mean": True,
            "interpolation": "linear",
        }
    if method_id.startswith("ecc_"):
        return "identity", {
            "max_iterations": 150,
            "epsilon": 1e-6,
            "gauss_filt_size": 5,
            "multiresolution": method_id == "ecc_affine",
            "pyramid_scales": (0.25, 0.5, 1.0),
            "pre_smoothing_sigma": 0.8,
            "interpolation": "linear",
        }
    if method_id.startswith(("orb_", "sift_")):
        affine = method_id.endswith("_affine")
        return None, {
            "n_features": 800,
            "ratio_threshold": 0.75,
            "minimum_matches": 6 if affine else 4,
            "reprojection_threshold": 3.0,
            "confidence": 0.99,
            "max_trials": 3000 if affine else 2000,
            "minimum_inliers": 6 if affine else 4,
            "minimum_spatial_coverage": 0.125 if affine else 0.0,
            "random_seed": 42,
            "interpolation": "linear",
        }
    if method_id.startswith("mi_"):
        return "geometry", {
            "histogram_bins": 32,
            "sampling_strategy": "none",
            "sampling_percentage": 1.0,
            "sampling_seed": 42,
            "learning_rate": 2.0,
            "minimum_step": 1e-3,
            "number_of_iterations": 150,
            "relaxation_factor": 0.5,
            "gradient_magnitude_tolerance": 1e-4,
            "shrink_factors": (4, 2, 1),
            "smoothing_sigmas": (2.0, 1.0, 0.0),
        }
    return None, {}


def _method_family(method_id: str) -> str:
    if method_id.startswith("phase_"):
        return "frequency_domain"
    if method_id.startswith("ecc_"):
        return "intensity_based"
    if method_id.startswith(("orb_", "sift_")):
        return "feature_based"
    if method_id.startswith("mi_"):
        return "mutual_information"
    return "other"


def _supported_modalities(method_id: str) -> frozenset[str]:
    # Unknown is intentionally permissive. It means that modality assumptions
    # are not available to exclude a method before execution, not that the method
    # is expected to be reliable for every modality.
    if method_id.startswith("mi_"):
        return frozenset({"monomodal", "multimodal", "simulated_multimodal", "unknown"})
    return frozenset({"monomodal", "unknown"})


def build_default_auto_method_catalog(
    registration_service: RegistrationService,
) -> tuple[AutoMethodSpec, ...]:
    """Build the automatic catalog from the existing 2D UI method registry."""
    methods: list[AutoMethodSpec] = []
    for descriptor in registration_service.list_methods():
        if 2 not in descriptor.dimensions:
            continue
        models = sorted(model.value for model in descriptor.motion_models)
        if len(models) != 1:
            raise ValueError(
                f"Automatic UI catalog requires one motion model per method: {descriptor.id}"
            )
        initialization, parameters = _automatic_method_configuration(descriptor.id)
        methods.append(
            AutoMethodSpec(
                method_id=descriptor.id,
                display_name=descriptor.display_name,
                method_family=_method_family(descriptor.id),
                transform_model=models[0],
                dimensions=frozenset({2}),
                supported_modality_classes=_supported_modalities(descriptor.id),
                requires_same_shape=bool(descriptor.requires_same_shape),
                optional=bool(descriptor.optional),
                metadata={
                    "initialization": initialization,
                    "parameters": dict(parameters),
                    "diagnostics": list(descriptor.diagnostics),
                },
            )
        )
    if not methods:
        raise ValueError("No 2D registration methods are available for automatic comparison.")
    return tuple(sorted(methods, key=lambda item: item.method_id))


def _preprocessing_payload(spec: PreprocessingSpec) -> dict[str, Any]:
    return {
        "grayscale": bool(spec.grayscale),
        "clipping_percentiles": None
        if spec.clipping_percentiles is None
        else list(spec.clipping_percentiles),
        "normalization": spec.normalization,
        "gaussian_sigma": spec.gaussian_sigma,
        "resize_policy": spec.resize_policy,
    }


def _pair_id(request: AutomaticComparisonRequest) -> str:
    payload = {
        "fixed_sha256": hash_image_source(request.fixed),
        "moving_sha256": hash_image_source(request.moving),
        "transform_model": request.transform_model.value,
        "modality_class": request.modality_class.strip().lower(),
        "preprocessing": _preprocessing_payload(request.preprocessing),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "ui-auto-" + hashlib.sha256(encoded).hexdigest()[:20]


def _as_transform_tuple(matrix: np.ndarray | None) -> tuple[tuple[float, ...], ...] | None:
    if matrix is None:
        return None
    values = np.asarray(matrix, dtype=np.float64)
    return tuple(tuple(float(value) for value in row) for row in values)


class AutomaticComparisonService:
    """Validate, execute, normalize, and compare automatic registration candidates."""

    def __init__(
        self,
        *,
        registration_service: RegistrationService | None = None,
        methods: Sequence[AutoMethodSpec] | None = None,
        evaluation_mi_bins: int = 24,
        agreement_grid_rows: int = 5,
        agreement_grid_cols: int = 5,
        agreement_margin_fraction: float = 0.10,
    ) -> None:
        self._registration_service = registration_service or build_default_registration_service()
        self._methods = tuple(
            methods
            if methods is not None
            else build_default_auto_method_catalog(self._registration_service)
        )
        if not self._methods:
            raise ValueError("Automatic comparison method catalog must not be empty.")
        method_ids = [method.method_id for method in self._methods]
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("Automatic comparison method catalog contains duplicate IDs.")
        if int(evaluation_mi_bins) < 2:
            raise ValueError("evaluation_mi_bins must be at least 2.")
        self._evaluation_mi_bins = int(evaluation_mi_bins)
        self._agreement_grid_rows = int(agreement_grid_rows)
        self._agreement_grid_cols = int(agreement_grid_cols)
        self._agreement_margin_fraction = float(agreement_margin_fraction)
        self._method_by_id = {method.method_id: method for method in self._methods}

    @property
    def methods(self) -> tuple[AutoMethodSpec, ...]:
        return self._methods

    def _validate_request(self, request: AutomaticComparisonRequest) -> str:
        modality = str(request.modality_class).strip().lower()
        if modality not in SUPPORTED_MODALITY_CLASSES:
            raise ValueError(
                "modality_class must be one of: "
                + ", ".join(sorted(SUPPORTED_MODALITY_CLASSES))
            )
        if request.transform_model not in {
            TransformModel.TRANSLATION,
            TransformModel.RIGID,
            TransformModel.SIMILARITY,
            TransformModel.AFFINE,
        }:
            raise ValueError("Automatic comparison currently supports 2D transform models only.")
        return modality

    def _prepare_pair(
        self,
        request: AutomaticComparisonRequest,
    ) -> tuple[AutoPairProfile, PreparedImage, PreparedImage]:
        modality = self._validate_request(request)
        fixed = prepare_image_source(request.fixed, request.preprocessing, name="Fixed")
        moving = prepare_image_source(request.moving, request.preprocessing, name="Moving")
        if fixed.array.ndim != 2 or moving.array.ndim != 2:
            raise ValueError("Automatic comparison currently requires preprocessed 2D images.")

        pair = AutoPairProfile(
            pair_id=_pair_id(request),
            dimensions=2,
            modality_class=modality,
            candidate_transform_models=(request.transform_model.value,),
            same_shape=bool(fixed.array.shape == moving.array.shape),
            # Stage 6 automatic comparison deliberately behaves as an unknown-GT workflow.
            reference=ReferenceEvidence(),
            metadata={
                "ground_truth_policy": "unavailable",
                "fixed_display_name": request.fixed.display_name,
                "moving_display_name": request.moving.display_name,
                "fixed_shape": list(fixed.array.shape),
                "moving_shape": list(moving.array.shape),
                "preprocessing": _preprocessing_payload(request.preprocessing),
            },
        )
        return pair, fixed, moving

    def _compatibility_view(
        self,
        *,
        pair: AutoPairProfile,
        image_shape: tuple[int, int],
        include_optional: bool,
    ) -> CompatibilityPreviewView:
        service = AutomaticMultiMethodService(
            self._methods,
            lambda task: (_ for _ in ()).throw(RuntimeError("preview executor is unused")),
            include_optional=include_optional,
        )
        decisions = service.compatibility(pair)
        compatible: list[MethodCompatibilityView] = []
        excluded: list[MethodCompatibilityView] = []
        for decision in decisions:
            method = self._method_by_id[decision.method_id]
            view = MethodCompatibilityView(
                method_id=method.method_id,
                display_name=method.display_name,
                method_family=method.method_family,
                transform_model=method.transform_model,
                optional=method.optional,
                compatible=decision.compatible,
                reasons=tuple(decision.reasons),
            )
            (compatible if decision.compatible else excluded).append(view)

        return CompatibilityPreviewView(
            pair_id=pair.pair_id,
            image_shape=image_shape,
            same_shape=pair.same_shape,
            modality_class=pair.modality_class,
            transform_model=pair.candidate_transform_models[0],
            ground_truth_status="unavailable",
            compatible=tuple(compatible),
            excluded=tuple(excluded),
        )

    def preview(self, request: AutomaticComparisonRequest) -> CompatibilityPreviewView:
        """Validate an image pair and return compatibility without executing methods."""
        pair, fixed, _moving = self._prepare_pair(request)
        return self._compatibility_view(
            pair=pair,
            image_shape=(int(fixed.array.shape[0]), int(fixed.array.shape[1])),
            include_optional=request.include_optional_methods,
        )

    def _candidate_executor(
        self,
        *,
        request: AutomaticComparisonRequest,
        fixed: PreparedImage,
        moving: PreparedImage,
        registered_available: dict[str, bool],
    ):
        def execute(task) -> UnifiedEvaluationRecord:
            method_parameters = dict(task.method.metadata.get("parameters", {}))
            initialization = task.method.metadata.get("initialization")
            registration_request = RegistrationRequest(
                fixed=request.fixed,
                moving=request.moving,
                preprocessing=request.preprocessing,
                registration=RegistrationSpec(
                    method_id=task.method.method_id,
                    transform_model=TransformModel(task.method.transform_model),
                    initialization=None if initialization is None else str(initialization),
                    parameters=method_parameters,
                    interpolation=str(method_parameters.get("interpolation", "bilinear")),
                ),
                evaluation=EvaluationContext(
                    ground_truth_status=GroundTruthStatus.UNAVAILABLE,
                    units=TransformUnits.PIXELS,
                ),
                request_id=task.candidate_id,
            )

            run = self._registration_service.run(registration_request)
            status = ExecutionStatus(run.run_status.value)
            estimated = (
                None
                if run.transform is None
                else np.asarray(run.transform.matrix, dtype=np.float64)
            )
            timings = {"total": max(0.0, float(run.runtime_seconds) * 1000.0)}
            metrics: dict[str, float] = {"total_runtime_ms": timings["total"]}
            overlap_fraction = None
            registered_available[task.candidate_id] = run.registered_array is not None

            evaluation_warnings = list(run.warnings)
            if (
                run.registered_array is not None
                and estimated is not None
                and status in {ExecutionStatus.COMPLETED, ExecutionStatus.CHECK}
            ):
                try:
                    support = transformed_support_mask(
                        moving.array.shape,
                        estimated,
                        destination_shape=(int(fixed.array.shape[0]), int(fixed.array.shape[1])),
                    )
                    descriptive = overlap_aware_descriptive_metrics(
                        fixed.array,
                        np.asarray(run.registered_array),
                        support,
                        mi_bins=self._evaluation_mi_bins,
                    )
                    overlap_fraction = float(descriptive["valid_overlap_fraction"])
                    metrics.update({key: float(value) for key, value in descriptive.items()})
                except ValueError as exc:
                    evaluation_warnings.append(
                        f"automatic_evaluation_unavailable: {type(exc).__name__}: {exc}"
                    )

            diagnostics = dict(run.diagnostics.values)
            diagnostics["ui_service_request_id"] = run.request_id
            diagnostics["ui_service_provenance"] = {
                "method_id": run.provenance.method_id,
                "transform_direction": run.provenance.transform_direction,
                "ground_truth_status": run.provenance.ground_truth_status.value,
            }

            return UnifiedEvaluationRecord(
                pair_id=task.pair.pair_id,
                method_id=task.method.method_id,
                method_family=task.method.method_family,
                transform_model=task.method.transform_model,
                modality_class=task.pair.modality_class,
                dimensions=task.pair.dimensions,
                execution_status=status,
                reference=task.pair.reference,
                valid_overlap_fraction=overlap_fraction,
                estimated_transform=estimated,
                transform_plausible=None if run.transform is None else run.transform.plausible,
                geometric_within_tolerance=None,
                metrics=metrics,
                timings_ms=timings,
                method_diagnostics=diagnostics,
                warnings=evaluation_warnings,
                failure_reason=run.failure_reason,
            )

        return execute

    def _candidate_view(
        self,
        candidate: NormalizedCandidateEvidence,
        *,
        registered_output_available: bool,
    ) -> CandidateComparisonView:
        if candidate.geometric_metrics or candidate.anatomical_metrics:
            raise ValueError(
                "Automatic comparison received ground-truth-dependent common evidence."
            )
        if candidate.geometric_within_tolerance is not None:
            raise ValueError(
                "Automatic comparison must not expose geometric PASS/CHECK without ground truth."
            )
        return CandidateComparisonView(
            candidate_id=candidate.candidate_id,
            method_id=candidate.method_id,
            display_name=candidate.display_name,
            method_family=candidate.method_family,
            transform_model=candidate.transform_model,
            execution_status=candidate.execution_status.value,
            transform_plausible=candidate.transform_plausible,
            estimated_transform=_as_transform_tuple(candidate.estimated_transform),
            geometric_metrics=dict(candidate.geometric_metrics),
            anatomical_metrics=dict(candidate.anatomical_metrics),
            descriptive_metrics=dict(candidate.descriptive_metrics),
            overlap_metrics=dict(candidate.overlap_metrics),
            runtime_metrics=dict(candidate.runtime_metrics),
            timings_ms=dict(candidate.timings_ms),
            method_diagnostics=dict(candidate.method_diagnostics),
            warnings=tuple(candidate.warnings),
            failure_reason=candidate.failure_reason,
            registered_output_available=registered_output_available,
        )

    @staticmethod
    def _agreement_view(
        auto_result: AutomaticRunResult,
        image_shape: tuple[int, int],
        *,
        grid_rows: int,
        grid_cols: int,
        margin_fraction: float,
    ) -> AgreementComparisonView:
        agreement = build_preliminary_consensus(
            auto_result,
            image_shape=image_shape,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            margin_fraction=margin_fraction,
        )
        display_names = {
            candidate.candidate_id: candidate.display_name
            for candidate in auto_result.candidates
        }
        pairwise = tuple(
            PairwiseAgreementView(
                candidate_a=item.candidate_a,
                candidate_b=item.candidate_b,
                method_a=item.method_a,
                method_b=item.method_b,
                display_name_a=display_names[item.candidate_a],
                display_name_b=display_names[item.candidate_b],
                rms_px=float(item.rms_px),
                median_px=float(item.median_px),
                p95_px=float(item.p95_px),
                max_px=float(item.max_px),
                normalized_rms=float(item.normalized_rms),
            )
            for item in agreement.pairwise
        )
        summaries = tuple(
            CandidateAgreementView(
                candidate_id=item.candidate_id,
                method_id=item.method_id,
                display_name=display_names[item.candidate_id],
                comparisons=int(item.comparisons),
                median_pairwise_rms_px=float(item.median_pairwise_rms_px),
                max_pairwise_rms_px=float(item.max_pairwise_rms_px),
                median_normalized_rms=float(item.median_normalized_rms),
            )
            for item in agreement.candidate_summaries
        )
        anchor_name = (
            None
            if agreement.consensus_anchor_candidate_id is None
            else display_names[agreement.consensus_anchor_candidate_id]
        )
        return AgreementComparisonView(
            status=agreement.status,
            eligible_candidate_ids=tuple(agreement.eligible_candidate_ids),
            excluded_candidates={
                key: tuple(value) for key, value in agreement.excluded_candidates.items()
            },
            pairwise=pairwise,
            candidate_summaries=summaries,
            consensus_anchor_candidate_id=agreement.consensus_anchor_candidate_id,
            consensus_anchor_method_id=agreement.consensus_anchor_method_id,
            consensus_anchor_display_name=anchor_name,
            median_pairwise_rms_px=agreement.median_pairwise_rms_px,
            max_pairwise_rms_px=agreement.max_pairwise_rms_px,
            median_pairwise_normalized_rms=agreement.median_pairwise_normalized_rms,
            interpretation=CONSENSUS_INTERPRETATION,
        )

    def run(self, request: AutomaticComparisonRequest) -> AutomaticComparisonView:
        """Execute all compatible candidates and return serializable UI evidence."""
        pair, fixed, moving = self._prepare_pair(request)
        preview = self._compatibility_view(
            pair=pair,
            image_shape=(int(fixed.array.shape[0]), int(fixed.array.shape[1])),
            include_optional=request.include_optional_methods,
        )
        registered_available: dict[str, bool] = {}
        auto_service = AutomaticMultiMethodService(
            self._methods,
            self._candidate_executor(
                request=request,
                fixed=fixed,
                moving=moving,
                registered_available=registered_available,
            ),
            include_optional=request.include_optional_methods,
        )
        auto_result = auto_service.run(pair)
        candidates = tuple(
            self._candidate_view(
                candidate,
                registered_output_available=registered_available.get(
                    candidate.candidate_id, False
                ),
            )
            for candidate in auto_result.candidates
        )
        agreement = self._agreement_view(
            auto_result,
            (int(fixed.array.shape[0]), int(fixed.array.shape[1])),
            grid_rows=self._agreement_grid_rows,
            grid_cols=self._agreement_grid_cols,
            margin_fraction=self._agreement_margin_fraction,
        )
        return AutomaticComparisonView(
            preview=preview,
            candidates=candidates,
            status_counts=dict(auto_result.status_counts),
            agreement=agreement,
            recommendation_status=auto_result.recommendation_status,
            ground_truth_status="unavailable",
        )
