# Plan 001: CMS Original Medicare Geographic Variation source contract

**Status:** Completed 2026-08-13  
**Source ID:** `cms_om_gv`  
**Target duration:** 60–90 minutes  
**Specification coverage:** Gate 0, T-001, and T-002  
**Authoritative requirements:** `specs.md` sections 5.1–5.4, 10.3, 11, 15, 18, and 20

## Outcome

Establish the first executable source contract for the CMS Original Medicare Geographic Variation dataset. The completed step will prove that the current official CMS catalog, data dictionary, and a bounded sample agree on the exact required source fields and grain keys before ingestion or transformation code is written.

This step completes T-001 and T-002 for `cms_om_gv`. It prepares representative cases for T-005 through T-007 but does not claim those later tests are complete.

## Why this comes next

The primary screening metric, observed outpatient dialysis use among Original Medicare beneficiaries, originates in this dataset. Implementing an extractor or transformation before confirming the current official labels, types, grain, suppression representation, and stable locator would turn assumptions into code and make future agents reproduce the same uncertainty.

## Invariants

- Resolve the dataset from official CMS metadata, beginning with `https://data.cms.gov/data.json` or the stable latest API.
- Use the stable dataset identity and official catalog or landing URL as the durable locator. A transient distribution URL may be recorded as observed provenance but must never be the only locator.
- Verify exact current labels against the official data dictionary; do not infer or guess unnamed fields from the specification's semantic descriptions.
- Treat all CSV values as raw strings at the contract boundary and preserve leading zeros and suppression tokens.
- Allow additive source columns and report them.
- Fail on missing or duplicated required columns, incompatible declared types, or absent and unparseable grain keys.
- Keep deterministic tests network-free. Perform the live CMS check separately and record its evidence.
- Commit only normalized schema evidence, the versioned official data dictionary, and small representative fixtures—never the full downloaded source file or a transient signed URL.

## Scope

### Included

- A bounded, read-only request to the official CMS catalog and a bounded data sample.
- Verification of the current official data dictionary URL and source vintage.
- A versioned local copy and SHA-256 hash of the official data dictionary.
- A normalized observed-schema snapshot with a deterministic schema hash.
- An explicit mapping from required semantic concepts to exact source labels.
- A small, hand-curated CSV fixture that preserves representative raw values.
- Source-contract validation code for required columns, additive columns, declared type compatibility, and grain-key parseability.
- Deterministic pytest coverage for T-001 and T-002.
- Updates to the source catalog and Gate 0 preflight evidence.

### Excluded

- Full-source download or immutable raw-snapshot publication.
- Retry, pagination, manifest, content-addressing, or atomic-publication infrastructure.
- Suppression normalization, numeric typing, county filtering, DC mapping, or `UNKNOWN` removal.
- dbt models, DuckDB loading, screening metrics, percentile logic, Airflow, Power BI, and CI.
- Live CMS requests in the default pytest command.
- Any other CMS, CDC, Census, or facility source.

## Planned artifacts

| Path | Purpose |
|---|---|
| `docs/source-catalog.md` | Human-readable source identity, official locators, vintage, access result, grain, and caveats. |
| `docs/source-schemas/cms_om_gv.schema.json` | Normalized current schema evidence, required semantic mapping, provenance, and schema hash. |
| `docs/source-dictionaries/cms_om_gv-<vintage>.pdf` | Pinned official dictionary used to resolve labels and definitions. |
| `src/kidney_care_mart/contracts/__init__.py` | Contract package boundary. |
| `src/kidney_care_mart/contracts/cms_om_gv.py` | Minimal source-specific contract and structured validation result. |
| `tests/fixtures/cms_om_gv/minimal.csv` | Small deterministic raw-string fixture containing the required representative cases. |
| `tests/unit/contracts/test_cms_om_gv_contract.py` | Offline T-001 and T-002 tests. |
| `docs/preflight.md` | Dated result of official metadata, dictionary, and bounded sample checks. |

Do not introduce a generic contract framework unless a concrete second source demonstrates the need. Keep the first implementation source-specific and easy to replace.

## Required semantic mapping

Discovery must resolve every row below to one exact official source label and definition before contract implementation begins.

