"""Week 8 preflight: metadata and frozen-evidence checks ONLY.

This command never invokes registration, opens image pixels, reads ground-truth
files, or evaluates held-out results. BLOCK means the final run must not start.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
from typing import Any

VERSION = "pre_week08_stage_a_v1"
REPORT_REL = Path("outputs/week08_preflight/preflight_report.json")
FROZEN_REL = Path("configs/week08_frozen_baseline.json")
LEDGER_REL = Path("configs/week08_source_use_ledger.json")
HANDOFF_REL = Path("reports/week07_day05_week08_handoff.json")
CLOSURE_REL = Path("reports/week07_week_closure.json")
PROTECTED = [Path("outputs/week07_day02_full"), Path("outputs/week07_day03_analysis"),
             Path("outputs/week07_day04_calibration"), Path("outputs/week07_day05_integration")]
REQUIRED_EVIDENCE = {
    "day32_journal": "outputs/week07_day02_full/benchmark_records.jsonl",
    "day32_plan": "outputs/week07_day02_full/benchmark_plan.json",
    "day34_policy": "outputs/week07_day04_calibration/tentative_policy_not_for_ui.json",
    "day35_journal": "outputs/week07_day05_integration/benchmark_records.jsonl",
    "day35_plan": "outputs/week07_day05_integration/benchmark_plan.json",
    "day35_manifest": "outputs/week07_day05_integration/day35_manifest.json",
    "day35_report": "outputs/week07_day05_integration/day35_report.json",
    "day35_results": "outputs/week07_day05_integration/benchmark_results.csv",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_file(root: Path, rel: str | None) -> Path | None:
    """Validate a project-relative path, blocking internal symlinks/junctions.

    The trust boundary begins at ``root``. Avoid resolving every child path:
    Windows filesystem junctions above root, and differences between Windows
    canonical/lexical paths, should never invalidate an ordinary staged file.
    Reject link/reparse components *inside* the repository with lstat instead.
    This does not open files or follow internal redirects.
    """
    # Manifest and ledger paths use the POSIX project-relative wire format on
    # every OS. Never interpret untrusted metadata via the host OS parser first:
    # on Windows '/etc/passwd' is rooted but Path.is_absolute() is False, and
    # joining it to a project root can escape to the drive root.
    if not isinstance(rel, str) or not rel or "\\" in rel or "\0" in rel or ":" in rel:
        return None
    win = PureWindowsPath(rel)
    if win.drive or win.root or rel.startswith("/"):
        return None
    pieces = rel.split("/")
    if any(part in ("", ".", "..") for part in pieces):
        return None
    relative = PurePosixPath(rel)
    try:
        base = root.absolute()
        current = base
        for part in relative.parts:
            current = current / part
            try:
                info = current.lstat()  # Does not follow symlinks or junctions.
            except FileNotFoundError:
                # Missing paths are separately rejected by checked_file();
                # no untrusted link can be traversed via a missing component.
                continue
            if stat.S_ISLNK(info.st_mode) or bool(
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                return None
        return current
    except (OSError, RuntimeError, ValueError):
        return None


class Audit:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.checks: list[dict[str, Any]] = []
        self.development_metadata: dict[str, dict[str, Any]] = {}

    def add(self, code: str, status: str, details: str, **fields: Any) -> None:
        assert status in {"PASS", "WARN", "BLOCK"}
        self.checks.append({"check": code, "status": status, "details": details, **fields})

    def checked_file(self, rel: str | None, kind: str) -> Path | None:
        path = safe_file(self.root, rel)
        if path is None or not path.is_file():
            self.add(kind, "BLOCK", f"Missing or unsafe required file: {rel}")
            return None
        return path

    def frozen(self) -> tuple[dict, dict]:
        manifest_path = self.checked_file(FROZEN_REL.as_posix(), "frozen_baseline")
        handoff_path = self.checked_file(HANDOFF_REL.as_posix(), "week07_handoff")
        closure_path = self.checked_file(CLOSURE_REL.as_posix(), "week07_closure")
        if not all((manifest_path, handoff_path, closure_path)):
            return {}, {}
        try:
            manifest, handoff, closure = map(read_json, (manifest_path, handoff_path, closure_path))
            assert manifest["version"] == VERSION
            assert closure["status"] == "complete_development_stage"
            assert handoff["independent_validation_completed"] is False
            assert handoff["policy_deployed_to_ui"] is False
            self.add("week07_closure_state", "PASS", "Week 7 closed, policy not independently validated or deployed")
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            self.add("week07_closure_state", "BLOCK", f"Invalid closure/handoff contract: {exc}")
            return {}, {}
        file_hashes = manifest.get("frozen_files", {})
        if not isinstance(file_hashes, dict) or len(file_hashes) < 20:
            self.add("frozen_sources", "BLOCK", "Missing or incomplete immutable source manifest")
            return manifest, handoff
        changed = []
        for rel, expected in sorted(file_hashes.items()):
            path = safe_file(self.root, rel)
            if path is None or not path.is_file() or digest(path) != expected:
                changed.append(rel)
        self.add("frozen_sources", "BLOCK" if changed else "PASS",
                 f"Validated {len(file_hashes) - len(changed)}/{len(file_hashes)} immutable files", mismatches=changed[:30])
        evidence_map = manifest.get("week7_evidence_files", {})
        if not isinstance(evidence_map, dict) or len(evidence_map) < 70:
            self.add("week7_complete_evidence", "BLOCK", "Incomplete Week 7 evidence-file checksum manifest")
        else:
            bad_evidence = []
            for rel, expected in sorted(evidence_map.items()):
                path = safe_file(self.root, rel)
                if path is None or not path.is_file() or digest(path) != expected:
                    bad_evidence.append(rel)
            self.add("week7_complete_evidence", "BLOCK" if bad_evidence else "PASS",
                     f"{len(evidence_map) - len(bad_evidence)}/{len(evidence_map)} Week 7 evidence files match the closure snapshot",
                     invalid=bad_evidence[:35])
        return manifest, handoff

    def evidence(self, handoff: dict) -> None:
        if not handoff:
            self.add("evidence_hashes", "BLOCK", "Week 7 handoff missing")
            return
        closure_path = self.root / CLOSURE_REL
        try:
            closure = read_json(closure_path)
            hashes = closure["provenance"]
            expected = {
                "day32_journal": hashes["day32_journal_sha256"],
                "day32_plan": hashes["day32_plan_sha256"],
                "day34_policy": handoff["policy_sha256"],
                "day35_journal": hashes["day35_journal_sha256"],
                "day35_plan": hashes["day35_plan_sha256"],
                "day35_manifest": hashes["day35_manifest_sha256"],
                "day35_report": hashes["day35_report_sha256"],
                "day35_results": hashes["day35_results_sha256"],
            }
            if expected["day32_journal"] != handoff["reference_day32_journal_sha256"]:
                raise ValueError("Day 32 journal contradicts handoff")
        except (ValueError, KeyError, TypeError) as exc:
            self.add("evidence_hashes", "BLOCK", f"Missing authoritative checksums: {exc}")
            return
        bad = []
        for key, rel in REQUIRED_EVIDENCE.items():
            p = safe_file(self.root, rel)
            if p is None or not p.is_file() or digest(p) != expected[key]:
                bad.append(rel)
        self.add("evidence_hashes", "BLOCK" if bad else "PASS",
                 "Frozen evidence checked against Week 7 closure and handoff",
                 verified=len(REQUIRED_EVIDENCE)-len(bad), total=len(REQUIRED_EVIDENCE), invalid=bad)
        if bad:
            self.add("evidence_restoration", "BLOCK",
                     "Restore original outputs/ from the complete Week 7 closure ZIP. Do not regenerate evidence")
            return
        try:
            policy = read_json(self.root / REQUIRED_EVIDENCE["day34_policy"])
            assert policy["gate"] == handoff["gate"]
            assert policy["status"] == "exploratory_not_deployed"
            assert policy["independent_validation"] is False
            self.add("policy_gate", "PASS", "Frozen Day 34 thresholds and non-deployment status verified")
        except (ValueError, KeyError, AssertionError, TypeError) as exc:
            self.add("policy_gate", "BLOCK", f"Policy/handoff mismatch: {exc}")
        try:
            self.verify_journals()
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            self.add("development_journal_schema", "BLOCK", f"Invalid or duplicate benchmark journal records: {exc}")

    def verify_journals(self) -> None:
        pair_sets = []
        for day, count, pairs in ((32, 963, 486), (35, 88, 40)):
            folder = f"outputs/week07_day0{2 if day == 32 else 5}_{'full' if day == 32 else 'integration'}"
            # Day 32 directory is day02_full; Day 35 is day05_integration.
            plan = read_json(self.root / folder / "benchmark_plan.json")
            expected = [t["experiment_id"] for t in plan["tasks"]]
            seen, pair_ids, statuses, successes = [], set(), {}, 0
            with (self.root / folder / "benchmark_records.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    seen.append(row["experiment_id"])
                    pair_ids.add(row["record"]["pair_id"])
                    status = row["record"]["execution_status"]
                    statuses[status] = statuses.get(status, 0) + 1
                    successes += row["record"].get("geometric_within_tolerance") is True
                    if row["experiment_id"] != row["task"]["experiment_id"]:
                        raise ValueError(f"Day {day} journal identity mismatch")
            ok = (len(expected) == len(seen) == count and len(set(seen)) == count
                  and set(seen) == set(expected) and len(pair_ids) == pairs
                  and successes == (840 if day == 32 else 61)
                  and sum(statuses.values()) == count
                  and set(statuses).issubset({"completed", "check", "failed", "validation_error"}))
            self.add(f"day{day}_journal_integrity", "PASS" if ok else "BLOCK",
                     f"{len(seen)} records; {len(pair_ids)} pairs; {successes} correct; statuses {statuses}")
            seeds = sorted({t.get("pair_metadata", {}).get("geometry_seed") for t in plan["tasks"]}, key=str)
            source_hashes = sorted({str(t.get("pair_metadata", {}).get("source_sha256", "")) for t in plan["tasks"]})
            directions = sorted({t.get("pair_metadata", {}).get("transform_direction") for t in plan["tasks"]}, key=str)
            metadata_complete = (all(x is not None for x in seeds) and all(len(x) == 64 for x in source_hashes)
                                 and directions == ["moving_to_fixed"] and len(source_hashes) > 0
                                 and all(t.get("config_id") and t.get("method_id") and t.get("method_family")
                                         and t.get("transform_model") for t in plan["tasks"]))
            self.add(f"day{day}_provenance_fields", "PASS" if metadata_complete else "BLOCK",
                     "Frozen task plan records geometry seeds, source hashes, method/config IDs and Moving->Fixed convention")
            self.development_metadata[f"day{day}"] = {
                "plan_fingerprint": plan.get("plan_fingerprint"), "geometry_seeds": seeds,
                "source_sha256": source_hashes, "transform_directions": directions,
                "method_ids": sorted({t["method_id"] for t in plan["tasks"]}),
                "task_count": len(expected),
            }
            pair_sets.append(set(seen))
        self.add("development_task_id_isolation", "BLOCK" if pair_sets[0] & pair_sets[1] else "PASS",
                 "Day 32 and Day 35 task IDs do not overlap" if not pair_sets[0] & pair_sets[1] else "Duplicate development IDs")

    def ground_truth_firewall(self) -> None:
        """Static, immutable contract check without importing registration or held-out data.

        The existing Day 34 regression tests additionally exercise label-mutation
        invariance. The not-yet-written Week 8 runner needs its own runtime guard.
        """
        import ast
        source = self.root / "src/image_registration/week7_calibration.py"
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            functions = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
            assert {"project_observables", "select_pair"}.issubset(functions)
            project = functions["project_observables"]
            returns = [x.value for x in ast.walk(project) if isinstance(x, ast.Return)]
            assert len(returns) == 1 and isinstance(returns[0], ast.Dict)
            keys = {x.value for x in returns[0].keys if isinstance(x, ast.Constant) and isinstance(x.value, str)}
            expected = {"experiment_id", "pair_id", "method_id", "family", "model", "modality",
                        "execution_status", "plausible", "transform", "shape_hw", "overlap",
                        "inlier_ratio", "match_coverage", "inliers", "ecc_final", "ecc_levels",
                        "mi_stop", "mi_metric", "mi_valid_points", "phase_response"}
            assert keys == expected
            prohibited = {"geometric_within_tolerance", "reference", "metrics", "ground_truth_transform",
                          "tre_mean_px", "geometry_seed", "degradation", "severity"}
            body = project.body[1:] if (project.body and isinstance(project.body[0], ast.Expr)
                                              and isinstance(project.body[0].value, ast.Constant)) else project.body
            observed_constants = {n.value for stmt in body for n in ast.walk(stmt)
                                  if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            assert not prohibited.intersection(observed_constants)
            select = functions["select_pair"]
            identifiers = {x.id for x in ast.walk(select) if isinstance(x, ast.Name)}
            assert not {"offline_evaluate", "labels_by_pair", "ground_truth"}.intersection(identifiers)
            test_file = self.root / "tests/test_week7_day34_offline_calibration.py"
            assert test_file.is_file() and "test_changing_ground_truth_and_synthetic_severity_cannot_change_gate" in test_file.read_text()
            self.add("day34_gt_firewall_contract", "PASS", "Immutable observable-only projection and Day 34 label-invariance regression verified; future Week 8 runner requires separate checks")
        except (SyntaxError, OSError, AssertionError, KeyError, TypeError) as exc:
            self.add("day34_gt_firewall_contract", "BLOCK", f"Ground-truth firewall contract failed: {type(exc).__name__}: {exc}")

    def sources(self) -> None:
        ledger_path = self.checked_file(LEDGER_REL.as_posix(), "source_use_ledger")
        if ledger_path is None:
            return
        try:
            ledger = read_json(ledger_path)
            known = ledger["known_prior_sources"]
            reserved = ledger["week08_sources"]
            src_index = read_json(self.root / "data/manifests/general_real_sources.json")["records"]
            known_sha = {row["sha256"] for row in src_index} | {entry["sha256"] for entry in known if entry.get("sha256")}
            known_paths = {row["path"] for row in src_index} | {entry["path"] for entry in known if entry.get("path")}
            seen_ids, selected, warnings, problems = set(), set(), [], []
            for entry in reserved:
                source_id = entry["source_id"]
                if not source_id or source_id in seen_ids:
                    problems.append("Duplicate or empty source_id")
                seen_ids.add(source_id)
                role = entry.get("role")
                if role not in {"full_project_independent", "policy_transfer_check", "real_technical_only"}:
                    problems.append(f"Unrecognized evaluation role: {source_id}")
                path = safe_file(self.root, entry.get("path"))
                if path is None or not path.is_file():
                    problems.append(f"Undeclared, missing or unsafe image path: {source_id}")
                    continue
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".nrrd", ".nii", ".gz"}:
                    problems.append(f"Unsupported image type: {source_id}")
                actual = digest(path)  # Byte-stream checksum only: no pixel decoding or label access.
                if actual != entry.get("sha256"):
                    problems.append(f"Image checksum mismatch: {source_id}")
                if entry.get("path") in selected or actual in selected:
                    problems.append(f"Duplicate held-out image identity: {source_id}")
                selected.add(entry.get("path"));selected.add(actual)
                previously_used = entry.get("path") in known_paths or actual in known_sha
                if role == "full_project_independent":
                    if previously_used or entry.get("previously_used", False):
                        problems.append(f"Previously used image claimed independent: {source_id}")
                    if not str(entry.get("path", "")).startswith("data/holdout/week08/"):
                        problems.append(f"Independent source must be staged under data/holdout/week08: {source_id}")
                    if entry.get("ground_truth_status") not in {"synthetic_created_after_freeze", "verified_landmarks", "verified_masks"}:
                        problems.append(f"Independent source lacks a valid geometric evaluation strategy: {source_id}")
                if role == "policy_transfer_check" and not previously_used:
                    warnings.append(f"Transfer role is not established as previously used: {source_id}")
                if entry.get("ground_truth_status") not in {"synthetic_created_after_freeze", "verified_landmarks", "verified_masks", "unavailable"}:
                    problems.append(f"Invalid ground truth status: {source_id}")
                if role == "real_technical_only" and entry.get("ground_truth_status") != "unavailable":
                    problems.append(f"Technical-only data ground-truth status inconsistent: {source_id}")
                if entry.get("ground_truth_status") == "unavailable":
                    warnings.append(f"No verified geometric GT for {source_id}: technical/descriptive evaluation only")
                if entry.get("reference_or_license") in (None, ""):
                    problems.append(f"Missing source/license provenance for {source_id}")
            independent = [x for x in reserved if x.get("role") == "full_project_independent"]
            if not independent:
                problems.append("No genuinely new full-project independent source declared. moon is a transfer check only")
            self.add("heldout_source_independence", "BLOCK" if problems else "PASS",
                     "Metadata and byte-level source audit (no image decoding)", errors=problems, warnings=warnings, sources=len(reserved))
            if warnings:
                self.add("ground_truth_availability", "WARN", "; ".join(warnings))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.add("heldout_source_independence", "BLOCK", f"Invalid source-use ledger: {exc}")

    def final_workspace(self) -> None:
        for rel in ("outputs/week08_final", "outputs/week08_holdout"):
            p = safe_file(self.root, rel)
            if p is None or (p.exists() and (not p.is_dir() or any(p.iterdir()))):
                self.add("clean_" + rel.split("/")[-1], "BLOCK", f"Final-test output must be absent or empty: {rel}")
            else:
                self.add("clean_" + rel.split("/")[-1], "PASS", f"Clean final-test output location: {rel}")
        self.add("week08_runner_identity_contract", "WARN",
                 "Stage A reserves a distinct Week 8 namespace; final evaluation runner must enforce unique IDs and label-after-decision ordering when implemented")

    def run(self) -> dict:
        baseline, handoff = self.frozen()
        self.evidence(handoff)
        self.ground_truth_firewall()
        self.sources()
        self.final_workspace()
        status = "BLOCK" if any(x["status"] == "BLOCK" for x in self.checks) else ("WARN" if any(x["status"] == "WARN" for x in self.checks) else "PASS")
        env = {"python": platform.python_version(), "platform": platform.platform(), "architecture": platform.machine(),
               "cpu_model": platform.processor() or "unavailable", "dependencies": {}}
        for pkg in ("numpy", "opencv-python", "SimpleITK", "scikit-image", "matplotlib", "pytest", "streamlit"):
            try:
                env["dependencies"][pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                env["dependencies"][pkg] = "not_installed"
        report = {"version": VERSION, "readiness": status, "checks": self.checks,
                  "environment": env, "development_plan_metadata": self.development_metadata,
                  "mode": "metadata_only_no_registration_or_ground_truth_access",
                  "week08_evaluation_executed": False,
                  "baseline_sha256": digest(self.root / FROZEN_REL) if (self.root / FROZEN_REL).is_file() else None,
                  "development_evidence_immutable": True if any(x["check"] == "evidence_hashes" and x["status"] == "PASS" for x in self.checks) else False,
                  "limitations": ["Stage A cannot validate a Week 8 runner that does not exist yet. Final-run code must enforce decision-before-label access and denominators.",
                                  "An unknown-ground-truth image cannot support numeric geometric correctness claims."]}
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true", help="Print report only, do not write preflight output")
    args = parser.parse_args(argv)
    audit = Audit(args.root)
    report = audit.run()
    for check in report["checks"]:
        print(f"[{check['status']}] {check['check']}: {check['details']}")
    print(f"Week 8 preflight readiness: {report['readiness']}")
    if not args.dry_run:
        outfile = audit.root / REPORT_REL
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Report: {outfile}")
    return 1 if report["readiness"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
