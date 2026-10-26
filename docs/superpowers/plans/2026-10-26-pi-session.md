# Pi session evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans.

**Goal:** Capture every visible event on a selected Pi v3 branch, retain complete original records, and resume safely after branch changes or interrupted ingestion.
**Architecture:** Fully validate each JSONL snapshot and its parent graph before selecting the ancestor path. Capture immutable event identities through native Source Definitions, and keep imported-record fingerprints in ConnectorLifecycle's durable per-binding checkpoint.
**Tech Stack:** Python 3.12, JSON, SHA-256, Pydantic, native registry/ingestion/connector APIs.
**Spec:** `competition/challenges/source-02-pi-history/instruction.md`. Native format reference: earendil-works/pi commit `6fb2e7815167e6b19006fc526d1a5d0f5f998787`, `packages/coding-agent/docs/session-format.md`.

## Global Constraints

- No additional dependency, online model, network call, module-level checkpoint or execution of archive commands.
- Strict UTF-8/BOM JSONL, session version 3, unique node IDs and already-seen/null parents; validate every branch before returning results.
- Preserve the full original record and visible content, including large tool outputs. Ignore thinking/image and control text, retain graph connections.
- Stable bounded identity depends only on session/event IDs; captured Source, `pi-event/1`, exact standard projection and native persistence.
- Connector `pi-session-history/1` commits progress only through ConnectorLifecycle after successful durable submission. Validate saved fingerprints even for previously imported events off the selected branch.
- Official competition assets remain unchanged.

## Review Focus

- An invalid unselected branch must still fail the complete snapshot atomically.
- Identical event IDs in different sessions must not collide, including long/delimiter-containing IDs.
- Header-only archives and explicit missing leaves must differ.
- Empty text blocks, tool-only messages, mixed image/thinking content and full large outputs preserve visibility and order.
- Restart, failed partial submission and same-session historical rewrites must not lose progress or duplicate evidence.

## Decisions

Native `parentId: null` denotes a root; a missing parent field is invalid. Explicit `display=false` custom messages are hidden in the native format and do not produce visible evidence; absent display remains visible for the competition's minimal records. All original records still participate in graph validation.

### Task 1: Parse and capture complete branch evidence

**Files:** Create `src/powercontext/sources/pi_session.py`, `tests/test_pi_session.py`.
**Interfaces:** PiSessionInput, PiEventInput, parse_pi_session, PI_EVENT_SOURCE_DEFINITION.

- [ ] Observe official tests fail for the absent module (observed).
- [ ] Add independent malformed-header/graph, namespace, visibility and large-output tests; observe failure before implementation.
- [ ] Implement snapshot validation, original ancestor traversal, rendering, captured resolve/read and exact projection.
- [ ] Run focused tests plus official `test_pi.py`; verify every event's real persisted citation.
- [ ] Commit verified parser/source implementation.

### Task 2: Durable incremental connector

**Files:** Extend `src/powercontext/sources/pi_session.py`, `tests/test_pi_session.py`.
**Interfaces:** PiSessionConnector(path, leaf_id=None), native ConnectorRunCompletion and opaque JSON checkpoint.

- [ ] Run incremental official test before adding the connector; expect missing PiSessionConnector.
- [ ] Add off-branch mutation and partial-failure/retry scenarios with durable SQLite state.
- [ ] Validate saved session fingerprints before submitting any new selected events, then propose the complete checkpoint for native lifecycle commit.
- [ ] Run all official Pi tests, focused tests and source/connector regressions; lint/type check changed modules and commit.
- [ ] Perform independent branch review, address demonstrated bugs with RED→GREEN checks, push and update submission information.
