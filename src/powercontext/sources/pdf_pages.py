"""Complete offline PDF page evidence and exact scoped Memory retrieval."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from pypdf import PdfReader

from powercontext.builtin.artifacts.memory.models import MemoryCitation, MemoryHit
from powercontext.builtin.artifacts.search import analyze_fts_query
from powercontext.builtin.runtime.models import GetMemoryEntryRequest, SearchMemoryRequest
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import ScopedMemoryApplication


class PDFDocumentInput(BaseModel):
    """Original PDF bytes, without pre-extracted pages or evidence labels."""

    document_id: str
    content: bytes

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("PDF document_id must not be blank")  # noqa: TRY003
        return value


class PDFPageInput(BaseModel):
    """One physical page tied to an exact full-document revision."""

    document_id: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(strict=True, ge=1)
    text: str

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return PDFDocumentInput.validate_document_id(value)


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Read every page before exposing a result; normalize parser failures."""
    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a nonempty user password")  # noqa: TRY003, TRY301
        return tuple(
            PDFPageInput(
                document_id=value.document_id,
                document_sha256=digest,
                page_number=index,
                text=page.extract_text() or "",
            )
            for index, page in enumerate(reader.pages, 1)
        )
    except Exception as error:
        raise ValueError("PDF cannot be completely parsed") from error  # noqa: TRY003


class PDFPageSource(Source, PDFPageInput):
    """Captured original page text rather than an answer or generated summary."""


class PDFPageSourceAdapter:
    input_class: type[PDFPageInput] = PDFPageInput
    source_class: type[PDFPageSource] = PDFPageSource
    name = "pdf-page"

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        # Hash the unbounded external document ID; retain its exact value in evidence.
        document_key = hashlib.sha256(value.document_id.encode("utf-8")).hexdigest()
        identity = f"pdf:{document_key}:{value.document_sha256}:{value.page_number}"
        return PDFPageSource(name=identity, materialization=SourceMaterialization.CAPTURED, **value.model_dump())

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput.model_validate(source.model_dump())


class PDFPageTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class: type[PDFPageSource] = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition[PDFPageInput, PDFPageSource, PDFPageInput](
    PDFPageSourceAdapter(), projections=(PDFPageTextEvidenceProjection(),)
)


def _plural_key(term: str) -> str:
    """Conflate light English plurals without stripping singular -ss, -is or -us."""
    if term in {"news", "series", "species"}:
        return term
    if len(term) > 4 and term.endswith("ies"):
        return f"{term[:-3]}y"
    if len(term) > 4 and term.endswith(("sses", "ches", "shes", "xes", "zes")):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "is", "us")):
        return term[:-1]
    return term


def _short_query_plural(term: str) -> str | None:
    """Offer at most one plural spelling when a short query has no other anchors."""
    if (
        len(term) < 4
        or not term.isalpha()
        or term in {"news", "series", "species"}
        or term.endswith(("is", "us"))
        or _plural_key(term) != term
    ):
        return None
    if term.endswith("y") and term[-2] not in "aeiou":
        return f"{term[:-1]}ies"
    return f"{term}es" if term.endswith(("s", "x", "z", "ch", "sh")) else f"{term}s"


def _rank_pages(hits: tuple[MemoryHit, ...], question: str) -> list[MemoryHit]:
    """BM25 over the actual candidate pages, with deterministic identity ties."""
    terms = {_plural_key(term) for term in re.findall(r"[a-z]+|\d+", analyze_fts_query(question))}
    counts = [Counter(_plural_key(term) for term in re.findall(r"[a-z]+|\d+", hit.text.lower())) for hit in hits]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / max(len(lengths), 1) or 1
    frequencies = {term: sum(term in count for count in counts) for term in terms}
    scores = []
    for index, (hit, count) in enumerate(zip(hits, counts, strict=True)):
        score = 0.0
        for term in terms:
            frequency = count[term]
            if frequency:
                inverse = math.log(1 + (len(hits) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * lengths[index] / average))
        scores.append((score, hit))
    scores.sort(key=lambda pair: (-pair[0], pair[1].memory_ref.artifact_id, pair[1].entry_id, pair[1].entry_version_id))
    return [hit for _, hit in scores]


async def search_pdf_pages(
    memory: ScopedMemoryApplication, question: str, limit: int = 10
) -> tuple[MemoryCitation, ...]:
    """Return actual persisted distinct-page citations, never synthetic references."""
    if type(limit) is not int or limit < 1 or not question.strip():
        raise ValueError("question must be nonblank and limit must be a positive integer")  # noqa: TRY003
    # A table may contain just a few content words from a long natural-language
    # question. The shared FTS admission floor measures whole-query coverage,
    # so collect short lexical views before ranking against the complete question.
    terms = tuple(dict.fromkeys(analyze_fts_query(question).split()))
    queries = [question]
    if len(terms) > 2:
        queries.extend(" ".join(terms[index : index + 2]) for index in range(0, len(terms), 2))
    # The stored FTS index remains exact. Alternate forms need their own lexical
    # views before the page-local ranker can compare the same inflection keys.
    inflections = tuple(dict.fromkeys(_plural_key(term) for term in terms if _plural_key(term) != term))
    if len(terms) <= 2:
        inflections = tuple(
            dict.fromkeys((
                *inflections,
                *(plural for term in terms if (plural := _short_query_plural(term)) is not None),
            ))
        )
    queries.extend(" ".join(inflections[index : index + 2]) for index in range(0, len(inflections), 2))
    # Fiscal-year notation is common in questions, while table headers usually
    # contain bare years. Retain every original view for pages using the prefix.
    years = tuple(dict.fromkeys(re.findall(r"\bfy(\d{4})\b", question, flags=re.IGNORECASE)))
    queries.extend(" ".join(years[index : index + 2]) for index in range(0, len(years), 2))
    candidates: dict[tuple[str, str, str], MemoryHit] = {}
    for query in queries:
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=max(100, limit * 10)))
        for hit in page.hits:
            identity = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            candidates.setdefault(identity, hit)
    selected: list[MemoryCitation] = []
    seen: set[str] = set()
    for hit in _rank_pages(tuple(candidates.values()), question):
        citation = MemoryCitation(
            memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
        )
        entry = await memory.get(GetMemoryEntryRequest(citation=citation))
        references = [source for source in entry.entry.sources if source.source_type == "pdf-page"]
        if len(references) != 1 or references[0].source_id in seen:
            continue
        seen.add(references[0].source_id)
        selected.append(citation)
        if len(selected) == limit:
            break
    return tuple(selected)
