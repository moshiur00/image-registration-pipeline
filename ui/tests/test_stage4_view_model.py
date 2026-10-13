from __future__ import annotations

import numpy as np

from ui.adapters import build_default_registration_service
from ui.core import DatasetCatalog, PreprocessingSpec
from ui.streamlit.view_model import (
    build_example_request,
    default_method_configuration,
    evidence_status_label,
    method_descriptors_for_example,
    tre_threshold_for_method,
)


def test_example_method_filter_matches_motion_model() -> None:
    catalog = DatasetCatalog()
    service = build_default_registration_service(example_provider=catalog)
    bundle = catalog.build("synthetic_affine")
    methods = method_descriptors_for_example(service.list_methods(), bundle)
    ids = {method.id for method in methods}
    assert ids == {"ecc_affine", "orb_affine", "sift_affine", "mi_affine_2d"}


def test_example_request_carries_existing_method_threshold() -> None:
    catalog = DatasetCatalog()
    service = build_default_registration_service(example_provider=catalog)
    bundle = catalog.build("synthetic_similarity")
    method = next(item for item in service.list_methods() if item.id == "orb_similarity")
    initialization, parameters = default_method_configuration(method.id)
    request = build_example_request(
        bundle=bundle,
        method=method,
        preprocessing=PreprocessingSpec(),
        initialization=initialization,
        parameters=parameters,
    )
    assert request.evaluation.thresholds["mean_tre_pixels"] == tre_threshold_for_method("orb_similarity")
    assert request.request_id.startswith("ui-")


def test_request_id_is_deterministic_for_same_configuration() -> None:
    catalog = DatasetCatalog()
    service = build_default_registration_service(example_provider=catalog)
    bundle = catalog.build("synthetic_translation")
    method = next(item for item in service.list_methods() if item.id == "phase_translation")
    initialization, parameters = default_method_configuration(method.id)
    first = build_example_request(
        bundle=bundle,
        method=method,
        preprocessing=PreprocessingSpec(),
        initialization=initialization,
        parameters=parameters,
    )
    second = build_example_request(
        bundle=bundle,
        method=method,
        preprocessing=PreprocessingSpec(),
        initialization=initialization,
        parameters=parameters,
    )
    assert first.request_id == second.request_id


def test_evidence_status_language_separates_unknown_from_pass() -> None:
    assert evidence_status_label(
        ground_truth_known=True, run_status="completed", within_tolerance=True
    ) == "PASS"
    assert evidence_status_label(
        ground_truth_known=False, run_status="completed", within_tolerance=None
    ) == "Completed"
    assert evidence_status_label(
        ground_truth_known=False, run_status="check", within_tolerance=None
    ) == "Warning"
