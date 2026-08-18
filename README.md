# Kidney Care Analytics Mart

This repository is being bootstrapped for a reproducible, test-driven county screening mart. The intended product combines observed outpatient dialysis use among Original Medicare beneficiaries, CDC/ATSDR social vulnerability context, and current dialysis-facility context for analyst investigation.

It is not a clinical tool, prevalence estimate, opaque opportunity score, or final site-selection recommendation. The complete product and engineering contract is in [`specs.md`](specs.md); repository working rules are in [`AGENTS.md`](AGENTS.md).

## Current status

The locked Python 3.12 environment and offline quality checks are verified. CMS contract v2, CDC/ATSDR SVI 2022, and the CMS Dialysis Facility Listing now assemble atomically into one run-scoped DuckDB input. dbt produces governed county facts, a fixed national continuous P75 threshold, a transparent screening mart, and typed facility dimensions and quality snapshots. In the pinned 2026-08-15 sources, all 7,490 facility rows reconcile through stage, dimension, and fact while county assignment remains visibly `not_attempted`. Facility-to-county mapping, county facility aggregates, screening context, publication, Airflow, and Power BI remain deferred; dated evidence is in [`docs/preflight.md`](docs/preflight.md).

## Human guides

- [Plan 001 — What is the CMS source contract?](docs/guides/001-cms-source-contract-explained.html) explains the first contract visually for readers who are new to data engineering.
- [Plan 002 — What is an ingestion manifest?](docs/guides/002-cms-ingestion-manifest-explained.html) explains raw downloads, bytes, blobs, hashes, manifests, atomic publication, and safe reruns at the same introductory level.
- [Plan 003 — How does raw CMS data become a typed county stage?](docs/guides/003-cms-staging-explained.html) explains manifest verification, raw-string loading, suppression and unavailability, county filtering, dbt tests, and deterministic reruns.
- [Plan 004 — How does the SVI county source contract protect the mart?](docs/guides/004-svi-source-contract-explained.html) explains the official layer identity, required fields, county grain, source-defined denominators, unavailable sentinel, dated live evidence, and safety boundaries.
- [Plan 005 — How do paginated SVI responses become trusted county facts?](docs/guides/005-svi-source-to-fact-explained.html) explains exact API pages, immutable hashes and manifests, raw-token typing, the county dimension, the SVI fact, and the boundary between source preparation and downstream classification.
- [Plan 006 — How do verified CMS and SVI inputs become governed facts?](docs/guides/006-cms-facts-and-geography-explained.html) explains atomic two-source assembly, CMS facts and benchmarks, the DC county-equivalent rule, historical identities, and full-outer current-county reconciliation.
- [Plan 007 — How does the transparent county screen work?](docs/guides/007-county-screening-explained.html) explains the fixed national percentile, inclusive boundaries, missing-data behavior, four quadrants, audit totals, and the decisions this screen does not make.
- [Plan 008 — How does a facility CSV become trusted raw evidence?](docs/guides/008-facility-source-and-ingestion-explained.html) explains textual CCN grain, dictionary and schema mapping, complete full-file checks, immutable blobs and manifests, measure companions, dated live evidence, and the work intentionally deferred.
- [Plan 009 — How do trusted facility rows become typed models?](docs/guides/009-facility-models-explained.html) explains manifest re-verification, raw-string preservation, availability codes, typed characteristics, model grains, quality companions, blocking tests, and the geography work intentionally deferred.

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
  --select stg_cdc_svi_county_2022 fct_svi_county `
  --indirect-selection cautious
```

Generated pages, manifests, DuckDB files, profiles, dbt logs, and dbt targets
are ignored. These models provide static 2022 social vulnerability context;
they do not calculate a screening quadrant or recommendation.

## CMS Dialysis Facility source and model quick start

The committed synthetic fixtures verify the 41-field raw contract, textual
CCN grain, complete CSV reconciliation, immutable publication, safe reruns,
and failure injection without network access:

```powershell
uv run pytest `
  tests/unit/contracts/test_cms_dialysis_facility_contract.py `
  tests/unit/extract/test_cms_dialysis_facility.py `
  tests/unit/stage/test_cms_dialysis_facility_stage.py `
  tests/integration/test_cms_dialysis_facility_dbt.py
```

Run the separate live extractor only when current-source validation is
intended. It begins with official CMS metadata and does not accept an arbitrary
download URL:

```powershell
uv run python -m kidney_care_mart.extract.cms_dialysis_facility `
  --run-id cms-dialysis-facility-live-<UTC timestamp> `
  --output-root data/raw
```

The live extractor publishes the unchanged CSV beneath a content SHA-256 and
its run manifest under `data/raw/manifests/cms_dialysis_facility/`; both are
ignored. The network-free Plan 009 loader then re-verifies those exact bytes,
preserves all 41 governed fields as raw strings, and dbt builds the facility
stage, dimension, and quality snapshot fact. It does not assign a county,
aggregate facilities, change the screen, or update a latest-mart pointer.

## Combined dimensional build quick start

The fixtures cover atomic three-source input, governed county and facility
facts, failure injection, reconciliation, and deterministic fresh-path
checksums without network access:

```powershell
uv run pytest tests/unit/stage/test_build_inputs.py
uv run pytest tests/integration/test_cms_dimensional_dbt.py
uv run pytest tests/integration/test_cms_dialysis_facility_dbt.py
```

To build from three already downloaded, verified manifests:

```powershell
uv run python -m kidney_care_mart.stage.build_inputs `
  --build-id <build-id> `
  --cms-manifest data/raw/manifests/cms_om_gv/<v2-run-id>.json `
  --svi-manifest data/raw/manifests/cdc_svi_county_2022/<run-id>.json `
  --facility-manifest `
    data/raw/manifests/cms_dialysis_facility/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<build-id>.duckdb
Copy-Item analytics/profiles.example.yml analytics/profiles.yml
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<build-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics
uv run dbt docs generate --project-dir analytics --profiles-dir analytics
```

The builder re-verifies all three manifests and every referenced byte, records
a deterministic input-set hash, and publishes only after all raw relations and
their audits reconcile. Build-input format v2 requires the facility manifest
at the CLI. A CMS v1 manifest is intentionally rejected. Generated databases,
manifests, profiles, and dbt artifacts stay ignored.

## Transparent county screening quick start

The Plan 007 fixture exercises percentile interpolation, both inclusive
boundaries, all four complete-data quadrants, explicit insufficient-data
reasons, failure injection, and independent fresh-path reproducibility:

```powershell
uv run pytest tests/integration/test_county_screening_dbt.py
```

To build the screen from an already assembled Plan 006 database, run the full
dbt project. The screening threshold is calculated once from the current
national county population and then copied unchanged to every candidate row:

```powershell
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<build-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics
uv run dbt docs generate --project-dir analytics --profiles-dir analytics
```

The output is a reproducible screening aid, not a prevalence estimate, opaque
score, ranking, recommendation, or automated decision. Facility context will
be added later for due diligence and cannot alter a screening quadrant.

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
