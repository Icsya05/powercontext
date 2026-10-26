"""Page identity and whole-document validation boundaries."""

import asyncio
import hashlib
import io

import pytest
from pypdf import PdfWriter

from powercontext.sources import SourceDefinitionRegistry
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION, PDFDocumentInput, parse_pdf_document


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
