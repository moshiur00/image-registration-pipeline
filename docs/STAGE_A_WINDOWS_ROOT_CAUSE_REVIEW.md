# Stage A Windows root-cause review

> **Superseding status - 13 November 2026:** The current Windows regression is
> green (702 backend passed, 3 expected skips; 179 UI passed), and the path
> compatibility failures described here no longer reproduce. Stage A remains
> **not accepted** because the independent-source gate is BLOCKED. The final
> evaluator/decision-before-label contract is now implemented and verified.
> Stage B attestation v2 exists, but human acceptance is 0/5 plus 0/5
> supplemental checks and UI v0.2 is not frozen.

## Exact error

Previous Stage A builds passed tests on POSIX but the authoritative Windows rerun failed eight Stage A checks. `frozen_baseline` reported existing files as missing or unsafe, so dependent checks did not appear. A separate Windows absolute-path assertion also failed.

## Root causes

1. `str(Path("configs/week08_frozen_baseline.json"))` uses backslashes on Windows, while `safe_file()` intentionally rejects backslashes as untrusted manifest separators. The same bug affected the handoff, closure, and source-use ledger.
2. `Path("/etc/passwd").is_absolute()` is not universally true on Windows, where a slash-rooted path can mean a drive-rooted path. It must be rejected before joining to any project root.
3. Earlier tests were run on Linux without simulating Windows path serialization. Changes to filesystem symlink handling did not address the actual problem.

## Corrective changes

- Call `.as_posix()` when passing trusted project-relative `Path` constants to the manifest-validation boundary.
- Parse untrusted manifest paths as POSIX-style components and reject Windows drive-anchored, root-anchored, drive-relative, traversal, backslash, colon and NUL forms before touching the filesystem.
- Keep symlink and reparse-point rejection inside the project root.
- Add cross-platform fixtures emulating `PureWindowsPath` serialization, `/etc/passwd`, `C:/...`, UNC, ADS, and relative traversal cases.

## Historical verification boundary

- Focused Stage A tests pass locally on Linux, including the added cross-platform cases.
- The preflight verifies 101 frozen source/configuration files and 81 frozen Week 7 evidence files, with intact Day 32 and Day 35 journals.
- Final evaluation remains intentionally BLOCKED because no genuinely independent Week 8 source has been registered.
- This is **not** Windows validation. The user must confirm the focused tests on the actual Windows system before Stage A is accepted.
- An integrity ledger can establish hashes and declared prior-use status, but cannot on its own prove dataset novelty or verified geometric annotations. Week 8 still needs real independent source vetting and runner-level label isolation.

## Historical project-scope recommendation

Stop changing the Week 7 registration algorithms and Day 34 policy. Complete Stage A's Windows compatibility checks, then prioritize a small UI acceptance pass and a frozen Week 8 evaluation protocol. Defer user-facing confidence percentages and automatic cross-model recommendations until independent evaluation supports them.

The compatibility-check action in that dated recommendation is now complete.
The remaining recommendation still applies: preserve the frozen Week 7 work,
finish the Stage B manual gate, and implement/freeze the Week 8 evaluator and
label firewall before any independent-source bytes are made accessible.
