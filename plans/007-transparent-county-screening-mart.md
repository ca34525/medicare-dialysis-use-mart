# Plan 007: Transparent county screening mart

**Status:** Completed 2026-08-15 UTC

**Source IDs:** `cms_om_gv` and `cdc_svi_county_2022`

**Depends on:** Completed Plans 001-006

**Recommended delivery boundary:** One cohesive implementation commit after all
acceptance checks pass; do not create that commit unless the user explicitly
requests it

**Expected size:** Approximately one Plan 006-sized slice; this plan is lighter
on source transport and heavier on governed metric semantics, boundary fixtures,
classification reconciliation, deterministic evidence, and analyst-facing
documentation

**Specification coverage:** The two-component screening portion of Milestone 2;
`mart_county_screening` before facility enrichment/publication; T-016, T-017,
and the screening-output portion of T-020

**Authoritative requirements:** `specs.md` sections 2-4, 6.1-6.2, 7-8,
9.1-9.3, 10.2-10.3, 11, 13.1-13.2, 14-17, and 20

## Outcome

Turn the reconciled latest CMS county fact and static SVI county fact into one
transparent, run-scoped county screening mart. Every row will show the exact
two component values, the national county threshold, the source statuses and
vintages, the two nullable component flags, and the resulting quadrant or
insufficient-data classification.

The completed flow will be:

```text
verified CMS v2 + SVI input set
             |
             v
  latest current CMS county rows --------+
             |                            |
             v                            |
reported BENES_OP_DLYS_PCT rows           |
             |                            |
             v                            |
national county continuous P75            |
             |                            |
             +-------------+--------------+
                           |
current SVI 2022 ----------+
                           |
                           v
             explicit component bands
             + missing-data reasons
                           |
                           v
              mart_county_screening
                           |
                           v
          five-category count reconciliation
```

This plan answers only the first half of the bounded product question: which
counties fall into each transparent two-component screen based on observed
outpatient dialysis use among Original Medicare beneficiaries and static 2022
social vulnerability context. It does not add facility context, publish
Parquet, update a latest-successful pointer, create a BI report, rank counties,
or recommend action.

## Why this is the next reasonable step

Plans 001-005 established verified CMS and SVI inputs. Plan 006 then created
the governed county/year facts, current county identity surface, explicit
historical identities, and a blocking latest-current full-outer
reconciliation. The Plan 006 handoff explicitly identifies the next
dependency-ordered slice as the national county 75th percentile,
`RPL_THEMES >= 0.75`, insufficient-data handling, and quadrant reconciliation.

This is the first slice that creates the product's actual screen, but the
inputs and uncertainties are already bounded:

1. the CMS metric is typed as a 0-to-1 decimal with a status that distinguishes
   reported, suppressed, blank, and `NA` values;
2. SVI `RPL_THEMES` is typed as a U.S.-based county percentile rank with
   `-999` and null represented as explicit unavailable statuses;
3. the latest CMS year is derived rather than hard-coded;
4. current CMS and SVI keys are already required to reconcile one-to-one; and
5. the combined input database already contains a deterministic `build_id` and
   `input_set_sha256` for run lineage.

No new source, network call, account, secret, dependency, or geography rule is
needed. That makes this plan particularly suitable for an unattended goal:
all implementation, failure injection, full-data calculation, documentation,
and verification can be completed from local verified inputs.

## Product and safety boundaries

- Use the phrase **“observed outpatient dialysis use among Original Medicare
  beneficiaries.”**
- Do not relabel the CMS measure or a quadrant as kidney disease prevalence,
  unmet need, disease burden, intervention opportunity, risk, demand, or a
  clinical outcome.
- The screen is a transparent classification for further analyst
  investigation, not an automated decision, score, ranking, prioritization,
  final site-selection result, provider recommendation, or contracting signal.
- `RPL_THEMES` is static 2022 social vulnerability context based on 2018-2022
  ACS data. Do not relabel it as a 2024, 2026, or trend observation.
- Do not compare SVI percentile ranks across vintages or recalculate an SVI
  percentile from the loaded rows.
- Facility characteristics are absent in this plan. A later facility slice may
  add due-diligence context but must never alter the component flags,
  threshold, or quadrant.
- Never use an official CMS National or State benchmark row as the national
  **county** 75th percentile. Those are source-published population benchmarks
  at a different grain.
- Never sum or average county rates or percentages to produce a State or
  National KPI.
- Never turn a suppressed, blank, `NA`, `-999`, null, or invalid value into
  zero. A reported numeric zero remains eligible data.
- Invalid source values continue to block the overall dbt build through the
  existing upstream tests. A defensive insufficient-data label must not make
  invalid input publishable.
- Historical-only county identities never enter the current screen and are not
  bridged, allocated, or compared to successor geographies.
- Use only public aggregate data. No patient-level data or PHI is in scope.
- Keep every default test deterministic and network-free.

## Scope decisions

### Included

- Declare the run-scoped `raw.build_input_audit` relation as a governed dbt
  source and require exactly one reconciled build row.
- Use its `build_id` as `screening_run_id` and its `input_set_sha256` as the
  deterministic identity of the candidate screening run.
- Derive the latest CMS year from `dim_year`/`fct_medicare_county_year`; do not
  embed `2024` in model SQL.
- Restrict the screen and percentile universe to current in-scope county
  identities in `dim_county`.
- Calculate the national county 75th percentile from latest-year, current,
  reported, nonnull `benes_op_dlys_pct` rows only.
- Pin the percentile to continuous inclusive linear interpolation, keep the
  full `decimal(38, 10)` result, and classify equality as higher use.
