"""Where do the annotated evidence pages actually sit?

The window score and the native MATCH ordering both fail most report groups, so
before trying another ranking this script checks the two things that ranking
depends on:

  * is the annotated evidence text present in the parsed page at the annotated
    page number, and how many of its terms survive the parse;
  * where does the gold page rank, and how well does the page score the
    question's terms at all.
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
DOCUMENTS = (
    "PEPSICO_2022_10K",
    "3M_2022_10K",
    "AMAZON_2017_10K",
    "AMD_2022_10K",
    "BOEING_2022_10K",
)


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def load_questions():
    path = FINANCEBENCH / "data/financebench_open_source.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row["doc_name"] in DOCUMENTS]


def document_bytes(name: str) -> bytes:
    if name == "PEPSICO_2022_10K":
        return PUBLIC_PDF.read_bytes()
    return (FINANCEBENCH / "pdfs" / f"{name}.pdf").read_bytes()


def main() -> None:
    from powercontext.sources.pdf_pages import PDFDocumentInput, parse_pdf_document

    questions = load_questions()
    pages: dict[str, list[str]] = {}
    for name in DOCUMENTS:
        pages[name] = [
            page.text
            for page in parse_pdf_document(PDFDocumentInput(document_id=name, content=document_bytes(name)))
        ]
    print(f"questions: {len(questions)}")

    frequency: Counter[str] = Counter()
    for texts in pages.values():
        for text in texts:
            frequency.update(set(tokenize(text)))
    total_pages = sum(len(texts) for texts in pages.values())

    print("\nevidence text present in the parsed page?")
    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        for item in row["evidence"]:
            number = item.get("evidence_page_num")
            if number is None:
                continue
            page_number = int(number) + 1
            evidence = item.get("evidence_text") or ""
            full = item.get("evidence_text_full_page") or ""
            if page_number > len(texts):
                print(f"  {name} p{page_number}: OUT OF RANGE ({len(texts)} pages)")
                continue
            page_terms = Counter(tokenize(texts[page_number - 1]))
            for label, wanted in (("sentence", evidence), ("full page", full)):
                if not wanted:
                    continue
                wanted_terms = Counter(tokenize(wanted))
                shared = sum((page_terms & wanted_terms).values())
                ratio = shared / max(1, sum(wanted_terms.values()))
                if label == "sentence":
                    print(
                        f"  {name:<20} p{page_number:<4} sentence overlap={ratio:.3f} "
                        f"page_len={len(page_terms)} q='{row['question'][:48]}'"
                    )

    print("\nhow well does the gold page score the question's terms?")
    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        terms = Counter(tokenize(row["question"]))
        unique = set(terms)
        weights = {term: math.log(1 + (total_pages + 1) / (frequency[term] + 1)) for term in unique}
        gold_numbers = sorted({int(item["evidence_page_num"]) + 1 for item in row["evidence"]})
        for page_number in gold_numbers:
            if page_number > len(texts):
                continue
            counts = Counter(tokenize(texts[page_number - 1]))
            covered = [term for term in counts if term in unique]
            mass = sum(weights[term] for term in covered)
            share = len(covered) / len(unique)
            # the best other page for the same question
            best_other = 0.0
            for index, text in enumerate(texts, start=1):
                if index == page_number:
                    continue
                other = Counter(tokenize(text))
                score = sum(weights[term] for term in other if term in unique)
                best_other = max(best_other, score)
            print(
                f"  {name:<20} p{page_number:<4} covered={len(covered)}/{len(unique)} "
                f"share={share:.2f} mass={mass:.2f} best_other_page={best_other:.2f}"
            )


if __name__ == "__main__":
    main()
