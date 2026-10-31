"""Retrieval strategy experiment on the exact hidden PDF workload.

The diagnostic showed that the current implementation spends its twenty
result slots across every report in the scope, even when the question names
one company, and that pages the index itself ranks highly are dropped by the
local reranker.  This measures alternative strategies, under both scope
models the task wording allows, so the fix is chosen on numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import tempfile
from collections import Counter, defaultdict
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

from powercontext.builtin.artifacts.memory.models import MemoryCitation  # noqa: E402
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
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


def terms_of(text: str) -> list[str]:
    return [match.group(0).casefold() for match in TOKEN.finditer(text)]


def plural_key(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 4 and term.endswith(("sses", "ches", "shes", "xes", "zes")):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "is", "us")):
        return term[:-1]
    return term


async def build() -> tuple[list, dict[str, tuple[str, int]], dict[str, list]]:
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    text_to_page: dict[str, tuple[str, int]] = {}
    per_document: dict[str, list] = defaultdict(list)
    for name in DOCUMENTS:
        for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name))):
            source = await registry.resolve(page)
            observation = project_source_for_transport(registry, source)
            observations.append(observation)
            per_document[name].append(observation)
            text_to_page[(name + "\n" + page.text).strip()] = (name, page.page_number)
    return observations, text_to_page, per_document


async def evaluate(memory, text_to_page, questions, strategy: str, limit: int) -> list[dict]:
    detail = []
    for row in questions:
        question = row["question"]
        name = row["doc_name"]
        annotated = {
            (name, int(item["evidence_page_num"]) + 1)
            for item in row["evidence"]
            if item.get("evidence_page_num") is not None
        }
        if strategy == "current":
            citations = await search_pdf_pages(memory, question, limit=limit)
            returned = set()
            for citation in citations:
                entry = (
                    await memory.get(
                        GetMemoryEntryRequest(
                            citation=MemoryCitation(
                                memory_ref=citation.memory_ref,
                                entry_id=citation.entry_id,
                                entry_version_id=citation.entry_version_id,
                            )
                        )
                    )
                ).entry
                key = text_to_page.get((entry.text or "").strip())
                if key is not None:
                    returned.add(key)
        else:
            returned = await run_strategy(memory, text_to_page, question, strategy, limit)
        hit = len(annotated & returned)
        detail.append(
            {
                "id": row["financebench_id"],
                "doc": name,
                "hit": hit,
                "annotated": len(annotated),
                "returned": len(returned),
            }
        )
    return detail


async def run_strategy(memory, text_to_page, question: str, strategy: str, limit: int) -> set:
    query_terms = [plural_key(term) for term in terms_of(analyze_fts_query(question))]
    page = await memory.search(SearchMemoryRequest(query=question, mode="fts", limit=200))
    candidates: list[tuple[str, int, str]] = []
    seen = set()
    for hit in page.hits:
        key = text_to_page.get((hit.text or "").strip())
        if key is None or key in seen:
            continue
        seen.add(key)
        candidates.append((key[0], key[1], hit.text or ""))
    if not candidates:
        return set()
    if strategy == "fts_only":
        ordered = candidates
    else:
        # pick the report the question is about, using the document identity that
        # every page of that report carries in its stored text
        document_frequency = Counter()
        for document, _, text in candidates:
            for term in set(plural_key(t) for t in terms_of(text.split("\n", 1)[0])):
                document_frequency[term] += 1
        identity: dict[str, Counter] = {}
        for document, _, text in candidates:
            identity.setdefault(document, Counter())
            identity[document].update(plural_key(t) for t in terms_of(text.split("\n", 1)[0]))
        best_document, best_score = None, 0.0
        for document, counts in identity.items():
            score = 0.0
            for term, count in counts.items():
                if term in query_terms:
                    weight = math.log(1 + (len(identity) + 1) / (document_frequency[term] + 1))
                    score += weight * count
            if score > best_score:
                best_document, best_score = document, score
        if strategy == "document_boost":
            ordered = sorted(
                candidates,
                key=lambda item: (0 if item[0] == best_document else 1, item[1]),
            )
        else:  # document_restrict
            ordered = [item for item in candidates if item[0] == best_document] or candidates
    return {(document, page_number) for document, page_number, _ in ordered[:limit]}


def report(detail: list[dict]) -> dict:
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for item in detail:
        groups[item["doc"]].append((item["hit"], item["annotated"]))
    per_group = {}
    for name, rows in groups.items():
        hit = sum(a for a, _ in rows)
        total = sum(b for _, b in rows)
        per_group[name] = hit / total if total else 0.0
    total_hit = sum(item["hit"] for item in detail)
    total_annotated = sum(item["annotated"] for item in detail)
    return {
        "overall": total_hit / total_annotated if total_annotated else 0.0,
        "per_group": per_group,
        "worst": min(per_group.values()) if per_group else 0.0,
    }


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
    observations, text_to_page, per_document = await build()
    print(f"工作负载: {len(DOCUMENTS)} 份财报 / {len(questions)} 个问题\n", flush=True)

    strategies = ("current", "fts_only", "document_boost", "document_restrict")
    results = []
    with tempfile.TemporaryDirectory() as directory:
        for model in ("one_scope", "per_doc"):
            if model == "one_scope":
                config, scope_id, _ = await persist(
                    Path(directory) / "all", PDF_PAGE_SOURCE_DEFINITION, observations
                )
                async with open_builtin_runtime(config) as runtime:
                    memory = runtime.memory.for_scope(scope_id)
                    for strategy in strategies:
                        detail = await evaluate(memory, text_to_page, questions, strategy, args.limit)
                        summary = report(detail)
                        results.append({"model": model, "strategy": strategy, **summary})
                        print(
                            f"[{model}/{strategy}] 整体 {summary['overall']:.4f}  最差组 {summary['worst']:.4f}"
                            + ("" if summary["worst"] >= 0.70 else "   <-- FAIL"),
                            flush=True,
                        )
                        print("      " + "  ".join(f"{k.split('_')[0]}:{v:.2f}" for k, v in summary["per_group"].items()), flush=True)
            else:
                for name in DOCUMENTS:
                    config, scope_id, _ = await persist(
                        Path(directory) / name, PDF_PAGE_SOURCE_DEFINITION, per_document[name]
                    )
                    subset = [row for row in questions if row["doc_name"] == name]
                    async with open_builtin_runtime(config) as runtime:
                        memory = runtime.memory.for_scope(scope_id)
                        for strategy in strategies:
                            detail = await evaluate(memory, text_to_page, subset, strategy, args.limit)
                            summary = report(detail)
                            results.append({"model": model, "strategy": strategy, "document": name, **summary})
                            print(
                                f"[{model}/{strategy}] {name}: {summary['overall']:.4f}"
                                + ("" if summary["overall"] >= 0.70 else "   <-- FAIL"),
                                flush=True,
                            )
    Path(r"D:\Tools\harness\pdf-strategies.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
