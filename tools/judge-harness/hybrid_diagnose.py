"""Locate where the evidence recall is lost on the hidden-style workload.

The published gate for retrieval-02 is an absolute evidence_recall_at_10 >= 0.95
over 60 searches, plus a per-query rule that no query may score below the frozen
two-query path.  This script reports, for every query:

  * the relevant document's rank in the raw full-text channel (before admission),
  * whether the admission floor kept it,
  * its rank in the vector channel,
  * its final position in the fused top 10,

so the lost recall can be attributed to one stage instead of guessed at.
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
from powercontext.builtin.scope import ScopeDraft

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
FIXED_VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)
TOKEN = re.compile(r"[a-z]+|\d+")
EMBED = os.environ.get("EMBED", "fixed")


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


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-diagnose-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        if EMBED == "fixed":
            return EmbeddingResult(vectors=tuple(FIXED_VECTOR for _ in texts))
        return EmbeddingResult(vectors=tuple(hash_embed(text) for text in texts))


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


async def main() -> None:
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs and qid != "1")
    sample_queries = usable[:20]

    relevant: set[str] = set()
    for qid in sample_queries:
        relevant.update(qrels[qid])
    terms: set[str] = set()
    for qid in sample_queries:
        terms.update(re.findall(r"[a-z]+", queries[qid].lower()))
    distractors = []
    for cid, row in corpus.items():
        if cid in relevant:
            continue
        overlap = len(terms & set(re.findall(r"[a-z]+", (row["title"] + " " + row["text"]).lower())))
        distractors.append((-overlap, cid))
    distractors.sort()
    documents = sorted(relevant) + [cid for _score, cid in distractors[: 173 - len(relevant)]]
    documents = documents[:173]
    texts = {cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents}
    text_to_id = {value: cid for cid, value in texts.items()}

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-diag-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_contexts(config, embedding_model=_Embedding()) as contexts:
        scope = await contexts.scopes.create(
            ScopeDraft(title="diag", summary="diag", idempotency_key="diag")
        )
        memory = (await contexts.get(scope.scope_id)).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(MemoryEntryInput(kind="document", text=texts[cid]) for cid in documents),
            mode="append",
        )
        assert head is not None
        print(f"documents={len(documents)} relevant={len(relevant)} queries={len(sample_queries)}")

        rows = []
        for qid in sample_queries:
            gold = set(qrels[qid])
            hybrid = await memory.search(queries[qid], memories=(head,), mode="hybrid", limit=10)
            fts = await memory.search(queries[qid], memories=(head,), mode="fts", limit=200)
            vector = await memory.search(queries[qid], memories=(head,), mode="vector", limit=200)
            hybrid_ids = [text_to_id.get(hit.text, "?") for hit in hybrid.hits]
            fts_ids = [text_to_id.get(hit.text, "?") for hit in fts.hits]
            vector_ids = [text_to_id.get(hit.text, "?") for hit in vector.hits]
            found = [cid for cid in hybrid_ids if cid in gold]
            missing = sorted(gold - set(hybrid_ids))
            detail = {}
            for cid in missing:
                detail[cid] = {
                    "fts_rank": (fts_ids.index(cid) + 1) if cid in fts_ids else None,
                    "vector_rank": (vector_ids.index(cid) + 1) if cid in vector_ids else None,
                }
            rows.append(
                {
                    "qid": qid,
                    "query": queries[qid],
                    "gold": sorted(gold),
                    "hybrid_top10": hybrid_ids,
                    "recall": len(found) / len(gold),
                    "mrr": next(
                        (1.0 / rank for rank, cid in enumerate(hybrid_ids, start=1) if cid in gold),
                        0.0,
                    ),
                    "fts_channel_size": len(fts_ids),
                    "vector_channel_size": len(vector_ids),
                    "missing": detail,
                }
            )

    total = sum(row["recall"] for row in rows) / len(rows)
    print(f"\nmean recall@10 = {total:.4f}  (absolute gate 0.95)")
    print(f"mean MRR@10    = {sum(row['mrr'] for row in rows) / len(rows):.4f}")
    print(f"fts channel size   : min={min(r['fts_channel_size'] for r in rows)} "
          f"max={max(r['fts_channel_size'] for r in rows)}")
    print(f"vector channel size: min={min(r['vector_channel_size'] for r in rows)} "
          f"max={max(r['vector_channel_size'] for r in rows)}")
    print("\nper query:")
    for row in rows:
        flag = "OK " if row["recall"] >= 1.0 else "MISS"
        where = ""
        for cid, info in row["missing"].items():
            where += (
                f" {cid}: fts_rank={info['fts_rank']} vector_rank={info['vector_rank']}"
            )
        print(
            f"{flag} q{row['qid']:<5} recall={row['recall']:.2f} mrr={row['mrr']:.3f} "
            f"fts={row['fts_channel_size']:<4} vec={row['vector_channel_size']:<4}{where}"
        )
        print(f"      q: {row['query']}")
    Path(os.environ.get("OUT", "/tmp/hybrid_diag.json")).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    import tempfile

    asyncio.run(main())
