# TestGen-AI
[![TestGen-AI CI](https://github.com/saarikar/testgenai/actions/workflows/ci.yml/badge.svg)](https://github.com/saarikar/testgenai/actions/workflows/ci.yml)

**Generate tests. Inspect the evidence.** A Python/FastAPI portfolio project for test automation, API testing, AI output evaluation, relational data, and observable execution.

Submit Python, generate a pytest suite through Groq or OpenAI, execute it locally, and inspect test results, branch coverage, timings, and persistent run history. A separate evaluation harness checks whether the same generated suite passes correct code and catches deliberate bugs.

## Quick start — Windows

Python 3.12 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Only copy the template if you do not already have a .env file:
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m uvicorn main:app --env-file .env --host 127.0.0.1 --port 8000
```

Save the configuration as `.env`, not `.env.txt`. Set `GROQ_API_KEY` and an enabled `GROQ_MODEL`, or configure `OPENAI_API_KEY` / `OPENAI_MODEL`. The template defaults to Groq. Never commit real credentials. SQLite is the default local database; migrations are applied during startup.

Open **http://127.0.0.1:8000/** for the dashboard or **http://127.0.0.1:8000/docs** for Swagger. Stop an older server with Ctrl+C and restart it after upgrading the project. No frontend build step is needed.

## Ubuntu / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # only on initial setup
# Edit .env with your provider credentials.
python -m uvicorn main:app --env-file .env --host 127.0.0.1 --port 8000
```

If the system lacks venv support, install Ubuntu's `python3-venv` package. Linux process groups allow the runner to kill ordinary descendants on timeout; Windows uses taskkill with weaker orphan cleanup guarantees.

## What the project demonstrates

| Job requirement | Concrete evidence |
|---|---|
| Test automation / API testing | Real pytest subprocess tests, FastAPI TestClient checks, negative-path tests |
| AI output evaluation | 10 specified examples, 20 deliberate bugs, repeated generation, eligibility and bug-detection metrics |
| Git / build pipelines | Ruff, tests, coverage, PostgreSQL integration, Docker build and health smoke test in GitHub Actions |
| Logs / reporting | JSON events with request IDs, JUnit XML, coverage HTML/XML, dashboard and saved failures |
| OOP / Python | Generator protocol and adapter, local runner, repository, plus class-based benchmark examples |
| Relational database | SQLAlchemy run/test-case relationships, Alembic migrations, PostgreSQL Compose service |
| Linux | Ubuntu CI, non-root Linux image, process-group cleanup, documented Linux setup |

## Architecture

```mermaid
flowchart LR
  UI[Dashboard / Swagger] --> API[FastAPI]
  API --> GEN[LangChain generator]
  GEN --> LLM[Groq / OpenAI]
  API --> RUN[Local pytest + coverage runner]
  RUN --> TMP[Temporary source and test files]
  API --> DB[(SQLite / PostgreSQL)]
  API --> LOG[JSON events with request IDs]
  DATA[Specifications + correct code + mutants] --> EVAL[Evaluation CLI]
  EVAL --> GEN
  EVAL --> RUN
  EVAL --> REPORT[JSON + Markdown evaluation reports]
```

`services/ai_generator.py` defines the generator contract, typed suite metadata, and prompt version. `services/sandbox.py` owns execution and bounded output collection. `services/repository.py` owns transactions and reports. The API coordinates these responsibilities; the evaluation harness reuses the generator and runner.

## API

| Endpoint | Purpose |
|---|---|
| `POST /generate-tests` | Generate, execute, and persist a suite |
| `GET /runs?limit=20&offset=0&status=passed` | Paginated/filterable run summaries |
| `GET /runs/{run_id}` | Generated tests, logs, coverage, and individual results |
| `GET /metrics` | Run counts by outcome and mean generation/execution times |
| `GET /health` | Liveness; not a provider-readiness check |

```json
{"code":"def add(a, b):\n    return a + b\n","provider":"groq","timeout_seconds":10}
```

Successful generation/execution responses contain `run_id`, `generated_tests`, `generation_seconds`, optional `token_usage`, and `execution`. Execution contains outcome, exit code, timeout flag, logs, truncation flag, test counts, individual results, and coverage totals. Test failures and test timeouts are HTTP 200 execution outcomes. Invalid source is 422; unavailable configuration/capacity/storage is 503; provider errors or malformed generated code are 502; generation timeout is 504; unexpected runner errors are 500.

Each response has `X-Request-ID`; successful run IDs match that request ID. Valid accepted generation attempts, including provider failures, are recorded. Invalid requests and capacity rejections appear in HTTP logs but do not create run records. Logs contain event names, IDs, outcomes, and durations, not source or credentials. Reports do contain generated tests and captured test output, which may include submitted data.

The source is represented in storage by SHA-256, not the original text. Model, provider, prompt version, token usage (if supplied), separate timings, and generated tests are retained. JUnit test cases are stored in a related table. Evaluation artifacts are separate local JSON/Markdown files, not database records.

## Verify and evaluate

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest --junitxml=artifacts/junit.xml --cov --cov-report=html:artifacts/htmlcov --cov-report=xml:artifacts/coverage.xml
.\.venv\Scripts\python.exe -m evaluation.run --mode reference --repeats 3 --output artifacts/reference
```

The offline reference mode uses hand-written tests and makes no provider calls. **Its results validate the harness, not AI performance.** Read the [measured reference baseline](docs/reference-baseline.md) and [evaluation methodology](docs/evaluation.md).

Live evaluation uses your provider quota and credentials:

```powershell
# Start with one example to check credentials and limits.
.\.venv\Scripts\python.exe -m evaluation.run --mode live --provider groq --case clamp --repeats 1 --env-file .env --output artifacts/live-smoke
# Then evaluate all ten examples, three generations each.
.\.venv\Scripts\python.exe -m evaluation.run --mode live --provider groq --repeats 3 --delay 60 --env-file .env --output artifacts/live
```

Requests run sequentially, with configurable pacing. Rate-limit errors are recorded as generation errors; there are no hidden retries. Each attempt checkpoints to disk. Outputs are `checkpoint.json`, `report.json`, and `report.md`; use separate output directories to preserve experiments. Review generated assertions against the specifications before drawing conclusions.

## PostgreSQL and Docker

Install Docker, add `POSTGRES_PASSWORD` to `.env` (use a URL-safe development password), then:

```sh
docker compose up --build
```

Compose starts PostgreSQL, waits for its health check, then runs the API with PostgreSQL persistence. The database has a named volume and no published host port. The API binds only to localhost. `docker compose down` preserves the database volume; do not add `-v` unless you intend to delete it.

For an existing database, set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB`. Percent-encode special characters in URL credentials. The single API worker applies Alembic migrations at startup. For multiple replicas, perform migrations once as a deployment step before starting replicas. Manual migration: `python -m alembic upgrade head` with `DATABASE_URL` already exported in your shell (Alembic does not load `.env` itself).

To exercise PostgreSQL tests locally, set `TEST_DATABASE_URL` to a disposable test database and run `python -m pytest -m postgres`. CI supplies its own PostgreSQL service. Never point test configuration at production data.

## CI and Git

`.github/workflows/ci.yml` runs on pushes and pull requests: Ruff checks, pytest with JUnit/coverage artifacts, a PostgreSQL integration test, an offline reference benchmark, and a Docker build/health smoke test. Live LLM calls do not run in CI. Reports are uploaded even if a test fails. The workflow becomes active after pushing this repository to GitHub; no hosted CI success is claimed before that happens.

A local Git repository is initialized. Review `git status` before your first commit. Environment files (including `.env.txt`), databases, virtual environments, and generated artifacts are ignored. No remote or author identity is configured for you. See [portfolio walkthrough](docs/demo.md) for a demo script and defensible résumé claims.

## Execution scope and limitations

This application runs arbitrary submitted and generated Python **for trusted local development**. A subprocess and temporary directory are not a security sandbox. The runner removes credentials from its child environment, but code can still access files, network, and other processes with the same user's privileges. API and test execution share a container in Compose. Public deployment requires separate disposable workers with no credentials, restricted networking, quotas, authentication, and rate limiting; that is not implemented here.

Two accepted runs may generate/execute concurrently per worker. Generation has a 60-second deadline; tests allow 1–60 seconds. Cleanup/reporting can add a few seconds. Logs retain 64 KiB per stream; reports are size-limited when read. The Docker setup adds memory, PID, and temporary-filesystem limits. Missing imports remain execution errors; dependencies are never installed automatically from submitted code.

Passing tests and high coverage do not establish specification correctness. Hand-designed mutants cover only selected bugs. Token usage is null when the provider does not report it. Live model comparisons, hosted CI results, and a Docker/PostgreSQL deployment must be measured in their actual environments.

References: [coverage JSON reports](https://coverage.readthedocs.io/en/latest/commands/cmd_json.html), [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html), [LangChain Groq](https://docs.langchain.com/oss/python/integrations/chat/groq).

Measured local checks are recorded in [verification results](docs/verification.md). A standalone Docker container defaults to temporary SQLite storage under /tmp; use Compose/PostgreSQL for durable container storage.
