# Plan 003: CMS Geographic Variation raw-to-stage transformation

**Status:** Completed 2026-08-14  
**Source ID:** `cms_om_gv`  
**Depends on:** Completed Plans 001 and 002  
**Specification coverage:** Milestone 1 CMS raw-to-stage work and the first
Milestone 2 model; T-005, the CMS portion of T-006, and the T-007 source-selection
rule  
**Authoritative requirements:** `specs.md` sections 4, 5.4, 6.1, 7, 8.1,
8.3-8.4, 9-11, 15-17, and 20

## Outcome

Build the first deterministic transformation boundary after raw ingestion. Given
one valid Plan 002 manifest, the implementation will verify the referenced
immutable blob, load its required columns as raw strings into a run-scoped
DuckDB database, and use dbt to produce a typed CMS county-year staging model.

The flow is:

```text
verified run manifest + immutable CSV blob
                    |
                    v
      recheck lineage and file integrity
                    |
                    v
       load required columns as raw text
                    |
                    v
        dbt types and scopes the rows
                    |
                    v
 typed County + All rows, one county FIPS x year
```

This plan makes the source usable for later dimensional models while preserving
the evidence needed to distinguish source suppression, source unavailability,
and a real numeric zero. It does not calculate screening percentiles or claim
that observed outpatient dialysis use among Original Medicare beneficiaries is
kidney disease prevalence, unmet need, disease burden, or an intervention
opportunity.

## Why this is the next dependency

Plans 001 and 002 established what the CMS source must contain and which exact
bytes a run used. The next models cannot safely consume the raw CSV directly:
raw metrics include suppression tokens and unavailable values, the transport
contains state, national, age-subgroup, and `UNKNOWN` rows, and county FIPS must
remain five-character text.

This is the smallest useful vertical slice that closes those gaps. It also
establishes the minimal dbt/DuckDB test harness required by every later source
and mart model without introducing SVI, facility, Airflow, BI, or publication
complexity early.

## Declared grains, denominators, vintage, and lineage

Declare these contracts before implementation:

| Layer | Grain | Denominator and interpretation | Vintage and lineage |
|---|---|---|---|
| Raw load | Plan 001 transport grain: `YEAR x BENE_GEO_LVL x BENE_GEO_DESC x BENE_GEO_CD x BENE_AGE_LVL` | Values are untyped source strings; no analytical interpretation is permitted | One Plan 002 manifest and its verified content-addressed blob |
| County stage | Canonical county FIPS x calendar year | CMS county `All` row; metrics retain their documented Original Medicare denominator and source units | Source year from `YEAR`, plus manifest run ID, content SHA-256, retrieval timestamp, and source modified date |

The county stage is not yet `fct_medicare_county_year`. It is a source-aligned,
typed staging model that the later fact will consume.

## Scope decisions

### Included

- Accept a local Plan 002 manifest path; never contact CMS from this path.
- Validate the manifest format, logical source ID, relative blob path, content
  SHA-256, byte count, row count, schema hash, and header hash before loading.
- Resolve the referenced blob beneath the configured raw root and reject path
  traversal or a missing/corrupt blob.
- Load only the existing required contract columns into a run-scoped DuckDB raw
  relation, preserving every value as text and retaining raw metric strings.
- Reconcile raw loaded rows to the manifest record count.
- Establish the minimal `analytics/` dbt project and a deterministic local
  DuckDB profile pattern with no credentials or external services.
- Select only `BENE_GEO_LVL = 'County'` and `BENE_AGE_LVL = 'All'` rows using
  exact, documented source values.
- Exclude source `UNKNOWN` pseudo-counties and territories.
- Validate canonical county FIPS as five ASCII digits, retain leading zeros,
  and represent the District of Columbia as `11001`.
- Preserve each required metric's raw string beside a typed value and an
  explicit status.
- Convert CMS `*`, blank, and `NA` to typed nulls with distinct statuses;
  preserve numeric zero as numeric zero with status `reported`.
- Type `YEAR` and required numeric measures without changing source scale.
- Add dbt unit/data tests for selection, typing, missingness, FIPS, grain, and
  lineage, plus a network-free fixture integration build.
- Document exact fixture and local-manifest commands.
- On completion, add the required standalone Plan 003 HTML guide and link it
  from the root `README.md` in plan order.

### Excluded

- SVI `-999` normalization; that is the remaining source-specific portion of
  T-006 and belongs with the SVI contract/ingestion plan.
- State or national benchmark models. Raw benchmark rows remain available for
  a later dedicated `fct_medicare_benchmark_year` path and must never be mixed
  into the county stage.
- `dim_county`, `dim_year`, final Medicare facts, screening thresholds,
  quadrants, or Parquet publication.