- Include a reported numeric zero in the percentile universe.
- Exclude suppressed, blank, `NA`, unavailable, null, historical, older-year,
  State, and National rows from the percentile universe.
- Record the threshold method, quantile, eligible/excluded/current counts,
  CMS year, both source lineages, run identity, and a screening-definition
  version in a one-row threshold model.
- Classify `RPL_THEMES >= 0.75` as higher social vulnerability, including exact
  equality, without re-ranking SVI.
- Carry the two raw governed component values, exact upstream statuses, CMS
  beneficiary denominator/status, SVI/ACS vintage, and lineage into the mart.
- Produce nullable boolean component flags and explicit component-band labels;
  unavailable components are null, never false.
- Produce exactly four complete-data quadrant keys plus one
  `insufficient_data` key.
- Add an explicit reason indicating whether the dialysis-use component, the
  social-vulnerability component, or both components are unavailable. Preserve
  the detailed upstream status fields beside that coarse reason.
- Ensure the national threshold is a fixed run attribute repeated on county
  rows; State, county, or future BI filters must not recalculate it.
- Create a five-category audit summary that emits a zero-count row for an empty
  quadrant and proves all category counts reconcile to the mart/current county
  total.
- Add dbt unit tests, singular data tests, fixture integration tests, failure
  injection, contract documentation, and ordered semantic-checksum coverage.
- Rebuild the existing ignored Plan 006 input set at two fresh paths and prove
  identical threshold, mart, summary row counts, and semantic checksums.
- Record reduced, dated full-build evidence without committing source rows,
  generated databases, or dbt artifacts.
- Create `docs/metric-dictionary.md` with the exact screening contract and link
  it from the relevant repository documentation.
- On completion, create and link the required standalone Plan 007 HTML guide
  and update any older guide made materially stale by the now-completed screen.

### Excluded

- Dialysis Facility source discovery, schema contracts, extraction, staging,
  CCN facts, facility geography, Census geocoding, aliases, quarantine,
  coverage thresholds, stations, ratings, modalities, or quality context.
- Any facility-derived column in `mart_county_screening`.
- Parquet export, atomic mart publication, output checksums, publish manifests,
  `latest-successful-run`, `audit_pipeline_run`, or pointer mutation.
- Calling the run a **published run** before a later publication gate exports
  it successfully. This plan produces a deterministic candidate screening run.
- Airflow, Docker, GitHub Actions expansion, Power BI, DAX, `.pbix`, map
  visuals, screenshots, or BI reconciliation.
- A composite score, weighted index, ranking, ordered priority list, top-N
  county list, recommendation, or automated narrative.
- A State-specific percentile, filter-responsive threshold, national CMS
  benchmark substitution, weighted percentile, or beneficiary-weighted
  threshold.
- Cross-year screening quadrants. Only the derived latest CMS year is screened;
  historical Medicare trends remain in `fct_medicare_county_year`.
- Cross-vintage SVI comparison or a new SVI calculation.
- Changing a CMS or SVI source contract, rerunning a live extractor, or
  contacting any external service.
- A dependency or lockfile change.
- Committing live source bytes, manifests, DuckDB databases, dbt targets/logs,
  row-level mart exports, or semantic-output dumps.

## Screening metric contract

### Screening run identity

The combined input database contains exactly one `raw.build_input_audit` row.
For this plan:

- `screening_run_id = build_id`;
- `input_set_sha256` identifies the exact ordered CMS/SVI input pair;
- `screening_definition_version = 'county_screening.v1'`; and
- the candidate-run key is `(screening_run_id, county_fips)`.

A run-scoped database contains only one candidate run, so `county_fips` will
also be physically unique in that database. Keep the composite logical key and
run lineage explicit so a later publication step can export multiple immutable
runs without redesigning the mart. The later publication plan owns the rule
that only a fully successful candidate becomes a published run.

The build must fail if `raw.build_input_audit` is absent, has anything other
than one row, conflicts with repeated fact lineage, has malformed hashes, or
does not describe the exact CMS/SVI manifests used by the facts.

### Latest current county universe

The screening denominator is the current in-scope county identity surface:

1. derive the latest CMS year from the one `dim_year` row where
   `is_latest_cms_year` is true and reconcile it to `max(year)` in the Medicare
   county fact;
2. join latest-year CMS rows to `dim_county` with
   `is_current_county = true`;
3. join exactly one `fct_svi_county` row for the governed static vintage; and
4. require the existing latest CMS/SVI audit status to be `matched` with one
   row from each source.

Historical-only dimension rows, older CMS observations, source State/National
benchmarks, territories, and source pseudo-counties are outside this
denominator. For the pinned Plan 006 input set, the expected current screening
row count is 3,144. Treat that as dated snapshot evidence, not a timeless
constant.

### National county 75th percentile

The metric is the unweighted national distribution of county-level reported
`BENES_OP_DLYS_PCT` values. Beneficiary counts do not weight the percentile.
This is intentionally different from a population benchmark.

Let the sorted eligible values be `x[0] ... x[n-1]`. Define:

```text
position = (n - 1) * 0.75
lower = floor(position)
upper = ceil(position)
weight = position - lower
P75 = x[lower] + weight * (x[upper] - x[lower])
```

Implement the equivalent DuckDB continuous aggregate, such as
`quantile_cont(benes_op_dlys_pct, 0.75)`, and retain the resulting
`decimal(38, 10)` without classification-time rounding. A deterministic
fixture with `0.01`, `0.02`, `0.03`, and `0.04` must return
`0.0325000000`.

Eligibility requires all of:

