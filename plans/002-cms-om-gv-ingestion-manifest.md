# Plan 002: CMS Geographic Variation extraction and immutable raw manifests

**Status:** Completed 2026-08-14
**Source ID:** `cms_om_gv`  
**Depends on:** Completed Plan 001 source contract  
**Specification coverage:** Milestone 1; T-003 and T-004 for the CMS full-file
transport  
**Authoritative requirements:** `specs.md` sections 5.1-5.4, 9, 10, 11,
12, 14, 15, and 20

## Outcome

Build the first production-shaped ingestion path. It will resolve the current
official CMS Geographic Variation CSV from durable CMS metadata, download it to
a temporary file, validate it with the existing source contract, and publish an
immutable content-addressed raw blob plus a run-scoped manifest.

The flow is:

```text
official CMS catalog
        |
        v
resolve one stable dataset and its current CSV
        |
        v
download to a same-volume temporary file
        |
        v
verify bytes, rows, schema, grain, and SHA-256
        |
        v
publish immutable blob + run manifest atomically
```

This step moves the project from “we know what the source must look like” to
“we can reproduce exactly which source bytes a later build used.” It does not
yet type metrics, normalize missing values, filter county rows, build DuckDB or
dbt models, or calculate observed outpatient dialysis use among Original
Medicare beneficiaries.

## Why this is the natural next step

Plan 001 established the source labels, declared types, grain keys, and
compatibility rules. A transformation built directly against a live URL would
still be irreproducible: the upstream file can change, a failed transfer can be
mistaken for a complete file, and a later analyst cannot prove which bytes were
used.

The raw snapshot and manifest are therefore the smallest dependency required
before typing and dimensional modeling. They also establish reusable ingestion
behavior needed by the facility and SVI sources without prematurely creating a
large extraction framework.

## Scope decisions

### Included

- Resolve stable dataset ID `6219697b-8f6c-4164-bed4-cd9317c58ebc` from the
  official CMS catalog.
- Prefer the complete official CSV distribution, as required by `specs.md`.
- Apply a descriptive user agent, bounded connect/read timeouts, and bounded
  retry with exponential backoff and jitter for transient HTTP failures only.
- Stream the response to disk while calculating byte count and SHA-256.
- Validate response length when CMS supplies `Content-Length`.
- Reconcile CMS metadata, the actual CSV header, required declared types,
  additive fields, row count, and all raw grain keys before publication.
- Reuse the existing `cms_om_gv` contract rather than redefining its fields.
- Publish a content-addressed raw blob and a canonical run manifest using
  same-volume temporary paths and atomic renames.
- Make same-content and same-run reruns deterministic and safe.
- Add deterministic, network-free tests for success, retries, truncation,
  schema failure, reconciliation failure, and idempotency.
- Provide a separate explicit live-source command and document its evidence.

### Excluded

- Metric typing or missingness normalization for `*`, blank, or `NA`.
- County FIPS normalization, County + All filtering, `UNKNOWN` removal, or the
  District of Columbia mapping.
- DuckDB, dbt, Parquet, screening metrics, SVI, facilities, Airflow, or Power
  BI.
- The `latest-successful-run` pointer; that pointer is updated only after the
  later complete build passes every publication gate.
- A multi-source plugin framework or automatic fallback to an unverified URL.
- Multi-page API completion claims for the facility and SVI sources. For this
  nonpaginated CMS CSV, T-003 is scoped to a complete one-response transfer
  with `page_count = 1`; multi-page overlap and termination behavior will be
  completed with the first genuinely paginated source.

## Invariants

- Begin resolution with the official CMS catalog or stable dataset identity.
  A version-specific distribution URL may be recorded as lineage but is never
  the only locator in code.
- A catalog lookup must produce exactly one matching dataset. Zero or multiple
  matches are blocking failures.
- Downloaded bytes remain unchanged. Validation may read the file but must not
  rewrite, normalize, or reserialize it.
- All CSV values remain raw strings at this boundary. In particular, leading
  zeros, suppression tokens, blanks, `NA`, and numeric zero remain distinct.
- Required-column removal, duplicate headers, incompatible required types,
  malformed grain keys, truncated content, or reconciliation failure blocks
  publication.
