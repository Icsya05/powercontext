# Embedding coalescing implementation plan

> **For agentic workers:** Use superpowers:executing-plans.

**Goal:** Share bounded in-flight embedding work, cache successful vectors and preserve each caller's ordered results and usage.
**Architecture:** One event-loop-owned wrapper maps text to shared futures, drains queued misses into bounded independent batches, and retains successful vectors in an LRU. Shield shared work from caller cancellation.
**Tech Stack:** Python 3.12 asyncio, OrderedDict, existing EmbeddingModel/EmbeddingResult/InferenceUsage.
**Spec:** `competition/challenges/memory-02-embedding-batches/instruction.md`

## Global Constraints

No new dependencies or online models. Preserve repeated positions and original order. Charge each distinct awaited provider batch once per caller. Cache only successful results, zero capacity disables caching while retaining in-flight sharing. Expose the provider profile. Native six-scope 24-text workload must make exactly four batches of at most six texts.

## Review Focus

- A late caller must share an already executing batch even with caching disabled.
- One failed batch must not poison an independent batch.
- Cancelling every waiter must not leave unhandled future exceptions.
- Cache hits mixed with in-flight misses must preserve order and usage.
- Invalid nonfinite windows and noninteger capacities must fail without scheduling work.

### Task 1: Coalescing wrapper

**Files:** Create `src/powercontext/builtin/inference/coalescing.py` and `tests/test_embedding_coalescing.py`.
**Interfaces:** Produce `CoalescingEmbeddingModel(model, *, max_batch_size=64, coalesce_ms=5.0, cache_size=1024)` with profile and async embed returning EmbeddingResult.

- [x] Observe official public tests fail for the absent module (observed).
- [x] Add late-waiter/partial-failure/cancellation and mixed-result regression scenarios.
- [x] Implement shared futures, independent bounded provider tasks, LRU and unique-batch usage aggregation.
- [x] Run official embedding and native request-budget tests plus focused tests; expect all pass.
- [x] Run lint/type checks and relevant inference regression tests, then commit.
