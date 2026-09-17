# Portfolio walkthrough

## Offline demo, no API key required

```powershell
.\.venv\Scripts\python.exe -m scripts.seed_demo --database-url sqlite:///./demo.db
$env:DATABASE_URL = "sqlite:///./demo.db"
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The seed script adds three real local executions: a passing reference test, a deliberate bug caught by that test, and a timeout. They are labeled `reference` / `offline-demo`, with generation duration zero. Running it again adds another three runs; it does not delete anything. Remove the `DATABASE_URL` shell variable before returning to your ordinary database configuration.

## Two-minute recording outline

1. Explain the problem: generated tests can look convincing while missing bugs.
2. Open the dashboard and select the passing offline run. Show test counts, branch coverage, and generated code.
3. Select the failed run. Show the assertion and logs that identify the intentionally broken clamp implementation.
4. Select the timeout run. Explain that the subprocess was terminated and no fabricated counts were returned.
5. Show `docs/reference-baseline.md`. State clearly that these are reference/harness results, then describe the separate live evaluation command.
6. Show the GitHub Actions workflow and database relationship. When pushed, replace the workflow code view with an actual CI run and its artifacts.
7. For a live provider demonstration, restart with your real `.env`, generate one small example, and disclose the provider/model. Never display your credentials.

A recording is not bundled. Use this outline to record the application on your own computer.

## Claims supported by the implementation

- Built a FastAPI application integrating Groq/OpenAI through LangChain, pytest execution, branch coverage, and persistent reports.
- Designed a 10-example evaluation dataset with 20 deliberate bugs and a repeated-run evaluation protocol.
- Implemented PostgreSQL-compatible storage and migrations, structured telemetry, and an Ubuntu CI workflow.

Do not describe reference bug-detection scores as AI accuracy, claim a public security sandbox, or claim a CI/deployment result until you have run it. After a live evaluation, add measured eligibility, false-failure, and bug-detection results to your résumé with the dataset size and model name.
