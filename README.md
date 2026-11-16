# JSearch

A local-first, private job-hunting tool. Upload your LaTeX resume and a list of company career sites; read-only browser agents discover openings, an LLM ranks them against your profile, and a React UI shows the matches. **You** apply manually — the tool never submits anything.

## How it works

```
resume.tex ──> LLM profile extraction ──> Candidate Profile
                                               │
companies.json ──> Playwright career agents ──> Discovered Jobs
                                               │
                                    Freshness + location filters
                                               │
                                        Deduplicate (URL)
                                               │
                                     LLM matching vs profile
                                               │
                               Eligibility gate (hard requirements)
                                               │
                          Ranked jobs  +  "ruled out" list in React UI
```

## Architecture

**Frontend** (React + Vite + Tailwind, port 3000) — all browser-side state lives in localStorage: resume, profile, companies, LLM settings, results, saved/ignored jobs. Two-zone layout: a dark rail for setup, a light column for triage. No outbound requests — fonts are bundled via `@fontsource`, never fetched from a CDN.

**Backend** (FastAPI + Playwright + Chromium, port 8000) — one process, no broker, no worker service. `POST /api/search` enqueues a search; a bounded pool of async runners executes it on the event loop. Progress streams over **SSE** with polling as automatic fallback. Lifecycle: `queued → running → completed / failed / cancelled`.

**Persistence** (SQLite via async SQLAlchemy) — jobs, searches, and matches in an embedded database (Docker named volume). Jobs are keyed by normalized-URL hash: a job matched within `SEEN_JOB_TTL_DAYS` (default 7) is not re-matched; its stored scores are reused. Profiles are cached by resume-content hash. Schema changes go through Alembic, applied automatically on startup.

**Reliability** — company browsing goes through a scheduler (`COMPANY_CONCURRENCY`, default 4) and a process-wide Chromium context cap (`MAX_BROWSER_CONTEXTS`, default 8). LLM calls are queued separately (`LLM_CONCURRENCY`, default 1): agents browse concurrently but take turns thinking. Companies retry once on failure; every search gets a time budget that scales with its company count; one failed company never affects the others.

**Pre-filtered URLs** — when `careers_url` includes query params (role, location, level), the agent skips search and location filtering and goes straight to extracting postings. This is the single highest-leverage optimization:

```jsonc
// before — agent browses 3,427 global jobs, picks ~8 at random
"careers_url": "https://careers.google.com/jobs/results/"

// after — 3 jobs, all matching your criteria
"careers_url": "https://www.google.com/about/careers/applications/jobs/results?target_level=EARLY&q=%22Software+Engineer%22&location=India"
```

## Quick start

```bash
docker compose up --build
```

Open **http://localhost:3000**.

