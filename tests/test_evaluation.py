from types import SimpleNamespace

import pytest

from evaluation.run import aggregate, load_dataset, score_suite
from services.sandbox import ExecutionResult


@pytest.mark.parametrize("case", load_dataset()["cases"], ids=lambda case: case["id"])
def test_reference_oracles_detect_mutants(case):
    score = score_suite(case, case["reference_tests"])
    assert score["eligible"]
    assert score["bug_detection_rate"] == 1
    assert score["correct_execution"]["coverage"] is not None


def result(status, passed=0, failed=0):
    return ExecutionResult(
        status=status,
        exit_code=0 if status == "passed" else 1,
        timed_out=status == "timeout",
        duration_seconds=0.1,
        stdout="",
        stderr="",
        logs_truncated=False,
        summary={"passed": passed, "failed": failed},
    )


def test_false_failing_suite_cannot_earn_bug_credit():
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return result("failed", failed=1)

    score = score_suite(
        load_dataset()["cases"][0], "def test_x(): assert False", SimpleNamespace(run=run)
    )
    assert score["false_failure"]
    assert not score["eligible"]
    assert score["mutants"] == []
    assert len(calls) == 1


def test_mutant_timeouts_and_errors_are_not_kills():
    results = iter([result("passed", passed=1), result("timeout"), result("error")])
    score = score_suite(
        load_dataset()["cases"][0],
        "def test_x(): pass",
        SimpleNamespace(run=lambda *a, **k: next(results)),
    )
    assert score["eligible"]
    assert score["bug_detection_rate"] == 0


def test_empty_and_invalid_suites():
    assert not score_suite(load_dataset()["cases"][0], "def broken(:")["syntax_valid"]
    score = score_suite(load_dataset()["cases"][0], "x = 1")
    assert not score["eligible"]
    assert score["bug_detection_rate"] is None


def test_aggregate_handles_failed_generations():
    rows = [
        {
            "case_id": "x",
            "generation_seconds": 1.0,
            "generation_error": "TimeoutError",
            "eligible": False,
        }
    ]
    summary = aggregate(rows)
    assert summary["generation_errors"] == 1
    assert summary["mean_bug_detection_rate_eligible_only"] is None


def test_live_evaluation_records_errors_and_keeps_other_attempts(monkeypatch, tmp_path):
    import asyncio
    import json
    from argparse import Namespace
    from unittest.mock import AsyncMock

    import evaluation.run as module
    from services.ai_generator import GeneratedSuite

    generated = GeneratedSuite("def test_x(): pass\n", "groq", "test-model", {"total_tokens": 12})
    mock = AsyncMock(side_effect=[TimeoutError(), generated])
    monkeypatch.setattr(module.LangChainTestGenerator, "generate", mock)
    monkeypatch.setattr(
        module,
        "score_suite",
        lambda *a: {
            "syntax_valid": True,
            "collectable": True,
            "eligible": True,
            "false_failure": False,
            "mutants": [],
            "bug_detection_rate": None,
            "correct_execution": None,
        },
    )
    report = asyncio.run(
        module.evaluate(
            Namespace(
                mode="live",
                provider="groq",
                repeats=2,
                case=["clamp"],
                output=str(tmp_path),
                delay=0,
            )
        )
    )
    assert report["summary"]["attempts"] == 2
    assert report["summary"]["generation_errors"] == 1
    assert report["runs"][1]["token_usage"]["total_tokens"] == 12
    assert len(json.loads((tmp_path / "checkpoint.json").read_text())) == 2
    assert (tmp_path / "report.md").exists()
    assert report["dataset_sha256"]
    prompts = [call.args[0] for call in mock.call_args_list]
    assert prompts[0] == prompts[1]
    assert "test_clamp" not in prompts[0]  # Never leak the reference oracle to the model.


def test_reference_evaluation_writes_labeled_report(tmp_path):
    import asyncio
    from argparse import Namespace

    from evaluation.run import evaluate

    report = asyncio.run(
        evaluate(
            Namespace(
                mode="reference",
                provider="groq",
                repeats=1,
                case=["clamp"],
                output=str(tmp_path),
                delay=0,
            )
        )
    )
    assert report["runs"][0]["provider"] == "reference"
    assert report["runs"][0]["prompt_version"] == "reference-v1"
    assert report["summary"]["mutants_detected"] == 2
    assert "NOT AI performance results" in (tmp_path / "report.md").read_text()
