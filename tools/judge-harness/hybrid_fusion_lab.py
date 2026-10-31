"""Compare fusion variants against the frozen two-query path.

Diagnosis so far: with a degenerate (constant) embedding the vector channel is
pure noise, and because a candidate found by both channels scores
1/(60+r) + 1/(60+s) while a lexical-only candidate scores 1/(60+r), the noise
channel pushes the best lexical evidence out of the fused top 10.

This lab measures, on the same scopes, heads, queries and embeddings:

  frozen   - the upstream RRF fusion (what the frozen dual-query path does)
  current  - the product's fusion as shipped
  anchored - a lexical-anchored fusion: candidates found by both channels keep
             the upstream order, lexical-only candidates follow in lexical rank
             order, and vector-only candidates fill the remaining slots.

For every variant it reports mean recall@10, mean MRR@10 and, against the
frozen path, how many queries regress per metric.
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

from powercontext.builtin.artifacts.memory import (
    EmbeddingProfile,
    MemoryChannelHit,
    MemoryEntryInput,
    MemoryHit,
)
from powercontext.builtin.artifacts.memory import fusion as fusion_module
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.scope import ScopeDraft

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")
FIXED_VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)
DISTRACTORS = os.environ.get("DISTRACTORS", "lexical")
EMBED = os.environ.get("EMBED", "hash")


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
        profile_id="hybrid-fusion-lab-v1",
        model="deterministic-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        if EMBED == "fixed":
            return EmbeddingResult(vectors=tuple(FIXED_VECTOR for _ in texts))
        return EmbeddingResult(vectors=tuple(hash_embed(text) for text in texts))


UPSTREAM_FUSE = fusion_module.fuse_rankings

# The frozen reference is the pre-rewrite product behaviour: the composite index
# runs the full-text statement and the vector statement separately, and the
# service fuses both complete candidate lists.  Reproduce it by taking the two
# statements apart again, not by fusing two already-fused top ten lists.
from powercontext.builtin.persistence.memory_index import (  # noqa: E402
    CompositeMemoryIndex,
    memory_channel_hits,
)
from powercontext.builtin.persistence.oceanbase.memory_index import (  # noqa: E402
    OceanBaseMemoryVectorIndex,
)
from powercontext.builtin.persistence.tags import memory_tag_parameters  # noqa: E402
from powercontext.builtin.artifacts.memory.protocols import MemorySearchChannels  # noqa: E402

_ORIGINAL_COMPOSITE_SEARCH = CompositeMemoryIndex.search
_ORIGINAL_VECTOR_SEARCH = OceanBaseMemoryVectorIndex.search


async def _dual_composite_search(self, connection, scope_id, request):
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


def dual_mode() -> None:
    CompositeMemoryIndex.search = _dual_composite_search
    OceanBaseMemoryVectorIndex.search = _dual_vector_search


def new_mode() -> None:
    CompositeMemoryIndex.search = _ORIGINAL_COMPOSITE_SEARCH
    OceanBaseMemoryVectorIndex.search = _ORIGINAL_VECTOR_SEARCH


def anchored_fuse(
    *,
    fts: tuple[MemoryChannelHit, ...],
    vector: tuple[MemoryChannelHit, ...],
    limit: int,
) -> tuple[MemoryHit, ...]:
    """Lexical-anchored fusion.

    Candidates found by both channels keep the upstream reciprocal-rank order and
    stay on top: their score is the sum of two terms, so upstream already ranks
    them above every single-channel candidate.  Lexical-only candidates then
    follow in lexical rank order, and vector-only candidates fill the rest.
    A lexical-only candidate therefore never falls below its upstream position,
    and a vector-only candidate keeps its relative order among its peers.
    """

    if limit < 1:
        raise ValueError("memory search limit must be positive")  # noqa: TRY003

    def identity(hit):
        return (
            hit.memory_ref.artifact_id,
            hit.memory_ref.revision,
            hit.entry_id,
            hit.entry_version_id,
        )

    fts_map = {identity(hit): hit for hit in fts}
    vector_map = {identity(hit): hit for hit in vector}
    both = [key for key in fts_map if key in vector_map]
    fts_only = [key for key in fts_map if key not in vector_map]
    vector_only = [key for key in vector_map if key not in fts_map]

    scores: dict[tuple, float] = {}
    for key, hit in fts_map.items():
        scores[key] = 1.0 / (60 + list(fts_map).index(key) + 1)
    for key, hit in vector_map.items():
        scores[key] = scores.get(key, 0.0) + 1.0 / (60 + list(vector_map).index(key) + 1)

    both.sort(key=lambda key: (-scores[key], key[0].encode(), key[2].encode(), key[3].encode()))
    ordered = both + fts_only + vector_only
    return tuple(
        MemoryHit(
            memory_ref=(fts_map.get(key) or vector_map[key]).memory_ref,
            entry_id=(fts_map.get(key) or vector_map[key]).entry_id,
            entry_version_id=(fts_map.get(key) or vector_map[key]).entry_version_id,
            text=(fts_map.get(key) or vector_map[key]).text,
            score=scores[key],
            matched_by=tuple(
                channel
                for channel, present in (("fts", key in fts_map), ("vector", key in vector_map))
                if present
            ),
        )
        for key in ordered[:limit]
    )


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
            if value > 0:
                qrels.setdefault(parts[0], []).append(parts[1])
    return qrels


def metrics(ids: list[str], gold: list[str]) -> tuple[float, float]:
    goldset = set(gold)
    if not goldset:
        return 0.0, 0.0
    found = sum(1 for cid in ids[:10] if cid in goldset)
    reciprocal = next((1.0 / rank for rank, cid in enumerate(ids[:10], start=1) if cid in goldset), 0.0)
    return found / len(goldset), reciprocal


async def main() -> None:
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs and qid != "1")
    sample = usable[:20]
    relevant: set[str] = set()
    for qid in sample:
        relevant.update(qrels[qid])
    terms: set[str] = set()
    for qid in sample:
        terms.update(re.findall(r"[a-z]+", queries[qid].lower()))
    if DISTRACTORS == "lexical":
        ranked = []
        for cid, row in corpus.items():
            if cid in relevant:
                continue
            overlap = len(terms & set(re.findall(r"[a-z]+", (row["title"] + " " + row["text"]).lower())))
            ranked.append((-overlap, cid))
        ranked.sort()
        pool = [cid for _s, cid in ranked]
    else:
        pool = sorted((cid for cid in corpus if cid not in relevant), key=lambda c: int(c) if c.isdigit() else 0)
    documents = (sorted(relevant) + pool[: 173 - len(relevant)])[:173]
    texts = {cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents}
    text_to_id = {value: cid for cid, value in texts.items()}
    print(f"embed={EMBED} distractors={DISTRACTORS} documents={len(documents)} relevant={len(relevant)}")

    database_path = Path(tempfile.mkdtemp(prefix="fusion-lab-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_contexts(config, embedding_model=_Embedding()) as contexts:
        scope_ids, heads = [], []
        for index in range(3):
            scope = await contexts.scopes.create(
                ScopeDraft(title=f"s{index}", summary="lab", idempotency_key=f"s{index}")
            )
            scope_ids.append(scope.scope_id)
            memory = (await contexts.get(scope.scope_id)).artifacts.memory
            head = await memory.remember(
                memory=None,
                entries=tuple(MemoryEntryInput(kind="document", text=texts[cid]) for cid in documents),
                mode="append",
            )
            assert head is not None
            heads.append(head)

        rows = []
        for index, scope_id in enumerate(scope_ids):
            memory = (await contexts.get(scope_id)).artifacts.memory
            head = heads[index]
            for qid in sample:
                query = queries[qid]
                gold = qrels[qid]

                # frozen reference: the pre-rewrite two-statement path, fused by the
                # product over both complete candidate lists
                dual_mode()
                try:
                    dual_page = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
                finally:
                    new_mode()
                dual = dual_page.hits
                dual_ids = [text_to_id.get(hit.text, "?") for hit in dual]

                current_page = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
                current_ids = [text_to_id.get(hit.text, "?") for hit in current_page.hits]

                fusion_module.fuse_rankings = anchored_fuse
                import powercontext.builtin.artifacts.memory.service as service_module

                service_module.fuse_rankings = anchored_fuse
                try:
                    anchored_page = await memory.search(query, memories=(head,), mode="hybrid", limit=10)
                finally:
                    fusion_module.fuse_rankings = UPSTREAM_FUSE
                    service_module.fuse_rankings = UPSTREAM_FUSE
                anchored_ids = [text_to_id.get(hit.text, "?") for hit in anchored_page.hits]

                rows.append(
                    {
                        "scope": index,
                        "qid": qid,
                        "dual": metrics(dual_ids, gold),
                        "current": metrics(current_ids, gold),
                        "anchored": metrics(anchored_ids, gold),
                        "dual_ids": dual_ids,
                        "current_ids": current_ids,
                        "anchored_ids": anchored_ids,
                        "dual_channels": [list(hit.matched_by) for hit in dual],
                        "current_channels": [list(hit.matched_by) for hit in current_page.hits],
                        "fts_ids": [],
                        "vector_ids": [],
                    }
                )

    def summarize(key: str) -> tuple[float, float, int, int]:
        recalls = [row[key][0] for row in rows]
        mrrs = [row[key][1] for row in rows]
        recall_down = sum(1 for row in rows if row[key][0] < row["dual"][0] - 1e-9)
        mrr_down = sum(1 for row in rows if row[key][1] < row["dual"][1] - 1e-9)
        return sum(recalls) / len(recalls), sum(mrrs) / len(mrrs), recall_down, mrr_down

    print()
    for key in ("dual", "current", "anchored"):
        recall, mrr, recall_down, mrr_down = summarize(key)
        print(
            f"{key:>9}: mean recall@10={recall:.4f}  mean MRR@10={mrr:.4f}  "
            f"queries below frozen: recall={recall_down} mrr={mrr_down}"
        )
    print("\nqueries where the current product path is below the frozen path:")
    for row in rows:
        if row["current"][0] < row["dual"][0] - 1e-9 or row["current"][1] < row["dual"][1] - 1e-9:
            print(
                f"  scope{row['scope']} q{row['qid']}: frozen={row['dual']} current={row['current']}"
            )
            print(f"    frozen  ids: {row['dual_ids']}")
            print(f"    current ids: {row['current_ids']}")
            print(f"    frozen  channels: {row['dual_channels']}")
            print(f"    current channels: {row['current_channels']}")
            pass
            pass
    Path(os.environ.get("OUT", "/tmp/fusion_lab.json")).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
