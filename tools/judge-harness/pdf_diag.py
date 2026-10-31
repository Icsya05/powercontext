"""Diagnose where the PDF retrieval loses the annotated evidence pages."""

from __future__ import annotations

import asyncio
import json
import re
import sys
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
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY  # noqa: E402
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


async def main() -> None:
    rows = [
        json.loads(line)
        for line in (FINANCEBENCH / "data/financebench_open_source.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [row for row in rows if row["doc_name"] in DOCUMENTS]

    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    page_text: dict[tuple[str, int], str] = {}
    for name in DOCUMENTS:
        for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name))):
            source = await registry.resolve(page)
            observations.append(project_source_for_transport(registry, source))
            page_text[(name, page.page_number)] = page.text

    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        config, scope_id, stored = await persist(Path(directory), PDF_PAGE_SOURCE_DEFINITION, observations)
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope_id)
            for row in questions:
                name = row["doc_name"]
                question = row["question"]
                annotated = sorted({int(item["evidence_page_num"]) + 1 for item in row["evidence"]})
                # 1) does the plain FTS search see the annotated pages at all?
                terms = tuple(dict.fromkeys(analyze_fts_query(question).split()))
                seen: set[tuple[str, int]] = set()
                fts_ranks: dict[tuple[str, int], int] = {}
                queries = [question]
                if len(terms) > 2:
                    queries.extend(" ".join(terms[i : i + 2]) for i in range(0, len(terms), 2))
                for query in queries:
                    page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=200))
                    for hit in page.hits:
                        entry = (await memory.get(GetMemoryEntryRequest(
                            citation=__import__("powercontext.builtin.artifacts.memory.models", fromlist=["MemoryCitation"]).MemoryCitation(
                                memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
                            )
                        ))).entry
                        for reference in entry.sources:
                            metadata = stored[reference.source_id].projection(TEXT_EVIDENCE_PROJECTION_KEY)["metadata"]
                            key = (metadata["document_id"], metadata["page_number"])
                            if key not in seen:
                                seen.add(key)
                                fts_ranks[key] = len(seen)
                hits = [page for page in annotated if (name, page) in seen]
                print("=" * 110)
                print(f"{row['financebench_id']} [{name}] {question[:150]}")
                print(f"  标注页: {annotated}")
                print(f"  FTS 候选集命中标注页: {hits}  (候选集大小 {len(seen)})")
                print(f"  标注页在 FTS 候选集中的名次: {[fts_ranks.get((name, p)) for p in annotated]}")
                if not hits:
                    gold_text = page_text.get((name, annotated[0]), "") if annotated else ""
                    gold_terms = set(TOKEN.findall(gold_text.lower()))
                    q_terms = set(TOKEN.findall(question.lower()))
                    print(f"  !! 标注页根本没被 FTS 召回。页首: {gold_text[:200]!r}")
                    print(f"     页面独有词: {sorted(gold_terms - q_terms)[:18]}")
                    print(f"     查询词未出现在该页: {sorted(q_terms - gold_terms)[:18]}")


if __name__ == "__main__":
    asyncio.run(main())
