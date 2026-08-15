# Environment and source preflight

**Record date:** 2026-08-15
**Status:** Gate 0 sources in progress; local bootstrap, CMS/SVI dimensional path, and facility raw ingestion verified

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
| CMS Dialysis Facility Listing | Yes | Verified 2026-08-15 | Official Provider Data dataset `23ew-n7w9`, its July 2026 dictionary, 142-field API schema, and one complete current CSV resolved without authentication. The immutable full-file extractor and an independent disk reread reconciled the API count, 7,490 CSV rows, and 7,490 distinct textual CCNs; a second run reused the verified blob. Exact hashes and limits are recorded below and in `docs/source-catalog.md`. |
| CDC/ATSDR SVI 2022 U.S. county data | Yes | Verified 2026-08-14 | The public ArcGIS service resolved item `f2af3fd35858443293b75d5f73c7d4d3`, county layer 1 `SVI2022 US county`, and object ID `GRASP_ID` without authentication. The production extractor saved two exact attribute-only pages with 2,000 and 1,144 rows, reconciled 3,144 unique county FIPS and object IDs, preserved DC `11001`, excluded territories, and published immutable page and snapshot hashes. A manifest-driven local load and SVI dbt selection produced 3,144 rows in the raw relation, typed stage, county dimension, and SVI fact with 73 passing model/test results. A second run reused both verified pages and recorded a content no-op. The official documentation remains pinned at 542,647 bytes and SHA-256 `5636ae52e13ec201b90f4a31b55d12959d55784469e8c11662b64c03f09424fc`. Generated pages, manifests, and databases are ignored. |
| Census Geocoder | Conditional | Pending | A sample or batch request succeeds for unresolved public facility business addresses. |

## CMS Dialysis Facility source-contract and ingestion check

On 2026-08-15 UTC, a read-only live check resolved exactly Provider Data
dataset `23ew-n7w9`, corroborated the expected Dialysis Facility - Listing by
Facility identity and official landing page, and found one current complete
CSV. The catalog described a release date of 2026-07-15, modification date of
2026-06-16, and next update date of 2026-10-28. The public Provider Data API
schema returned 142 raw-text fields and a count of 7,490 before the CSV was
downloaded.

The official 57-page July 2026 dictionary is committed as a 1,199,186-byte PDF
at SHA-256
`64348a21e3c98b9cb5b915a2243fb3a54b452ca61943c8f9f1eadf7429176fa0`.
Its labels, definitions, character/numeric/date declarations, maximum lengths,
units, and companion relationships reconcile to the 41-field executable
contract. The normalized evidence records all 142 ordered API/CSV fields, 101
compatible additions, ordered-header SHA-256
`f3e5a27bf8724f7ac4d20f415eedd399dbb78ccc178fa7f5de29a577d1a292cf`,
API-schema SHA-256
`9740947ff6269ff4e433cd8e0755855efcfd78ed74407965dda947183d69d2fd`,
and canonical schema-evidence SHA-256
`e87cf25487005a81c8af015b4256da6a0da4205a369c2406cb3ff9b399ceec0f`.

After the focused and then-current full offline suites passed, the explicit
extractor streamed the complete CSV unchanged into ignored storage. The file
was 7,263,788 bytes at SHA-256
`02a7155f9797fe3194f220e765eb8ac511cbc1402e286c3e235a3157ba7cee5f`.
An independent standard-library reread reparsed the canonical manifest and
blob and reproduced the byte/hash/header evidence, 7,490 logical data rows,
7,490 distinct nonblank CCNs, and 858 textual CCNs with a leading zero. The
survival period token was `01Jan2021-31Dec2024`; hospitalization and readmission
used `01Jan2024-31Dec2024`; all three outcome families contained availability
tokens `001`, `199`, `201`, and `258`. A second run under a new ID obtained the
same source bytes, required no retry, reused the verified blob, and recorded
`content_noop: true`.

The current 7,490-row result reconciles the earlier examined 7,490 snapshot in
`specs.md`; a planning-time catalog display of 7,557 preceded the July 2026
release. These are dated observations, not fixed acceptance counts. Git checks
confirmed the full CSV, manifests, temporary files, and response evidence are
ignored and absent from tracked content. The check preserves provider public
business location only: it performs no typing, county assignment, Census
Geocoder request, facility aggregate, screening enrichment, or mart
publication. The Census Geocoder preflight therefore remains Pending.

The strengthened Plan 008 offline loop passed 134 tests. The final canonical
locked loop completed `uv sync --locked`, clean Ruff format and lint checks,
and 389 passing pytest tests in 951.41 seconds. The final code independently
reread both live manifests and reproduced the 7,490-row/hash evidence and the
second run's content no-op. Automated HTML, accessibility, link, contrast,
responsive-rule, print-rule, and reduced-motion-rule checks passed. On
2026-08-15, the user confirmed rendered desktop/narrow, light/dark,
keyboard/focus, overflow, print, and reduced-motion QA for the standalone Plan
008 guide.

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
database remain under ignored paths. Plan 006 later completed CMS-to-SVI
reconciliation T-014, and Plan 007 later added the transparent threshold and
quadrants. Rankings and recommendations remain prohibited. The locked Plan 005
handoff completed `uv sync --locked`, clean Ruff format and lint checks, and
252 passing pytest tests.

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

