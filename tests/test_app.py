import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from services import ai_generator
from services.ai_generator import (
    ConfigurationError,
    GeneratedSuite,
    GenerationError,
    normalize_tests,
)
from services.sandbox import LOG_LIMIT, run_tests, validate_python

SOURCE = "def add(a, b):\n    return a + b\n"
TESTS = "from module_under_test import add\ndef test_add():\n    assert add(2, 3) == 5\n"


def test_pass_and_failure_results():
    result = run_tests(SOURCE, TESTS + "\ndef test_bad():\n    assert add(1, 1) == 3\n")
    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.summary == dict(total=2, passed=1, failed=1, error=0, skipped=0)
    assert "assert 2 == 3" in result.stdout


def test_timeout_preserves_output():
    result = run_tests(
        "",
        'import time\ndef test_slow():\n    print("started", flush=True)\n    time.sleep(30)\n',
        2,
    )
    assert result.status == "timeout"
    assert result.timed_out
    assert result.duration_seconds < 10
    assert "started" in result.stdout


@pytest.mark.parametrize("code", ["def broken(:", "return 1", 'x = "\x00"'])
def test_invalid_source(code):
    with pytest.raises((SyntaxError, ValueError)):
        validate_python(code, "source.py")


def test_collection_error():
    result = run_tests("", "import package_that_does_not_exist_87422\ndef test_x(): pass\n")
    assert result.status == "error"
    assert result.summary["error"] == 1


def test_no_tests():
    assert run_tests("", "x = 1\n").status == "no_tests"


def test_skipped_result():
    result = run_tests("", 'import pytest\ndef test_skip(): pytest.skip("example")\n')
    assert result.summary["skipped"] == 1
    assert result.tests[0].message == "example"


def test_logs_are_bounded_and_secrets_removed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--bad-option")
    result = run_tests(
        "",
        'import os\ndef test_env():\n    assert "OPENAI_API_KEY" not in os.environ\n    print("x" * 100000)\n',
    )
    assert result.status == "passed"
    assert result.logs_truncated
    assert len(result.stdout.encode()) <= LOG_LIMIT


def test_normalize_fence_and_blocks():
    assert normalize_tests("```python\n" + TESTS + "```") == TESTS
    assert normalize_tests([{"type": "text", "text": TESTS}]) == TESTS


@pytest.mark.parametrize(
    "content", ["", "Here are your tests:\ndef test_x(): pass", "def broken(:"]
)
def test_invalid_generated_output(content):
    with pytest.raises(GenerationError):
        normalize_tests(content)


def test_api_success(monkeypatch):
    mock = AsyncMock(return_value=GeneratedSuite(TESTS, "mock", "fixture"))
    monkeypatch.setattr(main, "generate_tests", mock)
    with TestClient(main.app) as client:
        response = client.post("/generate-tests", json={"code": SOURCE})
    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["status"] == "passed"
    assert body["execution"]["summary"]["passed"] == 1
    assert body["generated_tests"] == TESTS


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "def broken(:"},
        {"code": "   "},
        {"code": SOURCE, "timeout_seconds": 0},
        {"code": SOURCE, "timeout_seconds": 61},
        {"code": SOURCE, "provider": "unknown"},
    ],
)
def test_api_validation_precedes_llm(monkeypatch, payload):
    mock = AsyncMock()
    monkeypatch.setattr(main, "generate_tests", mock)
    with TestClient(main.app) as client:
        assert client.post("/generate-tests", json=payload).status_code == 422
    mock.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ConfigurationError("missing config"), 503),
        (GenerationError("invalid tests"), 502),
        (TimeoutError(), 504),
        (RuntimeError("private detail"), 500),
    ],
)
def test_api_error_mapping(monkeypatch, error, status):
    monkeypatch.setattr(main, "generate_tests", AsyncMock(side_effect=error))
    with TestClient(main.app) as client:
        response = client.post("/generate-tests", json={"code": SOURCE})
    assert response.status_code == status
    assert "private detail" not in response.text


def test_missing_provider_config(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        asyncio.run(ai_generator.generate_tests(SOURCE, "openai"))


@pytest.mark.parametrize(
    ("provider", "module_name", "class_name"),
    [
        ("openai", "langchain_openai", "ChatOpenAI"),
        ("groq", "langchain_groq", "ChatGroq"),
    ],
)
def test_provider_integration_mocked(monkeypatch, provider, module_name, class_name):
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setenv(provider.upper() + "_API_KEY", "test-key")
    monkeypatch.setenv(provider.upper() + "_MODEL", "test-model")
    client = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=TESTS)))
    monkeypatch.setattr(module, class_name, lambda **kwargs: client)
    assert asyncio.run(ai_generator.generate_tests(SOURCE, provider)) == TESTS
    client.ainvoke.assert_awaited_once()


def test_api_test_timeout_is_execution_result(monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_tests",
        AsyncMock(
            return_value=GeneratedSuite(
                "import time\ndef test_wait(): time.sleep(30)\n", "mock", "fixture"
            )
        ),
    )
    with TestClient(main.app) as client:
        response = client.post("/generate-tests", json={"code": SOURCE, "timeout_seconds": 1})
    assert response.status_code == 200
    assert response.json()["execution"]["status"] == "timeout"
    assert response.json()["execution"]["timed_out"] is True


def test_parallel_runs_have_separate_modules():
    from concurrent.futures import ThreadPoolExecutor

    tests = "from module_under_test import value\ndef test_value(): assert value == EXPECTED\n"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_tests, f"value = {i}\n", tests.replace("EXPECTED", str(i)))
            for i in [12, 34]
        ]
        assert all(future.result().status == "passed" for future in futures)
