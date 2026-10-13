from __future__ import annotations

from ui.core import DatasetCatalog
from ui.core.method_registry import DEFAULT_METHOD_REGISTRY
from pathlib import Path

from ui.streamlit.pages.benchmark_explorer import (
    _category_label,
    _method_family_label,
    _modality_label,
    _project_relative_path,
)


def test_public_example_titles_are_portfolio_facing() -> None:
    catalog = DatasetCatalog()
    titles = {item.id: item.title for item in catalog.list_examples()}
    assert titles["synthetic_translation"] == "Translation"
    assert titles["synthetic_rigid"] == "Rigid rotation"
    assert titles["synthetic_similarity"] == "Similarity transform"
    assert titles["synthetic_affine"] == "Affine transform"
    assert titles["synthetic_inversion_rigid"] == "Intensity inversion"
    assert titles["synthetic_edge_affine"] == "Edge-emphasized multimodal"
    assert all("Week 1" not in title for title in titles.values())


def test_benchmark_labels_hide_internal_identifiers() -> None:
    assert _category_label("synthetic_multimodal") == "Synthetic"
    assert _modality_label("simulated_multimodal") == "Multimodal"
    assert "_" not in _category_label("synthetic_multimodal")
    assert "_" not in _modality_label("simulated_multimodal")


def test_method_family_labels_are_research_facing() -> None:
    assert _method_family_label(DEFAULT_METHOD_REGISTRY.require("ecc_affine")) == "ECC"
    assert _method_family_label(DEFAULT_METHOD_REGISTRY.require("orb_affine")) == "ORB + RANSAC"
    assert _method_family_label(DEFAULT_METHOD_REGISTRY.require("sift_affine")) == "SIFT + RANSAC"
    assert _method_family_label(DEFAULT_METHOD_REGISTRY.require("mi_affine_2d")) == "Mattes MI"


def test_project_relative_path_hides_local_absolute_prefix(tmp_path: Path) -> None:
    manifest = tmp_path / "data" / "manifests" / "rire_training001.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    assert _project_relative_path(str(manifest), tmp_path) == "data/manifests/rire_training001.json"
