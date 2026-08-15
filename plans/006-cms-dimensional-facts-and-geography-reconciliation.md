# Plan 006: CMS dimensional facts and pinned geography reconciliation

**Status:** Completed 2026-08-15 UTC  
**Source IDs:** `cms_om_gv` and `cdc_svi_county_2022`  
**Depends on:** Completed Plans 001-005  
**Recommended delivery boundary:** One cohesive implementation commit after all
acceptance checks pass  
**Expected size:** Approximately one Plan 005-sized slice; this plan is lighter
on new network transport and heavier on contract evolution, dimensional
modeling, geography history, and cross-source reconciliation  
**Specification coverage:** The CMS fact/benchmark and CMS-to-SVI geography
portions of Milestone 2; T-007 through T-011, T-014, and the dimensional-output
portion of T-020  
**Authoritative requirements:** `specs.md` sections 2-8, 9.1-9.3, 10-11,
14-17, and 20

## Outcome

Turn the verified CMS raw snapshot and typed county stage into governed
dimensional models, while proving that the latest CMS county geography and the
current SVI county geography reconcile without silent drops.

The completed flow will be:

```text
verified CMS manifest v2 + verified SVI manifest
                    |
                    v
atomic, run-scoped two-source DuckDB input database
                    |
          +---------+----------+
          |                    |
          v                    v
 typed CMS county stage   typed CMS benchmark stage
          |                    |
          v                    v
 dim_year + governed      authoritative state/national
 Medicare county fact     Medicare benchmark fact
          |
          +---- current county keys ----+
                                         |
                                         v
                            SVI-backed current counties
                            + explicit historical identities
                                         |
                                         v
                         latest-year CMS/SVI reconciliation
                         (3,144 matched in pinned evidence)
```

This plan does not calculate the 75th-percentile threshold or the 2x2 screen.
It creates the facts, dimensions, lineage, and reconciliation evidence that a
later screening plan needs in order to implement that logic transparently.

## Why this is the next reasonable step

Plans 001-003 established the CMS contract, immutable full-file ingestion, raw
loading, missingness typing, and County + All staging. Plans 004-005 completed
the equivalent SVI path through `dim_county` and `fct_svi_county`. The primary
screen cannot be implemented responsibly until the CMS side reaches an equally
governed fact and the two county universes are reconciled.

This slice also resolves three known issues before they can leak into the
screening mart:

1. T-011 requires the reported dialysis-user count, but
   `BENES_OP_DLYS_CNT` is currently only an additive CMS field. It must become
   a required, typed field in a versioned CMS raw contract.
2. The live CMS file represents District of Columbia as a State row with code
   `11`, not as a County row. The county fact must apply one explicit,
   tested county-equivalent mapping to `11001` while retaining the raw source
   level and code.
3. Historical CMS county FIPS do not all exist in the current 2022 SVI county
   universe. Connecticut changed from eight counties to nine planning regions
   in the source beginning in 2022, and the pinned file also contains earlier
   Alaska and South Dakota identifiers. Those facts must remain traceable and
   visibly discontinuous; they cannot be dropped, fuzzy-matched, or allocated
   to current counties.

The existing 2026-08-14 generated evidence makes this suitable for an
unattended implementation goal. The verified CMS blob contains 2014-2024 data,
and the verified SVI snapshot contains 3,144 current in-scope counties. A fresh
CMS manifest is still required after the v2 contract change so the newly
required field is governed rather than opportunistically read as an additive
column.

## Product and safety boundaries

- Use the phrase **“observed outpatient dialysis use among Original Medicare
  beneficiaries.”**
- Do not relabel the CMS measure as kidney disease prevalence, unmet need,
  disease burden, intervention opportunity, or a clinical outcome.
- Standardized outpatient dialysis spending is payment-geography standardized,
  not health-status adjusted.
- State and national rows are authoritative published benchmarks. Never derive
  them by summing or taking an unweighted mean of county rates.
- Do not infer a missing dialysis-user count from the beneficiary share or
  vice versa.
- Do not allocate retired county observations to successor geographies or
  claim that pre/post-boundary trends are directly comparable.
- Do not calculate a percentile threshold, high/low component flag, quadrant,
  opaque score, ranking, recommendation, or facility-context measure.
- Use only public aggregate data. No patient-level data or PHI is in scope.
- Keep every default pytest and dbt fixture check deterministic and
  network-free.
- Do not contact the facility source, Census Geocoder, Power BI, AWS, or an
  authenticated service.

## Scope decisions

### Included

- Promote `BENES_OP_DLYS_CNT` to a required numeric field in
  `cms_om_gv.raw.v2`, with official label, definition, count unit, and schema
  evidence.
- Preserve v1 manifests and blobs as immutable historical artifacts, but
  require a v2 manifest for the Plan 006 combined dimensional build.
- Update the CMS fixtures, contract tests, manifest evidence, raw loader, typed
  stage, source catalog, and affected completed-plan documentation for the new
  governed field.
