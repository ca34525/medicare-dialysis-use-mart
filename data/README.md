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

Do not commit downloaded source files, generated manifests, DuckDB databases,
Parquet outputs, credentials, or patient information. Tests use only the small
representative fixtures under `tests/fixtures/`.
