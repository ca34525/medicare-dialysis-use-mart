# Plan 008: CMS Dialysis Facility source contract and immutable ingestion

**Status:** Completed 2026-08-15 UTC

**Source ID:** `cms_dialysis_facility`

**Depends on:** Completed Plans 001-007

**Recommended delivery boundary:** One cohesive implementation commit after all
acceptance checks pass; do not create that commit unless the user explicitly
requests it

**Expected size:** Approximately one Plan 005-sized slice; this plan reuses the
existing HTTP and immutable-manifest primitives but adds a broad current-source
contract, Provider Data Catalog resolution, facility-grain reconciliation, and
new live-source evidence

**Specification coverage:** The CMS Dialysis Facility portion of Gate 0 and
Milestone 1; T-001 through T-004 for the current full-CSV transport; the raw
distinct-CCN foundation for T-019; fixture preparation only for T-012 and T-013

**Authoritative requirements:** `specs.md` sections 2-3, 5.1-5.3, 5.5, 6.3,
7-11, 14-18, and 20

## Completion record

Contract `cms_dialysis_facility.raw.v1`, normalized schema SHA-256
`e87cf25487005a81c8af015b4256da6a0da4205a369c2406cb3ff9b399ceec0f`,
and the July 2026 dictionary at SHA-256
`64348a21e3c98b9cb5b915a2243fb3a54b452ca61943c8f9f1eadf7429176fa0`
are implemented and reconciled. On 2026-08-15 UTC, the explicit live extractor
and an independent disk reread reconciled the API count, 7,490 complete CSV
rows, and 7,490 distinct textual CCNs. The 7,263,788-byte source had SHA-256
`02a7155f9797fe3194f220e765eb8ac511cbc1402e286c3e235a3157ba7cee5f`;
a second run reused the verified blob with `content_noop: true`.

The strengthened focused loop passed 134 tests. Canonical verification
completed `uv sync --locked`, clean Ruff format and lint checks, and 389
passing pytest tests in 951.41 seconds. The final code independently reread
both live manifests and reproduced the 7,490-row/hash evidence and second-run
content no-op. Generated live data and manifests remain ignored and untracked.
Automated HTML, accessibility, link, contrast, responsiveness-rule, print-rule,
and reduced-motion-rule checks passed. On 2026-08-15, the user confirmed the
rendered desktop/narrow, light/dark, keyboard/focus, overflow, print, and
reduced-motion inspection.

This completion ends at the verified raw-source boundary. Typing, T-012 and
T-013, facility dimensions and facts, county assignment, Census remediation,
T-015, T-018, complete T-019 reconciliation, screening enrichment, mart
publication, Airflow, and Power BI remain explicitly deferred. Facility
business location is not patient residence, and no quality score, rank,
recommendation, clinical claim, causal claim, or screening-quadrant change was
introduced.

## Outcome

Establish a versioned executable contract for the current CMS Dialysis
Facility - Listing by Facility dataset, then use that contract to publish the
unchanged official full CSV as an immutable content-addressed raw snapshot with
a canonical run manifest.

The completed flow will be:

```text
official CMS Provider Data Catalog + current dictionary
                         |
                         v
resolve stable dataset 23ew-n7w9 and one current full CSV
                         |
              +----------+----------+
              |                     |
              v                     v
 normalized schema evidence   synthetic raw fixture
              |                     |
              +----------+----------+
                         |
                         v
 versioned facility contract: required fields + one-row-per-CCN grain
                         |
                         v
 stream current CSV to a same-volume temporary file
                         |
                         v
 verify bytes, headers, types, rows, distinct CCNs, and hashes
                         |
                         v
 atomically publish immutable blob + run-scoped manifest
```

This plan proves which current facility bytes were received and that the raw
source contains the required identity, public business-location, capacity,
ownership, modality, rating, hospitalization, readmission, and survival
fields. It does not type those values, interpret availability codes, assign a
county FIPS, calculate facility metrics, enrich the county screen, publish
Parquet, or update `latest-successful-run`.

## Why this is the next reasonable step

Plans 001-007 completed the CMS/SVI analytical spine and transparent county
screen. The bounded product question still requires current facility context
for analyst due diligence, but facility data cannot safely enter the mart until
the project can prove all of the following at the raw boundary:

1. the current official dataset is resolved from durable CMS metadata rather
   than a version-specific download URL;
2. every required semantic concept maps unambiguously across the dictionary,
   Provider Data Catalog metadata, API field name, and downloadable CSV header;
3. the current snapshot has exactly one raw row per textual CCN and does not
   lose leading zeros;
4. facility quality estimates remain coupled to their availability codes,
   measure periods, denominators, categories, and confidence limits; and
5. a failed or partial transfer cannot become a trusted input to later facility
   geography or aggregation work.

The Plan 007 handoff explicitly places this contract and immutable ingestion
before facility-to-county assignment. Reusing the existing transport and
manifest foundations keeps the slice small enough to verify independently and
prevents geography complexity from obscuring source-contract failures.

## Planning-time public evidence

The implementation must repeat and record its own bounded live checks. The
following observations only justify the plan and must not become timeless test
constants:

