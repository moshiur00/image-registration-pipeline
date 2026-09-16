from __future__ import annotations

import json

import numpy as np

from image_registration.reporting import write_report_snapshot


def test_write_report_snapshot_supports_numpy_values(tmp_path) -> None:
    output = tmp_path / "reports" / "summary.json"
    write_report_snapshot(
        output,
        {
            "count": np.int64(3),
            "score": np.float64(0.5),
            "matrix": np.eye(2),
        },
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["count"] == 3
    assert payload["score"] == 0.5
    assert payload["matrix"] == [[1.0, 0.0], [0.0, 1.0]]
