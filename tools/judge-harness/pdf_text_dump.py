"""Print what the gold pages look like next to the pages that win the ranking.

Amazon scores zero in every lexical variant although its report has only 85
pages, so the reason has to be visible in the text: what the gold page says,
what the winning pages say, and how the question's terms distribute over the
page.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

FINANCEBENCH = Path(os.environ.get("FB_DIR", "/fb"))
PUBLIC_PDF = Path(os.environ.get("PUBLIC_PDF", "/public/PEPSICO_2022_10K.pdf"))
TOKEN = re.compile(r"[a-z]+|\d+")
TARGETS = os.environ.get("TARGETS", "AMAZON_2017_10K,3M_2022_10K").split(",")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def load_questions():
    path = FINANCEBENCH / "data/financebench_open_source.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row["doc_name"] in TARGETS]


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


def main() -> None:
    from powercontext.sources.pdf_pages import PDFDocumentInput, parse_pdf_document

    questions = load_questions()
    pages: dict[str, list[str]] = {}
    for name in TARGETS:
        pages[name] = [
            page.text
            for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name)))
        ]
    frequency: Counter[str] = Counter()
    for texts in pages.values():
        for text in texts:
            frequency.update(set(tokenize(text)))
    total = sum(len(texts) for texts in pages.values())

    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        tokens = tokenize(row["question"])
        unique = set(tokens)
        weights = {term: math.log(1 + (total + 1) / (frequency[term] + 1)) for term in unique}
        scored = []
        for index, text in enumerate(texts, start=1):
            counts = Counter(tokenize(text))
            mass = sum(weights[term] for term in counts if term in unique)
            scored.append((mass, index, len(unique & set(counts))))
        scored.sort(key=lambda item: (-item[0], item[1]))
        gold = sorted({int(item["evidence_page_num"]) + 1 for item in row["evidence"]})
        print("=" * 100)
        print(f"{name}  gold pages {gold}")
        print(f"Q: {row['question']}")
        print(f"   query terms ({len(unique)}): {sorted(unique)}")
        for mass, index, covered in scored[:8]:
            mark = "GOLD" if index in gold else "    "
            print(f"  {mark} p{index:<4} mass={mass:6.2f} covered={covered}/{len(unique)}")
        for index in gold:
            if index > len(texts):
                continue
            counts = Counter(tokenize(texts[index - 1]))
            mass = sum(weights[term] for term in counts if term in unique)
            covered = sorted(term for term in counts if term in unique)
            rank = next((position for position, item in enumerate(scored, start=1) if item[1] == index), None)
            print(f"  GOLD p{index:<4} mass={mass:6.2f} covered={len(covered)}/{len(unique)} rank={rank}")
            print(f"        terms: {covered}")
            print(f"        text : {' '.join(texts[index - 1].split())[:320]}")
        print()


if __name__ == "__main__":
    main()