- Recalculation, aggregation, or comparison of rates and percentages.
- Live-source refreshes or changes to the Plan 002 extractor.
- SVI, facility, geocoder, Airflow, Power BI, hosting, AWS, machine learning,
  or patient-level data.
- A new runtime dependency. DuckDB, dbt Core, and dbt DuckDB are already locked.

## Staging field contract

Use clear, source-aligned names. At minimum, the county stage contains:

- `county_fips` as non-null five-character text;
- `year` as an integer;
- `source_geography_level`, `source_geography_description`,
  `source_geography_code`, and `source_age_level`;
- for each required numeric CMS metric, `<metric>_raw`, `<metric>`, and
  `<metric>_status`;
- `source_id`, `source_manifest_run_id`, `source_content_sha256`,
  `source_retrieved_at_utc`, and `source_modified_at`.

The initial metric status vocabulary is:

| Raw representation | Typed value | Status |
|---|---:|---|
| `*` | null | `suppressed` |
| blank, including whitespace-only | null | `unavailable_blank` |
| `NA`, matched case-insensitively after outer whitespace trim | null | `unavailable_na` |
| Valid numeric text, including `0` | parsed numeric | `reported` |

Any other nonblank, nonsuppression token in a required numeric field is
`invalid_numeric` and blocks the dbt build. It must not be silently converted
to an unavailable value. Raw strings remain unchanged; trimming is allowed only
for classification and numeric parsing.

Use fixed-point decimal types whose precision and scale are documented from the
source contract/dictionary. Do not use floating-point types for governed
metrics when an exact decimal representation is available. Preserve the CMS
source percent scale exactly; do not multiply or divide percentages during
staging.

## Geography rules

- Filtering occurs before county FIPS validation because state and national
  codes do not share the county-key contract.
- A selected county code must match `^[0-9]{5}$` as text.
- Leading-zero values such as `01001` must remain `01001` through DuckDB, dbt,
  tests, and exports.
- District of Columbia must be `11001`. If CMS supplies a recognized raw DC
  representation other than `11001`, map it only through an explicit tested
  rule while retaining the raw code. Do not add a speculative mapping.
- Exclude a row as `UNKNOWN` only through an explicit, tested source rule using
  the source geography description/code evidence. Do not exclude legitimate
  counties through substring or fuzzy matching.
- Territory rows are out of MVP scope and cannot enter the county stage.
- Duplicate `county_fips x year` rows are blocking failures.

## Planned repository artifacts

