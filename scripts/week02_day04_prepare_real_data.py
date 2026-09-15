from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import cv2
from skimage import data as skdata

from image_registration.config import load_config
from image_registration.datasets import (
    build_raster_source_record,
    sha256_file,
    validate_dataset_manifest,
    write_dataset_manifest,
)
from image_registration.medical import read_medical_image_metadata
from image_registration.rire import find_rire_volume_files, parse_rire_header


def _safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = (destination / member.name).resolve()
            try:
                member_path.relative_to(destination_resolved)
            except ValueError as exc:
                raise ValueError(f"Unsafe archive member path: {member.name}") from exc
        archive.extractall(destination)


def _stream_download(url: str, destination: Path, *, attempts: int = 3) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "image-registration-pipeline/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            partial.replace(destination)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"Could not download {destination.name}: {last_error}")


def _md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_named_files_from_zip(
    archive_path: Path,
    destination: Path,
    filenames: tuple[str, ...],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    wanted = set(filenames)
    found: dict[str, zipfile.ZipInfo] = {}

    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            basename = Path(info.filename).name
            if basename in wanted:
                if basename in found:
                    raise ValueError(f"Archive contains more than one file named {basename}.")
                found[basename] = info

        missing = sorted(wanted.difference(found))
        if missing:
            raise FileNotFoundError(
                "Zenodo archive does not contain required file(s): " + ", ".join(missing)
            )

        for filename, info in found.items():
            output_path = destination / filename
            with archive.open(info, "r") as source, output_path.open("wb") as target:
                shutil.copyfileobj(source, target)


def _prepare_general_sources(config: dict[str, Any], project_root: Path) -> Path:
    section = config["general_real_sources"]
    output_dir = (project_root / section["output_dir"]).resolve()
    manifest_path = (project_root / section["manifest"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for spec in section["images"]:
        image_id = str(spec["image_id"])
        loader_name = str(spec["loader"])
        loader = getattr(skdata, loader_name, None)
        if loader is None or not callable(loader):
            raise ValueError(f"Unknown scikit-image data loader: {loader_name}")
        image = loader()
        if image.ndim != 2:
            raise ValueError(f"Expected a grayscale sample for {loader_name}; found shape {image.shape}.")

        output_path = output_dir / f"{image_id}.png"
        if not cv2.imwrite(str(output_path), image):
            raise RuntimeError(f"Failed to write sample image: {output_path}")
        records.append(
            build_raster_source_record(
                image_id,
                output_path,
                project_root=project_root,
                modality="visible",
                source_name=f"scikit-image.data.{loader_name}",
            )
        )

    manifest = {
        "schema_version": 1,
        "dataset_id": section["dataset_id"],
        "record_type": "image_sources",
        "description": "Small real grayscale source subset for controlled registration experiments.",
        "records": records,
    }
    write_dataset_manifest(manifest, manifest_path)
    report = validate_dataset_manifest(manifest_path, project_root=project_root)
    if not report.ok:
        raise RuntimeError("General real-source manifest failed validation: " + "; ".join(report.errors))
    return manifest_path


def _relative(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return str(path.resolve())


def _prepare_mha_files(
    section: dict[str, Any],
    raw_root: Path,
    *,
    download_zenodo: bool,
) -> tuple[Path, Path] | None:
    mha_section = section["mha"]
    mha_dir = raw_root / str(mha_section["directory"])
    fixed_path = mha_dir / str(mha_section["fixed_name"])
    moving_path = mha_dir / str(mha_section["moving_name"])

    if fixed_path.exists() and moving_path.exists():
        return fixed_path, moving_path

    zenodo = section["zenodo"]
    archive_dir = raw_root / "archives"
    archive_path = archive_dir / str(zenodo["archive_name"])

    if not archive_path.exists() and download_zenodo:
        print(f"Downloading {archive_path.name} from Zenodo...")
        _stream_download(str(zenodo["archive_url"]), archive_path)

    if archive_path.exists():
        expected_md5 = str(zenodo.get("archive_md5", "")).strip().lower()
        if expected_md5:
            actual_md5 = _md5_file(archive_path)
            if actual_md5 != expected_md5:
                raise RuntimeError(
                    f"Zenodo archive MD5 mismatch: expected {expected_md5}, found {actual_md5}."
                )
        print("Extracting only the required CT and MR-T1 MHA files...")
        _extract_named_files_from_zip(
            archive_path,
            mha_dir,
            (fixed_path.name, moving_path.name),
        )
        return fixed_path, moving_path

    return None


def _prepare_legacy_raw_files(
    section: dict[str, Any],
    raw_root: Path,
) -> tuple[Path, Path, Path, Path] | None:
    legacy = section.get("legacy_raw")
    if not isinstance(legacy, dict):
        return None

    archive_dir = raw_root / "archives"
    fixed_archive = archive_dir / str(legacy["fixed_archive_name"])
    moving_archive = archive_dir / str(legacy["moving_archive_name"])
    if not fixed_archive.exists() or not moving_archive.exists():
        return None

    fixed_root = raw_root / str(legacy["fixed_key"])
    moving_root = raw_root / str(legacy["moving_key"])
    if not fixed_root.exists() or not any(fixed_root.iterdir()):
        print(f"Extracting {fixed_archive.name}...")
        _safe_extract_tar(fixed_archive, fixed_root)
    if not moving_root.exists() or not any(moving_root.iterdir()):
        print(f"Extracting {moving_archive.name}...")
        _safe_extract_tar(moving_archive, moving_root)

    fixed_header, fixed_image = find_rire_volume_files(fixed_root)
    moving_header, moving_image = find_rire_volume_files(moving_root)
    return fixed_header, fixed_image, moving_header, moving_image


def _prepare_mha_manifest(
    section: dict[str, Any],
    project_root: Path,
    fixed_path: Path,
    moving_path: Path,
) -> Path:
    fixed_metadata = read_medical_image_metadata(fixed_path)
    moving_metadata = read_medical_image_metadata(moving_path)

    manifest_path = (project_root / section["manifest"]).resolve()
    manifest = {
        "schema_version": 2,
        "dataset_id": section["dataset_id"],
        "record_type": "medical_volume_pairs",
        "description": "RIRE training_001 CT and MR-T1 real multimodal pair in SimpleITK-compatible MHA format.",
        "source_page": section["source_page"],
        "provenance_record": section["provenance_record"],
        "simpleitk_example": section["simpleitk_example"],
        "license_note": section["license_note"],
        "records": [
            {
                "pair_id": section["pair_id"],
                "fixed_image": _relative(project_root, fixed_path),
                "moving_image": _relative(project_root, moving_path),
                "fixed_modality": str(section["fixed_modality"]),
                "moving_modality": str(section["moving_modality"]),
                "modality_class": "real_multimodal",
                "ground_truth_status": "reference_landmarks_not_integrated_in_day04",
                "fixed_metadata": fixed_metadata.as_dict(),
                "moving_metadata": moving_metadata.as_dict(),
                "fixed_sha256": sha256_file(fixed_path),
                "moving_sha256": sha256_file(moving_path),
                "preprocessing_requirements": [
                    "preserve spacing, origin, and direction",
                    "operate in physical coordinates for 3D registration",
                    "do not force identical intensity histograms",
                ],
            }
        ],
    }
    write_dataset_manifest(manifest, manifest_path)
    report = validate_dataset_manifest(manifest_path, project_root=project_root)
    if not report.ok:
        raise RuntimeError("RIRE MHA manifest failed validation: " + "; ".join(report.errors))
    return manifest_path


def _prepare_legacy_manifest(
    section: dict[str, Any],
    project_root: Path,
    files: tuple[Path, Path, Path, Path],
) -> Path:
    fixed_header, fixed_image, moving_header, moving_image = files
    fixed_metadata = parse_rire_header(fixed_header)
    moving_metadata = parse_rire_header(moving_header)

    manifest_path = (project_root / section["manifest"]).resolve()
    manifest = {
        "schema_version": 1,
        "dataset_id": section["dataset_id"],
        "record_type": "rire_volume_pairs",
        "description": "RIRE training_001 CT and MR-T1 real multimodal pair in original raw format.",
        "source_page": section["source_page"],
        "license_note": section["license_note"],
        "records": [
            {
                "pair_id": section["pair_id"],
                "fixed_header": _relative(project_root, fixed_header),
                "fixed_image": _relative(project_root, fixed_image),
                "moving_header": _relative(project_root, moving_header),
                "moving_image": _relative(project_root, moving_image),
                "fixed_modality": fixed_metadata.modality,
                "moving_modality": moving_metadata.modality,
                "modality_class": "real_multimodal",
                "ground_truth_status": "reference_landmarks_not_integrated_in_day04",
                "fixed_metadata": fixed_metadata.as_dict(),
                "moving_metadata": moving_metadata.as_dict(),
                "preprocessing_requirements": [
                    "preserve voxel spacing",
                    "preserve patient orientation",
                    "do not force identical intensity histograms",
                ],
            }
        ],
    }
    write_dataset_manifest(manifest, manifest_path)
    report = validate_dataset_manifest(manifest_path, project_root=project_root)
    if not report.ok:
        raise RuntimeError("RIRE legacy manifest failed validation: " + "; ".join(report.errors))
    return manifest_path


def _prepare_rire_manifest(
    config: dict[str, Any],
    project_root: Path,
    *,
    download_zenodo: bool,
) -> tuple[Path | None, str]:
    section = config["rire_training_001"]
    raw_root = (project_root / section["raw_root"]).resolve()
    raw_root.mkdir(parents=True, exist_ok=True)

    mha_files = _prepare_mha_files(section, raw_root, download_zenodo=download_zenodo)
    if mha_files is not None:
        manifest_path = _prepare_mha_manifest(section, project_root, *mha_files)
        return manifest_path, "RIRE training_001 CT and MR-T1 MHA files validated successfully."

    legacy_files = _prepare_legacy_raw_files(section, raw_root)
    if legacy_files is not None:
        manifest_path = _prepare_legacy_manifest(section, project_root, legacy_files)
        return manifest_path, "RIRE training_001 original raw files validated successfully."

    mha_dir = raw_root / str(section["mha"]["directory"])
    fixed_name = str(section["mha"]["fixed_name"])
    moving_name = str(section["mha"]["moving_name"])
    archive_name = str(section["zenodo"]["archive_name"])
    message = (
        "RIRE files are not prepared yet. Place "
        f"{fixed_name} and {moving_name} in {_relative(project_root, mha_dir)}, "
        f"or place the downloaded Zenodo data.zip as {_relative(project_root, raw_root / 'archives' / archive_name)}."
    )
    return None, message


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Week 2 Day 4 real-data subsets.")
    parser.add_argument(
        "--config",
        default="configs/week02_day04_real_datasets.yaml",
        help="Path to the Day 4 YAML configuration.",
    )
    parser.add_argument(
        "--download-zenodo",
        action="store_true",
        help="Download the Zenodo data.zip archive before extracting the two RIRE MHA files.",
    )
    parser.add_argument(
        "--download-rire",
        action="store_true",
        help="Compatibility alias for --download-zenodo.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_config(project_root / args.config)

    general_manifest = _prepare_general_sources(config, project_root)
    rire_manifest, rire_status = _prepare_rire_manifest(
        config,
        project_root,
        download_zenodo=args.download_zenodo or args.download_rire,
    )

    report_path = (project_root / config["output"]["report"]).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "general_real_sources": {
            "status": "prepared",
            "manifest": _relative(project_root, general_manifest),
        },
        "rire_training_001": {
            "status": "prepared" if rire_manifest is not None else "external_data_required",
            "manifest": _relative(project_root, rire_manifest) if rire_manifest else None,
            "message": rire_status,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Week 2 Day 4 real-data preparation")
    print("-----------------------------------")
    print(f"General manifest: {_relative(project_root, general_manifest)}")
    print(f"RIRE status:      {rire_status}")
    print(f"Report:           {_relative(project_root, report_path)}")
    if rire_manifest is None:
        print("Preferred input: local training_001_ct.mha and training_001_mr_T1.mha files.")
        print("A locally downloaded Zenodo data.zip is also supported and only the two required MHA files are extracted.")


if __name__ == "__main__":
    main()
