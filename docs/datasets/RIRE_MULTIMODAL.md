# RIRE Multimodal Dataset Preparation

## Dataset

The real multimodal target for Week 2 is the Retrospective Image Registration Evaluation (RIRE) `training_001` case using CT and MR-T1 volumes.

The preferred local files are:

```text
training_001_ct.mha
training_001_mr_T1.mha
```

These filenames are used by the SimpleITK registration examples and are also included in the Netherlands eScience Center medical-imaging dataset published on Zenodo.

References:

```text
RIRE project:
https://rire.insight-journal.org/

SimpleITK registration example:
https://insightsoftwareconsortium.github.io/SimpleITK-Notebooks/Python_html/60_Registration_Introduction.html

Zenodo provenance record:
https://zenodo.org/records/14592145
DOI: 10.5281/zenodo.14592145
```

## Fixed and moving convention

For this project the Day 4 RIRE pair follows the same direction used in the SimpleITK registration introduction:

```text
Fixed image:  CT
Moving image: MR-T1
```

This keeps the later mutual-information registration workflow consistent with the project convention that the estimated transform maps Moving -> Fixed.

## Preferred local layout

Place the two MHA files here:

```text
data/raw/rire/training_001/mha/
├── training_001_ct.mha
└── training_001_mr_T1.mha
```

Then run:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml
```

The script reads both volumes with SimpleITK, validates that they are 3D, records size, spacing, origin, direction, pixel type, and SHA-256 hashes, and writes:

```text
data/manifests/rire_training001.json
```

The CT and MR volumes are not required to have identical matrix dimensions or spacing because they may have different acquisition geometry.

## Using the Zenodo data.zip archive

The Zenodo record provides one `data.zip` archive that contains both required MHA files. If the archive is downloaded manually, save it as:

```text
data/raw/rire/training_001/archives/zenodo_data.zip
```

Then run the normal preparation command. The script verifies the configured archive MD5 and extracts only:

```text
training_001_ct.mha
training_001_mr_T1.mha
```

The rest of the archive is not extracted into the project.

An optional network command is also supported:

```powershell
python scripts/week02_day04_prepare_real_data.py --config configs/week02_day04_real_datasets.yaml --download-zenodo
```

Public repositories can rate-limit large downloads, so manual download is the preferred path when network access is unreliable.

## Legacy raw RIRE fallback

The original RIRE format is still supported as a fallback. If the old `ct.tar.gz` and `mr_T1.tar.gz` archives are already available locally, place them under:

```text
data/raw/rire/training_001/archives/
```

The project can still parse the original:

```text
header.ascii
image.bin
```

format using `src/image_registration/rire.py`.

The current project no longer depends on the unreliable public IPFS links for normal Day 4 preparation.

## Manifest contents

For the preferred MHA path, the manifest records:

```text
pair ID
fixed and moving file paths
fixed modality: CT
moving modality: MR-T1
modality class
size
spacing
origin
direction
pixel type
SHA-256 hashes
source and provenance references
ground-truth status
preprocessing requirements
```

## Important limitation

Week 2 Day 4 prepares and validates the real multimodal data. It does not yet integrate the RIRE reference landmarks or estimate a registration transform. Registration and quantitative method evaluation begin in later work packages.