| Semantic concept | Known label | Required evidence |
|---|---|---|
| Year | Verify exact label | Dictionary definition and declared type |
| Geography level | Verify exact label | Values distinguish county, state, and national rows |
| Geography code | `BENE_GEO_CD` | Text preservation and official definition |
| Geography description | Verify exact label | Dictionary definition and declared type |
| Age level | Verify exact label | Exact all-ages representation |
| Original Medicare beneficiary count | Verify exact label | Definition, unit, and missingness rules |
| Medicare Advantage participation rate | Verify exact label | Definition, scale, and unit |
| Dual-eligible percentage | Verify exact label | Definition, scale, and unit |
| Outpatient dialysis beneficiary share | `BENES_OP_DLYS_PCT` | Definition, scale, and suppression rules |
| Outpatient dialysis visits per 1,000 beneficiaries | `OP_DLYS_VISITS_PER_1000_BENES` | Definition, denominator, and unit |
| Standardized outpatient dialysis payment per capita | `OP_DLYS_MDCR_STDZD_PYMT_PC` | Definition, currency unit, and adjustment caveat |
| Acute hospital readmission percentage | Verify exact label | Definition, denominator, and scale |
| Emergency-room visits per 1,000 beneficiaries | Verify exact label | Definition, denominator, and unit |

If a required concept is absent, renamed, duplicated, or definitionally incompatible, stop and record the discrepancy. Do not choose a substitute field without an explicit specification decision.

## Execution sequence

### 1. Resolve and inspect official metadata

1. Request the official CMS catalog with a descriptive user agent and bounded timeout.
2. Locate exactly one dataset using the stable identity from `specs.md`, currently `6219697b-8f6c-4164-bed4-cd9317c58ebc`, corroborated by title and landing page.
3. Record the catalog URL, stable dataset ID, landing URL, current modified or release date, and resolved distribution or API URL.
4. Confirm the distribution is public and does not require authentication.
5. Download the official data dictionary through its canonical CMS URL to a temporary path, verify that it is a nonempty PDF, calculate its SHA-256 hash, and publish it under a versioned filename in `docs/source-dictionaries/`. Record the canonical URL, document date, byte hash, and required field definitions.
6. Make only a bounded sample request using documented CMS parameters. If the parameter semantics are unclear, stop and consult official documentation rather than guessing.

The live discovery command or script is evidence gathering, not production extraction code. Record the exact endpoint category and result in `docs/preflight.md`, excluding credentials, signed query strings, and full response bodies.

### 2. Create normalized schema evidence

Create `docs/source-schemas/cms_om_gv.schema.json` with stable key ordering and at least:

- logical source ID;
- official catalog, landing, dictionary, and stable API identifiers;
- retrieval timestamp in UTC;
- source release or modified date;
- complete observed column list and declared types;
- the required semantic-to-source mapping;
- declared grain keys;
- compatible type family for each required field;
- documented units and suppression tokens where applicable;
- separately listed additive columns; and
- a SHA-256 hash of the normalized schema payload, excluding volatile retrieval metadata from the hashed portion.

The snapshot records what was observed. The executable contract records what must remain compatible. Do not silently make every observed additive column required.

### 3. Add the deterministic fixture

Create the smallest readable fixture that includes:

- a county plus all-ages row with a leading-zero county code;
- a county age-subgroup row;
- state and national rows;
- a District of Columbia row;
- an `UNKNOWN` pseudo-county row;
- CMS `*`, blank, and `NA` values;
- a genuine numeric zero; and
- nonzero values for the required dialysis metrics.

Keep source labels and raw strings exact. Clearly mark the fixture as synthetic and representative; it must not be presented as real county data.

### 4. Write failing contract tests

Add tests before validation code for these behaviors:

1. The verified schema and representative fixture pass.
2. Removing each required column fails with the missing labels listed.
3. Adding an unknown column passes and reports the additive label.
4. Duplicating any required header fails.
5. Changing a required field to an incompatible declared type fails.
6. Every grain key is required.
7. A non-integer year fails grain-key parsing.
8. Blank geography level, geography code, or age level fails grain-key parsing.
9. The leading-zero county code remains the raw string `01001`.
10. Validation returns structured issues suitable for future logs rather than relying on assertion text or printed output.

Do not test county-only filtering, suppression-to-null conversion, or metric calculations here; those belong to later T-005 through T-007 work.

### 5. Implement the minimum contract

