"""HTTP scoring adapter with bounded batches and global stable selection."""

from __future__ import annotations

import math

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage


def _read_scores(payload: object, ranks: set[int]) -> dict[int, int | float]:
    if not isinstance(payload, dict) or set(payload) != {"scores"} or not isinstance(payload["scores"], list):
        raise ValueError("response must contain only a scores array")  # noqa: TRY003
    scores: dict[int, int | float] = {}
    for item in payload["scores"]:
        if not isinstance(item, dict) or set(item) != {"rank", "score"}:
            raise ValueError("score records must contain exactly rank and score")  # noqa: TRY003
        rank, score = item["rank"], item["score"]
        if type(rank) is not int or rank not in ranks or rank in scores:
            raise ValueError("response ranks must cover the current batch exactly once")  # noqa: TRY003
        if type(score) not in (int, float):
            raise ValueError("scores must be finite numbers")  # noqa: TRY003
        if isinstance(score, float) and not math.isfinite(score):
            raise ValueError("scores must be finite numbers")  # noqa: TRY003
        scores[rank] = score
    if set(scores) != ranks:
        raise ValueError("response is missing batch ranks")  # noqa: TRY003
    return scores


class HTTPMemoryReranker:
    """Select original candidate ranks using a caller-owned HTTP client."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")  # noqa: TRY003
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size
        self.policy_id = policy_id

    async def rerank(self, query: str, candidates: tuple[MemoryHit, ...], limit: int, /) -> MemoryRerankDecision:
        if not candidates or type(limit) is not int or not 1 <= limit <= len(candidates):
            raise ValueError("limit must select between one and all candidates")  # noqa: TRY003
        scores: dict[int, int | float] = {}
        request_count = 0
        for start in range(0, len(candidates), self._batch_size):
            batch = candidates[start : start + self._batch_size]
            records = [{"rank": start + index, "text": candidate.text} for index, candidate in enumerate(batch, 1)]
            response = await self._client.post(self._endpoint, json={"query": query, "candidates": records})
            request_count += 1
            response.raise_for_status()
            scores.update(_read_scores(response.json(), set(range(start + 1, start + len(batch) + 1))))
        selected = sorted(scores, key=lambda rank: (-scores[rank], rank))[:limit]
        return MemoryRerankDecision(selected_ranks=tuple(selected), usage=InferenceUsage(requests=request_count))
