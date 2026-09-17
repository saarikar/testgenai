# Evaluation methodology

The benchmark is versioned in `evaluation/dataset.json`. It contains ten specifications, ten correct implementations, ten human-written reference suites, and twenty deliberate bug variants. Inputs follow each specification's stated domain; unspecified behavior is not part of the oracle.

## Protocol

1. Validate reference suites against correct implementations and mutants.
2. For live evaluation, supply only the specification and correct source to the model. Never supply reference tests or mutants.
3. Generate three independent suites per example. Preserve the exact suite, source/test hashes, provider, model, prompt version, environment versions, timings, and usage metadata.
4. Run each suite on correct code with branch coverage enabled.
5. A suite is eligible only if the correct implementation passes, the report is valid, and at least one test passes. All-skipped and empty suites are not eligible.
6. Execute that exact suite against every mutant. Do not regenerate or modify it per mutant.
7. Count a detection only for a failed pytest execution with actual failed tests. Collection errors, timeouts, and infrastructure failures are recorded without credit.
8. Record per-example minimum, maximum, and population standard deviation of eligible bug-detection scores. Missing or failed generations stay visible in the denominator of attempt-level metrics.

## Metrics and interpretation

- Syntax-valid rate: compilable suites / all generation attempts.
- Collectable rate: completed pass/fail executions without collection errors / all attempts. A timed-out run is conservatively not counted as collectable.
- Eligibility: passing correct-code suites with at least one passing test / attempts.
- False failure: a generated suite returns failing tests on the correct implementation. Collection and provider errors are distinct failures, not counted as false assertions.
- Bug-detection score: detected variants / executed variants, for eligible suites only. Always present this with eligibility; a high conditional score with low eligibility is misleading.
- Line coverage: covered lines / executable statements.
- Branch coverage: covered branch destinations / total branch destinations; no branches means N/A, not evidence of full branch testing.
- Generation and execution durations are separate. Usage tokens are provider-reported or null, never guessed.

Manual review remains necessary: compare expected values and exception assertions to the specification; look for implementation duplication, trivial assertions, skip abuse, unnecessary mocks, and assumptions about unspecified inputs. Record semantic-review findings in a separate report, rather than implying automatic pass results establish correctness.

## Reproducibility and limitations

`report.json` stores raw results, suite text, hashes, package versions, settings, and per-case dispersion. `checkpoint.json` preserves completed attempts if a run is interrupted; automatic resume is not implemented. Use a new output folder per experiment. Errors are not silently retried or dropped.

This is a small curated benchmark, not a statistically representative evaluation of all Python. The mutants were designed by the project author, and equivalent mutants are possible in larger future datasets. Reference mode validates the harness and should not be described as LLM performance. Model service changes and default sampling can affect repeated live runs even with the same model ID. The project has not yet measured a full live model benchmark.
