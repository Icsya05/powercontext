# Incremental context pack implementation plan

> **For agentic workers:** Use superpowers:executing-plans.

**Goal:** Serialize complete contexts and reconstruct later contexts from a validated reusable prefix and replacement suffix.
**Architecture:** Immutable dataclasses own canonical wire encoding, digest and validation. ScopedContextApplication calls its existing prepare and transforms only the transport representation.
**Tech Stack:** Python 3.12, dataclasses, SHA-256, JSON, Base64.
**Spec:** `competition/challenges/context-02-incremental-pack/instruction.md`

## Global Constraints

Exact v1 wire fields and schema names; canonical sorted compact UTF-8 JSON; standard Base64; sha256 digest over schema/items; self-inclusive exact byte_count. UTF-8 chunks default to at most 512 bytes. No content/citation changes, sender caches or hidden state. Invalid protocol inputs raise ContextPackError.

## Review Focus

- Self-inclusive byte count across decimal digit boundaries.
- UTF-8 characters requiring more bytes than the requested chunk limit.
- Duplicate keys, extra keys, invalid Base64 and malformed digest types.
- Empty targets, zero-prefix deltas and changes at every position.
- Corrupted caller-provided base packs and strict integer prefix validation.

### Task 1: Validated wire protocol and Runtime integration

**Files:** Create `src/powercontext/builtin/runtime/context_pack.py`, `tests/test_context_pack.py`; modify only ScopedContextApplication in `application.py`.
**Interfaces:** ContextPack build/from_content/to_bytes/from_bytes; ContextPackDelta between/to_bytes/from_bytes; apply_context_pack_delta; async prepare_incremental(request, base_pack=None).

- [ ] Observe all 14 official tests fail for missing module/method (observed).
- [ ] Add decoding, byte-count and Unicode boundaries independent of implementation.
- [ ] Implement deterministic bounded chunks, canonical codecs and prefix delta reconstruction; forward existing authorization in prepare_incremental.
- [ ] Run official protocol/Runtime tests and focused tests; expect all pass.
- [ ] Measure actual wire savings on a nontrivial repeated/changing context sequence without claiming hidden-workload acceptance; commit.
