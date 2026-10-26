"""Lossless captured CSV records with document-scoped, stable identities."""

from __future__ import annotations

import csv
import io
import json
from typing import Self
from urllib.parse import quote

from pydantic import BaseModel, field_validator, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Encode both identity components independently without normalizing them."""
    if not document_id or document_id != document_id.strip():
        raise ValueError("document_id must be non-empty without surrounding whitespace")  # noqa: TRY003
    if not primary_key_value.strip():
        raise ValueError("primary key value must not be blank")  # noqa: TRY003
    identity = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("encoded CSV identity exceeds the source ID limit")  # noqa: TRY003
    return identity


def _validate_header(columns: tuple[str, ...], primary_key: str) -> None:
    if not columns or any(not column.strip() for column in columns):
        raise ValueError("CSV columns must not be empty or blank")  # noqa: TRY003
    if len(set(columns)) != len(columns):
        raise ValueError("CSV columns must be unique")  # noqa: TRY003
    if not primary_key or primary_key not in columns:
        raise ValueError("primary_key must exactly match a column")  # noqa: TRY003


class CSVDocumentInput(BaseModel):
    """Complete offline CSV bytes and the column identifying each record."""

    document_id: str
    primary_key: str
    content: bytes

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("document_id must be non-empty without surrounding whitespace")  # noqa: TRY003
        return value


class CSVRowInput(BaseModel):
    """One validated row, preserving the exact original column/value order."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]

    @model_validator(mode="after")
    def validate_row(self) -> Self:
        _validate_header(self.columns, self.primary_key)
        if len(self.values) != len(self.columns):
            raise ValueError("CSV row width differs from its header")  # noqa: TRY003
        if self.values[self.columns.index(self.primary_key)] != self.primary_key_value:
            raise ValueError("primary key value does not match the captured row")  # noqa: TRY003
        csv_row_source_id(self.document_id, self.primary_key_value)
        return self


class CSVRowSource(Source, CSVRowInput):
    """A durable captured row whose identity matches its document and key."""

    source_id: str
    materialization: SourceMaterialization = SourceMaterialization.CAPTURED

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        identity = csv_row_source_id(self.document_id, self.primary_key_value)
        if (
            self.name != identity
            or self.source_id != identity
            or self.materialization != SourceMaterialization.CAPTURED
        ):
            raise ValueError("CSV source name and ID must match the row identity")  # noqa: TRY003
        return self


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Validate the entire document before returning any captured records."""
    reader = csv.reader(io.StringIO(value.content.decode("utf-8-sig"), newline=""), strict=True)
    try:
        columns = tuple(next(reader))
        _validate_header(columns, value.primary_key)
        key_index = columns.index(value.primary_key)
        rows: list[CSVRowInput] = []
        keys: set[str] = set()
        for record in reader:
            if not record:
                continue
            if len(record) != len(columns):
                raise ValueError("CSV row width differs from its header")  # noqa: TRY003
            key = record[key_index]
            if key in keys:
                raise ValueError("CSV primary key values must be unique")  # noqa: TRY003
            rows.append(
                CSVRowInput(
                    document_id=value.document_id,
                    primary_key=value.primary_key,
                    primary_key_value=key,
                    columns=columns,
                    values=tuple(record),
                )
            )
            keys.add(key)
        return tuple(rows)
    except (StopIteration, csv.Error) as error:
        raise ValueError("invalid CSV document") from error  # noqa: TRY003


class CSVRowSourceAdapter:
    """Resolve and read captured CSV rows through the native registry."""

    input_class: type[CSVRowInput] = CSVRowInput
    name = "csv-row"
    source_class: type[CSVRowSource] = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        identity = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(name=identity, source_id=identity, **value.model_dump())

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput.model_validate(source.model_dump())


class CSVRowTextEvidenceProjection:
    """Expose complete row evidence independently of the source plugin."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class: type[CSVRowSource] = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type="csv-row",
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition[CSVRowInput, CSVRowSource, CSVRowInput](
    CSVRowSourceAdapter(), projections=(CSVRowTextEvidenceProjection(),)
)
