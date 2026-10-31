"""Fast diagnosis of the PDF retrieval, under both scope models.

The stored entry text is exactly ``DOCUMENT_ID\\nPAGE_TEXT`` (stripped), so a
page can be identified from a search hit without a per-hit Memory read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

PRODUCT = Path(r"D:\Tools\pc-prelim")
COMPETITION = PRODUCT / "competition"
FINANCEBENCH = Path(
    r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb"
)
PUBLIC_PDF = (
    COMPETITION / "challenges/source-03-pdf-retrieval/workload/public/pdfs/PEPSICO_2022_10K.pdf"
)
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(COMPETITION))

from powercontext.builtin.artifacts.search import analyze_fts_query  # noqa: E402
from powercontext.builtin.artifacts.memory.models import MemoryCitation  # noqa: E402
from powercontext.builtin.runtime import (  # noqa: E402
    GetMemoryEntryRequest,
    SearchMemoryRequest,
    open_builtin_runtime,
)
from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport  # noqa: E402
from powercontext.sources.pdf_pages import (  # noqa: E402
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
    search_pdf_pages,
)
from selftest_support.source_acceptance import persist  # noqa: E402

DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)
TOKEN = re.compile(r"[a-z]+|\d+")


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in (FINANCEBENCH / "data/financebench_open_source.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [row for row in rows if row["doc_name"] in DOCUMENTS]

    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    text_to_page: dict[str, tuple[str, int]] = {}
    for name in DOCUMENTS:
        for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name))):
            source = await registry.resolve(page)
            observations.append(project_source_for_transport(registry, source))
            text_to_page[(name + "\n" + page.text).strip()] = (name, page.page_number)

    with tempfile.TemporaryDirectory() as directory:
        config, scope_id, stored = await persist(
            Path(directory), PDF_PAGE_SOURCE_DEFINITION, observations
        )
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope_id)
            print(f"{'id':<28}{'doc':<22}{'fts?':>6}{'rank':>8}{'top20?':>8}{'docInTop20':>12}  question")
            print("-" * 150)
            for row in questions:
                name = row["doc_name"]
                question = row["question"]
                annotated = sorted({int(item["evidence_page_num"]) + 1 for item in row["evidence"]})
                terms = tuple(dict.fromkeys(analyze_fts_query(question).split()))
                queries = [question]
                if len(terms) > 2:
                    queries.extend(" ".join(terms[i : i + 2]) for i in range(0, len(terms), 2))
                seen: dict[tuple[str, int], int] = {}
                for query in queries:
                    page = await memory.search(
                        SearchMemoryRequest(query=query, mode="fts", limit=200)
                    )
                    for hit in page.hits:
                        key = text_to_page.get((hit.text or "").strip())
                        if key is not None and key not in seen:
                            seen[key] = len(seen) + 1
                citations = await search_pdf_pages(memory, question, limit=args.limit)
                returned = set()
                for citation in citations:
                    entry = (
                        await memory.get(GetMemoryEntryRequest(citation=MemoryCitation(
                            memory_ref=citation.memory_ref,
                            entry_id=citation.entry_id,
                            entry_version_id=citation.entry_version_id,
                        )))
                    ).entry
                    key = text_to_page.get((entry.text or "").strip())
                    if key is not None:
                        returned.add(key)
                gold_hits = [(name, p) for p in annotated]
                in_fts = [key in seen for key in gold_hits]
                ranks = [seen.get(key) for key in gold_hits]
                in_top = [key in returned for key in gold_hits]
                docs_in_top = sorted({doc for doc, _ in returned})
                print(
                    f"{row['financebench_id']:<28}{name:<22}"
                    f"{sum(in_fts):>6}{str(ranks):>8}{sum(in_top):>8}"
                    f"{len(docs_in_top):>12}  {question[:70]}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
