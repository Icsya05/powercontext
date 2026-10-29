"""Page identity and whole-document validation boundaries."""

import asyncio
import hashlib
import io

import pytest
from pypdf import PdfWriter

from powercontext.sources import SourceDefinitionRegistry
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION, PDFDocumentInput, parse_pdf_document


@pytest.mark.parametrize(
    ("question", "page_text", "distractors", "expected_count"),
    [
        (
            "What were capital expenditures for Acme in fiscal 2024? "
            "Please explain the calculation using dollars rather than percentages, "
            "considering an analyst perspective and providing a concise response with supporting references.",
            "Consolidated cash flows\n2024 2023\nCapital expenditures 25 20\nDepreciation 10 9",
            (),
            1,
        ),
        ("What is FY2024?", "Consolidated cash flows\n2024 2023\nCapital expenditures 25 20", (), 1),
        (
            "income statements",
            "Consolidated statement of income\nRevenue 200",
            tuple(f"Income tax expense {index}" for index in range(20)),
            20,
        ),
        ("statements", "Consolidated statement of income", (), 1),
        ("flows", "Cash flow statement", (), 1),
        ("liabilities", "Liability 200", (), 1),
        ("geographies", "Geography and operations", (), 1),
        ("statement", "Consolidated statements of income", (), 1),
        ("flow", "Cash flows statement", (), 1),
        ("liability", "Liabilities 200", (), 1),
        ("geography", "Geographies and operations", (), 1),
        ("loss", "Losses from operations", (), 1),
        ("loss", "Loss from operations", tuple(f"Los {index}" for index in range(20)), 1),
        ("analysis", "Analysis of operations", tuple(f"Analysi {index}" for index in range(20)), 1),
        ("status", "Status of obligations", tuple(f"Statu {index}" for index in range(20)), 1),
        ("news", "News from operations", tuple(f"New {index}" for index in range(20)), 1),
        ("flow", "Flow from operations", tuple(f"Cashflow {index}" for index in range(20)), 1),
    ],
    ids=[
        "long-narrative",
        "fiscal-year",
        "plural-statement-among-tax-schedules",
        "plural-statement",
        "plural-flow",
        "plural-liability",
        "plural-geography",
        "reverse-statement",
        "reverse-flow",
        "reverse-liability",
        "reverse-geography",
        "reverse-loss",
        "protect-loss",
        "protect-analysis",
        "protect-status",
        "protect-news",
        "word-boundary",
    ],
)
def test_question_retrieves_concise_table_page(tmp_path, question, page_text, distractors, expected_count):
    """Natural inflections must retrieve exact pages without matching unrelated word fragments."""
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
                text=page_text,
            )
        )
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'pdf.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=EvidencePipeline()) as runtime:
            scope = await runtime.scopes.create(ScopeDraft(title="PDF", summary="Evidence", idempotency_key="pdf"))
            await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
            observation = project_source_for_transport(registry, source)
            await runtime.ingestion.submit(SubmitSourceObservation(scope_id=scope.scope_id, observation=observation))
            for number, text in enumerate(distractors, 3):
                other = await registry.resolve(
                    PDFPageInput(
                        document_id="ACME_2024_10K",
                        document_sha256="a" * 64,
                        page_number=number,
                        text=text,
                    )
                )
                await runtime.ingestion.submit(
                    SubmitSourceObservation(
                        scope_id=scope.scope_id,
                        observation=project_source_for_transport(registry, other),
                    )
                )
            memory = runtime.memory.for_scope(scope.scope_id)
            for _ in range(len(distractors) + 2):
                if not (await memory.flush()).processed:
                    break
            citations = await search_pdf_pages(
                memory,
                question,
                limit=20,
            )
            assert len(citations) == expected_count
            entries = [(await memory.get(GetMemoryEntryRequest(citation=citation))).entry for citation in citations]
            assert source.name in {entry.sources[0].source_id for entry in entries}

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