Exact filenames may be refined during red-green work, but responsibilities must
remain separated:

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/stage/cms_om_gv.py` | Manifest/blob verification and raw-string DuckDB loading. |
| `tests/unit/stage/test_cms_om_gv_stage.py` | Loader integrity, lineage, reconciliation, idempotency, and failure tests. |
| `tests/fixtures/cms_om_gv/staging.csv` | Small synthetic raw fixture covering all required selection and missingness cases. |
| `tests/fixtures/cms_om_gv/staging-manifest.json` | Deterministic fixture lineage, generated or maintained with reconciled hashes. |
| `analytics/dbt_project.yml` | Minimal dbt project configuration. |
| `analytics/profiles.example.yml` | Credential-free local DuckDB profile example; generated databases remain ignored. |
| `analytics/models/sources.yml` | Raw loaded relation declaration, descriptions, and lineage. |
| `analytics/models/staging/cms_om_gv/stg_cms_om_gv_county_year.sql` | Typed, source-scoped county-year staging model. |
| `analytics/models/staging/cms_om_gv/_cms_om_gv_models.yml` | Model contract, column documentation, unit tests, and data tests. |
| `analytics/macros/cms_numeric_value.sql` | Narrow reusable CMS numeric parsing expression, if SQL repetition justifies it. |
| `analytics/macros/cms_numeric_status.sql` | Narrow reusable CMS missingness classification, if SQL repetition justifies it. |
| `tests/integration/test_cms_om_gv_dbt.py` | Network-free fixture load plus `dbt build` acceptance test. |
| `docs/guides/003-cms-staging-explained.html` | Required beginner-friendly completed-plan guide. |
| `README.md` | Current status, Plan 003 guide link, and exact offline commands. |

Do not introduce a general ingestion framework, generic data-quality DSL, or
cross-source macro library in this slice. Extract common behavior only after a
second source proves the abstraction.

## Red-green-refactor execution sequence

### 1. Lock the fixture and expected semantics

Extend or add the smallest synthetic CMS fixture containing:

1. a leading-zero County + All row;
2. that county's age-subgroup row;
3. a state row and a national row;
4. a valid District of Columbia County + All row;
5. an `UNKNOWN` pseudo-county;
6. `*`, blank, `NA`, and numeric zero in required metrics;
7. surrounding whitespace for classification behavior;
8. an invalid numeric token for a blocking failure; and
9. a duplicate county-year case in a separate failing fixture or unit-test
   input.

Keep every label synthetic and representative. Do not copy or commit a full raw
snapshot or present fixture measurements as observations about real counties.

### 2. Test manifest-driven loading

Add failing Python tests proving that the loader:

1. accepts only `cms_om_gv` manifests with the supported manifest version;
2. resolves the blob only beneath the configured raw root;
3. independently verifies content hash, bytes, CSV rows, schema, and header;
4. loads required fields as raw text without losing `01001`, `*`, blank, `NA`,
   or `0`;
5. attaches manifest lineage to the raw relation;
6. reconciles loaded row count to the manifest;
7. creates no final database/relation after an integrity or contract failure;
8. handles an identical run/blob rerun without duplicates; and
9. rejects a conflicting rerun instead of overwriting prior run state.

Implement only enough loader behavior to pass. Reuse Plan 001 contract and Plan
002 canonical verification functions rather than duplicating their rules.

### 3. Establish the minimal dbt fixture harness

Create the dbt project, credential-free example profile, raw source declaration,
and a test helper that builds against a temporary DuckDB database. First prove:

1. `dbt parse` succeeds;
2. a fixture-sized `dbt build` is network-free;
3. generated targets, logs, and DuckDB files remain ignored; and
4. a failing dbt test makes the integration test fail with useful output.

Do not point default tests at `data/raw/` or the live Plan 002 snapshots.

### 4. Test county row selection and FIPS

Add failing dbt unit tests showing that:

1. only exact County + All rows are selected;
2. age subgroups, state rows, national rows, territories, and `UNKNOWN` are
   excluded;
3. `01001` remains five-character text;
4. District of Columbia is `11001`;
5. malformed county FIPS causes a blocking test failure; and
6. `county_fips x year` is unique and non-null.

Implement the narrow staging SQL needed to pass. Do not add final fact or
dimension logic.

### 5. Test CMS typing and missingness

For every required numeric measure, add parameterized or generated tests that
prove:

1. `*` becomes null plus `suppressed`;
2. blank becomes null plus `unavailable_blank`;
3. `NA` becomes null plus `unavailable_na`;
4. numeric zero remains zero plus `reported`;
5. a valid nonzero decimal retains its source scale and precision;
6. raw strings remain available unchanged; and
7. an invalid numeric token blocks the build.

Centralize repeated expressions only after the first direct implementation is
green and equivalence is covered by tests.

### 6. Add lineage and reconciliation tests

Add model/data tests proving that:

1. every staged row carries one source ID, manifest run ID, and content hash;
2. staged selected/excluded counts reconcile to raw fixture counts;
3. the model grain matches its declaration;
4. additive raw columns do not become accidental staging requirements; and
5. rebuilding the same fixture manifest produces identical semantic row counts
   and ordered-result checksums.

### 7. Refactor, document, and complete the guide

After all behavior is green:

1. keep source-specific parsing readable and narrowly named;
2. document model grain, denominators, units, statuses, vintage, and lineage in
   dbt YAML;
3. document exact fixture and local-manifest commands in the root README;
4. create the matching standalone, network-free Plan 003 HTML guide according
   to `docs/guides/README.md`;
5. link the guide from the root README after Plans 001 and 002;
6. update this plan to `Completed` with test counts and factual evidence; and
7. check Git status for generated data before handoff.

## Verification commands

Focused red-green loop:

```powershell
uv run pytest tests/unit/stage tests/integration/test_cms_om_gv_dbt.py
uv run dbt parse --project-dir analytics --profiles-dir <fixture-profile-dir>
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

The implementation must replace `<fixture-profile-dir>` in repository
documentation with one exact, reproducible command or helper. No verification
command may contact CMS or depend on an uncommitted raw snapshot.

An optional local-manifest smoke command may be documented after the fixture
path is green. It must read an already published local blob, perform no network
request, write only ignored run-scoped artifacts, and never update a
latest-successful publication pointer.

## Acceptance criteria

- [x] The transformation begins with one manifest and its verified immutable
  blob; it performs no network requests.
- [x] Required manifest/blob evidence is independently reconciled before load.
- [x] Raw required values enter DuckDB as strings with leading zeros and source
  missingness tokens intact.
- [x] T-005 passes: all selected county FIPS are five-character text and
  leading-zero examples survive end to end.
- [x] The CMS portion of T-006 passes for `*`, blank, `NA`, zero, valid numeric
  values, and blocking invalid tokens.
- [x] The T-007 source-selection rule passes in dbt: only County + All rows
  enter the stage, `UNKNOWN` is excluded, DC is `11001`, and other geography
  rows do not enter. The final fact must repeat this assertion when it is added.
