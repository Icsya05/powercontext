"""Is the annotated page even reachable by lexical matching?

No runtime needed: parse the five reports, take the annotated page, and
compare its terms with the question's.  This decides whether the retrieval
problem is a ranking problem (the page is findable, it is ranked too low) or
a reachability problem (the page shares almost nothing with the question).
"""

from __future__ import annotations

import json
import re
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
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "been", "by", "that", "this", "these", "those",
    "as", "at", "it", "its", "from", "we", "our", "their", "there", "which",
    "have", "has", "had", "not", "but", "can", "will", "such", "than", "then",
    "also", "may", "what", "how", "did", "does", "do", "based", "any", "each",
    "if", "when", "who", "why", "there", "these", "they", "them", "their",
}


def tokens(text: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in TOKEN.finditer(text)
        if match.group(0).casefold() not in STOP
    }


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
    reader = pypdf.PdfReader(__import__("io").BytesIO(document_bytes(name)))
    pages[name] = [(page.extract_text() or "") for page in reader.pages]

reachable = 0
total = 0
strong = 0
print(f"{'id':<28}{'doc':<20}{'overlap':>8}  {'gold page head'}")
print("-" * 140)
for row in questions:
    name = row["doc_name"]
    question_terms = tokens(row["question"])
    for item in row["evidence"]:
        number = item.get("evidence_page_num")
        if number is None:
            continue
        physical = int(number) + 1
        text = pages[name][physical - 1] if physical <= len(pages[name]) else ""
        page_terms = tokens(text)
        shared = question_terms & page_terms
        overlap = len(shared) / max(1, len(question_terms))
        total += 1
        if shared:
            reachable += 1
        if overlap >= 0.5:
            strong += 1
        print(
            f"{row['financebench_id']:<28}{name:<20}{overlap:>8.3f}  "
            f"{text[:80]!r}"
        )
        print(f"{'':<56}question terms: {sorted(question_terms)[:12]}")
        print(f"{'':<56}shared        : {sorted(shared)[:12]}")

print()
print(f"标注页总数: {total}")
print(f"与问题有至少一个共同词的标注页: {reachable} ({reachable / total:.1%})")
print(f"词覆盖率 >= 0.5 的标注页: {strong} ({strong / total:.1%})")
