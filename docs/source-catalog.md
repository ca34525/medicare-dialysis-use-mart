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
| Raw grain | `YEAR x BENE_GEO_LVL x BENE_GEO_CD x BENE_AGE_LVL` using CMS's raw geography-code representation |
| Primary county denominator | Original Medicare beneficiaries (`BENES_OM_CNT`) after later County + All filtering; this contract does not filter or calculate metrics |
| Primary screening field | `BENES_OP_DLYS_PCT`, observed outpatient dialysis use among Original Medicare beneficiaries |
| Access | Public CSV/API without authentication |
| Lineage | Official catalog -> stable dataset identity -> current API/data-viewer metadata and resolved version distribution; field definitions -> pinned official dictionary |

The version-specific CSV URL is retained only as observed provenance in the normalized schema snapshot. Resolution must begin with the official catalog or stable dataset identity; code must not treat that distribution URL as the durable locator.

The current metadata exposes 246 columns: 242 `NUMERIC` and four `TEXT`. The executable contract requires 13 fields and treats the other 233 observed fields as additive. Exact labels, definitions, declared types, full observed order, additive fields, type encoding, and hashes are recorded in `docs/source-schemas/cms_om_gv.schema.json`.

### Raw geography-code exception

The bounded current sample confirms `BENE_GEO_CD=""` for the National row. CMS also emits empty codes for State pseudo-rows `Territory` and `ZZ`. The raw contract therefore accepts an empty geography code only in those source contexts. County and ordinary State rows still require a nonblank code. County FIPS typing, scope filtering, District of Columbia handling, and removal of `UNKNOWN` pseudo-counties remain later transformation responsibilities.

### Missingness, denominator, and interpretation

- Read CSV/API values as raw strings at the contract boundary so leading zeros, `*`, blank, `NA`, and numeric zero remain distinct.
- The dictionary states that `*` suppresses variables where the beneficiary or user count is below 11. The current table metadata declares blank as missing, and `NA` appears in the bounded API sample.
- Percentage-labelled fields are represented as decimal proportions in the current sample; preserve that source scale until governed typing occurs.
- `OP_DLYS_MDCR_STDZD_PYMT_PC` adjusts for geographic payment-rate differences, not beneficiary health status.
- This source describes observed outpatient dialysis use among Original Medicare beneficiaries. It does not establish kidney disease prevalence, unmet need, disease burden, or an intervention or site-selection recommendation.

