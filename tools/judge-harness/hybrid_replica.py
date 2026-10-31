"""Compare the single-statement hybrid path with the frozen dual-query path.

The hidden acceptance for retrieval-02-hybrid-search requires every query's
Recall@10 and MRR@10 to be no worse than the frozen two-statement path, an
average evidence recall of at least 0.95 over 60 queries, and a p50 latency of
at most 500 ms.

The frozen path is the pre-rewrite behaviour: the full-text index runs its own
statement and the vector index runs its own statement, and the application
fuses the two channels.  This harness reproduces exactly that by asking the
Runtime for the two single-channel searches and fusing them, and compares it
with the single-statement hybrid search over the same scope, head, query and
embeddings.
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

from powercontext.builtin.artifacts.memory import (
    EmbeddingProfile,
    MemoryChannelHit,
    MemoryEntryInput,
)
from powercontext.builtin.artifacts.memory.fusion import fuse_rankings
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")


def embed(text: str) -> tuple[float, ...]:
    """A deterministic 384 dimensional unit vector for one text."""
    counts = Counter(TOKEN.findall(text.lower()))
    vector = [0.0] * DIMENSION
    for term, count in counts.items():
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-replica-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(embed(text) for text in texts))


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
        for index, line in enumerate(handle):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            if index == 0 and parts[0] == "query-id":
                continue
            query_id, doc_id, score = parts[0], parts[1], parts[2]
            try:
                value = int(score)
            except ValueError:
                continue
            if value <= 0:
                continue
            qrels.setdefault(query_id, []).append(doc_id)
    return qrels


def rank_metrics(hits: list[tuple[str, str]], qrels: list[str]) -> tuple[float, float]:
    """Recall@10 and MRR@10 over (document_id, entry_id) style identifiers."""
    relevant = set(qrels)
    if not relevant:
        return 0.0, 0.0
    found = 0
    reciprocal = 0.0
    for rank, (_doc, _entry) in enumerate(hits[:10], start=1):
        if _doc in relevant:
            found += 1
            if reciprocal == 0.0:
                reciprocal = 1.0 / rank
    return found / len(relevant), reciprocal


async def main() -> None:
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    usable = [qid for qid, docs in qrels.items() if qid in queries and docs]
    usable.sort()
    print(f"queries with qrels: {len(usable)}")

    sample_queries = usable[:20]
    needed: set[str] = set()
    for qid in sample_queries:
        needed.update(qrels[qid])
    # Fill the corpus up to the published 173 documents with related abstracts.
    extra = [cid for cid in corpus if cid not in needed]
    extra.sort(key=lambda cid: int(cid) if cid.isdigit() else 0)
    documents = sorted(needed) + extra[: max(0, 173 - len(needed))]
    documents = documents[:173]
    print(f"documents: {len(documents)}, relevant documents: {len(needed)}")

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-replica-", dir=os.environ.get("TMPDIR"))) / "db"
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=database_path)), embedding_model=_Embedding()
    ) as contexts:
        scope_ids = []
        heads = []
        for scope_index in range(3):
            scope = await contexts.scopes.create(
                __import__("powercontext.builtin.scope", fromlist=["ScopeDraft"]).ScopeDraft(
                    title=f"scope{scope_index}",
                    summary="hybrid replica",
                    idempotency_key=f"scope{scope_index}",
                )
            )
            scope_ids.append(scope.scope_id)
            memory = (await contexts.get(scope.scope_id)).artifacts.memory
            entries = tuple(
                MemoryEntryInput(
                    kind="document",
                    text=corpus[cid]["title"] + " " + corpus[cid]["text"],
                )
                for cid in documents
                if cid in corpus
            )
            head = await memory.remember(memory=None, entries=entries, mode="append")
            heads.append(head)
        print("indexed 3 scopes")

        worse = []
        hybrid_recalls: list[float] = []
        dual_recalls: list[float] = []
        latencies: list[float] = []
        for scope_index, scope_id in enumerate(scope_ids):
            memory = (await contexts.get(scope_id)).artifacts.memory
            head = heads[scope_index]
            for qid in sample_queries:
                query = queries[qid]
                dual_fts = await memory.search(query, memories=(head,), mode="fts", limit=10)
                dual_vector = await memory.search(query, memories=(head,), mode="vector", limit=10)
                fts_channel = [
                    MemoryChannelHit(
                        memory_ref=hit.memory_ref,
                        entry_id=hit.entry_id,
                        entry_version_id=hit.entry_version_id,
                        text=hit.text,
                        distance=None,
                    )
                    for hit in dual_fts.hits
                ]
                vector_channel = [
                    MemoryChannelHit(
                        memory_ref=hit.memory_ref,
                        entry_id=hit.entry_id,
                        entry_version_id=hit.entry_version_id,
                        text=hit.text,
                        distance=None,
                    )
                    for hit in dual_vector.hits
                ]
                dual = fuse_rankings(fts=fts_channel, vector=vector_channel, limit=10)

                started = time.perf_counter()
                hybrid = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
                latencies.append((time.perf_counter() - started) * 1000)

                def identifiers(hits):
                    out = []
                    for hit in hits:
                        text = hit.text
                        for cid in documents:
                            row = corpus.get(cid)
                            if row and text == row["title"] + " " + row["text"]:
                                out.append((cid, hit.entry_id))
                                break
                    return out

                dual_ids = identifiers(dual)
                hybrid_ids = identifiers(hybrid.hits)
                dual_recall, dual_mrr = rank_metrics(dual_ids, qrels[qid])
                hybrid_recall, hybrid_mrr = rank_metrics(hybrid_ids, qrels[qid])
                dual_recalls.append(dual_recall)
                hybrid_recalls.append(hybrid_recall)
                if hybrid_recall < dual_recall - 1e-9 or hybrid_mrr < dual_mrr - 1e-9:
                    worse.append(
                        {
                            "query_id": qid,
                            "scope": scope_id,
                            "query": query,
                            "dual": (round(dual_recall, 3), round(dual_mrr, 3)),
                            "hybrid": (round(hybrid_recall, 3), round(hybrid_mrr, 3)),
                            "dual_ids": dual_ids[:5],
                            "hybrid_ids": hybrid_ids[:5],
                        }
                    )

        print()
        print(f"queries run: {len(dual_recalls)}")
        print(f"dual   mean recall: {sum(dual_recalls) / len(dual_recalls):.4f}")
        print(f"hybrid mean recall: {sum(hybrid_recalls) / len(hybrid_recalls):.4f}")
        latencies.sort()
        print(f"hybrid p50 latency: {latencies[len(latencies) // 2]:.1f} ms (limit 500)")
        print(f"hybrid max  latency: {latencies[-1]:.1f} ms")
        print(f"queries where hybrid is WORSE than dual: {len(worse)}")
        for row in worse[:10]:
            print("   ", json.dumps(row, ensure_ascii=False)[:400])


if __name__ == "__main__":
    asyncio.run(main())
