# Source catalog

## `cms_om_gv` - CMS Original Medicare Geographic Variation

**Contract status:** Contract v2 and dimensional path verified 2026-08-15 UTC against the official CMS catalog, current full file, pinned 2014-2024 dictionary, and the paired SVI snapshot.

| Attribute | Contract |
|---|---|
| Durable identity | CMS dataset `6219697b-8f6c-4164-bed4-cd9317c58ebc` |
| Official catalog | `https://data.cms.gov/data.json` |
| Official landing page | `https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-comparisons/medicare-geographic-variation-by-national-state-county` |
| Stable latest API | `https://data.cms.gov/data-api/v1/dataset/6219697b-8f6c-4164-bed4-cd9317c58ebc/data` |
| Current source vintage | Calendar years 2014-2024; catalog modified 2026-05-15 |
| Raw transport grain | `YEAR x BENE_GEO_LVL x BENE_GEO_DESC x BENE_GEO_CD x BENE_AGE_LVL` using CMS's raw geography-code representation |
| Primary county denominator | Original Medicare beneficiaries (`BENES_OM_CNT`) for each source-published County + All row |
| Dialysis-user count | `BENES_OP_DLYS_CNT`, a reported integral count; never derived from a rounded share |
| Primary screening field | `BENES_OP_DLYS_PCT`, observed outpatient dialysis use among Original Medicare beneficiaries |
| Access | Public CSV/API without authentication |
| Lineage | Official catalog -> stable dataset identity -> current API/data-viewer metadata and resolved version distribution; field definitions -> pinned official dictionary |

The version-specific CSV URL is retained only as observed provenance in the normalized schema snapshot. Resolution must begin with the official catalog or stable dataset identity; code must not treat that distribution URL as the durable locator.

The current metadata exposes 246 columns: 242 `NUMERIC` and four `TEXT`. The executable v2 contract requires 14 fields, including `BENES_OP_DLYS_CNT`, and reports the other 232 observed fields as compatible additions. Exact labels, definitions, declared types, full observed order, additive fields, type encoding, and hashes are recorded in `docs/source-schemas/cms_om_gv.schema.json`. Existing v1 manifests remain immutable historical ingestion evidence, but the combined dimensional builder rejects them with `cms_contract_upgrade_required`.

### Full-file extraction and immutable lineage

The live extractor begins at the official catalog, matches stable dataset ID
`6219697b-8f6c-4164-bed4-cd9317c58ebc` exactly, corroborates the official title
and landing page, and resolves the catalog's one current full CSV. It then reads
the stable `data-viewer` metadata for the ordered headers, CMS-declared types,
row count, byte count, and source SHA-1 before downloading the resolved CSV.
A caller cannot supply an arbitrary download URL.

Run the live operation explicitly from the repository root; it is not part of
pytest or default pull-request checks:

```powershell
uv run python -m kidney_care_mart.extract.cms_om_gv `
  --run-id cms-om-gv-v2-live-<UTC timestamp> `
  --output-root data/raw
```

The request uses a descriptive user agent, a 30-second per-operation timeout,
and at most three attempts with capped exponential backoff and jitter. Only
connection failures, timeouts, HTTP 408, HTTP 429, HTTP 5xx, and incomplete
`Content-Length` transfers are retried. Schema, JSON, CSV, contract, grain, and
reconciliation failures fail immediately.

The unchanged response bytes are stored once at
`data/raw/blobs/sha256/<content-sha256>.csv`. Each pipeline run has a canonical
UTF-8 manifest at `data/raw/manifests/cms_om_gv/<run-id>.json`. Publication uses
same-volume temporary files and atomic, no-overwrite materialization. A later
run with identical bytes reuses the verified blob and records
`content_noop: true`; a repeated run ID with different content or lineage is a
blocking conflict.

The manifest records:

- format, extractor, contract, source, dataset, and pipeline-run identities;
- official catalog and landing URLs plus the resolved current CSV URL;
- UTC retrieval time, source release/modified date, ETag, and Last-Modified;
- content SHA-256, byte count, and logical CSV data-row count;
- transport mode `full_csv`, `page_count: 1`, and record count;
- ordered `{name, declared_type}` metadata pairs and their canonical JSON
  SHA-256;
