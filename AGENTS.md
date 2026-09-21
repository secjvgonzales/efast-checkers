# Repository Guide

## Application

Primary working application: **SEC eFAST Checkers – AFS & GIS Reviewer Assistance MVP**.

- Stack: Python + Streamlit prototype (SEC Philippines-oriented internal QA dashboard for AFS/GIS review, validation, figure extraction, reviewer corrections, historical and ranking views).

- Language/runtime: Python 3.11 (see `.replit`: `modules = ["nodejs-24", "python-3.11"]`).

- Key libraries: `streamlit`, `pandas`, `pymupdf` (`fitz`, primary PDF text extraction), `pdfplumber` (fallback extraction), `pillow`, `openpyxl` (declared in `requirements.txt`; `pillow`/`openpyxl` are not directly imported by the current Python modules). Stdlib used: `sqlite3`, `re`, `json`, `pathlib`, `datetime`, `difflib`, `subprocess` (bounded Tesseract OCR fallback in `pdf_utils.py` only when `tesseract` is installed).

- Main entry point: `app.py` (`main()` → `st.set_page_config`, `apply_styles()`, `bootstrap()`, sidebar navigation, `PAGES[...]() `dispatch). Run from the repository root.

- Startup behavior (`app.py::bootstrap`): calls `db.init_db()`, `storage.seed_company_master()`, and `storage.ensure_all_demo_documents()` (seeds demo suite on first run; presence-guarded so existing analysis/reviewer rows are not overwritten on restart).

- Navigation: seven screens registered in `app.py::PAGES` (`Dashboard`, `Upload / Intake`, `Document Review`, `AFS Figures Extraction Review`, `Historical Company View`, `Rankings / Research View`, `Demo Data & Configuration`).

Secondary scaffold (not used by the Streamlit app): a pnpm TypeScript monorepo.

- Tooling: pnpm workspaces, Node.js 24, TypeScript ~5.9 (`package.json`, `pnpm-workspace.yaml`, `.replit [agent] stack = "PNPM_WORKSPACE"`).

- Packages: `lib/db` (PostgreSQL + Drizzle ORM), `lib/api-spec` (Orval codegen from OpenAPI spec), `lib/api-zod`, `lib/api-client-react`, `scripts`, `artifacts/api-server` (Express 5 + esbuild CJS bundle), `artifacts/sec-efast-checkers` (React/Vite web artifact, also used as the Replit workflow cwd for launching the Streamlit app), `artifacts/mockup-sandbox` (design-preview Vite server).

- The Streamlit app does not import or call any TypeScript package.

## Development Direction

The repository is transitioning from a presentation-oriented prototype into a functional MVP for real AFS and GIS document processing. Existing demo behavior documents the current implementation; it is not automatically the target architecture.

Primary MVP Objective

The functional workflow is:

`PDF upload → document persistence → page text extraction → OCR fallback when required → content-based classification → report-specific validation/extraction → database persistence → human review/correction → reviewer disposition.`

- Real uploaded documents must be processed using their actual extracted content.

- Demo data must never silently substitute for failed extraction of a real upload.

- When processing cannot complete reliably, persist/report the failure and route the document to `Manual Review` or the existing equivalent reviewer status instead of fabricating successful results.

- Keep AFS and GIS as separate user-facing report workflows while reusing shared backend document-processing services where appropriate.

Architecture Direction

- Keep Python + Streamlit as the primary MVP application.

- Keep SQLite for the MVP unless an approved requirement explicitly justifies a database migration.

- Do not activate, migrate to, or couple the Streamlit MVP to the TypeScript/PostgreSQL scaffold unless explicitly requested as a separate architectural change.

- Preserve the existing module boundaries where practical. Functionalize the current application incrementally instead of rewriting it.

- Shared concerns such as file intake, PDF extraction, OCR fallback, page persistence, and processing status should be reusable by both AFS and GIS.

- Report-specific business rules must remain separated: AFS classification/validation/figure extraction must not be mixed with GIS classification/validation/field extraction.

Real Data vs Demo Data

- Demo workflows must remain explicitly identifiable as demo workflows.

