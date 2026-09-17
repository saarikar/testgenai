"""TestGen-AI: generation, execution, and persistent reporting."""

import asyncio
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from services.ai_generator import PROMPT_VERSION, ConfigurationError, GenerationError
from services.ai_generator import generate_suite as generate_tests
from services.repository import RunRepository
from services.sandbox import ExecutionResult, LocalTestRunner, validate_python
from services.telemetry import event

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = RunRepository()
    await run_in_threadpool(repository.migrate)
    app.state.repository = repository
    app.state.slots = asyncio.Semaphore(2)
    app.state.runner = LocalTestRunner()
    try:
        yield
    finally:
        repository.close()


app = FastAPI(
    title="TestGen-AI",
    version="2.0.0",
    lifespan=lifespan,
    description="Generate, execute, and evaluate pytest suites. Trusted local code only.",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def correlate_requests(request: Request, call_next):
    request.state.request_id = str(uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    event(
        "http_request",
        request_id=request.state.request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=round(time.perf_counter() - started, 4),
    )
    return response


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=50_000)
    provider: Literal["openai", "groq"] | None = None
    timeout_seconds: int = Field(default=10, ge=1, le=60, strict=True)

    @field_validator("code")
    @classmethod
    def nonempty_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must contain Python source")
        return value


class GenerateResponse(BaseModel):
    run_id: str
    generated_tests: str
    execution: ExecutionResult
    generation_seconds: float
    token_usage: dict | None = None


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/runs")
def list_runs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = None,
):
    return request.app.state.repository.list(limit, offset, status)


@app.get("/runs/{run_id}")
def get_run(run_id: str, request: Request):
    result = request.app.state.repository.get(run_id)
    if result is None:
        raise HTTPException(404, "Run not found")
    return result


@app.get("/metrics")
def metrics(request: Request):
    return request.app.state.repository.metrics()


@app.post("/generate-tests", response_model=GenerateResponse)
async def generate_and_run(payload: GenerateRequest, request: Request) -> GenerateResponse:
    try:
        validate_python(payload.code, "module_under_test.py")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "source_syntax_error",
                "message": str(exc),
                "line": getattr(exc, "lineno", None),
                "column": getattr(exc, "offset", None),
            },
        ) from exc
    slots = request.app.state.slots
    try:
        await asyncio.wait_for(slots.acquire(), timeout=1)
    except TimeoutError as exc:
        raise HTTPException(
            503, "Server busy; retry shortly", headers={"Retry-After": "2"}
        ) from exc
    started = time.perf_counter()
    provider = (payload.provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    record = dict(
        id=request.state.request_id,
        source_hash=hashlib.sha256(payload.code.encode()).hexdigest(),
        provider=provider,
        model=os.getenv(f"{provider.upper()}_MODEL", "unconfigured"),
        prompt_version=PROMPT_VERSION,
        generation_seconds=0.0,
        status="error",
    )
    error = None
    result = None
    try:
        suite = await generate_tests(payload.code, payload.provider)
        record.update(
            generation_seconds=round(time.perf_counter() - started, 4),
            generated_tests=suite.tests,
            provider=suite.provider,
            model=suite.model,
            prompt_version=suite.prompt_version,
            token_usage=suite.token_usage,
        )
        execution = await run_in_threadpool(
            request.app.state.runner.run,
            payload.code,
            suite.tests,
            payload.timeout_seconds,
            coverage=True,
        )
        record.update(
            status=execution.status,
            execution=execution.model_dump(),
            execution_seconds=execution.duration_seconds,
        )
        result = GenerateResponse(
            run_id=record["id"],
            generated_tests=suite.tests,
            execution=execution,
            generation_seconds=record["generation_seconds"],
            token_usage=suite.token_usage,
        )
    except ConfigurationError as exc:
        error = HTTPException(503, str(exc))
    except TimeoutError:
        error = HTTPException(504, "LLM generation timed out")
    except GenerationError as exc:
        error = HTTPException(502, str(exc))
    except Exception as exc:
        logger.error("TestGen request failed (%s)", type(exc).__name__)
        error = HTTPException(500, "Internal test execution error")
    finally:
        slots.release()
    if error:
        record["error"] = str(error.detail)
        if "generated_tests" not in record:
            record["generation_seconds"] = round(time.perf_counter() - started, 4)
    try:
        await run_in_threadpool(request.app.state.repository.save, record)
    except Exception as exc:
        event("persistence_error", run_id=record["id"], error_type=type(exc).__name__)
        raise HTTPException(503, "Run history storage unavailable") from exc
    event(
        "run_completed",
        run_id=record["id"],
        status=record["status"],
        generation_seconds=record["generation_seconds"],
        execution_seconds=record.get("execution_seconds"),
    )
    if error:
        raise error
    return result