- Type the dialysis-user count as a nonnegative whole-number decimal with its
  raw token and the existing CMS missingness status vocabulary.
- Apply the explicit DC State `11` -> county-equivalent `11001` rule only for
  the all-ages District of Columbia row, retaining the source geography fields
  and a visible mapping method.
- Build a typed State/National + All benchmark stage that excludes territories
  and the blank-code `Territory`/`ZZ` pseudo-rows without mixing benchmark rows
  into county facts.
- Add a network-free, atomic, single-writer input assembler that verifies one
  CMS v2 manifest and one SVI manifest before placing both raw relations in one
  run-scoped DuckDB database.
- Record a deterministic input-set identity and audit row for the exact ordered
  pair of source manifests/snapshot hashes.
- Extend `dim_county` from the current SVI universe with an explicit,
  version-controlled set of historical CMS-only county identities.
- Mark current and historical identities distinctly and carry a visible
  boundary/identity-discontinuity warning without creating a crosswalk or
  allocation.
- Build `dim_year`, `fct_medicare_county_year`, and
  `fct_medicare_benchmark_year` with enforced contracts, declared grains,
  metrics, units, denominators, statuses, and lineage.
- Add a non-BI reconciliation model at the union of latest CMS and current SVI
  county keys, with per-source presence, row counts, vintages, hashes, and an
  explicit reconciliation status.
- Prove on the pinned full build that the latest CMS set becomes 3,144 current
  counties after the DC mapping, all 3,144 match SVI, and there are no
  duplicates, unexplained source-only keys, or silent drops.
- Add deterministic semantic checksums for the affected dimensions, facts, and
  reconciliation result; prove the same input-set rebuild is identical.
- Add dbt unit tests, singular data tests, model documentation, fixture
  integration/failure-injection tests, and reduced dated full-build evidence.
- On completion, create and link the required standalone Plan 006 HTML guide
  and update any Plan 001-005 guide whose explanation became materially stale.

### Excluded

- The national county 75th percentile, `RPL_THEMES >= 0.75` component flag,
  insufficient-data classification, quadrants, or `mart_county_screening`.
- Dialysis Facility source discovery, ingestion, CCN modeling, facility
  geography mapping, Census geocoding, quarantine, or facility coverage rules.
- A current-to-retired county bridge, population allocation, proportional
  restatement, fuzzy match, ZIP-based geography, or claim of trend continuity.
- A generic slowly changing dimension. Historical source identifiers remain
  separate county keys; SCD Type 2 is still a non-goal.
- Parquet publication, `latest-successful-run`, `audit_pipeline_run`, Airflow,
  Docker, CI expansion, Power BI, and BI reconciliation.
- A generic multi-source plugin framework or broad refactor of working source
  extractors.
- A runtime or development dependency change.
- Committing live source bytes, generated manifests, DuckDB databases, dbt
  targets/logs, or semantic-output dumps.

## CMS raw contract v2

Create `cms_om_gv.raw.v2` by adding exactly one new required metric to the v1
contract:

| Source field | Meaning | Raw/typed rule |
|---|---|---|
| `BENES_OP_DLYS_CNT` | Reported count of Original Medicare beneficiaries using outpatient dialysis facility services | Preserve the raw string; type reported values as `decimal(38, 0)`; `*`, blank, and `NA` remain distinct null statuses; zero remains reported zero; negative or fractional reported values block the build. |

The official schema evidence already observes this label as numeric, but the
v2 evidence must move it from the deterministic additive-field list into the
required-field list and recompute the contract/schema identity according to the
existing manifest rules.

Do not mutate a v1 manifest or raw blob. A new live extraction may reuse an
identical content-addressed blob only after rehashing it, but it must publish a
new canonical v2 manifest under a new run ID. A v1 manifest presented to the
Plan 006 combined builder must fail early with an explicit
`cms_contract_upgrade_required`-style error rather than a misleading corruption
or missing-file error.

The narrow compatibility promise is:

- v1 manifests and blobs remain verifiable as Plan 002/003 artifacts at their
  original Git revision;
- Plan 006 final facts require v2 contract evidence; and
- no existing manifest is overwritten or silently relabeled as v2.

## Combined input-database contract

Add one network-free command with responsibilities equivalent to:

```powershell
uv run python -m kidney_care_mart.stage.build_inputs `
  --build-id <run-id> `
  --cms-manifest data/raw/manifests/cms_om_gv/<v2-run-id>.json `
  --svi-manifest data/raw/manifests/cdc_svi_county_2022/<run-id>.json `
  --raw-root data/raw `
  --database data/staging/<run-id>.duckdb
