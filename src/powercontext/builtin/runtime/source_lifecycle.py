"""Durable eligibility for explicitly registered Source dependency graphs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy import insert, select, update

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE as NODES
from powercontext.builtin.sources import validate_scope_id
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import BuiltinRuntime


class SourceLifecycleError(ValueError):
    """Invalid lifecycle registration, event, or resolution request."""

    def __init__(self, code: str) -> None:
        messages = {
            "database": "lifecycle requires a relational database",
            "source": "invalid Source registration",
            "memory": "invalid Memory citation",
            "topic": "invalid Topic reference",
            "policy": "invalid dependency policy or parents",
            "parents": "invalid parents",
            "named-parents": "derived nodes require named parents",
            "cycle": "duplicate or cyclic dependency",
            "node-id": "invalid node id",
            "binding": "node id already bound",
            "missing-parent": "parent must already be registered",
            "reference": "registered reference must exist and be readable",
            "event-type": "expected SourceLifecycleEvent",
            "revision": "unknown Source or lifecycle revision mismatch",
            "sequence": "event sequence is stale or conflicts",
            "persisted-cycle": "cyclic persisted dependencies",
            "body-changed": "registered Memory body changed",
            "purpose": "unknown resolution purpose",
            "unavailable": "unknown or unavailable node",
        }
        super().__init__(messages.get(code, code))


class SourceLifecycleEvent(BaseModel):
    """One ordered availability observation for a registered Source version."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    node_id: str
    revision: StrictInt = Field(gt=0)
    sequence: StrictInt = Field(gt=0)
    available: StrictBool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")  # noqa: TRY003
        return value


class _Binding(BaseModel):
    kind: Literal["source", "memory", "topic"]
    reference: SourceRef | MemoryCitation | ArtifactRef
    parents: tuple[str, ...] = ()
    policy: Literal["all", "any"] = "all"
    revision: int = 1


_Nodes = dict[str, tuple[_Binding, bool, SourceLifecycleEvent | None]]


