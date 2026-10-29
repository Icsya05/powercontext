from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

pytest.importorskip("pylibseekdb")

_PROFILE = EmbeddingProfile(
    profile_id="sparse-tagged-hybrid", model="synthetic", dimension=384, distance="l2", normalization="unit"
)


class _Embedding:
    profile = _PROFILE

    @staticmethod
    def _vector(seed: int) -> tuple[float, ...]:
        randomizer = random.Random(seed)  # noqa: S311 - deterministic synthetic vectors
        vector = [randomizer.uniform(-0.06, 0.06) for _ in range(384)]
        vector[0] = 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return tuple(value / norm for value in vector)

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(self._vector(int(re.search(r"item(\d+)", text)[1])) for text in texts))

    async def embed_query(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(self._vector(100000 + sum(text.encode())) for text in texts))


@pytest.mark.asyncio
async def test_hybrid_returns_sparse_tagged_semantic_matches(short_tmp_path: Path) -> None:
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=short_tmp_path / "db")), embedding_model=_Embedding()
    ) as contexts:
        memory = (await contexts.get("wanted")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(
                MemoryEntryInput(kind="fact", text=f"item{index:04d} broad scientific observation")
                for index in range(173)
            ),
            mode="append",
        )
        assert head is not None
        expected = {f"item{index:04d} broad scientific observation" for index in (140, 151, 160, 170)}
        for entry in await memory.entries(head):
            if entry.text in expected:
                target = MemoryEntryTagTarget(artifact_id=head.artifact_id, entry_id=entry.entry_id)
                current = await contexts.records.get_tags("wanted", target)
                await contexts.records.replace_tags("wanted", target, ("chosen",), expected_etag=current.etag)

        statements = []

        def record(_connection, _cursor, statement, parameters, _context, _executemany):
            if "AGAINST" in statement.upper() or "l2_distance" in statement.lower():
                statements.append((statement, parameters))

        event.listen(Engine, "before_cursor_execute", record)
        try:
            result = await memory.search(
                "unseenword", memories=(head,), mode="hybrid", limit=10, tag_filter=TagFilter(tags=("chosen",))
            )
        finally:
            event.remove(Engine, "before_cursor_execute", record)
        assert {hit.text for hit in result.hits} == expected
        assert all(hit.memory_ref == head.as_ref() and hit.matched_by == ("vector",) for hit in result.hits)
        assert len(statements) == 1
        async with contexts.database.transaction() as connection:
            statement, parameters = statements[0]
            plan = "\n".join(
                str(row[0]) for row in (await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
            )
        assert "TEXT RETRIEVAL SCAN" in plan
        assert "VECTOR INDEX" in plan


class _UnderfillEmbedding:
    profile = EmbeddingProfile(profile_id="native-underfill", model="test", dimension=3)

    async def embed(self, texts, /):
        return EmbeddingResult(
            vectors=tuple(
                (1.0, 0.0, 0.0)
                if text == "quartz"
                else (-1.0, 0.0, 0.0)
                if "quartz" in text
                else (0.29, math.sqrt(1 - 0.29**2), 0.0)
                for text in texts
            )
        )


@pytest.mark.asyncio
async def test_native_hybrid_backfills_available_semantic_hit_after_historical_prefix(short_tmp_path: Path) -> None:
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=short_tmp_path / "db")), embedding_model=_UnderfillEmbedding()
    ) as contexts:
        memory = (await contexts.get("underfill")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=(
                MemoryEntryInput(kind="fact", text="quartz lexical fact"),
                MemoryEntryInput(kind="fact", text="distinct semantic observation"),
            ),
            mode="append",
        )
        assert head is not None
        statements = []

        def record(_connection, _cursor, statement, parameters, _context, _executemany):
            if "AGAINST" in statement.upper() or "l2_distance" in statement.lower():
                statements.append((statement, parameters))

        event.listen(Engine, "before_cursor_execute", record)
        try:
            result = await memory.search("quartz", memories=(head,), mode="hybrid", limit=3)
        finally:
            event.remove(Engine, "before_cursor_execute", record)
        assert [hit.text for hit in result.hits] == ["quartz lexical fact", "distinct semantic observation"]
        assert [hit.matched_by for hit in result.hits] == [("fts",), ("vector",)]
        assert len(statements) == 1
        async with contexts.database.transaction() as connection:
            statement, parameters = statements[0]
            plan = "\n".join(
                str(row[0]) for row in (await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
            )
        assert "TEXT RETRIEVAL SCAN" in plan
        assert "VECTOR INDEX" in plan
