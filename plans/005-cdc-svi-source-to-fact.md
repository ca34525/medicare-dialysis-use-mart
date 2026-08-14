# Plan 005: CDC SVI paginated source-to-fact vertical slice

**Status:** Completed 2026-08-14  
**Source ID:** `cdc_svi_county_2022`  
**Depends on:** Completed Plans 001-004  
**Recommended delivery boundary:** One cohesive implementation commit after all
acceptance checks pass  
**Expected size:** Approximately three earlier plan-sized slices  
**Specification coverage:** Milestone 1 and the SVI portion of Milestone 2;
T-003, T-004, T-005, the SVI portion of T-006, T-008, the SVI portion of T-009,
and T-010  
**Authoritative requirements:** `specs.md` sections 4, 5.1-5.3, 5.6, 6.1-6.2,
7, 8.4, 9-11, 14-17, and 20

## Outcome

Complete one production-shaped SVI vertical slice. The implementation will
query the official CDC/ATSDR ArcGIS county layer in deterministic pages,
preserve every successful page as an immutable content-addressed JSON blob,
publish one reconciled run manifest, load the verified attributes as raw text
into DuckDB, and use dbt to build a typed SVI stage, the first canonical county
dimension, and `fct_svi_county`.

The end-to-end flow is:

```text
official layer metadata + count
              |
              v
explicit attribute-only pages ordered by GRASP_ID
              |
              v
validate every page and the complete 3,144-row snapshot shape
              |
              v
exact page bytes + one canonical run manifest
              |
              v
verified raw-string DuckDB relation
              |
              v
typed SVI stage -> dim_county + fct_svi_county
```

This is intentionally larger than Plans 001-004. Pagination, immutable
publication, raw loading, missingness typing, and final source-specific models
are bundled because they share one already verified source contract and one
clear grain. Stopping after pagination would leave the known `-999` rule and
the first useful SVI model unresolved; adding the CMS/SVI screen would cross
into separate threshold and multi-source decision logic.

## Why this is the next reasonable step

Plan 004 proved the official SVI layer identity, required fields, county grain,
page limit, ordering capability, unavailable sentinel, and source definitions.
The repository can now replace bounded evidence samples with a reproducible
full-source path without guessing about the API.

This slice also proves the genuinely paginated portion of ingestion. The CMS
extractor established immutable single-file snapshots, but it could not prove
that two or more pages are complete, nonoverlapping, and correctly ordered.
Finishing SVI through its fact model gives the project a second complete source
path and enough evidence to refactor only the ingestion primitives that are
actually shared.

## Product and safety boundaries

- Describe SVI only as static 2022 social vulnerability context based on
  2018-2022 ACS data.
- Do not describe SVI as a clinical measure, a cause, kidney disease
  prevalence, unmet need, disease burden, or an intervention opportunity.
- Do not calculate the 2x2 screening quadrant, a composite score, a ranking,
  or a site-selection recommendation in this plan.
- Do not contact CMS, facility sources, the Census Geocoder, Power BI, AWS, or
  any account-authenticated service.
- Use public aggregate data only. No patient-level data or PHI is in scope.
- Keep the default pytest and dbt fixture path deterministic and network-free.
- Perform the one full live SVI extraction only after the offline path is
  green, and retain it only beneath ignored generated-data paths.

## Scope decisions

### Included

- Resolve and validate the exact official layer 1 metadata on every live run.
- Request a count before pagination and treat it as a dated source observation,
  not a timeless constant.
- Request only the 17 Plan 004 required attributes, with
  `returnGeometry=false`, explicit `GRASP_ID ASC` ordering, and pages no larger
  than 2,000 records.
- Preserve the exact successful JSON response bytes for each page.
- Validate page envelopes, feature attributes, record counts, offsets,
  ordering, object IDs, FIPS, duplication, completeness, and count
  reconciliation before publishing a run manifest.
- Reuse the existing bounded HTTP retry policy for transient transport errors
  only; add a byte-preserving bounded JSON response seam where needed.
- Publish content-addressed page blobs and a canonical multi-page manifest
  without overwriting an earlier blob or manifest.
- Verify the manifest and every referenced page again before loading.
- Load required ArcGIS attributes into DuckDB as `VARCHAR`, preserving the JSON
  numeric token text for `-999`, zero, rank boundaries, and percentages.
- Produce a typed dbt staging model with raw/value/status fields for all five
  ranks and six selected `EP_*` percentages.
- Convert SVI `-999` to null with an explicit unavailable status; keep numeric
  zero as reported zero; block invalid numeric text and out-of-range values.