- Real uploads must produce only results derived from the real uploaded document and user-supplied metadata.

- Existing JSON-backed historical/ranking/demo views may remain during early functionalization phases, but treat them as transitional. Migrate them only through an explicitly approved phase after the core real-document workflow is reliable.

- Do not remove useful demo data merely because functional processing is added; demo and real-data paths may coexist as long as they are clearly separated.

Document Text and Evidence

- `text_preview` is for UI display only.

- Validation, classification, company/period checks, and financial figure extraction must operate on complete extracted page text unless a specific approved algorithm intentionally uses another representation.

- Do not truncate source text before analysis.

- Preserve page-level provenance: original extraction, OCR text when used, extraction source, page number, and evidence needed for reviewer verification.

- AFS component detection must be content/evidence-based. Do not assume fixed page numbers or a rigid Financial Statement page order.

Functional MVP Priority

Prioritize development in this order unless a later approved plan changes it:

reliable shared PDF intake for AFS and GIS;

complete text extraction and bounded OCR fallback;

persistence of document/page processing results;

AFS content classification and validation;

AFS financial figure extraction and normalization;

reviewer correction and disposition persistence;

GIS content classification, field extraction, and validation;

DB-driven historical/ranking views and cross-document checks.

Do not prioritize unrelated UI redesigns, framework migrations, infrastructure changes, or speculative AI/ML work while the approved functional workflow is incomplete.

Incremental Delivery Rule

- Build one approved milestone at a time and verify it before expanding scope.

- "Make the smallest targeted change necessary" does not mean preserving a known prototype limitation when that limitation directly prevents an approved functional requirement.

- Do not implement AFS and GIS business logic in the same change unless the approved milestone explicitly requires both. Prefer shared foundation first, then complete one report workflow end-to-end before expanding the other.

## Repository Structure

```text

app.py                    # Streamlit entry point, page registry, theme CSS, bootstrap, sidebar nav

config.py                 # App labels, intake defaults, BASE_DIR/DATA_DIR/UPLOADS_DIR/DB_PATH, JSON paths, PAGE_PRIORITY, RANKING_METRICS, STATUS_ORDER, TEXT_PREVIEW_MAX_CHARS

db.py                     # SQLite schema (init_db), sqlite3 CRUD helpers, reviewer-action/figure updates

storage.py                # JSON loading, demo-suite seeding (presence-guarded), SQLite read helpers, test-upload deletion

pdf_utils.py              # PyMuPDF extraction + OCR fallback + pdfplumber fallback, quality proxy, upload save

validation_engine.py      # Keyword page classifier + company/period/submission/orientation/completeness/readability rules

extraction_engine.py      # Regex label/year/value figure extractor + fiscal-year candidates

normalization.py          # raw-label alias mapping (label_mapping.json), amount/unit parsing

confidence.py             # Prototype confidence display helper (fixed/seeded estimate, not a model)

ui_helpers.py             # Shared badges, metric cards, peso/timestamp formatting, selectors, CSV download

pages/                    # One Streamlit screen per module, each exposing render():

  dashboard.py            # Live DB metrics, document queue, Open in Review navigation, charts

  upload_intake.py        # Metadata intake, PDF save/extract/analyze/validate, demo fallback, Load Demo, Test Uploads delete

  document_review.py      # Validation cards, page accordions + evidence highlight, disposition form, action display

  figures_review.py       # Editable figure table, save corrections, CSV export, normalized buckets

  historical_company.py   # Seeded demo_data.json 5-year history table/charts/CSV (not DB-driven)

  rankings.py             # Seeded demo_data.json 5-company ranking, selectable revenue metric, chart/CSV

  settings_demo_data.py   # Read-only reference display of JSON/config values (no live editing)

demo_data.json            # Demo suite (3 fictional companies), sample pages/validations/figures, historical + ranking data

label_mapping.json        # Raw financial-statement label aliases -> normalized fields

revert_reasons.json       # Reviewer revert-reason dropdown values

sample_company_master.json# Fictional Audentia Fortuna Holdings, Inc. master record (only master used by engine)

data/                     # Runtime SQLite dir (gitignored: data/*.sqlite); DB file created at startup

uploads/                  # Local uploaded PDFs (gitignored except .gitkeep); filename used as storage target

requirements.txt          # Python dependencies for the Streamlit app

.streamlit/config.toml    # Streamlit server (0.0.0.0:5000, headless), CORS/XSRF off, green theme

.replit                   # Replit modules, deployment, workflows (Streamlit/API/mockup), ports, nix packages

package.json / pnpm-workspace.yaml / tsconfig.base.json / tsconfig.json

                          # pnpm workspace root: typecheck/build scripts, workspace catalog, TS project references

lib/                      # Shared TS packages: db, api-spec, api-zod, api-client-react

artifacts/                # Runnable TS apps: api-server, sec-efast-checkers, mockup-sandbox

scripts/                  # Workspace helper TS package (@workspace/scripts, tsx)

docs/                     # Implementation-status and per-feature validation notes (see docs/CURRENT_*.md)

attached_assets/          # Pasted task/validation prompt transcripts (reference only)

```