- ordered raw CSV header labels and their canonical JSON SHA-256;
- sorted additive columns, relative blob path, and content no-op status.

The typed `schema_sha256` hashes canonical JSON for the ordered metadata pairs.
The `header_sha256` separately hashes canonical JSON for the ordered raw header
labels because a CSV header does not encode declared types. Both hashes exclude
the manifest's final presentation newline.

### CMS Geographic Variation raw-to-stage

Plan 003 adds a strictly local transformation boundary. It accepts one
canonical manifest path, resolves its content-addressed blob only beneath the
configured raw root, and independently reconciles the manifest format, source
and contract identity, content SHA-256, bytes, logical CSV rows, schema hash,
header hash, additive columns, and raw contract before creating a DuckDB file.
It performs no HTTP requests and never modifies the manifest or blob.

Run a local snapshot load from the repository root:

```powershell
uv run python -m kidney_care_mart.stage.cms_om_gv `
  --manifest data/raw/manifests/cms_om_gv/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<run-id>.duckdb
```

The database contains required source columns as text in `raw.cms_om_gv` and
one lineage record in `raw.cms_om_gv_load_audit`. Publication uses a temporary
database on the same volume and a no-overwrite hard link. Repeating the same
manifest/database pair is an idempotent no-op; different lineage at the same
database path is a blocking conflict.

Copy the credential-free profile example, point it at that run-scoped database,
and build the typed stage:

```powershell
Copy-Item analytics/profiles.example.yml analytics/profiles.yml
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<run-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics
```

`analytics/profiles.yml`, generated dbt targets/logs, and DuckDB files are
ignored. The deterministic fixture path requires no local snapshot:

```powershell
uv run pytest tests/integration/test_cms_om_gv_dbt.py
```

The typed stage grain is one five-character county FIPS by CMS calendar year.
It selects exact County + All rows, excludes the anchored `UNKNOWN` source
representation and territory prefixes, and preserves leading-zero FIPS. The
one explicit exception maps only State `DC` / code `11` / All to county-
equivalent `11001`, while retaining the State source fields and mapping method;
an ordinary County `11001` appearing simultaneously is a blocking ambiguity.
Each required metric retains its
raw string, fixed-point typed value, and one status: `reported`, `suppressed`,
`unavailable_blank`, `unavailable_na`, or the build-blocking
`invalid_numeric`. Rates and percentages retain their source scale and are not
aggregated in staging.

### Raw geography-code exception

The bounded current sample confirms `BENE_GEO_CD=""` for the National row. CMS also emits the same empty code for distinct State pseudo-rows `Territory` and `ZZ`. The raw transport grain therefore includes `BENE_GEO_DESC`, and the contract accepts an empty geography code only in those source contexts. Duplicate complete raw grains still block publication. County and ordinary State rows require a nonblank code. The live full file supplies DC as a State row rather than a County row, so Plan 006 owns the exact, audited State-to-`11001` exception. State and National + All rows are now staged separately as authoritative benchmarks; territory and pseudo-state rows are excluded.

### Combined dimensions, facts, and reconciliation

`kidney_care_mart.stage.build_inputs` accepts one CMS v2 manifest and one SVI
v1 manifest beneath the same raw root. It reuses the two source loaders only in
private paths, copies both verified raw relations and audits with one DuckDB
writer, adds `raw.build_input_audit`, reconciles row/page counts, and publishes
the final database atomically. The audit preserves both contract versions,
manifest IDs, retrieval timestamps, hashes, and the deterministic source-set
hash. Same target plus identical evidence is a no-op; changed evidence or a
partial working path is a conflict.

The governed models are:

| Model | Grain | Vintage, denominator, and lineage |
|---|---|---|
| `dim_year` | One loaded CMS calendar year | Derived from the union of county and benchmark fact years; latest year is the loaded maximum. |
| `dim_county` | One exact five-character FIPS identity | 3,144 current SVI 2022 identities plus 11 reviewed historical CMS-only identities. Current rows retain SVI manifest/hash lineage; historical rows retain seed version and explicit boundary warning. |
| `fct_medicare_county_year` | County FIPS x CMS year | Source-reported CMS counts, 0-to-1 proportions, rates per 1,000, dollars per beneficiary, statuses, DC mapping method, and CMS manifest/hash lineage. |
| `fct_medicare_benchmark_year` | Benchmark type x key x CMS year | Exact State/National + All source rows and CMS lineage. No county rate or percentage is aggregated. |
| `fct_svi_county` | County FIPS x SVI vintage | Static SVI 2022 ranks and contextual percentages with their distinct source denominators and SVI manifest/hash lineage. |
| `audit_cms_svi_county_reconciliation` | Unioned latest-current county FIPS | Full-outer CMS/SVI presence and row counts plus both vintages and source hashes. Any non-`matched` status blocks the build. |

The historical identity seed contains exact source labels and observed CMS year
bounds for `02261`, `02270`, the eight pre-2022 Connecticut county FIPS, and
`46113`. These keys remain inactive and separate. The seed deliberately has no
successor FIPS, fuzzy match, allocation, or longitudinal bridge.

T-011 checks only rows where both reported counts exist and rejects a dialysis-
user count above `BENES_OM_CNT`. It does not infer suppressed counts or demand
equality between a count and a rounded reported share.

### Missingness, denominator, and interpretation

- Read CSV/API values as raw strings at the contract boundary so leading zeros, `*`, blank, `NA`, and numeric zero remain distinct.
- The dictionary states that `*` suppresses variables where the beneficiary or user count is below 11. The current table metadata declares blank as missing, and `NA` appears in the bounded API sample.
- Percentage-labelled fields are represented as decimal proportions in the current sample; preserve that source scale until governed typing occurs.
- `OP_DLYS_MDCR_STDZD_PYMT_PC` adjusts for geographic payment-rate differences, not beneficiary health status.
- This source describes observed outpatient dialysis use among Original Medicare beneficiaries. It does not establish kidney disease prevalence, unmet need, disease burden, or an intervention or site-selection recommendation.

## `cdc_svi_county_2022` - CDC/ATSDR SVI 2022 U.S. county data

**Contract status:** Source-to-fact path verified 2026-08-14 against the
official CDC/ATSDR documentation and county layer, including complete ordered
pagination, immutable exact-page publication, manifest-driven loading, and
typed county models.

| Attribute | Contract |
|---|---|
| Durable identity | ArcGIS service item `f2af3fd35858443293b75d5f73c7d4d3`, layer 1 |
| Official documentation | `https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html` |
| Official service | `https://services3.arcgis.com/ZvidGQkLaDJxRSJ2/ArcGIS/rest/services/CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer` |
| County layer | `SVI2022 US county`; object ID `GRASP_ID` |
| Source vintage | SVI 2022, based on 2018-2022 ACS data; static context rather than a 2024 or 2026 observation |
| Source grain | One row per five-character `STCNTY` county FIPS; `GRASP_ID` is a transport ordering key, not the analytical key |
| Geographic scope | The 50 states and District of Columbia; District of Columbia is `11001`; territory prefixes `60`, `66`, `69`, `72`, and `78` are excluded from the MVP |
| Ranking denominator | `RPL_THEMES` and `RPL_THEME1` through `RPL_THEME4` are U.S.-based county percentile ranks on `[0,1]` when available |
| Access | Public ArcGIS REST metadata and queries without authentication |
| Lineage | Official documentation -> pinned PDF and hash; official service item -> layer metadata and count -> exact ordered attribute pages and canonical manifest -> raw relation -> typed stage -> county dimension and SVI fact |

