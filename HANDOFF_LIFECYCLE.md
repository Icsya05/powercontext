# Source lifecycle: implementation and verification

Branch: `competition/source-lifecycle`. Frozen task base: `8e9a4bc667f894ba2d7ade133c9b80e01f2b7234`.
Binding spec: `competition/challenges/memory-01-source-lifecycle/instruction.md`.

## Behavior

The Python runtime exposes `lifecycle.for_scope(scope_id)` with immutable Source/Memory/Topic registrations, all/any dependency propagation, strict ordered Source events, generation/audit resolution, and persistent scope isolation. Desired state is committed before native Memory transitions; replay reconciles incomplete writes without creating duplicate successful revisions. Topic eligibility is filtered before result fusion. Historical references remain readable.

Memory registration requires the cited body version still to be the current logical entry body. Readable historical revisions carrying that same body are accepted. A citation to a superseded body is rejected before registration, so its node ID remains usable. Binding does not revise or replace the current body.

The complete event reason is preserved in durable event identity. Native Memory audit reasons use a normalized excerpt bounded to the native 512-code-point limit.

## Actual evidence, 2026-10-26

- Initial missing-module baseline RED, then all 4 official lifecycle tests passed.
- Added native SQLite restart tests for interrupted withdrawal and restoration, exact historical body reads, replay revision stability, strict event validation, failed registration retry, and scope isolation.
- Fresh supported suite: **87 passed, 13 skipped in 35.54s**, including official lifecycle, own regressions, Memory services, and Topic scope processing.
- Independent review of `f7eb7323b3a3b32cbbf7514bca8b836c72333402` identified two Important defects: superseded-body binding persisted before rejection; oversized event reason permanently failed native propagation. Both have public API reproductions that failed before their fixes and passed afterward in the supported suite.
- Ruff changed source/table/Topic/test checks pass. `ty check --python <fixed-venv> src/powercontext/builtin/runtime/source_lifecycle.py` passes.
- Optional server-related `test_topic_memory_application.py` and `test_topic_memory_security.py` cannot collect in the fixed contest environment because `platformdirs` is absent. The wider repository previously had optional dependency collection errors. No whole-repository pass is claimed.
- A final integration suite must run after cherry-picking into the combined branch. No official platform submission, hidden acceptance, or score is claimed.

Verification uses Python3.12 and the fixed competition dependencies on Linux filesystem copies whose bytes are checked against the worktree. Native worker timings on `/mnt/c` are not treated as equivalent to native Linux storage. Do not modify official tests, fixtures, fixed dependencies, or synchronized project sources.

## Review rulings and limits

- Deferred design limit: Topic filtering follows backend candidate collection; very large inactive Topic populations can crowd out active candidates. The specified graph contains four Topics, below the minimum32 candidate pool. No general large-population guarantee is made.
- Multiple graph nodes sharing one native binding have unspecified alias semantics; this implementation is verified for the explicit independent evidence-node graph.
- Concurrent writers, external body edits during binding, and unsupported database backends are beyond the declared single-writer immutable-body SQLite task.
- HTTP/MCP lifecycle parity is not implemented; this challenge requires the Python runtime interface.
- Hidden/platform tests and formal scoring remain unverified.

## Integration

Cherry-pick the implementation and follow-up commits, preserving existing count-trigger composition changes. Touched shared files: runtime/application.py and composition.py, persistence/tables.py and topic_memory.py, plus the new source_lifecycle.py and own tests. The count and evidence work are independent; resolve any context conflicts deliberately.