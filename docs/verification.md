# Local verification

Verified on Windows with Python 3.12.14.

| Check | Result |
|---|---|
| Regression suite | 48 passed, 1 skipped |
| Application/evaluator coverage (statements and branches) | 89.67%; CI gate 80% |
| Ruff lint and formatting | Passed |
| Dependency compatibility (`pip check`) | Passed |
| Offline reference evaluation | 10 examples × 3 repeats; 30 eligible suites |
| Deliberate bug detection by reference suites | 60/60 executed variants detected |
| SQLite migrations, transactions, restart persistence | Passed |
| Browser inspection | Dashboard layout, saved failure, generated-code view, filtered history verified |
| Local PostgreSQL integration | Skipped: no PostgreSQL service; CI job supplies one |
| Docker build / Ubuntu execution | Configured in CI, not executed locally: Docker unavailable |
| Live model evaluation | Not run; no claim about model accuracy |
| Hosted GitHub Actions | Workflow ready; repository has not been pushed |

Command used:

```powershell
.\.venv\Scripts\python.exe -m pytest --junitxml=artifacts/junit.xml --cov --cov-fail-under=80 --cov-report=xml:artifacts/coverage.xml --cov-report=html:artifacts/htmlcov
```

Local JUnit and coverage artifacts are in `artifacts/`. That directory is ignored by Git; CI uploads its own artifacts. The suite emitted an upstream Starlette/AnyIO deprecation warning and a Windows pytest-cache permission warning; neither prevented testing or report generation.

The offline evaluation validates the reference tests and scoring infrastructure. It must not be presented as a live LLM benchmark. See `reference-baseline.md` and `evaluation.md` for methodology and limitations.
