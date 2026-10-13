from __future__ import annotations

import numpy as np

from ui.core import DatasetCatalog, GroundTruthStatus


def test_catalog_lists_public_research_examples_without_week1_fixture() -> None:
    catalog = DatasetCatalog()
    ids = {item.id for item in catalog.list_examples()}
    assert "tracked_week01_pair" not in ids
    assert "synthetic_translation" in ids
    assert "synthetic_affine" in ids
    assert "synthetic_inversion_rigid" in ids


def test_week1_fixture_remains_available_internally() -> None:
    catalog = DatasetCatalog()
    internal_ids = {item.id for item in catalog.list_internal_examples()}
    assert "tracked_week01_pair" in internal_ids
    bundle = catalog.build("tracked_week01_pair")
    assert bundle.descriptor.id == "tracked_week01_pair"


def test_synthetic_preset_is_deterministic_and_has_known_ground_truth() -> None:
    catalog = DatasetCatalog()
    first = catalog.build("synthetic_translation")
    second = catalog.build("synthetic_translation")
    assert first.evaluation.ground_truth_status is GroundTruthStatus.KNOWN
    assert np.array_equal(first.fixed.array, second.fixed.array)
    assert np.array_equal(first.moving.array, second.moving.array)
    assert np.allclose(first.evaluation.ground_truth_transform, second.evaluation.ground_truth_transform)


def test_rire_status_is_read_only_discovery() -> None:
    status = DatasetCatalog().rire_status()
    assert status["pair_id"] == "training001_mr_t1_to_ct"
    assert "available" in status
    assert status["ground_truth_status"] == "reference_landmarks_not_integrated_in_day04"
