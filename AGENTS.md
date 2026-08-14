# Repository operating guide

`specs.md` is the authoritative product and engineering specification. Read it before changing this repository. If this guide, another document, a test, or implementation behavior conflicts with `specs.md`, follow `specs.md` and resolve the conflict explicitly; do not silently reinterpret the specification.

## Scope and language

- Build a reproducible county screening and investigation mart using public, aggregate data.
- Use the phrase **“observed outpatient dialysis use among Original Medicare beneficiaries.”** Do not relabel it as kidney disease prevalence, unmet need, disease burden, or intervention opportunity.
- Do not introduce patient-level data, PHI, clinical or causal claims, opaque scores, automated decisions, or final site-selection, provider-ranking, partnership, or contracting recommendations.
- Keep AWS, hosting, streaming, machine learning, and other explicit non-goals out of the core implementation unless separately approved.
- Declare the grain, denominator, source vintage, and lineage of each model and metric before presenting it.

## Development workflow

For every critical transformation, use red–green–refactor:

1. Add the smallest deterministic fixture that expresses the rule or failure.
2. Add a failing pytest or dbt unit test.
3. Implement only enough behavior to pass.
4. Refactor without changing behavior.
5. Add or update data tests and documentation before considering the change complete.

Do not weaken tests to accommodate incorrect behavior. Required-column removal, incompatible types, invalid grains, duplicate keys, incomplete pagination, or failed reconciliation must block publication. Additive source columns are allowed but must be reported.

Use Python 3.12 and `uv`, and keep `uv.lock` committed. Dependency changes require a short architecture decision record and a green full test run, as required by `specs.md`.

## Numbered plan explainers

- Completing a numbered plan also requires a matching beginner-friendly standalone HTML guide under `docs/guides/`. Use the same three-digit prefix as the plan, link the guide from the root `README.md` in plan order, and follow `docs/guides/README.md`.
- Define unfamiliar terms in plain language, explain why the implementation exists, show the input-to-output flow and safety boundaries, identify what remains out of scope, link to the relevant plan/code/tests, and date any live-source evidence.
- Keep each guide network-free, useful without JavaScript, responsive, keyboard accessible, light/dark compatible, and free of raw source downloads, secrets, or claims that exceed `specs.md`.
- Update the matching guide whenever a completed plan changes materially. A missing or stale explainer means the plan documentation is incomplete.

## Geography, missingness, and metrics

- Treat county FIPS as five-character text matching `^[0-9]{5}$`; preserve leading zeros. District of Columbia is `11001`. Exclude territories and source `UNKNOWN` pseudo-counties from the MVP.
- Preserve raw source strings before typing. CMS `*`, blank, and `NA` become null with distinct suppression/unavailable status; a numeric zero remains zero. SVI `-999` becomes null with an unavailable flag.
- Never silently fuzzy-match facility geography or use ZIP code as a county key. Use the specified auditable cascade and quarantine unresolved rows.
- Never sum rates or percentages, use an unweighted county mean for a state or national KPI, average risk-standardized facility outcomes into a county quality score, or infer missing values as zero.
- Facility characteristics are due-diligence context only and never alter the screening quadrant.

## Offline and live checks

- Default unit, fixture integration, dbt fixture, and pull-request checks must be deterministic and network-free.
- Keep live-source smoke tests separate. Run them manually or on a schedule when the task explicitly calls for external validation.
- Treat the counts in `specs.md` as pinned-snapshot expectations, not timeless constants. Explain legitimate upstream changes rather than silently updating assertions.
- Retry only transient network failures with bounded backoff. Do not retry schema, contract, or data-quality failures.

## Data, generated artifacts, and secrets

- Commit representative fixtures, contracts, tests, documentation, dependency metadata, and reproducible queries—not full source downloads.
- Do not commit raw data, generated DuckDB files, generated Parquet data, Airflow logs, credentials, secrets, Terraform state, or patient information.
- Use ignored environment files for local secrets and keep only placeholders in `.env.example`.
- Preserve immutable, content-addressed raw snapshots and manifests. Publish marts atomically and update the latest-successful pointer only after all required checks pass.
- Respect DuckDB's single-writer discipline; BI consumes published Parquet rather than a live writable database.

## Handoff and commits

- Include a proposed commit message in the closing response for every completed repository change, even when the user does not ask for one explicitly.
- Make the proposed message ready to use, concise, imperative, and representative of the complete change set.
- Do not create a commit or push changes unless the user explicitly requests it.

## Canonical bootstrap verification

Run these commands from the repository root after the local prerequisites are available:

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

`uv sync --locked` may download missing locked packages on a newly provisioned machine. After synchronization, the Ruff and pytest checks are deterministic and network-free. Run every check relevant to changed code. As dbt, Airflow, and publication components are added, preserve the additional CI gates required by `specs.md`; document their exact repository commands rather than inventing alternate workflows. Do not run live-source checks as part of the default offline verification path.