Implement only the source-specific behavior needed to make the tests pass:

- immutable required-column and grain-key definitions;
- explicit compatible type families;
- `validate_schema(...)` returning a structured result;
- `validate_grain_keys(...)` operating on raw string mappings; and
- deterministic ordering of reported errors and additive columns.

Do not coerce metric values or county codes. In particular, `BENE_GEO_CD` cannot be globally constrained to five digits at the raw contract boundary because the same source includes state and national rows; county FIPS validation occurs only after geography-level filtering in a later step.

### 6. Document and verify

1. Add the `cms_om_gv` entry to `docs/source-catalog.md`.
2. Update `docs/preflight.md` with the dated live access result and any limitations.
3. Run the focused tests during red–green development.
4. Run the complete offline quality loop before handoff.
5. Inspect Git status to confirm that no full source file, response dump, secret, cache, or transient URL was added.

## Verification commands

Focused development loop:

```powershell
uv run pytest tests/unit/contracts/test_cms_om_gv_contract.py
uv run ruff format --check src tests
uv run ruff check src tests
```

Required handoff loop:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

The live CMS check must be a separate, explicitly invoked command recorded in `docs/preflight.md`. It must not run during the default test suite.

## Acceptance criteria

- [x] The official catalog resolves exactly one intended dataset without authentication.
- [x] The current official dictionary and a bounded data sample are accessible.
- [x] Every required semantic concept maps to one verified exact source label and definition.
- [x] The stable catalog or dataset ID is the durable locator; a transient URL is not the only locator.
- [x] The normalized schema snapshot includes provenance, the complete observed schema, declared grain, compatible types, and a deterministic hash.
- [x] Missing, duplicate, and incompatible required columns fail with structured, deterministic issues.
- [x] Additive columns pass and are reported.
- [x] Missing or unparseable grain keys fail.
- [x] The representative fixture preserves leading zeros, suppression tokens, blank values, `NA`, and numeric zero as distinct raw strings.
- [x] T-001 and T-002 pass offline for `cms_om_gv`.
- [x] The full repository quality loop passes.
- [x] `docs/source-catalog.md` and `docs/preflight.md` contain dated, evidence-backed results.
- [x] No full source data, secret, cache, transient response dump, or generated database is tracked; only the versioned official dictionary is retained as source documentation.

## Stop conditions

Stop and request a specification decision if:

- the stable dataset identity is missing or matches multiple catalog entries;
- any required semantic concept has no exact official field;
- a field's current definition or unit conflicts with `specs.md`;
- the source now requires authentication, a paid license, or nonpublic data;
- the official dictionary cannot be retained under the project's documented source and licensing policy;
- the dictionary and observed schema disagree materially; or
- live access remains unavailable after bounded attempts and the result cannot be distinguished from a local network restriction.

Do not encode a guess, silently relax the contract, or update a pinned expectation merely to obtain a green test.

## Handoff

The next implementation step after this plan is complete is the `cms_om_gv` extractor and immutable raw-manifest path covering T-003 and T-004. That work should consume this contract rather than redefine field names, types, or grain assumptions.

## Completion record

- Official catalog resolution returned exactly one intended dataset under stable ID `6219697b-8f6c-4164-bed4-cd9317c58ebc`; current catalog metadata is modified 2026-05-15.
- The bounded live data-viewer check reported 36,994 rows and 246 columns. Filtered samples verified the National All row, leading-zero county code `01001`, and `UNKNOWN` pseudo-county representation without authentication.
- The official 2014-2024 dictionary is pinned in `docs/source-dictionaries/` and verified by SHA-256 in the normalized schema snapshot.
- T-001 and T-002 are implemented as network-free pytest coverage in `tests/unit/contracts/test_cms_om_gv_contract.py`.
- CMS's empty National geography code required an explicit raw-boundary clarification: the column must exist, but an empty value is accepted only for National and the observed State pseudo-rows `Territory` and `ZZ`; blank county and ordinary-State codes fail.
- Amendment 2026-08-14: the first full-file duplicate-grain check proved that
  `Territory` and `ZZ` reuse the same blank code for the same year and age. The
  raw transport grain now includes required `BENE_GEO_DESC`; the county fact
  grain is unchanged. This corrects the specification and normalized schema
  evidence without weakening duplicate-key publication blocking.
