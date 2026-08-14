# Source catalog

## `cms_om_gv` - CMS Original Medicare Geographic Variation

**Contract status:** Verified 2026-08-13 against the official CMS catalog, current data-viewer metadata, a bounded API sample, and the pinned 2014-2024 data dictionary.

| Attribute | Contract |
|---|---|
| Durable identity | CMS dataset `6219697b-8f6c-4164-bed4-cd9317c58ebc` |
| Official catalog | `https://data.cms.gov/data.json` |
| Official landing page | `https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-comparisons/medicare-geographic-variation-by-national-state-county` |
| Stable latest API | `https://data.cms.gov/data-api/v1/dataset/6219697b-8f6c-4164-bed4-cd9317c58ebc/data` |
| Current source vintage | Calendar years 2014-2024; catalog modified 2026-05-15 |
| Raw transport grain | `YEAR x BENE_GEO_LVL x BENE_GEO_DESC x BENE_GEO_CD x BENE_AGE_LVL` using CMS's raw geography-code representation |
| Primary county denominator | Original Medicare beneficiaries (`BENES_OM_CNT`) after later County + All filtering; this contract does not filter or calculate metrics |
| Primary screening field | `BENES_OP_DLYS_PCT`, observed outpatient dialysis use among Original Medicare beneficiaries |
| Access | Public CSV/API without authentication |
| Lineage | Official catalog -> stable dataset identity -> current API/data-viewer metadata and resolved version distribution; field definitions -> pinned official dictionary |

The version-specific CSV URL is retained only as observed provenance in the normalized schema snapshot. Resolution must begin with the official catalog or stable dataset identity; code must not treat that distribution URL as the durable locator.

The current metadata exposes 246 columns: 242 `NUMERIC` and four `TEXT`. The executable contract requires 13 fields and treats the other 233 observed fields as additive. Exact labels, definitions, declared types, full observed order, additive fields, type encoding, and hashes are recorded in `docs/source-schemas/cms_om_gv.schema.json`.

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
  --run-id cms-om-gv-live-<UTC timestamp> `
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

### Raw geography-code exception

The bounded current sample confirms `BENE_GEO_CD=""` for the National row. CMS also emits the same empty code for distinct State pseudo-rows `Territory` and `ZZ`. The raw transport grain therefore includes `BENE_GEO_DESC`, and the contract accepts an empty geography code only in those source contexts. This correction was confirmed during the 2026-08-14 full-file live check after the narrower key correctly blocked as duplicated; duplicate complete raw grains still block publication. County and ordinary State rows require a nonblank code. County FIPS typing, scope filtering, District of Columbia handling, and removal of `UNKNOWN` pseudo-counties remain later transformation responsibilities.

### Missingness, denominator, and interpretation

- Read CSV/API values as raw strings at the contract boundary so leading zeros, `*`, blank, `NA`, and numeric zero remain distinct.
- The dictionary states that `*` suppresses variables where the beneficiary or user count is below 11. The current table metadata declares blank as missing, and `NA` appears in the bounded API sample.
- Percentage-labelled fields are represented as decimal proportions in the current sample; preserve that source scale until governed typing occurs.
- `OP_DLYS_MDCR_STDZD_PYMT_PC` adjusts for geographic payment-rate differences, not beneficiary health status.
- This source describes observed outpatient dialysis use among Original Medicare beneficiaries. It does not establish kidney disease prevalence, unmet need, disease burden, or an intervention or site-selection recommendation.
