# Source Lifecycle Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans; parent coordinates whole-branch review.

**Goal:** Persist scope-local evidence DAGs and propagate Source eligibility to native Memory and Topic retrieval.

**Architecture:** Store immutable bindings and the accepted Source event in the runtime database. Persist desired graph state before native Memory writes; retry reconciles desired state through idempotent native transitions. Filter Topic channels before fusion without rewriting immutable artifacts.

**Tech Stack:** Python 3.11+, Pydantic, SQLAlchemy, existing SQLite runtime.

**Spec:** competition/challenges/memory-01-source-lifecycle/instruction.md

## Global Constraints

- Single writer per scope; graph bindings are immutable after registration.
- No new dependencies, external models, network, or modifications to official tests.
- Preserve exact original references and body versions; successful replay adds no Memory revision.

## Review Focus

- Strict event types reject booleans as integers and extra fields.
- Invalid references and dependency conflicts must not leave registrations.
- Failed native writes and process restart preserve retryable desired state.
- Independent scopes and surviving any-support facts remain available.
- Topic eligibility must apply before fused result limits.

### Task 1: Durable graph and runtime integration

- [x] Read binding spec and public tests; observe missing-module baseline RED.
- [x] Add native schema table and scoped lifecycle application; validate original references before registration.
- [x] Persist accepted events and computed states, reconcile native Memory transitions, and filter Topic channels.
- [x] Run all official lifecycle tests to GREEN (4 passed in 34.38s).

### Task 2: Retry and strict validation regressions

- [ ] Add focused public-API tests for strict events, binding identity/isolation, and interrupted native writes across restart.
- [ ] Verify tests fail for the missing behavior before final fixes.
- [ ] Run focused Memory/Topic regressions, broader suite, Ruff, and type checks; report environmental limits.
- [ ] Commit code, tests, and this plan; parent integrates and reviews.

## Execution ledger

- Baseline official test collection fails because source_lifecycle module does not exist.
- Ruling: retain accepted events and desired graph state before projection writes so same-event retry repairs partial native commits. Native state transitions themselves are idempotent.
- Work stopped at the user's quota preservation request. No Task 2 tests or broad verification; see `HANDOFF_LIFECYCLE.md`. Ruff still has 19 TRY003 findings.

- Resumed 2026-10-26: 11 native/validation regressions passed; independent review found two Important defects. Added reproductions (both RED), fixed pre-insert body compatibility and native reason adaptation; supported suite GREEN 87 passed/13 skipped, Ruff and new-module ty clean. Final integration remains separate. Historical superseded bodies are rejected before binding; complete event reasons stay durable.

- Final combined code15edc33b passed95public +247focused/13skip; independent lifecycle findings fixed via RED/GREEN and complete suite.
- Ruling: four-Topic scale is supported; candidate starvation at larger inactive populations remains a documented limit. Alias semantics and concurrent/external edits remain outside the declared graph contract. HTTP lifecycle parity is not required by this Python interface task.