- Build `dim_county` at one row per five-character county FIPS and
  `fct_svi_county` at county FIPS x SVI vintage.
- Add source-specific dbt contracts, unit tests, data tests, documentation, and
  a combined fixture-sized `dbt build` that keeps the existing CMS path green.
- Prove same-snapshot and same-run idempotency and deterministic model output.
- Run one separate live SVI extraction and record only reduced, dated evidence.
- On completion, create the matching standalone Plan 005 HTML guide and link
  it from the root README after Plan 004.

### Excluded

- `fct_medicare_county_year`, Medicare benchmark facts, the CMS/SVI production
  join, and the pinned T-014 3,144/3,144 cross-source reconciliation.
- The 75th-percentile Medicare threshold, `RPL_THEMES >= 0.75`
  classification, quadrants, `mart_county_screening`, or any facility context.
- A multi-source production run-database assembler, Airflow, atomic Parquet
  publication, or a `latest-successful-run` pointer.
- Downloading all 161 SVI fields, geometry, tract/ZCTA/state layers, Puerto
  Rico, or another SVI vintage.
- Cross-year SVI comparisons or treating the SVI vintage as current-year data.
- A generic extraction plugin system, generic data-quality framework, or broad
  refactor of the working CMS path.
- A new runtime or development dependency.
- Committing full SVI responses, generated manifests, DuckDB files, or dbt
  output.

The Plan 005 models should make the later CMS/SVI reconciliation straightforward,
but they must not claim T-014 until a separate pinned full build joins both
verified source snapshots and accounts for every in-scope county.

## Source request contract

Use the durable layer URL already verified in Plan 004:

```text
https://services3.arcgis.com/ZvidGQkLaDJxRSJ2/ArcGIS/rest/services/
CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/1
```

Construct requests with a standard URL encoder. Do not store a hand-built or
transient query URL as the source identity.

### Metadata request

The layer metadata request must use `f=json` and verify:

- layer ID `1` and name `SVI2022 US county`;
- object-ID field `GRASP_ID`;
- all required fields once with compatible ArcGIS types;
- `maxRecordCount >= 2000` or an explicit smaller safe page-size adjustment;
- pagination and ordering capabilities; and
- a valid layer edit timestamp when the service supplies one.

Additive metadata fields remain compatible and are reported in the manifest.
A removed, duplicated, or incompatible required field blocks the run.

### Count request

The count query must use the same layer and filter as the data pages, with
`where=1=1` and `returnCountOnly=true`. It must return one nonnegative integer.
An ArcGIS `error` object, missing count, noninteger count, or implausible count
shape is a source/protocol failure and is not retried as data quality.

The Plan 004 observation of 3,144 rows is a pinned-snapshot expectation. A live
change must be investigated and documented; it must not be silently forced back
to 3,144 or silently accepted as equivalent.

### Page requests

Every page must use:

- `where=1=1`;
- `outFields` containing exactly the 17 required fields in one documented
  stable order;
- `returnGeometry=false`;
- `orderByFields=GRASP_ID ASC`;
- `resultOffset` beginning at zero and advancing by the requested page size;
- `resultRecordCount` no larger than 2,000; and
- `f=json`.

The implementation may lower the page size when verified metadata requires
it, but may never exceed the layer's reported maximum. It may not switch to
unordered pagination or `outFields=*` to make a failing run pass.

## Multi-page manifest contract

Use a source-specific manifest rather than forcing the CMS single-CSV manifest
to represent different transport semantics. Shared run-ID validation,
canonical JSON, hashing, path confinement, and no-overwrite publication may be
factored into narrow helpers only after tests prove their behavior remains
identical for CMS.

Write canonical UTF-8 JSON with sorted keys, stable array order, and one final
newline. The manifest must contain at least:

- manifest format version;
- source ID, pipeline run ID, extractor version, and Plan 004 contract version;
- durable feature-service and layer URLs, stable service item ID, layer ID,
  layer name, and object-ID field;
- retrieval timestamp, SVI release `2022`, ACS period `2018-2022`, and the
  observed layer edit timestamp;
- count-query result, requested page size, page count, total record count,
  exact ordered field projection, ordering rule, filter, and
  `return_geometry: false`;
- complete observed metadata field names/types, their deterministic schema
  hash, sorted additive fields, and the committed Plan 004 schema-evidence
  identity used for validation;
- one ordered entry per page containing page index, requested offset and limit,
  returned record count, exact byte count, SHA-256, relative blob path,
  first/last `GRASP_ID`, first/last county FIPS, and the observed
  `exceededTransferLimit` signal when present;
