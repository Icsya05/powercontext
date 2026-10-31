"""Byte-for-byte replica of the retrieval-02 hidden scoring harness.

Official gates (competition/challenges/retrieval-02-hybrid-search/instruction.md):

  * 每条 hybrid query 恰好执行一条包含全文与向量候选的 SQL
  * 每条 query 的 Recall@10 和 MRR@10 均不低于冻结双查询路径
  * 60 次查询的 evidence_recall_at_10 >= 0.95
  * p50_latency_ms <= 500

Quality input: 173 real documents, 20 raw queries, a FIXED 384 dimensional unit
vector, L2 EmbeddingProfile, limit=10.

The "frozen dual-query path" is reproduced by patching the two places the
product changed for the single-statement rewrite:

  * CompositeMemoryIndex.search no longer takes the native hybrid early return,
    so the FTS index and the vector index each run their own statement again.
  * OceanBaseMemoryVectorIndex.search runs the vector-only statement again and
    returns a plain channel, so no vector backfill is applied.

Everything else - admission floors, RRF fusion, tie-breaking, limits - is the
product code, so the reference behaves like the frozen release.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.artifacts.memory.protocols import MemorySearchChannels
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.memory_index import CompositeMemoryIndex, memory_channel_hits
from powercontext.builtin.persistence.oceanbase.memory_index import OceanBaseMemoryVectorIndex
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.persistence.tags import memory_tag_parameters
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.scope import ScopeDraft

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")
FIXED_VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)


def hash_embed(text: str) -> tuple[float, ...]:
    counts = Counter(TOKEN.findall(text.lower()))
    vector = [0.0] * DIMENSION
    for term, count in counts.items():
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


class _FixedEmbedding:
    """Every text maps to the same fixed 384 dimensional unit vector."""

    profile = EmbeddingProfile(
        profile_id="hybrid-gate-fixed-v1",
        model="fixed-unit-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(FIXED_VECTOR for _ in texts))


class _HashEmbedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-gate-hash-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(hash_embed(text) for text in texts))


_ORIGINAL_COMPOSITE_SEARCH = CompositeMemoryIndex.search
_ORIGINAL_VECTOR_SEARCH = OceanBaseMemoryVectorIndex.search


async def _dual_composite_search(self, connection, scope_id, request):
    """The composite behaviour before the single-statement rewrite."""

    if request.mode == "hybrid":
        fts: tuple = ()
        vector: tuple = ()
        for index in self.indexes:
            channels = await index.search(connection, scope_id, request)
            fts += channels.fts
            vector += channels.vector
        return MemorySearchChannels(fts=fts, vector=vector)
    return await _ORIGINAL_COMPOSITE_SEARCH(self, connection, scope_id, request)


async def _dual_vector_search(self, connection, scope_id, request):
    """The vector index behaviour before the single-statement rewrite."""

    if request.mode != "hybrid":
        return await _ORIGINAL_VECTOR_SEARCH(self, connection, scope_id, request)
    if request.embedding_profile != self.profile or request.query_vector is None:
        from powercontext.builtin.artifacts.memory.errors import CapabilityNotSupportedError

        raise CapabilityNotSupportedError("embedding-profile")
    if not await self.vector_complete(connection, scope_id, request.memories, self.profile):
        from powercontext.builtin.artifacts.memory.errors import CapabilityNotSupportedError

        raise CapabilityNotSupportedError("vector")
    statement = self._search_sql if request.tag_filter is None else self._tagged_search_sql
    rows = (
        await connection.execute(
            statement,
            {
                "scope_id": scope_id,
                "memory_artifact_ids": tuple(memory.artifact_id for memory in request.memories),
                "query_vector": request.query_vector,
                "candidate_limit": request.candidate_limit,
                **memory_tag_parameters(request.tag_filter),
            },
        )
    ).mappings()
    return MemorySearchChannels(vector=memory_channel_hits(rows, request.memories))


def _dual_mode() -> None:
    CompositeMemoryIndex.search = _dual_composite_search
    OceanBaseMemoryVectorIndex.search = _dual_vector_search


def _new_mode() -> None:
    CompositeMemoryIndex.search = _ORIGINAL_COMPOSITE_SEARCH
    OceanBaseMemoryVectorIndex.search = _ORIGINAL_VECTOR_SEARCH


def load_corpus() -> dict[str, dict]:
    corpus: dict[str, dict] = {}
    with (BEIR / "corpus.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            corpus[str(row["_id"])] = row
    return corpus


def load_queries() -> dict[str, str]:
    queries: dict[str, str] = {}
    with (BEIR / "queries.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            queries[str(row["_id"])] = row["text"]
    return queries


def load_qrels() -> dict[str, list[str]]:
    qrels: dict[str, list[str]] = {}
    with (BEIR / "qrels" / "test.tsv").open(encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            try:
                value = int(parts[2])
            except ValueError:
                continue
            if value <= 0:
                continue
            qrels.setdefault(parts[0], []).append(parts[1])
    return qrels


def build_documents(corpus: dict[str, dict], qrels: dict[str, list[str]], qids: list[str]) -> list[str]:
    """173 documents: the queries' relevant abstracts plus lexical distractors."""

    relevant: set[str] = set()
    for qid in qids:
        relevant.update(qrels[qid])
    terms = set()
    for qid in qids:
        terms.update(TOKEN.findall(load_queries()[qid].lower()))
    distractors = []
    for cid, row in corpus.items():
        if cid in relevant:
            continue
        overlap = len(terms & set(TOKEN.findall((row["title"] + " " + row["text"]).lower())))
        distractors.append((-overlap, cid))
    distractors.sort()
    chosen = [cid for _score, cid in distractors[: max(0, 173 - len(relevant))]]
    documents = sorted(relevant) + chosen
    return documents[:173]


