"""Print the execution plan of the single-statement hybrid candidate query.

The hidden acceptance for retrieval-02-hybrid-search requires the plan of that
statement to show both a TEXT RETRIEVAL SCAN and a VECTOR INDEX.  The public
acceptance only looks at the statement text, so this is the check the public
self-test does not make.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from sqlalchemy import event, text as sql_text
from sqlalchemy.engine import Engine

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts

PROFILE = EmbeddingProfile(
    profile_id="hybrid-plan-check",
    model="deterministic",
    dimension=3,
    distance="l2",
    normalization="unit",
)


class _Embedding:
    profile = PROFILE

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(
                (1.0, 0.0, 0.0)
                if "alpha" in text.casefold()
                else (0.0, 0.0, 1.0)
                if "gamma" in text.casefold()
                else (0.0, 1.0, 0.0)
                for text in texts
            )
        )


async def main() -> None:
    database_path = Path(tempfile.mkdtemp(prefix="hybrid-plan-", dir=os.environ.get("TMPDIR"))) / "db"
    captured: list[tuple[str, object]] = []

    def record(_connection, _cursor, statement, parameters, _context, _executemany) -> None:
        captured.append((str(statement), parameters))

    event.listen(Engine, "before_cursor_execute", record)
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=database_path)), embedding_model=_Embedding()
    ) as contexts:
        memory = (await contexts.get("project")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=(
                MemoryEntryInput(kind="fact", text="Alpha semantic record about mitochondria."),
                MemoryEntryInput(kind="fact", text="Beta lexical record about mitochondria."),
                MemoryEntryInput(kind="fact", text="Gamma entry in the newer memory head."),
            ),
            mode="append",
        )
        assert head is not None
        result = await memory.search("mitochondria alpha", memories=(head,), mode="hybrid", limit=10)
        print("hits:", len(result.hits), "mode:", result.mode)

        hybrid = [
            (statement, parameters)
            for statement, parameters in captured
            if "pc_memory_vector_entries" in statement and "AGAINST" in statement
        ]
        print("hybrid statements:", len(hybrid))
        if not hybrid:
            print("no hybrid statement captured; all statements:")
            for statement, _ in captured:
                print("   ", statement[:200])
            return
        statement, parameters = hybrid[0]
        if isinstance(parameters, (list, tuple)) and parameters and isinstance(parameters[0], dict):
            parameters = parameters[0]
        print("parameter container:", type(parameters).__name__, "->", str(parameters)[:200])

        engine = None
        for candidate in (memory._backend, getattr(memory._backend, "_database", None)):
            engine = getattr(candidate, "engine", None) or getattr(candidate, "_engine", None)
            if engine is not None:
                break
        if engine is None:
            print("could not reach the engine")
            return
        async with engine.connect() as connection:
            for label, sql in (("EXPLAIN", "EXPLAIN " + statement), ("EXPLAIN FORMAT=JSON", "EXPLAIN FORMAT=JSON " + statement)):
                try:
                    rows = await connection.exec_driver_sql(sql, parameters)
                    print("-" * 100)
                    print(label)
                    for row in rows:
                        line = " | ".join(str(cell) for cell in row)
                        print("   ", line)
                        for needle in ("TEXT RETRIEVAL SCAN", "VECTOR INDEX", "TABLE SCAN", "INDEX SCAN"):
                            if needle in line.upper():
                                print(f"        >>> contains {needle!r}")
                except Exception as error:  # noqa: BLE001
                    print(f"{label} failed:", type(error).__name__, str(error)[:400])


if __name__ == "__main__":
    asyncio.run(main())
