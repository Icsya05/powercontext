"""Compare the standalone vector query with the vector arm of the hybrid statement.

The vector channel orders by an approximate nearest-neighbour scan, so its top-k
candidate set depends on the plan.  The frozen two-query path runs the vector
statement on its own; the one-statement path runs it as a UNION ALL arm.  This
script runs both against the same database and prints the two candidate sets
side by side, so the difference can be attributed to the plan rather than to the
fusion.
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

from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.scope import ScopeDraft

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")
TARGET = os.environ.get("TARGET_QID", "1088")


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
        profile_id="hybrid-vecdiff-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(hash_embed(text) for text in texts))


def load(name: str):
    if name == "corpus.jsonl":
        out = {}
        with (BEIR / name).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                out[str(row["_id"])] = row
        return out
    if name == "queries.jsonl":
        out = {}
        with (BEIR / name).open(encoding="utf-8") as handle:
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
    documents = (sorted(relevant) + [cid for _s, cid in ranked[: 173 - len(relevant)]])[:173]
    texts = {cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents}
    text_to_id = {value: cid for cid, value in texts.items()}

    database_path = Path(tempfile.mkdtemp(prefix="vecdiff-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_contexts(config, embedding_model=_Embedding()) as contexts:
        scope = await contexts.scopes.create(ScopeDraft(title="v", summary="v", idempotency_key="v"))
        memory = (await contexts.get(scope.scope_id)).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(MemoryEntryInput(kind="document", text=texts[cid]) for cid in documents),
            mode="append",
        )
        assert head is not None
        query = queries[TARGET]

        captured: list[tuple[str, object]] = []

        def record(_c, _cur, statement, parameters, _ctx, _many):
            text = str(statement)
            if "l2_distance" not in text.lower() and "AGAINST" not in text.upper():
                return
            captured.append((text, parameters))

        event.listen(Engine, "before_cursor_execute", record)
        await memory.search(query, memories=(head,), mode="vector", limit=10)
        await memory.search(query, memories=(head,), mode="fts", limit=10)
        event.remove(Engine, "before_cursor_execute", record)
        standalone_sql, standalone_params = captured[0]
        standalone_fts_sql, standalone_fts_params = captured[1]
        print(f"captured standalone: {standalone_sql[:80]!r}")

        captured.clear()
        event.listen(Engine, "before_cursor_execute", record)
        await memory.search(query, memories=(head,), mode="hybrid", limit=10)
        event.remove(Engine, "before_cursor_execute", record)
        hybrid_sql, hybrid_params = captured[0]

        async with contexts.database.transaction() as connection:
            standalone_rows = (
                await connection.exec_driver_sql(standalone_sql, standalone_params)
            ).mappings().all()
            hybrid_rows = (await connection.exec_driver_sql(hybrid_sql, hybrid_params)).mappings().all()
            standalone_fts_rows = (
                await connection.exec_driver_sql(standalone_fts_sql, standalone_fts_params)
            ).mappings().all()
            hybrid_fts_rows = [
                row for row in hybrid_rows if row["channel"] == "fts"
            ]

        standalone_fts_ids = [text_to_id.get(row["text"], "?") for row in standalone_fts_rows]
        hybrid_fts_ids = [text_to_id.get(row["text"], "?") for row in hybrid_fts_rows]
        print("\nstandalone fts statement rows :", len(standalone_fts_ids))
        print("hybrid fts arm rows           :", len(hybrid_fts_ids))
        print(f"fts sets equal   : {set(standalone_fts_ids) == set(hybrid_fts_ids)}")
        print(f"fts order equal  : {standalone_fts_ids == hybrid_fts_ids}")
        print(f"fts only standalone: {sorted(set(standalone_fts_ids) - set(hybrid_fts_ids))}")
        print(f"fts only hybrid    : {sorted(set(hybrid_fts_ids) - set(standalone_fts_ids))}")
        print("standalone fts order:", standalone_fts_ids[:12])
        print("hybrid fts order   :", hybrid_fts_ids[:12])

        standalone = [
            (text_to_id.get(row["text"], "?"), round(float(row["distance"]), 6))
            for row in standalone_rows
        ]
        hybrid_vector = [
            (text_to_id.get(row["text"], "?"), round(float(row["distance"]), 6))
            for row in hybrid_rows
            if row["channel"] == "vector"
        ]

        print(f"query {TARGET}: {query}")
        print(f"standalone vector statement returned {len(standalone)} rows")
        print(f"hybrid statement vector arm returned {len(hybrid_vector)} rows")
        print("\nstandalone (frozen path):")
        for index, (cid, distance) in enumerate(standalone, start=1):
            mark = "GOLD" if cid in qrels[TARGET] else "    "
            print(f"  {index:>3}. {mark} {cid} distance={distance}")
        print("\nhybrid arm:")
        for index, (cid, distance) in enumerate(hybrid_vector, start=1):
            mark = "GOLD" if cid in qrels[TARGET] else "    "
            print(f"  {index:>3}. {mark} {cid} distance={distance}")

        standalone_ids = [cid for cid, _d in standalone]
        hybrid_ids = [cid for cid, _d in hybrid_vector]
        print(f"\nsets equal      : {set(standalone_ids) == set(hybrid_ids)}")
        print(f"order equal     : {standalone_ids == hybrid_ids}")
        print(f"only standalone : {sorted(set(standalone_ids) - set(hybrid_ids))}")
        print(f"only hybrid     : {sorted(set(hybrid_ids) - set(standalone_ids))}")


if __name__ == "__main__":
    asyncio.run(main())
