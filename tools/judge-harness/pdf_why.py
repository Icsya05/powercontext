"""Show what outranks the annotated page for the failing questions."""

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
TOKEN = re.compile(r"[a-z]+|\d+")
DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)
STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "been", "by", "that", "this", "these", "those",
    "as", "at", "it", "its", "from", "we", "our", "their", "there", "which",
    "have", "has", "had", "not", "but", "can", "will", "such", "than", "then",
    "also", "may", "what", "how", "did", "does", "do", "based", "any", "each",
    "if", "when", "who", "why", "they", "them", "calculate", "give",
    "define", "defined", "answer", "analyst", "assume", "assuming", "details",
    "use", "using", "including", "include", "state", "outlined", "explicitly",
    "directly", "primarily", "important", "ongoing", "reported", "compare",
}


def tokens(text: str) -> list[str]:
    return [m.group(0) for m in TOKEN.finditer(text.lower())]


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

shown = 0
for row in questions:
    name = row["doc_name"]
    q_tokens = [t for t in tokens(row["question"]) if t not in STOP]
    q_set = set(q_tokens)
    doc_tokens = [tokens(text) for text in pages[name]]
    df = Counter()
    for token_list in doc_tokens:
        df.update(set(token_list))
    average = sum(len(t) for t in doc_tokens) / max(1, len(doc_tokens))
    scored = []
    for index, token_list in enumerate(doc_tokens):
        counts = Counter(token_list)
        score = 0.0
        for term in q_set:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (len(doc_tokens) - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(token_list) / average))
        scored.append((score, index))
    order = [index for _, index in sorted(scored, key=lambda pair: (-pair[0], pair[1]))]
    position = {page: rank + 1 for rank, page in enumerate(order)}
    for item in row["evidence"]:
        number = item.get("evidence_page_num")
        if number is None:
            continue
        physical = int(number) + 1
        rank = position.get(physical, 10**6)
        if rank <= 20:
            continue
        shown += 1
        if shown > 4:
            continue
        print("=" * 118)
        print(f"{row['financebench_id']} [{name}] 标注页 p{physical} 的词面名次 = {rank} / {len(doc_tokens)}")
        print(f"  问题: {row['question'][:200]}")
        gold_index = physical - 1
        gold_counts = Counter(doc_tokens[gold_index])
        gold_score = dict((index, score) for score, index in scored).get(gold_index, 0.0)
        print(f"  标注页得分 {gold_score:.3f}; 命中查询词: {sorted(q_set & set(gold_counts))}")
        print(f"  标注页正文: {pages[name][gold_index][:220]!r}")
        print(f"  标注证据文本: {(item.get('evidence_text') or '')[:220]!r}")
        print("  排在前面的页面:")
        for page in order[:6]:
            head = pages[name][page][:110].replace("\n", " ")
            score = dict((index, value) for value, index in scored).get(page, 0.0)
            print(f"     p{page + 1:>4} score {score:6.3f}  {head!r}")
print()
print(f"（共 {sum(1 for row in questions for item in row['evidence'] if item.get('evidence_page_num') is not None)} 个标注页，其中名次 > 20 的已在上方展示前若干个）")