- the row is from the derived latest CMS year;
- its county identity is current and in scope;
- `benes_op_dlys_pct_status = 'reported'`; and
- `benes_op_dlys_pct` is nonnull and already within the upstream-governed
  `[0,1]` range.

Reported zero is eligible. Suppressed, unavailable blank, unavailable `NA`,
null, and invalid values are excluded from calculation. Invalid values must
also fail upstream quality tests, so they cannot become a successful screen.

The higher-use rule is:

```text
is_higher_observed_dialysis_use =
    benes_op_dlys_pct >= dialysis_use_p75_threshold
```

for a reported component. Equality is higher use. Because equality is
inclusive, ties can make more than exactly 25% of eligible counties higher
use; that is correct and must not be “fixed” with ranking or arbitrary
tie-breaking.

### Social-vulnerability component

Use the exact source rank and static vintage already governed in
`fct_svi_county`:

```text
is_higher_social_vulnerability = rpl_themes >= 0.75
```

for a reported, nonnull value. Exact `0.75` is higher vulnerability. A
reported zero is valid lower vulnerability. Do not calculate another
percentile, filter to a State, or compare SVI vintages.

### Missingness and invalid data

The mart must preserve the upstream component status fields. Derived booleans
and bands follow this truth table:

| Component condition | Boolean | Band |
|---|---:|---|
| Reported value at/above its threshold | `true` | `higher_use` or `higher_vulnerability` |
| Reported value below its threshold | `false` | `lower_use` or `lower_vulnerability` |
| Suppressed, unavailable, null, or invalid | `null` | `insufficient_data` |

The overall data status/reason must be:

| Component availability | `screening_data_status` | `screening_insufficient_reason` |
|---|---|---|
| Both available | `complete` | null |
| Dialysis-use unavailable only | `insufficient_data` | `dialysis_use_component_unavailable` |
| SVI unavailable only | `insufficient_data` | `social_vulnerability_component_unavailable` |
| Both unavailable | `insufficient_data` | `both_components_unavailable` |

“Unavailable” in this table is a derived screening concept; the exact source
cause remains visible in `benes_op_dlys_pct_status` and `rpl_themes_status`.
Do not discard the difference between suppression, blank, `NA`, SVI sentinel,
null, or invalid typing.

An invalid upstream value may defensively produce an insufficient-data row
while SQL models are evaluated, but the existing blocking source/fact tests
must still make the overall `dbt build` fail. This plan must not weaken those
tests or permit publication of invalid data.

### Quadrant vocabulary

Use exactly these stable machine keys:

1. `higher_use_higher_vulnerability`;
2. `higher_use_lower_vulnerability`;
3. `lower_use_higher_vulnerability`;
4. `lower_use_lower_vulnerability`; and
5. `insufficient_data`.

The first four require both reported components. Any unavailable component
produces `insufficient_data`, even if the other component is high. Do not use a
component result to impute the missing one.

The machine keys may have separate plain-language display labels in the model
documentation, but neither key nor label may use “opportunity,” “need,”
“burden,” “risk,” “priority,” or “recommendation.” Do not assign ordinal
weights or a sort that implies best-to-worst ranking. A neutral display order
is permitted only for stable layout and reconciliation.

### Fixed national behavior

The P75 threshold is calculated once for the candidate run and cross-joined to
all county rows. It must not be implemented as a window partitioned by State or
as a downstream BI measure that changes with filters. Tests must prove:

- every mart row in a run has the same threshold;
- a State subset retains the national threshold;
- removing an unavailable SVI value does not change the CMS percentile
  eligibility set;
- changing a CMS State/National benchmark does not change the threshold; and
- older-year or historical-only values do not change the threshold.

## dbt model contracts

### `int_county_screening_threshold`

**Grain:** one row per candidate screening run.

**Denominator:** latest-year current counties with reported, nonnull
`benes_op_dlys_pct`; every county has equal weight.

**Vintage:** derived latest CMS year plus the static SVI vintage used by the
candidate run.

**Lineage:** combined build identity plus both verified source manifests and
content/snapshot hashes.

Include at minimum:

- `screening_definition_version`;
- `screening_run_id`;
- `input_set_sha256`;
- `build_format_version`;
- `cms_year`;
- `svi_vintage`;
- `threshold_metric` with stable value `BENES_OP_DLYS_PCT`;
- `threshold_quantile` with exact value `0.75`;
- `threshold_method` documenting continuous inclusive linear interpolation;
- `dialysis_use_p75_threshold` as `decimal(38, 10)`;
- `current_county_count`;
- `threshold_eligible_count`;
- `threshold_excluded_count`;
- CMS manifest ID, content hash, retrieval time, and modified date; and
- SVI manifest ID, snapshot hash, retrieval time, and modified date.

Blocking invariants:

- exactly one run/input-set row exists;
- latest year and SVI vintage are singular and nonnull;
- `current_county_count = threshold_eligible_count +
  threshold_excluded_count`;
- eligible count is positive;
- the threshold is nonnull and within `[0,1]`;
- source hashes are well-formed and reconcile to facts/build audit; and
- the threshold uses no State/National benchmark value.

### `mart_county_screening`

**Logical grain:** candidate screening run x current county FIPS.

**Physical run-scoped invariant:** exactly one row per current county FIPS in
the database.

**Denominators:** the CMS proportion uses the source-reported Original Medicare
beneficiary denominator; SVI `RPL_THEMES` is a U.S.-based county percentile
rank.

**Vintages:** derived latest CMS year and static SVI/ACS period.

**Lineage:** candidate build, threshold definition, and both source identities.

Include at minimum:

- run fields: `screening_definition_version`, `screening_run_id`,
  `input_set_sha256`;
