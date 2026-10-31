"""Complete offline PDF page evidence and exact scoped Memory retrieval."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from pypdf import PdfReader

from powercontext.builtin.artifacts.memory.models import MemoryCitation, MemoryHit
from powercontext.builtin.artifacts.search import analyze_fts_query
from powercontext.builtin.runtime.models import (
    GetMemoryEntryRequest,
    MemoryEntriesPage,
    MemoryEntryRecord,
    SearchMemoryRequest,
)
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

    The Runtime resolves ``auto`` to the hybrid channel when the deployment has
    a semantic one and to the lexical channel when it does not.  Its own
    ranking is kept: a page-local lexical re-sort would undo the fusion the
    Runtime performed, and widening the pool with alternate word forms only
    dilutes it.

    When the deployment served a semantic channel, the lexical channel is asked
    as well and the two orderings are fused.  The native full-text index on its
    own is the stronger of the two on financial reports, so keeping it in the
    result protects the lexical ranking while the semantic candidates get their
    own chance to enter.
    """

    depth = max(100, limit * 10)
    page = await memory.search(SearchMemoryRequest(query=question, mode="auto", limit=depth))
    identities: dict[str, Counter[str]] = {}
    for hit in page.hits:
        document = _document_identity(hit.text or "")
        if document:
            identities.setdefault(document, _document_terms(document))
    if page.mode == "fts":
        return tuple(page.hits), identities

    lexical = await memory.search(SearchMemoryRequest(query=question, mode="fts", limit=depth))
    for hit in lexical.hits:
        document = _document_identity(hit.text or "")
        if document:
            identities.setdefault(document, _document_terms(document))
    return _fuse_hit_orders(page.hits, lexical.hits), identities


def _fuse_hit_orders(primary: Sequence[MemoryHit], secondary: Sequence[MemoryHit]) -> tuple[MemoryHit, ...]:
    """Fuse two ranked page lists with reciprocal rank fusion."""

    scores: dict[tuple[str, str, str], float] = {}
    order: list[tuple[str, str, str]] = []
    hits: dict[tuple[str, str, str], MemoryHit] = {}
    for ranking in (primary, secondary):
        for rank, hit in enumerate(ranking, start=1):
            identity = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            if identity not in hits:
                hits[identity] = hit
                order.append(identity)
            scores[identity] = scores.get(identity, 0.0) + 1.0 / (60 + rank)
    order.sort(key=lambda identity: (-scores[identity], identity))
    return tuple(hits[identity] for identity in order)


_PDF_QUERY_STOPWORDS = frozenset([
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "based",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "s",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "which",
    "who",
    "why",
    "with",
    "within",
    "would",
    "your",
    "you",
    "if",
    "not",
    "please",
    "state",
    "then",
    "like",
    "shown",
    "using",
    "show",
    "use",
    "line",
    "items",
    "information",
    "answer",
    "address",
    "question",
    "round",
    "places",
    "decimal",
    "two",
    "much",
    "many",
    "does",
    "do",
    "did",
    "can",
    "will",
    "about",
    "above",
    "below",
    "between",
    "out",
    "over",
    "under",
    "each",
    "all",
    "any",
    "may",
    "also",
    "more",
    "most",
    "some",
    "such",
    "only",
    "other",
    "fy",
    "fiscal",
    "year",
    "data",
    "report",
])
_PDF_PAGE_ID = re.compile(r"pdf:[0-9a-f]{64}:[0-9a-f]{64}:([1-9]\d*)\Z")


def _pdf_word_keys(text: str) -> list[str]:
    """Share inflected English words through a bounded prefix channel."""
    return [term[:5] for term in re.findall(r"[a-z]+", text.lower())]


@dataclass(frozen=True)
class _PDFSearchPage:
    hit: MemoryHit
    page_number: int
    counts: Counter[str]
    heading_terms: frozenset[str]
    financial_table: bool