## Environment

- Runtimes: Python 3.11 for the Streamlit app; Node.js 24 + pnpm for the TypeScript workspace.

- Package managers: `pip` + `requirements.txt` (Python side); `pnpm` only for the TS side (`package.json` `preinstall` hook rejects npm/yarn: `Use pnpm instead`). Do not use npm/yarn for workspace installs.

- Important configuration files (do not modify unnecessarily; never commit secrets):

  - `config.py` — titles, defaults (`DEFAULT_COMPANY`, `DEFAULT_REPORT_TYPE`, years), all data paths, ranking metrics, status order, 2000-char preview limit.

  - `requirements.txt` — `streamlit`, `pandas`, `pymupdf`, `pdfplumber`, `pillow`, `openpyxl` (unpinned).

  - `.streamlit/config.toml` — server address/port, headless, theme colors.

  - `.replit` — runtime modules, workflows, ports (5000 Streamlit, 8080 API, 8081/19613 artifacts), nix system packages (includes `tesseract`, `mupdf`).

  - `.npmrc` — `auto-install-peers=false`, `strict-peer-dependencies=false`.

  - `pnpm-workspace.yaml` — workspace globs (`artifacts/*`, `lib/*`, `lib/integrations/*`, `scripts`), dependency catalog, `minimumReleaseAge: 1440` supply-chain guard (do not disable), esbuild/platform overrides.

  - `tsconfig.base.json` / per-package `tsconfig.json` files — strict TS settings (`noImplicitAny`, `strictNullChecks`, etc.).

  - `demo_data.json`, `label_mapping.json`, `revert_reasons.json`, `sample_company_master.json` — editable demo content, served read-only by the Settings screen.

- No `.env`, secret manager, or Python lint/test config files were found in the repository. No passwords, keys, or tokens are documented here.

## Setup

Python/Streamlit app (verified from `requirements.txt`, `README.md`, `config.py`, `db.py`, `.gitignore`):

```bash

pip install -r requirements.txt

```

No further build or migration step is needed. `data/` and `uploads/` directories are created automatically at startup (`db.get_connection()` mkdirs `DATA_DIR`; `pdf_utils.prepare_uploaded_file()` mkdirs `uploads/`). The SQLite file and demo rows are created/seeded automatically on first app launch. `data/*.sqlite` and `uploads/*` (except `.gitkeep`) are gitignored.

TypeScript workspace (only if working on `lib/`, `artifacts/`, or `scripts/`; verified from `package.json`, `pnpm-workspace.yaml`, `replit.md`):

```bash

pnpm install

pnpm run typecheck

```

## Running the Application

Primary Streamlit app, from the repository root (verified from `README.md`, `replit.md`, `.streamlit/config.toml`):

```bash

streamlit run app.py --server.port 5000

```

Replit workflow equivalent (verified from `.replit`): cwd `./artifacts/sec-efast-checkers`, command `streamlit run ../../app.py --server.port $PORT --server.address 0.0.0.0`.