- county fields: `county_fips`, `state_fips`, `state_name`,
  `state_abbreviation`, `county_name`;
- vintage fields: `cms_year`, `svi_vintage`, `acs_period_start`,
  `acs_period_end`;
- denominator context: `benes_om_cnt`, `benes_om_cnt_status`;
- dialysis-use fields: `benes_op_dlys_pct`,
  `benes_op_dlys_pct_status`, `dialysis_use_p75_threshold`,
  `threshold_eligible_count`, `is_higher_observed_dialysis_use`, and
  `dialysis_use_band`;
- vulnerability fields: `rpl_themes`, `rpl_themes_status`,
  `is_higher_social_vulnerability`, and `social_vulnerability_band`;
- classification fields: `screening_data_status`,
  `screening_insufficient_reason`, and `screening_quadrant`;
- geography context: current/in-scope status and any current-row boundary
  warning field needed for downstream caveats; and
- CMS/SVI manifest IDs, hashes, retrieval times, and upstream modified dates.

Blocking invariants:

- `(screening_run_id, county_fips)` is unique and nonnull;
- every row resolves to a current `dim_county` member and none resolves to a
  historical-only identity;
- every row comes from the one derived latest CMS year and one SVI vintage;
- every row is `matched` one-to-one in the Plan 006 reconciliation audit;
- all rows share one run ID, input-set hash, definition version, and threshold;
- component values/statuses reconcile exactly to their governed facts;
- component flags, bands, overall data status, reason, and quadrant agree with
  the truth tables above;
- no missing component is represented as false/lower;
- the four complete quadrants contain only complete-data rows;
- `insufficient_data` contains every and only incomplete row; and
- no score, rank, recommendation, or facility field is present.

### `audit_screening_quadrant_summary`

**Grain:** candidate screening run x one of the five quadrant/category keys.

**Purpose:** blocking count and lineage reconciliation, not a ranking or KPI
substitute.

**Lineage:** the exact threshold and candidate screening run.

Emit all five category keys even when a category count is zero. Include at
minimum:

- `screening_definition_version`;
- `screening_run_id`;
- `input_set_sha256`;
- `cms_year` and `svi_vintage`;
- `screening_quadrant`;
- `screening_row_count`;
- `total_screening_row_count`;
- `dialysis_use_p75_threshold`;
- `threshold_eligible_count` and `threshold_excluded_count`; and
- both source manifest IDs and hashes.

Blocking invariants:

- exactly five rows exist for one run;
- category keys are unique and complete;
- each count is nonnegative;
- the sum of the five category counts equals
  `total_screening_row_count`, the mart row count, and the current county count;
- the sum of the first four categories equals the mart's complete-data count;
- the fifth category equals the mart's insufficient-data count;
- high/low component marginal totals reconcile to row-level flags; and
- all repeated run, threshold, vintage, and lineage fields are singular.

## Planning-time pinned evidence

A read-only dry run on 2026-08-15 against the ignored Plan 006 full database
with input-set SHA-256
`6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307`
produced these provisional expectations under the exact contract above:

| Evidence | Provisional value |
|---|---:|
| Current screening counties | 3,144 |
| Reported CMS rows eligible for P75 | 2,148 |
| CMS rows excluded from P75 | 996 |
| Continuous P75 | `0.0086000000` |
| Higher use / higher vulnerability | 354 |
| Higher use / lower vulnerability | 188 |
| Lower use / higher vulnerability | 259 |
| Lower use / lower vulnerability | 1,347 |
| Insufficient data | 996 |

These are reduced results derived from already verified local source inputs;
no external request was made for this plan. They are pinned-snapshot
expectations, not timeless national constants or findings. Implementation must
reproduce them from governed models, investigate any difference, and record
the final threshold/counts/checksums in the completion record. Do not silently
edit these values to make a failing build pass.

## Planned repository artifacts

Exact filenames may be refined during red-green work, but these
responsibilities must remain visible:

| Path | Purpose |
|---|---|
| `analytics/models/sources.yml` | Govern the one-row combined build audit as run lineage. |
| `analytics/models/intermediate/screening/int_county_screening_threshold.sql` or narrow equivalent | One fixed national county P75 per candidate run with method, counts, vintages, and lineage. |
| `analytics/models/intermediate/screening/_screening_intermediate_models.yml` | Enforced threshold contract and boundary-focused dbt unit tests. |
| `analytics/models/marts/screening/mart_county_screening.sql` | One transparent latest-year screening row per current county/run. |
| `analytics/models/marts/screening/_screening_models.yml` | Enforced grain, field meanings, denominators, statuses, flags, quadrants, lineage, and unit tests. |
| `analytics/models/audit/audit_screening_quadrant_summary.sql` | Five-category totals and run/threshold reconciliation. |
| `analytics/models/audit/_audit_models.yml` or a focused screening audit YAML | Summary contract and tests. |
| `analytics/tests/assert_screening_*.sql` | Blocking eligibility, threshold, flag, quadrant, total, lineage, and no-historical-row tests. |
| `tests/integration/test_county_screening_dbt.py` | End-to-end fixture, failure injection, full pinned calculation, and deterministic checksum evidence. |
| `docs/metric-dictionary.md` | Governed formula, grain, denominator, threshold method, status vocabulary, quadrant definitions, lineage, and limitations. |
| `docs/source-catalog.md` | Link source metrics to the derived screening contract without redefining them. |
| `docs/preflight.md` | Dated reduced full-build threshold/count/checksum evidence. |
| `docs/guides/007-county-screening-explained.html` | Required standalone beginner-friendly completed-plan guide. |
| `tests/unit/docs/test_plan_007_guide.py` | Static guide structure, language, local-link, and network-free checks. |
| `README.md` | Completed status, Plan 007 guide link, and local screening-build query/verification commands. |