```

Exact module names may be refined during implementation. The command must:

1. validate the build ID and confine every manifest/blob/page path beneath the
   configured raw root;
2. require exactly one supported CMS v2 manifest and one supported SVI
   manifest with distinct expected source IDs;
3. independently repeat each source-specific manifest, byte, schema, row,
   pagination, FIPS, and lineage verification already required by Plans 003
   and 005;
4. calculate `input_set_sha256` from canonical JSON containing the build format
   version and source entries ordered by logical source ID, including manifest
   run ID, contract version, and content/snapshot hash;
5. load both raw relations and their source audits into one temporary DuckDB
   database through one writer;
6. add one combined input audit row containing the build ID, input-set hash,
   both source identities, manifest IDs, hashes, row/page counts, and retrieval
   times;
7. reconcile both raw relations to their source audits before the final
   database path appears;
8. treat same target + same canonical input set as a no-op; and
9. reject same target + different input set without overwriting either the
   existing database or any source artifact.

This is a local build-input seam, not the Airflow run audit or published mart
commit boundary. It does not update a pointer and does not export Parquet.

## Geography policy for this plan

### Current county identities

SVI remains the source for the current 3,144-county identity surface. Current
rows retain their SVI geography vintage and provenance. Their geography status
must distinguish them from historical-only CMS identifiers.

### District of Columbia

The CMS source currently supplies District of Columbia at State grain. For the
county-equivalent fact only, accept exactly a row satisfying all of:

- `BENE_GEO_LVL = 'State'`;
- `BENE_GEO_DESC = 'DC'` after trim/case normalization;
- `BENE_GEO_CD = '11'` as raw two-character text; and
- `BENE_AGE_LVL = 'All'`.

Map only that row to canonical county FIPS `11001`. Retain raw level,
description, code, age level, and set a mapping method such as
`district_of_columbia_state_to_county_equivalent`. An ordinary County row with
`11001`, if a future source starts publishing one, creates an explicit source
change requiring investigation; it must not silently coexist with or replace
the State-derived row.

The same raw DC State row may also appear in the State benchmark fact because
the facts represent two declared analytical roles. Tests and documentation
must make that intentional reuse visible.

### Historical CMS-only identities

The pinned 2014-2024 CMS snapshot contains 11 source county FIPS that are not
in the current SVI universe:

- eight retired Connecticut county identifiers (`09001` through `09015` odd
  codes) used through 2021 in the pinned CMS source;
- Alaska `02261` and `02270`; and
- South Dakota `46113`.

Create a small reviewed seed or equivalent version-controlled mapping that
lists the exact source FIPS and label, state, observed CMS year range,
`historical_source_only` status, and a boundary/identity-discontinuity warning.
The seed is identity evidence only. It must not contain a successor FIPS,
allocation weight, inferred equivalence, or instruction to combine old and new
rows.

When a CMS county key does not resolve to either the current SVI dimension or
this explicit historical set, fail the build and report it. Do not silently add
an arbitrary new dimension row from unexpected live data.

The resulting pinned `dim_county` expectation is 3,155 unique rows: 3,144
current SVI counties plus 11 historical CMS-only identifiers. This is dated
pinned evidence, not a timeless national county count. The current-only filter
must still return exactly 3,144 rows.

## dbt model contracts

### `stg_cms_om_gv_county_year`

**Grain:** one row per canonical county FIPS x CMS calendar year.  
**Denominator:** Original Medicare beneficiaries in that source county/year.  
**Vintage:** CMS calendar years carried by the verified snapshot.  
**Lineage:** one verified CMS v2 manifest/content hash per build.

Extend the existing stage to include:

- raw/value/status fields for `BENES_OP_DLYS_CNT`;
- `county_geography_mapping_method`, with ordinary County rows distinguished
  from the one explicit DC county-equivalent mapping; and
- the source geography fields already retained for audit.

Continue to exclude age subgroups, territories, and anchored source
`UNKNOWN` pseudo-counties. The ordinary path remains County + All; DC is the
single documented exception. Every typed metric keeps exact decimal semantics.

Blocking value rules include:

- reported counts are nonnegative whole numbers;
- reported decimal-proportion fields are within `[0,1]`;
- reported visits-per-1,000 and payment fields are nonnegative;
- null typed values and missingness statuses agree;
- zero remains reported zero; and
- invalid numeric text blocks the build.

### `stg_cms_om_gv_benchmark_year`

**Grain:** benchmark geography type x benchmark geography key x CMS year.  
**Denominator:** the authoritative CMS State or National Original Medicare
beneficiary population for that row/year.  
**Vintage:** CMS calendar years carried by the verified snapshot.  
**Lineage:** the same verified CMS v2 manifest/content hash as the county stage.

Include State + All rows for the 50 states and District of Columbia, plus the
National + All row. Exclude territories and blank-code State pseudo-rows
`Territory` and `ZZ`.

Use a stable analytical key such as:

- `benchmark_geography_type = 'state'` and the two-character state FIPS as the
  key for State rows; and
- `benchmark_geography_type = 'national'` and `US` as the analytical key for
  the National row.

Preserve the raw source code, including the National blank, beside the
analytical key. Apply the same raw/value/status and value-range rules as the
county stage. Do not join or blend benchmark values into county rows.

### `dim_year`

**Grain:** one row per observed CMS calendar year.

Include at least the integer year and explicit CMS vintage role. The pinned
full build must contain exactly 2014 through 2024 with no duplicate or missing
year. Fixture tests may use a smaller contiguous set. Do not hard-code a latest
year into downstream model SQL; derive it deterministically from verified CMS
facts while asserting the pinned snapshot expectation separately.

### `dim_county`

**Grain:** one row per distinct current or explicitly supported historical
county FIPS.

Extend the existing dimension with fields sufficient to distinguish:

- current SVI-backed county identity;
- historical CMS-only source identity;
- current/inactive status;
- geography source and provenance;
- observed CMS year bounds for historical-only identities; and
- boundary/identity-discontinuity warning status.

Do not overwrite SVI current labels with CMS labels. Do not represent a retired
and current geography as one row. Every FIPS remains five-character text.

### `fct_medicare_county_year`

**Grain:** county FIPS x CMS calendar year.  
**Denominator:** reported Original Medicare beneficiary count for each row;
metric-specific definitions remain those in the CMS dictionary.  
**Lineage:** CMS source ID, v2 manifest run ID, content hash, retrieval time,
source modified date, and geography mapping method.

Include the governed typed values and statuses for:

- Original Medicare beneficiary count;
- outpatient dialysis-user count;
- Medicare Advantage participation rate;
- dual-eligible percentage;
- observed outpatient dialysis use among Original Medicare beneficiaries;
- outpatient dialysis visits per 1,000 beneficiaries;
- standardized outpatient dialysis payment per capita;
- acute hospital readmission percentage; and
- emergency-room visits per 1,000 beneficiaries.

Raw tokens remain in staging and need not be duplicated in the fact because a
tested one-to-one lineage path exists. Every county key must resolve to the
extended `dim_county`, and every year must resolve to `dim_year`.

T-011 must fail when both reported counts are defined and
`BENES_OP_DLYS_CNT > BENES_OM_CNT`. It must not compare suppressed or
unavailable values, derive one field from another, or introduce a rounded
share/count equality test that the specification does not require.

### `fct_medicare_benchmark_year`

**Grain:** benchmark geography type x benchmark geography key x CMS calendar
year.  
**Denominator:** the authoritative beneficiary count on that exact source
benchmark row.  
**Lineage:** the same CMS v2 lineage as the benchmark stage.

Carry the same typed metrics and statuses as the county fact. State/national
rates and percentages remain source-published values. The pinned build should
contain 51 State rows and one National row for each of 11 years, or 572 rows,
unless a legitimate source change is investigated and documented.

### Latest CMS/SVI reconciliation model

**Grain:** one row per county FIPS in the union of current latest-year CMS keys
and current SVI keys.  
**Purpose:** blocking audit evidence, not an analyst-facing score or mart.  
**Vintages:** derived latest CMS year and static SVI 2022 vintage.  
**Lineage:** both source manifest IDs and content/snapshot hashes.

Include:

- `county_fips`;
- CMS latest-year row count and presence;
- SVI current-vintage row count and presence;
- CMS year and SVI vintage;
- per-source manifest and snapshot/content identity; and
- a status such as `matched`, `cms_only`, `svi_only`,
  `duplicate_cms`, or `duplicate_svi`.

For the pinned build, every one of 3,144 rows must be `matched`; all other
statuses must have zero rows. Historical dimension members are explicitly
outside this latest-current reconciliation and must not inflate its denominator.

## Planned repository artifacts

Exact filenames may be refined during red-green work, but these
responsibilities must remain visible:

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/contracts/cms_om_gv.py` | Versioned v2 required-field contract and v1-to-v2 error behavior. |
| `src/kidney_care_mart/stage/cms_om_gv.py` | v2 raw-string loading with the governed dialysis-user count. |
| `src/kidney_care_mart/stage/build_inputs.py` or narrow equivalent | Atomic two-manifest verification, single-writer assembly, input-set hash, audit, and no-op/conflict behavior. |
| `tests/fixtures/cms_om_gv/*.csv` and manifest evidence | Deterministic v2 raw/staging cases, including count missingness and invalid relationships. |
| `analytics/seeds/historical_county_identities.csv` or equivalent | Reviewed historical CMS-only identity allowlist without successor allocation. |
| `analytics/models/staging/cms_om_gv/stg_cms_om_gv_county_year.sql` | County-year typing plus explicit DC county-equivalent mapping. |
| `analytics/models/staging/cms_om_gv/stg_cms_om_gv_benchmark_year.sql` | Separate authoritative State/National stage. |
| `analytics/models/marts/core/dim_year.sql` | One governed row per CMS year. |
| `analytics/models/marts/core/dim_county.sql` | Current SVI identities plus explicit historical-only CMS keys. |
| `analytics/models/marts/core/fct_medicare_county_year.sql` | Governed county-year Medicare fact. |
| `analytics/models/marts/core/fct_medicare_benchmark_year.sql` | Governed authoritative benchmark fact. |
| `analytics/models/audit/audit_cms_svi_county_reconciliation.sql` or equivalent | Latest-current key reconciliation evidence. |
| `analytics/models/**/_*.yml` | Enforced contracts, grains, relationships, units, denominators, lineage, and dbt unit tests. |
| `analytics/tests/assert_cms_*.sql` | Blocking scope, bounds, T-011, fact/stage reconciliation, benchmark, and geography tests. |
| `tests/unit/stage/test_build_inputs.py` | Network-free atomic combined-input and failure-injection tests. |
| `tests/integration/test_cms_dimensional_dbt.py` | Fixture and pinned-manifest DuckDB/dbt acceptance plus deterministic checksums. |
| `docs/source-schemas/cms_om_gv.schema.json` | v2 required-field evidence and recomputed schema identity. |
| `docs/source-catalog.md` | Updated CMS contract, models, geography exceptions, denominators, and live evidence. |
| `docs/preflight.md` | Reduced dated CMS v2 and full reconciliation evidence. |
| `docs/guides/006-cms-facts-and-geography-explained.html` | Required standalone beginner-friendly completed-plan guide. |
| `README.md` and `data/README.md` | Current status, guide link, fixture command, and combined local-build command. |

