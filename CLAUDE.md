# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ScreeningAccuracyAnalyzer is a job-application task for **Paul's Job** (`paulsjob.ai`), a
company whose automated-recruiting platform exposes a REST API. The tool fetches the AI's
candidate-screening decisions from that API, separates positive from negative criteria,
extracts the most common rejection reasons, groups the results by job and/or pipeline step,
and presents easy-to-understand insights in a Flask web UI. It ships as a Docker container.

## Status

Greenfield: no code exists yet. The layout, commands, and file paths below describe the
intended shape. Build it, don't assume it's already there.

## Decisions already made

- Python + **Flask**, server-rendered **Jinja2** templates with **Plotly** figures embedded
  as HTML fragments (`fig.to_html(full_html=False)`); minimal JS.
- pandas + numpy for aggregation. scikit-learn only if a metric helper is genuinely needed.
- Dependencies in `requirements.txt` (pip), not poetry.
- Tests with **pytest**.
- `Dockerfile` + `docker-compose.yml` for a one-command local run.

## Commands

```bash
python -m venv .venv && .venv\Scripts\Activate.ps1     # PowerShell; use bin/activate on POSIX
pip install -r requirements.txt

flask --app app run --debug          # dev server (once app/ exists)
docker compose up --build            # run via Docker

pytest                               # all tests
pytest tests/test_analysis.py::test_rejection_reason_tally -v   # single test
```

No linter/formatter is configured; do not invent one.

## Environment variables

Never hard-code the API key. Load it only from the environment (via `python-dotenv` from a
local `.env` that is git-ignored, or compose `environment:`).

- `PAULSJOB_API_KEY` — the company API key (`pj_...`). Required.
- `PAULSJOB_API_BASE_URL` — defaults to `https://api.paulsjob.ai/dev/v1`.
- `FLASK_ENV` / `FLASK_DEBUG` — as usual.

`.env`, `.env.*`, and `*.local` must be in `.gitignore`. Add a committed `.env.example` with
empty values.

## API notes (Paulsjob API v1)

- **Auth**: header `x-company-api-key: <PAULSJOB_API_KEY>` on every request (the
  `CompanyApiKeyAuth` scheme). No bearer token.
- **Tracing headers**: send `paul-correlation-id` (one UUIDv4 per analysis run, shared across
  all its requests) and `paul-request-id` (a fresh UUIDv4 per request). Both echo back in the
  response headers.
- **Pagination** comes in two shapes:
  - cursor: `LastEvaluatedKey` in the request, echoed in `data.LastEvaluatedKey` until empty
    (person list, assessments, notes, ...).
  - page: `Page` / `PerPage` in the body, with `data.Total` / `data.TotalPage` in the
    response (the `search-*` endpoints).
- Wrap the HTTP layer with retry + exponential backoff on `429` and `5xx`.

### Endpoints this tool relies on

| Purpose | Call |
| --- | --- |
| List jobs | `GET /recruiting/jobs` (deprecated) or `POST /recruiting/jobs/search-jobs` |
| Pipeline steps for a job | `GET /recruiting/jobs/{paulsjob_job_id}/steps` |
| Screening decisions across all applications | `POST /recruiting/applications/search-applications` → `ApplicationSearchListData[]` with `Application`, `Person`, `Job`, `StepName`, `StepCategory`, `PaulDecision`, `PaulDecisionSummary`, `HumanReview`, `AgentReview` |
| Per-application decision trail | `GET /recruiting/person/{person_slug}/applications/{application_id}` → `DetailedJobApplication.JobStepAssignmentHistory[]` with `PaulDecision`, `PaulDecisionExplanation`, `PaulDecisionSummary`, `PaulThinkingProcess`, `StepCategory`; plus `PrescreeningQnA` |
| Prescreening question scores | `GET /recruiting/{person_slug}/jobs/{paulsjob_job_id}/prescreening/questions` → per-question `Score` / `ScoreExplanation` |
| Structured assessments | `GET /company/person/{person_slug}/assessments` → `Assessment[]` (`Type`, `Status`, `AssessmentScore`, `AssessmentDetails`) |

`PaulDecision` vocabulary: `PositiveDecision`, `NegativeDecision`, `OptOutNoAnswer`,
`OptOutDeclineToTalkWithAI`, `OptOutDeclineToContinueApplication`.

## Architecture (the big picture)

Three layers, kept separate so each is testable on its own:

- **API client** (`screening/api_client.py`): the only module that does HTTP. Owns the base
  URL, the `x-company-api-key` header, the two tracing headers, both pagination styles, and
  retry/backoff. Returns plain dicts / dataclasses. Never imported by templates.
- **Analysis** (`screening/analysis.py`): pure functions over the fetched records, framework-
  free and I/O-free.
  - classify each step conclusion as positive / negative / opt-out from `PaulDecision`.
  - tally rejection reasons from `PaulDecisionSummary` + `PaulDecisionExplanation` on
    negative conclusions; normalize/cluster the free text before counting.
  - group counts by job (`PaulsjobJobID` / `JobPositionTitle`) and by pipeline step
    (`StepCategory`, `StepName`).
- **Presentation** (`app/`): Flask app factory (`app/__init__.py`), route blueprints, Jinja
  templates in `app/templates/`, and Plotly figure builders in `app/charts.py` that turn
  analysis output into embeddable HTML. Chart colors / layout defaults live only here.

**Data flow**: request → route → api_client fetch (or cached fixture) → analysis functions →
chart builders → template render.

**Caching**: fetch the decision set once per run and cache to disk/memory; the platform has
many candidates and the search endpoints page slowly, so re-fetching per request is not
viable during development.

## Testing approach

- Analysis functions: drive with fixture JSON captured from real API responses, stored under
  `tests/fixtures/`.
- API client: mock HTTP with `responses` or `requests-mock`. Keep real network calls out of
  the suite.

## Verification (end to end)

1. `pip install -r requirements.txt`, set `PAULSJOB_API_KEY` and `PAULSJOB_API_BASE_URL` in
   `.env`.
2. `pytest` — analysis and client tests green.
3. `flask --app app run --debug`, open the UI, confirm the insights page renders: a
   positive/negative breakdown, a most-common-rejection-reasons chart, and the same broken
   down by job and by pipeline step.
4. `docker compose up --build` and repeat step 3 against the container.