- On 2026-08-15, the official
  [Dialysis facilities topic page](https://data.cms.gov/provider-data/topics/dialysis-facilities)
  identified the current Listing by Facility release as 2026-07-15, modified
  2026-06-16, with the next update planned for 2026-10-28.
- The official
  [dataset page](https://data.cms.gov/provider-data/dataset/23ew-n7w9)
  advertised stable identifier `23ew-n7w9`, 7,557 rows, 142 columns, and a full
  CSV download without authentication.
- The current official
  [Dialysis Facility Care Compare data dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/dialysis/DF_Data_Dictionary.pdf)
  identifies the July 2026 release and documents CCN, facility identity,
  location, capacity, ownership, modalities, star-rating availability, and the
  required hospitalization, readmission, and survival measure families.
- The 7,557-row catalog observation differs from the 7,490 unique-CCN snapshot
  examined in `specs.md`. Section 5.2 already defines that earlier count as
  pinned evidence rather than a timeless constant. Implementation must explain
  the dated upstream change and reconcile the current file; it must not weaken
  uniqueness or silently replace the specification's historical observation.

No live response body, full CSV, transient distribution URL, or generated
manifest was retained while writing this plan.

## Declared grain, denominators, vintage, and lineage

### Raw grain

- The source snapshot is expected to contain one row per CMS Certification
  Number (CCN).
- CCN is a textual business identifier. It must never be inferred as a number,
  stripped of leading zeros, or replaced by facility name, address, phone, ZIP,
  or a generated row number.
- The complete raw business grain is `source_snapshot_sha256 x ccn`; within one
  downloaded snapshot, CCN must be nonblank and unique.
- The executable format rule for CCN must be derived from the current official
  dictionary and a complete live scan. If official evidence supports only
  nonblank text plus uniqueness, the contract must not invent a narrower width
  or numeric rule.
- The raw snapshot may contain territories or other rows later excluded from
  the MVP. Ingestion preserves the official bytes; scope filtering belongs to
  the typed staging/geography plan.

### Denominators and measure companions

This plan derives no metric and presents no facility estimate as a KPI. It
requires the source fields needed to keep each later estimate interpretable:

| Measure family | Period | Availability | Category | Denominator | Estimate and interval |
|---|---|---|---|---|---|
| Patient survival / standardized mortality | `DATE_SMR` | `PTSURV_C` | `DFCMORTTEXT` | `RDSMZ_F` patients | `SMR_RATE_F`, `SMR_RATE_LCI_F`, `SMR_RATE_UCI_F` |
| Hospitalization | `DATE_SHR` | `PTHOSP_C` | `DFCHOSPTEXT` | `RDSHY4_F` patients | `SHR_RATE_F`, `SHR_RATE_LCI_F`, `SHR_RATE_UCI_F` |
| Hospital readmission | `DATE_SRR` | `PTREAD_C` | `DFCSRRTEXT` | dictionary field currently shown as `INDEXY4_f` index discharges | `SRR_RATE_F`, `SRR_RATE_LCI_F`, `SRR_RATE_UCI_F` |

The exact case-sensitive dictionary names, friendly labels, CSV headers, and
API field names must be verified during implementation. A spelling shown in
this planning table is not permission to guess when official surfaces differ.

The future typed model must use eligible denominators and availability rules;
it must not average risk-standardized outcomes into a county quality score.
This raw plan merely guarantees that all companion fields travel together.

### Source vintage

- The dataset is a current quarterly snapshot, not a historical reconstruction.
- Record catalog release date, catalog modified date, retrieval timestamp, and
  content hash separately.
- Preserve each measure's raw period field. The three required outcome families
  may cover different windows even within the same quarterly source release.
- Do not relabel a measure period as the file release date or retrieval date.
- A future source refresh creates a new immutable snapshot; it never overwrites
  or retroactively relabels an older blob or manifest.

### Lineage

Every accepted snapshot must retain or derive:

- logical source ID and contract version;
- official Provider Data Catalog URL and stable dataset ID;
- official metadata and dictionary URLs;
- resolved current full-CSV URL as observed run lineage, never as the only
  locator in production code;
- source release and modified dates;
- UTC retrieval timestamp;
- HTTP ETag and Last-Modified when supplied;
- exact response byte count and SHA-256;
- CSV data-row count and distinct CCN count;
- complete ordered header and declared metadata field lists;
- canonical schema and header hashes;
- dictionary document byte count and SHA-256;
- extractor version, pipeline run ID, blob path, and content-no-op status; and
- sorted additive-field and compatible-schema-drift reports.

## Product and safety boundaries

- Facility rows are current public provider/business data used only for
  due-diligence context.
- Facility presence is not evidence of patient residence, service catchment,
  disease prevalence, unmet need, disease burden, intervention opportunity, or
  expected demand.
- No patient-level data, PHI, claims-line data, synthetic patient record, or
  patient targeting is permitted.
- Public facility addresses and phone numbers may be retained only as source
  lineage for the documented analytical purpose.
- No facility characteristic may change the Plan 007 threshold, component
  flags, or screening quadrant.
- Do not calculate a facility quality score, county quality score, provider
  rank, partnership recommendation, contracting recommendation, or final
  site-selection result.
- Preserve raw availability codes, periods, denominators, categories,
  estimates, and confidence limits. A blank or unavailable value is not zero.
- Do not interpret, type, bound, compare, or aggregate facility measures in
  this plan.
- Do not assign county FIPS, fuzzy-match county names, use ZIP as a county key,
  call the Census Geocoder, or create a geography quarantine in this plan.
- Keep default tests deterministic and network-free. Live CMS access is an
  explicit, separate completion check.
- Keep AWS, hosting, streaming, machine learning, Airflow, Power BI, and public
  publication outside this slice.

## Source contract

### Stable source identity

The resolver must begin with the official CMS Provider Data Catalog metadata
surface, currently `https://data.cms.gov/provider-data/data.json`, or the
official metastore record for stable dataset ID `23ew-n7w9`. It must:

1. select exactly one dataset by stable ID;
2. corroborate the Listing by Facility title and official landing page;
3. select one current complete CSV distribution;
4. reject state-average, national-average, patient-survey, archive bundle,
   HTML table, and similarly named dialysis datasets;
5. record the resolved distribution URL only as run lineage; and
6. fail rather than accept an arbitrary caller-supplied or stale hard-coded
   download URL as the source of truth.

The production transport for this plan is the official full CSV. Record it as
`transport_mode: full_csv` and `page_count: 1`. Do not claim multi-page API
coverage. If CMS no longer exposes a complete CSV, stop and make an explicit
architecture decision before implementing the specification's optional
datastore pagination path of at most 1,500 rows per request.

### Required semantic mapping

Create one normalized mapping for every required concept below. Each entry must
record the dictionary variable name, dictionary label and definition,
downloadable CSV header, Provider Data API field name when available, declared
type/maximum length, compatible type family, unit, and missingness/availability
companion.

#### Facility identity, public business location, and characteristics

| Semantic concept | Current dictionary variable | Contract requirement |
|---|---|---|
| CCN | `PROVFS` | Textual unique grain key; leading zeros preserved |
| Facility name | `QDFC_PROVNAME` | Raw source identity label |
| Address line 1 | `PHYADDR1` | Public business-address lineage |
| Address line 2 | `PHYADDR2` | Optional public business-address lineage |
| City | `PHYCITY` | Raw source location string |
| State | `STATE` | Raw postal code; no county assignment here |
| ZIP | `PHYZIP` | Raw text only; never a county key |
| Source county/parish | `PHYCOUNTY` | Raw text only; no fuzzy matching here |
| Telephone | `PHONENUM` | Public business contact lineage only |
| Ownership/profit status | `OWNTYPE` | Raw source category |
| Chain-owned flag | `CHAINYN` | Raw source category |
| Chain organization | `CHAINNAM` | Raw source label |
| Dialysis stations | `TOTSTAS` | Raw count string; typing deferred |
| In-center hemodialysis | `HD` | Raw modality availability |
| Peritoneal dialysis | `PD` | Raw modality availability |
| Home hemodialysis training | `HOMEHD` | Raw modality availability |
| Certification date | `CERTDATE` | Raw identity/context date |
| Five-star period | `DATE_FIVE_STAR` | Rating period travels with rating |
| Five-star rating | `FIVE_STAR` | Raw rating string; T-012 deferred |
| Five-star availability | `FIVE_STAR_C` | Availability travels with rating |

#### Required outcome families

Require all seven companion fields for each of the survival, hospitalization,
and readmission families listed in the denominator table above. A family is
not contract-complete if its estimate exists but its period, availability,
category, denominator, lower confidence limit, or upper confidence limit is
missing.

Do not require every one of the current source's roughly 142 columns merely
because it exists today. The immutable raw blob preserves all columns. The
executable v1 contract requires the bounded MVP set above; other columns are
compatible additions and are reported deterministically.

### Metadata and CSV compatibility

- Required fields must appear exactly once on every official surface used by
  the mapping.
- A required field's dictionary definition and unit must agree with the
  specification's semantic requirement.
- Text, integer/count, numeric/rate, and date/period fields must have explicitly
  compatible declared type families.
- The contract targets actual full-CSV headers, not an assumed dictionary
  variable name or web-table slug.
- If CMS exposes different names across dictionary, API, and CSV surfaces, the
  normalized mapping must record the relationship explicitly and prove it is
  one-to-one.
- Required-column removal, duplicate headers, ambiguous mapping, or an
  incompatible declared type blocks publication.
- Additive columns pass and are reported in stable sorted order. Reordering or
  additive drift changes evidence hashes but does not silently redefine the
  required contract.
- Raw values are not coerced during contract validation. Except for the CCN
  grain rules established from official evidence, blank and unavailable raw
  values remain representable for later typed handling.

### Contract versioning

Name the initial executable contract `cms_dialysis_facility.raw.v1` or an
equivalent explicit version. The manifest must store that version and the
normalized schema-evidence hash.

If a later refresh changes a required label, type, definition, or unit, do not
edit historical manifests or pretend the old contract observed the new shape.
Either prove backward compatibility under v1 or create a reviewed v2 contract
and migration plan.

## Scope decisions

### Included

- Bounded, read-only checks of official Provider Data Catalog metadata, the
  current dictionary, and a tiny current sample.
- A versioned local copy of the official dictionary, subject to the existing
  source/licensing policy, with byte count and SHA-256 evidence.
- Normalized schema evidence containing the complete observed source schema and
  the exact bounded required semantic mapping.
- A source-specific raw contract for required metadata, type compatibility,
  additive drift, and one-row-per-CCN grain validation.
- A small synthetic fixture containing representative identity, location,
  capacity, modality, rating, outcome, missingness, and duplicate-key cases.
- Stable Provider Data Catalog resolution and selection of the complete current
  full CSV.
- Reuse of the existing bounded HTTP, unchanged-byte streaming, canonical
  hashing, path-safety, immutable-blob, and run-manifest primitives.
- Source-specific full-file validation, row/distinct-CCN reconciliation, and
  manifest evidence.
- Atomic publication, same-content reuse, same-run idempotency, and conflict
  blocking under `data/raw/`.
- Network-free pytest coverage for the facility portions of T-001 through T-004.
- One explicit live extraction after offline tests are green, followed by
  independent disk reconciliation and concise dated evidence.
- Source catalog, preflight, data-layout, completed-plan guide, README, and plan
  completion updates.

### Excluded

- DuckDB raw loading or a typed facility staging model.
- Parsing dates, counts, booleans, categories, ratings, estimates, denominators,
  availability codes, or confidence intervals.
- T-012 star-rating bounds and T-013 confidence-interval/period ordering; this
  plan only preserves the raw cases needed by those later tests.
- `dim_facility`, `fct_facility_quality_snapshot`,
  `fct_county_facility_snapshot`, or `mart_county_screening` enrichment.
- Exact/alias/manual facility-to-county matching, Census Geocoder calls,
  `match_method`, `match_status`, coverage thresholds, Connecticut handling,
  or `quarantine_facility_geography`.
- T-015, T-018, or complete T-019 claims. Only the raw distinct-CCN term needed
  by later reconciliation is established here.
- Parquet export, atomic mart publication, `latest-successful-run`,
  `audit_pipeline_run`, Airflow, Docker, GitHub Actions, Power BI, or BI
  reconciliation.
- Historical reconstruction from the CMS dialysis archives.
- Patient-level data, claims-line data, PHI, clinical inference, causal claims,
  scores, ranks, recommendations, or automated decisions.
- A new runtime/development dependency or a broad extractor-framework rewrite.

## Generated storage layout

Reuse the existing immutable raw layout with a new source-specific manifest
directory:

```text
data/raw/
|-- blobs/
|   `-- sha256/
|       `-- <content-sha256>.csv
|-- manifests/
|   `-- cms_dialysis_facility/
|       `-- <run-id>.json
`-- .tmp/
    `-- <run-id>/
```

The blob path depends only on the content SHA-256. A run manifest references
the verified blob using a safe relative path. A later run with identical bytes
reuses the existing verified blob and records `content_noop: true`; it does not
overwrite either run's lineage.

All generated full-source data and manifests remain ignored. Commit only
fixtures, contracts, normalized schema evidence, the official dictionary if
permitted, tests, and documentation.

## Facility manifest contract

Reuse the canonical manifest behavior established in Plans 002 and 005. Extend
the manifest format only when facility-specific evidence cannot be represented
without ambiguity, and preserve backward reading/validation of existing CMS and
SVI manifests.

The facility run manifest must contain at least:

- manifest format version and facility raw-contract version;
- logical source ID `cms_dialysis_facility`;
- pipeline run ID and extractor version;
- official catalog, landing, metadata, and dictionary URLs;
- stable dataset ID `23ew-n7w9`;
- resolved current full-CSV URL as observed lineage;
- retrieval timestamp in UTC;
- source release and modified dates;
- HTTP ETag and Last-Modified when present;
- content SHA-256 and exact byte count;
- CSV data-row count, excluding the header;
- distinct nonblank CCN count and the governed CCN source header;
- transport mode `full_csv`, `page_count: 1`, and record count;
- complete ordered CSV headers and observed metadata fields/types;
- canonical schema hash and actual-header hash;
- normalized schema-evidence and dictionary hashes;
- sorted additive columns and compatible drift observations;
- safe relative content-addressed blob path; and
- `content_noop` / existing-blob reuse state.

Canonical serialization remains UTF-8 JSON with sorted keys, stable list
ordering, and a final newline. Volatile retrieval timestamps are lineage but
must not enter hashes intended to describe source schema semantics.

## Planned repository artifacts

Exact internal names may be refined during red-green work, but responsibilities
must remain separated:

| Path | Purpose |
|---|---|
| `src/kidney_care_mart/contracts/cms_dialysis_facility.py` | Facility required-field, metadata-mapping, and raw CCN-grain contract. |
| `src/kidney_care_mart/extract/cms_dialysis_facility.py` | Official metadata resolution and source-specific full-CSV extraction orchestration. |
| `src/kidney_care_mart/extract/http.py` | Reused bounded transport behavior; change only when a tested shared gap exists. |
| `src/kidney_care_mart/extract/manifest.py` | Reused canonical immutable publication; evolve compatibly only if required. |
| `tests/fixtures/cms_dialysis_facility/catalog.json` | Minimal official-shaped metadata with one intended dataset and one current CSV. |
| `tests/fixtures/cms_dialysis_facility/minimal.csv` | Synthetic raw-string contract fixture with facility edge cases. |
| `tests/fixtures/cms_dialysis_facility/download.csv` | Small complete-download fixture for extraction and manifest tests. |
| `tests/unit/contracts/test_cms_dialysis_facility_contract.py` | Network-free facility T-001/T-002 tests. |
| `tests/unit/extract/test_cms_dialysis_facility.py` | Resolver, full-file reconciliation, and fixture extraction tests. |
| `docs/source-schemas/cms_dialysis_facility.schema.json` | Normalized full observed schema, required mapping, provenance, and hash. |
| `docs/source-dictionaries/cms_dialysis_facility-<release>.pdf` | Pinned official dictionary used to define the v1 contract. |
| `docs/source-catalog.md` | Facility source grain, fields, periods, access, lineage, and limitations. |
| `docs/preflight.md` | Dated live metadata/extraction/reconciliation evidence. |
| `data/README.md` | Facility raw manifest layout and ignored-artifact reminder. |
| `docs/guides/008-facility-source-and-ingestion-explained.html` | Required standalone completed-plan explainer. |
| `tests/unit/docs/test_plan_008_guide.py` | Static structure, accessibility, evidence, and internal-link checks. |
| `docs/guides/README.md` | Completed Plan 008 guide registration. |
| `README.md` | Completed status, guide link, and explicit live extraction command. |

Do not create the Plan 008 guide or mark this plan completed until the contract,
extractor, live evidence, documentation, and canonical offline verification are
all green.

## Red-green-refactor execution sequence

### 1. Resolve official meaning before contract code

Perform bounded official-source checks with a descriptive user agent, explicit
timeouts, and no authentication:

1. resolve exactly stable dataset ID `23ew-n7w9` from official metadata;
2. corroborate the Listing by Facility title and landing page;
3. record current release, modified date, planned refresh if published, row and
   column counts if published, and one complete CSV distribution;
4. download the official dictionary to a temporary path, verify a nonempty PDF,
   calculate its byte count and SHA-256, and retain the reviewed version under a
   release-specific filename if permitted;
5. compare dictionary variable names/labels/types with metadata fields, API
   field slugs, and a bounded full-CSV header/sample;
6. resolve every required semantic concept to exactly one current CSV header;
7. confirm public unauthenticated access; and
8. reduce live results to schema/count/hash evidence without retaining a sample
   response dump or transient URL in Git.

Create `docs/source-schemas/cms_dialysis_facility.schema.json` only from the
verified official surfaces. The normalized evidence must include:

- complete ordered observed dictionary/metadata/CSV field lists;
- the cross-surface required mapping;
- declared types, maximum lengths, units, and definitions;
- raw grain and contract version;
- catalog/dictionary provenance and dated release metadata;
- separately listed additive fields;
- dictionary byte/hash evidence; and
- a deterministic semantic schema hash that excludes volatile retrieval data.

If the dictionary, metadata, API, and CSV cannot be reconciled one-to-one for a
required field, stop before writing the executable contract.

### 2. Lock the smallest deterministic facility fixture

Create synthetic, plainly labeled fixture rows that exercise raw preservation
without making claims about real facilities. Include at least:

1. a leading-zero textual CCN and a complete reported row;
2. public business address fields, including a blank optional address line;
3. ownership, chain, station, and all three required modality fields;
4. a reported five-star value with its period and availability code;
5. a missing star value with a nonreported/unavailable companion code;
6. complete survival, hospitalization, and readmission families with distinct
   raw periods, denominators, categories, estimates, and confidence limits;
7. an unavailable outcome with its availability code and blank estimate/
   interval values preserved rather than converted to zero;
8. a missing confidence-limit token reserved for later T-013 handling;
9. a Connecticut source county string and a separate alias-like county string
   reserved for later geography tests, with no FIPS or match result invented;
10. a harmless additive column; and
11. separate mutations for blank CCN, duplicate CCN, duplicate required header,
    missing field, and incompatible metadata type failures.

Do not use a real facility name, address, phone number, or quality observation
in committed fixtures. Do not type or classify fixture values in this plan.

### 3. Add failing schema-contract tests

Write the smallest deterministic tests proving that:

1. the verified normalized schema satisfies the v1 required mapping;
2. each required concept maps to one dictionary variable and one full-CSV
   header, with an API field name recorded when CMS supplies one;
3. removing any required field fails with a structured deterministic issue;
4. duplicating a required header or mapping target fails;
5. incompatible text/numeric/date type-family drift fails;
6. dictionary and observed-schema hashes reconcile to committed evidence;
7. additive fields pass and are reported in sorted order;
8. a renamed or ambiguous required field is not accepted merely because its
   friendly label looks similar; and
9. all three required outcome families are complete only when their period,
   availability, category, denominator, estimate, lower limit, and upper limit
   fields are present.

Implement only enough source-specific contract behavior to make these tests
green. Reuse small immutable result/issue types only when their semantics match
the existing contracts exactly.

### 4. Add failing raw-grain tests

Before implementing row validation, add tests proving that:

1. CCN is read and returned as raw text;
2. a leading-zero CCN survives byte-to-CSV parsing unchanged;
3. blank or whitespace-only CCN fails;
4. a duplicate CCN anywhere in a complete snapshot fails rather than being
   deduplicated;
5. the accepted CCN shape matches the official dictionary and complete
   observed current source without numeric coercion;
6. facility name, address, state, ZIP, county, and phone remain raw strings;
7. ZIP is never interpreted as county identity;
8. blank non-key values remain distinguishable from raw zero or other tokens;
9. source rows are not excluded at the raw boundary based on state, territory,
   county-name, or measure availability; and
10. validation issues are stable, structured, and suitable for future audit
    logs.

This completes only the facility portion of T-002. Geography validity,
availability interpretation, numeric bounds, and outcome consistency belong to
later plans.

### 5. Test official metadata and current-CSV resolution

Use an official-shaped local metadata fixture and injected transport seams. Add
failing tests proving that the resolver:

1. selects exactly stable dataset ID `23ew-n7w9`;
2. corroborates the expected Listing by Facility identity;
3. selects one current complete CSV distribution;
4. retains official catalog, landing, metadata, dictionary, and stable dataset
   identifiers as durable lineage;
5. rejects zero intended matches and multiple intended matches;
6. rejects state/national averages, patient-survey datasets, archive bundles,
   HTML tables, partial samples, ZIP bundles, and non-CSV resources;
7. fails if no complete official CSV is available;
8. never treats a caller-supplied arbitrary download URL as source authority;
9. captures source release/modified dates without confusing them with retrieval
   time; and
10. compares current metadata compatibility through the facility contract
    before downloading full content.

Keep resolution source-specific. Do not generalize both CMS catalog families
into a plugin system unless tests demonstrate a concrete shared abstraction
that preserves every existing source's behavior.

### 6. Test complete full-file transport and reconciliation

Reuse and, only where needed, extend the existing injected HTTP interfaces.
Add fixture tests proving:

1. the response streams in chunks to a same-volume temporary file;
2. response bytes are never normalized, decoded, or reserialized before hash
   publication;
3. SHA-256 and byte counts are exact;
4. `Content-Length` is enforced when present;
5. HTML/error payloads and unsupported media types cannot pass as CSV;
6. connection failures, timeouts, HTTP 408, HTTP 429, and HTTP 5xx retry with
   bounded exponential backoff and jitter;
7. ordinary HTTP 4xx, schema, contract, CSV, duplicate-key, and reconciliation
   failures do not retry;
8. exhausted or interrupted transfers remove temporary files;
9. CSV row counting handles quoted commas and quoted newlines correctly;
10. actual ordered headers reconcile with the selected official metadata and
    required mapping;
11. data-row count equals distinct nonblank CCN count;
12. schema, header, contract, dictionary, byte, row, and distinct-key evidence
    are internally consistent; and
13. any failure occurs before a final blob or manifest is visible.

For this full-CSV transport, T-003 means complete one-response transfer with
`page_count = 1`. Do not claim empty-page termination, overlap detection, or
other paginated behavior for this source.

### 7. Test facility manifest publication and idempotency

Add source-specific fixture tests on top of the shared manifest suite proving:

1. canonical facility manifest JSON is byte-for-byte deterministic;
2. every manifest field reconciles independently to the staged CSV, contract,
   normalized schema, and dictionary evidence;
3. a valid temporary file moves atomically to its SHA-256 blob path;
4. the manifest publishes only after blob, schema, and distinct-CCN validation;
5. failed validation leaves no final facility manifest and changes no prior
   artifact;
6. a later run with identical content reuses the verified blob and records a
   content no-op;
7. rerunning the same run ID with identical content and lineage is a successful
   no-op;
8. the same run ID with different bytes or lineage fails without overwrite;
9. an existing blob whose bytes disagree with its filename hash blocks reuse;
10. facility run IDs and manifest/blob paths cannot escape the configured raw
    root; and
11. any manifest-version extension remains compatible with completed CMS and
    SVI manifest tests.

Do not add or update a mart publication pointer. Raw-source content reuse is not
the same as a successful end-to-end mart publication.

### 8. Assemble the source-specific extractor

Implement one narrow orchestration function and module command that:

1. validates the run ID and output root;
2. resolves official current metadata and the full CSV;
3. validates the current metadata through the facility v1 contract;
4. streams the response to a run-scoped temporary file;
5. validates the actual header, raw grain, all rows, and additive fields;
6. computes and reconciles manifest evidence;
7. atomically publishes or reuses the immutable blob;
8. atomically publishes the run-scoped manifest; and
9. returns a structured result containing status, safe paths, hashes, byte/row/
   distinct-CCN counts, schema evidence, additives, retry count, and
   `content_noop`.

The intended explicit live command is:

```powershell
uv run python -m kidney_care_mart.extract.cms_dialysis_facility `
  --run-id cms-dialysis-facility-live-<UTC timestamp> `
  --output-root data/raw
```

The command must not accept a raw download URL that bypasses official metadata.
It must not run from default pytest, dbt, or pull-request checks.

### 9. Run the separate full-source live check

Only after all focused and complete offline checks are green:

1. run one explicit official full-CSV extraction;
2. independently reopen the generated manifest and blob from disk;
3. recalculate bytes, content hash, row count, distinct CCNs, header hash, and
   required/additive field reconciliation;
4. confirm raw leading-zero CCNs remain textual without recording facility
   identities in documentation;
5. summarize distinct raw period tokens and availability-code presence for the
   three required outcome families without publishing row-level source data;
6. compare the dated row/distinct-CCN result with the earlier 7,490 examined
   snapshot and explain any legitimate upstream change;
7. run a second immediate extraction under a new run ID and verify content reuse
   if the official bytes are unchanged; if the source genuinely changes between
   requests, retain both immutable lineages and investigate rather than forcing
   a no-op;
8. record concise dated evidence in `docs/preflight.md` and
   `docs/source-catalog.md`; and
9. verify with `git status`, `git ls-files`, and `git check-ignore` that the full
   CSV, manifests, temporary files, response dumps, and transient URLs are not
   tracked.

The live check may corroborate the planning-time 7,557-row observation, but the
acceptance rule is current complete reconciliation, not a hard-coded 7,557 or
7,490 assertion.

### 10. Refactor and complete documentation

After source behavior is green:

1. keep Provider Data Catalog mapping and facility-contract logic narrow,
   explicit, and source-specific;
2. remove accidental duplication only where shared semantics are proven by
   tests across all affected sources;
3. document the raw grain, release vintage, separate measure periods,
   denominators, availability companions, dictionary mapping, and manifest
   lineage in `docs/source-catalog.md`;
4. update the facility row in `docs/preflight.md` from Pending only when the
   explicit live result actually passes;
5. keep Census Geocoder preflight Pending because this plan makes no geocoder
   request;
6. update `data/README.md` only if the new source exposes an undocumented layout
   detail;
7. create the standalone network-free Plan 008 guide according to
   `docs/guides/README.md`;
8. explain in the guide why CCN is the raw grain, what a manifest proves, why
   measure companions remain together, and why facility location is not patient
   residence or a recommendation;
9. add static guide tests and complete rendered desktop/narrow, light/dark,
   keyboard, focus, overflow, print, and reduced-motion QA;
10. register and link the guide from `docs/guides/README.md` and the root
    `README.md` after Plan 007;
11. update the root README status without claiming typed facility facts, county
    mapping, facility context, publication, Airflow, or Power BI;
12. mark this plan `Completed` with exact completion date, contract/schema/
    dictionary identities, live evidence, test counts, and boundary statement;
    and
13. inspect the final diff and Git status for full source data, generated files,
    secrets, or scope creep.

## Verification commands

Focused red-green loop:

```powershell
uv run pytest `
  tests/unit/contracts/test_cms_dialysis_facility_contract.py `
  tests/unit/extract/test_cms_dialysis_facility.py `
  tests/unit/extract/test_http.py `
  tests/unit/extract/test_manifest.py `
  tests/unit/docs/test_plan_008_guide.py
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

Explicit live check, only after the offline handoff loop passes:

```powershell
uv run python -m kidney_care_mart.extract.cms_dialysis_facility `
  --run-id cms-dialysis-facility-live-<UTC timestamp> `
  --output-root data/raw
```

The default suite remains network-free. A live-source failure is recorded and
investigated separately; it must not be hidden by weakening deterministic
contract or reconciliation tests.

No dbt command is required by this plan because no DuckDB/dbt facility model is
in scope. The complete pytest suite still exercises the existing fixture-sized
dbt paths and protects all completed plans from regression.

## Acceptance criteria

- [x] Official Provider Data Catalog metadata resolves exactly stable dataset
  `23ew-n7w9`, corroborates the Listing by Facility source, and exposes one
  current complete CSV without authentication.
- [x] The current official dictionary is pinned with release, byte count, and
  SHA-256 evidence, subject to the repository's source/licensing policy.
- [x] Every required identity, public business location, characteristic,
  rating, hospitalization, readmission, and survival concept maps one-to-one
  across official dictionary, metadata/API, and actual CSV surfaces.
- [x] `cms_dialysis_facility.raw.v1` or its documented equivalent declares the
  exact required field set, compatible type families, raw CCN grain, and
  normalized schema-evidence hash.
- [x] T-001 passes for the facility source: required-column removal,
  duplication, ambiguity, and incompatible types block; additives pass and are
  reported.
- [x] T-002 passes for the facility source: raw CCN is nonblank, textual,
  format-compatible with official evidence, leading-zero safe, and unique
  across the complete snapshot.
- [x] The synthetic fixture covers missing star rating, missing confidence
  limit, unavailable outcome, duplicate CCN, public business-location lineage,
  and later geography edge strings without performing typed or geography work.
- [x] The three required quality families retain period, availability,
  category, denominator, estimate, lower limit, and upper limit companions.
- [x] Stable official metadata, not a transient or caller-supplied distribution
  URL, remains the production source locator.
- [x] The valid fixture path streams unchanged CSV bytes and publishes one
  content-addressed blob plus one canonical facility run manifest.
- [x] Hash, byte, row, distinct-CCN, schema, header, contract, dictionary, and
  blob-path evidence reconciles exactly.
- [x] T-003 passes for a complete one-response full-CSV transport recorded as
  `page_count = 1`; no multi-page API claim is made.
- [x] T-004 passes for source bytes, rows, distinct CCNs, schemas, headers, and
  manifest reconciliation.
- [x] Transient retry is bounded; permanent HTTP, contract, schema, CSV, key,
  and reconciliation failures do not retry.
- [x] Truncated, interrupted, HTML, incompatible, duplicate-key, or otherwise
  invalid inputs cannot create a final blob or manifest.
- [x] Same-content and same-run reruns are idempotent without overwriting
  immutable history; conflicts and corrupt existing blobs block.
- [x] Existing CMS and SVI extraction/manifest behavior remains green and
  backward compatible.
- [x] One separate live extraction succeeds and is independently reconciled
  from disk, with the current row/distinct-CCN result recorded as dated evidence
  and compared honestly with the earlier 7,490 examined snapshot.
- [x] Raw facility data, generated manifests, response dumps, temporary files,
  transient URLs, secrets, credentials, databases, and patient information are
  ignored and absent from tracked Git content.
- [x] `docs/source-catalog.md`, `docs/preflight.md`, and `data/README.md` where
  needed accurately describe only completed behavior and dated evidence.
- [x] The Plan 008 guide is standalone, network-free, accessible, linked in
  numeric order, internally valid, and passes automated plus rendered visual QA.
- [x] README and every materially affected completed guide remain accurate.
- [x] No dependency or lockfile change is made; if one becomes necessary, work
  stops for the required architecture decision.
- [x] The canonical locked Ruff and complete pytest suite pass.
- [x] The completion record states explicitly that typing, T-012/T-013,
  facility facts, county assignment, Census remediation, T-015/T-018/complete
  T-019, screening enrichment, publication, Airflow, and Power BI remain
  deferred.

## Stop conditions

Stop and request a specification or architecture decision if:

- stable dataset ID `23ew-n7w9` is missing, ambiguous, renamed to a
  definitionally different source, or no longer the current Listing by Facility
  dataset;
- the official catalog no longer exposes one complete current CSV;
- public access requires authentication, payment, a private agreement, or
  nonpublic/patient-level data;
- the dictionary cannot be retained under the repository's source/licensing
  policy;
- dictionary, metadata/API, and CSV surfaces cannot be mapped one-to-one for a
  required semantic concept;
- a required field is absent or its definition, denominator, unit, or type is
  materially incompatible with `specs.md`;
- the complete current source legitimately contains duplicate or blank CCNs
  that cannot be resolved without redefining the source grain;
- CCN cannot be preserved as a stable textual identifier without lossy numeric
  coercion;
- the current source no longer carries availability, period, denominator,
  category, estimate, and interval companions for one of the three required
  outcome families;
- metadata and downloaded content appear to come from different releases and
  cannot be reconciled after bounded investigation;
- a current count difference cannot be explained as a legitimate source change
  or data-quality failure;
- a correct complete-transfer proof requires silently switching to paginated
  API or archive-bundle transport;
- correct implementation requires a new dependency, incompatible manifest
  change, or broad extractor rewrite without the required architecture decision;
- an existing content-addressed blob fails integrity verification;
- generated files cannot be kept out of tracked Git content;
- bounded live attempts cannot distinguish an upstream failure from a local
  network restriction; or
- any completed Plan 001-007 test would have to be weakened.

Do not silently switch to another dialysis dataset, infer a field mapping from
similar words, coerce CCN to a number, deduplicate facilities, treat missing as
zero, flatten quality measures, hard-code 7,490 or 7,557 as timeless, overwrite
an immutable artifact, call the Census Geocoder, assign a county, enrich the
screen, or mark a failed transfer as a successful snapshot.

## Autonomous execution boundary

This plan is suitable for an unattended implementation goal. All code and
fixture work is local and test-driven; the only external side effect is the
explicit read-only download from an official public CMS source into generated,
ignored local storage. No account, secret, payment, GUI, dependency change,
commit, push, geocoder request, or external write is authorized.

The execution goal is:

> Implement Plan 008 completely using red-green-refactor. Verify the current
> official CMS Dialysis Facility Listing and dictionary; create normalized
> schema evidence and the versioned raw facility contract; preserve textual CCN
> grain and all required facility/quality companion fields; resolve and stream
> the current official full CSV; block schema, transfer, duplicate-key, and
> reconciliation failures; publish immutable content-addressed raw bytes and a
> canonical run manifest with safe idempotent reuse; add deterministic fixtures,
> failure injection, documentation, and the standalone Plan 008 HTML guide;
> perform the explicit full-source live reconciliation; and run the canonical
> locked offline verification. Make no dependency change, commit, push, typed
> facility model, county assignment, Census request, facility aggregate,
> screening change, Parquet publication, Airflow/CI/Power BI work, score, rank,
> recommendation, clinical claim, or causal claim. Stop only at a listed stop
> condition; otherwise continue until every acceptance criterion is satisfied.

## Handoff

After Plan 008 is complete, the next dependency-ordered slice should load one
verified facility manifest into DuckDB as raw strings, build a typed facility
stage, and create the one-row-per-CCN `dim_facility` plus the
CCN-by-source-snapshot `fct_facility_quality_snapshot`. That plan should
interpret source-defined availability, periods, denominators, categories,
estimates, and confidence limits; prove T-012 and T-013; and reconcile raw rows
to typed facility rows without contacting CMS directly.

Facility-to-county assignment should remain a later independent slice. Only
after the raw/stage/facility-fact path is green should the project implement
exact and explicit-alias matching, Census remediation, manual exceptions,
quarantine, national/state coverage policy, county facility aggregates, T-015,
T-018, and complete T-019. No later facility work may alter the Plan 007
threshold, component flags, or screening quadrant.
