# Generated data layout

This directory is the local boundary for generated source snapshots and later
published mart artifacts. Generated contents are intentionally ignored by Git;
only this explanation is version controlled.

The CMS Original Medicare Geographic Variation extractor writes:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       `-- <content-sha256>.csv
|-- manifests/
|   `-- cms_om_gv/
|       `-- <pipeline-run-id>.json
`-- .tmp/
    `-- <pipeline-run-id>/
```

Downloads first land beneath the run-scoped `.tmp` directory. Contract, grain,
byte-count, row-count, and hash checks must all pass before a file is published
under its SHA-256 identity. A run manifest is published only after its blob is
verified. Existing blobs and manifests are never overwritten; identical source
content is reused and recorded as a content no-op.

The CMS Dialysis Facility extractor shares the content-addressed CSV blob
directory and uses its own source-specific manifest namespace:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       `-- <content-sha256>.csv
|-- manifests/
|   `-- cms_dialysis_facility/
|       `-- <pipeline-run-id>.json
`-- .tmp/
    `-- <pipeline-run-id>/
```

Its one-response full-file manifest records `page_count: 1`, the official
catalog/dataset/schema/dictionary lineage, ordered API and CSV fields, exact
schema and header hashes, compatible additions, byte and logical row counts,
distinct textual CCNs, leading-zero CCNs, and the safe relative blob path. The
manifest is not visible until the unchanged CSV bytes, ordered header, raw CCN
grain, API count, and all hashes reconcile. An identical later source snapshot
reuses the verified blob; it does not overwrite either run's immutable
manifest. Plan 008 creates no DuckDB relation or mart publication pointer.

The CDC/ATSDR SVI extractor uses the same generated-data boundary but retains
each exact ArcGIS response page separately:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       `-- <page-sha256>.json
|-- manifests/
|   `-- cdc_svi_county_2022/
|       `-- <pipeline-run-id>.json
`-- .tmp/
    `-- <pipeline-run-id>/
```

Its canonical manifest records the ordered offset, requested limit, exact byte
count, row count, page SHA-256, and relative path for every page. It also
records the count response, required projection, layer/schema identity, global
key checks, and an ordered `snapshot_sha256`. No manifest is published until
all pages reconcile. Verified identical pages are reused; a later run with the
same ordered snapshot records a content no-op without overwriting a blob.

The Plan 003 network-free loader writes one run-scoped DuckDB file only after a
manifest and its referenced blob reconcile:

```text
data/staging/
`-- <pipeline-run-id>.duckdb
```

The database contains `raw.cms_om_gv`, with required source values preserved as
text, and `raw.cms_om_gv_load_audit`, with the manifest lineage and reconciled
row count. An identical load is a no-op. A different manifest cannot overwrite
an existing database path. dbt adds the typed
`staging.stg_cms_om_gv_county_year` model to that same run-scoped database.

The SVI loader uses the same run-scoped database boundary and creates
`raw.cdc_svi_county_2022` plus `raw.cdc_svi_county_2022_load_audit`. Every page
is independently rehashed and reparsed before loading. Required ArcGIS
attributes remain text, including numeric JSON tokens and the raw `-999`
sentinel, and each row carries manifest, snapshot, and page lineage. dbt then
adds `staging.stg_cdc_svi_county_2022` and `staging.fct_svi_county`. The stage
converts `-999` and JSON null to typed nulls
with distinct statuses while reported numeric zero remains zero.

Plan 006 adds an atomic combined-input path:

```text
data/staging/
`-- <build-id>.duckdb
    |-- raw.cms_om_gv
    |-- raw.cms_om_gv_load_audit
    |-- raw.cdc_svi_county_2022
    |-- raw.cdc_svi_county_2022_load_audit
    `-- raw.build_input_audit
```

Both manifests and every referenced blob/page are independently verified in a
private working directory. The final database appears only after both raw
relations, both source audits, and the one-row build audit reconcile. The audit
records both contract versions, manifest runs, row/page counts, source hashes,
and a deterministic `input_set_sha256`. Same path plus same inputs is a no-op;
different inputs or an abandoned partial path are blocking conflicts.

dbt adds `staging.dim_year`, the 3,144-current-plus-11-historical
`staging.dim_county`, `staging.fct_medicare_county_year`, the authoritative
`staging.fct_medicare_benchmark_year`, and
`staging.audit_cms_svi_county_reconciliation`. Historical identities are
version-controlled metadata only: no successor FIPS, boundary allocation, or
trend bridge is generated.

Do not commit downloaded source files, generated manifests, DuckDB databases,
Parquet outputs, credentials, or patient information. Tests use only the small
representative fixtures under `tests/fixtures/`.