- total distinct county FIPS and object-ID counts;
- District of Columbia `11001` presence and zero territory rows;
- a `snapshot_sha256`; and
- content and same-run no-op status.

Define `snapshot_sha256` as the SHA-256 of canonical JSON containing the ordered
page identities: page index, offset, record count, byte count, and exact page
SHA-256. It identifies the ordered set of raw response bytes; it is not a hash
of reserialized feature objects.

## Pagination and publication invariants

- Store exact successful page bytes. Do not pretty-print, normalize, or combine
  them before hashing and publication.
- Reject an ArcGIS `error` envelope, invalid JSON, a non-object root, a missing
  `features` array, a feature without an `attributes` object, or unexpected
  geometry.
- Every feature must contain every requested required attribute. Missing
  required values remain present as JSON null; a missing attribute key is a
  contract failure.
- Each page must contain at most the requested number of rows.
- All nonfinal pages must be complete. An empty or short page before the count
  is satisfied is a truncated extraction.
- `GRASP_ID` values must be positive, globally unique, and strictly increasing
  across and within pages.
- County FIPS values must be globally unique five-character text, agree with
  the two-character state prefix, include DC as `11001`, and exclude territory
  prefixes.
- Page counts must sum exactly to the count-query result. Never infer missing
  rows from offsets or `exceededTransferLimit` alone.
- Validate all pages and global reconciliation before publishing the manifest.
- Publish page blobs under their SHA-256 identities and never overwrite them.
  The manifest is the successful-snapshot commit boundary.
- A failed or interrupted run cannot create a successful manifest or alter a
  previous manifest, raw blob, staging database, or published mart state.
- A new run with identical ordered page hashes records a content no-op and
  reuses verified blobs.
- Repeating the same run ID with identical canonical lineage is a successful
  no-op. The same run ID with different bytes or lineage is a conflict.

## Generated storage layout

