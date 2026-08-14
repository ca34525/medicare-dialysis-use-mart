# Kidney Care Analytics Mart

This repository is being bootstrapped for a reproducible, test-driven county screening mart. The intended product combines observed outpatient dialysis use among Original Medicare beneficiaries, CDC/ATSDR social vulnerability context, and current dialysis-facility context for analyst investigation.

It is not a clinical tool, prevalence estimate, opaque opportunity score, or final site-selection recommendation. The complete product and engineering contract is in [`specs.md`](specs.md); repository working rules are in [`AGENTS.md`](AGENTS.md).

## Current status

Bootstrap only. The locked Python 3.12 development environment and offline quality checks are verified on the initial implementation machine. A working ingestion pipeline, dbt mart, Airflow DAG, and Power BI report have not yet been established, and external-source access remains pending as recorded in [`docs/preflight.md`](docs/preflight.md).

## Bootstrap quick start

The specified local baseline is Python 3.12 with `uv`. Run from the repository root:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

`uv sync --locked` may download missing locked packages or the configured Python version on a newly provisioned machine. After synchronization, the Ruff and pytest checks are deterministic and network-free. None of these commands fetch live CMS, CDC, or Census data. A successful local run should be recorded in `docs/preflight.md` rather than assumed from the presence of configuration files.

## Implementation order

Complete and record Gate 0 preflight before domain coding. Then proceed in the specification's order: ingestion and source contracts, dimensional mart, decision-facing BI, orchestration and CI, and portfolio packaging. Optional AWS work is outside core acceptance and requires separate approval.