## Red-green-refactor execution sequence

### 1. Lock the v2 CMS fixtures and contract failures

Before changing production behavior:

1. extend the smallest CMS fixtures with `BENES_OP_DLYS_CNT` values covering a
   positive count, zero, `*`, blank, `NA`, a count greater than beneficiaries,
   a negative count, and a fractional count;
2. add a fixture where the new required column is missing;
3. add a fixture where its declared source type is incompatible;
4. update canonical fixture manifests only through the existing deterministic
   manifest helpers;
5. add failing contract tests that distinguish v1 and v2 evidence; and
6. prove no full source download enters Git.

Implement only the v2 contract and evidence changes required to make those
tests pass. Keep all other required labels and raw-grain rules unchanged.

### 2. Test v2 raw loading and CMS typing

Add failing tests proving that:

1. the raw relation receives `BENES_OP_DLYS_CNT` as exact text;
2. raw zero, whitespace, suppression, blank, and `NA` remain distinguishable;
3. v2 manifest/hash/schema reconciliation occurs before database creation;
4. a v1 manifest fails the combined Plan 006 path with an explicit upgrade
   message;
5. the typed stage produces value/status fields without deriving the count;
6. negative, fractional, or invalid numeric count text blocks the dbt build;
7. all existing CMS missingness and county-scope tests remain green; and
8. the same v2 snapshot rebuild has an identical semantic checksum.

