from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.builtin.runtime import PrepareContextRequest
from powercontext.builtin.runtime.prepared_context import PreparedContextBuilder, PreparedMemoryCandidates


def group(scope: str, text: str) -> PreparedMemoryCandidates:
    ref = ArtifactRef(family="memory", artifact_id="original", revision=7)
    return PreparedMemoryCandidates(
        scope_id=scope,
        memory_ref=ref,
        hits=(
            MemoryHit(
                memory_ref=ref, entry_id="fact", entry_version_id="body-1", text=text, score=1.0, matched_by=("fts",)
            ),
        ),
    )


def build(query: str, groups: tuple[PreparedMemoryCandidates, ...], budget: int = 1200):
    return PreparedContextBuilder().build_scopes_result(
        request=PrepareContextRequest(query=query, max_bytes=budget, evidence_selection=True),
        current_scope_id="local",
        memory_candidates=groups,
    )


def test_query_selects_distinct_late_literal_sentences():
    text = (
        "Routine paperwork is archived. " * 80
        + "The violet thermometer reads 41 degrees. The orange meter reads 23 degrees."
    )
    first = build("violet thermometer", (group("local", text),))
    second = build("orange meter", (group("local", text),))
    assert "violet thermometer" in first.fragments[0].text
    assert "orange meter" in second.fragments[0].text
    assert first.fragments[0].start > 2000
    assert first.fragments != second.fragments


def test_same_text_across_scopes_keeps_both_exact_identities():
    result = build(
        "telescope",
        (group("local", "The telescope recorded a flare."), group("shared", "The telescope recorded a flare.")),
        4000,
    )
    assert {fragment.address.memory.scope_id for fragment in result.fragments} == {"local", "shared"}
    assert tuple(fragment.address for fragment in result.fragments) == result.origins


def test_escaped_unicode_budget_offsets_and_exact_boundary():
    text = '登记说明。\n海洋 station records "quoted" temperatures 🌊.\nOther material.'
    result = build("station temperatures", (group("local", text),))
    assert result.fragments
    for fragment in result.fragments:
        assert fragment.text == text[fragment.start : fragment.end]
        assert type(fragment.start) is int and type(fragment.end) is int
    assert result.context.content_bytes == len(result.context.content.encode("utf-8"))
    exact = build("station temperatures", (group("local", text),), result.context.content_bytes)
    assert exact.context == result.context
    smaller = build("station temperatures", (group("local", text),), result.context.content_bytes - 1)
    assert smaller.context.content_bytes <= result.context.content_bytes - 1
    body = json.loads(result.context.content.splitlines()[-2])
    assert body["trust"] == "untrusted_history"
    assert body["items"][0]["content"] == result.fragments[0].text


def test_long_unpunctuated_sentence_selects_a_late_window():
    text = "irrelevant " * 1000 + "magnesium channel blocks calcium influx"
    result = build("magnesium channel calcium", (group("local", text),))
    assert result.fragments and "magnesium channel" in result.fragments[0].text
    assert result.fragments[0].text == text[result.fragments[0].start : result.fragments[0].end]
    assert result.context.content_bytes <= 1200


@pytest.mark.parametrize("value", [1, "true", None])
def test_selection_flag_is_strict(value):
    with pytest.raises(ValidationError):
        PrepareContextRequest(query="query", evidence_selection=value)


def test_default_prepare_is_unchanged_by_explicit_false():
    builder = PreparedContextBuilder()
    groups = (group("local", "Ordinary source text."),)
    implicit = builder.build_scopes_result(
        request=PrepareContextRequest(query="source"), current_scope_id="local", memory_candidates=groups
    )
    explicit = builder.build_scopes_result(
        request=PrepareContextRequest(query="source", evidence_selection=False),
        current_scope_id="local",
        memory_candidates=groups,
    )
    assert implicit == explicit
    assert implicit.fragments == ()