## Red-green-refactor execution sequence

### 1. Lock the screening fixtures and expected vocabulary

Before adding model SQL:

1. create the smallest dbt unit-test inputs that cover four reported CMS
   values `0.01`, `0.02`, `0.03`, and `0.04` and expect P75
   `0.0325000000`;
2. add reported zero, exact-threshold equality, and duplicate/tied-threshold
   cases;
3. add CMS `suppressed`, `unavailable_blank`, `unavailable_na`, null, and an
   invalid defensive case while preserving the existing blocking invalid test;
4. add SVI reported `0`, exact `0.75`, `1`, unavailable sentinel, unavailable
   null, and invalid/out-of-range failure cases;
5. add an older-year high CMS value, a historical-only latest-year value, and
   State/National benchmark values that would change the answer if incorrectly
   included;
6. add at least one reported CMS row with unavailable SVI to prove that SVI
   availability does not change CMS percentile eligibility;
7. name all five category keys and three insufficient-reason keys explicitly
   in test expectations; and
8. make the first focused dbt unit/integration run fail because the screening
   models do not yet exist.

Do not change source fixtures merely to manufacture a pleasing quadrant
distribution. Unit fixtures express metric rules; full-data evidence reports
the actual pinned result.

### 2. Govern candidate-run lineage

Add failing source/data tests proving that:

1. `raw.build_input_audit` exists and has exactly one row;
2. `build_id` and `input_set_sha256` are nonnull and well formed;
3. both source IDs, contract versions, manifest IDs, hashes, retrieval times,
   page counts, and row counts remain present;
4. build-audit CMS lineage equals the Medicare fact lineage;
5. build-audit SVI lineage equals the SVI fact lineage;
6. a missing, duplicate, or conflicting audit row blocks the build; and
7. no wall-clock timestamp or generated random identifier enters screening
   semantics.

Implement only the dbt source declaration and narrow reconciliation needed to
make those tests pass. Do not turn this into `audit_pipeline_run` or a publish
pointer.

### 3. Build and test the fixed national threshold

Add `int_county_screening_threshold` only after failing tests prove:

1. latest CMS year is derived and singular;
2. current county membership is explicit;
3. only reported, nonnull CMS values are eligible;
4. zero is included;
5. suppression, blank, `NA`, null, invalid, older-year, historical-only,
   State, and National rows are excluded;
6. continuous interpolation produces the exact four-value fixture result;
7. ties are not broken or ranked;
8. eligible plus excluded equals the current county count;
9. the threshold remains `decimal(38, 10)` and is not rounded before use;
10. one definition/run/input-set row carries both source lineages; and
11. zero eligible rows or multiple latest years fail with named evidence.

Keep the threshold calculation readable in SQL. A macro is justified only if
tests show real repeated behavior; do not create a generic scoring framework.

### 4. Build component flags and all five classifications

Add failing unit tests for `mart_county_screening` before its SQL:

1. a reported CMS value equal to P75 is higher use;
2. a reported SVI value equal to `0.75` is higher vulnerability;
3. reported zero remains available and lower when below the threshold;
4. all four complete-data flag combinations map to their exact quadrant keys;
5. each single-component unavailable case maps to `insufficient_data` with the
   correct coarse reason and null component boolean/band;
6. both unavailable maps to `both_components_unavailable`;
7. the available component remains visible when the other is unavailable but
   does not produce a complete quadrant;
8. exact upstream statuses remain present;
9. beneficiary denominator/status, CMS year, SVI/ACS vintage, county labels,
   run identity, and source lineage remain present;
10. only current reconciled county keys enter;
11. every row repeats the one fixed national threshold; and
12. no score, rank, priority, recommendation, or facility field appears.

Implement explicit `case` logic with nullable booleans. Refactor repeated
availability predicates only after the direct truth-table tests are green.

### 5. Prove category and marginal reconciliation

Create `audit_screening_quadrant_summary` after failing tests prove:

1. all five category keys appear even when one has zero rows;
2. the category grain is unique;
3. category counts are nonnegative integers;
4. their sum equals the screening mart and current county totals;
5. complete quadrant counts equal the complete-data row count;
6. insufficient count equals the incomplete row count;
7. higher/lower use and vulnerability marginal counts reconcile to row flags;
8. the threshold eligible/excluded counts reconcile to mart statuses;
9. one run, threshold, year, SVI vintage, and lineage are repeated exactly;
   and
10. selecting a State subset of the mart still shows the national threshold
    rather than a recomputed State threshold.

Keep this model audit-facing. It must not order categories as a market ranking
or claim that one category warrants action.

### 6. Add failure injection and protect upstream gates

Extend the integration harness with named failures for:

1. duplicate build-audit rows;
2. fact/build lineage mismatch;
3. multiple or missing latest-year flags;
4. historical county leakage;
5. a threshold built from a suppressed or unavailable value;
6. a threshold accidentally partitioned by State;
7. null or out-of-range threshold;
8. a component flag inconsistent with its value/status;
9. a complete quadrant containing missing data;
10. category totals that do not reconcile;
11. missing SVI or CMS keys that should already fail Plan 006 reconciliation;
    and
12. invalid CMS/SVI values that must continue to fail upstream rather than
    becoming a successful insufficient-data build.

Each case must fail with named dbt evidence. Do not weaken Plan 001-006 tests
or bypass a failed upstream model merely to exercise downstream SQL.

### 7. Prove deterministic fixture and full screening output

Using the existing network-free builders and ignored verified Plan 006
manifests:

