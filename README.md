# Screening Accuracy Analyzer

Fetches the AI candidate-screening decisions from the **Paul's Job** recruiting
platform API, turns them into easy-to-read insights, and serves them from a small
Flask + Plotly web UI. Runs locally or in Docker.

## Goals

The tool answers two questions about Paul's automated screening:

**What is the AI deciding?**

- Split every step conclusion into **positive / negative / opt-out / pending** from
  `PaulDecision`.
- Tally the **most common rejection reasons** from the free-text decision summary,
  normalised before counting.
- Surface the **positive signals** that lead to a candidate being advanced.
- Break all of the above down **by job** and **by pipeline step**.
- Show **opt-outs** by sub-reason (no answer / declined the AI interview / withdrew)
  and by the step they happen at.
- Plot **decisions over time** (ISO week) to see throughput and trend.

**Was the AI right?**

- **AI vs. human agreement** — where a human reviewed a conclusion, compare their
  verdict with Paul's (agreement rate + a confusion table), plus how often human /
  agent review is triggered at all.
- **Assessment score vs. AI decision** — distribution of structured-assessment
  scores split by what Paul decided for that candidate.
- **Disagreement list** — candidates Paul rejected who passed their assessment, or
  advanced who failed, ranked by distance from the passing mark.
- **Assessments by job** — mean score and pass rate per role.

## Architecture

Three layers, each testable on its own:

| Layer | Module | Responsibility |
| ----- | ------ | ---------------|
| API client | `screening/api_client.py` | The only module doing HTTP. Auth, tracing headers, retry/backoff, both pagination styles. Returns plain dicts. |
| Analysis | `screening/analysis.py` | Pure functions, no I/O, no framework. Normalised records → aggregates. |
| Presentation | `app/` | Flask app factory, routes, `charts.py` (Plotly HTML fragments), Jinja templates. |

Data flow: request → route → `services.py` (client + cache) → `analysis.py` →
`charts.py` → template.

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1            # PowerShell (use source .venv/bin/activate on POSIX)
pip install -r requirements.txt

cp .env.example .env                  # then set PAULSJOB_API_KEY (or SCREENING_DEMO=1)
```

The API key is read **only** from the environment. `.env`, `.env.*` and `*.local`
are git-ignored; never commit a real key. `.env.example` is committed with empty
values.

### Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `PAULSJOB_API_KEY` | &mdash; | Company API key. Required unless `SCREENING_DEMO` is set. |
| `PAULSJOB_API_BASE_URL` | `https://api.paulsjob.ai/dev/v1` | API base URL (dev tenant by default). |
| `SCREENING_DEMO` | `0` | `1`/`true`/`yes`/`on` → run against the bundled demo dataset, no API key needed. |
| `SCREENING_CACHE_TTL` | `900` | On-disk cache lifetime, seconds. Must be an integer. |
| `FLASK_DEBUG` | &mdash; | Standard Flask flag. |

## Run

```bash
flask --app app run --debug                     # http://127.0.0.1:5000
SCREENING_DEMO=1 flask --app app run --debug     # same, against demo data

docker compose up --build                        # http://127.0.0.1:8000 (gunicorn)
```

Docker reads `.env` via `env_file` and bind-mounts `./.cache`. To run the container
against demo data, add `SCREENING_DEMO=1` to `.env`.

### Routes

| Route | Purpose |
| ----- | ------- |
| `/` | Screening-decisions dashboard (current pipeline step per application). |
| `/?deep=1` | Also walks each application's full step history — slower, gives reason text for every past conclusion. Ignored in demo mode. |
| `/?refresh=1` | Bypass the on-disk cache and re-fetch. |
| `/assessments` | Structured-assessment dashboard (scores, pass rates, score-vs-decision, disagreements). |
| `/assessments?refresh=1` | As above, re-fetch. |
| `/healthz` | Liveness check. |

### Demo data

```bash
python demo/generate.py --persons 60 --seed 42   # writes demo/applications.json, demo/assessments.json
```

Deterministic; regenerate after changing the knobs at the top of the script.

## API endpoints

Auth: header `x-company-api-key: <PAULSJOB_API_KEY>` on every request
(`CompanyApiKeyAuth`; no bearer token). Tracing: `paul-correlation-id` (one UUIDv4
per analysis run) and `paul-request-id` (fresh per request).

### Used by the dashboards

