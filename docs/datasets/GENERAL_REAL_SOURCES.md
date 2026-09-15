# General Real-Image Source Subset

## Purpose

Week 2 uses a very small set of real grayscale images as source content for later controlled registration experiments. The images are distributed with `scikit-image` and are copied into the project sample area by the Day 4 preparation script.

This subset is not treated as a standalone registration benchmark with native geometric ground truth. Instead, it provides real image content that can receive known synthetic transformations during the integrated benchmark in Week 2 Day 5.

## Included source images

The current subset contains:

```text
camera
coins
moon
```

These images provide different structures and texture distributions while keeping the project repository small.

## Manifest

The generated manifest is:

```text
data/manifests/general_real_sources.json
```

Each record stores:

```text
image ID
project-relative path
modality label
source name
shape
data type
SHA-256 digest
ground-truth status
preprocessing requirements
```

## Reproduction

Run:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml
```

The same installed `scikit-image` version and the same configuration reproduce the tracked sample files and manifest.

## Limitation

These images are general real-image sources, not naturally paired registration cases. Known registration ground truth will be introduced later through the controlled synthetic geometry already implemented in Week 2 Day 1.