TypeScript artifacts (verified from per-package `package.json` files; not required for the Streamlit app):

```bash

pnpm --filter @workspace/api-server run dev   # Express API on port 8080 (builds, then starts dist/index.mjs)

pnpm --filter @workspace/sec-efast-checkers run dev   # Vite web app

pnpm --filter @workspace/mockup-sandbox run dev       # component preview server on port 8081

```

## Database

Streamlit app database (verified from `db.py`, `config.py`, `storage.py`):

- Engine: SQLite via stdlib `sqlite3` (one connection per operation, `sqlite3.Row` → dict rows). File: `data/sec_efast_checkers.sqlite` (`config.DB_PATH`). No migration framework, no ORM, no seed scripts to run manually.

- Initialization: `db.init_db()` runs `CREATE TABLE IF NOT EXISTS` for `documents`, `company_master`, `page_analysis`, `validations`, `extracted_figures`, `reviewer_actions`, plus idempotent `ALTER TABLE ... ADD COLUMN` backfills for newer `page_analysis`/`documents` columns. Safe to run on every startup.

- Seeding: `storage.seed_company_master()` inserts the sample master once (guarded by SEC registration no.); `storage.ensure_all_demo_documents()` seeds each `demo_suite` entry once (guarded by filename + existing `page_analysis` rows; default reviewer actions created only when absent). Upload fallbacks may substitute seeded demo pages/figures with an on-screen warning.

- Relationships are application-level `document_id` columns; the schema declares no foreign keys or cascades. `replace_document_analysis()` deletes/reinserts the three analysis sets per document; `save_reviewer_action()` upserts one row per `document_id` (history view shows the latest action, not an append-only log); `delete_document_records()` deletes one document and its dependent rows atomically.

- Destructive rules: never delete the SQLite file or run manual `DELETE`/`DROP` outside the app unless explicitly requested. Demo documents (filenames listed in `demo_data.json` `demo_suite`) are protected from deletion by `storage.delete_test_document()`; only non-demo "test uploads" can be removed, and only via the Upload / Intake Delete → Confirm Delete flow.

TypeScript workspace database (separate scaffold, verified from `lib/db/package.json`, `replit.md`; not connected to the Streamlit app):

```bash

pnpm --filter @workspace/db run push        # drizzle-kit push (dev only)

pnpm --filter @workspace/api-spec run codegen  # regenerate API hooks/Zod schemas from OpenAPI spec

```

PostgreSQL connection details for that scaffold were not verified; check `lib/db/` (`drizzle.config.ts`, `src/`) before use.

## Coding Conventions

Verified from `app.py`, `db.py`, `storage.py`, `pdf_utils.py`, `validation_engine.py`, `ui_helpers.py`, `pages/*.py`, `config.py`:

- Layout: flat root modules for engine/storage/db/config; `pages/` holds one screen module each exposing `render()`; shared presentation helpers live in `ui_helpers.py`. Follow this split — do not add new top-level layers or move screens.

- Python style: `snake_case` functions/variables, `UPPER_SNAIL` config constants, stdlib-first imports (`pathlib`, `re`, `json`, `datetime`, `sqlite3`, `difflib`), then third-party (`streamlit`, `pandas`, `fitz`/`pdfplumber`), then local modules. Keep imports in that order.

- DB access: go through `db.py` helpers (`query`, `execute`, `insert_document`, `replace_document_analysis`, `save_reviewer_action`, `update_figure_reviews`, `delete_document_records`) and `storage.py` readers (`get_document(s)`, `get_pages`, `get_validations`, `get_figures`, `get_reviewer_actions`). Do not open ad-hoc `sqlite3` connections in pages. Return rows as plain dicts.

- Text handling: page text is truncated to `TEXT_PREVIEW_MAX_CHARS` (2000) for `text_preview`; extraction scans `text_preview`, not full PDFs. Preserve `original_text`/`ocr_text`/`extraction_source` fields in `page_analysis` rows.

- Status vocabularies (exact strings): validations use `Passed` / `Warning` / `Failed` / `Needs Review` (`STATUS_ORDER`); recommendations use `Accept` / `Revert` / `Needs Review`. Recommendation reduction: any `Failed` → `Revert`, else any `Warning` → `Needs Review`, else `Accept`. Do not rename these strings.

