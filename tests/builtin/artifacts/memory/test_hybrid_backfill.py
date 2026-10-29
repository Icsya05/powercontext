from __future__ import annotations

import asyncio
import math
from typing import cast

import pytest

from powercontext import ArtifactRef
from powercontext.builtin.artifacts.memory import (
    EmbeddingProfile,
    Memory,
    MemoryBackend,
    MemoryCapabilities,
    MemoryChannelHit,
    MemoryContent,
    MemoryManifest,
    MemoryRerankDecision,
    MemorySearchChannels,
    MemoryService,
)
from powercontext.builtin.artifacts.memory.fusion import fuse_rankings
from powercontext.builtin.artifacts.search import AdmissionFloor
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage

_PROFILE = EmbeddingProfile(profile_id="backfill-unit", model="test", dimension=3)
_REF = ArtifactRef(family="memory", artifact_id="memory", revision=1)


def _candidate(entry_id: str, *, distance: float | None = None) -> MemoryChannelHit:
    return MemoryChannelHit(
        memory_ref=_REF,
        entry_id=entry_id,
        entry_version_id=f"version-{entry_id}",
        text="quartz lexical fact" if entry_id == "lexical" else f"distinct {entry_id} observation",
        distance=distance,
    )


class _Embedding:
    profile = _PROFILE

    async def embed(self, texts, /):
        return EmbeddingResult(vectors=tuple((1.0, 0.0, 0.0) for _ in texts))


class _Backend:
    def __init__(self, *, opt_in: bool) -> None:
        self.memory = Memory(
            artifact_id="memory", revision=1, content=MemoryContent(manifest=MemoryManifest(entries=()))
        )
        self.channels = MemorySearchChannels(
            fts=(_candidate("lexical"),),
            vector=(
                _candidate("semantic", distance=math.sqrt(2 * (1 - 0.29))),
                _candidate("zero", distance=math.sqrt(2)),
            ),
            allow_vector_backfill=opt_in,
        )
        self.requests = []

    async def capabilities(self):
        return MemoryCapabilities(fts=True, vector=True, hybrid=True, embedding_profile=_PROFILE)

    async def get(self, _ref):
        return self.memory

    async def latest(self, _artifact_id):
        return self.memory

    async def vector_complete(self, _memories, _profile):
        return True

    async def search(self, request, /):
        self.requests.append(request)
        return self.channels


class _Reranker:
    policy_id = "preserve-historical"

    async def rerank(self, _query, candidates, _limit, /):
        assert tuple(hit.entry_id for hit in candidates) == ("lexical",)
        return MemoryRerankDecision(selected_ranks=(1,), usage=InferenceUsage(requests=1))


def test_opted_in_hybrid_appends_positive_semantic_match_without_moving_historical_hit() -> None:
    async def scenario():
        backend = _Backend(opt_in=True)
        service = MemoryService(backend=cast(MemoryBackend, backend), embedding_model=_Embedding())
        result = await service.search("quartz", memories=(backend.memory,), limit=3, mode="hybrid")
        historical = fuse_rankings(fts=backend.channels.fts, vector=(), limit=3)
        assert tuple(hit.entry_id for hit in result.hits) == ("lexical", "semantic")
        assert result.hits[:1] == historical
        assert result.hits[1].matched_by == ("vector",)
        assert 0 < result.hits[1].score <= result.hits[0].score
        assert result.admission is not None
        assert (result.admission.retrieved, result.admission.admitted) == (3, 2)
        assert len(backend.requests) == 1
        assert "allow_vector_backfill" not in backend.channels.model_dump()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("opt_in", "mode", "admission", "reranker", "limit", "expected"),
    [
        (False, "hybrid", None, None, 3, ("lexical",)),
        (True, "hybrid", AdmissionFloor(), None, 3, ("lexical",)),
        (True, "fts", None, None, 3, ("lexical",)),
        (True, "vector", None, None, 3, ()),
        (True, "hybrid", None, _Reranker(), 3, ("lexical",)),
        (True, "hybrid", None, None, 1, ("lexical",)),
    ],
)
def test_hybrid_backfill_respects_explicit_policies_and_legacy_paths(
    opt_in, mode, admission, reranker, limit, expected
):
    async def scenario():
        backend = _Backend(opt_in=opt_in)
        service = MemoryService(backend=cast(MemoryBackend, backend), embedding_model=_Embedding(), reranker=reranker)
        result = await service.search("quartz", memories=(backend.memory,), limit=limit, mode=mode, admission=admission)
        assert tuple(hit.entry_id for hit in result.hits) == expected

    asyncio.run(scenario())


