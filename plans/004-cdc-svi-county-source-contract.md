# Plan 004: CDC/ATSDR SVI 2022 county source contract

**Status:** Completed 2026-08-14  
**Source ID:** `cdc_svi_county_2022`  
**Target duration:** 60-90 minutes  
**Depends on:** Completed Plans 001-003  
**Specification coverage:** Gate 0 plus the SVI portions of T-001 and T-002  
**Authoritative requirements:** `specs.md` sections 4, 5.1-5.3, 5.6, 6.1-6.2,
7-11, 14-18, and 20

## Outcome

Establish the executable raw-boundary contract for the 2022 U.S. county
CDC/ATSDR Social Vulnerability Index (SVI) layer. The completed increment will
prove that the official documentation, ArcGIS layer metadata, and bounded live
samples agree on the exact required fields, declared types, county grain, U.S.-
based ranking semantics, and static 2018-2022 ACS context before paginated
ingestion or dbt transformation is written.

The flow is:

```text
official CDC documentation + ArcGIS county-layer metadata
                         |
                         v
        pin exact labels, types, grain, and meanings
                         |
                         v
          validate a small synthetic raw fixture
                         |
                         v
       record a bounded, dated live-source smoke result
```

This plan completes only the source-contract boundary. It does not download the
full 3,144-row pinned snapshot, normalize `-999`, join SVI to CMS, calculate the
screening quadrant, or treat social vulnerability as a clinical or causal
measure.

## Why this is the next dependency

Plans 001-003 make the CMS Original Medicare source reproducible through a
typed county-year stage. The next decision component is `RPL_THEMES`, but the
project cannot safely build `dim_county`, `fct_svi_county`, the CMS-to-SVI
reconciliation, or the screening mart until the SVI county layer has an
executable contract.

This is the smallest dependency-ordered increment that fits an unattended work
session. It resolves field and denominator decisions now, without combining
them with ArcGIS pagination, immutable publication, dbt typing, or cross-source
joins. The following plan can then implement pagination and raw publication
against a stable contract instead of rediscovering source semantics inside an
extractor.

## Declared grain, denominators, vintage, and lineage

Declare these facts before implementation:

| Concern | Contract |
|---|---|
| Source grain | One row per `STCNTY` county FIPS in ArcGIS FeatureServer layer 1, `SVI2022 US county`. `GRASP_ID` is the transport object ID, not the analytical county key. |
| Canonical key | `STCNTY` remains five-character text matching `^[0-9]{5}$`; its first two characters must equal `ST`. District of Columbia is `11001`. |
| Geographic scope | The 50 states and District of Columbia only. Puerto Rico and other territories are outside the MVP. |
| Ranking denominator | `RPL_THEMES` and `RPL_THEME1` through `RPL_THEME4` are U.S.-based county percentile ranks on `[0,1]` when available. They are not state-based ranks. |
| Context-percentage denominators | Each retained `EP_*` field keeps its own source-defined population or household denominator. The percentages are not interchangeable, summable, or suitable for an unweighted combined score. |
| Vintage | SVI 2022, based on 2018-2022 ACS data. It is static context and must never be labeled as a 2024 or 2026 observation. |
| Lineage | Official CDC/ATSDR documentation URL, official ArcGIS service and layer identity, service item ID if supplied, metadata retrieval time, documentation hash, observed field metadata, and schema hash. |

The primary product use remains a transparent contextual component: high
social vulnerability means `RPL_THEMES >= 0.75` only after the later stage has
validated and typed the value. This plan does not implement that classification.

## Required field contract

The contract must validate exact ArcGIS labels and compatible ArcGIS type
families. It must allow and report additive fields while blocking missing,
duplicated, or incompatibly typed required fields.

