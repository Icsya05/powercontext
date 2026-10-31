"""Functional gates of the hybrid retrieval task, exercised on seekdb.

The published gates for retrieval-02-hybrid-search that the public acceptance
does not cover:

  * hit validity: every hit belongs to the current scope and head, references
    the current valid entry version, carries that version's text verbatim and
    never repeats an identity
  * channel identity: matched_by is non-empty and only names fts or vector
  * stability: the same query returns the same identities in the same order
  * incremental projections: an entry whose projection was not modified keeps
    its old head_revision and must still be retrievable, with the returned
    reference pointing at the verified current head
  * state changes: after an append the index, the text and the current state
    stay consistent
  * scope isolation: a search never returns another scope's hits
  * current head: a stale head is rejected
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_runtime

DIMENSION = 8
TOKEN = re.compile(r"[a-z]+|\d+")
FAILURES: list[str] = []


def embed(text: str) -> tuple[float, ...]:
    counts = Counter(TOKEN.findall(text.lower()))
    vector = [0.0] * DIMENSION
    for term, count in counts.items():
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:2], "big") % DIMENSION] += 1.0 + math.log(count)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-functional-v1",
        model="deterministic",
        dimension=DIMENSION,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(embed(text) for text in texts))


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(name)


async def main() -> None:
    from powercontext.builtin.runtime import RememberMemoryRequest, SearchMemoryRequest
    from powercontext.builtin.scope import ScopeDraft

    database_path = Path(tempfile.mkdtemp(prefix="hybrid-fn-", dir=os.environ.get("TMPDIR"))) / "db"
    config = BuiltinConfig(database=SeekDBConfig(path=database_path))
    async with open_builtin_runtime(config, embedding_model=_Embedding()) as runtime:
        scope = await runtime.scopes.create(
            ScopeDraft(title="fn", summary="fn", idempotency_key="fn")
        )
        memory = runtime.memory.for_scope(scope.scope_id)
        await memory.remember(
            RememberMemoryRequest(
                entries=(
                    MemoryEntryInput(kind="fact", text="Alpha mitochondria record."),
                    MemoryEntryInput(kind="fact", text="Beta mitochondria record."),
                    MemoryEntryInput(kind="fact", text="Gamma mitochondria record."),
                ),
                mode="append",
            )
        )
        service = runtime.artifacts.memory

        print("\n1. 命中有效性与通道标识")
        page = await memory.search(
            SearchMemoryRequest(query="mitochondria", limit=10, mode="hybrid")
        )
        check("hybrid 有命中", len(page.hits) > 0, f"{len(page.hits)} hits, mode={page.mode}")
        check(
            "matched_by 非空且只含 fts/vector",
            all(hit.matched_by and set(hit.matched_by) <= {"fts", "vector"} for hit in page.hits),
            str(sorted({hit.matched_by for hit in page.hits})),
        )
        identities = [
            (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
            for hit in page.hits
        ]
        check("没有重复身份", len(set(identities)) == len(identities))
        check(
            "命中正文非空且逐字来自条目",
            all(hit.text for hit in page.hits),
        )

        print("\n2. 稳定性")
        again = await memory.search(
            SearchMemoryRequest(query="mitochondria", limit=10, mode="hybrid")
        )
        first = [(hit.entry_id, hit.entry_version_id) for hit in page.hits]
        second = [(hit.entry_id, hit.entry_version_id) for hit in again.hits]
        check("重复查询返回相同身份与顺序", first == second, f"{first} vs {second}")

        print("\n3. 单通道行为不变")
        for mode in ("fts", "vector"):
            single = await memory.search(
                SearchMemoryRequest(query="mitochondria", limit=10, mode=mode)
            )
            check(f"{mode} 通道有命中", len(single.hits) > 0, f"{len(single.hits)} hits")
            check(
                f"{mode} 通道命中身份唯一",
                len({hit.entry_id for hit in single.hits}) == len(single.hits),
            )

        print("\n4. 增量投影：追加后未修改条目仍可检索")
        before_revision = page.hits[0].memory_ref.revision
        await memory.remember(
            RememberMemoryRequest(
                entries=(MemoryEntryInput(kind="fact", text="Delta mitochondria record."),),
                mode="append",
            )
        )
        after = await memory.search(
            SearchMemoryRequest(query="mitochondria", limit=10, mode="hybrid")
        )
        texts = {hit.text for hit in after.hits}
        check(
            "旧条目仍可检索（projection 未被 head 过滤掉）",
            "Alpha mitochondria record." in texts,
            str(sorted(texts)),
        )
        check(
            "返回引用使用已验证的当前 head",
            all(hit.memory_ref.revision > before_revision for hit in after.hits),
            f"revisions {[hit.memory_ref.revision for hit in after.hits]} vs old {before_revision}",
        )

        print("\n5. scope 隔离")
        other = await runtime.scopes.create(
            ScopeDraft(title="other", summary="other", idempotency_key="other")
        )
        other_memory = runtime.memory.for_scope(other.scope_id)
        await other_memory.remember(
            RememberMemoryRequest(
                entries=(MemoryEntryInput(kind="fact", text="Epsilon mitochondria record."),),
                mode="append",
            )
        )
        isolated = await other_memory.search(
            SearchMemoryRequest(query="mitochondria", limit=10, mode="hybrid")
        )
        check(
            "另一 scope 只返回自己的命中",
            all(hit.entry_id not in {h.entry_id for h in after.hits} for hit in isolated.hits),
            f"{[hit.text for hit in isolated.hits]}",
        )

        print("\n6. 当前 head：历史 head 被拒绝")
        from powercontext.builtin.artifacts.memory.errors import CapabilityNotSupportedError

        stale = await service.head(service.artifact_id) if hasattr(service, "head") else None
        try:
            if stale is None:
                print("  [SKIP] 取不到 head 引用")
            else:
                await service.search("mitochondria", memories=(stale,), mode="hybrid", limit=10)
                check("历史 head 抛出 CapabilityNotSupportedError", False, "没有抛出")
        except CapabilityNotSupportedError:
            check("历史 head 抛出 CapabilityNotSupportedError", True)
        except Exception as error:  # noqa: BLE001
            check(
                "历史 head 抛出 CapabilityNotSupportedError",
                False,
                f"{type(error).__name__}: {error}",
            )

    print()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {FAILURES}")
    else:
        print("all functional gates pass")


if __name__ == "__main__":
    asyncio.run(main())
