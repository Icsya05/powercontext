"""Count admission uses durable metadata and preserves accepted invocations."""

from __future__ import annotations

import asyncio
from functools import partial

from sqlalchemy import insert, select

from powercontext.builtin.persistence.cursors import SourceCursorRepository
from powercontext.builtin.persistence.processing_intents import ArtifactProcessingIntentRepository
from powercontext.builtin.persistence.sqlite import SQLiteConfig, SQLiteProfile
from powercontext.builtin.persistence.tables import SHARED_TABLES, SOURCE_JOURNAL_HEADS_TABLE
from powercontext.builtin.runtime import processing_discovery
from powercontext.builtin.runtime.artifact_processing import ArtifactProcessingBinding, ArtifactProcessingSupervisor
from powercontext.builtin.runtime.processing_contracts import ArtifactProcessingWorkerCompletion
from powercontext.builtin.runtime.processing_execution import ScopeInvocation
from powercontext.builtin.sources import SourceCursor


def _count_filter(binding, threshold):
    function = getattr(processing_discovery, "source_count_scopes", None)
    assert callable(function), "Missing persisted Source count admission"
    return partial(function, binding_name=binding, threshold=threshold)


def _profile(tmp_path):
    return SQLiteProfile.open(SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'counts.db'}"), tables=SHARED_TABLES)


async def _seed(database, scope, high, binding="memory"):
    async with database.transaction() as connection:
        await connection.execute(insert(SOURCE_JOURNAL_HEADS_TABLE).values(scope_id=scope, position=high))
        await ArtifactProcessingIntentRepository().mark_dirty(connection, scope, binding)


async def _wait_until(predicate):
    async with asyncio.timeout(10):
        while not await predicate():  # noqa: ASYNC110 - bounded observation of durable progress
            await asyncio.sleep(0.01)


class _WindowLauncher:
    """Replace the slow model/process boundary; commit real cursors and requests."""

    def __init__(self, database):
        self.database = database

    async def start(self, assignment):
        launcher = self

        class Handle:
            async def wait(self):
                invocation = ScopeInvocation(assignment)
                async with launcher.database.transaction() as connection:
                    await invocation.start(connection)
                    cursors = SourceCursorRepository()
                    old = await cursors.load(connection, assignment.scope_id, assignment.binding_name)
                    position = (0 if old is None else old.cursor.sequence) + 1
                    high = await connection.scalar(
                        select(SOURCE_JOURNAL_HEADS_TABLE.c.position).where(
                            SOURCE_JOURNAL_HEADS_TABLE.c.scope_id == assignment.scope_id
                        )
                    )
                    await cursors.save(
                        connection,
                        assignment.scope_id,
                        assignment.binding_name,
                        SourceCursor(sequence=position),
                        expected_generation=None if old is None else old.generation,
                    )
                    await invocation.complete(connection, remaining_work=position < high)
                return ArtifactProcessingWorkerCompletion()

            async def terminate(self):
                pass

        return Handle()


def test_count_reads_successful_family_cursor_instead_of_dirty_generations(tmp_path):
    async def scenario():
        count = _count_filter("memory", 3)
        async with _profile(tmp_path) as profile:
            await _seed(profile.database, "scope", 5)
            async with profile.database.transaction() as connection:
                await SourceCursorRepository().save(
                    connection, "scope", "memory", SourceCursor(sequence=3), expected_generation=None
                )
                assert await count(connection, ("scope", "missing")) == frozenset()
                assert await _count_filter("topic-memory", 3)(connection, ("scope",)) == frozenset({"scope"})
                assert await _count_filter("memory", 2)(connection, ("scope",)) == frozenset({"scope"})
                assert await count(connection, ()) == frozenset()

    asyncio.run(scenario())


def test_partial_windows_recheck_count_without_new_capture_and_stop_below_threshold(tmp_path):
    async def scenario():
        count = _count_filter("memory", 3)
        async with _profile(tmp_path) as profile:
            await _seed(profile.database, "scope", 5)
            async with ArtifactProcessingSupervisor(
                database=profile.database,
                bindings=(
                    ArtifactProcessingBinding(
                        "memory", "memory", _WindowLauncher(profile.database), automatic_count_filter=count
                    ),
                ),
                lease_mode="single-process",
                oceanbase_tick_seconds=0.02,
            ):

                async def consumed_three():
                    async with profile.database.transaction() as connection:
                        row = await SourceCursorRepository().load(connection, "scope", "memory")
                        return row is not None and row.cursor.sequence == 3

                await _wait_until(consumed_three)
                await asyncio.sleep(0.15)
                assert await consumed_three()
                async with profile.database.transaction() as connection:
                    intent = await ArtifactProcessingIntentRepository().load(connection, "scope", "memory")
                    assert intent is not None
                    assert intent.requested_generation == intent.handled_generation == 3

    asyncio.run(scenario())


def test_full_page_below_threshold_does_not_starve_later_scope(tmp_path):
    async def scenario():
        count = _count_filter("memory", 3)
        async with _profile(tmp_path) as profile:
            for index in range(105):
                await _seed(profile.database, f"quiet-{index:03d}", 2)
            await _seed(profile.database, "ready", 3)
            async with ArtifactProcessingSupervisor(
                database=profile.database,
                bindings=(
                    ArtifactProcessingBinding(
                        "memory", "memory", _WindowLauncher(profile.database), automatic_count_filter=count
                    ),
                ),
                lease_mode="single-process",
                oceanbase_tick_seconds=0.02,
            ):

                async def completed():
                    async with profile.database.transaction() as connection:
                        row = await SourceCursorRepository().load(connection, "ready", "memory")
                        return row is not None and row.cursor.sequence == 1

                await _wait_until(completed)
                async with profile.database.transaction() as connection:
                    quiet = await ArtifactProcessingIntentRepository().load(connection, "quiet-000", "memory")
                    assert quiet is not None
                    assert quiet.requested_generation == 0

    asyncio.run(scenario())


def test_accepted_request_reopens_even_after_threshold_is_increased(tmp_path):
    async def scenario():
        count = _count_filter("memory", 100)
        async with _profile(tmp_path) as profile:
            await _seed(profile.database, "scope", 1)
            async with profile.database.transaction() as connection:
                await ArtifactProcessingIntentRepository().request(connection, "scope", "memory")
        async with (
            _profile(tmp_path) as profile,
            ArtifactProcessingSupervisor(
                database=profile.database,
                bindings=(
                    ArtifactProcessingBinding(
                        "memory", "memory", _WindowLauncher(profile.database), automatic_count_filter=count
                    ),
                ),
                lease_mode="single-process",
                oceanbase_tick_seconds=0.02,
            ),
        ):

            async def completed():
                async with profile.database.transaction() as connection:
                    row = await SourceCursorRepository().load(connection, "scope", "memory")
                    return row is not None and row.cursor.sequence == 1

            await _wait_until(completed)

    asyncio.run(scenario())
