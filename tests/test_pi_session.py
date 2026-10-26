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


@pytest.mark.asyncio
async def test_off_branch_record_mutation_is_detected_before_new_submission(tmp_path):
    from selftest_support.runtime_fixture import run_connector_persisted

    from powercontext.sources import ConnectorBinding
    from powercontext.sources.pi_session import PiSessionConnector

    path = tmp_path / "session.jsonl"
    records = [_message(), _message("left", "root", "left"), _message("right", "root", "right")]
    path.write_bytes(_archive(records).content)
    binding = ConnectorBinding(
        scope_id="pi-test", binding_id="pi", connector_name="pi-session-history", connector_version="1"
    )
    first, _ = await run_connector_persisted(
        tmp_path, PI_EVENT_SOURCE_DEFINITION, PiSessionConnector(path, "left"), binding
    )
    records[1]["extra"] = "rewritten off-branch metadata"
    path.write_bytes(_archive(records).content)
    with pytest.raises(ValueError):
        await run_connector_persisted(tmp_path, PI_EVENT_SOURCE_DEFINITION, PiSessionConnector(path, "right"), binding)
    del records[1]["extra"]
    path.write_bytes(_archive(records).content)
    repaired, entries = await run_connector_persisted(
        tmp_path, PI_EVENT_SOURCE_DEFINITION, PiSessionConnector(path, "right"), binding
    )
    assert repaired.previous_checkpoint == first.committed_checkpoint
    assert len(repaired.items) == 1 and len(entries) == 3


@pytest.mark.asyncio
async def test_failed_partial_ingestion_keeps_checkpoint_and_retry_is_idempotent(tmp_path):
    from selftest_support.runtime_fixture import RuntimeCheckpoints, RuntimeSink

    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts, open_builtin_runtime
    from powercontext.builtin.scope import ScopeDraft
    from powercontext.sources import ConnectorBinding, manifest_for_definition
    from powercontext.sources.connectors import ConnectorLifecycle
    from powercontext.sources.pi_session import PiSessionConnector

    path = tmp_path / "partial.jsonl"
    path.write_bytes(_archive([_message(), _message("second", "root", "second")]).content)
    config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'partial.db'}"))
    registry = SourceDefinitionRegistry((PI_EVENT_SOURCE_DEFINITION,))
    async with open_builtin_runtime(config) as runtime:
        scope = await runtime.scopes.create(
            ScopeDraft(title="Pi", summary="Failure recovery", idempotency_key="pi-failure")
        )
        await runtime.ingestion.register(manifest_for_definition(PI_EVENT_SOURCE_DEFINITION))
        binding = ConnectorBinding(
            scope_id=scope.scope_id, binding_id="pi", connector_name="pi-session-history", connector_version="1"
        )
        checkpoints = RuntimeCheckpoints(runtime)
        sink = RuntimeSink(runtime, registry)

        class FailSecond:
            async def submit(self, binding, item_id, definition_name, value):
                if value.event_id == "second":
                    raise RuntimeError("injected ingestion failure")  # noqa: TRY003
                return await sink.submit(binding, item_id, definition_name, value)

        connector = PiSessionConnector(path)
        with pytest.raises(RuntimeError):
            await ConnectorLifecycle(sink=FailSecond(), checkpoints=checkpoints).run(connector, binding)
        assert await checkpoints.load(binding) is None
    async with open_builtin_runtime(config) as runtime:
        checkpoints = RuntimeCheckpoints(runtime)
        lifecycle = ConnectorLifecycle(sink=RuntimeSink(runtime, registry), checkpoints=checkpoints)
        recovered = await lifecycle.run(PiSessionConnector(path), binding)
        assert recovered.committed_checkpoint is not None
        assert (await lifecycle.run(PiSessionConnector(path), binding)).items == ()
    async with open_builtin_contexts(config) as contexts:
        journal = await (await contexts.get(scope.scope_id)).sources.journal.entries()
        assert len(journal) == 2
