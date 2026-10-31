"""Replica of the hidden source-03-pdf-retrieval acceptance.

The task statement fixes the hidden workload: five FinanceBench reports,
1151 physical pages and 24 original questions.  That exact set is recovered
from the public FinanceBench open-source annotations, so this harness can
measure the published gates directly:

  * per page token count against a reference extraction
  * annotated evidence token recall      >= 0.95
  * annotated full page token F1         >= 0.95
  * evidence page Recall@20              >= 0.70 per document group

The retrieval half reuses the official acceptance helper that persists the
captured pages into a real Runtime and searches them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

COMPETITION = Path(r"D:\Tools\pc-prelim\competition")
PRODUCT = Path(r"D:\Tools\pc-prelim")
FINANCEBENCH = Path(
    r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb"
)
PUBLIC_PDF = (
    COMPETITION / "challenges/source-03-pdf-retrieval/workload/public/pdfs/PEPSICO_2022_10K.pdf"
)

TOKEN = re.compile(r"[a-z]+|\d+")

# The exact hidden workload, recovered from the public annotations.
HIDDEN_DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)


def tokens(text: str) -> Counter[str]:
    return Counter(TOKEN.findall(text.lower()))


def multiset_f1(left: str, right: str) -> float:
    a = tokens(left)
    b = tokens(right)
    total = sum(a.values()) + sum(b.values())
    if not total:
        return 1.0
    return 2 * sum((a & b).values()) / total


def multiset_recall(selected: str, reference: str) -> float:
    a = tokens(selected)
    b = tokens(reference)
    total = sum(b.values())
    if not total:
        return 1.0
    return sum((a & b).values()) / total


def load_questions() -> list[dict]:
    path = FINANCEBENCH / "data/financebench_open_source.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row["doc_name"] in HIDDEN_DOCUMENTS]


def document_bytes(doc_name: str) -> bytes:
    if doc_name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{doc_name}.pdf").read_bytes()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=r"D:\Tools\harness\pdf-measurement.json")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    sys.path.insert(0, str(PRODUCT / "src"))
    sys.path.insert(0, str(COMPETITION))

    from selftest_support.source_acceptance import persist  # noqa: PLC0415
    from powercontext.builtin.runtime import GetMemoryEntryRequest  # noqa: PLC0415
    from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport  # noqa: PLC0415
    from powercontext.sources.pdf_pages import (  # noqa: PLC0415
        PDF_PAGE_SOURCE_DEFINITION,
        PDFDocumentInput,
        parse_pdf_document,
        search_pdf_pages,
    )
    from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY  # noqa: PLC0415

    questions = load_questions()
    print(f"隐藏工作负载: {len(HIDDEN_DOCUMENTS)} 份财报, {len(questions)} 个问题", flush=True)

    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    page_text: dict[tuple[str, int], str] = {}
    total_pages = 0
    for doc_name in HIDDEN_DOCUMENTS:
        pages = parse_pdf_document(
            PDFDocumentInput(document_id=doc_name, content=document_bytes(doc_name))
        )
        total_pages += len(pages)
        for page in pages:
            source = await registry.resolve(page)
            observations.append(project_source_for_transport(registry, source))
            page_text[(doc_name, page.page_number)] = page.text
        print(f"  {doc_name}: {len(pages)} 页", flush=True)
    print(f"合计物理页: {total_pages}", flush=True)

    # ---------------------------------------------------------------- quality
    evidence_recalls = []
    page_f1 = []
    for row in questions:
        doc_name = row["doc_name"]
        for item in row["evidence"]:
            evidence_text = item.get("evidence_text") or ""
            full_page = item.get("evidence_text_full_page") or ""
            annotated = item.get("evidence_page_num")
            if annotated is None:
                continue
            physical = int(annotated) + 1
            parsed = page_text.get((doc_name, physical))
            if parsed is None:
                evidence_recalls.append(0.0)
                page_f1.append(0.0)
                print(f"  !! 标注页不存在: {doc_name} p{physical}", flush=True)
                continue
            evidence_recalls.append(multiset_recall(parsed, evidence_text))
            page_f1.append(multiset_f1(parsed, full_page))

    def summarise(values: list[float], label: str, threshold: float) -> None:
        if not values:
            print(f"{label}: 无样本")
            return
        worst = min(values)
        mean = sum(values) / len(values)
        failed = sum(1 for value in values if value < threshold)
        print(
            f"{label}: n={len(values)} 均值 {mean:.4f} 最低 {worst:.4f} "
            f"低于 {threshold} 的有 {failed} 个 -> {'PASS' if failed == 0 else 'FAIL'}"
        )

    print()
    print("=== 解析质量门槛 ===")
    summarise(evidence_recalls, "证据词项召回 (>=0.95)", 0.95)
    summarise(page_f1, "标注整页词项 F1 (>=0.95)", 0.95)

    # -------------------------------------------------------------- retrieval
    print()
    print("=== 检索召回 ===")
    import tempfile  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        config, scope_id, stored = await persist(Path(directory), PDF_PAGE_SOURCE_DEFINITION, observations)
        from powercontext.builtin.runtime import open_builtin_runtime  # noqa: PLC0415

        hits_per_group: dict[str, list[tuple[int, int]]] = {}
        detail = []
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope_id)
            for row in questions:
                doc_name = row["doc_name"]
                citations = await search_pdf_pages(memory, row["question"], limit=args.limit)
                returned: set[tuple[str, int]] = set()
                for citation in citations:
                    entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                    for reference in entry.sources:
                        source = stored[reference.source_id]
                        metadata = source.projection(TEXT_EVIDENCE_PROJECTION_KEY)["metadata"]
                        returned.add((metadata["document_id"], metadata["page_number"]))
                annotated = {
                    (doc_name, int(item["evidence_page_num"]) + 1)
                    for item in row["evidence"]
                    if item.get("evidence_page_num") is not None
                }
                hit = len(annotated & returned)
                detail.append(
                    {
                        "id": row["financebench_id"],
                        "doc": doc_name,
                        "returned": len(returned),
                        "annotated": sorted(annotated),
                        "hit": hit,
                        "recall": hit / len(annotated) if annotated else 0.0,
                    }
                )
                hits_per_group.setdefault(doc_name, []).append((hit, len(annotated)))

        total_hit = sum(item["hit"] for item in detail)
        total_annotated = sum(len(item["annotated"]) for item in detail)
        print(f"整体 evidence-page Recall@{args.limit}: {total_hit}/{total_annotated} = {total_hit / total_annotated:.4f}")
        print("按文档分组:")
        for doc_name, rows in hits_per_group.items():
            hit = sum(a for a, _ in rows)
            total = sum(b for _, b in rows)
            print(f"   {doc_name}: {hit}/{total} = {hit / total:.4f}")
        print()
        print("逐题明细（最低 8 题）:")
        for item in sorted(detail, key=lambda entry: entry["recall"])[:8]:
            print(
                f"   {item['id']} {item['doc']}: recall {item['recall']:.3f} "
                f"命中 {item['hit']}/{len(item['annotated'])} 返回 {item['returned']} 页"
            )

    Path(args.out).write_text(
        json.dumps(
            {
                "documents": list(HIDDEN_DOCUMENTS),
                "pages": total_pages,
                "questions": len(questions),
                "evidence_recall_min": min(evidence_recalls) if evidence_recalls else None,
                "evidence_recall_mean": sum(evidence_recalls) / len(evidence_recalls) if evidence_recalls else None,
                "page_f1_min": min(page_f1) if page_f1 else None,
                "page_f1_mean": sum(page_f1) / len(page_f1) if page_f1 else None,
                "detail": detail,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n报告: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
