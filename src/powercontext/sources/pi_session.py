"""Original Pi v3 branch evidence, independent of compressed model context."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, JsonValue, field_validator

from powercontext.sources.connectors import (
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    ConnectorSubmissionStatus,
)
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

_Record = dict[str, JsonValue]


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Pi identity and type fields must be nonblank strings")  # noqa: TRY003
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> _Record:
    result: _Record = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key in Pi archive")  # noqa: TRY003
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant: {value}")  # noqa: TRY003


class PiSessionInput(BaseModel):
    """A complete offline JSONL snapshot and optional selected tree leaf."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One full visible event with its untouched original JSON record."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: _Record

    @field_validator("session_id", "event_id", "event_type", "role")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        return _required_string(value)


def _text_blocks(value: JsonValue | None, *, tools: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError("Pi message content must be text or content blocks")  # noqa: TRY003, TRY004
    parts: list[str] = []
    for block in value:
        if not isinstance(block, dict):
            raise ValueError("Pi content blocks must be objects")  # noqa: TRY003, TRY004
        if block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise ValueError("Pi text block must contain a string")  # noqa: TRY003
            parts.append(text)
        elif tools and block.get("type") == "toolCall":
            name = _required_string(block.get("name"))
            call_id = _required_string(block.get("id"))
            if "arguments" not in block:
                raise ValueError("Pi tool call is missing its arguments")  # noqa: TRY003
            arguments = _canonical(block["arguments"]).decode("utf-8")
            parts.append(f"[tool_call {name} {call_id}] {arguments}")
    return "\n".join(parts)


def _render_event(record: _Record) -> tuple[str, str] | None:
    event_type = record["type"]
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            raise ValueError("Pi message entry is missing its message object")  # noqa: TRY003
        role = _required_string(message.get("role"))
        if role == "bashExecution":
            command, output = message.get("command", ""), message.get("output", "")
            if not isinstance(command, str) or not isinstance(output, str):
                raise ValueError("Pi bash command and output must be strings")  # noqa: TRY003
            body = f"$ {command}\n{output}" if command.strip() or output.strip() else ""
        else:
            body = _text_blocks(message.get("content"), tools=role != "toolResult")
            if role == "toolResult" and body.strip():
                tool_name = _required_string(message.get("toolName"))
                call_id = _required_string(message.get("toolCallId"))
                body = f"[tool_result {tool_name} {call_id}] {body}"
    elif event_type in {"compaction", "branch_summary"}:
        role = str(event_type)
        body = _text_blocks(record.get("summary"))
    elif event_type == "custom_message":
        if record.get("display") is False:
            return None
        role = "custom"
        body = _text_blocks(record.get("content"))
    else:
        return None
    return (role, f"{role}: {body}") if body.strip() else None


@dataclass(frozen=True, slots=True)
class _Archive:
    session_id: str
    records: dict[str, _Record]
    events: tuple[PiEventInput, ...]


def _read_records(content: bytes) -> list[_Record]:
    records: list[_Record] = []
    # JSONL splits only at LF; Unicode separators are legal inside JSON strings.
    for line in content.decode("utf-8-sig").split("\n"):
        if not line.strip(" \t\r"):
            continue
        record = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if not isinstance(record, dict):
            raise ValueError("Pi archive records must be JSON objects")  # noqa: TRY003, TRY004
        _canonical(record)
        records.append(cast(_Record, record))
    if not records:
        raise ValueError("Pi archive is empty")  # noqa: TRY003
    return records


def _parse_archive(value: PiSessionInput) -> _Archive:
    records = _read_records(value.content)
    header = records[0]
    if header.get("type") != "session" or type(header.get("version")) is not int or header["version"] != 3:
        raise ValueError("Pi archive must begin with a version 3 session")  # noqa: TRY003
    session_id = _required_string(header.get("id"))
    nodes: dict[str, _Record] = {}
    for record in records[1:]:
        event_id = _required_string(record.get("id"))
        _required_string(record.get("type"))
        if event_id in nodes or "parentId" not in record or record["type"] == "session":
            raise ValueError("Pi nodes require unique IDs and an explicit parent")  # noqa: TRY003
        parent = record["parentId"]
        if parent is not None and (not isinstance(parent, str) or parent not in nodes):
            raise ValueError("Pi parent must be null or an already present node")  # noqa: TRY003
        nodes[event_id] = record
    leaf = value.leaf_id if value.leaf_id is not None else next(reversed(nodes), None)
    if leaf is not None and leaf not in nodes:
        raise ValueError("Pi selected leaf does not exist")  # noqa: TRY003
    chain: list[_Record] = []
    while leaf is not None:
        node = nodes[leaf]
        chain.append(node)
        leaf = cast(str | None, node["parentId"])
    events = []
    for record in reversed(chain):
        rendered = _render_event(record)
        if rendered is not None:
            role, content = rendered
            events.append(
                PiEventInput(
                    session_id=session_id,
                    event_id=cast(str, record["id"]),
                    parent_id=cast(str | None, record["parentId"]),
                    event_type=cast(str, record["type"]),
                    role=role,
                    content=content,
                    record=record,
                )
            )
    return _Archive(session_id, nodes, tuple(events))


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Return original visible ancestors, never a compaction/context-edit replay."""
    return _parse_archive(value).events


class PiEventSource(Source, PiEventInput):
    """Captured evidence tied solely to one session/event identity pair."""


class PiEventSourceAdapter:
    input_class: type[PiEventInput] = PiEventInput
    name = "pi-event"
    source_class: type[PiEventSource] = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        identity = "pi:" + hashlib.sha256(_canonical((value.session_id, value.event_id))).hexdigest()
        return PiEventSource(name=identity, materialization=SourceMaterialization.CAPTURED, **value.model_dump())

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput.model_validate(source.model_dump())


class PiEventTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class: type[PiEventSource] = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pi-event",
            source_id=source.name,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition[PiEventInput, PiEventSource, PiEventInput](
    PiEventSourceAdapter(), projections=(PiEventTextEvidenceProjection(),)
)


def _checkpoint_hashes(value: JsonValue) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Pi checkpoint event fingerprints must be an object")  # noqa: TRY003, TRY004
    result = {}
    for event_id, fingerprint in value.items():
        _required_string(event_id)
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in fingerprint)
        ):
            raise ValueError("invalid Pi checkpoint event fingerprint")  # noqa: TRY003
        result[event_id] = fingerprint
    return result


def _checkpoint_sessions(value: JsonValue | None) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) != {"version", "sessions"}:
        raise ValueError("invalid Pi checkpoint format")  # noqa: TRY003
    if type(value["version"]) is not int or value["version"] != 1 or not isinstance(value["sessions"], dict):
        raise ValueError("unsupported Pi checkpoint version or sessions")  # noqa: TRY003
    return {
        _required_string(session_id): _checkpoint_hashes(records) for session_id, records in value["sessions"].items()
    }


class PiSessionConnector:
    """Resume file snapshots using only lifecycle-owned durable checkpoints."""

    name = "pi-session-history"
    version = "1"
    source_definitions = frozenset({"pi-event"})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        content = await asyncio.to_thread(self._path.read_bytes)
        archive = _parse_archive(PiSessionInput(content=content, leaf_id=self._leaf_id))
        sessions = _checkpoint_sessions(session.checkpoint)
        imported = sessions.setdefault(archive.session_id, {})
        # Check every previously captured record, including the other branches,
        # before any new submissions can produce side effects.
        for event_id, fingerprint in imported.items():
            original = archive.records.get(event_id)
            if original is None or hashlib.sha256(_canonical(original)).hexdigest() != fingerprint:
                raise ValueError("previously imported Pi event was removed or rewritten")  # noqa: TRY003
        complete = True
        for event in archive.events:
            if event.event_id in imported:
                continue
            item_id = "pi:" + hashlib.sha256(_canonical((event.session_id, event.event_id))).hexdigest()
            outcome = await session.submit(item_id, "pi-event", event)
            if outcome.status is ConnectorSubmissionStatus.ACCEPTED:
                imported[event.event_id] = hashlib.sha256(_canonical(event.record)).hexdigest()
            else:
                complete = False
        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE if complete else ConnectorRunStatus.INCOMPLETE,
            checkpoint=cast(JsonValue, {"version": 1, "sessions": sessions}),
        )
