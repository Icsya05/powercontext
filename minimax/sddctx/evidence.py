"""Evidence recording.

Every external interaction the module has - a SQL statement and its result
count, an HTTP call to PowerContext, the MiniMax request and its token usage,
a test run - is appended to a JSONL file under ``minimax/evidence/raw/``.

The JSONL files are the raw material for the "技术使用记录" that the topic
requires; they are written by the module itself rather than transcribed by
hand, so they cannot drift from what actually happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RAW_EVIDENCE_DIR


@dataclass
class EvidenceRecorder:
    """Append-only recorder for one command run."""

    run_name: str
    raw_dir: Path = field(default_factory=lambda: RAW_EVIDENCE_DIR)
    records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = self.raw_dir / f"{stamp}-{self.run_name}.jsonl"

    def record(self, kind: str, **fields: Any) -> dict[str, Any]:
        """Record one event and return the stored payload."""
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            **fields,
        }
        self.records.append(entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def to_markdown(self, title: str) -> str:
        """Render the recorded events as a readable evidence report."""
        lines = [f"# {title}", "", f"Run: `{self.run_name}`", f"Raw log: `{self.path.as_posix()}`", ""]
        for entry in self.records:
            kind = entry.get("kind", "?")
            detail = {k: v for k, v in entry.items() if k not in {"at", "kind"}}
            lines.append(f"## {kind}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(detail, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
        return "\n".join(lines)

    def write_markdown(self, path: Path, title: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(title), encoding="utf-8")
        return path