| Purpose | Call | Pagination |
| ------- | ---- | ---------- |
| Screening decisions across all applications | `POST /recruiting/applications/search-applications` → `ApplicationSearchListData[]` (`Application`, `Person`, `Job`, `StepName`, `StepCategory`, `PaulDecision`, `PaulDecisionSummary`, `HumanReview`, `AgentReview`) | Page / PerPage, `data.TotalPage` |
| Per-application decision trail (`?deep=1`) | `GET /recruiting/person/{person_slug}/applications/{application_id}` → `DetailedJobApplication.JobStepAssignmentHistory[]` (`PaulDecision`, `PaulDecisionExplanation`, `PaulDecisionSummary`, `StepCategory`) | &mdash; |
| Structured assessments | `GET /company/person/{person_slug}/assessments` → `Assessment[]` (`Type`, `Status`, `AssessmentScore`, `AssessmentDetails`) | none (one call per candidate) |

### Implemented in the client, not yet surfaced in the UI

| Purpose | Call |
| --------| ---- |
| List jobs | `POST /recruiting/jobs/search-jobs` |
| Pipeline steps for a job | `GET /recruiting/jobs/{paulsjob_job_id}/steps` |
| Interview scorecards | `POST /recruiting/interviews/search-interviews` (embedded `ScoreCards`) |

`PaulDecision` vocabulary: `PositiveDecision`, `NegativeDecision`, `OptOutNoAnswer`,
`OptOutDeclineToTalkWithAI`, `OptOutDeclineToContinueApplication`.

## Assumptions

- **No company-wide assessments endpoint.** Assessments are fetched one call per
  candidate; the candidate list comes from the cached application search, and the
  result is cached as `{person_slug: Assessment[]}`. A per-candidate failure is
  logged and skipped, not fatal.
- **`Assessment.AssessmentDetails` is schema-free** (`additionalProperties: true`).
  Every key is read defensively; `PassingScore` is taken from there when present.
- **Assessments are not job-scoped in the API**, so each is joined to the job the
  candidate applied for (first application wins) to support the by-job view.
- **A missing / empty / unrecognised `PaulDecision` is treated as _pending_** (not
  yet concluded), not as an error.
- **Rejection-reason text is free text.** It is normalised — whitespace collapsed,
  first sentence only, lowercased — then counted. No semantic clustering.
- **AI vs. human agreement:** `ApplicationSearchListData` exposes `HumanReview` and
  `AgentReview` as booleans; the spec at hand does not name the field carrying the
  human's actual verdict, so it is modelled as a sibling string `HumanDecision`.
  Agreement is computed only for conclusions that carry that value; otherwise the
  chart shows an empty state and only the review-trigger counts are reported. The
  demo generator emits `HumanDecision`; adjust the key in
  `analysis.record_from_search_item` once the real name is known.
- **Decisions-over-time** buckets by ISO week from `Application.ApplicationDate`;
  conclusions with no date are excluded from that chart only.
- **"Passed" an assessment** means `AssessmentScore >= AssessmentDetails.PassingScore`.
  A rejected-but-passed or advanced-but-failed candidate is flagged as a
  disagreement.
- **Caching.** The whole decision set is fetched once and cached to disk (TTL
  `SCREENING_CACHE_TTL`, default 900s) because the search endpoints page slowly;
  re-fetching per request is not viable in development. Cache writes are
  best-effort — a write failure is logged and the request still succeeds.
- **Pagination safety.** Both paginators stop after `MAX_PAGES` (1000) iterations to
  bound a misbehaving API; `TotalPage` is trusted only when present, otherwise an
  empty page ends the loop.
- **Base URL defaults to the dev tenant.** That tenant currently returns zero
  assessments, which is why demo mode exists — to exercise the full UI without live
  data.
- **Demo mode ignores `?deep=1`** and always returns current-step records.

## Tests

```bash
pytest
pytest tests/test_analysis.py::test_analyze_groups_and_tallies_reasons -v
```

Analysis is driven by fixture JSON under `tests/fixtures/`; the API client is tested
with `requests-mock` — no real network calls in the suite.

## Layout

```
config.py              env-only configuration
screening/
  api_client.py        the only module doing HTTP (auth, tracing headers, retry, pagination)
  analysis.py          pure: dict -> records, and analyze() / analyze_assessments()
  cache.py             tiny atomic on-disk JSON cache
  demo.py              loader for the bundled demo dataset
app/
  __init__.py          Flask app factory
  routes.py            /, /assessments, /healthz, error handlers
  services.py          client + cache + analysis glue
  charts.py            Plotly figure builders (HTML fragments)
  templates/, static/
demo/generate.py       deterministic demo-data generator
tests/                 pytest, HTTP mocked with requests-mock
```

See `CLAUDE.md` for the fuller design notes.
