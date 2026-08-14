# Environment and source preflight

**Record date:** 2026-08-14
**Status:** Gate 0 in progress; local bootstrap, CMS ingestion/stage, and SVI source-to-fact path verified

This record distinguishes facts observed in the initial workspace from checks that still need to run on the implementation machine. A specification or configuration file is not evidence that its corresponding tool or integration works.

## Observed workspace state

| Check | Status | Evidence / next action |
|---|---|---|
| Product and engineering specification | Verified 2026-08-13 | Root `specs.md` was present and reviewed. |
| Initial repository contents | Verified 2026-08-13 | Before bootstrap changes, `specs.md` was the only workspace file returned by the repository inventory. |
| Local Git repository | Verified 2026-08-13 | Initialized on `main`; `git status` succeeds. No remote was created. |

## Required local checks

| Check | Required stage | Status | Pass evidence to record |
|---|---|---|---|
| Python 3.12 | Gate 0 | Verified 2026-08-13 | `uv run python --version` reported Python 3.12.13. |
| `uv` | Gate 0 | Verified 2026-08-13 | `uv --version` reported 0.11.32; its user installation directory was added to the user `PATH`. |
| Locked dependency environment | Gate 0 | Verified 2026-08-13 | `uv lock` resolved 62 packages and `uv sync --locked` completed; the smoke tests verify DuckDB 1.5.5, dbt Core 1.11.13, dbt DuckDB 1.11.0, and setuptools 84.0.0. |
| Offline bootstrap checks | Gate 0 | Verified 2026-08-13 | `uv run ruff format --check .`, `uv run ruff check .`, and `uv run pytest` passed; pytest collected nine tests covering the package, interpreter, runtime imports, and locked versions. |
| Git executable and local repository | Gate 0 | Verified 2026-08-13 | Git 2.55.0 is available; the repository is on `main`. The exact workspace was added to the user's Git safe-directory list because Codex and the interactive user have different Windows accounts. |
| GitHub access | Gate 0 | Pending | Remote creation, push access, and GitHub Actions access were intentionally outside the bootstrap scope. |
| Docker and Compose 2.14+ | Portfolio final | Pending | Version checks pass. |
| Container memory | Portfolio final | Pending | At least 4 GB is allocated; 8 GB is preferred. |
| Supported 64-bit Windows machine | Power BI final | Verified 2026-08-13 | The implementation machine reports Windows 11 Home on a 64-bit operating system. |
| Power BI Desktop | Power BI final | Pending | Desktop opens and imports a local Parquet file. |

## Required source checks

The specification's research review found these public services feasible, but each still requires an implementation-machine check. Do not mark a source verified here solely from that research result.

| Source | Required? | Status | Pass evidence to record |
|---|---:|---|---|
| CMS Original Medicare Geographic Variation | Yes | Verified 2026-08-13 | A read-only request to `data.cms.gov/data.json` resolved exactly one intended dataset, stable ID `6219697b-8f6c-4164-bed4-cd9317c58ebc`, modified 2026-05-15. The stable data-viewer endpoint with `size=1&offset=0` reported 36,994 rows and 246 columns (242 `NUMERIC`, four `TEXT`) without authentication. Bounded filtered `data` requests returned the 2024 National All row and the 2024 County All row for raw code `01001`, preserving the leading zero; a bounded `UNKNOWN` query confirmed pseudo-county code `01000`. The National code is an empty raw string, with the contract exception documented in the source catalog. The 14-page official 2014-2024 dictionary downloaded successfully as a 563,924-byte PDF and is pinned at SHA-256 `75a8d4bef07d1900a50732c78a2aec688ba3ca132dad1dc6cab1a9243d55109f`. Exact labels, types, definitions, schema provenance, and the bounded-sample limitation are recorded in `docs/source-schemas/cms_om_gv.schema.json`; no full CSV or response dump was retained. |
| CMS Dialysis Facility Listing | Yes | Pending | Official metadata resolves and a paginated sample or full CSV succeeds without an API key; pagination is complete and CCNs reconcile. |
| CDC/ATSDR SVI 2022 U.S. county data | Yes | Verified 2026-08-14 | The public ArcGIS service resolved item `f2af3fd35858443293b75d5f73c7d4d3`, county layer 1 `SVI2022 US county`, and object ID `GRASP_ID` without authentication. The production extractor saved two exact attribute-only pages with 2,000 and 1,144 rows, reconciled 3,144 unique county FIPS and object IDs, preserved DC `11001`, excluded territories, and published immutable page and snapshot hashes. A manifest-driven local load and SVI dbt selection produced 3,144 rows in the raw relation, typed stage, county dimension, and SVI fact with 73 passing model/test results. A second run reused both verified pages and recorded a content no-op. The official documentation remains pinned at 542,647 bytes and SHA-256 `5636ae52e13ec201b90f4a31b55d12959d55784469e8c11662b64c03f09424fc`. Generated pages, manifests, and databases are ignored. |
| Census Geocoder | Conditional | Pending | A sample or batch request succeeds for unresolved public facility business addresses. |

## CDC/ATSDR SVI county source-contract check