- Additive columns are compatible, reported in the result and manifest, and do
  not silently become required.
- Retry only transport failures that are plausibly transient. Contract,
  parsing, schema, and data-quality failures fail immediately.
- Final raw blobs and manifests are immutable. Existing final files are never
  overwritten to make a rerun succeed.
- A failed run cannot change a prior raw blob, prior manifest, or any published
  mart state.
- The default pytest path performs no external network requests.
- Full raw data and generated manifests remain ignored by Git.

## Generated storage layout

Use separate immutable blobs and run-scoped references so repeated content does
not create duplicate raw files while each run retains its own lineage:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       `-- <content-sha256>.csv
|-- manifests/
|   `-- cms_om_gv/
|       `-- <run-id>.json
`-- .tmp/
    `-- <run-id>/
```

`data/raw/` is generated and ignored. Only a short tracked `data/README.md` and
optional `.gitkeep` should document the layout.

The blob path depends only on the content hash. A manifest belongs to a logical
pipeline run and references that blob by relative path and hash. If a later run
downloads identical bytes, it reuses the verified blob and writes a new
run-scoped manifest with `content_noop: true`.

## Manifest contract

Write canonical UTF-8 JSON with sorted keys, stable list ordering, and a final
newline. The manifest must contain at least:

- manifest format version;
- logical source ID;
- pipeline run ID and extractor version;
- official catalog URL, landing URL, stable dataset ID, and resolved current
  CSV URL;
- retrieval timestamp in UTC;
- source release or modified date;
- HTTP ETag and Last-Modified when present;
- content SHA-256 and byte count;
- CSV data-row count, excluding the header;
- transport mode `full_csv`, `page_count: 1`, and record count;
- ordered source columns and CMS-declared types;
- deterministic typed-schema hash;
- deterministic actual-header hash;
- required contract version or schema-evidence hash;
- sorted additive columns;
- relative content-addressed blob path; and
- whether the content already existed and was reused.

Define both schema hashes precisely in code and tests:

1. `schema_hash`: SHA-256 of canonical JSON containing the ordered
   `{name, declared_type}` metadata pairs.
2. `header_hash`: SHA-256 of canonical JSON containing the ordered raw CSV
   header labels.

The distinction is necessary because CSV headers do not carry types. A total
schema hash change is evidence to report, not by itself a failure; compatibility
is decided by the required-field contract.

