from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import (
    EmbeddingProfile,
    Memory,
    MemoryEntryInput,
    MemorySearchRequest,
    MemoryService,
)
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.artifacts import ArtifactRepository
from powercontext.builtin.persistence.memory import RelationalMemoryBackend
from powercontext.builtin.persistence.memory_index import CompositeMemoryIndex
from powercontext.builtin.persistence.oceanbase.memory_index import OceanBaseMemoryFTSIndex, OceanBaseMemoryVectorIndex
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

pytest.importorskip("pylibseekdb")

PROFILE = EmbeddingProfile(
    profile_id="hybrid-filter-regression", model="test", dimension=3, distance="l2", normalization="unit"
)


class _Embedding:
    profile = PROFILE

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple((1.0, 0.0, 0.0) for _ in texts))


@pytest.mark.asyncio
async def test_native_hybrid_filters_each_channel_before_limit_and_preserves_tied_order(tmp_path: Path) -> None:
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=tmp_path / "db")), embedding_model=_Embedding()
    ) as contexts:
        memory = (await contexts.get("wanted")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(MemoryEntryInput(kind="fact", text=f"needle equal text number {i}") for i in range(6)),
            mode="append",
        )
        assert head is not None
        index = CompositeMemoryIndex(OceanBaseMemoryFTSIndex(), OceanBaseMemoryVectorIndex(PROFILE))
        alternate_memory = MemoryService(
            backend=RelationalMemoryBackend(
                database=contexts.database, scope_id="wanted", artifacts=ArtifactRepository((Memory,)), index=index
            ),
            embedding_model=_Embedding(),
        )
        await alternate_memory.remember(
            memory=None, entries=(MemoryEntryInput(kind="fact", text="needle artifact decoy"),), mode="append"
        )
        other = (await contexts.get("unwanted")).artifacts.memory
        await other.remember(
            memory=None, entries=(MemoryEntryInput(kind="fact", text="needle scope decoy"),), mode="append"
        )
        entries = sorted(head.content.manifest.entries, key=lambda entry: entry.entry_id)
        for entry, tags in ((entries[-2], ("chosen",)), (entries[-1], ("chosen", "both"))):
            target = MemoryEntryTagTarget(artifact_id=head.artifact_id, entry_id=entry.entry_id)
            current = await contexts.records.get_tags("wanted", target)
            await contexts.records.replace_tags("wanted", target, tags, expected_etag=current.etag)
        statements = []

        def record(_connection, _cursor, statement, parameters, _context, _executemany):
            if "AGAINST" in statement.upper() or "l2_distance" in statement.lower():
                statements.append((statement, parameters))

        for tag_filter, allowed in (
            (None, {entry.entry_id for entry in entries}),
            (TagFilter(tags=("chosen", "both"), match="any"), {entries[-2].entry_id, entries[-1].entry_id}),
            (TagFilter(tags=("chosen", "both"), match="all"), {entries[-1].entry_id}),
            (TagFilter(tags=("absent",)), set()),
        ):
            request = MemorySearchRequest(
                query="needle",
                analyzed_query="needle",
                memories=(head.as_ref(),),
                candidate_limit=2,
                mode="hybrid",
                query_vector=(1.0, 0.0, 0.0),
                embedding_profile=PROFILE,
                tag_filter=tag_filter,
            )
            statements.clear()
            event.listen(Engine, "before_cursor_execute", record)
            try:
                async with contexts.database.transaction() as connection:
                    result = await index.search(connection, "wanted", request)
            finally:
                event.remove(Engine, "before_cursor_execute", record)
            assert len(statements) == 1
            for channel in (result.fts, result.vector):
                assert len(channel) == min(2, len(allowed))
                assert all(hit.entry_id in allowed and hit.memory_ref == head.as_ref() for hit in channel)
                assert len({hit.entry_id for hit in channel}) == len(channel)
            async with contexts.database.transaction() as connection:
                repeated = await index.search(connection, "wanted", request)
                assert repeated == result
                statement, parameters = statements[0]
                plan = "\n".join(
                    str(row[0]) for row in (await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
                )
            assert "TEXT RETRIEVAL SCAN" in plan
            assert "VECTOR INDEX" in plan
