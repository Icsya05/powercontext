"""How well could any lexical ranker place the annotated page?

For every question, score every page of the report it is about with several
lexical scorers and report where the annotated page lands.  This is the
ceiling for any reranking approach that only sees the page text.
"""

from __future__ import annotations

import io
import json
import math
import re
from collections import Counter
from pathlib import Path

import pypdf

FINANCEBENCH = Path(
    r"D:\Tools\financebench\financebench-cc39aeb4afdf33909ee1412188bf89035950c2eb"
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
TOKEN = re.compile(r"[a-z]+|\d+")
STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "been", "by", "that", "this", "these", "those",
    "as", "at", "it", "its", "from", "we", "our", "their", "there", "which",
    "have", "has", "had", "not", "but", "can", "will", "such", "than", "then",
    "also", "may", "what", "how", "did", "does", "do", "based", "any", "each",
    "if", "when", "who", "why", "they", "them", "their", "calculate", "give",
    "define", "defined", "answer", "analyst", "assume", "assuming", "details",
    "use", "using", "including", "include", "state", "outlined", "explicitly",
    "directly", "primarily", "important", "ongoing", "reported", "compare",
}


def tokens(text: str) -> list[str]:
    return [m.group(0) for m in TOKEN.finditer(text.lower())]


def query_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOP]


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

page_tokens = {
    name: [tokens(text) for text in pages[name]] for name in DOCUMENTS
}

results = {}
for scorer_name in ("bm25", "coverage", "coverage_weighted"):
    ranks = []
    for row in questions:
        name = row["doc_name"]
        q_tokens = query_tokens(row["question"])
        q_set = set(q_tokens)
        doc_tokens = page_tokens[name]
        df = Counter()
        for tokens_ in doc_tokens:
            df.update(set(tokens_))
        average = sum(len(t) for t in doc_tokens) / max(1, len(doc_tokens))
        scored = []
        for index, tokens_ in enumerate(doc_tokens):
            counts = Counter(tokens_)
            if scorer_name == "bm25":
                score = 0.0
                for term in q_set:
                    frequency = counts.get(term, 0)
                    if not frequency:
                        continue
                    idf = math.log(1 + (len(doc_tokens) - df[term] + 0.5) / (df[term] + 0.5))
                    score += idf * frequency * 2.2 / (
                        frequency + 1.2 * (0.25 + 0.75 * len(tokens_) / average)
                    )
            elif scorer_name == "coverage":
                score = float(len(q_set & set(tokens_)))
            else:
                matched = q_set & set(tokens_)
                score = sum(
                    math.log(1 + (len(doc_tokens) - df[term] + 0.5) / (df[term] + 0.5))
                    for term in matched
                )
            scored.append((score, index))
        order = [index for _, index in sorted(scored, key=lambda pair: (-pair[0], pair[1]))]
        position = {page: rank + 1 for rank, page in enumerate(order)}
        for item in row["evidence"]:
            number = item.get("evidence_page_num")
            if number is None:
                continue
            physical = int(number) + 1
            ranks.append(position.get(physical, 10**6))
    top20 = sum(1 for rank in ranks if rank <= 20)
    top5 = sum(1 for rank in ranks if rank <= 5)
    print(
        f"{scorer_name:<20} 标注页排名 <=20 的比例: {top20}/{len(ranks)} = {top20 / len(ranks):.1%}"
        f"   <=5 的比例: {top5}/{len(ranks)} = {top5 / len(ranks):.1%}"
    )
    results[scorer_name] = ranks

print()
print("按打分函数的标注页名次分布:")
for name, ranks in results.items():
    ordered = sorted(ranks)
    print(f"   {name:<20} 中位 {ordered[len(ordered) // 2]:>4}  最好 {ordered[0]:>4}  最差 {ordered[-1]:>6}")
print()
print("说明: 若名次普遍大于 20，则任何只看正文的词面重排都无法把标注页送进前 20。")