The live metadata exposes 161 fields: 77 doubles, 55 integers, 21 small
integers, seven strings, and one object ID. The executable contract requires 17
fields and treats the other 144 observed fields as compatible additions that
must be reported. The required fields are the geography/audit fields `ST`,
`STATE`, `ST_ABBR`, `STCNTY`, `COUNTY`, and `GRASP_ID`; the overall and four
theme ranks `RPL_THEMES` and `RPL_THEME1` through `RPL_THEME4`; and six
plain-language context fields `EP_POV150`, `EP_UNINSUR`, `EP_AGE65`,
`EP_DISABL`, `EP_LIMENG`, and `EP_NOVEH`.

The selected percentage fields deliberately retain separate source-defined
denominators:

| Field | Unit | Source-defined denominator or source field |
|---|---|---|
| `EP_POV150` | Percent | Population represented by `S1701_C01_001E` |
| `EP_UNINSUR` | Percent | Total civilian noninstitutionalized population |
| `EP_AGE65` | Percent | Total population in the source `S0101` percentage |
| `EP_DISABL` | Percent | Civilian noninstitutionalized population |
| `EP_LIMENG` | Percent | Persons age 5 and older represented by `B16005_001E` |
| `EP_NOVEH` | Percent | Households in the source `DP04` percentage |

