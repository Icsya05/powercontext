"""Self-contained v1 context transport with verified prefix reconstruction."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_PACK_SCHEMA = "powercontext.context-pack.v1"
_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ContextPackError(ValueError):
    """A context transport value violates its public wire contract."""


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _encoded(items: tuple[bytes, ...]) -> list[str]:
    if not isinstance(items, tuple) or any(not isinstance(item, bytes) for item in items):
        raise ContextPackError("chunks must be a tuple of bytes")  # noqa: TRY003
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decoded(value: object) -> tuple[bytes, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContextPackError("encoded chunks must be a string array")  # noqa: TRY003
    decoded = []
    for item in value:
        try:
            raw = base64.b64decode(item, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ContextPackError("invalid Base64 chunk") from error  # noqa: TRY003
        if base64.b64encode(raw).decode("ascii") != item:
            raise ContextPackError("chunk must use standard canonical Base64")  # noqa: TRY003
        decoded.append(raw)
    return tuple(decoded)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContextPackError("duplicate JSON field")  # noqa: TRY003
        result[key] = value
    return result


def _read_wire(raw: bytes, keys: set[str], schema: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, AttributeError) as error:
        raise ContextPackError("invalid UTF-8 JSON context payload") from error  # noqa: TRY003
    if not isinstance(value, dict) or set(value) != keys or value["schema"] != schema:
        raise ContextPackError("context payload fields or schema do not match")  # noqa: TRY003
    return value


def _digest(items: tuple[bytes, ...]) -> str:
    return "sha256:" + hashlib.sha256(_json({"schema": _PACK_SCHEMA, "items": _encoded(items)})).hexdigest()


def _check_digest(value: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ContextPackError("invalid context digest")  # noqa: TRY003


def _pack_wire(items: tuple[bytes, ...], digest: str, byte_count: int) -> bytes:
    return _json({"schema": _PACK_SCHEMA, "items": _encoded(items), "digest": digest, "byte_count": byte_count})


@dataclass(frozen=True, slots=True)
class ContextPack:
    """A complete ordered context whose digest covers its exact chunk layout."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    def __post_init__(self) -> None:
        if self.digest != _digest(self.items):
            raise ContextPackError("context pack digest mismatch")  # noqa: TRY003
        if type(self.byte_count) is not int or self.byte_count != len(self.to_bytes()):
            raise ContextPackError("context pack byte count mismatch")  # noqa: TRY003

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        digest = _digest(items)
        count = 0
        while (actual := len(_pack_wire(items, digest, count))) != count:
            count = actual
        return cls(items, digest, count)

    @classmethod
    def from_content(cls, content: str | None, *, chunk_bytes: int = 512) -> ContextPack:
        if type(chunk_bytes) is not int or chunk_bytes <= 0:
            raise ContextPackError("chunk_bytes must be a positive integer")  # noqa: TRY003
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ContextPackError("context content must be text")  # noqa: TRY003
        try:
            raw = content.encode("utf-8")
        except UnicodeError as error:
            raise ContextPackError("context content must be valid UTF-8") from error  # noqa: TRY003
        chunks = []
        offset = 0
        while offset < len(raw):
            end = min(offset + chunk_bytes, len(raw))
            while end < len(raw) and end > offset and raw[end] & 0xC0 == 0x80:
                end -= 1
            if end == offset:
                raise ContextPackError("a UTF-8 character exceeds the chunk byte limit")  # noqa: TRY003
            chunks.append(raw[offset:end])
            offset = end
        return cls.build(tuple(chunks))

    def to_bytes(self) -> bytes:
        return _pack_wire(self.items, self.digest, self.byte_count)

    @classmethod
    def from_bytes(cls, raw: bytes) -> ContextPack:
        value = _read_wire(raw, {"schema", "items", "digest", "byte_count"}, _PACK_SCHEMA)
        return cls(_decoded(value["items"]), value["digest"], value["byte_count"])


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """Retain a base prefix and append the complete replacement suffix."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    def __post_init__(self) -> None:
        _check_digest(self.base_digest)
        _check_digest(self.target_digest)
        if type(self.prefix_items) is not int or self.prefix_items < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")  # noqa: TRY003
        _encoded(self.appended)

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        base = ContextPack.from_bytes(base.to_bytes())
        target = ContextPack.from_bytes(target.to_bytes())
        prefix = 0
        for first, second in zip(base.items, target.items, strict=False):
            if first != second:
                break
            prefix += 1
        return cls(base.digest, target.digest, prefix, target.items[prefix:])

    def to_bytes(self) -> bytes:
        return _json({
            "schema": _DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": _encoded(self.appended),
        })

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> ContextPackDelta:
        value = _read_wire(raw, {"schema", "base_digest", "target_digest", "prefix_items", "appended"}, _DELTA_SCHEMA)
        return cls(value["base_digest"], value["target_digest"], value["prefix_items"], _decoded(value["appended"]))


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Validate both endpoints without relying on any sender-side state."""
    base = ContextPack.from_bytes(base.to_bytes())
    delta = ContextPackDelta.from_bytes(delta.to_bytes())
    if delta.base_digest != base.digest or delta.prefix_items > len(base.items):
        raise ContextPackError("delta does not match its base pack")  # noqa: TRY003
    result = ContextPack.build(base.items[: delta.prefix_items] + delta.appended)
    if result.digest != delta.target_digest:
        raise ContextPackError("delta target digest mismatch")  # noqa: TRY003
    return result
