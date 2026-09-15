# Real Data Manifests and Integrity Checks

## Purpose

Real-data preparation needs explicit metadata and validation so later registration results can be traced back to the exact files used in an experiment.

Week 2 Day 4 introduces two manifest types:

```text
image_sources
rire_volume_pairs
```

## General real-image source records

Each real-image source record stores:

```text
image_id
path
modality
modality_class
source_name
shape
dtype
sha256
ground_truth_status
preprocessing_requirements
```

Integrity validation checks:

```text
unique image IDs
file existence
image decoding
shape agreement with manifest
SHA-256 agreement
```

## RIRE volume-pair records

Each RIRE pair record stores:

```text
pair_id
fixed_header
fixed_image
moving_header
moving_image
fixed_modality
moving_modality
modality_class
ground_truth_status
preprocessing_requirements
```

Integrity validation checks:

```text
unique pair IDs
presence of all four raw files
header parsing
header modality agreement
voxel count against rows x columns x slices
non-empty volumes
```

## Why shape equality is not required for RIRE

CT and MR volumes can have different matrix sizes and physical sampling. The Day 4 integrity checker therefore validates each volume against its own metadata rather than requiring equal NumPy shapes.

Later registration stages will operate using explicit geometry and physical-space conventions.
