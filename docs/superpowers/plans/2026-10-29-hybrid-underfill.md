# Native hybrid underfill implementation plan

**Goal:** Recover available positive-cosine native ANN candidates when historical hybrid fusion returns fewer than the requested limit, preserving every historical result and rank.

**Evidence:** On the eight original public SciFact abstracts with separately obtained pinned MiniLM proxy vectors, ANN matches exact NumPy order; the public claim's nearest document has cosine0.291556 and is rejected by the historical0.3floor. Both current/frozen searches return one lexical hit, leaving nine slots. This is a real-text proxy, not the formal hidden embeddings/qrels or proof of score.

**Architecture:** Add a default-false, excluded-from-serialization backend-neutral `MemorySearchChannels.allow_vector_backfill` hint. Only the existing native hybrid SQL path opts in; old/frozen channels, SQLite, FTS-only and vector-only remain unchanged. Service owns the optional policy: after unchanged historical fusion, append eligible raw vector hits only when admission is implicit, no reranker is configured, and the original result underfills. Positive cosine and finite nonnegative native distance are required. Preserve the complete original prefix, its scores and channel labels; avoid duplicate identities; keep appended scores at or below the prefix tail and ordered. Use existing SQL candidates only, with no added SQL, embedding, model or network dependency.

**Nondegradation:** Underfill-only append preserves every previous relevant document and its rank, so Recall@k and MRR@k cannot decrease relative to that historical prefix. No guarantee of formal absolute0.95recall is claimed.

**Files:** `memory/protocols.py` for optional internal hint; `memory/fusion.py` for additive rank helper; `memory/service.py` for guarded application and truthful admission counts; `persistence/oceanbase/memory_index.py` to opt in for native hybrid only. Existing public APIs are retained.

**Tests:**
- [x] RED public service/native SQL synthetic unit vectors with cosine0.29 and one historical lexical hit; expected prefix retained and available semantic hit appended.
- [x] GREEN helper handles full prefix unchanged, duplicates, zero/negative cosine, invalid distances, empty historical prefix and ordered scores.
- [x] Explicit AdmissionFloor, reranker, FTS-only, vector-only and legacy non-opt-in channels preserve behavior.
- [x] Verify honest retrieved/admitted counts and one candidate SQL; both native indexes remain.
- [x] Compare pinned proxy native output and exact frozen prefix on public texts/title queries; no labels.
- [x] Run core Memory regressions, native hybrid/public acceptance, lint/format, and independent review before commit.

Only modify product/test source. Do not change public assets, fixed dependencies, hidden labels or distances returned by the database.

Verification: public service and real native cosine0.29 regressions were observed failing before implementation. Final core Memory run:73passed13skipped; added mixed three-hit prefix regression then passed11focused backfill tests. Native regressions/public acceptance:4passed. Independent review found no blocking issues. Lint and formatting passed. The pinned proxy preserved all nine frozen prefixes and added only positive-cosine native neighbors; this is not official Recall/MRR or score evidence. The prefix guarantee applies only to the direct Memory.search result at the same limit, not Runtime prepared output, expansion work or context quality.

