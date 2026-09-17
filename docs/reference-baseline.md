# TestGen-AI evaluation

Mode: **reference**

Reference mode uses human-written fixtures. These are harness checks, NOT AI performance results.

Dataset: 1.0 | Repeats: 3

Eligible suites: 30/30
False-failing suites: 0
Mutants detected: 60/60 executed

| Example | Repeat | Eligible | Bug detection | Branches covered/total | Generation seconds |
|---|---:|---|---|---|---:|
| clamp | 1 | True | 100% | 2/2 | 0.000 |
| clamp | 2 | True | 100% | 2/2 | 0.000 |
| clamp | 3 | True | 100% | 2/2 | 0.000 |
| mean | 1 | True | 100% | 2/2 | 0.000 |
| mean | 2 | True | 100% | 2/2 | 0.000 |
| mean | 3 | True | 100% | 2/2 | 0.000 |
| dedupe | 1 | True | 100% | 0/0 | 0.000 |
| dedupe | 2 | True | 100% | 0/0 | 0.000 |
| dedupe | 3 | True | 100% | 0/0 | 0.000 |
| slug | 1 | True | 100% | 0/0 | 0.000 |
| slug | 2 | True | 100% | 0/0 | 0.000 |
| slug | 3 | True | 100% | 0/0 | 0.000 |
| palindrome | 1 | True | 100% | 0/0 | 0.000 |
| palindrome | 2 | True | 100% | 0/0 | 0.000 |
| palindrome | 3 | True | 100% | 0/0 | 0.000 |
| median | 1 | True | 100% | 4/4 | 0.000 |
| median | 2 | True | 100% | 4/4 | 0.000 |
| median | 3 | True | 100% | 4/4 | 0.000 |
| chunks | 1 | True | 100% | 2/2 | 0.000 |
| chunks | 2 | True | 100% | 2/2 | 0.000 |
| chunks | 3 | True | 100% | 2/2 | 0.000 |
| cart | 1 | True | 100% | 2/2 | 0.000 |
| cart | 2 | True | 100% | 2/2 | 0.000 |
| cart | 3 | True | 100% | 2/2 | 0.000 |
| inventory | 1 | True | 100% | 4/4 | 0.000 |
| inventory | 2 | True | 100% | 4/4 | 0.000 |
| inventory | 3 | True | 100% | 4/4 | 0.000 |
| bank | 1 | True | 100% | 4/4 | 0.000 |
| bank | 2 | True | 100% | 4/4 | 0.000 |
| bank | 3 | True | 100% | 4/4 | 0.000 |

## Interpretation

Only suites passing the correct implementation with at least one passing test are eligible. Invalid/false-failing suites earn no bug-detection credit. Mutant collection errors and timeouts are recorded but not credited. The score denominator contains only mutants actually executed; always report eligibility alongside that score.

Review assertions against specifications before claiming semantic correctness. Coverage is not correctness. This small, hand-designed dataset does not establish general coding performance. Repeated reference results are deterministic harness validation, not model consistency.

See report.json for per-example variance, exact generated suites, hashes, prompt version, provider/model, token usage when available, runtime versions, logs, and all individual results.

## Recorded execution

Created: 2026-09-17T13:57:58.113670+00:00

Python: 3.12.14; platform: Windows. Raw local artifacts: `artifacts/reference/report.json`.

This checked-in summary is a measured offline baseline. It contains no live provider results.
