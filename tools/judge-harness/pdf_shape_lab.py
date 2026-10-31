"""Find a retrieval shape that reaches the PDF evidence-page gate.

Two measurements decided the shape of this search:

  * the evidence pages are the financial statements and the tables the question
    points at - 3M pages 48, 50 and 52 are the income statement, the balance
    sheet and the cash flow statement, and Amazon's question names the balance
    sheet and the profit and loss statement while its evidence pages are 38 and
    40;
  * those pages score badly on the question's terms, because the prose pages of
    MD&A repeat the question's wording, and the Memory admission floor drops a
    candidate whose query-term coverage is below 0.25, which is exactly the
    long questions' evidence pages.

So the candidate pool comes from a query of the question's rarest terms, which
the admission floor keeps, and the ranking then rewards the page whose heading
and best sentence window carry the question's distinctive terms.

This script measures that shape and the simpler baselines side by side.
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
LIMIT = 20
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "based", "by", "for", "from",
    "has", "have", "how", "in", "into", "is", "it", "its", "of", "on", "or", "s",
    "that", "the", "their", "there", "these", "they", "this", "to", "was", "were",
    "what", "when", "which", "who", "why", "with", "within", "would", "your", "you",
    "if", "not", "please", "state", "then", "like", "shown", "using", "show", "use",
    "line", "items", "information", "answer", "address", "question", "round",
    "places", "decimal", "two", "much", "many", "does", "do", "did", "can", "will",
    "about", "above", "below", "between", "into", "out", "over", "under", "each",
    "all", "any", "may", "also", "more", "most", "some", "such", "only", "other",
}


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
    frequency: Counter[str] = Counter()
    for texts in pages.values():
        for text in texts:
            frequency.update(set(tokenize(text)))

    def idf(term: str) -> float:
        return math.log(1 + (total_pages + 1) / (frequency[term] + 1))

    def lines_of(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def sentences_of(text: str) -> list[str]:
        parts = [part.strip() for part in SENTENCE.split(text) if part.strip()]
        return parts or [text]

    def keyword_query(question: str, count: int) -> list[str]:
        terms = [term for term in dict.fromkeys(tokenize(question)) if term not in STOPWORDS]
        terms.sort(key=lambda term: (-idf(term), term))
        return terms[:count]

    def admitted(page_terms: set[str], query: set[str]) -> bool:
        if not query:
            return False
        matched = len(query & page_terms)
        if matched < 2:
            return False
        return matched / len(query) >= 0.25

    def heading_mass(question_terms: set[str], weights: dict[str, float], text: str) -> float:
        head = " ".join(lines_of(text)[:3])
        counts = set(tokenize(head))
        return sum(weights[term] for term in counts if term in question_terms)

    def window_mass(question_terms: set[str], weights: dict[str, float], text: str) -> float:
        best = 0.0
        for sentence in sentences_of(text):
            counts = set(tokenize(sentence))
            mass = sum(weights[term] for term in counts if term in question_terms)
            best = max(best, mass)
        return best

    def page_mass(question_terms: set[str], weights: dict[str, float], text: str) -> float:
        counts = set(tokenize(text))
        return sum(weights[term] for term in counts if term in question_terms)

    def report_preference(question: str) -> str | None:
        query = set(tokenize(question))
        scores = {}
        for document in pages:
            counts = Counter(tokenize(document))
            scores[document] = sum(
                idf(term) * count for term, count in counts.items() if term in query
            )
        best = max(scores, key=lambda document: (scores[document], document))
        if scores[best] <= 0:
            return None
        runner_up = max((value for document, value in scores.items() if document != best), default=0.0)
        if runner_up > 0 and scores[best] < runner_up * 2:
            return None
        return best

    variants = {
        "page": (0.0, 0.0, 1.0),
        "window": (0.0, 1.0, 0.0),
        "heading": (1.0, 0.0, 0.0),
        "heading+window": (1.0, 1.0, 0.0),
        "heading+window+page": (2.0, 1.0, 0.5),
        "window+page": (0.0, 1.0, 0.5),
        "2heading+window+page": (4.0, 1.0, 0.5),
    }
    pool_sizes = (8, 12, 20)
    results: dict[tuple[str, int], dict[str, list[tuple[int, int]]]] = {
        (name, pool): {} for name in variants for pool in pool_sizes
    }

    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        annotated = {
            (name, int(item["evidence_page_num"]) + 1)
            for item in row["evidence"]
            if item.get("evidence_page_num") is not None
        }
        question_terms = set(tokenize(row["question"]))
        weights = {term: idf(term) for term in question_terms}
        chosen = report_preference(row["question"])
        for pool in pool_sizes:
            keywords = set(keyword_query(row["question"], pool))
            admitted_indexes = [
                index
                for index, text in enumerate(texts)
                if admitted(set(tokenize(text)), keywords)
            ]
            for variant, (heading_w, window_w, page_w) in variants.items():
                scored = []
                for index in admitted_indexes:
                    text = texts[index]
                    score = (
                        heading_w * heading_mass(question_terms, weights, text)
                        + window_w * window_mass(question_terms, weights, text)
                        + page_w * page_mass(question_terms, weights, text)
                    )
                    scored.append((score, index))
                scored.sort(key=lambda item: (-item[0], item[1]))
                if chosen is not None:
                    scored.sort(key=lambda item: (name != chosen, -item[0], item[1]))
                returned = {(name, index + 1) for _score, index in scored[:LIMIT]}
                results[(variant, pool)].setdefault(name, []).append(
                    (len(annotated & returned), len(annotated))
                )

    print(f"{'variant':<24}{'pool':>5}{'overall':>9}{'worst':>8}   groups")
    best = None
    for (variant, pool), groups in sorted(results.items()):
        total_hit = sum(a for rows in groups.values() for a, _ in rows)
        total_annotated = sum(b for rows in groups.values() for _, b in rows)
        worst = 1.0
        detail = []
        for name in DOCUMENTS:
            rows = groups.get(name, [])
            hit = sum(a for a, _ in rows)
            total = sum(b for _, b in rows)
            value = hit / total if total else 0.0
            worst = min(worst, value)
            detail.append(f"{name.split('_')[0]}={value:.2f}")
        flag = "PASS" if worst >= 0.70 else "fail"
        print(
            f"{variant:<24}{pool:>5}{total_hit / max(1, total_annotated):>9.4f}{worst:>8.4f}   "
            f"{flag} " + " ".join(detail)
        )
        if worst >= 0.70 and (best is None or total_hit / max(1, total_annotated) > best[0]):
            best = (total_hit / max(1, total_annotated), variant, pool)
    print()
    print(f"best passing shape: {best}")


if __name__ == "__main__":
    main()
