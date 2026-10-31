"""Locate where the hybrid retrieval loses the relevant document.

The hidden acceptance needs an average evidence recall of at least 0.95 over
60 queries.  This asks the Runtime for each channel separately and for the
fused hybrid result, and reports whether the relevant document survives in each.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")


def embed(text: str) -> tuple[float, ...]:
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
        profile_id="hybrid-stages-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(embed(text) for text in texts))


def load_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_qrels() -> dict[str, list[str]]:
    qrels: dict[str, list[str]] = {}
    with (BEIR / "qrels" / "test.tsv").open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3 or (index == 0 and parts[0] == "query-id"):
                continue
            if int(parts[2]) > 0:
                qrels.setdefault(parts[0], []).append(parts[1])
    return qrels


async def main() -> None:
    corpus = {str(row["_id"]): row for row in load_jsonl(BEIR / "corpus.jsonl")}
    queries = {str(row["_id"]): row["text"] for row in load_jsonl(BEIR / "queries.jsonl")}
    qrels = load_qrels()
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs)
    sample_queries = usable[:20]
    needed: set[str] = set()
    for qid in sample_queries:
        needed.update(qrels[qid])
    extra = [cid for cid in corpus if cid not in needed]
    documents = (sorted(needed) + extra)[:173]
    text_of = {cid: corpus[cid]["title"] + " " + corpus[cid]["text"] for cid in documents}
    doc_of_text = {value: cid for cid, value in text_of.items()}
    print(f"queries={len(sample_queries)} documents={len(documents)} relevant={len(needed)}")

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-stages-", dir=os.environ.get("TMPDIR"))) / "db"
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=database_path)), embedding_model=_Embedding()
    ) as contexts:
        scope = await contexts.scopes.create(
            __import__("powercontext.builtin.scope", fromlist=["ScopeDraft"]).ScopeDraft(
                title="s", summary="s", idempotency_key="s"
            )
        )
        memory = (await contexts.get(scope.scope_id)).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(
                MemoryEntryInput(kind="document", text=text_of[cid]) for cid in documents
            ),
            mode="append",
        )

        totals = Counter()
        details = []
        for qid in sample_queries:
            query = queries[qid]
            relevant = set(qrels[qid])
            fts = await memory.search(query, memories=(head,), mode="fts", limit=10)
            vector = await memory.search(query, memories=(head,), mode="vector", limit=10)
            hybrid = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
            fts_docs = {doc_of_text.get(hit.text) for hit in fts.hits}
            vec_docs = {doc_of_text.get(hit.text) for hit in vector.hits}
            hyb_docs = [doc_of_text.get(hit.text) for hit in hybrid.hits]
            totals["queries"] += 1
            totals["fts_reaches"] += bool(relevant & fts_docs)
            totals["vector_reaches"] += bool(relevant & vec_docs)
            totals["hybrid_reaches"] += bool(relevant & set(hyb_docs))
            if relevant & set(hyb_docs):
                first = next(i + 1 for i, d in enumerate(hyb_docs) if d in relevant)
                totals["rank1"] += first == 1
                totals["rank_le10"] += first <= 10
            else:
                details.append({"q": query[:90], "relevant": sorted(relevant)})

        print()
        print(f"  FTS top-10 contains the relevant document : {totals['fts_reaches']}/{totals['queries']}")
        print(f"  vector top-10 contains it                : {totals['vector_reaches']}/{totals['queries']}")
        print(f"  hybrid top-10 contains it                : {totals['hybrid_reaches']}/{totals['queries']}")
        print(f"  relevant doc ranked 1st in hybrid         : {totals['rank1']}/{totals['queries']}")
        print()
        print("  missed queries:")
        for row in details:
            print("   ", json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