Extend the ignored generated-data boundary without changing the CMS layout:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       |-- <cms-content-sha256>.csv
|       `-- <svi-page-sha256>.json
|-- manifests/
|   |-- cms_om_gv/
|   `-- cdc_svi_county_2022/
|       `-- <pipeline-run-id>.json
`-- .tmp/
    `-- <pipeline-run-id>/

data/staging/
`-- <pipeline-run-id>.duckdb
```

The SVI staging database is run-scoped and source-specific in this plan. It
does not update a published pointer. A later orchestration plan will assemble
all verified source manifests into one run-scoped mart build under DuckDB's
single-writer discipline.

## Raw DuckDB loading contract

The network-free loader accepts exactly one SVI manifest and its configured raw
root. Before creating a final database it must:

1. require the supported canonical manifest format, source ID, contract
   version, layer identity, and query contract;
2. confine the manifest and every page path beneath the configured raw root;
3. independently rehash and recount every exact page blob;
4. reconstruct and verify `snapshot_sha256`;
5. reparse all envelopes and repeat page/global count, order, uniqueness, FIPS,
   and field-presence validation; and
6. reconcile loaded rows to the manifest.

Parse JSON numeric tokens with `json.loads(..., parse_int=str,
parse_float=str)` or an equivalently tested mechanism so the raw relation keeps
the source token text instead of introducing a Python floating-point round
trip. JSON strings remain strings and JSON null remains SQL null.

Create at least:

- `raw.cdc_svi_county_2022`, containing the 17 required attributes as
  `VARCHAR` plus source/run/snapshot/page lineage; and
- `raw.cdc_svi_county_2022_load_audit`, containing one reconciled row for the
  manifest, page count, record count, schema hash, and snapshot hash.

Useful row lineage includes source ID, manifest run ID, snapshot hash,
retrieval timestamp, source edit timestamp, page index, page offset, and page
content hash. `GRASP_ID` remains raw text in this boundary even though it was
validated as a positive integer transport key.

The final DuckDB file must appear only after a complete successful load. An
identical manifest/database rerun is a no-op; different lineage at the same
path is a conflict. Do not weaken the existing Plan 003 CMS database
guarantees while introducing the second loader.

## dbt model contracts

### `stg_cdc_svi_county_2022`

**Grain:** one row per `county_fips` for SVI vintage 2022.  
**Denominators:** the five `RPL_*` fields are U.S.-based county percentile
ranks; each `EP_*` field retains the distinct official source-defined
denominator recorded in Plan 004.  
**Vintage:** SVI release 2022, based on 2018-2022 ACS data.  
**Lineage:** one verified SVI manifest and snapshot hash per build.

At minimum include:

- `county_fips`, `state_fips`, `state_name`, `state_abbreviation`, and
  `county_name`;
- `source_object_id` as a positive integer typed only for audit/order use;
- `svi_vintage = 2022`, `acs_period_start = 2018`, and
  `acs_period_end = 2022`;
- raw/value/status triplets for `RPL_THEMES`, `RPL_THEME1`, `RPL_THEME2`,
  `RPL_THEME3`, `RPL_THEME4`, `EP_POV150`, `EP_UNINSUR`, `EP_AGE65`,
  `EP_DISABL`, `EP_LIMENG`, and `EP_NOVEH`; and
- source manifest, snapshot, retrieval, edit, and contract lineage.

Use readable lower-snake-case analytical names while documenting each exact
source label. Retain exact decimal semantics; do not use binary floating point
for governed values.

The SVI status vocabulary is:

| Raw representation | Typed value | Status |
|---|---:|---|
| `-999` | null | `unavailable_sentinel` |
| JSON null | null | `unavailable_null` |
| valid numeric text, including `0` | parsed decimal | `reported` |
| any other token | null | `invalid_numeric` and the build fails |

After sentinel/null handling:

- every reported rank must be within `[0,1]`;
- every reported selected `EP_*` percentage must be within `[0,100]`;
- zero must remain reported zero;
- `0.75` must remain exactly `0.75`; and
- raw `-999` must remain available beside its null typed value and explicit
  status.

### `dim_county`

**Grain:** one row per canonical five-character county FIPS.  
**Source:** the verified 2022 U.S. SVI county snapshot.  
**Purpose:** establish the first tested county identity and label surface for
later CMS and facility joins.

Include canonical county FIPS, state FIPS, state name, state abbreviation,
county name, a valid/in-scope geography status, SVI geography vintage, and
source manifest/snapshot provenance. The model must contain DC `11001`, no
territories, no duplicate FIPS, and no inferred or fuzzy geography.

This dimension is not evidence that SVI is clinically authoritative. It uses
the source's complete in-scope county geography and retains that provenance so
a later plan can reconcile other sources explicitly.

### `fct_svi_county`

**Grain:** county FIPS x SVI vintage.  
**Denominators:** retain the same per-field meanings as the stage.  
**Lineage:** retain source ID, manifest run ID, snapshot hash, retrieval time,
source edit time, and ACS period.

Include the typed five ranks and six selected percentages with explicit
availability statuses. Keep the raw token in staging; it need not be repeated
in the fact if the fact has a tested one-to-one lineage path back to staging.
Every county key must resolve to `dim_county`.

Do not add `is_high_social_vulnerability`, a quadrant, or an analyst-facing
interpretation in this plan. The later screening model owns the exact
`RPL_THEMES >= 0.75` rule together with the Medicare threshold and
insufficient-data classification.

## Planned repository artifacts

Exact filenames may be refined during red-green work, but these
responsibilities must remain visible:

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/extract/cdc_svi_county_2022.py` | Official metadata/count resolution, page planning, global validation, live CLI, and orchestration. |
| `src/kidney_care_mart/extract/arcgis.py` | Narrow ArcGIS page-envelope/query helpers if repetition justifies a separate module. |
| `src/kidney_care_mart/extract/manifest.py` or a narrow sibling | Shared canonical hash/path primitives plus the source-specific multi-page manifest/publication behavior. |
| `src/kidney_care_mart/stage/cdc_svi_county_2022.py` | Manifest/page verification and raw-string DuckDB loading. |
| `tests/fixtures/cdc_svi_county_2022/layer.json` | Minimal official-shaped layer metadata fixture. |
| `tests/fixtures/cdc_svi_county_2022/count.json` | Deterministic count response requiring at least two fixture pages. |
| `tests/fixtures/cdc_svi_county_2022/pages/` | Small exact JSON page bodies covering page boundaries and values. |
| `tests/fixtures/cdc_svi_county_2022/staging-manifest.json` | Reconciled canonical fixture manifest. |
| `tests/unit/extract/test_cdc_svi_county_2022.py` | Query, pagination, reconciliation, failure, publication, and idempotency tests. |
| `tests/unit/stage/test_cdc_svi_county_2022_stage.py` | Local integrity, raw-string load, lineage, atomicity, and conflict tests. |
| `analytics/models/staging/cdc_svi_county_2022/stg_cdc_svi_county_2022.sql` | Typed one-row-per-county SVI stage. |
| `analytics/models/staging/cdc_svi_county_2022/_cdc_svi_county_2022_models.yml` | Stage contract, documentation, unit tests, and data tests. |
| `analytics/models/marts/core/dim_county.sql` | Canonical county dimension sourced with explicit SVI provenance. |
| `analytics/models/marts/core/fct_svi_county.sql` | Typed SVI county-vintage fact. |
| `analytics/models/marts/core/_core_models.yml` | Dimension/fact contracts, relationships, grains, units, and lineage. |
| `analytics/tests/assert_svi_*.sql` | Blocking rank, percentage, grain, lineage, and reconciliation tests that do not fit generic YAML tests. |
| `tests/integration/test_cdc_svi_county_2022_dbt.py` | Network-free manifest -> DuckDB -> dbt acceptance and failure injection. |
| `data/README.md` | Multi-page raw layout and SVI local commands. |
| `docs/source-catalog.md` | SVI extraction, model grain, denominator, vintage, and lineage documentation. |
| `docs/preflight.md` | Reduced dated live extraction and disk-reconciliation evidence. |
| `docs/guides/005-svi-source-to-fact-explained.html` | Required standalone beginner-friendly completed-plan guide. |
| `README.md` | Current status, guide link, and exact fixture/live/local commands. |

