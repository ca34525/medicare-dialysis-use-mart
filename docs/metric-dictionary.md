# Metric dictionary

This dictionary governs the derived metrics and classifications exposed by the
county screening mart. [`specs.md`](../specs.md) remains authoritative. Source
field definitions, raw contracts, and dated source evidence are in the
[`source catalog`](source-catalog.md).

## Product boundary

The screen combines two transparent components for analyst investigation:

1. observed outpatient dialysis use among Original Medicare beneficiaries; and
2. static CDC/ATSDR SVI 2022 social vulnerability context.

It is not kidney disease prevalence, unmet need, disease burden, intervention
opportunity, clinical risk, a composite score, a ranking, an automated
decision, or a final site-selection recommendation. Facility characteristics
are not present in Plan 007 and will never alter the screening quadrant.

## Model grains and run identity

| Model | Grain | Purpose |
|---|---|---|
| `int_county_screening_threshold` | One row per candidate screening run | Records the fixed national county threshold, eligibility counts, method, vintages, and lineage. |
| `mart_county_screening` | Candidate screening run × current county FIPS | Carries component values, exact statuses, nullable flags, quadrant, vintages, denominator context, and lineage. |
| `audit_screening_quadrant_summary` | Candidate screening run × five category keys | Reconciles all category and component marginal counts, including zero-count categories. |

The physical DuckDB input is run-scoped and contains one
`raw.build_input_audit` row. Plan 007 maps:

- `screening_run_id` to the combined `build_id`;
- `input_set_sha256` to the canonical ordered CMS/SVI input-set hash; and
- `screening_definition_version` to `county_screening.v1`.

These are candidate-run semantics. A later publication plan decides whether a
successful candidate is exported and updates a latest-successful pointer.

## Component 1: observed outpatient dialysis use

| Attribute | Contract |
|---|---|
| Source field | `BENES_OP_DLYS_PCT` |
| Model field | `benes_op_dlys_pct` |
| Grain | County FIPS × CMS calendar year |
| Unit | Source-reported proportion on `[0,1]` |
| Denominator | Original Medicare beneficiaries in the exact source county/year row |
| Denominator field | `benes_om_cnt`, with `benes_om_cnt_status` |
| Screening year | The one derived latest CMS year; never hard-coded in model SQL |
| Higher-use rule | Reported value `>= dialysis_use_p75_threshold` |
| Missing rule | Nullable flag and `insufficient_data`; never zero or lower-use imputation |

The required phrase is **“observed outpatient dialysis use among Original
Medicare beneficiaries.”** Standardized payment, visits per 1,000, and the
source-published State/National rates remain separate metrics and do not enter
this component.

### National county P75

Eligible values meet all four rules:

1. they belong to the derived latest CMS year;
2. the county is current and in scope in `dim_county`;
3. `benes_op_dlys_pct_status = 'reported'`; and
4. `benes_op_dlys_pct` is nonnull and already within the upstream-governed
   `[0,1]` range.

Each eligible county has equal weight. Original Medicare beneficiary counts do
not weight the percentile. Reported zero is eligible. Suppressed, blank, `NA`,
null, invalid, older-year, historical-only, State, and National rows are
excluded. Invalid source data also fails upstream quality tests, so it cannot
become a successful insufficient-data build.

For sorted eligible values `x[0] ... x[n-1]`:

```text
position = (n - 1) × 0.75
lower = floor(position)
upper = ceil(position)
weight = position - lower
P75 = x[lower] + weight × (x[upper] - x[lower])
```

The implementation uses DuckDB continuous inclusive interpolation and retains
`decimal(38, 10)` precision. The deterministic values `0.01`, `0.02`, `0.03`,
and `0.04` produce `0.0325000000`. Classification uses the unrounded value.
Equality is higher use. Ties can therefore place more than exactly 25% of
eligible counties in the higher band; no ranking or arbitrary tie-break is
applied.

The threshold is calculated once per run and repeated on every county row. A
State, county, quadrant, or later BI filter does not recalculate it.

## Component 2: static social vulnerability context

| Attribute | Contract |
|---|---|
| Source field | `RPL_THEMES` |
| Model field | `rpl_themes` |
| Grain | County FIPS × SVI vintage |
| Unit | U.S.-based county percentile rank on `[0,1]` |
| Source vintage | SVI 2022 |
| Underlying period | 2018-2022 ACS |
| Higher-vulnerability rule | Reported value `>= 0.75` |
| Missing rule | Nullable flag and `insufficient_data`; never zero or lower-vulnerability imputation |

Exact `0.75` is higher vulnerability, and reported zero is valid lower
vulnerability. Plan 007 does not re-rank SVI, calculate a State percentile, or
compare ranks across vintages. SVI 2022 is static context, not a 2024, 2026, or
trend observation.

