# Native hybrid candidate search implementation plan

> **For agentic workers:** Execute inline with superpowers:executing-plans and TDD. The parent agent performs the final fresh review and integration.

**Goal:** Obtain both Memory candidate channels with one native seekdb statement.

**Architecture:** The native vector index advertises hybrid support and returns a UNION ALL of separately bounded native FTS and ANN branches. CompositeMemoryIndex delegates hybrid requests to a hybrid-capable provider; existing independent indexes and single-channel requests retain their paths. Candidate rows use the already validated requested current head, including unchanged projections from older revisions.

**Tech Stack:** Python 3.11+, SQLAlchemy, pylibseekdb==1.3.0.post4.

**Spec:** competition/challenges/retrieval-02-hybrid-search/instruction.md

## Global constraints

- Reuse the product AsyncConnection and existing schema; no new service or dependencies.
- Exactly one hybrid candidate statement using TEXT RETRIEVAL SCAN and VECTOR INDEX.
- Apply scope, artifact, tags, and per-channel candidate limits inside the database.
- Preserve head validation, state changes, fusion, exact text, and public single-channel behavior.
- Do not modify competition assets, runtime application/configuration, or worker scheduling.

## Review focus

- Unchanged old-revision projections retain current references (public acceptance).
- Multiple scopes and artifacts cannot leak candidates (focused regression).
- Both any/all tag filtering happen before each channel's candidate limit (focused regression).
- Equal vector distances have a stable explicit result order (focused regression).
- Historical heads and version changes keep existing rejection/state behavior (public acceptance).

### Task 1: Native fused candidate provider

**Files:** Modify src/powercontext/builtin/persistence/memory_index.py and src/powercontext/builtin/persistence/oceanbase/memory_index.py; add tests/builtin/persistence/test_seekdb_hybrid.py.

**Interfaces:** Consume MemorySearchRequest; return MemorySearchChannels with independently ordered fts/vector candidates and requested current refs.

- [x] Run the unmodified public hybrid acceptance to establish RED (zero combined statements).
- [x] Add a real backend regression checking bounded filtered channel candidates and equal-distance repeated identity order; confirm RED.
- [x] Implement hybrid delegation and the native UNION ALL query, retaining vector completeness checks and existing single-channel SQL.
- [x] Run public hybrid acceptance and focused regressions, inspect actual EXPLAIN of captured SQL for both native operators.
- [x] Run affected persistence/Memory tests, the project test suite, Ruff and type checking; report unavailable optional environments or existing failures explicitly.
- [x] Commit implementation, tests, and plan on competition/hybrid-single-sql; no merge/push.

## Verification and rulings

- Public RED: one failure, zero combined statements. Final public GREEN: 1 passed in 46.43s.
- Small-limit tagged ANN RED: vector returned 0 of 2. Scalar uncorrelated JSON tag membership moves the filter into the native VECTOR INDEX pre-filter; any/all/absent tag cases pass.
- Final affected suite: 94 passed, 15 skipped in 65.51s; Ruff check/format and targeted ty passed.
- Full project suite attempted: 5 skipped, 110 collection errors due to absent optional development dependencies (see HANDOFF_HYBRID.md), not claimed green.
- Ruling: materialize eligible exact artifact/entry tag pairs once in the database because correlated COUNT and tuple IN subplans filter after native ANN top-k. Cost: high-cardinality tag set materialization is unbenchmarked.
- User steering: stop at the quota checkpoint; parent owns fresh review and integration. No subagents, merge, push or further feature work.
