# Screening Accuracy Analyzer

Fetches the AI candidate-screening decisions from the **Paul's Job** platform API,
separates positive from negative conclusions, extracts the most common rejection
reasons, groups results by job and pipeline step, and shows the insights in a small
Flask + Plotly web UI. Runs in Docker.

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1            # PowerShell (use source .venv/bin/activate on POSIX)
pip install -r requirements.txt

cp .env.example .env                  # then set PAULSJOB_API_KEY
```

The API key is read **only** from the environment (`PAULSJOB_API_KEY`). `.env` is
git-ignored; never commit a real key.

## Run

```bash
flask --app app run --debug          # http://127.0.0.1:5000
# or
docker compose up --build            # http://127.0.0.1:8000
```

- `/` &mdash; insights dashboard (current pipeline step per application).
- `/?deep=1` &mdash; also walks each application's full step history (slower, richer
  rejection-reason text).
- `/?refresh=1` &mdash; bypass the on-disk cache and re-fetch.
- `/healthz` &mdash; liveness check.

## Tests

```bash
pytest
pytest tests/test_analysis.py::test_analyze_groups_and_tallies_reasons -v
```

## Layout

```
config.py              env-only configuration
screening/
  api_client.py        the only module doing HTTP (auth, tracing headers, retry, pagination)
  analysis.py          pure: dict -> DecisionRecord, and analyze()
  cache.py             tiny on-disk JSON cache
app/
  __init__.py          Flask app factory
  routes.py            the / and /healthz routes
  services.py          client + cache + analysis glue
  charts.py            Plotly figure builders (HTML fragments)
  templates/, static/
tests/                 pytest, HTTP mocked with requests-mock
```

See `CLAUDE.md` for the endpoint reference and design notes.