## Planned repository artifacts

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/extract/__init__.py` | Small extraction package boundary. |
| `src/kidney_care_mart/extract/http.py` | Bounded HTTP request, retry classification, and streamed download behavior. |
| `src/kidney_care_mart/extract/manifest.py` | Immutable manifest model, canonical hashing, reconciliation, and atomic publication. |
| `src/kidney_care_mart/extract/cms_om_gv.py` | CMS catalog resolution and source-specific extraction orchestration. |
| `tests/fixtures/cms_om_gv/catalog.json` | Minimal official-shaped catalog fixture with one intended dataset. |
| `tests/fixtures/cms_om_gv/download.csv` | Small raw CSV download fixture; no real full source data. |
| `tests/unit/extract/test_http.py` | Retry, timeout, streaming, and truncation tests. |
| `tests/unit/extract/test_manifest.py` | Canonical manifest, reconciliation, atomicity, and idempotency tests. |
| `tests/unit/extract/test_cms_om_gv.py` | Resolver and end-to-end fixture extraction tests. |
| `data/README.md` | Tracked explanation of ignored generated raw storage. |
| `docs/source-catalog.md` | Command and extraction-lineage documentation. |
| `docs/preflight.md` | Dated, bounded live extraction result and limitations. |

Do not add an HTTP dependency merely for convenience. The Python standard
library is adequate for this bounded first extractor. If implementation proves
otherwise, stop, write the required architecture decision record, update the
lockfile, and run the full quality loop before continuing.

## Red-green-refactor execution sequence

### 1. Define deterministic seams

Before adding live behavior, define narrow injected interfaces for:

- retrieving parsed catalog metadata;
- opening a streaming response;
- sleeping between retries;
- supplying jitter and current UTC time; and
- choosing the generated output root.

Production defaults use the standard library. Tests use in-memory or temporary
fake responses, clocks, and sleepers. Tests must never patch global networking
or contact CMS.

### 2. Test catalog resolution first

Add failing tests proving that the resolver:

1. selects exactly the stable dataset ID and corroborates its title or landing
   page;
2. selects the current full CSV distribution rather than a transient sample;
3. retains the catalog and landing URLs as durable lineage;
4. fails on zero intended matches;
5. fails on multiple intended matches;
6. fails when no usable official CSV distribution exists; and
7. never accepts a caller-supplied arbitrary download URL as the source of
   truth.

Implement only the CMS-specific resolver needed to pass those tests.

### 3. Test bounded download behavior

Add the smallest failing tests for:

1. streaming several chunks without loading the complete response into memory;
2. exact SHA-256 and byte-count calculation;
3. propagation of ETag and Last-Modified headers;
4. failure when received bytes disagree with `Content-Length`;
5. bounded retry for connection failures, timeouts, HTTP 408, HTTP 429, and
   HTTP 5xx responses;
6. no retry for ordinary HTTP 4xx responses;
7. deterministic backoff assertions through injected sleep and jitter; and
8. cleanup of the temporary file after an interrupted or exhausted transfer.

Use a small maximum-attempt count and cap the delay. Every request includes a
descriptive user agent and explicit timeout.

### 4. Test raw-file validation and reconciliation

Use the representative CSV fixture and add failing tests showing that:

1. the actual header has no duplicates;
2. the existing contract accepts all required fields and reports additives;
3. required CMS declared types remain compatible;
4. every data row has parseable raw grain keys under the Plan 001 exceptions;
5. CSV row count is deterministic and excludes the header;
6. embedded delimiters or quoted newlines do not corrupt row counting;
7. actual header labels reconcile to the resolved metadata;
8. schema and header hashes match their canonical algorithms; and
9. any contract, CSV, grain, or reconciliation issue blocks final publication.

Keep the validation streaming or iterator-based. The current source is small,
but correctness does not require loading the full table into memory.

### 5. Test the manifest and atomic publication

Add failing tests proving that:

1. canonical manifest serialization is byte-for-byte deterministic;
2. the manifest reconciles to the staged blob's hash, byte count, row count,
   schema hash, and header hash;
3. a valid temporary blob is atomically moved to its content-addressed path;
4. the manifest is published only after blob and contract validation succeed;
5. a failed validation leaves no final manifest and does not modify earlier
   artifacts;
6. a later run with the same content reuses the verified blob;
7. rerunning the same run ID with the same manifest is a successful no-op;
8. rerunning the same run ID with different content or lineage fails instead
   of overwriting history;
9. an existing blob whose bytes do not match its filename hash is a blocking
   integrity failure; and
10. invalid run IDs cannot escape the generated manifest directory.

Use temporary directories in tests and atomic replacement only within the same
filesystem volume.

### 6. Assemble the source-specific extractor

Implement one orchestration function that:

1. validates the run ID;
2. resolves current official metadata;
3. validates the CMS-declared schema;
4. downloads to a run-scoped temporary file;
5. validates the actual raw CSV and all grain keys;
6. computes and reconciles manifest evidence;
7. publishes or reuses the immutable blob;
8. publishes the run manifest; and
9. returns a structured result with status, paths, hashes, counts, additives,
   retry count, and `content_noop`.

Provide an explicit module command, for example:

```powershell
uv run python -m kidney_care_mart.extract.cms_om_gv `
  --run-id cms-om-gv-20260814T120000Z `
  --output-root data/raw
```

The command is a live-source operation and must not run from `pytest` or the
default pull-request checks.

### 7. Document and verify

1. Document the generated storage layout and why raw files are ignored.
2. Update the source catalog with the extraction command and manifest fields.
3. Run one explicitly invoked live extraction after all offline tests pass.
4. Recalculate the saved file hash, bytes, rows, and schema from disk and prove
   they match the manifest.
5. Run the same live command under a new run ID and verify blob reuse if CMS
   content is unchanged.
6. Record only concise evidence in `docs/preflight.md`; do not commit the raw
   CSV, generated manifest, response body, or a transient signed URL.
7. Check Git status and `git check-ignore` before handoff.

## Verification commands

Focused red-green loop:

```powershell
uv run pytest tests/unit/extract
uv run ruff format --check src tests
uv run ruff check src tests
```

Required offline handoff loop:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Explicit live check, only after offline verification:

```powershell
uv run python -m kidney_care_mart.extract.cms_om_gv `
  --run-id cms-om-gv-live-<UTC timestamp> `
  --output-root data/raw