| Field | Required meaning | Expected ArcGIS type family | Later analytical role |
|---|---|---|---|
| `GRASP_ID` | Layer object ID | OID/integer | Deterministic pagination and transport audit only |
| `ST` | Two-character state FIPS | String | Validate the county-key prefix |
| `STATE` | State name | String | Source geography label |
| `ST_ABBR` | State abbreviation | String | Source geography label |
| `STCNTY` | Five-character county FIPS | String | Canonical join key after validation |
| `COUNTY` | County name | String | Source geography label |
| `RPL_THEMES` | Overall U.S. county SVI percentile rank | Numeric | Primary social-vulnerability component |
| `RPL_THEME1` | Socioeconomic Status theme percentile rank | Numeric | Descriptive context |
| `RPL_THEME2` | Household Characteristics theme percentile rank | Numeric | Descriptive context |
| `RPL_THEME3` | Racial & Ethnic Minority Status theme percentile rank | Numeric | Descriptive context |
| `RPL_THEME4` | Housing Type & Transportation theme percentile rank | Numeric | Descriptive context |
| `EP_POV150` | Percentage of persons below 150% of the poverty threshold | Numeric | Interpretable socioeconomic context |
| `EP_UNINSUR` | Percentage uninsured in the source-defined civilian noninstitutionalized population | Numeric | Interpretable socioeconomic context |
| `EP_AGE65` | Percentage of persons aged 65 and older | Numeric | Interpretable household-characteristics context |
| `EP_DISABL` | Percentage with a disability in the source-defined civilian noninstitutionalized population | Numeric | Interpretable household-characteristics context |
| `EP_LIMENG` | Percentage of persons age 5+ who speak English less than well | Numeric | Interpretable household-characteristics context |
| `EP_NOVEH` | Percentage of households with no vehicle available | Numeric | Interpretable transportation context |

The six `EP_*` fields are deliberately a small contextual subset. They cover
clearly explainable socioeconomic, age/disability, language, and transportation
conditions without importing every SVI component into the MVP. They must retain
their exact official labels, units, and denominators. They must not be used to
create a new score, alter the screening quadrant, or imply causation.

If the current official documentation gives any field a materially different
name, definition, denominator, or type, stop under the conditions below rather
than silently substituting another variable.

## Contract behavior

### Metadata validation

- Resolve the official service and county layer from the durable service URL
  already named in `specs.md`; require layer ID 1 and the expected county-layer
  identity rather than selecting a similarly named tract, ZCTA, state-based, or
  theme-only layer.
- Validate the complete ordered ArcGIS `fields` array before reading samples.
- Treat duplicate field labels as blocking even if a mapping would overwrite
  one occurrence.
- Require the object-ID field advertised by the layer to be `GRASP_ID` and
  require it in the executable contract.
- Validate required fields by compatible ArcGIS type family: string, numeric,
  or object ID. Do not accept a numeric county FIPS.
- Allow additive fields, report them in deterministic sorted order, and include
  the complete observed field list in normalized schema evidence.
- Record, but do not hard-code as timeless, the layer's reported maximum record
  count and pagination capabilities for the next plan.

### Raw grain validation

- Require `ST`, `STATE`, `ST_ABBR`, `STCNTY`, `COUNTY`, and `GRASP_ID` to be
  present.
- Require nonblank state and county labels.
- Require `ST` to be exactly two ASCII digits and `STCNTY` to be exactly five
  ASCII digits, both retained as text.
- Require `STCNTY` to begin with `ST`; never repair a mismatch by numeric
  coercion, name matching, or ZIP logic.
- Preserve a leading-zero example such as `01001` and require District of
  Columbia to be `11001`.
- Reject territory state prefixes `60`, `66`, `69`, `72`, and `78` if they
  appear in this U.S. county layer.
- Require `GRASP_ID` to be parseable as a positive integer for transport
  ordering, but do not treat it as a stable business key outside this source
  snapshot.
- Detect duplicate `STCNTY` values across a complete observed sample or live
  reconciliation; no later transformation may silently deduplicate them.

### Deferred value rules

The fixture must contain rank values `0`, `0.75`, and `1`, the SVI unavailable
sentinel `-999`, and one out-of-range rank. Those cases prepare the next
transformation plan, but this raw contract does not type, normalize, bound, or
classify them. Specifically:

- `-999` remains distinguishable at the raw boundary and is not converted to
  zero;
- a later typed stage must convert `-999` to null with an explicit unavailable
  status;
- a later dbt test must require ranks to be null or within `[0,1]`; and
- the `0.75` boundary is not classified in this plan.

## Scope decisions

### Included

- A bounded, read-only request to the official ArcGIS service/layer metadata.
- A bounded count query and tiny attribute-only samples from distinct offsets;
  no geometry and no full raw-source retention.
- Verification of the current official 2022 documentation and data dictionary.
- A versioned local copy of the official documentation plus byte count and
  SHA-256 evidence, subject to the repository's source/licensing policy.
- A normalized schema snapshot containing the complete observed field list,
  type metadata, exact required semantic mapping, source URLs, layer identity,
  retrieval date, documentation provenance, and deterministic schema hash.