- [x] The staging model is unique and non-null at county FIPS x year grain.
- [x] Typed metrics preserve documented source scales; rates and percentages
  are not summed, averaged, or reinterpreted.
- [x] Every staged row retains source vintage and manifest lineage.
- [x] Fixture loading and `dbt build` are deterministic and network-free.
- [x] Integrity, schema, invalid FIPS, invalid numeric, and duplicate-grain
  failures block the build and leave prior artifacts unchanged.
- [x] No full raw data, generated DuckDB file, dbt output, manifest, or secret
  appears in Git status.
- [x] The Plan 003 guide exists, passes its automated accessibility/link checks,
  and is linked from the README in numeric order.
- [x] The locked Ruff and complete pytest/dbt fixture checks pass.

The in-app browser safety policy blocked the local `file:` URL on 2026-08-14 and
prohibited an alternate-browser workaround. Static HTML parsing,
semantic/accessibility assertions, responsive/dark/reduced-motion/print CSS
assertions, WCAG AA palette-contrast checks, and every local link check passed.
The user then confirmed the required rendered visual QA passed on 2026-08-14.

## Stop conditions

Stop and request a specification or architecture decision if:

- a required metric's source precision cannot be represented safely without a
  new or changed type policy;
- the existing manifest lacks evidence needed to verify its blob without
  silently trusting generated state;
- current CMS values require an undocumented missingness token or geography
  mapping;
- legitimate County + All rows do not satisfy the five-character FIPS policy;
- District of Columbia cannot be represented as `11001` without inventing a
  mapping;
- a correct dbt fixture build requires changing locked dependencies;
- the proposed implementation would modify an immutable raw blob or manifest;
- a generated file cannot be kept outside version control; or
- a failing quality check would have to be weakened to complete the plan.

Do not silently coerce invalid values to null, infer missing values as zero,
drop unexplained rows, fuzzy-match geography, load from a live URL, or relabel
the source measure.

## Autonomous execution boundary

This plan is suitable for an unattended goal because all required inputs are
already local, tests are deterministic, no account or browser interaction is
needed, and the stop conditions are objective. The execution goal is:

> Implement Plan 003 completely using red-green-refactor, including the
> manifest-driven DuckDB load, dbt staging model, deterministic tests,
> documentation, matching HTML guide, and all offline verification. Do not run
> live-source checks, change dependencies, commit, push, or proceed beyond the
> stated scope. Stop only at a listed stop condition; otherwise continue until
> every acceptance criterion is satisfied.

## Handoff

After this plan is complete, the next dependency-ordered step is the 2022 CDC
SVI county source contract and paginated ingestion path. That later plan should
finish the SVI-specific `-999` portion of T-006 and the genuinely paginated
portion of T-003 before joining CMS and SVI or calculating the screening
quadrants.

## Implementation record

- Added a source-specific, network-free loader that parses only canonical Plan
  002 manifests, requires the supported source/contract versions, confines
  manifest and blob paths to the configured raw root, and reuses the existing
  full manifest/blob reconciliation before any database write.
- Added atomic, no-overwrite DuckDB materialization with raw required values as
  `VARCHAR`, repeated manifest lineage, a load-audit row, identical-load no-op
  behavior, different-lineage conflict blocking, and owned partial/WAL cleanup.
- Added the minimal credential-free dbt DuckDB project with telemetry disabled,
  a contracted county-year staging model, fixed-point typing, raw/value/status
  metric triplets, exact County + All filtering, anchored `UNKNOWN` removal,
  territory exclusion, five-character FIPS validation, DC `11001` validation,
  and selected-row reconciliation.
- Added 12 loader unit tests, two dbt unit tests, 32 dbt data tests, five pytest
  integration tests, and four guide structure/link/contrast tests. Failure injection
  proves invalid numeric text, malformed FIPS, and duplicate county-year grain
  each fail `dbt build` with the expected named test.
- The fixture build runs `dbt parse`, `dbt build`, and `dbt docs generate`,
  inspects every governed metric, and verifies an identical ordered semantic
  checksum after rebuild. It makes no external requests and uses only synthetic
  committed fixture values.
- `uv sync --locked`, `uv run ruff format --check .`,
  `uv run ruff check .`, and `uv run pytest` pass on 2026-08-14. The complete
  suite has 125 passing tests.
- Generated dbt targets/logs, local profiles, raw snapshots, manifests, and
  DuckDB databases are ignored and absent from ordinary Git status. No
  dependency or lockfile change was made, and no live-source check was run.
- The user confirmed rendered desktop/narrow and light/dark guide QA passed on
  2026-08-14, closing the final documentation acceptance item.
