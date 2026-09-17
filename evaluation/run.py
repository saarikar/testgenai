"""Run `python -m evaluation.run --mode reference` for an offline baseline."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from services.ai_generator import GeneratedSuite, LangChainTestGenerator
from services.sandbox import LocalTestRunner, validate_python

DATASET = Path(__file__).with_name("dataset.json")


def load_dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def score_suite(case, tests, runner=None):
    runner = runner or LocalTestRunner()
    try:
        validate_python(tests, "test_generated.py")
    except (SyntaxError, ValueError, RecursionError):
        return {
            "syntax_valid": False,
            "collectable": False,
            "eligible": False,
            "false_failure": False,
            "mutants": [],
            "bug_detection_rate": None,
            "correct_execution": None,
        }
    correct = runner.run(case["source"], tests, coverage=True)
    collectable = correct.status in {"passed", "failed"} and not correct.summary.get("error", 0)
    eligible = (
        correct.status == "passed"
        and correct.summary.get("passed", 0) > 0
        and not correct.report_error
    )
    mutants = []
    if eligible:
        for mutant in case["mutants"]:
            result = runner.run(mutant["source"], tests)
            # Infrastructure/collection failures and timeouts are NOT bug detections.
            detected = result.status == "failed" and result.summary.get("failed", 0) > 0
            mutants.append(
                {"id": mutant["id"], "detected": detected, "execution": result.model_dump()}
            )
    rate = sum(m["detected"] for m in mutants) / len(mutants) if mutants else None
    return {
        "syntax_valid": True,
        "collectable": collectable,
        "eligible": eligible,
        "false_failure": correct.status == "failed",
        "mutants": mutants,
        "bug_detection_rate": rate,
        "correct_execution": correct.model_dump(),
    }


def aggregate(rows):
    eligible = [row for row in rows if row.get("eligible")]
    rates = [row["bug_detection_rate"] for row in eligible if row["bug_detection_rate"] is not None]
    mutants = [m for row in eligible for m in row["mutants"]]
    by_case = {}
    for case_id in sorted({r["case_id"] for r in rows}):
        case_rows = [r for r in rows if r["case_id"] == case_id]
        scores = [
            r["bug_detection_rate"] for r in case_rows if r.get("bug_detection_rate") is not None
        ]
        by_case[case_id] = {
            "attempts": len(case_rows),
            "eligible": sum(r.get("eligible", False) for r in case_rows),
            "bug_detection_min": min(scores) if scores else None,
            "bug_detection_max": max(scores) if scores else None,
            "bug_detection_stdev": statistics.pstdev(scores) if len(scores) > 1 else None,
        }
    count = len(rows)
    return {
        "attempts": count,
        "eligible_suites": len(eligible),
        "syntax_valid_rate": sum(r.get("syntax_valid", False) for r in rows) / count
        if count
        else None,
        "collectable_rate": sum(r.get("collectable", False) for r in rows) / count
        if count
        else None,
        "false_failure_count": sum(r.get("false_failure", False) for r in rows),
        "generation_errors": sum("generation_error" in r for r in rows),
        "mutants_detected": sum(m["detected"] for m in mutants),
        "mutants_executed": len(mutants),
        "mean_bug_detection_rate_eligible_only": statistics.mean(rates) if rates else None,
        "mean_generation_seconds": statistics.mean(r["generation_seconds"] for r in rows)
        if rows
        else None,
        "by_case": by_case,
    }


def markdown_report(report):
    summary = report["summary"]
    lines = [
        "# TestGen-AI evaluation",
        "",
        f"Mode: **{report['mode']}**",
        "",
        "Reference mode uses human-written fixtures. These are harness checks, NOT AI performance results.",
        "",
        f"Dataset: {report['dataset_version']} | Repeats: {report['repeats']}",
        "",
        f"Eligible suites: {summary['eligible_suites']}/{summary['attempts']}",
        f"False-failing suites: {summary['false_failure_count']}",
        f"Mutants detected: {summary['mutants_detected']}/{summary['mutants_executed']} executed",
        "",
        "| Example | Repeat | Eligible | Bug detection | Branches covered/total | Generation seconds |",
        "|---|---:|---|---|---|---:|",
    ]
    for row in report["runs"]:
        coverage = (row.get("correct_execution") or {}).get("coverage") or {}
        rate = row.get("bug_detection_rate")
        label = f"{rate:.0%}" if rate is not None else "N/A"
        lines.append(
            f"| {row['case_id']} | {row['repeat']} | {row.get('eligible', False)} | {label} | "
            f"{coverage.get('covered_branches', 'N/A')}/{coverage.get('num_branches', 'N/A')} | "
            f"{row['generation_seconds']:.3f} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "Only suites passing the correct implementation with at least one passing test are eligible. "
        "Invalid/false-failing suites earn no bug-detection credit. Mutant collection errors and timeouts "
        "are recorded but not credited. The score denominator contains only mutants actually executed; "
        "always report eligibility alongside that score.",
        "",
        "Review assertions against specifications before claiming semantic correctness. Coverage is not "
        "correctness. This small, hand-designed dataset does not establish general coding performance. "
        "Repeated reference results are deterministic harness validation, not model consistency.",
        "",
        "See report.json for per-example variance, exact generated suites, hashes, prompt version, "
        "provider/model, token usage when available, runtime versions, logs, and all individual results.",
    ]
    return "\n".join(lines) + "\n"


async def evaluate(args):
    dataset = load_dataset()
    selected = [case for case in dataset["cases"] if not args.case or case["id"] in args.case]
    if not selected or (args.case and set(args.case) - {c["id"] for c in selected}):
        raise ValueError("Unknown or empty case selection")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    generator = LangChainTestGenerator(args.provider)
    for case in selected:
        for repeat in range(1, args.repeats + 1):
            start = time.perf_counter()
            row = {
                "case_id": case["id"],
                "repeat": repeat,
                "source_hash": hashlib.sha256(case["source"].encode()).hexdigest(),
            }
            try:
                if args.mode == "reference":
                    suite = GeneratedSuite(
                        case["reference_tests"],
                        "reference",
                        "human-fixture",
                        prompt_version="reference-v1",
                    )
                else:
                    # Supply the specification as data alongside the correct source.
                    prompt_source = f"# Specification: {case['specification']}\n{case['source']}"
                    suite = await generator.generate(prompt_source)
                row.update(
                    generation_seconds=time.perf_counter() - start,
                    generated_tests=suite.tests,
                    tests_hash=hashlib.sha256(suite.tests.encode()).hexdigest(),
                    provider=suite.provider,
                    model=suite.model,
                    prompt_version=suite.prompt_version,
                    token_usage=suite.token_usage,
                )
            except Exception as exc:
                row.update(
                    generation_seconds=time.perf_counter() - start,
                    generation_error=type(exc).__name__,
                    eligible=False,
                    syntax_valid=False,
                    collectable=False,
                    false_failure=False,
                    mutants=[],
                    bug_detection_rate=None,
                )
            else:
                row.update(await asyncio.to_thread(score_suite, case, suite.tests))
            rows.append(row)
            print(f"{case['id']} repeat={repeat} eligible={row.get('eligible', False)}", flush=True)
            # Checkpoint every attempt so interrupted evaluation does not lose completed work.
            (out / "checkpoint.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
            if args.mode == "live" and args.delay:
                await asyncio.sleep(args.delay)
    report = {
        "mode": args.mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset["version"],
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "repeats": args.repeats,
        "settings": {
            "provider": args.provider,
            "delay_seconds": args.delay,
            "test_timeout_seconds": 10,
            "llm_timeout_seconds": 60,
            "temperature": "provider default",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["pytest", "coverage", "langchain-openai", "langchain-groq"]
            },
        },
        "summary": aggregate(rows),
        "runs": rows,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["reference", "live"], default="reference")
    parser.add_argument("--provider", choices=["openai", "groq"], default="groq")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--case", action="append")
    parser.add_argument("--output", default="artifacts/evaluation")
    parser.add_argument(
        "--env-file", help="Optional local credentials file; never included in reports"
    )
    parser.add_argument("--delay", type=float, default=10, help="Seconds between live requests")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20 or args.delay < 0:
        parser.error("repeats must be 1..20; delay must be nonnegative")
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
    report = asyncio.run(evaluate(args))
    summary = report["summary"]
    # A broken offline oracle or a completely unsuccessful live run must fail CI/CLI.
    if args.mode == "reference":
        return int(
            summary["eligible_suites"] != summary["attempts"]
            or summary["mutants_detected"] != summary["mutants_executed"]
        )
    return int(summary["generation_errors"] > 0 or summary["eligible_suites"] == 0)


if __name__ == "__main__":
    raise SystemExit(main())
