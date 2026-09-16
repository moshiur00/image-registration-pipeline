# Report Snapshots

This directory keeps compact, machine-readable progress summaries with the source repository so later technical-report generation does not depend only on local `outputs/` folders.

The project uses two result layers:

1. `outputs/` contains complete run artifacts such as CSV/JSON tables, resolved configurations, plots, images, logs, and per-case diagnostics. These files can be large and are intentionally excluded from Git and lightweight sharing archives.
2. `reports/` contains compact JSON snapshots of validated milestones and experiment summaries. These files are small and are tracked with the project.

Narrative context is stored separately in `docs/daily/` and `docs/weekly/`.

For future report generation, use all three sources when available:

- `reports/` for compact quantitative summaries;
- `docs/daily/` and `docs/weekly/` for implementation decisions and interpretation;
- the local `outputs/` directory for full tables, figures, and case-level evidence.

Week 3 experiment scripts write or refresh their compact report snapshot automatically after a successful run.

## Week 3 baseline snapshots

Week 3 stores one compact JSON snapshot for each experimental day. Day 5 also writes an integrated baseline snapshot containing method-level, condition-level, and motion-model summaries. The raw CSV/JSON tables and figures remain under `outputs/`, while the compact snapshot stays tracked with the repository.
