"""Pi archives must preserve full original evidence and validate the whole graph."""

import asyncio
import json

import pytest

from powercontext.sources import SourceDefinitionRegistry, TextEvidence
from powercontext.sources.pi_session import PI_EVENT_SOURCE_DEFINITION, PiSessionInput, parse_pi_session
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY


def _archive(records, *, session_id="s", leaf_id=None):
    header = {"type": "session", "version": 3, "id": session_id}
    content = "\n".join(json.dumps(value, ensure_ascii=False) for value in [header, *records]).encode()
    return PiSessionInput(content=content, leaf_id=leaf_id)


def _message(event_id="root", parent=None, text="original"):
    return {"type": "message", "id": event_id, "parentId": parent, "message": {"role": "user", "content": text}}


def test_invalid_unselected_branch_prevents_any_result():
    records = [_message(), _message("bad", "missing")]
    with pytest.raises(ValueError):
        parse_pi_session(_archive(records, leaf_id="root"))


def test_header_only_is_valid_but_a_nonexistent_leaf_is_not():
    assert parse_pi_session(_archive([])) == ()
    with pytest.raises(ValueError):
        parse_pi_session(_archive([], leaf_id="root"))


def test_unicode_line_separators_inside_json_strings_are_not_jsonl_boundaries():
    text = "first\u2028second\u0085third"
    event = parse_pi_session(_archive([_message(text=text)]))[0]
    assert event.content == "user: " + text


@pytest.mark.parametrize("version", [True, 3.0, "3", 2])
def test_session_version_is_not_coerced(version):
    raw = json.dumps({"type": "session", "version": version, "id": "s"}).encode()
    with pytest.raises(ValueError):
        parse_pi_session(PiSessionInput(content=raw))


def test_complete_large_tool_output_and_record_survive_captured_readback():
    text = "原始工具输出\n" * 10000
    record = {
        "type": "message",
        "id": "tool",
        "parentId": None,
        "extra": {"keep": [1, False]},
        "message": {
            "role": "toolResult",
            "toolName": "read",
            "toolCallId": "call:1",
            "content": [{"type": "text", "text": text}],
        },
    }
    event = parse_pi_session(_archive([record]))[0]
    assert event.content == "toolResult: [tool_result read call:1] " + text
    assert event.record == record
    registry = SourceDefinitionRegistry((PI_EVENT_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(event))
    assert asyncio.run(registry.read(source)) == event
    assert TextEvidence.model_validate(registry.project(source, TEXT_EVIDENCE_PROJECTION_KEY)).content == event.content


def test_empty_blocks_preserve_newlines_and_hidden_custom_keeps_parent_connection():
    records = [
        _message(text=[{"type": "text", "text": "one"}, {"type": "text", "text": ""}, {"type": "text", "text": "two"}]),
        {"type": "custom_message", "id": "hidden", "parentId": "root", "display": False, "content": "hidden"},
        _message("end", "hidden", "tail"),
    ]
    events = parse_pi_session(_archive(records))
    assert [(event.event_id, event.content) for event in events] == [
        ("root", "user: one\n\ntwo"),
        ("end", "user: tail"),
    ]
    assert events[-1].parent_id == "hidden"


def test_namespace_identity_is_bounded_and_separates_session_event_pairs():
    registry = SourceDefinitionRegistry((PI_EVENT_SOURCE_DEFINITION,))
    values = [("a:b", "c"), ("a", "b:c"), ("文" * 300, "事件" * 300)]
    identities = []
    for session_id, event_id in values:
        event = parse_pi_session(_archive([_message(event_id)], session_id=session_id))[0]
        identities.append(asyncio.run(registry.resolve(event)).name)
    assert len(set(identities)) == 3
    assert all(len(identity) <= 256 for identity in identities)