- A source-specific Python contract for metadata and raw grain validation.
- A small synthetic fixture that covers leading-zero FIPS, DC, `-999`, rank
  boundaries, an out-of-range rank, and an additive source field.
- Deterministic pytest coverage for the SVI portions of T-001 and T-002.
- Dated updates to `docs/source-catalog.md` and `docs/preflight.md` based only on
  checks actually performed.
- On completion, a matching standalone Plan 004 HTML guide linked from the root
  `README.md` after the Plan 003 guide.

### Excluded

- A full SVI download or committed full-source rows.
- Production ArcGIS pagination, page retries, empty-page termination, offset
  reconciliation, or immutable raw publication; those belong to Plan 005.
- Raw-to-DuckDB loading, dbt sources/models, or `-999` normalization.
- `fct_svi_county`, `dim_county`, the CMS-to-SVI join, the pinned 3,144/3,144
  reconciliation, P75 screening logic, or quadrant assignment.
- Tract, ZCTA, state-based, Puerto Rico, geometry, mapping, or spatial analysis.
- Cross-year SVI comparison or any claim that SVI is a current clinical measure.
- Facility data, geocoding, Airflow, Parquet publication, Power BI, AWS,
  machine learning, patient-level data, or PHI.
- A new runtime or development dependency.

## Planned repository artifacts

Exact filenames may be refined during red-green work, but responsibilities must
remain separated:

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/contracts/cdc_svi_county_2022.py` | Source-specific field/type and raw-grain contract. |
| `tests/unit/contracts/test_cdc_svi_county_2022_contract.py` | Deterministic T-001/T-002 contract tests. |
| `tests/fixtures/cdc_svi_county_2022/minimal.csv` | Synthetic raw-string fixture with representative edge cases. |
| `docs/source-schemas/cdc_svi_county_2022.schema.json` | Normalized, hashed official layer schema and required semantic mapping. |
| `docs/source-dictionaries/svi-2022-documentation.pdf` | Pinned official 2022 documentation, if retention is permitted. |
| `docs/source-catalog.md` | Grain, fields, units, vintage, lineage, limitations, and dated evidence. |
| `docs/preflight.md` | Dated implementation-machine live-source result. |
| `docs/guides/004-svi-source-contract-explained.html` | Required beginner-friendly completed-plan guide. |
| `README.md` | Completed status and Plan 004 guide link in numeric order. |

Do not refactor the CMS contract into a generic framework merely to share a few
types. Reuse an existing immutable data class only if the second source proves
that its semantics are genuinely identical and tests cover both contracts.

## Red-green-refactor execution sequence

### 1. Pin official meaning before code

Perform bounded official-source checks and record:

1. the service and layer identity for `SVI2022 US county`;
2. the full ordered field metadata, object-ID field, maximum record count, and
   supported query behavior;
3. the official 2022 documentation URL, content hash, and byte count;
4. exact definitions and denominators for the five ranks and six selected
   `EP_*` fields; and
5. explicit confirmation that the selected layer is U.S.-based county data,
   not a tract, ZCTA, state-based, or Puerto Rico dataset.

Create normalized schema evidence only from those official results. Do not put
transient query URLs, response dumps, or full source rows in Git.

### 2. Lock the smallest deterministic fixture

Create synthetic rows containing:

1. leading-zero FIPS `01001` with consistent `ST = 01`;
2. District of Columbia `11001`;
3. rank boundaries `0`, `0.75`, and `1` distributed across governed fields;
4. `-999` in at least one rank and one selected `EP_*` field;
5. an out-of-range rank reserved for the later stage test;
6. representative numeric zero distinct from `-999`;
7. one additive field; and
8. separate mutations for malformed, mismatched, duplicate, and territory FIPS
   failures.

Use synthetic names and values. Do not present fixture values as observations
about real counties.

### 3. Add failing schema-contract tests

Add the smallest failing tests proving that:

1. the verified official schema satisfies the required mapping;
2. removing each required field fails with a structured issue;
3. duplicating any required field fails deterministically;
4. changing string, numeric, or object-ID fields to an incompatible type fails;
5. additive fields pass and are reported in sorted order;
6. the advertised object-ID field must be `GRASP_ID`; and
7. the normalized schema and pinned documentation hashes reconcile to their
   committed evidence.

Implement only enough source-specific contract behavior to pass.

### 4. Add failing grain-contract tests

Add tests proving that:

1. `01001` remains five-character text;
2. `11001` is accepted for District of Columbia;
3. missing or blank keys and labels fail;
4. non-ASCII-digit, short, long, or numeric-coerced FIPS fail;
5. `ST` and the `STCNTY` prefix must agree;
6. territory prefixes fail;
7. `GRASP_ID` must be a positive integer-shaped transport value; and
8. duplicate county FIPS in an observed row set fail instead of being silently
   deduplicated.

Refactor only after these behaviors are green.

### 5. Run the separate bounded live smoke check

Use only official endpoints and a descriptive user agent. The smoke check must:

1. fetch layer metadata without authentication;
2. run a count-only query and record the observed total as dated evidence;
3. fetch tiny, attribute-only samples with explicit required fields,
   `returnGeometry=false`, deterministic `GRASP_ID` ordering, and offsets on
   opposite sides of the layer's page limit;
4. prove the leading-zero FIPS and field types survive JSON decoding;
5. compare live metadata with the executable contract; and
6. discard response bodies after reducing them to non-sensitive schema/count
   evidence.

The pinned 3,144-row expectation is evidence for the examined 2022 snapshot,
not a timeless assertion. If the observed count differs, investigate and
explain the upstream state; do not silently edit the expected value.

### 6. Refactor, document, and complete the guide

After the contract is green:

1. keep SVI naming and type-family logic narrow and readable;
2. document grain, every denominator, U.S.-based rank semantics, ACS period,
   unavailable sentinel, and static-vintage limitation;
3. update `docs/source-catalog.md` and `docs/preflight.md` with dated facts only;
4. create the network-free Plan 004 HTML guide according to
   `docs/guides/README.md`;
5. explain in the guide why SVI is context, not a clinical measure or causal
   explanation;
6. link the guide from the root README after Plans 001-003;
7. mark this plan `Completed` with test counts and concise evidence; and
8. inspect Git status for response dumps, full source data, caches, or generated
   databases before handoff.

## Verification commands

Focused red-green loop:

```powershell
uv run pytest tests/unit/contracts/test_cdc_svi_county_2022_contract.py
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