- UI: Streamlit session state keys `active_document_id`, `_current_page`, `review_context`; sidebar button navigation with disabled-active-button pattern in `app.py`; metric cards/badges via `ui_helpers`; theme CSS lives in `app.py::apply_styles` + `.streamlit/config.toml`. HTML-escape dynamic page text/reviewer values before injecting into markup (`html.escape`).

- Figures: regex extractor requires `label + year + value` layout; one `unit_basis` (`Pesos`/`Thousands`/`Millions`) per page; `reviewed_value`/`review_status` are the only reviewer-editable figure fields, saved via `update_figure_reviews()` by figure `id` + `document_id` (does not recompute `normalized_peso_value`). Confidence is a fixed/seeded estimate rendered as `x% · Est.` — do not present it as a computed model score.

- TypeScript side: strict TS (`tsconfig.base.json`), workspace `catalog:` versions, `workspace:*` intra-repo deps; validate with `pnpm run typecheck` and format with Prettier (`prettier` is a root devDependency; no ESLint config was found).

- Historical/Rankings screens currently read `demo_data.json` arrays only. Treat this as the current implementation, not the permanent target architecture. Do not rewire them to SQLite incidentally; migrate them only as part of an explicitly approved functionalization phase. Settings screen is currently read-only reference despite its title — do not add file-writing there unless an approved requirement calls for it.

- Smallest targeted change: reuse existing helpers, constants (`config.py`), JSON-driven labels/reasons/mappings, and established page patterns instead of introducing new frameworks, ORMs, or config systems.

## Testing

No test suite exists in the repository (verified 2026-09-07): no `test_*.py`, `*_test.py`, `conftest.py`, `pytest.ini`, `pyproject.toml`, or tox config; no `*.test.ts`, vitest/jest/playwright config, and no `test` script in any `package.json` (root scripts are `build`, `typecheck`, `typecheck:libs`; per-package scripts are `dev`/`build`/`start`/`typecheck`, plus `push`/`codegen`/`hello`). `docs/*_VALIDATION.md` files record manual/browser regression passes (flows A–K), not automated tests.

Available verification commands (verified from `package.json` files):

```bash

pnpm run typecheck   # full TypeScript typecheck across all packages (tsc --build + per-package typecheck)

pnpm run build       # typecheck + build all packages

```

Python side has no lint/test runner configured. After Python changes, at minimum compile-check the touched files (example: `python -m py_compile app.py db.py storage.py`) and exercise the affected Streamlit screen manually; report that no automated tests exist.

## Validation

Before considering a change complete:

- run the appropriate syntax/lint checks (`pnpm run typecheck` for TypeScript; `py_compile` smoke check for Python — no Python linter is configured)

- run relevant tests (none exist — state this explicitly and describe the manual screen/flow exercised instead)

- inspect affected execution paths (intake → analysis → validation → review → figures → reviewer-action persistence; confirm demo-seed guards and active-document handling still behave)

- report anything that could not be verified

## Agent Rules

Future agents must:

- Read AGENTS.md before modifying the repository.

- Inspect the current implementation before proposing or making changes.

- Do not guess when the answer can be verified from the repository.

- Prefer executable configuration and current code over stale documentation.

- Follow existing architecture and conventions.

- Make the smallest targeted change necessary.

- Do not perform unrelated refactoring.

- Do not modify dependencies unless required.

- Do not modify environment or configuration files unnecessarily.

- Never expose or commit credentials, tokens, API keys, passwords, or secrets.

- Do not run destructive database commands unless explicitly requested.

- Do not commit or push unless explicitly requested.

- Preserve existing behavior outside the requested change.

- Run appropriate verification after changes.

- Clearly report what was changed, what was verified, and what remains unverified.

## Git Safety

- Do not commit automatically.

- Do not push automatically.

- Do not force-push.

- Do not reset or discard user changes.

- Check git status before making significant changes.

- Preserve unrelated uncommitted work.