On 2026-08-14, a read-only live check resolved the official 2022 U.S. county
ArcGIS layer and compared its complete field metadata with the executable raw
contract. The layer advertised service version 12, maximum record count 2,000,
pagination and ordered-query support, 161 fields, and `GRASP_ID` as its object
ID. The field metadata comprised 77 doubles, 55 integers, 21 small integers,
seven strings, and one object ID. All 17 required fields matched their expected
type families; the other 144 fields were recorded as compatible additions.

The count-only response reported 3,144 county rows. Tiny attribute-only samples
at offsets 0 and 2,000 retained five-character FIPS, including leading-zero
values. A bounded two-page scan requested only `GRASP_ID`, `ST`, and `STCNTY`
with geometry disabled and deterministic object-ID ordering. It reconciled
3,144 records, 3,144 distinct FIPS, and 3,144 distinct object IDs; found
District of Columbia `11001`; and found no state-prefix mismatch or territory
row. This dated result supports the pinned 2022 snapshot expectation but is not
a timeless row-count assertion. The production source-to-fact check below
supersedes the earlier implementation deferral.

The official documentation was retrieved from the CDC/ATSDR documentation
page and visually checked for the five U.S.-based county percentile ranks, the
six selected contextual percentage definitions and their distinct
denominators, the 2018-2022 ACS period, and the `-999` unavailable meaning. The
committed PDF, normalized schema, exact official locators, hashes, retrieval
time, layer edit time, and reduced live evidence are recorded under
`docs/source-dictionaries/` and `docs/source-schemas/`. Default tests remain
network-free.

## CDC/ATSDR SVI source-to-fact live check

On 2026-08-14, after the offline extractor, loader, dbt, and failure-injection
tests passed, the explicit live extractor requested the 17 required attributes
with geometry disabled and `GRASP_ID ASC`. It saved two exact response bodies:
2,000 rows and 635,389 bytes at offset 0, followed by 1,144 rows and 365,449
bytes at offset 2,000. Their SHA-256 values were
`06b724e33bb61b4d3cd5996ce3b12a122e3de38807e84b3c7fe5a58541d377eb`
and
`62376e01a8197cc1772e78f2eda9b47b40ec4ac0f78ccd86b7525d6cd669ccf5`.
The canonical ordered snapshot SHA-256 was
`51c2fbc79ddf9eb5a2f71480bde151f5b4e4e2d0494c2e780baa557e7014a2ee`.

Independent disk reconciliation rehashed and reparsed the manifest and both
pages before a fresh DuckDB load. The result contained 3,144 records, 3,144
distinct county FIPS, 3,144 distinct object IDs, DC `11001`, and no territory
rows. The SVI dbt selection completed 73 model, unit-test, and data-test results
with zero errors and produced 3,144 rows in each of the raw relation,
`stg_cdc_svi_county_2022`, `dim_county`, and `fct_svi_county`. A second live run
under a new run ID produced the same page and snapshot hashes, reused both
verified page blobs, needed no retry, and recorded `content_noop: true`.

These are dated observations about the examined static 2022 snapshot, not
timeless row-count guarantees. The generated responses, manifests, and
database remain under ignored paths. CMS-to-SVI reconciliation T-014 and all
screening thresholds, quadrants, rankings, and recommendations remain
deferred. The final locked offline handoff completed `uv sync --locked`, clean
Ruff format and lint checks, and 252 passing pytest tests.

## CMS Geographic Variation full-file ingestion check

On 2026-08-14, the explicit live extractor resolved the current full CSV from
the official CMS catalog and stable dataset identity without authentication.
The first validation attempt correctly blocked before publication because the
then-declared four-field raw key duplicated the distinct State pseudo-rows
`Territory` and `ZZ`, both of which use a blank code. Bounded one-row API checks
confirmed the source representation. The authoritative specification,
executable contract, normalized schema evidence, and source catalog were
corrected together to include required `BENE_GEO_DESC` in the raw transport
grain; duplicate complete raw grains still block publication.

The corrected live run published one ignored content-addressed blob with
SHA-256 `10c8304012da34da3ecfe4caf4548927095f693383814d0e79ce6711b6806fad`,
57,865,948 bytes, 36,994 logical CSV data rows, 246 ordered columns, and 233
contract-compatible additive columns. The one-response transport recorded
`page_count: 1`. A second run under a new run ID resolved the same bytes, reused
the one verified blob, and recorded `content_noop: true` in a second canonical
manifest.

A separate standard-library reconciliation reread the saved blob and manifest
from disk. Content SHA-256, byte count, logical row count, record count, typed
schema SHA-256 `4b409f690a9bc0a9378559035ba2829b9873490680376fdbf1a0d62639296d50`,
raw-header SHA-256 `2c9d097415be8f240dd0d462f0d8907a2ce9209eb8742c840c771afe6f1465db`,
canonical JSON bytes, and the single-blob/two-manifest layout all reconciled.
The raw CSV, manifests, and temporary paths are ignored and are not committed.
After the raw-grain correction, the exact locked offline handoff commands passed
with 104 tests plus clean Ruff formatting and lint checks.

## Deferred or not required

| Check | Status | Note |
|---|---|---|
| AWS account, billing, and IAM | Not required | Optional phase only; it must not block the local mart and requires separate approval. |
| Power BI Service/public hosting | Not required | The core deliverable is a local `.pbix` plus documented artifacts. |

## Recording rule

When a check is actually performed, add the date, exact command or endpoint category, concise result, and any limitation. Do not record credentials, secrets, transient signed URLs, or full downloaded source data in this file.