Refactor repeated numeric expressions only after the direct behavior is green.

### 3. Test the DC county-equivalent rule

Replace the synthetic assumption that DC arrives as an ordinary County row
with an official-shaped State `DC`/`11`/All fixture. Add failing tests proving:

1. the row becomes county FIPS `11001` in county staging;
2. its raw State level, code, description, and mapping method remain visible;
3. DC age subgroups do not enter the county stage;
4. an ordinary State row does not enter county staging;
5. an unexpected simultaneous County `11001` and State `11` row blocks the
   build as an ambiguous source change; and
6. no generic State-to-county conversion exists.

Update affected Plan 003 documentation and tests rather than preserving a
fixture shape that contradicts the live source.

### 4. Test benchmark staging separately

Add failing dbt unit and data tests showing that:

1. 50 states plus DC enter with two-character state keys;
2. National enters once per year with analytical key `US` while its blank raw
   code remains preserved;
3. territories and blank-code `Territory`/`ZZ` State pseudo-rows are excluded;
4. age subgroups do not enter;
5. State and National rows never enter the county fact through this model;
6. the benchmark grain is unique and nonnull; and
7. all metric values, statuses, units, denominators, and lineage match the
   source row rather than a county aggregation.

### 5. Test atomic two-source input assembly

Add failing unit tests for the network-free assembler:

1. both manifests and every referenced source byte are reverified;
2. source IDs, contract versions, and manifest paths are exact and confined;
3. `input_set_sha256` is deterministic and independent of CLI argument order;
4. both raw tables and all source/build audit rows reconcile before publish;
5. a corrupt CMS blob, corrupt SVI page, wrong source, or missing manifest
   leaves no final database;
6. same target + same inputs is a no-op;
7. same target + different inputs is a conflict;
8. a partial temporary database is not mistaken for success; and
9. loading uses one writer and introduces no live network seam.

Reuse source-specific verification/load helpers only after tests protect the
existing standalone commands and atomicity behavior.

### 6. Build `dim_year` and the two Medicare facts

Add failing dbt unit/data tests before model SQL:

