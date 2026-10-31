"""Measure the PDF retrieval under both scope models.

The task statement says the judge retrieves "from the document set of the same
data partition" and that "different document sets are stored in separate
databases".  That is ambiguous in two directions, so measure both:

  one_scope : all five reports in one scope (the harder model)
  per_doc   : one scope per report (the reading the wording supports)

Everything else - the pages, the annotations, the limit - is the hidden
workload exactly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

PRODUCT = Path(os.environ.get("PRODUCT_DIR", r"D:\Tools\pc-prelim"))
COMPETITION = Path(os.environ.get("COMPETITION_DIR", str(PRODUCT / "competition")))
FINANCEBENCH = Path(
    os.environ.get(
        "FB_DIR",
        r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb",
    )
)
PUBLIC_PDF = Path(
    os.environ.get(
        "PUBLIC_PDF",
        str(COMPETITION / "challenges/source-03-pdf-retrieval/workload/public/pdfs/PEPSICO_2022_10K.pdf"),
    )
)
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(COMPETITION))

from powercontext.builtin.runtime import (  # noqa: E402
    GetMemoryEntryRequest,
    open_builtin_runtime,
)
from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport  # noqa: E402
from powercontext.sources.pdf_pages import (  # noqa: E402
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
    search_pdf_pages,
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


async def build_observations() -> tuple[list, dict]:
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    pages_by_doc: dict[str, list] = {}
    for name in DOCUMENTS:
        pages = parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name)))
        pages_by_doc[name] = pages
        for page in pages:
            source = await registry.resolve(page)
            observations.append(project_source_for_transport(registry, source))
    return observations, pages_by_doc


async def run_model(model: str, observations, questions, limit: int) -> dict:
    results: dict[str, list[tuple[int, int]]] = {}
    detail = []
    with tempfile.TemporaryDirectory() as directory:
        if model == "one_scope":
            groups = [(None, observations)]
        else:
            by_document: dict[str, list] = {}
            for observation in observations:
                metadata = observation.projection(TEXT_EVIDENCE_PROJECTION_KEY)["metadata"]
                by_document.setdefault(str(metadata["document_id"]), []).append(observation)
            groups = list(by_document.items())
        for document_key, group in groups:
            config, scope_id, stored = await persist(
                Path(directory) / (document_key or "all"), PDF_PAGE_SOURCE_DEFINITION, group
            )
            async with open_builtin_runtime(config) as runtime:
                memory = runtime.memory.for_scope(scope_id)
                for row in questions:
                    name = row["doc_name"]
                    if model == "per_doc" and name != document_key:
                        continue
                    citations = await search_pdf_pages(memory, row["question"], limit=limit)
                    returned: set[tuple[str, int]] = set()
                    for citation in citations:
                        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                        for reference in entry.sources:
                            metadata = stored[reference.source_id].projection(TEXT_EVIDENCE_PROJECTION_KEY)["metadata"]
                            returned.add((metadata["document_id"], metadata["page_number"]))
                    annotated = {
                        (name, int(item["evidence_page_num"]) + 1)
                        for item in row["evidence"]
                        if item.get("evidence_page_num") is not None
                    }
                    hit = len(annotated & returned)
                    results.setdefault(name, []).append((hit, len(annotated)))
                    detail.append(
                        {
                            "id": row["financebench_id"],
                            "doc": name,
                            "hit": hit,
                            "annotated": len(annotated),
                            "returned": len(returned),
                        }
                    )
    total_hit = sum(item["hit"] for item in detail)
    total_annotated = sum(item["annotated"] for item in detail)
    print(f"--- 模型 {model} ---")
    print(f"整体 Recall@{limit}: {total_hit}/{total_annotated} = {total_hit / total_annotated:.4f}")
    per_group = {}
    for name, rows in results.items():
        hit = sum(a for a, _ in rows)
        total = sum(b for _, b in rows)
        per_group[name] = hit / total if total else 0.0
        flag = "PASS" if per_group[name] >= 0.70 else "FAIL"
        print(f"   {name}: {hit}/{total} = {per_group[name]:.4f}  {flag}")
    worst = min(per_group.values())
    print(f"   最差分组: {worst:.4f}  ->  {'PASS' if worst >= 0.70 else 'FAIL'}")
    print()
    return {"model": model, "overall": total_hit / total_annotated, "per_group": per_group, "detail": detail}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default=r"D:\Tools\harness\pdf-scope-models.json")
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in (FINANCEBENCH / "data/financebench_open_source.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [row for row in rows if row["doc_name"] in DOCUMENTS]
    observations, _ = await build_observations()
    print(f"隐藏工作负载: {len(DOCUMENTS)} 份财报, {len(questions)} 个问题\n")

    report = []
    for model in ("one_scope", "per_doc"):
        report.append(await run_model(model, observations, questions, args.limit))
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
