"""CSV boundaries that must preserve evidence rather than normalize it."""

import asyncio

import pytest

from powercontext.sources import SourceDefinitionRegistry, SourceMaterialization
from powercontext.sources.csv_rows import (
    CSV_ROW_SOURCE_DEFINITION,
    CSVDocumentInput,
    CSVRowInput,
    csv_row_source_id,
    parse_csv_document,
)


def test_identity_length_is_checked_after_percent_encoding() -> None:
    assert csv_row_source_id("d", "x" * 250) == "csv:d:" + "x" * 250
    with pytest.raises(ValueError):
        csv_row_source_id("d", "x" * 251)
    assert csv_row_source_id("中文", "%:/") == "csv:%E4%B8%AD%E6%96%87:%25%3A%2F"
    with pytest.raises(ValueError):
        csv_row_source_id("d", "中" * 28)


@pytest.mark.parametrize(
    ("document_id", "primary_key", "content"),
    [
        ("", "id", b"id,name\n"),
        (" d", "id", b"id,name\n"),
        ("d", "", b"id,name\n"),
        ("d", "missing", b"id,name\n"),
        ("d", "id", b"\nid,name\n"),
        ("d", "id", b'id\n""\n'),
        ("d", "id", b'id,name\n1,valid\n2,"bad"tail\n'),
        ("d", "id", b"id,name\n1,valid\n \t,blank\n"),
    ],
)
def test_invalid_documents_raise_before_exposing_rows(document_id, primary_key, content) -> None:
    with pytest.raises(ValueError):
        parse_csv_document(CSVDocumentInput(document_id=document_id, primary_key=primary_key, content=content))


def test_empty_physical_records_do_not_erase_empty_fields_or_unicode() -> None:
    rows = parse_csv_document(
        CSVDocumentInput(
            document_id="表格", primary_key=" id ", content=' id ,内容\r\n\r\n 01 ,""\r\n\r\n02,中文\r\n'.encode()
        )
    )
    assert [row.values for row in rows] == [(" 01 ", ""), ("02", "中文")]
    registry = SourceDefinitionRegistry((CSV_ROW_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(rows[0]))
    assert source.materialization is SourceMaterialization.CAPTURED
    assert asyncio.run(registry.read(source)) == rows[0]


@pytest.mark.parametrize(
    ("columns", "values", "primary_key_value"),
    [
        (("id", "name"), ("1",), "1"),
        (("id", "id"), ("1", "1"), "1"),
        (("id", " "), ("1", "x"), "1"),
        (("name",), ("1",), "1"),
        (("id",), ("2",), "1"),
    ],
)
def test_direct_row_input_cannot_capture_inconsistent_evidence(columns, values, primary_key_value) -> None:
    with pytest.raises(ValueError):
        CSVRowInput(
            document_id="doc", primary_key="id", primary_key_value=primary_key_value, columns=columns, values=values
        )
