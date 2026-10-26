# Source lifecycle challenge — work in progress

This branch is deliberately incomplete and unreviewed. Work stopped at the user's quota preservation request on 2026-10-26. Do not claim challenge acceptance or platform points from it.

## Branch and starting point

- Branch: `competition/source-lifecycle`.
- Base: `8e9a4bc667f894ba2d7ade133c9b80e01f2b7234`.
- Own worktree: `output/repositories/powercontext-lifecycle` beside original `powercontext`; main competition checkout was not modified.
- Binding specification: `competition/challenges/memory-01-source-lifecycle/instruction.md`; read the entire file and public `acceptance/checks.py` / `test_lifecycle.py`.
- Concise plan: `docs/superpowers/plans/2026-10-26-source-lifecycle.md` (force-added because repository ignores this directory).

## Implemented, pending verification

- New `src/powercontext/builtin/runtime/source_lifecycle.py` exports `SourceLifecycleError(ValueError)` and strict/frozen Pydantic `SourceLifecycleEvent` with extra fields forbidden, nonblank string node/reason, positive strict integer revision/sequence, and strict boolean availability.
- Runtime provides `runtime.lifecycle.for_scope(scope_id)` with asynchronous `register_source`, `register_memory`, `register_topic`, `apply`, and `resolve`.
- One persistent `pc_source_lifecycle_nodes` table uses the same relational database as the runtime. Primary key `(scope_id,node_id)`; fields `kind`, JSON text `binding`, boolean `available`, nullable JSON `last_event`. Binding stores original typed reference, parents, all/any policy, and lifecycle revision.
- Registered bindings are immutable, identical registration retries reconcile desired state, references are read before first registration, parents must already exist and be unique/nonempty, and source event version and monotonic sequence/replay identity are checked.
- Each accepted event computes the entire explicit DAG, persists desired state before projection writes, then calls native Memory `forget`/`reactivate` against original entry versions. Successful replay uses native transition idempotency. This approach is intended to repair partial native commits on same-event retry, including after restart.
- Topic search filters unavailable registered Topic artifact IDs from all four search channels before fusion. Immutable artifacts/publications remain readable for audit. Topic filtering currently sits in shared `TopicMemoryRepository.search`, so native runtime/context search follows it.

## Known unfinished work / risks

1. No new product regression tests were added yet. Add meaningful tests for partial native Memory write failure, same-event retry after restart, successful replay revision stability, strict event type matrix, missing refs, identical/conflicting registration, and cross-scope IDs.
2. Ruff check currently reports **19 TRY003 errors** in `source_lifecycle.py`: exception messages need project-style ownership within `SourceLifecycleError` or deliberate local suppression. Ruff import sorting was applied and formatter ran successfully. Do not describe lint as passing.
3. Type checker has not run. Several internal helpers are intentionally still unannotated WIP (`_register_derived`, `_load`, `_reconcile`, `resolve`); annotate/type-check them.
4. Topic channel filtering happens after backend channel candidate limits (but before final fusion). Within the challenge's four Topics and channel minimum 32 this should avoid starvation; generally many unavailable Topics could crowd out survivors. Consider database eligibility predicates before candidate selection if promising broader correctness. Browse eligibility is not filtered; the explicit task tests search/context, but assess expected public browse behavior.
5. Source reference validation currently uses `_records().get_source`, supporting captured built-in content sources. Evaluate other Source types only if within actual challenge/public contract; do not silently promise all adapters.
6. Only latest accepted event is stored per Source, sufficient for monotonic replay contract but not a full event history. Original refs and immutable native history remain.
7. Registration reconciliation scans all registered Memory nodes and rereads heads individually. Expected graph is 16–20 nodes, but no performance measurement was made.
8. No broad project suite, focused native regressions, independent review, or hidden/platform verification has completed. Parent was planning final integrated review.
9. `node_id` column is VARCHAR(255) on MySQL while input validation only checks nonblank; task is single-writer SQLite, where length is not enforced. If broader backend behavior is desired, define the contract deliberately.

## Integration overlap

- `src/powercontext/builtin/runtime/composition.py`: exactly one new constructor keyword `lifecycle_database=contexts.database` after `provider=contexts`; count-trigger worker agent also edits composition, so preserve both.
- `src/powercontext/builtin/runtime/application.py`: imports `AsyncDatabase` and `SourceLifecycleApplication`; optional constructor `lifecycle_database` immediately after capabilities; `self.lifecycle` immediately after `self.memory`. Parent's other runtime/evidence work may touch this large file.
- `src/powercontext/builtin/persistence/tables.py`: new table before `BUILTIN_TABLES` and appended table in tuple. Hybrid backend work might touch other persistence files.
- `src/powercontext/builtin/persistence/topic_memory.py`: imports JSON and lifecycle table, filters channels immediately after `self.index.search`. Resolve merge carefully if retrieval work changes the same path.
- New source module and this handoff/plan have no expected overlap.

## Actual verification and reproducible environment

Execution used Windows Git and PowerShell for files, WSL distro `Ubuntu-24.04`, user `ocean`, Python 3.12.3, fixed venv `/home/ocean/.venvs/powercontext-2026`. `competition/.venv` is a local untracked/ignored symlink to it. Do not commit the symlink, modify that shared venv, install dependencies, restart WSL, or touch the already running seekdb databases (original 2881 / new 2883).

1. Initial pytest invocation hit duplicate pytest-asyncio plugin registration due to autoload plus `competition/pytest.ini` explicitly loading it. Correct by setting `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
2. Corrected baseline, before implementation: official lifecycle collection failed with `ModuleNotFoundError: powercontext.builtin.runtime.source_lifecycle` (one collection error, no tests run), establishing RED.
3. Ran Ruff `check --fix` on all five changed source files: 20 findings, 1 import-order autofix, 19 remaining TRY003; formatter changed two files, left three unchanged.
4. Post-implementation official lifecycle tests: **4 passed in 34.38s**, exit code 0, using the command below. No broader verification has been run. Passing these four public tests does not establish retry/failure behavior or full hidden acceptance.

From worktree root in WSL:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/src:$PWD/competition" \
  competition/.venv/bin/python -m pytest \
  competition/challenges/memory-01-source-lifecycle/acceptance -q -x
```

Read repository `AGENTS.md` and `REVIEW.md` before proceeding. Do not modify official challenge tests, dependencies, data, synced project sources, or status documents. No network/model calls or hardcoded hidden assets are allowed.