1. `dim_year` is unique, integer, and reconciles to observed fact years;
2. county facts are unique at county FIPS x year;
3. benchmark facts are unique at type x key x year;
4. every fact year resolves to `dim_year`;
5. every county fact resolves to `dim_county`;
6. raw stage and final facts reconcile one-to-one at their declared grains;
7. all required lineage fields are nonnull and constant for the build input;
8. reported proportions/counts/rates/payments meet their documented bounds;
9. T-011 fails only when both reported counts exist and dialysis users exceed
   Original Medicare beneficiaries; and
10. no state/national rate is recomputed from counties.

### 7. Extend county identity without inventing continuity

Add the minimal reviewed historical-identity seed and failing tests proving:

1. the 11 expected pinned historical-only FIPS are five-character text and
   unique;
2. every seeded key is absent from the current SVI identity set;
3. source label, state, observed year bounds, inactive status, and warning are
   present;
4. no successor FIPS or allocation field exists;
5. current SVI labels and provenance remain authoritative for current rows;
6. an expected historical CMS fact resolves to the historical dimension row;
7. an unexpected CMS-only key blocks the build; and
8. Connecticut pre-2022 and 2022+ rows remain separate keys with a visible
   boundary discontinuity.

Do not generalize this into a historical geography service or SCD framework.

### 8. Prove latest-year CMS/SVI reconciliation

Add failing reconciliation-model and singular tests showing that:

1. latest CMS year is derived deterministically;
2. only current county identities participate;
3. the DC mapping contributes `11001` exactly once;
4. full outer reconciliation reports source presence and row counts;
5. a CMS-only key, SVI-only key, or duplicate produces a named blocking
   status rather than disappearing in an inner join;
6. matched row count plus every mismatch count equals the union row count;
7. source vintages and hashes remain present on every audit row; and
8. the pinned full build has 3,144 union rows, all `matched`.

This step proves T-014 but must not add high/low flags or screening logic.

### 9. Prove deterministic full dimensional output

Using a specific ignored CMS v2 manifest and one verified ignored SVI manifest:

1. assemble a fresh run-scoped database;
2. run the complete affected dbt build and docs generation;
3. record row counts for raw inputs, stages, dimensions, facts, and
   reconciliation;
4. hash ordered semantic rows for every Plan 006 dimensional model;
5. rebuild the same input set at a fresh database path;
6. require identical row counts and semantic hashes;
7. record only reduced hashes/counts/vintages in documentation; and
8. keep both databases and all raw/generated bytes ignored.

For the current pinned evidence, investigate rather than silently change these
expected shapes:

- 2014-2024 in `dim_year`;
- 3,155 total county-dimension rows, including 3,144 current rows;
- 3,144 latest CMS counties after the DC mapping;
- 3,144 matched latest CMS/SVI reconciliation rows;
- 51 State plus one National benchmark row per year; and
- no unexpected CMS-only county key beyond the 11 reviewed historical
  identities.

### 10. Run the bounded live CMS v2 refresh

Only after all offline contract/extractor tests are green:

1. run the existing official CMS full-file extractor with a new run ID under
   the v2 contract;
2. allow reuse of an identical content-addressed blob only after byte/hash
   verification;
3. confirm the new manifest declares v2 and the newly required field;
4. do not overwrite either existing v1 manifest;
5. pair the v2 manifest with a verified SVI manifest in the combined builder;
6. run the pinned full dbt/reconciliation checks; and
7. explain any legitimate upstream change instead of silently updating an
   assertion.

No other live source may be contacted by this plan.

### 11. Refactor, document, and complete the guide

After all behavior is green:

1. keep contract-version, DC, historical-identity, benchmark, and
   reconciliation rules easy to audit;
2. update the source catalog with every model grain, denominator, unit,
   vintage, lineage field, and limitation;
3. update preflight with dated, reduced live/full-build evidence;
4. update Plan 001-005 text or guides wherever the v2 field, DC source shape,
   or expanded county dimension made the completed explanation materially
   stale;
5. create the network-free Plan 006 HTML guide according to
   `docs/guides/README.md`;
6. explain facts, benchmarks, DC county-equivalent handling, historical
   identities, and full-outer reconciliation for a beginner;
7. link the guide from the root README after Plan 005;
8. add static guide tests and complete desktop/narrow, light/dark, keyboard,
   print, and reduced-motion QA;
9. update this plan to `Completed` with exact test and live evidence;
10. run the full locked verification loop; and
11. inspect Git status and ignored generated paths before handoff.

## Verification commands

Focused Python and contract loop:

```powershell
uv run pytest tests/unit/contracts/test_cms_om_gv_contract.py
uv run pytest tests/unit/stage/test_cms_om_gv_stage.py
uv run pytest tests/unit/stage/test_build_inputs.py
uv run ruff format --check src tests
uv run ruff check src tests
```

Focused dbt/integration loop:

```powershell
uv run pytest tests/integration/test_cms_om_gv_dbt.py
uv run pytest tests/integration/test_cms_dimensional_dbt.py
uv run pytest tests/integration/test_cdc_svi_county_2022_dbt.py
uv run dbt parse --project-dir analytics --profiles-dir analytics
uv run dbt docs generate --project-dir analytics --profiles-dir analytics
```

