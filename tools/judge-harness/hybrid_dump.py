"""Dump the raw rows of the native hybrid statement for one query.

The diagnose run showed relevant documents sitting at full-text ranks 1, 2 and 3
that never reach the fused top 10.  This script runs the captured hybrid
statement directly and prints the rows the database returns, next to the
full-text-only ranking, so the loss can be attributed to the statement, the
fusion or the admission step.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.scope import ScopeDraft

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
FIXED_VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)
TARGET = os.environ.get("TARGET_QID", "1029")


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-dump-v1",
        model="fixed-unit-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(FIXED_VECTOR for _ in texts))


def load(name: str):
    path = BEIR / name
    if name == "corpus.jsonl":
        out = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                out[str(row["_id"])] = row
        return out
    if name == "queries.jsonl":
        out = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                out[str(row["_id"])] = row["text"]
        return out
    out = {}
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
            if value > 0:
                out.setdefault(parts[0], []).append(parts[1])
    return out


async def main() -> None:
    corpus = load("corpus.jsonl")
    queries = load("queries.jsonl")
    qrels = load("qrels.tsv")
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs and qid != "1")
    sample = usable[:20]
    relevant: set[str] = set()
    for qid in sample:
        relevant.update(qrels[qid])
    terms: set[str] = set()
    for qid in sample:
        terms.update(re.findall(r"[a-z]+", queries[qid].lower()))
    ranked = []
    for cid, row in corpus.items():
        if cid in relevant:
            continue
        overlap = len(terms & set(re.findall(r"[a-z]+", (row["title"] + " " + row["text"]).lower())))
        ranked.append((-overlap, cid))
    ranked.sort()
    documents = sorted(relevant) + [cid for _s, cid in ranked[: 173 - len(relevant)]]
    documents = documents[:173]
    texts = {cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents}
    text_to_id = {value: cid for cid, value in texts.items()}

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-dump-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_contexts(config, embedding_model=_Embedding()) as contexts:
        scope = await contexts.scopes.create(ScopeDraft(title="dump", summary="dump", idempotency_key="dump"))
        memory = (await contexts.get(scope.scope_id)).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(MemoryEntryInput(kind="document", text=texts[cid]) for cid in documents),
            mode="append",
        )
        assert head is not None

        captured: list[tuple[str, object]] = []

        def record(_c, _cur, statement, parameters, _ctx, _many):
            text = str(statement)
            if "pc_memory_entry_heads" in text and "pc_memory_vector_entries" in text:
                captured.append((text, parameters))

        event.listen(Engine, "before_cursor_execute", record)
        query = queries[TARGET]
        page = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
        event.remove(Engine, "before_cursor_execute", record)

        fts = await memory.search(query, memories=(head,), mode="fts", limit=200)
        fts_ids = [text_to_id.get(hit.text, "?") for hit in fts.hits]

        print(f"query {TARGET}: {query}")
        print(f"gold: {qrels[TARGET]}")
        print(f"\nhybrid top 10 ({len(page.hits)} hits):")
        for index, hit in enumerate(page.hits, start=1):
            cid = text_to_id.get(hit.text, "?")
            mark = "GOLD" if cid in qrels[TARGET] else "    "
            print(f"  {index:>2}. {mark} {cid} matched_by={hit.matched_by} score={hit.score:.6f}")
        print(f"\nfts-only ranking, first 12 of {len(fts_ids)}:")
        for index, cid in enumerate(fts_ids[:12], start=1):
            mark = "GOLD" if cid in qrels[TARGET] else "    "
            print(f"  {index:>2}. {mark} {cid}")

        statement, parameters = captured[0]
        async with contexts.database.transaction() as connection:
            rows = (await connection.exec_driver_sql(statement, parameters)).mappings().all()
        print(f"\nraw hybrid statement returned {len(rows)} rows; first 12:")
        for row in rows[:12]:
            cid = text_to_id.get(row["text"], "?")
            mark = "GOLD" if cid in qrels[TARGET] else "    "
            print(
                f"  {mark} {cid} channel={row['channel']} channel_order={row['channel_order']} "
                f"distance={row['distance']}"
            )
        fts_rows = [r for r in rows if r["channel"] == "fts"]
        vector_rows = [r for r in rows if r["channel"] == "vector"]
        print(f"\nchannel sizes: fts={len(fts_rows)} vector={len(vector_rows)}")
        gold_rows = [
            (i, text_to_id.get(r["text"], "?"), r["channel_order"])
            for i, r in enumerate(rows)
            if text_to_id.get(r["text"], "") in qrels[TARGET]
        ]
        print(f"gold rows inside the statement (row index, doc, channel_order): {gold_rows}")


if __name__ == "__main__":
    asyncio.run(main())