## Component availability and bands

| Condition | Boolean flag | Band |
|---|---:|---|
| Reported value at or above the component threshold | `true` | `higher_use` or `higher_vulnerability` |
| Reported value below the component threshold | `false` | `lower_use` or `lower_vulnerability` |
| Suppressed, unavailable, null, or invalid | null | `insufficient_data` |

`is_dialysis_use_threshold_eligible` is true only when the CMS component is
reported and nonnull. `is_higher_observed_dialysis_use` and
`is_higher_social_vulnerability` are nullable; missing never becomes false.

The source-specific fields remain beside these derived bands:

- CMS: `reported`, `suppressed`, `unavailable_blank`, `unavailable_na`, or a
  build-blocking invalid status;
- SVI: `reported`, `unavailable_sentinel`, `unavailable_null`, or a
  build-blocking invalid status.

## Screening categories

| CMS component | SVI component | `screening_quadrant` |
|---|---|---|
| Higher use | Higher vulnerability | `higher_use_higher_vulnerability` |
| Higher use | Lower vulnerability | `higher_use_lower_vulnerability` |
| Lower use | Higher vulnerability | `lower_use_higher_vulnerability` |
| Lower use | Lower vulnerability | `lower_use_lower_vulnerability` |
| Either component unavailable | Any | `insufficient_data` |

The first four categories require two available components and have
`screening_data_status = 'complete'`. Incomplete rows preserve the available
component but do not receive a complete quadrant. Their coarse reason is one
of:

- `dialysis_use_component_unavailable`;
- `social_vulnerability_component_unavailable`; or
- `both_components_unavailable`.

The exact component status fields explain the underlying suppression or
unavailability. Category display order is neutral layout metadata, not a
priority rank.

## Geography and lineage

The screening denominator begins with current `dim_county` rows. Historical
CMS-only identities never enter. Every screening row must also have one
`matched` latest-current Plan 006 reconciliation row with exactly one CMS row
and one SVI row.

Each row carries:

- current county and State labels plus five-character county FIPS;
- CMS year, SVI vintage, and ACS period;
- CMS manifest ID, content SHA-256, retrieval time, and modified date;
- SVI manifest ID, snapshot SHA-256, retrieval time, and modified date; and
- candidate run ID, input-set SHA-256, and screening-definition version.

## Reconciliation and failure behavior

T-016 requires that P75 use only current latest-year reported county values.
T-017 requires the four complete quadrant counts plus insufficient-data count
to equal the screening row count. The five-row audit also reconciles:

- complete and insufficient totals;
- higher/lower CMS marginal counts;
- higher/lower SVI marginal counts;
- threshold eligible and excluded counts; and
- one fixed threshold, year, vintage, run, and lineage identity.

Duplicate build audits, lineage mismatches, invalid values, geography
mismatches, historical leakage, threshold drift, inconsistent flags, and
nonreconciling totals block the dbt build. No failed candidate updates a publish
pointer because publication is outside Plan 007.

## Pinned Plan 007 evidence

On 2026-08-15, two fresh local databases independently reverified and loaded
the same Plan 006 CMS/SVI manifests at input-set SHA-256
`6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307`.
Both produced:

| Evidence | Result |
|---|---:|
| Current screening rows | 3,144 |
| P75-eligible CMS rows | 2,148 |
| P75-excluded CMS rows | 996 |
| Continuous national county P75 | `0.0086000000` |
| Higher use / higher vulnerability | 354 |
| Higher use / lower vulnerability | 188 |
| Lower use / higher vulnerability | 259 |
| Lower use / lower vulnerability | 1,347 |
| Insufficient data | 996 |

Ordered semantic SHA-256 values matched between both fresh paths:

| Relation | SHA-256 |
|---|---|
| `int_county_screening_threshold` | `3df5e14cfa6ce24e5161bf6ac67ce52397a7a762b816e0aa5f5935ee0e6945ac` |
| `mart_county_screening` | `5fffc53ae6392119d445bf65b1d6d91dedddadd58e13ab75d445bd7531275166` |
| `audit_screening_quadrant_summary` | `1796d8d4002818a4ffc81386040e29f08421289000c9ba978eec50a6e51eacf1` |

These are dated pinned-snapshot results, not timeless national constants,
clinical findings, rankings, or recommendations. Full raw rows and generated
databases remain ignored.

## Deferred work

Plan 007 does not provide facility context, Parquet publication,
`latest-successful-run`, Airflow, CI expansion, Power BI, BI reconciliation,
portfolio findings, hosting, or optional AWS infrastructure. A later facility
slice may add due-diligence columns only after independent contracts and
geography coverage gates; it must not change this threshold or quadrant.
