"""Can a contiguous page region reach the PDF evidence-page gate?

The annotated evidence pages carry the answer to the question, not the
question's wording: a gold page scores 1.9x worse on the question's terms than
the best other page of the same report.  What the annotation does show is that
the evidence pages of one question cluster - 3M pages 48, 50 and 52, Amazon 38
and 40, PepsiCo 62 and 64, Boeing 8, 10 and 14 - because the answer sits in a
passage.

This script therefore scores a contiguous page region instead of a single
page: it slides a window over the physical page order of the report the
question names and ranks the regions by the score they collect.  Several
variants are measured so the choice is not one knob fitted to the sample.
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

    frequency: Counter[str] = Counter()
    for texts in pages.values():
        for text in texts:
            frequency.update(set(tokenize(text)))
    total_pages = sum(len(texts) for texts in pages.values())

    def page_scores(query: str, texts: list[str]) -> tuple[list[float], list[float]]:
        unique = set(tokenize(query))
        weights = {term: math.log(1 + (total_pages + 1) / (frequency[term] + 1)) for term in unique}
        raw: list[float] = []
        normalised: list[float] = []
        for text in texts:
            counts = Counter(tokenize(text))
            matched = [term for term in counts if term in unique]
            mass = sum(weights[term] for term in matched)
            raw.append(mass)
            length = max(1, len(counts))
            normalised.append(mass / math.sqrt(length))
        return raw, normalised

    def best_window(scores: list[float], width: int) -> list[int]:
        if len(scores) <= width:
            return list(range(len(scores)))
        running = sum(scores[:width])
        best = running
        best_at = 0
        for index in range(width, len(scores)):
            running += scores[index] - scores[index - width]
            if running > best:
                best = running
                best_at = index - width + 1
        return list(range(best_at, best_at + width))

    def smoothed(scores: list[float], width: int) -> list[float]:
        half = width // 2
        out = []
        for index in range(len(scores)):
            low = max(0, index - half)
            high = min(len(scores), index + half + 1)
            out.append(sum(scores[low:high]))
        return out

    def report_preference(question: str) -> str | None:
        query = set(tokenize(question))
        scores = {}
        for document in pages:
            counts = Counter(tokenize(document))
            scores[document] = sum(
                math.log(1 + (len(pages) + 1) / (frequency[term] + 1)) * count
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

    variants = {
        "window-raw": lambda raw, norm: best_window(raw, LIMIT),
        "window-normalised": lambda raw, norm: best_window(norm, LIMIT),
        "smooth-raw-41": lambda raw, norm: sorted(
            range(len(raw)), key=lambda i: (-smoothed(raw, 41)[i], i)
        )[:LIMIT],
        "smooth-normalised-41": lambda raw, norm: sorted(
            range(len(norm)), key=lambda i: (-smoothed(norm, 41)[i], i)
        )[:LIMIT],
        "smooth-raw-21": lambda raw, norm: sorted(
            range(len(raw)), key=lambda i: (-smoothed(raw, 21)[i], i)
        )[:LIMIT],
        "page-raw": lambda raw, norm: sorted(range(len(raw)), key=lambda i: (-raw[i], i))[:LIMIT],
    }

    results: dict[str, dict[str, list[tuple[int, int]]]] = {
        name: {} for name in variants
    }
    for row in questions:
        name = row["doc_name"]
        texts = pages[name]
        annotated = {
            (name, int(item["evidence_page_num"]) + 1)
            for item in row["evidence"]
            if item.get("evidence_page_num") is not None
        }
        raw, normalised = page_scores(row["question"], texts)
        chosen = report_preference(row["question"])
        for variant, select in variants.items():
            if chosen is not None and chosen != name:
                results[variant].setdefault(name, []).append((0, len(annotated)))
                continue
            indexes = select(raw, normalised)
            returned = {(name, index + 1) for index in indexes[:LIMIT]}
            results[variant].setdefault(name, []).append((len(annotated & returned), len(annotated)))

    print(f"{'variant':<26}{'overall':>10}{'worst group':>14}   groups")
    for variant, groups in results.items():
        total_hit = sum(a for rows in groups.values() for a, _ in rows)
        total_annotated = sum(b for rows in groups.values() for _, b in rows)
        detail = []
        worst = 1.0
        for name in DOCUMENTS:
            rows = groups.get(name, [])
            hit = sum(a for a, _ in rows)
            total = sum(b for _, b in rows)
            value = hit / total if total else 0.0
            worst = min(worst, value)
            detail.append(f"{name.split('_')[0]}={value:.2f}")
        flag = "PASS" if worst >= 0.70 else "fail"
        print(
            f"{variant:<26}{total_hit / max(1, total_annotated):>10.4f}{worst:>14.4f}   "
            f"{flag} " + " ".join(detail)
        )


if __name__ == "__main__":
    main()