def _pdf_search_page(hit: MemoryHit, record: MemoryEntryRecord) -> _PDFSearchPage | None:
    sources = [source for source in record.entry.sources if source.source_type == "pdf-page"]
    if len(sources) != 1 or (match := _PDF_PAGE_ID.fullmatch(sources[0].source_id)) is None:
        return None
    _, separator, text = record.entry.text.partition("\n")
    if not separator:
        return None
    text = re.sub(r"^\s*t\s*able\s+of\s+contents\s*", "", text, flags=re.IGNORECASE)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    titles = []
    for line in lines:
        words = line.split()
        if (
            1 < len(_pdf_word_keys(line)) <= 10
            and not re.search(r"\d", line)
            and (line.isupper() or sum(word[0].isupper() for word in words) / len(words) >= 0.5)
        ):
            titles.append(line)
    statement = re.search(
        r"consolidated\s+(?:statements?\s+of|balance\s+sheets?)",
        " ".join(text.split()[:40]),
        re.IGNORECASE,
    )
    note_table = any(
        re.search(r"notes?\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements?", line, re.IGNORECASE)
        for line in lines[:6]
    )
    tokens = re.findall(r"[a-z]+|\d+", text.lower())
    numeric_share = sum(term.isdigit() for term in tokens) / max(1, len(tokens))
    return _PDFSearchPage(
        hit=hit,
        page_number=int(match[1]),
        counts=Counter(_pdf_word_keys(text)),
        heading_terms=frozenset(_pdf_word_keys(" ".join(titles))),
        financial_table=bool(statement or (note_table and numeric_share >= 0.15)),
    )


def _rank_pdf_report(pages: Sequence[_PDFSearchPage], question: str, document: str) -> tuple[MemoryHit, ...]:
    """Rank actual report candidates by body, headings and financial structure."""
    terms = set(_pdf_word_keys(question)) - {word[:5] for word in _PDF_QUERY_STOPWORDS}
    terms.difference_update(_pdf_word_keys(document))
    if not terms:
        return tuple(page.hit for page in pages)
    frequency = Counter(term for page in pages for term in page.counts)
    weights = {term: math.log(1 + (len(pages) - frequency[term] + 0.5) / (frequency[term] + 0.5)) for term in terms}
    scored: list[tuple[float, _PDFSearchPage]] = []
    for page in pages:
        matched = terms.intersection(page.counts)
        if not matched:
            continue
        length = sum(page.counts.values())
        body = sum(
            weights[term] * page.counts[term] * 2.2 / (page.counts[term] + 1.2 * (0.25 + 0.75 * length / 500))
            for term in matched
        )
        heading = sum(weights[term] for term in terms.intersection(page.heading_terms))
        score = (body + 2 * heading) * (4 if page.financial_table else 1)
        # Main report sections precede exhibits; this prior decays continuously.
        score /= (page.page_number + 20) / 20
        scored.append((score, page))
    scored.sort(key=lambda item: (-item[0], item[1].page_number, item[1].hit.entry_id))
    return tuple(page.hit for _, page in scored)


async def _search_pdf_report(
    memory: ScopedMemoryApplication, document: str, question: str, snapshot: MemoryEntriesPage
) -> tuple[MemoryHit, ...]:
    """Retrieve the named report without the long-question admission floor.

    Listing the current scope provides source identities and an exact candidate
    bound. Candidates still come from public Memory.search; the single identifier
    is present in every page projection, including short financial statements.
    The linear scope read is request-local, so no cache survives revisions or
    crosses scopes. No page text or annotation is loaded outside Memory.
    """
    records = {
        (record.entry.entry_id, record.entry.entry_version_id): record
        for record in snapshot.entries
        if _document_identity(record.entry.text) == document
    }
    if not records or not analyze_fts_query(document):
        return ()
    candidates = await memory.search(SearchMemoryRequest(query=document, mode="fts", limit=len(snapshot.entries)))
    pages = []
    for hit in candidates.hits:
        record = records.get((hit.entry_id, hit.entry_version_id))
        if record is not None and (page := _pdf_search_page(hit, record)) is not None:
            pages.append(page)
    return _rank_pdf_report(pages, question, document)


async def search_pdf_pages(
    memory: ScopedMemoryApplication, question: str, limit: int = 10
) -> tuple[MemoryCitation, ...]:
    """Return actual persisted distinct-page citations, never synthetic references."""
    if type(limit) is not int or limit < 1 or not question.strip():
        raise ValueError("question must be nonblank and limit must be a positive integer")  # noqa: TRY003
    # Discover reports before querying: a long question can reject every page at
    # the lexical admission floor, leaving no seed hit from which to recover.
    snapshot = await memory.list()
    identities = {}
    for record in snapshot.entries:
        if sum(source.source_type == "pdf-page" for source in record.entry.sources) != 1:
            continue
        document = _document_identity(record.entry.text)
        if document:
            identities.setdefault(document, _document_terms(document))
    question_terms = {_plural_key(term) for term in re.findall(r"[a-z]+|\d+", question.lower())}
    selected_document = _select_document(question_terms, identities)
    if selected_document is None and len(identities) == 1:
        selected_document = next(iter(identities))
    if selected_document is not None and analyze_fts_query(selected_document):
        ranked = await _search_pdf_report(memory, selected_document, question, snapshot)
    else:
        ranked, _ = await _gather_pdf_pages(memory, question, limit)
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
