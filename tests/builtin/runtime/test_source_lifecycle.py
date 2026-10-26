"""Durable lifecycle repair and registration contracts through the runtime."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.artifacts.memory.service import MemoryService
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    CaptureSource,
    GetMemoryEntryRequest,
    RememberMemoryRequest,
    ReviseMemoryEntryRequest,
    open_builtin_runtime,
)
from powercontext.builtin.runtime.source_lifecycle import SourceLifecycleError, SourceLifecycleEvent
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import SourceRef


def observation(sequence: int, available: bool) -> SourceLifecycleEvent:
    return SourceLifecycleEvent(node_id="source", revision=3, sequence=sequence, available=available, reason="test")


@pytest.mark.parametrize("restoring", [False, True])
def test_interrupted_native_writes_repair_after_restart_without_duplicate_revisions(tmp_path, monkeypatch, restoring):
    async def run():
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'repair.db'}"))
        async with open_builtin_runtime(config) as runtime:
            scope = (
                await runtime.scopes.create(
                    ScopeDraft(title="Repair", summary="Durable repair", idempotency_key="repair")
                )
            ).scope_id
            service = runtime.lifecycle.for_scope(scope)
            source = await runtime.sources.for_scope(scope).capture(
                CaptureSource(source_id="s", content="evidence", metadata={})
            )
            await service.register_source("source", source.source_ref, revision=3)
            citations = []
            for number in range(3):
                result = await runtime.memory.for_scope(scope).remember(
                    RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text=f"repair fact {number}"),))
                )
                citations.append(result.entry.citation)
                await service.register_memory(
                    f"memory-{number}", result.entry.citation, parents=("source",), policy="all"
                )
            if restoring:
                await service.apply(observation(1, False))
            method = "reactivate" if restoring else "forget"
            original = getattr(MemoryService, method)
            calls = 0

            async def interrupted(self, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    message = "interrupted native write"
                    raise OSError(message)
                return await original(self, *args, **kwargs)

            pending = observation(2 if restoring else 1, restoring)
            with monkeypatch.context() as patch:
                patch.setattr(MemoryService, method, interrupted)
                with pytest.raises(OSError, match="interrupted native write"):
                    await service.apply(pending)
            partial = await runtime.memory.for_scope(scope).list(include_inactive=True)
            assert {record.state for record in partial.entries} == {"active", "inactive"}
            partial_revision = partial.memory_ref.revision
        async with open_builtin_runtime(config) as runtime:
            service = runtime.lifecycle.for_scope(scope)
            assert await service.apply(pending) == (["memory-0", "memory-1", "memory-2", "source"] if restoring else [])
            repaired = await runtime.memory.for_scope(scope).list(include_inactive=True)
            assert {record.state for record in repaired.entries} == ({"active"} if restoring else {"inactive"})
            assert repaired.memory_ref.revision == partial_revision + 2
            assert await service.apply(pending) == (["memory-0", "memory-1", "memory-2", "source"] if restoring else [])
            assert (await runtime.memory.for_scope(scope).list(include_inactive=True)).memory_ref == repaired.memory_ref
            for number, citation in enumerate(citations):
                original_body = await runtime.memory.for_scope(scope).get(GetMemoryEntryRequest(citation=citation))
                assert original_body.entry.text == f"repair fact {number}"
                assert await service.resolve(f"memory-{number}", purpose="audit") == citation
                if restoring:
                    assert await service.resolve(f"memory-{number}", purpose="generation") == citation
                else:
                    with pytest.raises(SourceLifecycleError):
                        await service.resolve(f"memory-{number}", purpose="generation")

    asyncio.run(run())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("node_id", " "),
        ("reason", "\t"),
        ("sequence", True),
        ("revision", 1.0),
        ("sequence", "1"),
        ("available", 1),
        ("revision", 0),
        ("unknown", "extra"),
    ],
)
def test_event_rejects_non_contract_values(field, value):
    payload = observation(1, True).model_dump() | {field: value}
    with pytest.raises(ValidationError):
        SourceLifecycleEvent.model_validate(payload)


def test_failed_registration_does_not_reserve_identity_and_scopes_stay_independent(tmp_path):
    async def run():
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"))
        async with open_builtin_runtime(config) as runtime:
            scopes = []
            for number in range(2):
                scope = (
                    await runtime.scopes.create(
                        ScopeDraft(title="Identity", summary="Independent scopes", idempotency_key=str(number))
                    )
                ).scope_id
                scopes.append(scope)
                service = runtime.lifecycle.for_scope(scope)
                with pytest.raises(SourceLifecycleError):
                    await service.register_source(
                        "source", SourceRef(source_type="content", source_id="absent"), revision=3
                    )
                source = await runtime.sources.for_scope(scope).capture(
                    CaptureSource(source_id="s", content="evidence", metadata={})
                )
                await service.register_source("source", source.source_ref, revision=3)
                await service.register_source("source", source.source_ref, revision=3)
                with pytest.raises(SourceLifecycleError):
                    await service.register_source("source", source.source_ref, revision=4)
                result = await runtime.memory.for_scope(scope).remember(
                    RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text="isolated fact"),))
                )
                with pytest.raises(SourceLifecycleError):
                    await service.register_memory("memory", result.entry.citation, parents=("missing",), policy="all")
                await service.register_memory("memory", result.entry.citation, parents=("source",), policy="all")
            await runtime.lifecycle.for_scope(scopes[0]).apply(observation(1, False))
        async with open_builtin_runtime(config) as runtime:
            assert (await runtime.memory.for_scope(scopes[0]).list()).entries == ()
            assert len((await runtime.memory.for_scope(scopes[1]).list()).entries) == 1
            assert await runtime.lifecycle.for_scope(scopes[1]).apply(observation(1, True)) == ["memory", "source"]

    asyncio.run(run())


def test_unbindable_historical_body_does_not_poison_graph():
    async def run():
        async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
            scope = (
                await runtime.scopes.create(ScopeDraft(title="History", summary="Old body", idempotency_key="old"))
            ).scope_id
            service = runtime.lifecycle.for_scope(scope)
            source = await runtime.sources.for_scope(scope).capture(
                CaptureSource(source_id="s", content="evidence", metadata={})
            )
            await service.register_source("source", source.source_ref, revision=3)
            memory = runtime.memory.for_scope(scope)
            original = await memory.remember(
                RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text="original body"),))
            )
            revised = await memory.revise(
                ReviseMemoryEntryRequest(citation=original.entry.citation, kind="fact", text="revised body")
            )
            assert (
                await memory.get(GetMemoryEntryRequest(citation=original.entry.citation))
            ).entry.text == "original body"
            with pytest.raises(SourceLifecycleError):
                await service.register_memory("memory", original.entry.citation, parents=("source",), policy="all")
            # Rejection must leave the identity usable and the accepted Source graph healthy.
            with pytest.raises(SourceLifecycleError):
                await service.resolve("memory", purpose="audit")
            await service.register_memory("memory", revised.entry.citation, parents=("source",), policy="all")
            assert await service.apply(observation(1, False)) == []
            assert await service.resolve("memory", purpose="audit") == revised.entry.citation

    asyncio.run(run())


def test_long_event_reason_survives_native_projection_and_replay():
    async def run():
        async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
            scope = (
                await runtime.scopes.create(ScopeDraft(title="Reason", summary="Long reason", idempotency_key="reason"))
            ).scope_id
            service = runtime.lifecycle.for_scope(scope)
            source = await runtime.sources.for_scope(scope).capture(
                CaptureSource(source_id="s", content="evidence", metadata={})
            )
            await service.register_source("source", source.source_ref, revision=3)
            result = await runtime.memory.for_scope(scope).remember(
                RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text="reason fact"),))
            )
            await service.register_memory("memory", result.entry.citation, parents=("source",), policy="all")
            pending = SourceLifecycleEvent(
                node_id="source", revision=3, sequence=1, available=False, reason="原因" * 600
            )
            assert await service.apply(pending) == []
            before = (await runtime.memory.for_scope(scope).list(include_inactive=True)).memory_ref
            assert await service.apply(pending) == []
            assert (await runtime.memory.for_scope(scope).list(include_inactive=True)).memory_ref == before
            with pytest.raises(SourceLifecycleError):
                await service.apply(pending.model_copy(update={"reason": pending.reason[:512]}))
            assert (await runtime.memory.for_scope(scope).list()).entries == ()

    asyncio.run(run())
