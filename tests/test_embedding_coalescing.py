"""Cross-call sharing must survive late arrival and independent failures."""

import asyncio

import pytest

from powercontext.builtin.artifacts.memory import EmbeddingProfile
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel


def test_late_waiter_shares_inflight_work_with_cache_disabled() -> None:
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        class Base:
            profile = EmbeddingProfile(profile_id="late", model="local", dimension=1)

            async def embed(self, texts):
                calls.append(texts)
                started.set()
                await release.wait()
                return EmbeddingResult(vectors=((2.0,),), usage=InferenceUsage(requests=1, input_tokens=7))

        model = CoalescingEmbeddingModel(Base(), cache_size=0, coalesce_ms=0)
        first = asyncio.create_task(model.embed(("same",)))
        await started.wait()
        late = asyncio.create_task(model.embed(("same", "same")))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        result = await late
        assert result.vectors == ((2.0,), (2.0,))
        assert result.usage.input_tokens == 7
        assert calls == [("same",)]

    asyncio.run(run())


def test_failed_batch_does_not_poison_independent_work_or_retry() -> None:
    async def run():
        calls = []

        class Base:
            profile = EmbeddingProfile(profile_id="partial", model="local", dimension=1)

            async def embed(self, texts):
                calls.append(texts)
                if texts == ("bad",) and calls.count(texts) == 1:
                    raise RuntimeError("failed batch")  # noqa: TRY003
                return EmbeddingResult(vectors=tuple((1.0,) for _ in texts), usage=InferenceUsage(requests=1))

        model = CoalescingEmbeddingModel(Base(), max_batch_size=1, coalesce_ms=0)
        bad, good = await asyncio.gather(model.embed(("bad",)), model.embed(("good",)), return_exceptions=True)
        assert isinstance(bad, RuntimeError)
        assert good.vectors == ((1.0,),)
        assert (await model.embed(("good", "bad", "good"))).vectors == ((1.0,), (1.0,), (1.0,))
        assert calls.count(("good",)) == 1
        assert calls.count(("bad",)) == 2

    asyncio.run(run())
