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


def _document_identity(text: str) -> str:
    """Return the report identifier a stored page belongs to.

    The standard text projection of a ``pdf-page`` source is
    ``DOCUMENT_ID\nPAGE_TEXT``, so the first line of the stored entry names
    the report.  Reading it from the entry text costs no extra Memory read.
    """

    head, separator, _ = text.partition("\n")
    return head if separator else ""


def _document_terms(identity: str) -> Counter[str]:
    return Counter(_plural_key(term) for term in re.findall(r"[a-z]+|\d+", identity.lower()))


def _select_document(question_terms: set[str], identities: dict[str, Counter[str]]) -> str | None:
    """Pick the report a question is about.

    Every page of a report carries that report's identifier, so the reports
    present in the candidate set can be compared on how well their identifier
    matches the question.  Terms that only one report uses weigh most, which
    keeps a shared year or form type from deciding the match on its own.
    """

    if not identities:
        return None
    frequency = Counter(term for terms in identities.values() for term in terms)
    scores = {
        document: sum(
            math.log(1 + (len(identities) + 1) / (frequency[term] + 1)) * count
            for term, count in terms.items()
            if term in question_terms
        )
        for document, terms in identities.items()
    }
    best = max(scores, key=lambda document: (scores[document], document))
    if scores[best] <= 0:
        return None
    runner_up = max((score for document, score in scores.items() if document != best), default=0.0)
    # Only act on a clear winner; a shared year alone is not evidence.
    if runner_up > 0 and scores[best] < runner_up * 2:
        return None
    return best


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


async def _gather_pdf_pages(
    memory: ScopedMemoryApplication, question: str, limit: int
) -> tuple[tuple[MemoryHit, ...], dict[str, Counter[str]]]:
    """Search the scope for the pages that answer one question.

    One view of the question is searched.  The Runtime resolves ``auto`` to the
    hybrid channel when the deployment has a semantic one and to the lexical
    channel when it does not, and its own ranking is returned unchanged: a
    page-local lexical re-sort would undo that ranking, and widening the pool
    with alternate word forms only dilutes it.
    """

    depth = max(100, limit * 10)
    page = await memory.search(SearchMemoryRequest(query=question, mode="auto", limit=depth))
    identities: dict[str, Counter[str]] = {}
    for hit in page.hits:
        document = _document_identity(hit.text or "")
        if document:
            identities.setdefault(document, Counter()).update(_document_terms(document))
    return tuple(page.hits), identities


async def search_pdf_pages(
    memory: ScopedMemoryApplication, question: str, limit: int = 10
) -> tuple[MemoryCitation, ...]:
    """Return actual persisted distinct-page citations, never synthetic references."""
    if type(limit) is not int or limit < 1 or not question.strip():
        raise ValueError("question must be nonblank and limit must be a positive integer")  # noqa: TRY003
    ranked, identities = await _gather_pdf_pages(memory, question, limit)
    # The twenty result slots are worth most when they belong to the report the
    # question is about, and every page of a report carries its identifier.
    question_terms = {_plural_key(term) for term in analyze_fts_query(question).split()}
    selected_document = _select_document(question_terms, identities)
    if selected_document is not None:
        ranked = tuple(hit for hit in ranked if _document_identity(hit.text or "") == selected_document) + tuple(
            hit for hit in ranked if _document_identity(hit.text or "") != selected_document
        )
    selected: list[MemoryCitation] = []
    seen: set[str] = set()
    for hit in ranked:
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