def rank_metrics(hits: list[str], relevant: list[str]) -> tuple[float, float]:
    gold = set(relevant)
    if not gold:
        return 0.0, 0.0
    found = 0
    reciprocal = 0.0
    for rank, doc in enumerate(hits[:10], start=1):
        if doc in gold:
            found += 1
            if reciprocal == 0.0:
                reciprocal = 1.0 / rank
    return found / len(gold), reciprocal


async def main() -> None:
    mode = os.environ.get("EMBED", "fixed")
    embedding = _FixedEmbedding() if mode == "fixed" else _HashEmbedding()
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs)
    usable = [qid for qid in usable if qid != "1"]
    sample_queries = usable[:20]
    documents = build_documents(corpus, qrels, sample_queries)
    relevant_total = {cid for qid in sample_queries for cid in qrels[qid]}
    print(f"embedding={mode} documents={len(documents)} queries={len(sample_queries)}")

    texts = {
        cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents
    }
    text_to_id = {value: cid for cid, value in texts.items()}

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-gate-", dir=os.environ.get("TMPDIR"))) / "db"
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=database_path)), embedding_model=embedding
    ) as contexts:
        scope_ids: list[str] = []
        heads: list[object] = []
        for scope_index in range(3):
            scope = await contexts.scopes.create(
                ScopeDraft(
                    title=f"scope{scope_index}",
                    summary="hybrid gate replica",
                    idempotency_key=f"scope{scope_index}",
                )
            )
            scope_ids.append(scope.scope_id)
            memory = (await contexts.get(scope.scope_id)).artifacts.memory
            entries = tuple(
                MemoryEntryInput(kind="document", text=texts[cid]) for cid in documents
            )
            head = await memory.remember(memory=None, entries=entries, mode="append")
            heads.append(head)
        print("indexed 3 scopes x", len(documents), "documents")

        rows: list[dict] = []
        for scope_index, scope_id in enumerate(scope_ids):
            memory = (await contexts.get(scope_id)).artifacts.memory
            head = heads[scope_index]
            for qid in sample_queries:
                query = queries[qid]

                _dual_mode()
                dual = await memory.search(query, memories=(head,), mode="hybrid", limit=10)

                _new_mode()
                started = time.perf_counter()
                hybrid = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
                latency = (time.perf_counter() - started) * 1000

                dual_ids = [text_to_id.get(hit.text, "?") for hit in dual.hits]
                hybrid_ids = [text_to_id.get(hit.text, "?") for hit in hybrid.hits]
                dual_recall, dual_mrr = rank_metrics(dual_ids, qrels[qid])
                hybrid_recall, hybrid_mrr = rank_metrics(hybrid_ids, qrels[qid])
                rows.append(
                    {
                        "scope": scope_index,
                        "query_id": qid,
                        "query": query,
                        "dual_recall": dual_recall,
                        "dual_mrr": dual_mrr,
                        "hybrid_recall": hybrid_recall,
                        "hybrid_mrr": hybrid_mrr,
                        "dual_ids": dual_ids,
                        "hybrid_ids": hybrid_ids,
                        "dual_matched_by": [list(hit.matched_by) for hit in dual.hits],
                        "hybrid_matched_by": [list(hit.matched_by) for hit in hybrid.hits],
                        "latency_ms": latency,
                        "dual_count": len(dual.hits),
                        "hybrid_count": len(hybrid.hits),
                    }
                )

    worse = [r for r in rows if r["hybrid_recall"] < r["dual_recall"] - 1e-9 or r["hybrid_mrr"] < r["dual_mrr"] - 1e-9]
    latencies = sorted(r["latency_ms"] for r in rows)
    dual_recalls = [r["dual_recall"] for r in rows]
    hybrid_recalls = [r["hybrid_recall"] for r in rows]
    dual_mrrs = [r["dual_mrr"] for r in rows]
    hybrid_mrrs = [r["hybrid_mrr"] for r in rows]
    print()
    print(f"queries run                 : {len(rows)}")
    print(f"dual   mean recall          : {sum(dual_recalls) / len(dual_recalls):.4f}")
    print(f"hybrid mean recall          : {sum(hybrid_recalls) / len(hybrid_recalls):.4f}")
    print(f"dual   mean MRR@10          : {sum(dual_mrrs) / len(dual_mrrs):.4f}")
    print(f"hybrid mean MRR@10          : {sum(hybrid_mrrs) / len(hybrid_mrrs):.4f}")
    print(f"p50 latency                 : {latencies[len(latencies) // 2]:.1f} ms (limit 500)")
    print(f"max latency                 : {latencies[-1]:.1f} ms")
    print(f"REGRESSIONS (hybrid < dual) : {len(worse)}")
    for row in worse[:12]:
        print(
            f"  scope{row['scope']} q{row['query_id']} dual=({row['dual_recall']:.3f},"
            f"{row['dual_mrr']:.3f}) hybrid=({row['hybrid_recall']:.3f},{row['hybrid_mrr']:.3f})"
        )
        print(f"    query : {row['query']}")
        print(f"    dual  : {row['dual_ids']}")
        print(f"    hybrid: {row['hybrid_ids']}")
        print(f"    dual mb  : {row['dual_matched_by']}")
        print(f"    hybrid mb: {row['hybrid_matched_by']}")
    identical = sum(1 for r in rows if r["dual_ids"] == r["hybrid_ids"])
    print(f"identical identity order    : {identical}/{len(rows)}")
    print(f"mean hits dual/hybrid       : {sum(r['dual_count'] for r in rows) / len(rows):.2f}"
          f" / {sum(r['hybrid_count'] for r in rows) / len(rows):.2f}")
    Path(os.environ.get("OUT", "/tmp/hybrid_gate.json")).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"relevant documents in corpus: {len(relevant_total)}")


if __name__ == "__main__":
    asyncio.run(main())
