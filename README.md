# Kidney Care Analytics Mart

This repository is being bootstrapped for a reproducible, test-driven county screening mart. The intended product combines observed outpatient dialysis use among Original Medicare beneficiaries, CDC/ATSDR social vulnerability context, and current dialysis-facility context for analyst investigation.

It is not a clinical tool, prevalence estimate, opaque opportunity score, or final site-selection recommendation. The complete product and engineering contract is in [`specs.md`](specs.md); repository working rules are in [`AGENTS.md`](AGENTS.md).

## Current status

The locked Python 3.12 development environment and offline quality checks are verified on the initial implementation machine. The CMS Original Medicare Geographic Variation source contract, full-file extractor, immutable raw snapshot/manifest path, and manifest-driven DuckDB/dbt county-year stage are implemented. The CDC/ATSDR SVI 2022 U.S. county path now runs from exact, immutable ArcGIS pages through a reconciled manifest and raw-string DuckDB load to a typed county stage, `dim_county`, and `fct_svi_county`. Both source paths preserve five-character county FIPS, raw missingness evidence, declared grain, vintage, and lineage with deterministic fixture tests. The facility source, CMS final facts and benchmarks, pinned CMS/SVI reconciliation, screening mart, Airflow DAG, and Power BI report remain deferred; current source and environment evidence is recorded in [`docs/preflight.md`](docs/preflight.md).

## Human guides

- [Plan 001 — What is the CMS source contract?](docs/guides/001-cms-source-contract-explained.html) explains the first contract visually for readers who are new to data engineering.
- [Plan 002 — What is an ingestion manifest?](docs/guides/002-cms-ingestion-manifest-explained.html) explains raw downloads, bytes, blobs, hashes, manifests, atomic publication, and safe reruns at the same introductory level.
- [Plan 003 — How does raw CMS data become a typed county stage?](docs/guides/003-cms-staging-explained.html) explains manifest verification, raw-string loading, suppression and unavailability, county filtering, dbt tests, and deterministic reruns.
- [Plan 004 — How does the SVI county source contract protect the mart?](docs/guides/004-svi-source-contract-explained.html) explains the official layer identity, required fields, county grain, source-defined denominators, unavailable sentinel, dated live evidence, and safety boundaries.
- [Plan 005 — How do paginated SVI responses become trusted county facts?](docs/guides/005-svi-source-to-fact-explained.html) explains exact API pages, immutable hashes and manifests, raw-token typing, the county dimension, the SVI fact, and the boundaries that keep this context out of screening decisions for now.

Open any downloaded HTML file in a web browser. The numbering follows the matching files in [`plans/`](plans/); the authoring and review convention is in [`docs/guides/README.md`](docs/guides/README.md).

## CMS staging quick start

The committed fixture exercises the complete local manifest → DuckDB → dbt
path without network access or generated Git artifacts:

```powershell
uv run pytest tests/integration/test_cms_om_gv_dbt.py
```

To stage an already downloaded local snapshot, first load its verified manifest
and immutable blob:

```powershell
uv run python -m kidney_care_mart.stage.cms_om_gv `
  --manifest data/raw/manifests/cms_om_gv/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<run-id>.duckdb
```

Then use the credential-free local dbt profile:

```powershell
Copy-Item analytics/profiles.example.yml analytics/profiles.yml
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<run-id>.duckdb").Path
uv run dbt parse --project-dir analytics --profiles-dir analytics
uv run dbt build --project-dir analytics --profiles-dir analytics
```

These commands do not contact CMS. The copied profile, DuckDB database, dbt
logs, and dbt targets are ignored. This stage does not update a published-mart
pointer.

## SVI source-to-fact quick start

The committed fixtures exercise pagination, exact-page reconciliation,
manifest-driven loading, SVI typing, `dim_county`, and `fct_svi_county` without
network access:

```powershell
uv run pytest tests/unit/extract/test_cdc_svi_county_2022.py
uv run pytest tests/unit/stage/test_cdc_svi_county_2022_stage.py
uv run pytest tests/integration/test_cdc_svi_county_2022_dbt.py
```

Run the separate live extractor only when current-source validation is
intended:

```powershell
uv run python -m kidney_care_mart.extract.cdc_svi_county_2022 `
  --run-id cdc-svi-2022-live-<UTC timestamp> `
  --output-root data/raw
```

Load a verified local manifest and build only the SVI path:

```powershell
uv run python -m kidney_care_mart.stage.cdc_svi_county_2022 `
  --manifest data/raw/manifests/cdc_svi_county_2022/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<run-id>.duckdb
Copy-Item analytics/profiles.example.yml analytics/profiles.yml
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<run-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics `
  --select stg_cdc_svi_county_2022+
```

Generated pages, manifests, DuckDB files, profiles, dbt logs, and dbt targets
are ignored. These models provide static 2022 social vulnerability context;
they do not calculate a screening quadrant or recommendation.

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