1. **Resume** — click *Upload .tex or .pdf* (or *Paste LaTeX*). The backend extracts a candidate profile using your configured LLM.
2. **Companies** — copy `companies.example.json`, edit to taste, import via the UI. Toggle companies on/off freely.
3. **LLM settings** — configure an Ollama server (base URL + model) or any OpenAI-compatible API. API keys stay in memory only — never stored.
4. **Locations** — add target locations (e.g. *Bangalore*, *Remote*) for pre-filtering.
5. **Posted within** — select a freshness window to skip stale jobs.
6. **Find jobs** — watch live per-company progress.
7. **Resume score** (second tab) — rates the resume on open source, projects, production experience and skills, with evidence, bonuses and deductions. If the resume links a GitHub profile, its public repos are read too (set `GITHUB_TOKEN` on the backend to lift GitHub's 60 req/h anonymous limit).

## Fit vs. eligibility

Two different questions, kept apart:

- **Fit** — role/skill/experience/location breakdown. *Would you do well here?*
- **Eligibility** — does the posting state a hard bar you fail? A disqualifier is a **gate**, not a score penalty. Ruled-out jobs are shown in a collapsible section with the posting's own wording — you can disagree.

**Keyword coverage** — the share of the posting's own words that appear verbatim in your resume. Computed in Python from raw resume text, never asked of the LLM. The model treats "K8s" as "Kubernetes"; a recruiter's boolean search does not. High fit + low coverage = right job, wrong words.

## Configuration

`.env` is optional — every value has a working default (see `.env.example`). No LLM defaults are baked in; the backend is configured entirely from the UI per request.

Key knobs:

| Variable | Default | Purpose |
|---|---|---|
| `COMPANY_CONCURRENCY` | 4 | Chromium contexts per search |
| `MAX_BROWSER_CONTEXTS` | 8 | Process-wide Chromium cap |
| `LLM_CONCURRENCY` | 1 | LLM requests in flight at once |
| `SEARCH_TIMEOUT_S` | 1800 | Floor for whole-search time budget |
| `SEEN_JOB_TTL_DAYS` | 7 | Reuse matched scores within this window |
| `DISCOVERY_ATTEMPTS` | 2 | Discovery tries per company |
| `AGENT_MAX_STEPS` | 30 | Total actions per site |
| `AGENT_MAX_JOB_VISITS` | 12 | Job detail pages per site |
| `GITHUB_TOKEN` | — | Optional; raises GitHub API limit for resume scoring |

The search budget scales with company count: `rounds * per-company cap`, floored at `SEARCH_TIMEOUT_S`. Raising `SEARCH_TIMEOUT_S` is rarely needed — the real knob for long lists is `LLM_CONCURRENCY` if your model server supports parallel requests.

## Ports

| Container | Port | Notes |
|-----------|------|-------|
| frontend  | 3000 | Serves the production build; proxies `/api` to the backend |
| backend   | 8000 | FastAPI; also directly reachable |

The frontend makes zero outbound requests. The backend needs internet access for career sites and your LLM host. `docker-compose.yml` adds `host.docker.internal:host-gateway` so you can point the UI at local services.

`GET /api/health` returns 200 only when the database is reachable.

## Logs

Set `LOG_LEVEL` (default `INFO`) and `LOG_FORMAT` (`text` or `json`).

Every line carries correlation ids (`search_id`, `company`, `request_id`) so concurrent searches stay separable:

```
INFO app.services.search: [search_id=cf3e582caffa event=search.started companies=2] search started
INFO app.llm.base: [search_id=cf3e582caffa company=Google] llm call: model=qwen3:32b wait=0.0s gen=9.4s
```

`gen=` is the model's speed; `wait=` is time queued behind another company. High `wait=` with low `gen=` means more agents than the server can feed — raise `LLM_CONCURRENCY` only if it can genuinely serve more at once.

`LOG_FORMAT=json` emits one JSON object per line. API keys are redacted before anything reaches a handler.

## Testing

```bash
# Backend (no real sites, no real LLM)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
.venv/bin/python -m pytest

# Database schema changes
.venv/bin/alembic revision --autogenerate -m "what changed"

# Frontend
cd ../frontend
npm install && npm test && npm run build
```

All browser-agent tests run against a deterministic local fixture (`backend/tests/browser_fixture/`) — never against real career sites. The test suite includes:

- **275+ backend tests** covering agent navigation, link harvesting, location/freshness filtering, keyword coverage, eligibility ranking, persistence, reliability, LLM queue serialization, SSE streaming, and Alembic migrations
- **68 frontend tests** covering components, local store, search progress, and a CI guard against third-party assets on the page load

## Troubleshooting

**"Could not connect to Ollama"** — check the base URL in the UI. Hosted URLs must include any path prefix (e.g. `/ollama`).

**"Model not found"** — the model name doesn't exist on that server. List available models: `curl <base_url>/api/tags`.

**"Career site could not be navigated"** — some sites block headless browsers. Other companies continue unaffected.

**"LLM returned invalid structured data"** — small models sometimes produce malformed JSON. The backend retries once; try a stronger model.

**Backend restarted mid-search** — active searches are in-memory only; a restart marks them `failed`. Resume/companies/settings are safe in browser localStorage; completed history is safe in SQLite.
