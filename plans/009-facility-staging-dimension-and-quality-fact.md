# Plan 009: Facility staging, dimension, and quality snapshot fact

**Status:** Completed 2026-08-18  
**Depends on:** Completed Plans 001-008  
**Source ID:** `cms_dialysis_facility`  
**Raw contract:** `cms_dialysis_facility.raw.v1`  
**Authoritative requirements:** `specs.md` sections 3, 5.5, 6.3, 7-11,
14-18, and 20

## Outcome

Load one already-verified CMS Dialysis Facility manifest into DuckDB without
contacting CMS, preserve all 41 governed fields as raw strings, and build:

- `stg_cms_dialysis_facility` at one row per textual CCN and source snapshot;
- `dim_facility` at one row per textual CCN; and
- `fct_facility_quality_snapshot` at CCN x source-snapshot SHA-256.

The typed path interprets the official CMS availability codes, preserves raw
tokens, parses measurement periods, retains each source-specific denominator,
and keeps survival, hospitalization, and readmission estimates with their
confidence intervals. It proves T-012 and T-013 and reconciles the raw row
count through both final models.

This plan does not assign county FIPS, call the Census Geocoder, calculate a
county facility aggregate, enrich `mart_county_screening`, publish Parquet,
or change a screening quadrant.

## Why this is the next dependency

Plan 008 ended with this explicit handoff: load a verified facility manifest
as raw strings, build a typed facility stage, then create `dim_facility` and
`fct_facility_quality_snapshot` before attempting geography assignment.

That order is necessary because county mapping cannot safely aggregate a
facility whose CCN, capacity, modalities, availability, period, denominator,
estimate, or confidence interval has not first passed its own contract. It
also keeps facility context independent from the transparent screen of
observed outpatient dialysis use among Original Medicare beneficiaries and
static SVI 2022 context.

## Declared grains, denominators, vintage, and lineage

| Model | Grain | Denominator and vintage | Lineage |
|---|---|---|---|
| `raw.cms_dialysis_facility` | Textual CCN x one complete source snapshot | No derived metric; exact required CSV strings | Manifest run, full-CSV SHA-256, retrieval, release, modified date |
| `stg_cms_dialysis_facility` | Textual CCN x source snapshot | Survival/hospitalization use source patient counts; readmission uses index discharges; current quarterly release with separate measure periods | Raw lineage repeated on every row |
| `dim_facility` | Textual CCN | Current identity, public business location, ownership, chain, stations, modalities, and certification date | Facility snapshot and manifest lineage |
| `fct_facility_quality_snapshot` | Textual CCN x source-snapshot SHA-256 | Star rating has no outcome denominator; survival and hospitalization are rates per 100 patient-years; readmission is percent of hospital discharges | Facility snapshot, manifest, release, and retrieval lineage |

Public facility address, city, state, ZIP, county/parish label, and telephone
are business-location fields. They are not patient residence, patient origin,
service catchment, or a county assignment. ZIP is never a county key.

## Availability and typing contract

The pinned official dictionary's availability table defines `001` as data
available. The all-measure unavailability codes used here are:

| Code | Stable analytical reason |
|---|---|
| `199` | `insufficient_patients` |
| `201` | `data_not_reported` |
| `255` | `inaccurate_measure` |
| `258` | `insufficient_history` |
| `270` | `disaster_suppression` |
| `280` | `external_factors` |

The star rating additionally accepts `260`, `261`, and `281` for insufficient
star data, an inaccurate star component, and external factors specific to the
star rating. Codes documented only for surveys, modalities, or pediatric
measures are not silently accepted for these four governed measure surfaces.
An unknown or measure-incompatible code is `invalid` and blocks dbt.

Raw values remain in `raw.cms_dialysis_facility`. The stage also retains raw
station, modality, date, period, rating, category, denominator, estimate, and
interval tokens beside typed fields. A typed rating or outcome is exposed only
when its companion code is `001`; unavailable source tokens never become zero.
A reported zero remains zero.

Reported outcome categories normalize case-only source presentation to:

- `better_than_expected`;
- `as_expected`; and
- `worse_than_expected`.

The raw category text remains available for audit. No category is converted
to a score or provider rank.

## Product and safety boundaries

- Facility characteristics and quality measures are due-diligence context
  only and never alter the Plan 007 threshold, component flags, or quadrant.