def test_vector_backfill_preserves_prefix_scores_labels_and_unique_order() -> None:
    from powercontext.builtin.artifacts.memory.fusion import append_vector_backfill

    prefix = (fuse_rankings(fts=(_candidate("lexical"),), vector=(), limit=1)[0].model_copy(update={"score": 0.001}),)
    semantic = _candidate("semantic", distance=math.sqrt(2 * (1 - 0.29)))
    weak = _candidate("weak", distance=math.sqrt(2 * (1 - 0.1)))
    result = append_vector_backfill(
        hits=prefix, vector=(_candidate("lexical", distance=0.5), semantic, semantic, weak), limit=3
    )
    assert result[:1] == prefix
    assert tuple(hit.entry_id for hit in result) == ("lexical", "semantic", "weak")
    assert tuple(hit.score for hit in result) == (0.001, 0.001, 0.001)
    assert tuple(hit.matched_by for hit in result) == (("fts",), ("vector",), ("vector",))
    assert append_vector_backfill(hits=result, vector=(weak,), limit=3) == result


def test_vector_backfill_handles_empty_prefix_and_rejects_invalid_or_nonpositive_neighbors() -> None:
    from powercontext.builtin.artifacts.memory.fusion import append_vector_backfill

    valid = _candidate("semantic", distance=math.sqrt(2 * (1 - 0.29)))
    invalid = tuple(
        _candidate(str(index)).model_copy(update={"distance": value})
        for index, value in enumerate((None, -1.0, float("nan"), float("inf"), 1e308, math.sqrt(2), 2.0))
    )
    result = append_vector_backfill(hits=(), vector=(*invalid, valid), limit=3)
    assert tuple(hit.entry_id for hit in result) == ("semantic",)
    assert result[0].score == pytest.approx(1 / 68)
    with pytest.raises(ValueError, match="positive"):
        append_vector_backfill(hits=(), vector=(valid,), limit=0)


def test_legacy_channels_keep_default_and_explicit_admission_equivalent() -> None:
    async def scenario():
        backend = _Backend(opt_in=False)
        backend.channels = MemorySearchChannels(fts=backend.channels.fts, vector=backend.channels.vector)
        assert not backend.channels.allow_vector_backfill
        service = MemoryService(backend=cast(MemoryBackend, backend), embedding_model=_Embedding())
        implicit = await service.search("quartz", memories=(backend.memory,), mode="hybrid")
        explicit = await service.search("quartz", memories=(backend.memory,), mode="hybrid", admission=AdmissionFloor())
        assert implicit.hits == explicit.hits
        assert implicit.admission == explicit.admission

    asyncio.run(scenario())


def test_vector_backfill_preserves_complete_mixed_channel_prefix() -> None:
    from powercontext.builtin.artifacts.memory.fusion import append_vector_backfill

    dual = _candidate("dual", distance=0.5)
    vector_only = _candidate("vector-only", distance=0.9)
    fts_only = _candidate("fts-only")
    semantic = _candidate("semantic", distance=math.sqrt(2 * (1 - 0.29)))
    prefix = fuse_rankings(fts=(dual, fts_only), vector=(dual, vector_only), limit=5)
    assert tuple(hit.matched_by for hit in prefix) == (("fts", "vector"), ("fts",), ("vector",))

    result = append_vector_backfill(hits=prefix, vector=(dual, vector_only, semantic), limit=5)

    assert result[: len(prefix)] == prefix
    assert tuple(
        (hit.memory_ref, hit.entry_id, hit.entry_version_id, hit.score, hit.matched_by) for hit in result[:3]
    ) == (
        (_REF, "dual", "version-dual", 2 / 61, ("fts", "vector")),
        (_REF, "fts-only", "version-fts-only", 1 / 62, ("fts",)),
        (_REF, "vector-only", "version-vector-only", 1 / 62, ("vector",)),
    )
    assert result[3].entry_id == "semantic"
    assert result[3].score <= prefix[-1].score
    assert result[3].matched_by == ("vector",)
    assert len(result) == 4
