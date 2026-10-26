"""Event-loop-local embedding sharing with bounded batches and successful LRU."""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(frozen=True, eq=False, slots=True)
class _BatchUsage:
    usage: InferenceUsage


_SharedResult = tuple[EmbeddingVector, _BatchUsage]


def _consume_failure(future: asyncio.Future[_SharedResult]) -> None:
    # All waiters may cancel before a failed provider finishes its shared work.
    if not future.cancelled():
        future.exception()


def _token_sum(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


class CoalescingEmbeddingModel:
    """Share in-flight text work without letting one caller cancel another."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size <= 0:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")  # noqa: TRY003
        if type(coalesce_ms) not in (int, float) or not math.isfinite(coalesce_ms) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be a finite non-negative number")  # noqa: TRY003
        self.profile = model.profile
        self._model = model
        self._batch_size = max_batch_size
        self._delay = coalesce_ms / 1000
        self._capacity = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._pending: dict[str, asyncio.Future[_SharedResult]] = {}
        self._queued: list[str] = []
        self._drain_task: asyncio.Task[None] | None = None
        self._workers: set[asyncio.Task[None]] = set()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Restore each caller's original order and charge each awaited batch once."""
        resolved: dict[str, EmbeddingVector] = {}
        waiting: dict[str, asyncio.Future[_SharedResult]] = {}
        loop = asyncio.get_running_loop()
        for text in dict.fromkeys(texts):
            if text in self._cache:
                resolved[text] = self._cache[text]
                self._cache.move_to_end(text)
                continue
            future = self._pending.get(text)
            if future is None:
                future = loop.create_future()
                future.add_done_callback(_consume_failure)
                self._pending[text] = future
                self._queued.append(text)
            waiting[text] = future
        if self._queued and self._drain_task is None:
            self._drain_task = asyncio.create_task(self._drain())
        results = await asyncio.gather(*(asyncio.shield(future) for future in waiting.values()))
        batches: set[_BatchUsage] = set()
        for text, (vector, batch) in zip(waiting, results, strict=True):
            resolved[text] = vector
            batches.add(batch)
        usage = InferenceUsage(
            requests=sum(batch.usage.requests for batch in batches),
            input_tokens=_token_sum([batch.usage.input_tokens for batch in batches]),
            output_tokens=_token_sum([batch.usage.output_tokens for batch in batches]),
        )
        return EmbeddingResult(vectors=tuple(resolved[text] for text in texts), usage=usage)

    async def _drain(self) -> None:
        await asyncio.sleep(self._delay)
        queued, self._queued = self._queued, []
        self._drain_task = None
        for offset in range(0, len(queued), self._batch_size):
            texts = tuple(queued[offset : offset + self._batch_size])
            worker = asyncio.create_task(self._complete_batch(texts))
            self._workers.add(worker)
            worker.add_done_callback(self._workers.discard)

    async def _complete_batch(self, texts: tuple[str, ...]) -> None:
        futures = [self._pending[text] for text in texts]
        try:
            result = await self._model.embed(texts)
            if len(result.vectors) != len(texts):
                raise ValueError("provider vector count differs from the requested batch")  # noqa: TRY003, TRY301
        except asyncio.CancelledError:
            for future in futures:
                future.cancel()
            raise
        except Exception as error:
            for future in futures:
                future.set_exception(error)
        else:
            batch = _BatchUsage(result.usage)
            for text, vector, future in zip(texts, result.vectors, futures, strict=True):
                self._cache_vector(text, vector)
                future.set_result((vector, batch))
        finally:
            for text in texts:
                del self._pending[text]

    def _cache_vector(self, text: str, vector: EmbeddingVector) -> None:
        if self._capacity:
            self._cache[text] = vector
            self._cache.move_to_end(text)
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)