- Do not average the three risk-standardized outcomes into a facility or
  county quality score.
- Do not rank providers, recommend a partnership, contract, site, or
  intervention, or make a clinical or causal claim.
- Do not infer missing values as zero or discard an availability code,
  denominator, measurement period, or confidence limit.
- Keep territories at the source/facility grain until the later geography
  policy decides their out-of-scope disposition; do not silently drop them in
  this plan.
- `dim_facility` exposes `geography_match_status = 'not_attempted'` and null
  county assignment fields so deferred work is visible rather than implied.

## Scope

### Included

- Network-free manifest/blob re-verification and atomic DuckDB loading.
- Raw-string preservation for all 41 required fields and complete lineage.
- Build-input format v2 with optional legacy fixture support in the Python API
  and a required facility manifest in the current CLI.
- Typed identity, capacity, ownership, modality, certification, star-rating,
  survival, hospitalization, and readmission fields.
- Source-defined availability interpretation and stable unavailability labels.
- Period parsing, source-specific denominators, category normalization,
  decimal estimates, and confidence intervals.
- T-012, T-013, key, lineage, reconciliation, and deterministic-output tests.
- A pinned, network-free full build from the already-downloaded 2026-08-15
  manifests.

### Excluded

- New live CMS, CDC, or Census requests.
- Exact county-name, alias, geocoder, or manual facility mapping.
- `quarantine_facility_geography`, national/state mapping coverage, T-015,
  county facility aggregation, stations per 10,000, and complete T-018/T-019.
- Any `mart_county_screening` facility columns or screening-logic change.
- Parquet publication, a latest-successful pointer, Airflow, CI expansion,
  Power BI, hosting, AWS, or a dependency change.

## Red-green-refactor execution record

1. A three-row synthetic staging fixture added a leading-zero CCN, reported
   zero, unavailable rating and outcome codes, source county edge text,
   modality flags, distinct periods, and complete denominators/intervals.
2. New raw-loader and dbt integration tests failed first because the facility
   staging module and dbt models did not exist.
3. The loader reuses the Plan 008 manifest verifier, bulk-loads only governed
   fields as text, writes a one-row audit, and publishes the DuckDB file
   atomically. Corrupt bytes cannot create a final database.
4. The dbt stage, dimension, fact, contracts, and named data tests implemented
   the minimum behavior needed for the fixture to pass.
5. Failure injection proves invalid ratings, missing or reversed confidence
   limits, reversed periods, and unknown availability codes block the build.
6. The pinned full build exposed CMS category capitalization not represented
   in the first fixture. The implementation was refactored to preserve raw
   category text and normalize exact semantic categories; the data test was not
   weakened.
7. The first full load also exposed slow row-wise facility insertion. The
   loader was refactored to DuckDB's bulk CSV scanner with an explicit null
   sentinel so empty strings remain raw empty strings.
8. The canonical suite exposed two-source compatibility regressions. A new
   deterministic test now proves that the optional Python compatibility path
   preserves build format v1 and its historical input hash, while the current
   three-source CLI path alone emits format v2. CMS/SVI lineage and facility/v2
   lineage remain separate blocking gates so partial selections cannot bypass
   either contract.

## Verification commands

Focused loop:

```powershell
uv run pytest `
  tests/unit/stage/test_cms_dialysis_facility_stage.py `
  tests/unit/stage/test_build_inputs.py `
  tests/integration/test_cms_dialysis_facility_dbt.py
uv run ruff format --check src tests
uv run ruff check src tests
```

Current three-source input and dbt build:

```powershell
uv run python -m kidney_care_mart.stage.build_inputs `
  --build-id <build-id> `
  --cms-manifest data/raw/manifests/cms_om_gv/<v2-run-id>.json `
  --svi-manifest data/raw/manifests/cdc_svi_county_2022/<run-id>.json `
  --facility-manifest `
    data/raw/manifests/cms_dialysis_facility/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<build-id>.duckdb
$env:KIDNEY_CARE_DUCKDB_PATH = `
  (Resolve-Path "data/staging/<build-id>.duckdb").Path