```

The live check must remain separate from the default test suite.

## Acceptance criteria

- [x] Official catalog resolution returns exactly the stable intended dataset
  and one usable current full CSV.
- [x] Production code has no hard-coded version-specific CSV as its sole
  locator.
- [x] A valid fixture extraction publishes one content-addressed blob and one
  canonical run manifest.
- [x] The raw bytes are unchanged from the completed response.
- [x] Content hash, byte count, row count, schema hash, header hash, and blob
  path reconcile exactly.
- [x] Required schema and grain failures block publication; additive columns
  pass and are reported.
- [x] Truncated or interrupted transfers cannot create a final blob or
  manifest.
- [x] Retry is bounded and limited to transient transport failures.
- [x] Same-content and same-run behavior is idempotent without overwrites.
- [x] T-003 passes for the CMS full-file, one-response transport and is
  explicitly recorded as `page_count = 1`; no multi-page source claim is made.
- [x] T-004 passes for hash, bytes, rows, and schema reconciliation.
- [x] Offline tests make zero external requests.
- [x] A separate live extraction succeeds and its manifest is independently
  reconciled from disk.
- [x] Generated raw data and manifests are ignored and absent from Git status.
- [x] Ruff and the complete pytest suite pass from the locked environment.

## Stop conditions

Stop and request a specification or architecture decision if:

- the stable dataset is missing or resolves ambiguously;
- the catalog no longer exposes a complete official CSV;
- CMS metadata and the CSV disagree on a required label or type;
- the source introduces duplicate headers or an incompatible required type;
- a correct complete-transfer check cannot be implemented without changing the
  selected transport;
- a new runtime dependency is necessary;
- the generated path would escape the configured output root;
- an existing content-addressed blob fails integrity verification;
- live access now requires authentication, payment, or nonpublic data; or
- bounded live attempts cannot distinguish an upstream failure from a local
  network restriction.

Do not silently switch to a different source, weaken the contract, overwrite an
immutable artifact, infer missing bytes, or record a failed download as a
successful snapshot.

## Handoff

After this plan is implemented, the next dependency-ordered step is the
`cms_om_gv` raw-to-stage transformation covering T-005 through T-007: preserve
five-character county FIPS, type CMS missingness with distinct statuses, select
County + All rows, exclude `UNKNOWN`, and map the District of Columbia to
`11001`. That later plan must consume the immutable manifest and raw blob
rather than contacting CMS directly.

## Completion record

- Added standard-library catalog/data-viewer resolution, bounded JSON and CSV
  transport, transient-only retry, unchanged-byte streaming, and cleanup of
  failed partial transfers.
- Added streaming raw validation for exact ordered headers, compatible declared
  types, logical row counts, parseable and unique raw grains, additive columns,
  CMS metadata byte/SHA-1 reconciliation, and separate canonical schema/header
  hashes.
- Added atomic no-overwrite publication for SHA-256 blobs and canonical
  run-scoped manifests, including verified content reuse, same-run idempotency,
  conflict detection, corrupt-blob blocking, and path traversal protection.
- Added 49 network-free extraction tests. The complete locked suite contains
  104 passing tests; Ruff formatting and lint gates pass.
- The 2026-08-14 live check published the 57,865,948-byte, 36,994-row source at
  SHA-256 `10c8304012da34da3ecfe4caf4548927095f693383814d0e79ce6711b6806fad`.
  A second run reused the single blob and wrote a second manifest with
  `content_noop: true`; independent disk reconciliation matched all evidence.
- The live duplicate-key gate exposed and explicitly corrected the raw-grain
  definition: CMS reuses a blank State code for distinct `Territory` and `ZZ`
  rows, so the transport grain includes `BENE_GEO_DESC`. No duplicate-key rule
  was weakened, and the downstream county fact grain is unchanged.
