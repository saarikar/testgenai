import hashlib
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import main
from services.ai_generator import GeneratedSuite
from services.repository import RunRepository
from services.repository import TestCase as CaseRecord


def record(run_id=None):
    return dict(
        id=run_id or str(uuid4()),
        source_hash=hashlib.sha256(b"source").hexdigest(),
        provider="reference",
        model="human-fixture",
        prompt_version="v1",
        status="passed",
        generation_seconds=0.5,
        execution_seconds=0.2,
        generated_tests="def test_x(): pass",
        token_usage=None,
        execution={
            "status": "passed",
            "tests": [
                {"name": "test_x", "status": "passed", "duration_seconds": 0.1, "message": None}
            ],
        },
    )


def check_repository(url):
    repository = RunRepository(url)
    repository.migrate()
    repository.migrate()
    value = record()
    repository.save(value)
    with Session(repository.engine) as session:
        assert session.scalar(select(func.count()).select_from(CaseRecord)) >= 1
    repository.close()
    reopened = RunRepository(url)
    saved = reopened.get(value["id"])
    assert saved["tests"][0]["name"] == "test_x"
    assert saved["created_at"].endswith("+00:00")
    assert reopened.list(status="passed")["total"] >= 1
    assert reopened.list(status="timeout")["items"] == []
    assert reopened.metrics()["total_runs"] >= 1
    assert reopened.get("missing") is None
    reopened.close()


def test_sqlite_persistence_and_migrations(tmp_path):
    check_repository("sqlite:///" + (tmp_path / "persistence.db").as_posix())


@pytest.mark.postgres
def test_postgres_persistence_and_migrations():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL supplied by CI; TEST_DATABASE_URL not set locally")
    check_repository(url)


def test_api_history_and_telemetry(monkeypatch, caplog):
    suite = GeneratedSuite(
        "from module_under_test import add\ndef test_add(): assert add(1, 2) == 3\n",
        "mock",
        "fixture",
    )
    monkeypatch.setattr(main, "generate_tests", AsyncMock(return_value=suite))
    caplog.set_level("INFO", logger="testgen.events")
    with TestClient(main.app) as client:
        response = client.post("/generate-tests", json={"code": "def add(a, b): return a + b"})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        assert response.headers["X-Request-ID"] == run_id
        assert response.json()["execution"]["coverage"]["covered_lines"] > 0
        assert client.get("/runs").json()["total"] == 1
        assert client.get("/runs/" + run_id).json()["tests"][0]["status"] == "passed"
        assert client.get("/metrics").json()["total_runs"] == 1
        assert client.get("/runs/missing").status_code == 404
        assert client.get("/runs?limit=0").status_code == 422
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
    assert '"event": "run_completed"' in caplog.text
    assert "def add" not in caplog.text
    with TestClient(main.app) as client:
        assert client.get("/runs/" + run_id).status_code == 200


def test_capacity_rejection_and_health(monkeypatch):
    import asyncio

    mock = AsyncMock()
    monkeypatch.setattr(main, "generate_tests", mock)
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        main.app.state.slots = asyncio.Semaphore(0)
        response = client.post("/generate-tests", json={"code": "x = 1"})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "2"
        assert client.get("/runs").json()["total"] == 0
    mock.assert_not_called()


def test_database_failure_is_explicit(monkeypatch):
    from unittest.mock import Mock

    suite = GeneratedSuite("def test_ok(): assert True\n", "mock", "fixture")
    monkeypatch.setattr(main, "generate_tests", AsyncMock(return_value=suite))
    with TestClient(main.app) as client:
        monkeypatch.setattr(
            main.app.state.repository, "save", Mock(side_effect=RuntimeError("private DSN"))
        )
        response = client.post("/generate-tests", json={"code": "x = 1"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Run history storage unavailable"
    assert "private DSN" not in response.text