Do not create a shared framework merely to make these filenames symmetrical.
If CMS and SVI genuinely share only canonical JSON, hashing, run-ID, and path
rules, share only those primitives and keep source transport contracts
separate.

## Red-green-refactor execution sequence

### 1. Lock the multi-page fixture protocol

Add the smallest official-shaped metadata, count, and page fixtures that prove:

1. at least two pages are required even though the fixture is small;
2. requested offsets and `GRASP_ID` order are observable;
3. `01001` and `11001` retain leading zeros and valid FIPS;
4. zero, `0.75`, `1`, `-999`, JSON null, and a valid percentage are present;
5. page blobs contain attributes only and no geometry;
6. one mutation creates a short/truncated first page;
7. one mutation duplicates an object ID across pages;
8. one mutation duplicates county FIPS across pages;
9. one mutation reverses or overlaps page order;
10. one mutation removes a required attribute; and
11. separate dbt mutations contain an out-of-range rank, an out-of-range
    percentage, and invalid numeric text.

The committed fixtures are synthetic protocol examples, not observations about
real counties. Keep the existing Plan 004 raw-contract fixture valid for its
own purpose; add dedicated page/staging fixtures instead of weakening it.

### 2. Test exact query construction and transient behavior

Add failing tests showing that the extractor:

1. validates current layer metadata with the Plan 004 contract before paging;
2. uses the same filter for count and data requests;
3. requests exactly the required attributes and no geometry;
4. orders by `GRASP_ID ASC`;
5. never requests more than the verified page limit;
6. URL-encodes parameters deterministically;
7. sends the repository's descriptive user agent and bounded timeout;
8. retries connection failures, timeouts, HTTP 408, 429, and 5xx only within
   the existing bounded policy; and
9. does not retry ArcGIS error envelopes, schema issues, malformed JSON,
   contract failures, or reconciliation failures.

If exact page bytes require extending the HTTP helper, write the failing helper
tests first and preserve every existing CMS test unchanged.

### 3. Test page and global reconciliation

Add failing tests for every pagination invariant before publication code:

1. exact page response bytes and hashes are retained;
2. page envelopes and attribute keys are valid;
3. per-page counts do not exceed the requested limit;
4. offsets cover the count without gaps or overlaps;
5. a short nonfinal page and early empty page block completion;
6. object IDs are positive, unique, and strictly increasing globally;
7. county FIPS values are valid, unique, in-scope, and state-prefix consistent;
8. DC is represented as `11001`;
9. summed page rows equal the count query exactly;
10. a misleading or absent `exceededTransferLimit` signal cannot override count
    reconciliation; and
11. pagination stops after the count is satisfied without an unbounded
    empty-page loop.

Implement only enough source-specific page planning and validation to pass.

### 4. Test the manifest and immutable publication

Add failing tests proving that:

1. canonical manifest bytes are deterministic;
2. every page entry reconciles to its exact blob bytes and observed rows;
3. `snapshot_sha256` follows the documented ordered-page algorithm;
4. no manifest is published until all pages and global invariants pass;
5. a failed page or validation leaves prior successful artifacts unchanged;
6. same-content pages are reused only after their existing bytes rehash
   correctly;
7. same-snapshot/new-run behavior records a content no-op;
8. same-run/same-lineage behavior is a no-op;
9. same-run/different-lineage behavior fails without overwrite;
10. a corrupt existing page blob blocks publication; and
11. invalid run IDs or manifest/page paths cannot escape `data/raw`.

