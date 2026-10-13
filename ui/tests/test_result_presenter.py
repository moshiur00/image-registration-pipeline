from __future__ import annotations

from pathlib import Path, PureWindowsPath

import numpy as np

from ui.core.result_presenter import to_json_safe


def test_to_json_safe_handles_numpy_path_and_collections() -> None:
    payload = to_json_safe(
        {
            "matrix": np.eye(2),
            "count": np.int64(3),
            "path": Path("example/file.png"),
            "windows_path": PureWindowsPath(r"example\file.png"),
            "values": (1, 2),
        }
    )
    assert payload["matrix"] == [[1.0, 0.0], [0.0, 1.0]]
    assert payload["count"] == 3
    assert payload["path"] == "example/file.png"
    assert payload["windows_path"] == "example/file.png"
    assert payload["values"] == [1, 2]
