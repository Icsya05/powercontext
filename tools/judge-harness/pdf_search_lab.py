"""Retrieval strategy search with a persisted database cache.

Persisting 1151 pages into a real Runtime takes minutes, so the database is
built once into a fixed directory and reused by every strategy afterwards.

Strategies under test, all of them built on the public Memory search API:

  current          the shipped implementation
  rare_terms       short high-information queries, fused with reciprocal rank
                   fusion, the report the question names preferred
  rare_plus_doc    the same, but the matching report is preferred hard
  rrf_all          reciprocal rank fusion over every query view
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
CACHE = Path(r"D:\Tools\harness\pdf-cache")
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
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY  # noqa: E402
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


def plural_key(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 4 and term.endswith(("sses", "ches", "shes", "xes", "zes")):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "is", "us")):
        return term[:-1]
    return term


async def build_observations():
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    observations = []
    text_to_page = {}
    for name in DOCUMENTS:
        for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name))):
            source = await registry.resolve(page)
            observations.append(project_source_for_transport(registry, source))
            text_to_page[(name + "\n" + page.text).strip()] = (name, page.page_number)
    return observations, text_to_page


async def open_cached(observations):
    """Build the database once, then reuse it."""
    CACHE.mkdir(parents=True, exist_ok=True)
    marker = CACHE / "sources.db"
    scope_file = CACHE / "scope.json"
    if marker.exists() and scope_file.exists():
        from powercontext.builtin.persistence.sqlite import SQLiteConfig
        from powercontext.builtin.runtime import BuiltinConfig

        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{marker}"))
        scope_id = json.loads(scope_file.read_text(encoding="utf-8"))["scope_id"]
        return config, scope_id
    config, scope_id, _ = await persist(CACHE, PDF_PAGE_SOURCE_DEFINITION, observations)
    scope_file.write_text(json.dumps({"scope_id": scope_id}), encoding="utf-8")
    return config, scope_id


def query_terms(question: str) -> list[str]:
    return [plural_key(t) for t in analyze_fts_query(question).split()]


def rare_queries(terms: list[str], document_frequency: Counter, maximum: int = 6) -> list[str]:
    """Short queries built from the most selective terms of the question."""
    ordered = sorted(terms, key=lambda term: (document_frequency.get(term, 0), term))
    queries = []
    for term in ordered[:maximum]:
        queries.append(term)
    for index in range(min(len(ordered) - 1, 4)):
        queries.append(f"{ordered[index]} {ordered[index + 1]}")
    return queries


async def collect(memory, text_to_page, queries, per_query: int):
    """Run every query and return the fused ranking with reciprocal rank fusion."""
    fused: dict[tuple[str, int], float] = defaultdict(float)
    ranks: dict[tuple[str, int], int] = {}
    document_of: dict[tuple[str, int], str] = {}
    text_of: dict[tuple[str, int], str] = {}
    for query in queries:
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=per_query))
        for rank, hit in enumerate(page.hits, 1):
            key = text_to_page.get((hit.text or "").strip())
            if key is None:
                continue
            fused[key] += 1.0 / (60 + rank)
            ranks.setdefault(key, rank)
            document_of.setdefault(key, key[0])
            text_of.setdefault(key, hit.text or "")
    return fused, ranks, document_of, text_of


def pick_document(question: str, documents: dict[str, Counter], document_frequency: Counter) -> str | None:
    terms = set(query_terms(question))
    scores = {}
    for document, counts in documents.items():
        scores[document] = sum(
            math.log(1 + (len(documents) + 1) / (document_frequency.get(term, 0) + 1)) * count
            for term, count in counts.items()
            if term in terms
        )
    if not scores:
        return None
    best = max(scores, key=lambda document: (scores[document], document))
    if scores[best] <= 0:
        return None
    runner_up = max((s for d, s in scores.items() if d != best), default=0.0)
    if runner_up > 0 and scores[best] < runner_up * 2:
        return None
    return best


async def run(memory, text_to_page, question: str, strategy: str, limit: int):
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
        return returned

    if strategy == "scope_bm25":
        from pdf_scope_bm25 import scope_and_rank

        return await scope_and_rank(memory, text_to_page, question, query_terms(question), limit)

    terms = query_terms(question)
    # document frequency of the query terms over the stored pages
    document_frequency = Counter()
    for query in terms:
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=400))
        document_frequency[query] = len(page.hits)

    queries = [question] + rare_queries(terms, document_frequency)
    fused, ranks, document_of, text_of = await collect(memory, text_to_page, queries, 60)

    identities: dict[str, Counter] = defaultdict(Counter)
    identity_frequency = Counter()
    for key, text in text_of.items():
        head = (text or "").split("\n", 1)[0]
        tokens = {plural_key(t) for t in re.findall(r"[a-z]+|\d+", head.lower())}
        identities[key[0]].update(tokens)
        identity_frequency.update(tokens)
    chosen = pick_document(question, dict(identities), identity_frequency)

    if strategy == "rrf_all":
        ordered = sorted(fused, key=lambda key: (-fused[key], key))
    elif strategy == "rare_terms":
        ordered = sorted(fused, key=lambda key: (-fused[key], key))
    else:  # rare_plus_doc
        ordered = sorted(
            fused,
            key=lambda key: (0 if chosen is not None and key[0] == chosen else 1, -fused[key], key),
        )
    return set(ordered[:limit])


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--strategies", nargs="+", default=["current", "rrf_all", "rare_terms", "rare_plus_doc"])
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in (FINANCEBENCH / "data/financebench_open_source.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [row for row in rows if row["doc_name"] in DOCUMENTS]
    observations, text_to_page = await build_observations()
    config, scope_id = await open_cached(observations)
    print(f"数据库: {CACHE / 'sources.db'}", flush=True)

    async with open_builtin_runtime(config) as runtime:
        memory = runtime.memory.for_scope(scope_id)
        for strategy in args.strategies:
            groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for row in questions:
                name = row["doc_name"]
                annotated = {
                    (name, int(item["evidence_page_num"]) + 1)
                    for item in row["evidence"]
                    if item.get("evidence_page_num") is not None
                }
                returned = await run(memory, text_to_page, row["question"], strategy, args.limit)
                groups[name].append((len(annotated & returned), len(annotated)))
            print(f"--- {strategy} ---")
            worst = 1.0
            for name, rows_ in groups.items():
                hit = sum(a for a, _ in rows_)
                total = sum(b for _, b in rows_)
                value = hit / total if total else 0.0
                worst = min(worst, value)
                print(f"   {name:<22} {hit}/{total} = {value:.4f}" + ("" if value >= 0.70 else "   FAIL"))
            print(f"   最差组 {worst:.4f}  ->  {'PASS' if worst >= 0.70 else 'FAIL'}\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
