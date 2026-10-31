"""Can a lexical window score reach the PDF evidence-page gate?

The judged PDF workload is five FinanceBench reports, 1151 pages and 24
questions, and every report group has to reach evidence-page Recall@20 >= 0.70.
The evaluation runs offline and calls no model, so the gate has to be reached
with the text alone.

The native full-text index ranks a page by its MATCH score over the whole
page, and that ranking reaches 0.3438 on this workload: a page carries about a
thousand words while the evidence the question was written from is one
sentence, so the page-level score is diluted.

This script scores a page by its best sentence window instead - the IDF
weighted overlap between the question's terms and one sentence of the page -
and measures the evidence-page Recall@20 per report group, with the report the
question names preferred.
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
SENTENCE = re.compile(r"(?<=[.;:])\s+|\n+")
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
    total_pages = sum(len(texts) for texts in pages.values())
    print(f"questions: {len(questions)} pages: {total_pages}")

    # document frequency over the whole corpus, for the IDF weighting
    frequency: Counter[str] = Counter()
    for texts in pages.values():
        for text in texts:
            frequency.update(set(tokenize(text)))

    def sentences(text: str) -> list[str]:
        parts = [part.strip() for part in SENTENCE.split(text) if part.strip()]
        return parts or [text]

    def page_score(question_terms: list[str], weights: dict[str, float], text: str) -> float:
        best = 0.0
        for sentence in sentences(text):
            counts = Counter(tokenize(sentence))
            if not counts:
                continue
            matched = sum(weights.get(term, 0.0) for term in counts if term in question_terms)
            covered = len([term for term in counts if term in question_terms])
            if not covered:
                continue
            score = matched * (1.0 + math.log(1 + min(counts.values())))
            best = max(best, score)
        return best

    def report_preference(question: str, documents: list[str]) -> str | None:
        query = set(tokenize(question))
        identities = {document: Counter(tokenize(document)) for document in documents}
        total = len(identities)
        scores = {}
        for document, counts in identities.items():
            scores[document] = sum(
                math.log(1 + (total + 1) / (frequency[term] + 1)) * count
                for term, count in counts.items()
                if term in query
            )
        if not scores:
            return None
        best = max(scores, key=lambda document: (scores[document], document))
        if scores[best] <= 0:
            return None
        runner_up = max((value for document, value in scores.items() if document != best), default=0.0)
        if runner_up > 0 and scores[best] < runner_up * 2:
            return None
        return best

    groups: dict[str, list[tuple[int, int]]] = {}
    total_hit = total_annotated = 0
    for row in questions:
        name = row["doc_name"]
        annotated = {
            (name, int(item["evidence_page_num"]) + 1)
            for item in row["evidence"]
            if item.get("evidence_page_num") is not None
        }
        terms = tokenize(row["question"])
        query_terms = set(terms)
        weights = {term: math.log(1 + (total_pages + 1) / (frequency[term] + 1)) for term in query_terms}
        scored = []
        for document, texts in pages.items():
            for index, text in enumerate(texts, start=1):
                scored.append((page_score(terms, weights, text), document, index))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        chosen = report_preference(row["question"], list(pages))
        if chosen is not None:
            scored.sort(key=lambda item: (item[1] != chosen, -item[0], item[1], item[2]))
        returned = {(document, index) for _score, document, index in scored[:20]}
        hit = len(annotated & returned)
        total_hit += hit
        total_annotated += len(annotated)
        groups.setdefault(name, []).append((hit, len(annotated)))
        print(
            f"  {name:<20} hit={hit}/{len(annotated)}  {row['question'][:70]}",
            flush=True,
        )

    print()
    worst = 1.0
    for name, rows in groups.items():
        hit = sum(a for a, _ in rows)
        total = sum(b for _, b in rows)
        value = hit / total if total else 0.0
        worst = min(worst, value)
        flag = "OK " if value >= 0.70 else "FAIL"
        print(f"  {flag} {name:<22} {hit}/{total} = {value:.4f}")
    print()
    print(f"  overall evidence-page Recall@20: {total_hit}/{total_annotated} "
          f"= {total_hit / total_annotated:.4f}")
    print(f"  worst group: {worst:.4f}  (gate 0.70)")


if __name__ == "__main__":
    main()