The implementation must use the repository's credential-free temporary
profile helper or its exact documented equivalent. Do not require a committed
`profiles.yml`.

Required offline handoff loop:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Explicit live check, only after the offline path is green:

```powershell
uv run python -m kidney_care_mart.extract.cms_om_gv `
  --run-id cms-om-gv-v2-live-<UTC timestamp> `
  --output-root data/raw
```

Then assemble the documented CMS v2/SVI manifest pair and run the affected dbt
build against the generated run-scoped database. The complete default suite
must make zero external requests.

## Acceptance criteria

- [x] `BENES_OP_DLYS_CNT` is required by a versioned CMS v2 contract and is no
  longer silently consumed as an additive field.
- [x] The v2 manifest/schema/raw loader path preserves its exact raw string,
  value, status, unit, and source definition.
- [x] Existing v1 manifests/blobs are not overwritten or relabeled; the Plan
  006 build fails early and clearly when given v1 evidence.
- [x] CMS `*`, blank, and `NA` remain distinct null statuses for the new count,
  while numeric zero remains reported zero.
- [x] Negative, fractional, invalid, or otherwise incompatible reported count
  values block the build.
- [x] T-007 passes with County + All rows, anchored `UNKNOWN` exclusion,
  territory exclusion, and exactly one tested DC State-to-`11001` exception.
- [x] An ambiguous future DC source shape blocks rather than duplicating or
  silently changing county identity.
- [x] State and National + All benchmark rows are staged separately; territory
  and pseudo-state rows are excluded.
- [x] The combined input database verifies both source manifests and all raw
  bytes before atomic creation, uses one writer, records a deterministic input
  set, and has tested no-op/conflict behavior.
- [x] `dim_year`, extended `dim_county`, `fct_medicare_county_year`, and
  `fct_medicare_benchmark_year` have enforced contracts and declared grains,
  denominators, vintages, and lineage.
- [x] T-008 passes for every Plan 006 primary key.
- [x] T-009 passes: every Medicare fact county/year key resolves, including
  reviewed historical identities; unexpected geography blocks the build.
- [x] The current SVI identity surface remains 3,144 rows while historical CMS
  identities remain separate, inactive, and visibly discontinuous.
- [x] No historical identity seed contains a successor allocation, fuzzy
  match, or invented trend bridge.
- [x] T-010 passes for all governed CMS counts, proportions, rates, payments,
  units, and status/value consistency.
- [x] T-011 passes without deriving missing counts or enforcing an invented
  rounded count/share equality.
- [x] Authoritative benchmark values are copied from exact CMS State/National
  rows and are never computed as summed rates or unweighted county means.
- [x] T-014 passes on the pinned full build: latest CMS and current SVI each
  contribute 3,144 unique current county keys, all match, and no mismatch is
  hidden by join choice.
- [x] The reconciliation model carries both vintages and both source hashes and
  excludes historical-only identities from its current-county denominator.
- [x] The same two manifests reproduce identical model row counts and ordered
  semantic checksums at a fresh path, satisfying this plan's portion of T-020.
- [x] Failure injection for contract removal/type change, corrupt input,
  duplicate keys, invalid metrics, DC ambiguity, unexpected geography, and
  reconciliation mismatch blocks the build.
- [x] One bounded CMS v2 live refresh and combined full build complete, or a
  legitimate upstream change is investigated and explicitly documented.
- [x] The Plan 006 guide is standalone, network-free, accessible, linked from
  the README in numeric order, and passes static plus rendered visual QA.
- [x] Every older guide materially affected by this plan remains accurate.
- [x] No live source response, manifest, DuckDB file, dbt output, secret,
  patient information, or transient source URL appears in Git status.
- [x] No dependency or lockfile change is made.
- [x] The locked Ruff and complete offline pytest/dbt fixture suite pass.
- [x] The completion record states explicitly that percentile, quadrant,
  facility, publication, orchestration, and BI work remain deferred.

## Completion record

Plan 006 completed on 2026-08-15 UTC. The implementation promoted
`BENES_OP_DLYS_CNT` into `cms_om_gv.raw.v2`, preserved source strings and
missingness statuses, added the exact audited DC county-equivalent rule,
separated source-published State/National benchmarks, atomically assembled the
verified CMS/SVI inputs, and built the declared dimensions, Medicare facts,
historical identity surface, and latest-current reconciliation.

The bounded CMS refresh reverified 36,994 rows and 57,865,948 bytes at content
SHA-256 `10c8304012da34da3ecfe4caf4548927095f693383814d0e79ce6711b6806fad`
with zero retries. Paired with the 3,144-row SVI snapshot, both independently
assembled databases had input-set SHA-256
`6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307`.
Each full dbt build completed 214 results with zero warnings or errors and
produced 34,563 county-year facts, 572 benchmark facts, 11 years, 3,155 county
dimension rows (3,144 current plus 11 historical), and 3,144 latest-current
`matched` reconciliation rows with no mismatch.

