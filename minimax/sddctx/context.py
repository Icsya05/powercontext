"""Development context assembly.

The context is what the module hands to MiniMax and what it prints as
"where the answer came from".  It is assembled from three places:

* **seekdb** selects the specification entries, the code symbols and the
  tests that apply to the task (the queries are recorded as evidence).
* the task document states the goal, the behaviour that must not change and
  the acceptance commands.
* **PowerContext** contributes what already happened: finished items, open
  items and the verification results recorded by earlier runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .code_index import CodeSymbol, TestCase
from .documents import Document
from .seekdb_store import SeekDBStore


@dataclass
class Task:
    """A development task, parsed from ``minimax/tasks/<id>.md``."""

    task_id: str
    title: str
    goal: str = ""
    keep: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    spec_ids: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    target_tests: list[str] = field(default_factory=list)
    source_path: str = ""

    @property
    def search_text(self) -> str:
        parts = [self.title, self.goal, *self.keywords, *self.applies_to]
        return " ".join(part for part in parts if part)


@dataclass
class ContextEntry:
    """One retrieved item together with where it came from."""

    identifier: str
    title: str
    body: str
    source_path: str
    source_line: int
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> str:
        return f"{self.source_path}:{self.source_line}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "kind": self.kind,
            "title": self.title,
            "source": self.source,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "body": self.body,
            **({"detail": self.detail} if self.detail else {}),
        }


@dataclass
class DevelopmentContext:
    """The assembled context for one task."""

    task: Task
    specs: list[ContextEntry] = field(default_factory=list)
    code: list[ContextEntry] = field(default_factory=list)
    tests: list[ContextEntry] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    todo: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    retrieval: dict[str, Any] = field(default_factory=dict)
    #: exact current content of the files the task says it will change
    files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": {
                "task_id": self.task.task_id,
                "title": self.task.title,
                "goal": self.task.goal,
                "keep": self.task.keep,
                "acceptance": self.task.acceptance,
                "spec_ids": self.task.spec_ids,
                "applies_to": self.task.applies_to,
                "target_tests": self.task.target_tests,
                "source_path": self.task.source_path,
            },
            "specifications": [entry.to_dict() for entry in self.specs],
            "code": [entry.to_dict() for entry in self.code],
            "tests": [entry.to_dict() for entry in self.tests],
            "progress": {
                "finished": self.finished,
                "todo": self.todo,
                "verification": self.verification,
            },
            "retrieval": self.retrieval,
        }

    def to_prompt(self) -> str:
        """Render the context as the prompt body for MiniMax."""
        lines: list[str] = []
        lines.append(f"# Task {self.task.task_id}: {self.task.title}")
        lines.append("")
        lines.append("## Goal")
        lines.append(self.task.goal or self.task.title)
        lines.append("")
        if self.task.keep:
            lines.append("## Behaviour that must NOT change")
            for item in self.task.keep:
                lines.append(f"- {item}")
            lines.append("")
        lines.append("## Applicable specification entries")
        for entry in self.specs:
            lines.append(f"### {entry.identifier} | {entry.title}")
            lines.append(f"(source: {entry.source})")
            lines.append(entry.body)
            lines.append("")
        lines.append("## Code that has to change")
        for entry in self.code:
            lines.append(f"### {entry.detail.get('file_path')} :: {entry.identifier}")
            lines.append(f"(source: {entry.source})")
            lines.append("```python")
            lines.append(entry.body)
            lines.append("```")
            lines.append("")
        if self.files:
            lines.append(
                "## Exact current content of the files under change "
                "(the diff context lines must match these bytes exactly)"
            )
            for relative, content in self.files.items():
                lines.append(f"### {relative}")
                lines.append("```python")
                lines.append(content.rstrip("\n"))
                lines.append("```")
                lines.append("")
        lines.append("## Tests that verify the behaviour")
        for entry in self.tests:
            lines.append(f"### {entry.identifier}")
            lines.append(f"(source: {entry.source})")
            if entry.detail.get("target"):
                lines.append(f"verifies: {entry.detail['target']}")
            lines.append("```python")
            lines.append(entry.body)
            lines.append("```")
            lines.append("")
        if self.finished or self.todo or self.verification:
            lines.append("## Progress recorded by earlier runs")
            for item in self.finished:
                lines.append(f"- done: {item}")
            for item in self.verification:
                lines.append(f"- verified: {item}")
            for item in self.todo:
                lines.append(f"- todo: {item}")
            lines.append("")
        if self.task.acceptance:
            lines.append("## Acceptance commands")
            for item in self.task.acceptance:
                lines.append(f"- {item}")
            lines.append("")
        return "\n".join(lines)


def parse_task(document: Document) -> Task:
    """Turn a parsed task document into a :class:`Task`."""
    front = document.front_matter
    goal = ""
    keep: list[str] = []
    acceptance: list[str] = []

    for section in document.sections:
        if section.section_id.upper().startswith("GOAL"):
            goal = section.body.strip()
        elif section.section_id.upper().startswith("KEEP"):
            keep = [line.strip("-* ").strip() for line in section.body.splitlines() if line.strip()]
        elif section.section_id.upper().startswith("ACCEPT"):
            acceptance = [line.strip("-* ").strip() for line in section.body.splitlines() if line.strip()]

    def as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str) and value:
            return [value]
        return []

    return Task(
        task_id=str(front.get("task_id") or document.doc_id),
        title=str(front.get("title") or document.title),
        goal=goal,
        keep=keep,
        acceptance=acceptance,
        spec_ids=as_list(front.get("spec_ids")),
        keywords=as_list(front.get("keywords")),
        applies_to=as_list(front.get("applies_to")),
        target_tests=as_list(front.get("target_tests")),
        source_path=document.source_path,
    )


def _spec_entry(row: dict[str, Any]) -> ContextEntry:
    return ContextEntry(
        identifier=f"{row['spec_id']}#{row['section_id']}",
        title=row.get("title") or row["section_id"],
        body=row.get("content") or "",
        source_path=row.get("source_path") or "",
        source_line=int(row.get("source_line") or 0),
        kind=row.get("kind") or "requirement",
        detail={"spec_id": row["spec_id"], "section_id": row["section_id"]},
    )


def _code_entry(row: dict[str, Any]) -> ContextEntry:
    return ContextEntry(
        identifier=row.get("symbol") or "",
        title=row.get("signature") or row.get("symbol") or "",
        body=row.get("content") or "",
        source_path=row.get("source_path") or "",
        source_line=int(row.get("source_line") or 0),
        kind=row.get("kind") or "function",
        detail={"file_path": row.get("file_path") or ""},
    )


def _test_entry(row: dict[str, Any]) -> ContextEntry:
    return ContextEntry(
        identifier=row.get("test_id") or "",
        title=row.get("name") or "",
        body=row.get("content") or "",
        source_path=row.get("source_path") or "",
        source_line=int(row.get("source_line") or 0),
        kind="test",
        detail={
            "file_path": row.get("file_path") or "",
            "target": row.get("target") or "",
        },
    )


def build_context(
    task: Task,
    store: SeekDBStore,
    *,
    state: dict[str, Any] | None = None,
    project_root: Path | None = None,
    limit_specs: int = 12,
    limit_code: int = 8,
    limit_tests: int = 8,
) -> DevelopmentContext:
    """Query seekdb for the material that applies to ``task``.

    The selection order is deliberate:

    1. the symbols of the files the task says it will change,
    2. the test cases of the test files the task says it will add,
    3. whatever else the full-text index in seekdb considers relevant.

    Steps 1 and 2 come from the task document; step 3 is the database
    contribution, and the recorded query shows exactly what it returned.
    """
    keyword = (
        " ".join(task.keywords)
        if task.keywords
        else store.keyword(task.search_text)
    )

    spec_rows, spec_mode = store.search_specs(keyword, limit=limit_specs)
    # The named specifications are authoritative; pull every section of them
    # so the model sees the complete requirement set.
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for row in spec_rows:
        selected[(row["spec_id"], row["section_id"])] = row
    for spec_id in task.spec_ids:
        for row in store.get_spec_sections(spec_id):
            selected.setdefault((row["spec_id"], row["section_id"]), row)

    # --- code: the files under change first, then index hits ------------
    code_rows: list[dict[str, Any]] = []
    seen_code: dict[tuple[str, str], dict[str, Any]] = {}
    for file_path in task.applies_to:
        for row in store.get_code_of_file(file_path):
            if (row["file_path"], row["symbol"]) not in seen_code:
                seen_code[(row["file_path"], row["symbol"])] = row
                code_rows.append(row)
    keyword_code, code_mode = store.search_code(keyword, limit=limit_code)
    for row in keyword_code:
        key = (row["file_path"], row["symbol"])
        if key not in seen_code:
            seen_code[key] = row
            code_rows.append(row)

    # --- tests: the target test files first, then index hits ------------
    test_rows: list[dict[str, Any]] = []
    seen_tests: dict[str, dict[str, Any]] = {}
    for test_path in task.target_tests:
        for row in store.get_tests_of_file(test_path):
            if row["test_id"] not in seen_tests:
                seen_tests[row["test_id"]] = row
                test_rows.append(row)
    keyword_tests, test_mode = store.search_tests(keyword, limit=limit_tests)
    for row in keyword_tests:
        if row["test_id"] not in seen_tests:
            seen_tests[row["test_id"]] = row
            test_rows.append(row)

    finished: list[str] = []
    todo: list[str] = []
    verification: list[str] = []
    if state:
        finished = list(state.get("finished") or [])
        todo = list(state.get("todo") or [])
        verification = list(state.get("verification") or [])

    # The exact bytes of the files under change.  A development assistant
    # writes a diff, and diff context lines have to match the file byte for
    # byte, so the context carries the current content verbatim.
    files: dict[str, str] = {}
    if project_root is not None:
        for relative in task.applies_to:
            path = project_root / relative
            if path.is_file():
                files[relative] = path.read_text(encoding="utf-8")

    return DevelopmentContext(
        task=task,
        specs=[_spec_entry(row) for row in selected.values()],
        code=[_code_entry(row) for row in code_rows],
        tests=[_test_entry(row) for row in test_rows],
        finished=finished,
        todo=todo,
        verification=verification,
        retrieval={
            "keyword": keyword,
            "spec_mode": spec_mode,
            "code_mode": code_mode,
            "test_mode": test_mode,
            "spec_hits": len(selected),
            "code_hits": len(code_rows),
            "test_hits": len(test_rows),
            "code_from_task_files": len(code_rows) - len(keyword_code),
            "tests_from_task_files": len(test_rows) - len(keyword_tests),
            "files_under_change": sorted(files),
        },
        files=files,
    )