These percentages are contextual measures with different denominators. They
must not be summed, averaged into a new score, used to alter the screening
quadrant, or interpreted as clinical or causal evidence. `RPL_THEMES` is the
transparent social-vulnerability component used by the Plan 007 screening
model. This source contract does not classify its `0.75` boundary; the
downstream screen classifies a reported value at or above the boundary as
higher social vulnerability.

### Paginated extraction and immutable lineage

Run the explicit live operation from the repository root; it is separate from
pytest and default pull-request checks:

```powershell
uv run python -m kidney_care_mart.extract.cdc_svi_county_2022 `
  --run-id cdc-svi-2022-live-<UTC timestamp> `
  --output-root data/raw
```

The extractor first validates the exact official layer metadata and a
count-only query. It then requests only the 17 required fields, disables
geometry, orders by `GRASP_ID ASC`, and uses deterministic offsets no larger
than the verified 2,000-row limit. Exact JSON response bytes are stored at
`data/raw/blobs/sha256/<page-sha256>.json`; one canonical manifest is published
at `data/raw/manifests/cdc_svi_county_2022/<run-id>.json` only after every page,
global ID/FIPS ordering, count, and path invariant reconciles.

Each page entry records its offset, requested limit, rows, bytes, hash, and
relative blob path. The manifest also records the official source/layer and
schema identities, field projection, source vintage and modification time,
count result, aggregate row/key checks, ordered page hashes, and
`snapshot_sha256`. Publication is atomic and no-overwrite. A verified page can
be reused by content hash, a new run of the unchanged source records a content
no-op, and conflicting or corrupt existing artifacts block progress.

### SVI raw-to-stage and county models

Load an already downloaded manifest without network access:

```powershell
uv run python -m kidney_care_mart.stage.cdc_svi_county_2022 `
  --manifest data/raw/manifests/cdc_svi_county_2022/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<run-id>.duckdb