Fresh-path T-020 evidence matched exactly for every affected relation:

| Relation | Ordered semantic SHA-256 |
|---|---|
| `dim_year` | `60a5de80a85611756662ab0f5900041fe2118f52af4a913d62149a3971d26b6c` |
| `dim_county` | `6f3d6dd0ec70a6b01715c4de9ac8ece612f3a61a3aabca31323a69df9b7d7eb7` |
| `fct_medicare_county_year` | `2c8de8759bc599bca20a32b2fdb09568c7846c9b2f70d23ec3914e36815cbeed` |
| `fct_medicare_benchmark_year` | `0369f9c11124131e29bd1af90a4cfd571af239a8dc02de3ca4528c44f63abef4` |
| `audit_cms_svi_county_reconciliation` | `3c94415a2b4ba9b7d4e505b1cd2a964d7c38d2aa7c3b8da0b88f89b33631fe0b` |

The canonical locked handoff loop passed: `uv sync --locked`, Ruff format and
lint checks, and 278 network-free pytest cases. dbt parse and docs generation
also passed. The standalone guide passed static tests and rendered QA at the
normal 1,280-pixel viewport and a 320-pixel narrow viewport; its native
landmarks/disclosures, skip link, dark/light palette, print rules, and reduced
motion rules remain present. Git inspection confirmed that raw responses,
manifests, live DuckDB files, and dbt targets are ignored, and neither
`pyproject.toml` nor `uv.lock` changed.

The national percentile, screening quadrant, facility context, Parquet
publication, orchestration, and BI work remain explicitly deferred to later
plans. This completion makes no clinical or causal claim and does not rank
providers or select sites.

## Stop conditions

Stop and request a specification or architecture decision if:

- the official CMS metadata no longer exposes `BENES_OP_DLYS_CNT` with a
  compatible numeric definition;
- adding the required count would require weakening or silently relabeling a
  v1 manifest;
- the full CMS file no longer contains one unambiguous DC State row per year
  and no official County DC row;
- a current CMS county cannot be reconciled to current SVI after the documented
  DC rule;
- a new historical CMS-only key appears and its identity/boundary status cannot
  be established from authoritative evidence already in scope;
- preserving historical facts would require an inferred allocation or fuzzy
  geography match;
- state/national source rows cannot be distinguished from pseudo/territory rows
  with deterministic source fields;
- a reported metric introduces an undocumented missingness token, incompatible
  scale, negative value, or nonintegral count;
- the paired manifests cannot be assembled atomically without weakening an
  existing source loader's integrity checks;
- pinned row-count or semantic-checksum differences persist after a bounded,
  evidence-backed investigation;
- correct implementation requires a new dependency or a change to an approved
  metric/geography policy;
- generated artifacts cannot be kept outside version control;
- public CMS/CDC access now requires authentication, payment, or nonpublic
  data; or
- any required test would have to be weakened to complete the plan.

Do not silently drop a county, alter the reviewed historical allowlist, map an
old county to a successor, turn missingness into zero, average county rates
into a benchmark, accept a partial database, update a pinned expectation, or
proceed into screening logic to make a failing build appear complete.

## Autonomous execution boundary

This plan is suitable for an unattended goal. All default development and
failure-injection work is local and deterministic; the only live operation is
one bounded, public, read-only CMS refresh after offline tests pass. Existing
source locators and transport behavior are already verified. Generated data is
ignored, no account or secret is needed, dependency changes are excluded, and
the stop conditions cover the known specification uncertainties.

The execution goal is:

> Implement Plan 006 completely using red-green-refactor. Upgrade the CMS raw
> contract to v2 with governed outpatient dialysis-user count evidence; retain
> raw missingness and lineage; model the explicit District of Columbia
> county-equivalent rule; build separate CMS county and authoritative
> State/National stages, `dim_year`, the current-plus-historical `dim_county`,
> `fct_medicare_county_year`, and `fct_medicare_benchmark_year`; atomically
> assemble verified CMS v2 and SVI manifests in one run-scoped DuckDB database;
> prove the pinned 3,144/3,144 latest-current geography reconciliation and
> deterministic rebuild; update tests, source/model documentation, affected
> older guides, and the matching standalone Plan 006 HTML guide; run one
> bounded CMS v2 refresh only after the offline path is green. Keep every
> default test network-free. Do not change dependencies, commit, push, contact
> facility/Census/AWS services, publish Parquet, build the screening quadrant,
> or proceed beyond this plan. Stop only at a listed stop condition; otherwise
> continue until every acceptance criterion is satisfied.

## Handoff

After Plan 006 is complete, the dependency-ordered next slice should implement
the transparent two-component screening mart from the reconciled latest CMS
fact and static SVI fact. That later plan should own the national county 75th
percentile, `RPL_THEMES >= 0.75`, insufficient-data logic, quadrant totals, and
screening-specific documentation. Facility context can follow as a separate
source/geography vertical slice and must never alter the quadrant.
