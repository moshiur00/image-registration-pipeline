"""Core package for the image registration internship project."""

from .config import build_transform, config_hash, load_config, with_defaults
from .conventions import (
    ANGLE_UNIT,
    COORDINATE_ORDER,
    POSITIVE_ROTATION_DIRECTION,
    STORED_TRANSFORM_DIRECTION,
)
from .evaluation import (
    evaluate_pair,
    mean_absolute_error,
    mean_squared_error,
    normalized_cross_correlation,
    structural_similarity,
)
from .io import LoadedImage, load_image, validate_image_pair
from .pipeline import ExperimentResult, run_experiment
from .preprocessing import (
    clip_percentiles,
    crop_to_mask,
    gaussian_smooth,
    preprocess_image,
    resize_image,
    robust_normalize,
    to_grayscale,
)
from .transforms import (
    affine_matrix,
    apply_transform,
    compose_transforms,
    from_homogeneous,
    identity_matrix,
    invert_transform,
    rigid_matrix,
    rotation_matrix,
    similarity_matrix,
    to_homogeneous,
    translation_matrix,
)
from .registration import RegistrationMethod, RegistrationResult
from .visualization import (
    absolute_difference,
    alpha_overlay,
    checkerboard,
    save_comparison_figure,
    save_grayscale_image,
)
from .warping import warp_image, warp_mask

__all__ = [
    "ANGLE_UNIT",
    "ExperimentResult",
    "RegistrationMethod",
    "RegistrationResult",
    "COORDINATE_ORDER",
    "POSITIVE_ROTATION_DIRECTION",
    "STORED_TRANSFORM_DIRECTION",
    "LoadedImage",
    "absolute_difference",
    "build_transform",
    "config_hash",
    "affine_matrix",
    "alpha_overlay",
    "apply_transform",
    "checkerboard",
    "clip_percentiles",
    "compose_transforms",
    "crop_to_mask",
    "evaluate_pair",
    "from_homogeneous",
    "gaussian_smooth",
    "identity_matrix",
    "invert_transform",
    "load_config",
    "load_image",
    "mean_absolute_error",
    "mean_squared_error",
    "normalized_cross_correlation",
    "preprocess_image",
    "resize_image",
    "rigid_matrix",
    "robust_normalize",
    "run_experiment",
    "rotation_matrix",
    "save_comparison_figure",
    "save_grayscale_image",
    "similarity_matrix",
    "structural_similarity",
    "to_grayscale",
    "to_homogeneous",
    "translation_matrix",
    "validate_image_pair",
    "warp_image",
    "warp_mask",
    "with_defaults",
]
