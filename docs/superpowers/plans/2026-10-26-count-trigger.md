# Source Count Trigger Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically accept Memory and Topic Memory invocations after enough persisted Source identities accumulate.

**Architecture:** Add strict optional runtime thresholds and a bounded count admission channel to the existing supervisor. Read journal heads and each family's successful cursor; persist accepted requests before enqueueing and reuse existing workers, retry, and recovery behavior.

**Tech Stack:** Python 3.11+, Pydantic, SQLAlchemy, SQLite, pytest.

**Spec:** `competition/challenges/processing-01-count-trigger/instruction.md`

## Global Constraints

- Threshold defaults are `None`; nonempty values are strictly positive integers.
- Source journal identities include lineage Sources and exclude duplicate capture/receipt upgrades.
- Count and time are OR gates; explicit flush bypasses count admission.
- Memory consumes one window then rechecks; accepted Topic Memory waves keep their existing continuation.
- Preserve official competition tests, dependencies, and all unrelated feature behavior.

## Review Focus

- A full page of scopes below threshold must not hide an eligible later scope.
- Successful partial Memory processing must use the advanced cursor, even if dirty counters remain high.
- Accepted retries must survive restart and later threshold configuration changes.
- Lineage-only writes must be discovered without relying on capture notifications.
- Count admission must not reset the time schedule or duplicate outstanding requests.

### Task 1: Count configuration and bounded admission

**Files:** Modify `src/powercontext/builtin/runtime/{config,processing_discovery,artifact_processing,composition}.py`; add `tests/builtin/runtime/test_source_count_trigger.py`.

- [x] Run the official public suite before implementation. Expected: missing configuration assertions (17 failures).
- [x] Add boundary tests for per-family successful cursors and paged admission; run and observe missing implementation failures.
- [x] Add strict optional fields; wire a metadata-only scope filter into bounded supervisor count discovery without changing time scans or accepted-worker behavior.
- [x] Run the new boundary tests and full official count-trigger suite. Expected: all pass.
- [x] Run existing processing/configuration/persistence regressions, the repository test command, Ruff, and ty. Record actual limits.
- [x] Commit code, tests, and this plan. Parent performs independent whole-branch review before integration.

## Execution ledger

- Baseline: official suite failed 17/17 due to missing public count configuration.
- Ruling: The parent explicitly delegated this bounded task and reserved independent review/integration; execute inline without additional subagents or confirmation, and return a verified commit.
- Boundary RED: all four added tests failed with missing persisted Source count admission; GREEN: 4 passed in 15.08s.
- Regressions: 95 passed in 140.29s across count, scheduler, scan rollback, composition, Topic Memory processing, and intent persistence tests.
- Full repository pytest was attempted: 5 skipped and 110 collection errors because the fixed competition environment lacks optional/development dependencies (including platformdirs, typer, FastAPI, FastMCP, markdown-it, and LangChain adapters). The wider initial regression selection also hit missing platformdirs in artifact-processing-config and family-processing tests. No environment dependencies changed.
- Ruff: changed files pass when excluding DTZ901; the raw run flags only two unchanged datetime.max lines in artifact_processing.py, confirmed in the base commit. Formatting passes for all five Python files.
- ty: changed files pass with deprecated diagnostics excluded; the raw run reports only three unchanged AsyncIterator decorators in composition.py, confirmed in the base commit.
- Ruling: Validate native workers on a byte-identical Linux temporary mirror to avoid Windows-mounted filesystem import overhead. All 511 src/competition files were SHA256-compared with the worktree before running unchanged official tests using the same fixed virtual environment. The Windows-mounted run and isolated repeat timed out on the Topic Memory wave; the identical Linux mirror passed that test. No official tests, timeouts, or product behavior were altered.
- Official verification: unchanged `make -C competition test-count-trigger` on the byte-identical Linux mirror passed all 17 tests in 257.23s. The Windows-mounted run completed with 16 passed and one Topic wave timeout in 701.21s; the isolated Windows-mounted repeat also timed out. Filesystem overhead is the supported explanation, not a change to the acceptance contract.
- Handoff: implementation is verified within the recorded limits; independent whole-branch review and integration remain with the parent. Preserve the branch and `HANDOFF_COUNT_TRIGGER.md` for portable continuation; no push or merge was performed here.