The test contract should treat the manifest as the successful-snapshot commit
record. A content-addressed blob left by a process crash is not a successful
snapshot unless a valid manifest references and reconciles it.

### 5. Assemble the live extractor command

Provide one explicit command, for example:

```powershell
uv run python -m kidney_care_mart.extract.cdc_svi_county_2022 `
  --run-id cdc-svi-2022-<UTC timestamp> `
  --output-root data/raw
```

It returns a concise structured result with status, manifest path, snapshot
hash, page hashes/counts, record count, distinct FIPS/object-ID counts, retry
count, and content no-op state. It must not print full feature rows or store a
transient query URL as source identity.

Do not run the live command until the extractor's deterministic success and
failure tests are green.

### 6. Test manifest-driven raw loading

Add failing loader tests proving that:

1. only the supported SVI source/manifest/contract/layer identity is accepted;
2. canonical manifest bytes and all path boundaries are required;
3. every page is rehashed, reparsed, and globally reconciled before database
   creation;
4. JSON numeric tokens enter DuckDB as raw strings without a float round trip;
5. `01001`, `11001`, `-999`, `0`, `0.75`, and JSON null remain distinct;
6. every row carries manifest, snapshot, and page lineage;
7. loaded rows and audit evidence reconcile exactly to the manifest;
8. a corrupt/missing page, bad FIPS, duplicate key, or count mismatch creates
   no final database;
9. an identical final database is a no-op; and
10. conflicting lineage cannot overwrite an existing database.

Keep the loader network-free and source-specific. Reuse shared helpers only
where their behavior is truly identical to Plan 003.

### 7. Test SVI typing and bounds in dbt

Add failing dbt unit/data tests for every governed field showing that:

1. `-999` becomes null plus `unavailable_sentinel`;
2. JSON null becomes null plus `unavailable_null`;
3. zero remains zero plus `reported`;
4. valid decimal text keeps its source scale;
5. raw strings remain unchanged in staging;
6. invalid numeric text blocks the build;
7. each rank is null or within `[0,1]`;
8. each selected percentage is null or within `[0,100]`;
9. `0.75` remains exact but is not yet classified; and
10. model lineage and SVI/ACS vintages are nonnull and constant as declared.

Centralize the repeated SVI value/status expressions only after one direct
implementation is green and tests prove the refactor is behavior-preserving.

### 8. Build and test the county dimension and SVI fact

Add failing tests proving that:

1. `dim_county` is unique and nonnull at county FIPS grain;
2. every dimension FIPS is five-character text and state-prefix consistent;
3. DC `11001` is present in the appropriate complete fixture/live build;
4. no territory row enters the dimension;
5. geography labels and source provenance are retained without fuzzy repair;
6. `fct_svi_county` is unique and nonnull at county FIPS x SVI vintage;
7. every fact county resolves to exactly one dimension row;
8. fact values/statuses reconcile one-to-one to the valid stage;
9. source labels, units, denominators, and vintages are documented; and
10. an ordered result checksum is stable across a same-manifest rebuild.

Update the existing fixture dbt harness so the repository can build its CMS
and SVI models together without network access. Do not change the meaning of
the CMS stage or its existing assertions to accommodate the new source.

### 9. Run live extraction and reduced reconciliation

After all offline checks pass:

1. run one full SVI extraction from the official layer;
2. independently rehash every page and the manifest from disk;
3. verify page sizes, global ordering, row count, distinct FIPS, distinct object
   IDs, DC presence, and zero territories;
4. load the generated manifest into a fresh ignored DuckDB database;
5. run the SVI dbt selection and verify `dim_county` and `fct_svi_county` row
   counts and tests;
6. rerun with a new run ID if the layer is unchanged and prove page reuse and
   content no-op behavior; and
7. reduce the result to dated hashes/counts/status in `docs/preflight.md`.

If a verified local CMS manifest already exists, a read-only ad hoc
reconciliation may report how its latest in-scope county set compares with the
new SVI dimension. Label that evidence as preparatory only; do not mark T-014
complete or add screening logic in this plan.

No response body, generated page, manifest, database, or transient query URL
may enter Git.

### 10. Refactor, document, and complete the guide

After all behavior is green:

1. keep source-specific query, manifest, and typing rules easy to audit;
2. document exact generated layout, fixture command, live command, and local
   manifest-to-dbt command;
3. update the source catalog with every grain, denominator, unit, vintage,
   lineage field, and limitation;
4. create the network-free Plan 005 HTML guide according to
   `docs/guides/README.md`;