```

The loader independently verifies canonical manifest bytes, all page bytes and
hashes, page envelopes, global counts, ordering, FIPS, and snapshot identity.
It writes the 17 required attributes as raw text to
`raw.cdc_svi_county_2022`, retaining JSON numeric-token spelling and nulls,
plus manifest, snapshot, and page lineage. Its audit relation records the
reconciled load. Database publication is atomic, an identical load is a no-op,
and conflicting lineage cannot overwrite an existing path.

Build the typed stage and its downstream county models with the local profile:

```powershell
Copy-Item analytics/profiles.example.yml analytics/profiles.yml
$env:KIDNEY_CARE_DUCKDB_PATH = (Resolve-Path `
  "data/staging/<run-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics `
  --select stg_cdc_svi_county_2022+
```

`stg_cdc_svi_county_2022` has one row per five-character county FIPS for SVI
vintage 2022. Every selected rank and percentage retains its raw token, a
fixed-point typed value, and a status: `reported`, `unavailable_sentinel`,
`unavailable_null`, or build-blocking `invalid_numeric`. The sentinel `-999`
and JSON null become typed nulls with distinct statuses; numeric zero remains
reported zero. Ranks must be null or `[0,1]`, and percentages must be null or
`[0,100]`.

The current portion of `dim_county` has one row per SVI county FIPS with SVI
geography labels and source provenance; Plan 006 appends only the 11 reviewed
historical CMS identities. `fct_svi_county` remains one row per current county FIPS x SVI vintage
and preserves the five ranks, six contextual percentages, status fields,
source-defined denominator labels, and manifest/snapshot lineage. These models
provide contextual facts only; facility characteristics, future Medicare facts,
and screening decisions do not alter this fact.

### Dated live source-to-fact evidence and deferred cross-source work

On 2026-08-14, the layer advertised a maximum of 2,000 records per response and
support for pagination and ordered queries. A count-only query returned 3,144
rows. Tiny two-row, geometry-free samples at offsets 0 and 2,000 preserved FIPS
`01001`, `01003`, `38017`, and `38019`. A separate reduced scan requested only
`GRASP_ID`, `ST`, and `STCNTY` in ascending object-ID order. Its two pages held
2,000 and 1,144 records; all 3,144 FIPS and object IDs were distinct; object IDs
ran strictly from 1 through 3,144; District of Columbia `11001` was present;
and no state-prefix mismatch or territory row appeared. These observations are
dated evidence for the examined static snapshot, not timeless constants.

The pinned 17-page official PDF is 542,647 bytes with SHA-256
`5636ae52e13ec201b90f4a31b55d12959d55784469e8c11662b64c03f09424fc`.
The complete ordered field labels and types, 17-field semantic mapping, 144
additions, exact locators, retrieval timestamp, layer edit timestamp, document
provenance, and canonical schema hash are recorded in
`docs/source-schemas/cdc_svi_county_2022.schema.json`.

The official `-999` value means that data were unavailable or could not be
calculated because source Census data were unavailable. The source-to-fact
path preserves the raw sentinel distinctly from numeric zero, then represents
it as a typed null with `unavailable_sentinel` status.

On 2026-08-14, the production extractor saved two complete pages: 2,000 rows
and 635,389 bytes, then 1,144 rows and 365,449 bytes. Their hashes were
`06b724e33bb61b4d3cd5996ce3b12a122e3de38807e84b3c7fe5a58541d377eb`
and
`62376e01a8197cc1772e78f2eda9b47b40ec4ac0f78ccd86b7525d6cd669ccf5`;
the ordered snapshot hash was
`51c2fbc79ddf9eb5a2f71480bde151f5b4e4e2d0494c2e780baa557e7014a2ee`.
A separately loaded database and SVI dbt selection produced 3,144 rows in the
raw relation, stage, dimension, and fact with 73 passing results. A second run
reused both pages and recorded a content no-op. These are dated observations,
not timeless constants. No full source rows, geometry, manifest, or generated
database are committed.

Plan 006 completes pinned CMS-to-SVI geography reconciliation T-014 and the CMS
fact/benchmark models. Plan 007 applies the `RPL_THEMES >= 0.75` component only
after the source fact passes its own contracts. This source fact does not
itself classify, rank, or recommend counties.

## Derived transparent county screening mart

Plan 007 adds a derived, run-scoped screening layer without changing either
source contract. Its candidate grain is one row per build input set × latest
CMS year × current reconciled county FIPS. It uses exactly two components:

| Component | Denominator and vintage | Fixed boundary |
|---|---|---|
| `BENES_OP_DLYS_PCT` | CMS source-defined Original Medicare beneficiary denominator; latest governed CMS year | National continuous county P75 among current, reported, nonnull county values; equality is higher use |
| `RPL_THEMES` | CDC/ATSDR SVI 2022 static U.S. county percentile rank | `0.75`; equality is higher social vulnerability |

The P75 is not an official CMS State or National benchmark and is never
recalculated after a user filters the mart. Suppressed, unavailable, or invalid
inputs never become zero. Rows with both components map to exactly one of
`higher_use_higher_vulnerability`, `higher_use_lower_vulnerability`,
`lower_use_higher_vulnerability`, or `lower_use_lower_vulnerability`; all other rows are
`insufficient_data` with a coarse source-availability reason. The five-category
audit summary reconciles to the candidate county total, including zero-count
categories.

This layer describes observed outpatient dialysis use among Original Medicare
beneficiaries alongside social-vulnerability context. It is not a clinical or
causal measure, prevalence estimate, composite score, rank, recommendation, or
automated decision. Facility data, once added, are due-diligence context only
and may not change these classifications. Exact metric definitions and dated
pinned results are in [`metric-dictionary.md`](metric-dictionary.md).
