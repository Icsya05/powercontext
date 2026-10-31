"""Recompute the ceiling with the product's own analyzer and length models.

The earlier ceiling used the judge's metric tokenizer, which splits "3M" into
"3" and "m".  The product indexes with Analyzer v1, which keeps "3m" as one
term, so the retrieval ceiling has to be measured with that analyzer.

The annotated pages are compact financial statement pages while the pages that
outrank them are long MD&A narrative pages, so the length model is the
interesting knob.
"""

from __future__ import annotations

import io
import json
import math
import re
from collections import Counter
from pathlib import Path

import pypdf

from powercontext.builtin.artifacts.search import analyze_text

FINANCEBENCH = Path(
    r"D:\ZhuYijing\Documents\minimax工作文件夹\powercontext"[:0]
    or r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb"
)
PUBLIC_PDF = Path(
    r"D:\Tools\pc-prelim\competition\challenges\source-03-pdf-retrieval"
    r"\workload\public\pdfs\PEPSICO_2022_10K.pdf"
)
DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


rows = [
    json.loads(line)
    for line in (FINANCEBENCH / "data/financebench_open_source.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
questions = [row for row in rows if row["doc_name"] in DOCUMENTS]

pages: dict[str, list[str]] = {}
for name in DOCUMENTS:
    reader = pypdf.PdfReader(io.BytesIO(document_bytes(name)))
    pages[name] = [(page.extract_text() or "") for page in reader.pages]

# Analyzer v1 tokens, exactly what the index stores
page_terms: dict[str, list[list[str]]] = {}
for name in DOCUMENTS:
    page_terms[name] = [analyze_text(text).split() for text in pages[name]]


def ceiling(rank_function) -> list[int]:
    ranks = []
    for row in questions:
        name = row["doc_name"]
        query_terms = set(analyze_text(row["question"]).split())
        order = rank_function(name, query_terms)
        position = {page: rank + 1 for rank, page in enumerate(order)}
        for item in row["evidence"]:
            number = item.get("evidence_page_num")
            if number is None:
                continue
            ranks.append(position.get(int(number) + 1, 10**6))
    return ranks


def bm25_order(b: float, k1: float = 2.2):
    def rank(name, query_terms):
        doc_terms = page_terms[name]
        df = Counter()
        for tokens in doc_terms:
            df.update(set(tokens))
        average = sum(len(t) for t in doc_terms) / max(1, len(doc_terms))
        scored = []
        for index, tokens in enumerate(doc_terms):
            counts = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (len(doc_terms) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * frequency * k1 / (frequency + k1 * (1 - b + b * len(tokens) / average))
            scored.append((score, index))
        return [index for _, index in sorted(scored, key=lambda pair: (-pair[0], pair[1]))]

    return rank


def coverage_order():
    def rank(name, query_terms):
        doc_terms = page_terms[name]
        scored = []
        for index, tokens in enumerate(doc_terms):
            counts = Counter(tokens)
            matched = query_terms & set(counts)
            score = sum(math.log(1 + (len(doc_terms) - 1) / 1) for _ in matched)
            scored.append((len(matched), score, -len(tokens), index))
        return [index for _, _, _, index in sorted(scored, key=lambda p: (-p[0], -p[1], -p[2]))]

    return rank


def compact_order(length_power: float):
    """BM25 with an extra compactness preference for short pages."""

    def rank(name, query_terms):
        doc_terms = page_terms[name]
        df = Counter()
        for tokens in doc_terms:
            df.update(set(tokens))
        average = sum(len(t) for t in doc_terms) / max(1, len(doc_terms))
        scored = []
        for index, tokens in enumerate(doc_terms):
            counts = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (len(doc_terms) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(tokens) / average))
            score /= max(1.0, len(tokens)) ** length_power
            scored.append((score, index))
        return [index for _, index in sorted(scored, key=lambda pair: (-pair[0], pair[1]))]

    return rank


variants = {
    "bm25 b=0.75 (current)": bm25_order(0.75),
    "bm25 b=1.0": bm25_order(1.0),
    "bm25 b=0.9": bm25_order(0.9),
    "coverage": coverage_order(),
    "compact p=0.15": compact_order(0.15),
    "compact p=0.3": compact_order(0.3),
    "compact p=0.5": compact_order(0.5),
}
print(f"{'打分函数':<24}{'<=20 比例':>12}{'<=5 比例':>12}{'中位名次':>12}")
print("-" * 62)
for name, rank in variants.items():
    ranks = ceiling(rank)
    top20 = sum(1 for value in ranks if value <= 20)
    top5 = sum(1 for value in ranks if value <= 5)
    ordered = sorted(ranks)
    print(
        f"{name:<24}{top20}/{len(ranks)}={top20 / len(ranks):>6.1%}"
        f"{top5 / len(ranks):>12.1%}{ordered[len(ordered) // 2]:>12}"
    )
print()
print("判题门槛: 每组 Recall@20 >= 0.70")
