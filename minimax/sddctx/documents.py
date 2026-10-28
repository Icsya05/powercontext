"""Parser for the SDD documents used by the context module.

Two document kinds share one format:

* **specification** - ``minimax/specs/*.md``
* **task** - ``minimax/tasks/*.md``

Both start with a small YAML-ish front matter block and then use level-2
sections whose heading carries a stable identifier::

    ---
    spec_id: SPEC-JP-FN-001
    title: matches(subject, pattern)
    applies_to:
      - jmespath/functions.py
    ---

    ## R1 | matches 必须是恰好两个字符串参数

    Body of the requirement ...

The parser keeps the source file and the source line of every section so the
retrieved context can point back to a real location.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: ``## <ID> | <title>``
SECTION_RE = re.compile(r"^##\s+(?P<id>[A-Za-z0-9_.\-]+)\s*\|\s*(?P<title>.+?)\s*$")
#: ``## <id>`` without a title
SECTION_RE_NO_TITLE = re.compile(r"^##\s+(?P<id>[A-Za-z0-9_.\-]+)\s*$")

#: How a section id maps onto the kind of statement it makes.
KIND_BY_PREFIX = {
    "R": "requirement",
    "B": "invariant",
    "A": "acceptance",
    "G": "goal",
    "S": "step",
    "K": "keep",
}

#: The leading letters of a section id, e.g. ``R1`` -> ``R``.
_PREFIX_RE = re.compile(r"^[A-Za-z]+")


@dataclass
class Section:
    """One level-2 section of a document."""

    section_id: str
    title: str
    body: str
    source_path: str
    source_line: int

    @property
    def kind(self) -> str:
        match = _PREFIX_RE.match(self.section_id)
        prefix = match.group(0).upper() if match else ""
        return KIND_BY_PREFIX.get(prefix, "note")


@dataclass
class Document:
    """A parsed specification or task document."""

    doc_id: str
    title: str
    front_matter: dict
    sections: list[Section] = field(default_factory=list)
    source_path: str = ""

    @property
    def path(self) -> Path:
        return Path(self.source_path)


def parse_front_matter(text: str) -> tuple[dict, int]:
    """Parse the ``---`` delimited front matter.

    Only the small subset the documents use is supported: scalars and simple
    ``- item`` lists.  Returns the mapping and the number of consumed lines.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    data: dict = {}
    index = 1
    while index < len(lines) and lines[index].strip() != "---":
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("- ") and data:
            key = next(reversed(data))
            if isinstance(data[key], list):
                data[key].append(stripped[2:].strip().strip('"').strip("'"))
        elif ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                data[key] = []
            else:
                data[key] = value.strip('"').strip("'")
        index += 1
    return data, index + 1


def parse_document(path: Path, doc_id: str | None = None) -> Document:
    """Parse a specification or task document from disk."""
    text = path.read_text(encoding="utf-8")
    front_matter, offset = parse_front_matter(text)
    lines = text.splitlines()

    sections: list[Section] = []
    current_id: str | None = None
    current_title = ""
    current_line = 0
    buffer: list[str] = []

    def flush() -> None:
        if current_id is None:
            return
        sections.append(
            Section(
                section_id=current_id,
                title=current_title,
                body="\n".join(buffer).strip(),
                source_path=path.as_posix(),
                source_line=current_line,
            )
        )

    for number, raw in enumerate(lines[offset:], start=offset + 1):
        match = SECTION_RE.match(raw) or SECTION_RE_NO_TITLE.match(raw)
        if match:
            flush()
            current_id = match.group("id")
            current_title = (match.groupdict().get("title") or current_id).strip()
            current_line = number
            buffer = []
            continue
        if current_id is not None:
            buffer.append(raw)
    flush()

    resolved_id = doc_id or front_matter.get("spec_id") or front_matter.get("task_id") or path.stem
    return Document(
        doc_id=str(resolved_id),
        title=str(front_matter.get("title") or path.stem),
        front_matter=front_matter,
        sections=sections,
        source_path=path.as_posix(),
    )


def load_documents(directory: Path, doc_id: str | None = None) -> list[Document]:
    """Parse every markdown document in ``directory`` (sorted by file name)."""
    if not directory.is_dir():
        return []
    documents = []
    for path in sorted(directory.glob("*.md")):
        documents.append(parse_document(path, doc_id=doc_id))
    return documents
