"""Page identity and whole-document validation boundaries."""

import asyncio
import hashlib
import io

import pytest
from pypdf import PdfWriter

from powercontext.sources import SourceDefinitionRegistry
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION, PDFDocumentInput, parse_pdf_document


def test_long_financial_question_retrieves_concise_table_page(tmp_path):
    """Narrative instructions must not exclude the table needed to answer a question."""
    from powercontext.builtin.artifacts.memory import MemoryEntryInput
    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import (
        BuiltinConfig,
        GetMemoryEntryRequest,
        SubmitSourceObservation,
        open_builtin_runtime,
    )
    from powercontext.builtin.scope import ScopeDraft
    from powercontext.sources import manifest_for_definition, project_source_for_transport
    from powercontext.sources.pdf_pages import PDFPageInput, search_pdf_pages
    from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY

    class EvidencePipeline:
        async def extract(self, request, /):
            return tuple(
                MemoryEntryInput(
                    kind="source-evidence",
                    text=item.projection(TEXT_EVIDENCE_PROJECTION_KEY)["content"],
                    sources=(item,),
                )
                for item in request.sources
            )

    async def scenario():
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        source = await registry.resolve(
            PDFPageInput(
                document_id="ACME_2024_10K",
                document_sha256="a" * 64,
                page_number=2,
                text="Consolidated cash flows\n2024 2023\nCapital expenditures 25 20\nDepreciation 10 9",
            )
        )
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'pdf.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=EvidencePipeline()) as runtime:
            scope = await runtime.scopes.create(ScopeDraft(title="PDF", summary="Evidence", idempotency_key="pdf"))
            await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
            observation = project_source_for_transport(registry, source)
            await runtime.ingestion.submit(SubmitSourceObservation(scope_id=scope.scope_id, observation=observation))
            memory = runtime.memory.for_scope(scope.scope_id)
            await memory.flush()
            citations = await search_pdf_pages(
                memory,
                "What were capital expenditures for Acme in fiscal 2024? "
                "Please explain the calculation using dollars rather than percentages, "
                "considering an analyst perspective and providing a concise response with supporting references.",
                limit=20,
            )
            assert len(citations) == 1
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert entry.sources[0].source_id == source.name

    asyncio.run(scenario())


def test_long_document_names_are_preserved_with_bounded_page_identity():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    document_id = "文档:/" * 100
    page = parse_pdf_document(PDFDocumentInput(document_id=document_id, content=buffer.getvalue()))[0]
    assert page.document_sha256 == hashlib.sha256(buffer.getvalue()).hexdigest()
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(page))
    assert len(source.name) <= 256
    assert asyncio.run(registry.read(source)) == page


@pytest.mark.parametrize("document_id", ["", " \t\n"])
def test_blank_document_identity_is_rejected_even_before_page_extraction(document_id):
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id=document_id, content=b"not PDF"))


def test_nonempty_password_protection_is_a_value_error():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt(user_password="secret", owner_password="owner")  # noqa: S106 - Synthetic PDF fixture passwords.
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="locked", content=buffer.getvalue()))
