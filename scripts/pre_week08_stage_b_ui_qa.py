"""Prepare and track manual Stage B Streamlit acceptance (not scientific evaluation)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.qa.stage_b_acceptance import (
    RUNTIME,
    SCENARIOS,
    SUPPLEMENTAL_CHECKS,
    prepare_fixtures,
    readiness,
    record_manual_result,
    record_supplemental_result,
    write_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare", help="Generate deterministic, development-only QA PNGs in ui/runtime")
    sub.add_parser("status", help="Show pending/passed/failed operator-reviewed scenarios")
    recorder = sub.add_parser("record", help="Record a manual observation, not an automated test")
    recorder.add_argument("scenario", choices=tuple(SCENARIOS))
    recorder.add_argument("verdict", choices=("pass", "fail", "blocked"))
    recorder.add_argument("--reviewer", required=True, help="Human Windows operator/reviewer identity")
    recorder.add_argument("--platform", required=True, help="Target Windows edition, version and architecture")
    recorder.add_argument("--environment", required=True, help="Python and dependency environment under review")
    recorder.add_argument(
        "--release-commit", required=True,
        help="Exact 40-character checked-out tested Git HEAD in a clean worktree",
    )
    recorder.add_argument("--note", required=True, help="Concrete UI behavior observed during the manual walkthrough")
    recorder.add_argument(
        "--screenshot", action="append", required=True,
        help="Screenshot path under ui/runtime/pre_week08_stage_b; repeat for multiple files",
    )
    recorder.add_argument(
        "--zip-evidence", action="append", default=[],
        help="Analysis ZIP path under ui/runtime/pre_week08_stage_b; repeat for multiple files",
    )
    supplemental_recorder = sub.add_parser(
        "record-supplemental",
        help="Record one required supplemental human Windows observation",
    )
    supplemental_recorder.add_argument("check", choices=tuple(SUPPLEMENTAL_CHECKS))
    supplemental_recorder.add_argument("verdict", choices=("pass", "fail", "blocked"))
    supplemental_recorder.add_argument(
        "--reviewer", required=True, help="Human Windows operator/reviewer identity"
    )
    supplemental_recorder.add_argument(
        "--platform", required=True, help="Target Windows edition, version and architecture"
    )
    supplemental_recorder.add_argument(
        "--environment", required=True, help="Python and dependency environment under review"
    )
    supplemental_recorder.add_argument(
        "--release-commit", required=True,
        help="Exact 40-character checked-out tested Git HEAD in a clean worktree",
    )
    supplemental_recorder.add_argument(
        "--note", required=True, help="Concrete supplemental behavior observed"
    )
    supplemental_recorder.add_argument(
        "--screenshot", action="append", required=True,
        help="Screenshot path under ui/runtime/pre_week08_stage_b; repeat for multiple files",
    )
    report_parser = sub.add_parser(
        "report", help="Write the sanitized tracked validation report from human attestations"
    )
    for suite in ("backend", "ui"):
        for outcome in ("passed", "skipped", "failed"):
            report_parser.add_argument(
                f"--{suite}-{outcome}", type=int, required=True,
                help=f"Exact full {suite} suite {outcome} count",
            )
    report_parser.add_argument(
        "--stage-c", choices=("INCLUDED", "DEFERRED"), required=True,
        help="Final scope decision for the Stage C Research Evidence page",
    )
    report_parser.add_argument(
        "--rire-expansion", choices=("INCLUDED", "DEFERRED"), required=True,
        help="Final scope decision for interactive RIRE expansion",
    )
    report_parser.add_argument(
        "--recommendation-path", choices=("INCLUDED", "DEFERRED"), required=True,
        help="Final scope decision for the dormant/narrow recommendation display path",
    )
    report_parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "reports/pre_week08_stage_b_validation.json",
        help="Sanitized tracked report path",
    )
    args = parser.parse_args(argv)
    if args.action == "prepare":
        manifest = prepare_fixtures()
        print(f"Prepared {len(manifest['files'])} QA fixtures in {RUNTIME}")
        print("NOT held-out research data. Does not mark any manual test as passed.")
    elif args.action == "record":
        record_manual_result(
            scenario=args.scenario,
            verdict=args.verdict,
            reviewer=args.reviewer,
            platform=args.platform,
            environment=args.environment,
            release_commit=args.release_commit,
            note=args.note,
            screenshots=args.screenshot,
            zips=args.zip_evidence,
        )
        print(f"Recorded operator observation for {args.scenario}: {args.verdict}")
    elif args.action == "record-supplemental":
        record_supplemental_result(
            check=args.check,
            verdict=args.verdict,
            reviewer=args.reviewer,
            platform=args.platform,
            environment=args.environment,
            release_commit=args.release_commit,
            note=args.note,
            screenshots=args.screenshot,
        )
        print(f"Recorded supplemental operator observation for {args.check}: {args.verdict}")
    elif args.action == "report":
        output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        validation = write_validation_report(
            output=output,
            backend_passed=args.backend_passed,
            backend_skipped=args.backend_skipped,
            backend_failed=args.backend_failed,
            ui_passed=args.ui_passed,
            ui_skipped=args.ui_skipped,
            ui_failed=args.ui_failed,
            scope_decisions={
                "stage_c_research_evidence": args.stage_c,
                "interactive_rire_expansion": args.rire_expansion,
                "recommendation_display_path": args.recommendation_path,
            },
        )
        print(f"Wrote sanitized Stage B validation report to {output}")
        print(json.dumps(validation, indent=2))
        return 0 if validation["formal_ui_v02_frozen"] else 2
    report = readiness()
    print(json.dumps(report, indent=2))
    return 0 if args.action != "status" or report["status"] == "MANUALLY_ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
