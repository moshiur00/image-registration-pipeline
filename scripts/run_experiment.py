"""Run a configuration-driven image-registration experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_registration.pipeline import run_experiment  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/day05_week01_smoke_test.yaml",
        help="Configuration path relative to the project root, or an absolute path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    result = run_experiment(config_path, project_root=PROJECT_ROOT)

    print("Week 1 configuration-driven smoke test")
    print("--------------------------------------")
    print(f"Run ID:             {result.run_id}")
    print(f"Run directory:      {result.run_directory.relative_to(PROJECT_ROOT)}")
    if result.unregistered_metrics and result.registered_metrics:
        print(f"Unregistered MAE:   {result.unregistered_metrics['mae']:.4f}")
        print(f"Registered MAE:     {result.registered_metrics['mae']:.4f}")
        print(f"Unregistered NCC:   {result.unregistered_metrics['ncc']:.4f}")
        print(f"Registered NCC:     {result.registered_metrics['ncc']:.4f}")
        print(f"Unregistered SSIM:  {result.unregistered_metrics['ssim']:.4f}")
        print(f"Registered SSIM:    {result.registered_metrics['ssim']:.4f}")
    print(f"Total runtime:      {result.timing_seconds['total']:.4f} s")


if __name__ == "__main__":
    main()
