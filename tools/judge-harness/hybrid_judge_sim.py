"""Simulate the hidden functional gates of retrieval-02-hybrid-search.

The published acceptance for seekdb hybrid candidate search lists functional
requirements that the public acceptance test does not fully cover:

  * hit validity: 20 queries x 3 scopes = 60 searches; every hit belongs to the
    requested scope and head, references the current valid entry version, carries
    that version's text verbatim, has a non-empty channel tag from {fts, vector},
    and never repeats an identity.
  * candidate access cost: exactly one candidate statement per hybrid query.
  * native indexes: the statement's EXPLAIN shows both TEXT RETRIEVAL SCAN and
    VECTOR INDEX.
  * stability: repeated queries return the same identities in the same order.
  * single channel behaviour: fts-only and vector-only still work.
  * current head: a stale head is rejected.
  * incremental projection: unmodified entries stay retrievable; the returned
    reference is the verified current head.
  * state changes: append, revise, deactivate and reactivate stay consistent.
  * scope isolation: a search never returns another scope's hits.

The workload mirrors the published quality input: 173 real SciFact abstracts,
20 raw queries, a fixed 384 dimensional unit vector, L2 EmbeddingProfile and
limit=10.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import (
    CapabilityNotSupportedError,
    EmbeddingProfile,
    MemoryEntryInput,
)
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.scope import ScopeDraft
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

BEIR = Path(os.environ.get("BEIR_DIR", "/beir/scifact"))
DIMENSION = 384
TOKEN = re.compile(r"[a-z]+|\d+")
FIXED_VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)
FAILURES: list[str] = []


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-judge-sim-v1",
        model="fixed-unit-384",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(FIXED_VECTOR for _ in texts))


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(name)
        print(f"  [FAIL] {name}{(' - ' + detail) if detail else ''}")
    else:
        print(f"  [ok]   {name}{(' - ' + detail) if detail else ''}")


class _Statements:
    """Record every statement the driver executes."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, object]] = []
        self._record = None

    def __enter__(self) -> "_Statements":
        def record(_connection, _cursor, statement, parameters, _context, _executemany):
            self.rows.append((str(statement), parameters))

        self._record = record
        event.listen(Engine, "before_cursor_execute", record)
        return self

    def __exit__(self, *exc) -> None:
        if self._record is not None:
            event.remove(Engine, "before_cursor_execute", self._record)

    def native(self) -> list[tuple[str, object]]:
        return [
            (statement, parameters)
            for statement, parameters in self.rows
            if "pc_memory_entry_heads" in statement
            and "pc_memory_vector_entries" in statement
            and "AGAINST" in statement.upper()
            and "l2_distance" in statement.lower()
        ]


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
    return corpus_free_qrels(qrels)


def corpus_free_qrels(qrels: dict[str, list[str]]) -> dict[str, list[str]]:
    return qrels


def build_documents(corpus: dict[str, dict], qrels: dict[str, list[str]], qids: list[str]) -> list[str]:
    relevant: set[str] = set()
    for qid in qids:
        relevant.update(qrels[qid])
    distractors = sorted(
        (cid for cid in corpus if cid not in relevant),
        key=lambda cid: int(cid) if cid.isdigit() else 0,
    )
    documents = sorted(relevant) + distractors[: max(0, 173 - len(relevant))]
    return documents[:173]


