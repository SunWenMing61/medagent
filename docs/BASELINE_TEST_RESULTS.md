# Baseline and Phase 0 test results

Recorded on 2026-08-05 on Windows, Python 3.12.7 and the repository's installed Node toolchain. These are command results, not estimates.

## Before Phase 0 fixes

| Check | Result |
|---|---|
| `python -m pytest -q` | Could not collect tests: `pytest.ini` was UTF-8 but read with the GBK locale. |
| `PYTHONUTF8=1 python -m pytest -q` | 115 passed, 5 failed, 3 skipped, 11 warnings in 16.64 s. |
| Backend failures | Three rule-classifier fallbacks returned `non_medical`; embedding timeout was converted to `ValueError`; classifier accuracy was 45%. |
| `npm run typecheck` | Failed before checking source because `tsconfig.json` contained non-schema `_comment_*` options and TypeScript 6 rejected deprecated settings. |
| `npm test -- --passWithNoTests` | Passed with no test files found. |
| `npm run build` | Failed for the same TypeScript configuration errors. |
| `python -m alembic history` | Failed with a GBK `UnicodeDecodeError` while reading `alembic.ini`. |
| Docker validation | Not run: Docker is not installed in this environment. |

## After Phase 0 fixes

| Check | Result |
|---|---|
| `python -m pytest -q` | 120 passed, 3 skipped, 11 warnings in 16.13 s. |
| `python -m alembic history` | Passed; no revisions existed at this point. |
| `npm run typecheck` | Passed after the remaining source type error was fixed (verified again in subsequent phase checks). |
| `npm run build` | Verified again in subsequent phase checks. |

The three skipped backend API tests report `Login failed`; they require a running integration stack and are not silently counted as passes. Pydantic v2 deprecation warnings remain tracked technical debt.

## Final refactor verification

Recorded after all parsing, retrieval, ACL, safety, task, deployment, and UI changes:

| Check | Result |
|---|---|
| `python -m pytest -q` | 146 passed, 3 skipped, 11 warnings in 15.72 s. |
| `python -m compileall -q app alembic tests` | Passed. |
| `python -m alembic history` | Passed; one linear chain from `0000_legacy_schema` through `0003_task_outbox`. |
| `npm run build` | Passed; TypeScript validation and Vite production bundle completed (1,464 modules). |
| `npm test -- --run --passWithNoTests` | Passed, but the frontend currently contains no Vitest test files. |
| Compose YAML parse | Passed with PyYAML. Docker image/runtime validation was unavailable because Docker is not installed. |
| `git diff --check` | Passed. |

The production bundle reports a non-blocking warning for a 1.88 MB JavaScript chunk; route-level code splitting remains a performance follow-up.

The executable 20-case rule-classifier evaluation produced accuracy `0.65`, macro precision `0.7875`, macro recall `0.6625`, and macro F1 `0.685119`. Live retrieval Recall@K/MRR/nDCG are intentionally emitted only when a captured provider/database run is supplied; the runner does not fabricate those measurements.

## Scanned PDF incident baseline

The repository sample `4bb2f7502ed44bee81a23fb03bc335cc.pdf` has 265 pages; 255 pages require OCR. The old RQ default job timeout was 180 seconds, while the UI mapped the final backend stage to 95%. A timeout/worker termination therefore left the last observable progress at 95%, with no durable failure transition. The regression fix gives document jobs a 14,400-second timeout, performs page-level OCR with progress heartbeats, uses three total execution attempts with backoff, and installs an RQ terminal-failure callback plus stale-task reconciliation. Execution exceptions are re-raised to RQ instead of being returned as false-success results.

## Reproduction commands

```powershell
& 'C:\Users\swm_0\anaconda3\python.exe' -m pytest -q
& 'C:\Users\swm_0\anaconda3\python.exe' -m alembic history
npm.cmd run typecheck
npm.cmd run build
npm.cmd test -- --run --passWithNoTests
& 'C:\Users\swm_0\anaconda3\python.exe' -m app.evaluation.runner
```
