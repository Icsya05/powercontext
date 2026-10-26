"""Protect strict identities and errors at the HTTP scoring boundary."""

import asyncio

import httpx
import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory.http_reranker import HTTPMemoryReranker
from powercontext.builtin.artifacts.memory.models import MemoryHit


def _candidate() -> MemoryHit:
    return MemoryHit(
        memory_ref=ArtifactRef(family="memory", artifact_id="m", revision=1),
        entry_id="e",
        entry_version_id="v",
        text="Evidence",
        score=1.0,
        matched_by=("fts",),
    )


@pytest.mark.parametrize(
    "record",
    [
        {"rank": True, "score": 0.5},
        {"rank": "1", "score": 0.5},
        {"rank": 1.0, "score": 0.5},
        {"rank": 1, "score": True},
        {"rank": 1, "score": "0.5"},
        {"rank": 1, "score": None},
    ],
)
def test_response_never_coerces_identity_or_score(record) -> None:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"scores": [record]}))
        ) as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://score.invalid", client=client).rerank("q", (_candidate(),), 1)

    asyncio.run(run())


@pytest.mark.parametrize("value", [True, 1.5, "1", 0, -1])
def test_invalid_batch_size_fails_without_requests(value) -> None:
    async def run():
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                HTTPMemoryReranker("https://score.invalid", client=client, batch_size=value)

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 400, 429, 503])
def test_status_failures_remain_httpx_errors(status) -> None:
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await HTTPMemoryReranker("https://score.invalid", client=client).rerank("q", (_candidate(),), 1)

    asyncio.run(run())


def test_cross_batch_rank_cannot_satisfy_current_batch() -> None:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"scores": [{"rank": 2, "score": 1}]}))
        ) as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://score.invalid", client=client, batch_size=1).rerank(
                    "q", (_candidate(), _candidate()), 1
                )

    asyncio.run(run())


def test_distinct_large_integer_scores_are_not_rounded_into_a_tie() -> None:
    async def run():
        payload = {"scores": [{"rank": 1, "score": 2**60}, {"rank": 2, "score": 2**60 + 1}]}
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client:
            result = await HTTPMemoryReranker("https://score.invalid", client=client).rerank(
                "q", (_candidate(), _candidate()), 1
            )
            assert result.selected_ranks == (2,)

    asyncio.run(run())