5. explain pagination, exact raw pages, manifests, `-999`, dimensions, and facts
   for a beginner without implying clinical meaning;
6. link the guide from the root README after Plan 004;
7. add static guide tests and complete rendered desktop/narrow,
   light/dark, keyboard, print, and reduced-motion QA;
8. update this plan to `Completed` with exact test/live evidence;
9. run the full locked verification loop; and
10. inspect Git status and ignored generated paths before handoff.

## Verification commands

Focused extractor and loader loop:

```powershell
uv run pytest tests/unit/extract/test_cdc_svi_county_2022.py
uv run pytest tests/unit/stage/test_cdc_svi_county_2022_stage.py
uv run ruff format --check src tests
uv run ruff check src tests
```

Focused dbt/integration loop:

```powershell
uv run pytest tests/integration/test_cdc_svi_county_2022_dbt.py
uv run dbt parse --project-dir analytics --profiles-dir analytics
```

The implementation must replace any fixture-profile assumption with the exact
repository helper or temporary profile command used by tests. The checked-in
`analytics/profiles.example.yml` remains credential-free.

Required offline handoff loop:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Explicit live check, only after offline verification:

```powershell
uv run python -m kidney_care_mart.extract.cdc_svi_county_2022 `
  --run-id cdc-svi-2022-live-<UTC timestamp> `
  --output-root data/raw
```

The complete default suite must make zero external requests. Live checks are
manual/generated evidence and never a pytest, dbt, or pull-request dependency.

## Acceptance criteria

- [x] Official metadata validation resolves exactly layer 1 `SVI2022 US
  county`, object-ID field `GRASP_ID`, and all required fields before paging.
- [x] Page queries use explicit required fields, no geometry, deterministic
  object-ID ordering, and a verified maximum of 2,000 records per page.
- [x] T-003 passes for a genuinely paginated source: offsets are complete,
  pages do not overlap, IDs/FIPS are globally distinct, and record totals match
  the count query exactly.
- [x] Exact page response bytes are immutable, content-addressed, and fully
  reconciled by one canonical source-specific manifest.
- [x] T-004 passes for every page hash/byte/row count, the ordered snapshot
  hash, schema evidence, and total record count.
- [x] Contract, API envelope, truncated page, duplicate, order, count, path,
  and integrity failures cannot publish a successful manifest or final staging
  database.
- [x] Transient network failures retry with bounded backoff; protocol,
  contract, and data-quality failures fail immediately.
- [x] Same-content and same-run reruns are idempotent without overwriting
  immutable artifacts.
- [x] T-005 passes for SVI from JSON page bytes through DuckDB and dbt,
  including `01001` and DC `11001` as five-character text.
- [x] The SVI portion of T-006 passes: `-999` becomes null with
  `unavailable_sentinel`, JSON null is distinct, and numeric zero remains
  reported zero.
- [x] T-008 passes for `stg_cdc_svi_county_2022`, `dim_county`, and
  `fct_svi_county` at their declared grains.
- [x] The SVI portion of T-009 passes: every fact county resolves to exactly one
  `dim_county` row; no unexplained geography is dropped or repaired.
- [x] T-010 passes: ranks are null or `[0,1]`, selected percentages are null or
  `[0,100]`, and documented source units/denominators are preserved.
- [x] All stage, dimension, and fact rows retain sufficient source vintage and
  manifest/snapshot lineage for audit.
- [x] Fixture extraction, loading, dbt build, failure injection, and checksum
  tests are deterministic and network-free.
- [x] One separate live extraction and local model build complete, with dated
  reduced evidence and independently reconciled generated artifacts.
- [x] The live 3,144-row expectation is either corroborated as dated evidence
  or any legitimate upstream change is investigated and explained without
  silently changing a timeless assertion.
- [x] The Plan 005 guide is standalone, network-free, accessible, linked from
  the README in numeric order, and passes static plus rendered visual QA.
- [x] No full response, manifest, DuckDB file, dbt output, secret, patient
  information, or transient query URL appears in Git status.
- [x] No dependency or lockfile change is made.
- [x] The locked Ruff and complete offline pytest/dbt fixture suite pass.
- [x] This plan's completion record states explicitly that screening logic and
  pinned CMS/SVI T-014 reconciliation remain deferred.

## Completion record

Completed 2026-08-14 with red-green-refactor at each critical boundary. The
extractor tests were written before the source module and initially failed at
import; the loader and dbt tests likewise preceded their implementations. The
focused green suite now contains 25 extractor tests, 11 loader tests, seven SVI
dbt integration/failure-injection tests, and four static guide tests. The final
locked handoff completed `uv sync --locked`, Ruff format and lint checks, and
all 252 network-free pytest tests with no failures. No dependency or lockfile
changed.

