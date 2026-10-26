# HTTP Memory reranker implementation plan

> **For agentic workers:** Use superpowers:executing-plans.

**Goal:** Score bounded batches over HTTP and select globally ordered original Memory identities.
**Architecture:** Add an adapter for the existing MemoryReranker protocol; retain the caller-owned AsyncClient and all existing Memory search behavior.
**Tech Stack:** Python 3.12, httpx, standard JSON and math, existing inference usage.
**Spec:** `competition/challenges/retrieval-01-reranking/instruction.md`

## Global Constraints

No added runtime dependencies. Each original one-based rank is sent exactly once. Strict exact response keys, finite numeric scores, exact batch coverage; preserve httpx transport/status errors. Sort by descending score then ascending global rank. Report actual request count.

## Review Focus

- Boolean/string/fractional ranks must not be treated as integer identities.
- Boolean or string scores are not JSON numeric scores.
- Cross-batch ranks must be rejected even when globally valid.
- Invalid bounds must fail before any HTTP requests.
- HTTP errors and malformed JSON retain their documented exception types.

### Task 1: Bounded HTTP adapter

**Files:** Create `src/powercontext/builtin/artifacts/memory/http_reranker.py`, `tests/test_http_reranker.py`.
**Interfaces:** Produce `HTTPMemoryReranker(endpoint, *, client, batch_size=32, policy_id='http-cross-encoder-v1')` and async `rerank(query, candidates, limit) -> MemoryRerankDecision`.

- [x] Run official public test before implementation; expect missing adapter module (observed).
- [x] Add strict response, invalid bounds, error and global ordering boundary tests.
- [x] Implement bounded sequential POSTs, exact response validation, one global sort and actual request usage.
- [x] Run public and focused tests, existing reranking tests and new-module lint/type checks; expect all pass.
- [x] Commit and prepare the actual repository/SHA for submission.