The contract tests and complete handoff loop must remain network-free. The live
smoke check must be an explicit separate command or narrowly scoped script; it
must not run during default pytest, dbt, or pull-request checks.

## Acceptance criteria

- [x] The official 2022 U.S. county layer and documentation are resolved from
  durable CDC/ATSDR and ArcGIS identifiers without authentication.
- [x] T-001 passes for SVI: every required field exists once with a compatible
  type; additive fields remain compatible and are reported.
- [x] T-002 passes for SVI: required grain keys are present and parseable,
  `STCNTY` is unique five-character text, and its prefix agrees with `ST`.
- [x] Leading-zero FIPS and District of Columbia `11001` survive the raw
  contract without numeric coercion.
- [x] Territory prefixes are rejected for the MVP U.S. county layer.
- [x] The required five ranks and six `EP_*` fields have exact source-backed
  definitions, units, and denominators in schema/catalog evidence.
- [x] The fixture preserves `-999`, zero, `0.75`, and an out-of-range rank for
  later transformation tests without claiming T-006 or T-010 is complete.
- [x] The live smoke check records dated layer identity, count, pagination
  capability, and bounded sample evidence without retaining full source rows.
- [x] The pinned documentation and normalized schema evidence have verified
  byte/hash provenance and contain no transient signed URL.
- [x] The Plan 004 guide is standalone, network-free, accessible, linked from
  the README in numeric order, and passes its static checks plus rendered visual
  QA.
- [x] No dependency changes, full source download, response dump, generated
  database, secret, or patient information appear in Git status.
- [x] The locked Ruff and complete offline pytest suite pass.

## Implementation record

Completed on 2026-08-14 without a dependency change.

- The official service resolved stable item
  `f2af3fd35858443293b75d5f73c7d4d3`, layer 1 `SVI2022 US county`, and
  object-ID field `GRASP_ID` without authentication. The layer reported 161
  fields, a 2,000-record maximum, pagination and ordering support, and a dated
  count of 3,144 rows.
- The pinned 17-page official documentation is 542,647 bytes with SHA-256
  `5636ae52e13ec201b90f4a31b55d12959d55784469e8c11662b64c03f09424fc`.
  Visual checks of the relevant pages confirmed the `-999` unavailable meaning,
  the U.S.-based overall and four theme ranks, the 2018-2022 ACS period, and the
  six selected percentage definitions and distinct denominators.
