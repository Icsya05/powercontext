"""Can a phrase-aware score reach the PDF evidence-page gate?

The native full-text index tokenises on whitespace, so a distinctive phrase of
the question - "days payable outstanding", "unadjusted EBITDA", "primary
customers", "capital-intensive" - only contributes as separate words.  The
pages that answer a financial question often carry that phrase verbatim while
other pages merely carry its words.

This script scores pages with the IDF weighted presence of the question's
bigrams and trigrams, with and without the unigram terms, and measures the
evidence-page Recall@20 per report group.
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
LIMIT = 20


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def ngrams(tokens: list[str], size: int) -> list[str]:
    return [" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)]


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

    # corpus level document frequency for unigrams and ngrams
    unigram_df: Counter[str] = Counter()
    bigram_df: Counter[str] = Counter()
    trigram_df: Counter[str] = Counter()
    page_ngrams: dict[str, list[set[str]]] = {}
    page_bigrams: dict[str, list[set[str]]] = {}
    for name, texts in pages.items():
        page_ngrams[name] = []
        page_bigrams[name] = []
        for text in texts:
            tokens = tokenize(text)
            unigrams = set(tokens)
            bigrams = set(ngrams(tokens, 2))
            trigrams = set(ngrams(tokens, 3))
            unigram_df.update(unigrams)
            bigram_df.update(bigrams)
            trigram_df.update(trigrams)
            page_ngrams[name].append(unigrams)
            page_bigrams[name].append(bigrams)

    def report_preference(question: str) -> str | None:
        query = set(tokenize(question))
        scores = {}
        for document in pages:
            counts = Counter(tokenize(document))
            scores[document] = sum(
                math.log(1 + (len(pages) + 1) / (unigram_df[term] + 1)) * count
                for term, count in counts.items()
                if term in query
            )
        best = max(scores, key=lambda document: (scores[document], document))
        if scores[best] <= 0:
            return None
        runner_up = max((value for document, value in scores.items() if document != best), default=0.0)
        if runner_up > 0 and scores[best] < runner_up * 2:
            return None
        return best

    def score_page(
        query_unigrams: set[str],
        query_bigrams: set[str],
        query_trigrams: set[str],
        weights: dict[str, float],
        page_unigrams: set[str],
        page_bigrams: set[str],
    ) -> float:
        mass = 0.0
        for term in query_unigrams & page_unigrams:
            mass += weights.get("u:" + term, 0.0)
        for gram in query_bigrams & page_bigrams:
            mass += weights.get("b:" + gram, 0.0)
        for gram in query_trigrams:
            tokens = gram.split()
            if all(token in page_unigrams for token in tokens):
                mass += weights.get("t:" + gram, 0.0)
        return mass

    def weights_for(query: str) -> dict[str, float]:
        tokens = tokenize(query)
        weights = {}
        for term in set(tokens):
            weights["u:" + term] = math.log(1 + (total_pages + 1) / (unigram_df[term] + 1))
        for gram in set(ngrams(tokens, 2)):
            weights["b:" + gram] = 3.0 * math.log(1 + (total_pages + 1) / (bigram_df[gram] + 1))
        for gram in set(ngrams(tokens, 3)):
            weights["t:" + gram] = 2.0 * math.log(1 + (total_pages + 1) / (trigram_df[gram] + 1))
        return weights

    variants = ("unigram", "bigram", "bigram+trigram", "all")
    results: dict[str, dict[str, list[tuple[int, int]]]] = {name: {} for name in variants}
    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        annotated = {
            (name, int(item["evidence_page_num"]) + 1)
            for item in row["evidence"]
            if item.get("evidence_page_num") is not None
        }
        tokens = tokenize(row["question"])
        query_unigrams = set(tokens)
        query_bigrams = set(ngrams(tokens, 2))
        query_trigrams = set(ngrams(tokens, 3))
        chosen = report_preference(row["question"])
        for variant in variants:
            if chosen is not None and chosen != name:
                results[variant].setdefault(name, []).append((0, len(annotated)))
                continue
            weights = weights_for(row["question"])
            if variant == "unigram":
                weights = {key: value for key, value in weights.items() if key.startswith("u:")}
            elif variant == "bigram":
                weights = {key: value for key, value in weights.items() if key[:2] in ("u:", "b:")}
            elif variant == "bigram+trigram":
                weights = {key: value for key, value in weights.items() if not key.startswith("u:") or True}
            scored = []
            for index in range(len(texts)):
                mass = score_page(
                    query_unigrams,
                    query_bigrams,
                    query_trigrams,
                    weights,
                    page_ngrams[name][index],
                    page_bigrams[name][index],
                )
                scored.append((mass, index))
            scored.sort(key=lambda item: (-item[0], item[1]))
            returned = {(name, index + 1) for _mass, index in scored[:LIMIT]}
            results[variant].setdefault(name, []).append((len(annotated & returned), len(annotated)))

    print(f"{'variant':<20}{'overall':>10}{'worst':>9}   groups")
    for variant, groups in results.items():
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
        print(f"{variant:<20}{total_hit / max(1, total_annotated):>10.4f}{worst:>9.4f}   {flag} " + " ".join(detail))


if __name__ == "__main__":
    main()
