# Environment and source preflight

**Record date:** 2026-08-13  
**Status:** Gate 0 in progress; local bootstrap and first CMS source contract verified

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
| CDC/ATSDR SVI 2022 U.S. county data | Yes | Pending | Official CSV or deterministic REST pagination returns the pinned 3,144-row county snapshot, with distinct FIPS. |
| Census Geocoder | Conditional | Pending | A sample or batch request succeeds for unresolved public facility business addresses. |

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