1. build the dedicated screening fixture from a fresh database path;
2. run the complete dbt build and docs generation;
3. assert the exact fixture threshold, five category counts, component flags,
   missing reasons, grain, and lineage;
4. calculate ordered semantic SHA-256 values for the threshold, screening
   mart, and category summary;
5. rebuild the fixture at a second fresh path and require identical results;
6. build the pinned full input set at two fresh paths without network access;
7. require the provisional 3,144/2,148/996 counts, P75
   `0.0086000000`, and five category counts unless a bounded investigation
   identifies an implementation or documented input difference;
8. require identical ordered semantic hashes across the two full builds;
9. record only reduced run ID, input-set hash, vintages, threshold, counts, and
   semantic hashes; and
10. keep every generated database and row-level output ignored.

This plan performs no live-source refresh. If the ignored Plan 006 input set is
missing locally, fixture completion may proceed, but full pinned acceptance is
a stop condition until the exact verified manifests/blobs can be restored or
the user explicitly changes the delivery boundary.

### 8. Refactor and document the metric contract

After behavior is green:

1. keep the percentile eligibility predicate, continuous method, component
   availability, flags, reasons, and quadrant mapping easy to audit;
2. add `docs/metric-dictionary.md` with model grain, denominator, source unit,
   formula, threshold method, equality rule, status vocabulary, vintage,
   lineage, examples, and limitations;
3. distinguish the national county percentile from source-published National
   and State benchmarks;
4. explain why filters do not recalculate the threshold;
5. document that invalid data blocks the build even though unavailable rows
   have an analyst-visible insufficient-data classification;
6. update the source catalog and preflight with links and reduced dated
   evidence rather than duplicated source definitions;
7. update README current status and add one exact local query/verification
   path for the screening models;
8. update earlier guides only where statements that screening remains deferred
   became materially stale; and
9. keep publication, facility, orchestration, and BI work explicitly deferred.

### 9. Complete and verify the Plan 007 guide

Create the required network-free HTML guide according to
`docs/guides/README.md`:

1. explain a percentile, continuous interpolation, a threshold, nullable
   component flag, quadrant, denominator, source vintage, and lineage in plain
   language;
2. show the two independent components flowing into four complete quadrants
   plus insufficient data;
3. use one analogy that does not imply clinical risk or market opportunity;
4. show that equality belongs to the higher band and ties may make more than
   25% higher use;
5. make suppression/unavailability visibly different from zero;
6. explain that SVI is static 2022 context and facilities remain absent;
7. link to the specification, Plan 007, metric dictionary, relevant models,
   tests, source catalog, and prior foundation guides;
8. add static tests for semantic HTML, exact safe language, local links, no
   network assets, and required content;
9. perform desktop and 320-pixel narrow visual QA in light and dark modes;
10. exercise keyboard focus/native controls, print layout, reduced motion, and
    no-JavaScript first render; and
11. link the guide from README and `docs/guides/README.md` in numeric order
    only when the implementation is complete.

### 10. Close the plan without crossing its boundary

1. update this plan status to `Completed` with the exact completion date;
2. replace provisional evidence with a completion record containing exact
   fixture/full checks, semantic hashes, and canonical test totals;
3. run every focused and canonical offline verification command;
4. inspect Git diff/status and confirm no generated/raw artifacts appear;
5. confirm `pyproject.toml` and `uv.lock` are unchanged;
6. confirm every Plan 007 acceptance checkbox is satisfied;
7. explicitly state that facility context, Parquet publication,
   latest-successful pointer, orchestration, CI expansion, and BI remain
   deferred; and
8. propose a concise imperative commit message without committing or pushing.

## Verification commands

Focused screening loop:

```powershell
uv run pytest tests/integration/test_county_screening_dbt.py
uv run dbt parse --project-dir analytics --profiles-dir analytics
uv run dbt docs generate --project-dir analytics --profiles-dir analytics
```

The integration test must create a temporary credential-free dbt profile or
use the repository's existing exact helper. Do not require a committed
machine-specific `profiles.yml`.

Focused regression loop:

