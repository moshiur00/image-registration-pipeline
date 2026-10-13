from __future__ import annotations

from ui.core import DEFAULT_METHOD_REGISTRY, TransformModel


def test_method_registry_ids_are_unique() -> None:
    methods = DEFAULT_METHOD_REGISTRY.list()
    ids = [method.id for method in methods]
    assert len(ids) == len(set(ids))


def test_registry_contains_planned_methods() -> None:
    ids = {method.id for method in DEFAULT_METHOD_REGISTRY.list()}
    assert {
        "phase_translation",
        "ecc_translation",
        "ecc_rigid",
        "ecc_affine",
        "orb_similarity",
        "orb_affine",
        "sift_similarity",
        "sift_affine",
        "mi_rigid_2d",
        "mi_affine_2d",
        "mi_rigid_3d_rire",
    } <= ids


def test_phase_correlation_supports_translation_only() -> None:
    descriptor = DEFAULT_METHOD_REGISTRY.require("phase_translation")
    assert descriptor.motion_models == frozenset({TransformModel.TRANSLATION})
    assert descriptor.dimensions == frozenset({2})
