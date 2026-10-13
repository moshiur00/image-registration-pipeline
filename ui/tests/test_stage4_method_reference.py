"""Regression checks for the research-facing Method Reference page."""

from __future__ import annotations

from ui.adapters import build_default_registration_service
from ui.streamlit.pages.method_reference import (
    _compatibility_rows,
    _diagnostics,
    _family_descriptors,
    _METHOD_FAMILIES,
)


def test_method_reference_groups_registry_variants_into_research_families() -> None:
    service = build_default_registration_service()
    ecc = next(family for family in _METHOD_FAMILIES if family.title == "ECC")
    descriptors = _family_descriptors(service, ecc)
    assert {descriptor.id for descriptor in descriptors} == {
        "ecc_translation",
        "ecc_rigid",
        "ecc_affine",
    }


def test_method_reference_humanizes_diagnostic_names() -> None:
    service = build_default_registration_service()
    mi = next(family for family in _METHOD_FAMILIES if family.title == "Mattes Mutual Information")
    labels = _diagnostics(_family_descriptors(service, mi))
    assert "MI value" in labels
    assert "Convergence trace" in labels
    assert "Valid metric points" in labels
    assert all("_" not in label for label in labels)


def test_compatibility_matrix_has_one_row_per_public_method_family_plus_rire() -> None:
    service = build_default_registration_service()
    rows = _compatibility_rows(service)
    names = [row["Method"] for row in rows]
    assert names == [
        "Phase Correlation",
        "ECC",
        "ORB + RANSAC",
        "SIFT + RANSAC",
        "Mattes Mutual Information",
        "RIRE CT / MR-T1",
    ]
    ecc = next(row for row in rows if row["Method"] == "ECC")
    assert ecc["Translation"] == "✓"
    assert ecc["Rigid"] == "✓"
    assert ecc["Affine"] == "✓"
    assert ecc["Similarity"] == ""
