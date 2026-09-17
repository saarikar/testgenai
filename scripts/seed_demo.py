"""Seed explicitly labeled offline examples; never contacts an LLM."""

import argparse
import hashlib
from uuid import uuid4

from evaluation.run import load_dataset
from services.repository import RunRepository
from services.sandbox import LocalTestRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default="sqlite:///./demo.db")
    args = parser.parse_args()
    repository = RunRepository(args.database_url)
    repository.migrate()
    case = load_dataset()["cases"][0]
    variants = [
        (case["source"], case["reference_tests"], 10),
        (case["mutants"][0]["source"], case["reference_tests"], 10),
        ("", "import time\ndef test_slow(): time.sleep(30)\n", 1),
    ]
    for source, tests, timeout in variants:
        result = LocalTestRunner().run(source, tests, timeout, coverage=True)
        run_id = str(uuid4())
        repository.save(
            dict(
                id=run_id,
                source_hash=hashlib.sha256(source.encode()).hexdigest(),
                provider="reference",
                model="offline-demo",
                prompt_version="reference-v1",
                status=result.status,
                generation_seconds=0,
                generated_tests=tests,
                execution_seconds=result.duration_seconds,
                execution=result.model_dump(),
            )
        )
        print(f"{run_id}: {result.status} (offline fixture)")
    repository.close()


if __name__ == "__main__":
    main()
