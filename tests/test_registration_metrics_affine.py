from __future__ import annotations

import numpy as np
import pytest

from image_registration.registration_metrics import affine_linear_error
from image_registration.transforms import affine_matrix


def test_affine_linear_error_is_zero_for_equal_transforms() -> None:
    transform = affine_matrix([[1.1, 0.1], [0.02, 0.9]], tx=4.0, ty=-3.0)
    assert affine_linear_error(transform, transform) == pytest.approx(0.0)


def test_affine_linear_error_ignores_translation_component() -> None:
    first = affine_matrix([[1.0, 0.1], [0.0, 0.95]], tx=0.0, ty=0.0)
    second = affine_matrix([[1.0, 0.1], [0.0, 0.95]], tx=30.0, ty=-20.0)
    assert affine_linear_error(first, second) == pytest.approx(0.0)


def test_affine_linear_error_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="shape"):
        affine_linear_error(np.eye(2), np.eye(3))