class ScopedSourceLifecycle:
    """Manage one immutable DAG; native writes are retryable projections."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None, scope_id: str) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = validate_scope_id(scope_id)

    def _db(self) -> AsyncDatabase:
        if self._database is None:
            raise SourceLifecycleError("database")
        return self._database

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int) -> None:
        if type(revision) is not int or revision <= 0 or not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError("source")
        await self._register(node_id, _Binding(kind="source", reference=source_ref, revision=revision))

    async def register_memory(
        self, node_id: str, citation: MemoryCitation, *, parents: tuple[str, ...], policy: str
    ) -> None:
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("memory")
        await self._register_derived(node_id, "memory", citation, parents, policy)

    async def register_topic(
        self, node_id: str, artifact_ref: ArtifactRef, *, parents: tuple[str, ...], policy: str
    ) -> None:
        if not isinstance(artifact_ref, ArtifactRef) or artifact_ref.family != "topic-memory":
            raise SourceLifecycleError("topic")
        await self._register_derived(node_id, "topic", artifact_ref, parents, policy)

    async def _register_derived(
        self,
        node_id: str,
        kind: Literal["memory", "topic"],
        reference: MemoryCitation | ArtifactRef,
        parents: Iterable[str],
        policy: str,
    ) -> None:
        if policy not in {"all", "any"} or isinstance(parents, str):
            raise SourceLifecycleError("policy")
        try:
            parents = tuple(parents)
        except TypeError as error:
            raise SourceLifecycleError("parents") from error
        if not parents or any(not isinstance(parent, str) or not parent.strip() for parent in parents):
            raise SourceLifecycleError("named-parents")
        if len(set(parents)) != len(parents) or node_id in parents:
            raise SourceLifecycleError("cycle")
        await self._register(node_id, _Binding(kind=kind, reference=reference, parents=parents, policy=policy))

    async def _load(self) -> _Nodes:
        async with self._db().transaction() as connection:
            rows = (await connection.execute(select(NODES).where(NODES.c.scope_id == self.scope_id))).mappings()
            return {
                str(row["node_id"]): (
                    _Binding.model_validate_json(row["binding"]),
                    bool(row["available"]),
                    None if row["last_event"] is None else SourceLifecycleEvent.model_validate_json(row["last_event"]),
                )
                for row in rows
            }

    async def _register(self, node_id: str, binding: _Binding) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node-id")
        async with self._runtime._context(self.scope_id) as context, self._runtime._locked(self.scope_id):
            nodes = await self._load()
            if node_id in nodes:
                if nodes[node_id][0] != binding:
                    raise SourceLifecycleError("binding")
                await self._reconcile(nodes)
                return
            if any(parent not in nodes for parent in binding.parents):
                raise SourceLifecycleError("missing-parent")
            # Requiring all parents to preexist makes cycles impossible in an immutable graph.
            try:
                ref = binding.reference
                if isinstance(ref, SourceRef):
                    await self._runtime._records().get_source(self.scope_id, ref.source_type, ref.source_id)
                elif isinstance(ref, MemoryCitation):
                    await context.artifacts.memory.validate_citation(ref)
                else:
                    await self._runtime._records().get_artifact_revision(
                        self.scope_id, ref.family, ref.artifact_id, ref.revision
                    )
            except Exception as error:
                raise SourceLifecycleError("reference") from error
            supports = [nodes[parent][1] for parent in binding.parents]
            available = (
                True if binding.kind == "source" else (all(supports) if binding.policy == "all" else any(supports))
            )
            async with self._db().transaction() as connection:
                await connection.execute(
                    insert(NODES).values(
                        scope_id=self.scope_id,
                        node_id=node_id,
                        kind=binding.kind,
                        binding=binding.model_dump_json(),
                        available=available,
                    )
                )
            nodes[node_id] = (binding, available, None)
            await self._reconcile(nodes)

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("event-type")
        async with self._runtime._context(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load()
            node = nodes.get(event.node_id)
            if node is None or node[0].kind != "source" or node[0].revision != event.revision:
                raise SourceLifecycleError("revision")
            previous = node[2]
            if previous is not None and (
                event.sequence < previous.sequence or (event.sequence == previous.sequence and event != previous)
            ):
                raise SourceLifecycleError("sequence")
            nodes[event.node_id] = (node[0], event.available, event)
            pending = set(nodes)
            visited = set()
            while pending:
                ready = sorted(key for key in pending if set(nodes[key][0].parents) <= visited)
                if not ready:
                    raise SourceLifecycleError("persisted-cycle")
                for key in ready:
                    binding, available, last = nodes[key]
                    if binding.kind != "source":
                        supports = [nodes[parent][1] for parent in binding.parents]
                        available = all(supports) if binding.policy == "all" else any(supports)
                    nodes[key] = (binding, available, last)
                pending.difference_update(ready)
                visited.update(ready)
            # Desired state commits first. A failed native write leaves a durable repair target;
            # replay always reconciles instead of treating an accepted event as completed work.
            async with self._db().transaction() as connection:
                for key, (_binding, available, last) in nodes.items():
                    await connection.execute(
                        update(NODES)
                        .where(NODES.c.scope_id == self.scope_id, NODES.c.node_id == key)
                        .values(available=available, last_event=None if last is None else last.model_dump_json())
                    )
            await self._reconcile(nodes, reason=event.reason)
            return sorted(key for key, (_, available, _) in nodes.items() if available)

    async def _reconcile(self, nodes: _Nodes, *, reason: str = "Source lifecycle") -> None:
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            for binding, available, _last in nodes.values():
                ref = binding.reference
                if binding.kind != "memory" or not isinstance(ref, MemoryCitation):
                    continue
                memory, entries = await service.head_entries(ref.memory_ref.artifact_id)
                entry = next((entry for entry in entries if entry.entry_id == ref.entry_id), None)
                if entry is None or entry.entry_version_id != ref.entry_version_id:
                    raise SourceLifecycleError("body-changed")
                transition = service.reactivate if available else service.forget
                await transition(memory, entries=(entry,), reason=reason)

    async def resolve(self, node_id: str, *, purpose: str) -> SourceRef | MemoryCitation | ArtifactRef:
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("purpose")
        async with self._runtime._scope_operation(self.scope_id):
            node = (await self._load()).get(node_id)
            if node is None or (purpose == "generation" and not node[1]):
                raise SourceLifecycleError("unavailable")
            return node[0].reference


class SourceLifecycleApplication:
    """Select the lifecycle graph belonging to a scope."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None) -> None:
        self._runtime = runtime
        self._database = database

    def for_scope(self, scope_id: str) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, self._database, scope_id)
