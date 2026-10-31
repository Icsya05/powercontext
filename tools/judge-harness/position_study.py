"""Measure where the annotated evidence sits inside its document, and how much
excluding the leading sentence would buy."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PRODUCT = Path(r"D:\Tools\pc-prelim")
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_variants import document_text, evidence_spans, load_claims, load_corpus  # noqa: E402
from powercontext.builtin.runtime.prepared_context import _literal_sentences  # noqa: E402

corpus = load_corpus()
claims = load_claims("train")

position = Counter()
relative = Counter()
sentence_total = []
first_is_gold = 0
total = 0
doc_sentence_counts = Counter()

for claim in claims:
    evidence = claim.get("evidence") or {}
    support = {
        doc_id: entries
        for doc_id, entries in evidence.items()
        if any(entry.get("label") == "SUPPORT" for entry in entries)
    }
    for doc_id, entries in support.items():
        row = corpus.get(doc_id)
        if row is None:
            continue
        text = document_text(row)
        spans = _literal_sentences(text)
        if not spans:
            continue
        indices = sorted({i for entry in entries for i in entry.get("sentences", [])})
        # map the annotation sentence indexes (corpus abstract order) to the
        # entry's sentence spans
        abstract = row["abstract"]
        base = len(row["title"]) + 1
        starts = []
        cursor = 0
        for sentence in abstract:
            starts.append(cursor)
            cursor += len(sentence) + 1
        gold_char_spans = []
        for index in indices:
            if index < len(abstract):
                start = base + starts[index]
                gold_char_spans.append((start, start + len(abstract[index])))
        if not gold_char_spans:
            continue
        total += 1
        doc_sentence_counts[len(spans)] += 1
        sentence_total.append(len(spans))
        for order, (start, end) in enumerate(spans):
            for gold_start, gold_end in gold_char_spans:
                if start <= gold_start and gold_end <= end:
                    position[order] += 1
                    relative[round(order / max(1, len(spans) - 1), 1)] += 1
                    if order == 0:
                        first_is_gold += 1
                    break

print(f"带 SUPPORT 标注的 (claim, doc) 对: {total}")
print(f"证据句落在文档第 0 句（= 标题）的次数: {first_is_gold}  ({first_is_gold / total:.1%})")
print()
print("证据句在文档中的绝对位置分布（句序 → 次数）:")
for index in sorted(position):
    bar = "#" * max(1, position[index] // 8)
    print(f"  第 {index:>3} 句: {position[index]:>5}  {bar}")
print()
print("相对位置（0=首句, 1=末句）分桶:")
for bucket in sorted(relative):
    bar = "#" * max(1, relative[bucket] // 8)
    print(f"  {bucket:>4}: {relative[bucket]:>5}  {bar}")
print()
print("文档句数分布:", dict(sorted(doc_sentence_counts.items())[:12]), "...")
print("平均句数:", sum(sentence_total) / len(sentence_total))