async def main() -> None:
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    usable = sorted(qid for qid, docs in qrels.items() if qid in queries and docs and qid != "1")
    sample_queries = usable[:20]
    documents = build_documents(corpus, qrels, sample_queries)
    texts = {cid: (corpus[cid]["title"] + " " + corpus[cid]["text"])[:8000] for cid in documents}
    print(f"documents={len(documents)} queries={len(sample_queries)}")

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-sim-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_contexts(config, embedding_model=_Embedding()) as contexts:
        scope_ids: list[str] = []
        heads: list[object] = []
        for index in range(3):
            scope = await contexts.scopes.create(
                ScopeDraft(title=f"scope{index}", summary="judge sim", idempotency_key=f"scope{index}")
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
        print("indexed 3 scopes")

        print("\n1. sixty searches: hit validity and statement cost")
        statement_counts: Counter[int] = Counter()
        invalid_identity = invalid_version = invalid_text = invalid_channel = duplicate = 0
        unstable = 0
        latencies: list[float] = []
        for index, scope_id in enumerate(scope_ids):
            memory = (await contexts.get(scope_id)).artifacts.memory
            head = heads[index]
            versions = {entry.entry_id: entry for entry in await memory.entries(head)}
            for qid in sample_queries:
                with _Statements() as statements:
                    started = time.perf_counter()
                    page = await memory.search(queries[qid], memories=(head,), mode="hybrid", limit=10)
                    latencies.append((time.perf_counter() - started) * 1000)
                statement_counts[len(statements.native())] += 1
                identities: set[tuple[str, str, str]] = set()
                for hit in page.hits:
                    identity = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
                    if identity in identities:
                        duplicate += 1
                    identities.add(identity)
                    if hit.memory_ref != head.as_ref():
                        invalid_identity += 1
                    version = versions.get(hit.entry_id)
                    if version is None or version.entry_version_id != hit.entry_version_id:
                        invalid_version += 1
                    elif version.text != hit.text:
                        invalid_text += 1
                    if not hit.matched_by or not set(hit.matched_by) <= {"fts", "vector"}:
                        invalid_channel += 1
                again = await memory.search(queries[qid], memories=(head,), mode="hybrid", limit=10)
                first = [(hit.entry_id, hit.entry_version_id) for hit in page.hits]
                second = [(hit.entry_id, hit.entry_version_id) for hit in again.hits]
                if first != second:
                    unstable += 1
        check("one candidate statement per hybrid search", set(statement_counts) == {1}, str(dict(statement_counts)))
        check("hits reference the current head", invalid_identity == 0, f"{invalid_identity} bad")
        check("hits reference the current entry version", invalid_version == 0, f"{invalid_version} bad")
        check("hit text matches that version verbatim", invalid_text == 0, f"{invalid_text} bad")
        check("matched_by non-empty and within fts/vector", invalid_channel == 0, f"{invalid_channel} bad")
        check("no duplicate identity", duplicate == 0, f"{duplicate} bad")
        check("repeated queries stable", unstable == 0, f"{unstable} unstable")
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        check("p50 latency <= 500ms", p50 <= 500, f"p50={p50:.1f}ms max={latencies[-1]:.1f}ms")

        print("\n2. native index EXPLAIN")
        memory = (await contexts.get(scope_ids[0])).artifacts.memory
        with _Statements() as statements:
            await memory.search(queries[sample_queries[0]], memories=(heads[0],), mode="hybrid", limit=10)
        native = statements.native()
        check("captured one candidate statement", len(native) == 1, f"{len(native)}")
        if native:
            statement, parameters = native[0]
            async with contexts.database.transaction() as connection:
                plan = "\n".join(
                    str(row[0]) for row in (await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
                )
            check("EXPLAIN has TEXT RETRIEVAL SCAN", "TEXT RETRIEVAL SCAN" in plan)
            check("EXPLAIN has VECTOR INDEX", "VECTOR INDEX" in plan)

        print("\n3. single channel behaviour")
        for mode in ("fts", "vector"):
            with _Statements() as statements:
                page = await memory.search(queries[sample_queries[0]], memories=(heads[0],), mode=mode, limit=10)
            check(f"{mode} channel returns hits", len(page.hits) > 0, f"{len(page.hits)} hits")
            check(f"{mode} channel does not run the hybrid statement", not statements.native())

        print("\n4. scope isolation")
        first_ids = {
            hit.entry_id
            for hit in (await memory.search(queries[sample_queries[0]], memories=(heads[0],), mode="hybrid", limit=10)).hits
        }
        other = (await contexts.get(scope_ids[1])).artifacts.memory
        other_page = await other.search(queries[sample_queries[0]], memories=(heads[1],), mode="hybrid", limit=10)
        check("another scope returns none of this scope's hits", not (first_ids & {hit.entry_id for hit in other_page.hits}))

        print("\n5. current head: a stale head is rejected")
        stale_head = heads[0]
        advanced = await memory.remember(
            memory=stale_head,
            entries=(MemoryEntryInput(kind="document", text="A brand new fact for the head check."),),
            mode="append",
        )
        assert advanced is not None
        try:
            await memory.search(queries[sample_queries[0]], memories=(stale_head,), mode="hybrid", limit=10)
            check("stale head rejected", False, "no error raised")
        except CapabilityNotSupportedError:
            check("stale head rejected", True)
        except Exception as error:  # noqa: BLE001
            check("stale head rejected", False, f"{type(error).__name__}: {error}")

        print("\n6. incremental projection and state changes")
        probe_query = " ".join(re.findall(r"[A-Za-z]+", texts[documents[0]])[:6])
        print(f"  probe query: {probe_query}")
        target = next(
            entry for entry in await memory.entries(advanced) if entry.text.startswith(texts[documents[0]][:40])
        )
        unchanged = next(entry for entry in await memory.entries(advanced) if entry.entry_id != target.entry_id)
        revised = await memory.remember(
            memory=advanced,
            entries=(MemoryEntryInput(kind="document", text=texts[documents[0]] + " revised", entry=target),),
            mode="append",
        )
        assert revised is not None
        page = await memory.search(probe_query, memories=(revised,), mode="hybrid", limit=10)
        hit_ids = {hit.entry_id for hit in page.hits}
        check("unmodified entry stays retrievable", unchanged.entry_id in hit_ids)
        check("returned reference is the current head", all(hit.memory_ref == revised.as_ref() for hit in page.hits))
        current = next(entry for entry in await memory.entries(revised) if entry.entry_id == target.entry_id)
        check("revision returns the new entry version", current.entry_version_id != target.entry_version_id)
        check("revision returns the new text", any(hit.text.endswith(" revised") for hit in page.hits))
        inactive = await memory.forget(revised, entries=(current,))
        page = await memory.search(probe_query, memories=(inactive,), mode="hybrid", limit=10)
        check("deactivated entry leaves the search", target.entry_id not in {hit.entry_id for hit in page.hits})
        restored = await memory.reactivate(inactive, entries=(current,))
        page = await memory.search(probe_query, memories=(restored,), mode="hybrid", limit=10)
        check("reactivated entry returns to the search", target.entry_id in {hit.entry_id for hit in page.hits})
        check(
            "reactivated entry keeps its entry version",
            any(hit.entry_version_id == current.entry_version_id for hit in page.hits),
        )
        check("reactivated entry uses the restored head", all(hit.memory_ref == restored.as_ref() for hit in page.hits))

        print("\n7. tag filter applies inside the database")
        tagged_entry = next(entry for entry in await memory.entries(restored) if entry.entry_id != target.entry_id)
        tag_target = MemoryEntryTagTarget(artifact_id=restored.artifact_id, entry_id=tagged_entry.entry_id)
        empty = await contexts.records.get_tags(scope_ids[0], tag_target)
        await contexts.records.replace_tags(scope_ids[0], tag_target, ("selected",), expected_etag=empty.etag)
        page = await memory.search(
            probe_query,
            memories=(restored,),
            mode="hybrid",
            limit=10,
            tag_filter=TagFilter(tags=("selected",)),
        )
        check(
            "tag filter returns only the tagged entry",
            all(hit.entry_id == tagged_entry.entry_id for hit in page.hits) and len(page.hits) > 0,
            f"{[hit.entry_id for hit in page.hits]} vs {tagged_entry.entry_id}",
        )

    print()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {FAILURES}")
    else:
        print("all simulated functional gates pass")


if __name__ == "__main__":
    asyncio.run(main())