The live source check retrieved 3,144 rows in two exact pages: 2,000 rows and
635,389 bytes at offset 0, then 1,144 rows and 365,449 bytes at offset 2,000.
Page SHA-256 values were
`06b724e33bb61b4d3cd5996ce3b12a122e3de38807e84b3c7fe5a58541d377eb`
and
`62376e01a8197cc1772e78f2eda9b47b40ec4ac0f78ccd86b7525d6cd669ccf5`;
the ordered snapshot SHA-256 was
`51c2fbc79ddf9eb5a2f71480bde151f5b4e4e2d0494c2e780baa557e7014a2ee`.
Independent disk reconciliation and loading produced 3,144 rows in the raw
relation, typed stage, county dimension, and SVI fact. The live SVI dbt
selection passed 73 results. A second run reproduced both page hashes and the
snapshot hash, reused both page blobs without retry, and recorded a content
no-op.

The Plan 005 guide passed its static semantic, accessibility, contrast,
network-free, internal-link, print, and reduced-motion assertions. Rendered QA
at 1,280 x 720 and 390 x 844 confirmed readable light and dark presentations,
native keyboard focus, semantic landmarks, responsive stacking, and no
horizontal overflow. Generated pages, manifests, DuckDB files, the local dbt
profile, logs, and targets remained ignored and absent from Git status.

Screening logic, the `RPL_THEMES >= 0.75` classification, CMS final facts and
benchmarks, and pinned CMS/SVI geography reconciliation T-014 remain explicitly
deferred. This plan produces transparent contextual source facts only; it does
not create a score, quadrant, ranking, or recommendation.

## Stop conditions

Stop and request a specification or architecture decision if:

- the durable service no longer resolves the exact verified 2022 U.S. county
  layer;
- pagination or deterministic ordering is no longer supported;
- the count query and complete ordered pagination cannot be reconciled after
  bounded retries;
- a required field is removed, duplicated, or changes to an incompatible type
  or materially different definition/denominator;
- legitimate in-scope rows violate five-character FIPS, state-prefix, DC, or
  unique-county policy;
- live rows introduce an undocumented missingness token or valid values outside
  the documented rank/percentage scales;
- exact page preservation or atomic successful-manifest semantics require
  overwriting an immutable artifact;
- correct decimal typing requires a dependency or type-policy change;
- the existing CMS extractor/stage would have to be weakened or behaviorally
  changed to share code;
- generated artifacts cannot be kept outside version control;
- public access now requires authentication, payment, or nonpublic data;
- bounded live attempts cannot distinguish an upstream failure from a local
  network restriction; or
- any required test would have to be weakened to complete the plan.

Do not silently switch layers, reduce the requested field contract, accept
partial pages, coerce FIPS through numbers, convert `-999` to zero, discard raw
tokens, ignore out-of-range values, change SVI vintage, or proceed into the
screening mart.

## Autonomous execution boundary

This plan is suitable for an unattended goal. The source contract and official
locators are already verified; live operations are public, read-only, bounded,
and account-free; default verification is deterministic; generated artifacts
are ignored; dependency changes and cross-source decision logic are excluded;
and objective stop conditions cover the remaining uncertainty.

The execution goal is:

> Implement Plan 005 completely using red-green-refactor. Deliver deterministic
> ArcGIS pagination, immutable exact-page blobs and a reconciled multi-page
> manifest, manifest-driven raw-string DuckDB loading, the typed SVI stage,
> `dim_county`, `fct_svi_county`, source/model tests and documentation, the
> matching standalone HTML guide, one bounded live SVI extraction, and all
> offline verification. Keep every default test network-free and preserve the
> required grains, denominators, vintages, lineage, missingness, and product
> language. Do not change dependencies, commit, push, contact other live
> sources, build the CMS/SVI screen, or proceed beyond this plan. Stop only at a
> listed stop condition; otherwise continue until every acceptance criterion is
> satisfied.

## Handoff

After Plan 005 is complete, the next dependency-ordered choice is either:

1. establish the CMS final county/year and benchmark facts, then perform the
   pinned CMS/SVI geography reconciliation before implementing the transparent
   screening threshold; or
2. complete the Dialysis Facility source contract and ingestion path before
   entering the cross-source dimensional mart.

The first option creates the primary two-component county screen sooner. The
second keeps Milestone 1 source acquisition strictly complete before more
Milestone 2 modeling. Choose explicitly in the next numbered plan; Plan 005
must not silently begin either path.