- The normalized schema records all 161 fields, their declared types and order,
  the exact 17-field semantic mapping, 144 compatible additions, official
  locators, document provenance, layer metadata, reduced live evidence, and
  canonical schema SHA-256
  `3bb2d1800f927dfe28f476320a67f7a000619a4bf49db22e306ce8fb7f7b6e3f`.
- The red step first produced the expected missing-module failure for the source
  contract and the expected missing-guide failure. The green implementation
  added structured T-001/T-002 validation, a synthetic raw-string fixture, and
  static guide checks. The focused Plan 004 suite finished with 80 passing
  tests.
- Tiny attribute-only samples at offsets 0 and 2,000 preserved `01001`,
  `01003`, `38017`, and `38019`. A separate reduced scan requested only
  `GRASP_ID`, `ST`, and `STCNTY` with geometry disabled and deterministic
  ordering. Its page sizes were 2,000 and 1,144; all 3,144 FIPS and object IDs
  were distinct; IDs increased from 1 through 3,144; `11001` was present; and
  no state-prefix mismatch or territory row appeared. No full metric rows or
  response dump were retained.
- Rendered guide QA covered a 1280-by-720 desktop viewport and a 390-by-844
  narrow viewport in the in-app browser. The narrow layout had no horizontal
  overflow and collapsed its flow and evidence grids to one column. Light and
  manual dark palettes, native controls, semantic landmarks, the skip target,
  print rules, and reduced-motion rules were present; all repository links are
  relative and the guide has no scripts or external dependencies.
- The exact offline handoff completed with `uv sync --locked`, 31 files already
  formatted, clean Ruff lint, and 205 passing pytest tests in 9.81 seconds.
  Git inspection found only the intended Plan 004 source, fixture, tests,
  evidence, catalog/preflight, guide, plan, and README changes.

## Stop conditions

Stop and request a specification or architecture decision if:

- the official service no longer resolves one unambiguous 2022 U.S. county
  layer;
- a required rank, geography field, or selected `EP_*` field is missing or has
  a materially different definition, denominator, or type;
- the official documentation and live layer metadata disagree materially;
- county FIPS is no longer supplied as five-character text or legitimate rows
  violate the repository geography policy;
- District of Columbia cannot be represented as `11001` without inventing a
  mapping;
- the layer contains unexpected territories or duplicate county FIPS that
  cannot be explained from official evidence;
- official documentation cannot be retained under the repository's documented
  source/licensing policy;
- public access now requires authentication, payment, or nonpublic data;
- bounded live attempts cannot distinguish an upstream failure from a local
  network restriction;
- a correct contract requires a dependency change; or
- a failing contract/test would have to be weakened to complete the plan.

Do not silently switch layers, infer definitions, coerce numeric FIPS, convert
`-999` to zero, update the pinned row expectation without explanation, or
describe SVI as kidney disease prevalence, unmet need, disease burden, an
intervention opportunity, or a causal factor.

## Autonomous execution boundary

This plan is suitable for an unattended goal. The work is source-specific,
bounded, and test-driven; default tests are deterministic; live access is
read-only and requires no account; dependency changes and downstream modeling
are explicitly excluded. The execution goal is:

> Implement Plan 004 completely using red-green-refactor, including official
> schema/documentation evidence, the SVI source contract, synthetic fixtures,
> deterministic tests, dated source-catalog/preflight updates, the matching
> standalone HTML guide, and all offline verification. Perform only the bounded
> read-only live checks named in the plan. Do not download or retain the full
> source, change dependencies, commit, push, start Plan 005, or proceed beyond
> the stated scope. Stop only at a listed stop condition; otherwise continue
> until every acceptance criterion is satisfied.

## Handoff

After Plan 004 is complete, Plan 005 should implement deterministic ArcGIS REST
pagination and immutable raw publication for `cdc_svi_county_2022`. It must use
explicit fields, `returnGeometry=false`, `GRASP_ID` ordering, pages no larger
than 2,000 records, verified offsets, complete record/count reconciliation,
distinct county FIPS, bounded transient-only retry, and run/content no-op
behavior. A later SVI staging plan must preserve raw values, convert `-999` to
null with an explicit unavailable status, enforce `[0,1]` rank bounds, and only
then support the CMS-to-SVI reconciliation and screening mart.