uv run dbt build --project-dir analytics --profiles-dir analytics
uv run dbt docs generate --project-dir analytics --profiles-dir analytics
```

Canonical offline handoff:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## Acceptance criteria

- [x] A verified facility manifest and exact blob load without network access.
- [x] All 41 required fields remain raw strings and textual CCNs retain leading
  zeros.
- [x] Raw, stage, dimension, and fact row counts reconcile one-to-one.
- [x] `dim_facility` is unique at textual CCN grain and visibly defers county
  assignment.
- [x] `fct_facility_quality_snapshot` is unique at CCN x snapshot SHA-256.
- [x] CMS availability code `001` governs reported values; documented
  unavailable codes remain explicit; unknown codes block.
- [x] Reported zero remains zero and unavailable source tokens do not become
  reported typed values.
- [x] T-012 blocks a reported star rating outside integer 1-5.
- [x] T-013 blocks incomplete or reversed confidence intervals and reversed or
  invalid periods.
- [x] Each outcome retains its own period, availability, category, denominator,
  estimate, lower limit, upper limit, unit, and lineage.
- [x] The three-source input-set hash includes facility content and contract
  identity.
- [x] The pinned 7,490-row full build passes all dbt gates and reproduces the
  same ordered semantic checksums on an immediate rebuild.
- [x] The Plan 009 guide is linked, network-free, accessible, and passes static
  plus rendered visual QA.
- [x] The canonical locked Ruff and complete pytest suite pass.
- [x] No dependency, live-source request, county assignment, screen change,
  generated database, raw source, secret, or patient information is committed.

## Goal-mode execution boundary

This plan is suitable for an unattended implementation goal. All required
source bytes already exist beneath ignored local storage. The work may read
those verified public snapshots, write generated ignored DuckDB/dbt artifacts,
edit repository code/tests/docs, and run deterministic checks. It may not make
an external request, install or change a dependency, call the Census Geocoder,
commit, push, publish, or perform a geography or screening expansion.

The execution goal is:

> Implement Plan 009 completely using red-green-refactor. Reverify and load one
> immutable facility manifest as raw strings; add the typed facility stage,
> one-row-per-CCN dimension, and CCN-by-snapshot quality fact; preserve exact
> availability, period, denominator, category, estimate, interval, and lineage
> semantics; prove T-012 and T-013 plus row/grain reconciliation and
> deterministic outputs; complete the Plan 009 guide and documentation; and
> run the canonical locked offline verification. Make no network request,
> dependency change, county assignment, screen change, publication, commit,
> push, provider ranking, score, recommendation, clinical claim, or causal
> claim.

## Completion record

Completed on 2026-08-18 with no dependency or live-source request.

- Plan-specific checks covered five guide tests, two facility-loader tests,
  twelve combined-input tests, and six facility dbt integration cases.
- The historical two-source pinned replay preserved input-set SHA-256
  `6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307`
  and passed its two fresh screening builds in 661.80 seconds.
- The final three-source builder loaded 36,994 CMS rows, 3,144 SVI rows, and
  7,490 facility rows under input-set SHA-256
  `d2f323cc5349ed5d24593f5889e526e997222670dca0f5e68f699d34f911a0f5`.
- The final full dbt build completed `PASS=380 WARN=0 ERROR=0 SKIP=0`, and
  `dbt docs generate` wrote a fresh catalog. The only console warning is the
  pre-existing dbt project-flags deprecation.
- `uv sync --locked` checked all 62 locked packages; Ruff format and lint
  passed; and the complete deterministic offline suite passed 404 tests in
  1008.37 seconds.
- The standalone guide passed static HTML, link, network, accessibility,
  contrast, responsive, print, and reduced-motion checks. Rendered inspection
  covered 1,440-pixel desktop and 320-pixel narrow layouts, light and dark
  palettes, native controls, and wide-table containment with no page-level
  horizontal overflow.
- Generated DuckDB, dbt, browser-server, and PDF-render artifacts remain
  ignored and were not added to the repository.

## Handoff

The next dependency-ordered slice is facility-to-county assignment: exact
state plus normalized county-name matching, version-controlled explicit
aliases, separate Census remediation for unresolved public business addresses,
reviewed manual exceptions, and `quarantine_facility_geography`. That plan must
prove national coverage at least 99%, calculate visible state coverage,
suppress facility-derived county metrics below 95% state coverage, handle the
Connecticut boundary warning, build `fct_county_facility_snapshot`, and finish
T-015, T-018, and T-019 before adding any due-diligence columns to the screen.
