"""Local runner with timeout/temporary files; NOT a security boundary.

Only run trusted code. Environment filtering does not stop code from accessing
the host filesystem, network, or other processes. Use a separately isolated
execution service for adversarial or public submissions.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from defusedxml import ElementTree
from pydantic import BaseModel, Field

LOG_LIMIT = 64 * 1024
REPORT_LIMIT = 2 * 1024 * 1024


class TestCaseResult(BaseModel):
    name: str
    classname: str
    status: Literal["passed", "failed", "error", "skipped"]
    duration_seconds: float
    message: str | None = None


class ExecutionResult(BaseModel):
    status: Literal["passed", "failed", "error", "timeout", "no_tests"]
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    logs_truncated: bool
    summary: dict[str, int] = Field(default_factory=dict)
    tests: list[TestCaseResult] = Field(default_factory=list)
    report_error: str | None = None
    coverage: dict | None = None


def validate_python(source: str, filename: str) -> None:
    # Compilation catches errors that ast.parse alone can miss, e.g. top-level return.
    compile(source, filename, "exec", dont_inherit=True)


def _read_stream(stream, target: bytearray, truncated: list[bool]) -> None:
    try:
        while chunk := stream.read(8192):
            available = LOG_LIMIT - len(target)
            target.extend(chunk[:available])
            if len(chunk) > available:
                truncated[0] = True
    finally:
        stream.close()


def _stop_process_tree(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        # Windows fallback. Docker/Linux provides process-group cleanup even after
        # the immediate parent exits; Windows cannot guarantee that behavior.
        try:
            system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            subprocess.run(
                [
                    str(system_root / "System32" / "taskkill.exe"),
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()


def _parse_report(path: Path) -> tuple[list[TestCaseResult], dict[str, int]]:
    with path.open("rb") as report:
        data = report.read(REPORT_LIMIT + 1)
    if len(data) > REPORT_LIMIT:
        raise ValueError("Report too large")
    root = ElementTree.fromstring(data)
    cases = []
    summary = dict(total=0, passed=0, failed=0, error=0, skipped=0)
    for case in root.iter("testcase"):
        status, message = "passed", None
        for tag, outcome in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
            detail = case.find(tag)
            if detail is not None:
                status = outcome
                message = (detail.get("message") or detail.text or "")[:4000]
                break
        cases.append(
            TestCaseResult(
                name=case.get("name", ""),
                classname=case.get("classname", ""),
                status=status,
                duration_seconds=float(case.get("time", "0")),
                message=message,
            )
        )
        summary[status] += 1
        summary["total"] += 1
    return cases, summary


def run_tests(
    code: str, test_code: str, timeout_seconds: int = 10, *, measure_coverage: bool = False
) -> ExecutionResult:
    if not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between 1 and 60")
    validate_python(code, "module_under_test.py")
    validate_python(test_code, "test_generated.py")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="testgen-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        (root / "module_under_test.py").write_text(code, encoding="utf-8")
        (root / "test_generated.py").write_text(test_code, encoding="utf-8")
        (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        env = {
            key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ
        }
        env.update(
            {
                "PATH": os.defpath,
                "HOME": directory,
                "USERPROFILE": directory,
                "TMPDIR": directory,
                "TMP": directory,
                "TEMP": directory,
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-s",
            "--tb=short",
            "--color=no",
            "-p",
            "no:cacheprovider",
            "-c",
            "pytest.ini",
            "--confcutdir",
            directory,
            "--junitxml=results.xml",
            "test_generated.py",
        ]
        if measure_coverage:
            command = [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--branch",
                "--source=module_under_test",
                "-m",
                "pytest",
                *command[3:],
            ]
        process = subprocess.Popen(
            command,
            cwd=directory,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=(os.name == "posix"),
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        stdout, stderr = bytearray(), bytearray()
        truncated = [False]
        readers = [
            threading.Thread(target=_read_stream, args=(stream, output, truncated), daemon=True)
            for stream, output in ((process.stdout, stdout), (process.stderr, stderr))
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            _stop_process_tree(process)
            process.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=1)
        status = (
            "timeout"
            if timed_out
            else {0: "passed", 1: "failed", 5: "no_tests"}.get(process.returncode, "error")
        )
        cases, summary, report_error = [], {}, None
        try:
            cases, summary = _parse_report(root / "results.xml")
        except Exception:
            report_error = "Pytest report unavailable or invalid; see execution logs"
            if status == "passed":
                status = "error"
        coverage_summary = None
        if measure_coverage and not timed_out and (root / ".coverage").exists():
            try:
                report = subprocess.run(
                    [sys.executable, "-m", "coverage", "json", "-o", "coverage.json"],
                    cwd=directory,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                if report.returncode == 0:
                    with (root / "coverage.json").open("rb") as handle:
                        raw = handle.read(REPORT_LIMIT + 1)
                    if len(raw) <= REPORT_LIMIT:
                        coverage_summary = json.loads(raw)["totals"]
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                pass
        return ExecutionResult(
            status=status,
            exit_code=process.returncode,
            timed_out=timed_out,
            duration_seconds=round(time.monotonic() - started, 3),
            stdout=bytes(stdout).decode("utf-8", errors="replace"),
            stderr=bytes(stderr).decode("utf-8", errors="replace"),
            logs_truncated=truncated[0],
            summary=summary,
            tests=cases,
            report_error=report_error,
            coverage=coverage_summary,
        )


class LocalTestRunner:
    """Adapter shared by API and evaluation orchestration."""

    def run(
        self, code: str, tests: str, timeout: int = 10, *, coverage: bool = False
    ) -> ExecutionResult:
        return run_tests(code, tests, timeout, measure_coverage=coverage)
