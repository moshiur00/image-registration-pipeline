"""Prepare and track manual Stage B Streamlit acceptance (not scientific evaluation)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.qa.stage_b_acceptance import RUNTIME, SCENARIOS, prepare_fixtures, readiness, record_manual_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare", help="Generate deterministic, development-only QA PNGs in ui/runtime")
    sub.add_parser("status", help="Show pending/passed/failed operator-reviewed scenarios")
    recorder = sub.add_parser("record", help="Record a manual observation, not an automated test")
    recorder.add_argument("scenario", choices=tuple(SCENARIOS))
    recorder.add_argument("verdict", choices=("pass", "fail", "blocked"))
    recorder.add_argument("--note", required=True, help="Concrete UI behavior observed during the manual walkthrough")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        manifest = prepare_fixtures()
        print(f"Prepared {len(manifest['files'])} QA fixtures in {RUNTIME}")
        print("NOT held-out research data. Does not mark any manual test as passed.")
    elif args.action == "record":
        record_manual_result(scenario=args.scenario, verdict=args.verdict, note=args.note)
        print(f"Recorded operator observation for {args.scenario}: {args.verdict}")
    report = readiness()
    print(json.dumps(report, indent=2))
    return 0 if args.action != "status" or report["status"] == "MANUALLY_ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
