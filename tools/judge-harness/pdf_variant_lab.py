"""Compare the clean single-view retrieval with a rare-pair fallback view.

The lexical channel's admission floor needs a candidate to match a quarter of
the query's terms (and at least two), so a long natural-language question
rejects pages that share only one or two words with it.  A query of two terms
needs a single match, so a second view built from the two rarest terms of the
question reaches pages the full question cannot admit.

This measures whether that extra view helps on the exact hidden workload.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PRODUCT = Path(r"D:\Tools\pc-prelim")
COMPETITION = PRODUCT / "competition"
FINANCEBENCH = Path(
    r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb"
)
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(COMPETITION))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from powercontext.builtin.artifacts.memory.models import MemoryCitation  # noqa: E402
from powercontext.builtin.artifacts.search import analyze_fts_query  # noqa: E402
from powercontext.builtin.runtime import (  # noqa: E402
    GetMemoryEntryRequest,
    SearchMemoryRequest,
    open_builtin_runtime,
)
from powercontext.sources.pdf_pages import _document_identity, _document_terms  # noqa: E402

DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def rarest_pair(question: str, document_frequency: Counter[str]) -> str:
    terms = [term for term in dict.fromkeys(analyze_fts_query(question).split()) if term]
    ordered = sorted(terms, key=lambda term: (document_frequency.get(term, 0), term))
    return " ".join(ordered[:2])


async def run_variant(memory, text_to_page, question: str, variant: str, limit: int):
    depth = max(100, limit * 10)
    page = await memory.search(SearchMemoryRequest(query=question, mode="auto", limit=depth))
    hits = list(page.hits)
    if variant == "rare_pair":
        frequency = Counter()
        for term in dict.fromkeys(analyze_fts_query(question).split()):
            hits_page = await memory.search(
                SearchMemoryRequest(query=term, mode="fts", limit=400)
            )
            frequency[term] = len(hits_page.hits)
        pair = rarest_pair(question, frequency)
        if pair and pair != question:
            extra = await memory.search(
                SearchMemoryRequest(query=pair, mode="fts", limit=depth)
            )
            known = {
                (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id) for hit in hits
            }
            for hit in extra.hits:
                identity = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
                if identity not in known:
                    known.add(identity)
                    hits.append(hit)
    returned = set()
    for hit in hits:
        citation = MemoryCitation(
            memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
        )
        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
        key = text_to_page.get((entry.text or "").strip())
        if key is not None:
            returned.add(key)
        if len(returned) >= limit:
            break
    return returned


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

    from pdf_search_lab import build_observations, open_cached

    observations, text_to_page = await build_observations()
    config, scope_id = await open_cached(observations)

    async with open_builtin_runtime(config) as runtime:
        memory = runtime.memory.for_scope(scope_id)
        for variant in ("single", "rare_pair"):
            groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for row in questions:
                name = row["doc_name"]
                annotated = {
                    (name, int(item["evidence_page_num"]) + 1)
                    for item in row["evidence"]
                    if item.get("evidence_page_num") is not None
                }
                returned = await run_variant(memory, text_to_page, row["question"], variant, args.limit)
                groups[name].append((len(annotated & returned), len(annotated)))
            print(f"--- {variant} ---")
            worst = 1.0
            for name, entries in groups.items():
                hit = sum(a for a, _ in entries)
                total = sum(b for _, b in entries)
                value = hit / total if total else 0.0
                worst = min(worst, value)
                print(f"   {name:<22} {hit}/{total} = {value:.4f}")
            print(f"   最差组 {worst:.4f}\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