The corrected v1 live run published one ignored content-addressed blob with
SHA-256 `10c8304012da34da3ecfe4caf4548927095f693383814d0e79ce6711b6806fad`,
57,865,948 bytes, 36,994 logical CSV data rows, 246 ordered columns, and 233
contract-compatible additive columns under the then-current 13-field contract.
The one-response transport recorded
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

## Plan 006 CMS v2 and paired dimensional check

On 2026-08-15 UTC, after the expanded offline contract, loader, dbt, and
failure-injection path was green, one bounded CMS refresh ran under contract
`cms_om_gv.raw.v2`. The v2 manifest promotes `BENES_OP_DLYS_CNT` to the
14-field required contract and reports 232 compatible additions. It reverified
the same 57,865,948 bytes and 36,994 rows at SHA-256
`10c8304012da34da3ecfe4caf4548927095f693383814d0e79ce6711b6806fad`,
required no retry, reused the verified blob, and did not alter either v1
manifest. The schema and header hashes remained
`4b409f690a9bc0a9378559035ba2829b9873490680376fdbf1a0d62639296d50`
and
`2c9d097415be8f240dd0d462f0d8907a2ce9209eb8742c840c771afe6f1465db`.

The atomic combined builder paired that CMS v2 manifest with the verified SVI
2022 manifest. It loaded 36,994 CMS rows and 3,144 SVI rows under input-set
SHA-256
`6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307`.
The full dbt build completed 214 model, seed, unit-test, and data-test results
with zero errors. Reduced dimensional evidence was:

| Relation/evidence | Rows or result |
|---|---:|
| CMS county stage and fact | 34,563 each |
| CMS benchmark stage and fact | 572 each; 51 State plus one National in each year 2014-2024 |
| `dim_year` | 11; 2014-2024 |
| `dim_county` | 3,155; 3,144 current plus 11 historical-only |
| Latest CMS county fact | 3,144; 3,143 direct County codes plus one audited DC mapping |
| Latest CMS/SVI reconciliation | 3,144 `matched`; zero mismatch |

The first ordered semantic hashes were `60a5de80…d26b6c` (`dim_year`),
`6f3d6dd0…b7d7eb7` (`dim_county`), `2c8de875…15cbeed` (county fact),
`0369f9c1…3abef4` (benchmark fact), and `3c94415a…631fe0b`
(reconciliation). A second database assembled independently at a fresh path
from the same two manifests reproduced the same input-set hash, row counts,
214-result green dbt build, and all five complete semantic hashes. Full raw
rows, manifests, DuckDB databases, and dbt artifacts remain ignored.

## Plan 007 transparent county screening check

On 2026-08-15 UTC, the verified Plan 006 input set was rebuilt twice at fresh
database paths. Both builds derived the same fixed national continuous P75 for
`BENES_OP_DLYS_PCT`: `0.0086000000`. The calculation used the latest governed
CMS year, current reconciled counties, and only reported nonnull values; it did
not use the source-published CMS National benchmark.

Each build produced 3,144 screening rows. Of those, 2,148 had both reported
components and 996 were `insufficient_data`. The complete-data categories
reconciled as follows:

| Screening category | County count |
|---|---:|
| Higher use / higher SVI | 354 |
| Higher use / lower SVI | 188 |
| Lower use / higher SVI | 259 |
| Lower use / lower SVI | 1,347 |
| Insufficient data | 996 |

The ordered semantic SHA-256 values matched across both paths:
`3df5e14cfa6ce24e5161bf6ac67ce52397a7a762b816e0aa5f5935ee0e6945ac`
for `int_county_screening_threshold`,
`5fffc53ae6392119d445bf65b1d6d91dedddadd58e13ab75d445bd7531275166`
for `mart_county_screening`, and
`1796d8d4002818a4ffc81386040e29f08421289000c9ba978eec50a6e51eacf1`
for `audit_screening_quadrant_summary`. A separate four-value fixture verified
DuckDB continuous interpolation as `0.0325000000`; boundary fixtures verified
that equality to P75 and equality to SVI `0.75` are both classified on the
higher side. Failure injection covered lineage mismatch, latest-year ambiguity,
historical leakage, threshold drift, component-flag inconsistency, invalid
thresholds, and summary drift.

These are dated pinned-snapshot observations, not timeless population counts.
The screen is transparent classification only. Facility context, publication,
Airflow, Power BI, and any ranking or recommendation remain outside Plan 007.

## Deferred or not required

| Check | Status | Note |
|---|---|---|
| AWS account, billing, and IAM | Not required | Optional phase only; it must not block the local mart and requires separate approval. |
| Power BI Service/public hosting | Not required | The core deliverable is a local `.pbix` plus documented artifacts. |

## Recording rule

When a check is actually performed, add the date, exact command or endpoint category, concise result, and any limitation. Do not record credentials, secrets, transient signed URLs, or full downloaded source data in this file.