```powershell
uv run pytest tests/integration/test_cms_dimensional_dbt.py
uv run pytest tests/integration/test_cdc_svi_county_2022_dbt.py
uv run pytest tests/unit/docs/test_plan_007_guide.py
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

All commands are network-free after the locked environment is synchronized.
There is no live command in this plan. Do not contact CMS, CDC, Census,
facility, AWS, Power BI, or any authenticated service.

## Acceptance criteria

- [x] The candidate screening run derives from exactly one reconciled
  `raw.build_input_audit` row and carries `screening_run_id`,
  `input_set_sha256`, and `county_screening.v1` on every output.
- [x] Latest CMS year and current county membership are derived from governed
  models rather than hard-coded year/FIPS lists.
- [x] Historical-only county identities, older years, benchmarks, territories,
  and pseudo-counties cannot enter the screen or threshold.
- [x] T-016 passes: P75 uses only latest-year, current, reported, nonnull county
  `benes_op_dlys_pct` rows with equal county weight.
- [x] Continuous inclusive interpolation is fully specified and the four-value
  fixture returns `0.0325000000` as `decimal(38, 10)`.
- [x] Reported zero is eligible; suppression, blank, `NA`, null, unavailable,
  and invalid values are not used in P75.
- [x] Invalid source values still block the overall dbt build and are not made
  publishable by an insufficient-data label.
- [x] Equality to P75 is higher use, equality to SVI `0.75` is higher
  vulnerability, and tied threshold values are never arbitrarily split.
- [x] `int_county_screening_threshold` declares and tests its one-row grain,
  denominator, method, eligible/excluded counts, vintages, run identity, and
  both source lineages.
- [x] The fixed national threshold is identical on every county row and does
  not recalculate for State/county filters or SVI availability.
- [x] Official CMS State/National benchmark values never substitute for or
  influence the national county percentile.
- [x] `mart_county_screening` has one row per candidate run/current county and
  carries county labels, CMS denominator context, both component values and
  exact statuses, vintages, flags, bands, reason, quadrant, and lineage.
- [x] Unavailable component booleans are null rather than false; reported zero
  remains an available lower value when appropriate.
- [x] All four complete-data flag combinations map to the exact approved
  quadrant keys.
- [x] Every incomplete row maps to `insufficient_data` with the correct coarse
  reason while retaining detailed source statuses.
- [x] No complete quadrant contains a missing component and no complete row is
  classified as insufficient.
- [x] T-017 passes: the four quadrant counts plus insufficient-data count equal
  the screening mart/current county row count.
- [x] `audit_screening_quadrant_summary` always emits five unique categories,
  including zero-count categories, and reconciles category and marginal totals.
- [x] Screening rows reconcile one-to-one to Plan 006 latest CMS/SVI matched
  audit rows and exact fact values/source lineage.
- [x] No opaque score, weighting, rank, priority, recommendation, provider,
  site-selection, clinical, causal, or facility-derived field or claim is
  introduced.
- [x] The pinned Plan 006 input set reproduces the provisional 3,144 rows,
  2,148 eligible, 996 excluded, P75 `0.0086000000`, and category counts, or a
  legitimate difference is investigated and explicitly resolved before
  completion.
- [x] The same fixture and pinned input set reproduce identical threshold,
  model row counts, and ordered semantic checksums at fresh paths, satisfying
  the screening-output portion of T-020.
- [x] Failure injection for audit lineage, latest-year ambiguity, historical
  leakage, eligibility, State partitioning, invalid inputs, flag/quadrant
  consistency, and total reconciliation blocks the build with named evidence.
- [x] `docs/metric-dictionary.md` declares every screening grain, denominator,
  source unit, formula, method, status, vintage, lineage field, and limitation.
- [x] The Plan 007 guide is standalone, network-free, accessible, linked in
  numeric order, and passes static plus rendered visual QA.
- [x] Every older guide materially affected by completed screening logic is
  updated without rewriting historical plan scope.
- [x] README, source catalog, preflight, dbt docs, and Plan 007 agree on exact
  terminology and deferred work.
- [x] No raw source response, manifest, generated DuckDB/Parquet file, dbt
  output, row-level screening export, secret, patient information, or transient
  URL appears in Git status.
- [x] No dependency or lockfile change is made.
- [x] The locked Ruff and complete offline pytest/dbt fixture suite pass.
- [x] The completion record explicitly states that facility context,
  publication, orchestration, CI expansion, Power BI, and recommendations
  remain deferred.

## Completion record

Plan 007 completed on 2026-08-15 UTC with screening-definition version
`county_screening.v1`. The implementation derives the latest CMS year and
current county population from governed Plan 006 models, calculates one fixed
national continuous P75, classifies the two nullable components, and emits a
five-row category audit. It describes observed outpatient dialysis use among
Original Medicare beneficiaries alongside static social-vulnerability context;
it does not introduce a clinical or causal interpretation, score, rank, or
recommendation.

### Reproducible input identities

| Evidence set | Build ID | Input-set SHA-256 | CMS manifest | SVI manifest |
|---|---|---|---|---|
| Deterministic fixture | `plan-007-screening-fixture-001` | `4414e08ed23b52c93e65daf05a1f3a1fea41ff8ba97f0a8fe30146d75fd6d85d` | `cms-om-gv-screening-fixture-001` | `cdc-svi-screening-fixture-001` |
| Pinned Plan 006 input | `plan-007-pinned-screening-001` | `6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307` | `cms-om-gv-v2-live-20260815T015000Z` | `cdc-svi-2022-live-20260814T194625Z` |

Both evidence sets were built independently at two fresh database paths. The
fixture derived CMS year 2024, SVI vintage 2022 / ACS period 2018-2022, three
current and eligible counties, zero excluded counties, and P75
`0.0150000000`. Its five category counts were 0 higher-use/higher-vulnerability,
1 higher-use/lower-vulnerability, 2 lower-use/higher-vulnerability, 0
lower-use/lower-vulnerability, and 0 insufficient-data rows. The separate
four-value interpolation unit fixture returned `0.0325000000` exactly.

The pinned input derived CMS year 2024, SVI vintage 2022 / ACS period
2018-2022, 3,144 current counties, 2,148 threshold-eligible counties, 996
excluded counties, and national P75 `0.0086000000`. Its category counts were:

| Category | Count |
|---|---:|
| `higher_use_higher_vulnerability` | 354 |
| `higher_use_lower_vulnerability` | 188 |
| `lower_use_higher_vulnerability` | 259 |
| `lower_use_lower_vulnerability` | 1,347 |
| `insufficient_data` | 996 |

### Fresh-path semantic identities

Each SHA-256 below is the ordered semantic identity reproduced identically by
both fresh paths for its evidence set:

| Relation | Fixture SHA-256 | Pinned SHA-256 |
|---|---|---|
| `int_county_screening_threshold` | `dbc34e0dfcc13d46008ea6400f42725a6dd259da127bc0b4bbbc4663d9f4573c` | `3df5e14cfa6ce24e5161bf6ac67ce52397a7a762b816e0aa5f5935ee0e6945ac` |
| `mart_county_screening` | `bbde05e7c99b8bcf9d5d6f7c3dd20ff7ebc35bab39fb6a36e38cfd5e93793246` | `5fffc53ae6392119d445bf65b1d6d91dedddadd58e13ab75d445bd7531275166` |
| `audit_screening_quadrant_summary` | `5f768a90b2de13ddea7b925463d814f5a5bba8b16aa2cc044abf0a888f7107ff` | `1796d8d4002818a4ffc81386040e29f08421289000c9ba978eec50a6e51eacf1` |

### Verification and boundaries

- The focused pinned dbt selection `int_county_screening_threshold+` passed 94
  model, unit-test, and data-test results. `dbt parse` and `dbt docs generate`
  also completed; the project discovered 12 models, 309 data tests, one seed,
  three sources, and seven unit tests.
- The canonical locked handoff passed `uv sync --locked`, Ruff formatting and
  lint checks, and all 289 offline pytest tests in 16 minutes 19 seconds. The
  legacy CMS and SVI integration suites also passed together after their paired
  fixture adopted the required one-row build audit.
- The Plan 007 guide passed its four static accessibility, contrast, evidence,
  and internal-link tests; all 20 guide tests passed together. Browser QA
  inspected light and dark palettes at 1280 × 900 and the responsive layout at
  320 × 900, confirmed no page-level horizontal overflow, kept the wide table
  inside its own scroll region, showed visible focus, and exercised the native
  disclosure.
- No live source or other network call occurred. `pyproject.toml` and
  `uv.lock` are unchanged. Raw responses, manifests, generated DuckDB/Parquet
  files, dbt artifacts, logs, and row-level screening outputs remain ignored
  and absent from Git status.
- Deferred work remains explicit: facility contract/ingestion and auditable
  county assignment; Parquet publication and the latest-successful pointer;
  Airflow orchestration; CI expansion; Power BI; portfolio presentation,
  hosting, and optional AWS; and every provider ranking, site-selection,
  partnership, contracting, or other recommendation. Future facility context
  is due-diligence context only and cannot alter a Plan 007 threshold, flag, or
  quadrant.

## Stop conditions

Stop and request a specification or architecture decision if:

- the existing input database lacks one trustworthy `build_input_audit` row or
  its lineage cannot be reconciled to both facts;
- the derived latest CMS year is ambiguous or disagrees between `dim_year` and
  the Medicare fact;
- latest current CMS/SVI keys no longer reconcile one-to-one under Plan 006;
- more than one SVI vintage is present and selecting the intended static
  context would require a new policy;
- there are zero eligible CMS counties or continuous P75 is null/out of range;
- the same pinned input set does not reproduce P75 `0.0086000000` after a
  bounded investigation of method, eligibility, types, and input identity;
- a new upstream status token cannot be mapped without redefining source
  missingness or weakening a blocking validation;
- implementing the exact percentile method requires lossy float conversion or
  classification-time rounding;
- current implementation can only produce a State/filter-responsive threshold
  or beneficiary-weighted percentile;
- an invalid source value would have to be accepted as a successful
  insufficient-data row;
- a historical-only identity enters the latest current screen and cannot be
  excluded without changing the geography policy;
- facility context or publication semantics are required to make the core
  quadrant model internally valid;
- correct implementation requires a new dependency, live source refresh,
  external account, authentication, payment, or nonpublic data;
- generated row-level outputs cannot be kept outside version control;
- pinned row-count or semantic-checksum differences persist after bounded,
  evidence-backed investigation; or
- any required Plan 001-006 test would have to be weakened.

Do not silently change the percentile method, round the threshold before
classification, weight by beneficiaries, recalculate per State, use a CMS
benchmark row, treat missingness as zero/lower, drop a county with an inner
join, update provisional counts, or add facility/BI/publication work to make a
failing build appear complete.

## Autonomous execution boundary

This plan is suitable for an unattended goal. The inputs already exist as
verified, immutable local artifacts; all production changes and tests are
deterministic and network-free; no secret, account, GUI, dependency, commit,
push, or external side effect is required. The metric formulas, percentile
method, equality behavior, missingness truth table, category vocabulary,
expected pinned result, acceptance criteria, and stop conditions are explicit.

The execution goal is:

> Implement Plan 007 completely using red-green-refactor. Govern the combined
> build identity; calculate one fixed national county continuous P75 from
> latest-year, current, reported `BENES_OP_DLYS_PCT` rows; classify reported
> `RPL_THEMES >= 0.75`; build the run-scoped transparent county screening mart
> with nullable component flags, exact statuses, vintages, denominators,
> lineage, four complete-data quadrants, and insufficient-data reasons; build
> the five-category reconciliation audit; prove T-016, T-017, and deterministic
> fresh-path output on fixtures and the pinned Plan 006 input set; add the
> governed metric dictionary, model documentation, failure injection, and the
> standalone Plan 007 HTML guide; update affected repository documentation;
> and run the canonical locked offline verification. Make no network request,
> dependency change, commit, push, facility change, Parquet publication,
> pointer update, Airflow/CI/Power BI work, score, ranking, recommendation,
> clinical claim, or causal claim. Stop only at a listed stop condition;
> otherwise continue until every acceptance criterion is satisfied.

## Handoff

After Plan 007 is complete, the next dependency-ordered vertical slice should
establish the CMS Dialysis Facility source contract and immutable ingestion
path before attempting facility-to-county assignment. That later work should
retain CCN grain, facility measure availability/periods/denominators, and public
business-address lineage; it should defer Census remediation and county
facility aggregates until the facility raw/stage contract is independently
green. No later facility characteristic may alter the Plan 007 threshold,
component flags, or screening quadrant.
