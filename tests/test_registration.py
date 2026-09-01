from __future__ import annotations

import numpy as np

from image_registration.registration import RegistrationResult


def test_registration_result_holds_standard_fields() -> None:
    image = np.zeros((4, 4), dtype=np.float32)
    result = RegistrationResult(
        transform=np.eye(3, dtype=np.float64),
        registered_image=image,
        success=True,
        runtime_seconds=0.01,
        convergence_info={"iterations": 0},
    )
    assert result.success is True
    assert result.failure_reason is None
    assert result.transform.shape == (3, 3)
    assert result.registered_image.shape == (4, 4)
