"""Independent malformed-wire and UTF-8 boundary checks."""

import json

import pytest

from powercontext.builtin.runtime.context_pack import ContextPack, ContextPackDelta, ContextPackError


@pytest.mark.parametrize("length", [1, 9, 99, 999, 9999])
def test_full_wire_count_includes_its_own_digits(length):
    pack = ContextPack.from_content("x" * length)
    assert pack.byte_count == len(pack.to_bytes())
    assert ContextPack.from_bytes(pack.to_bytes()) == pack


@pytest.mark.parametrize("size", [True, 0, -1, 1.5, "4"])
def test_invalid_chunk_bounds_fail(size):
    with pytest.raises(ContextPackError):
        ContextPack.from_content("text", chunk_bytes=size)


def test_unicode_chunk_boundaries_preserve_complete_codepoints():
    pack = ContextPack.from_content("a海🌊b", chunk_bytes=4)
    assert b"".join(pack.items) == "a海🌊b".encode()
    assert all(len(item) <= 4 and item.decode() for item in pack.items)


def test_duplicate_wire_keys_and_noncanonical_base64_are_rejected():
    pack = ContextPack.build((b"a",))
    duplicate = pack.to_bytes().replace(b'"byte_count":', b'"byte_count":0,"byte_count":')
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(duplicate)
    delta = ContextPackDelta.between(pack, ContextPack.build((b"b",)))
    payload = json.loads(delta.to_bytes())
    payload["appended"] = ["Yg==="]
    with pytest.raises(ContextPackError):
        ContextPackDelta.from_bytes(json.dumps(payload).encode())
