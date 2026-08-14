# Numbered human-guide convention

Every completed numbered engineering plan has a matching beginner-friendly HTML
explainer. These guides make the work understandable to readers who are new to
data engineering without creating a second, conflicting specification.

## Naming and discovery

- Match `plans/NNN-<plan-topic>.md` with
  `docs/guides/NNN-<concise-topic>-explained.html`.
- Preserve the same three-digit prefix even when the concise guide topic is not
  an exact copy of the plan slug.
- Identify the plan number in the guide and link back to the plan.
- Link every guide from the root `README.md` in numeric plan order.
- Update the matching guide whenever a completed plan changes materially. A
  missing or stale guide means the plan documentation is incomplete.

Current guides:

- `001-cms-source-contract-explained.html` corresponds to
  `plans/001-cms-om-gv-source-contract.md`.
- `002-cms-ingestion-manifest-explained.html` corresponds to
  `plans/002-cms-om-gv-ingestion-manifest.md`.
- `003-cms-staging-explained.html` corresponds to
  `plans/003-cms-om-gv-raw-to-stage.md`.
- `004-svi-source-contract-explained.html` corresponds to
  `plans/004-cdc-svi-county-source-contract.md`.
- `005-svi-source-to-fact-explained.html` corresponds to
  `plans/005-cdc-svi-source-to-fact.md`.

## Required content

Write for a reader who understands ordinary files and tables but may not know
the data-engineering vocabulary. Each guide should:

1. define the main concept and unfamiliar terms in plain language;
2. explain why the implementation exists, preferably with one useful analogy;
3. show the input-to-output flow and the checks or decisions along the way;
4. explain important design emphasis, invariants, and failure behavior;
5. distinguish completed behavior from intentionally deferred work;
6. link to the authoritative specification, matching plan, relevant code,
   fixtures, tests, and operational documentation;
7. include a short glossary; and
8. report verification evidence precisely.

Use the exact product language required by `specs.md`. Do not turn source
measures into clinical, causal, prevalence, need, opportunity, ranking,
contracting, or final site-selection claims.

## Evidence and authority

- `specs.md` remains authoritative. The guide explains it; the guide does not
  silently redefine it.
- Distinguish deterministic fixture results from live-source observations.
- Date live evidence and label snapshot counts as dated observations rather
  than timeless constants.
- Reconcile metrics, hashes, and test counts to the plan completion record or
  reproducible repository output before publishing them.
- Do not embed full source downloads, patient information, secrets, credentials,
  transient signed URLs, or generated manifests.

## HTML quality baseline

Each guide is a committed, standalone, network-free HTML document:

- include a descriptive title and meta description;
- use semantic landmarks, one `h1`, ordered headings, a skip link, native
  controls, visible focus, and appropriate accessible labels;
- make the first render complete and useful without JavaScript; interaction is
  optional and must only clarify the explanation;
- support keyboard use, reduced-motion preferences, light and dark color
  schemes, printing, and responsive layouts down to 320 CSS pixels;
- use no external fonts, scripts, styles, analytics, network requests, or
  embedded full source data; and
- keep repository links relative so a locally downloaded checkout remains
  navigable.

Before handoff, parse the document as HTML, check internal file links, exercise
every control with a keyboard, inspect representative desktop and narrow
layouts in light and dark modes, and run the repository's canonical offline
verification commands.
