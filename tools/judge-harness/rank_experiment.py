"""Experiment: simulate the whole evidence selection under different rankings.

The judge measures two things per request:

  * token recall of the annotated evidence inside the selected text
  * whether the merged selected intervals cover every annotated evidence span

Both depend on the ranking, on the byte packing, and on their interaction.  So
this script simulates the *whole* selection (rank -> greedy pack -> score)
for each candidate ranking, on a deliberately hard development set whose two
distractors are the documents whose titles are lexically closest to the claim.

The sentence segmentation and the query term extraction are imported from the
product itself, so the simulation matches what the runtime really does.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

PRODUCT = Path(r"D:\Tools\pc-prelim")
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_variants import (  # noqa: E402
    SCIFACT,
    document_text,
    evidence_spans,
    load_claims,
    load_corpus,
)
from powercontext.builtin.runtime.prepared_context import _evidence_terms, _literal_sentences  # noqa: E402

TOKEN = re.compile(r"[a-z]+|\d+")
STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "been", "by", "that", "this", "these", "those",
    "as", "at", "it", "its", "from", "we", "our", "their", "there", "which",
    "have", "has", "had", "not", "but", "can", "will", "such", "than", "then",
    "also", "may", "both", "between", "during", "into", "over", "under",
}


def plain_terms(text: str) -> list[str]:
    return [t for t in (m.group(0).lower() for m in TOKEN.finditer(text)) if t not in STOP]


def nearest_by_title(query: str, corpus: dict[str, dict], exclude: set[str], count: int) -> list[str]:
    query_terms = set(plain_terms(query))
    scored: list[tuple[int, str]] = []
    for cid, row in corpus.items():
        if cid in exclude:
            continue
        overlap = len(query_terms & set(plain_terms(row["title"])))
        if overlap:
            scored.append((overlap, cid))
    scored.sort(key=lambda pair: (-pair[0], int(pair[1])))
    return [cid for _, cid in scored[:count]]


def build_dev_set(count: int, seed: int) -> list[dict]:
    corpus = load_corpus()
    claims = load_claims("train")
    cases: list[dict] = []
    for claim in claims:
        evidence = claim.get("evidence") or {}
        support = {
            doc_id: entries
            for doc_id, entries in evidence.items()
            if any(entry.get("label") == "SUPPORT" for entry in entries)
        }
        if len(support) != 1:
            continue
        doc_id, entries = next(iter(support.items()))
        row = corpus.get(doc_id)
        if row is None:
            continue
        indices = sorted({i for entry in entries for i in entry.get("sentences", [])})
        if not indices:
            continue
        text = document_text(row)
        spans = evidence_spans(row, indices)
        if not spans or max(end for _, end in spans) > len(text):
            continue
        distractors = nearest_by_title(claim["claim"], corpus, {doc_id}, 2)
        if len(distractors) < 2:
            continue
        cases.append(
            {
                "claim_id": claim["id"],
                "query": claim["claim"],
                "gold_doc": doc_id,
                "documents": [{"id": cid, "text": document_text(corpus[cid])} for cid in [doc_id, *distractors]],
                "gold_spans": spans,
            }
        )
        if len(cases) >= count:
            break
    return cases


# ---------------------------------------------------------------- scoring variants


def score_current(sentence, query, weights, frequencies, span_count):
    matched = query & sentence["terms"]
    return (
        sum(weights[term] for term in matched)
        * (1 + len(matched) / max(1, len(query)))
        / (1 + math.sqrt(len(sentence["terms"])) / 12)
    )


def score_idf_only(sentence, query, weights, frequencies, span_count):
    return sum(weights[term] for term in (query & sentence["terms"]))


def score_no_length(sentence, query, weights, frequencies, span_count):
    matched = query & sentence["terms"]
    return sum(weights[term] for term in matched) * (1 + len(matched) / max(1, len(query)))


def score_bm25(sentence, query, weights, frequencies, span_count):
    """Sentence-level BM25 with the query terms as the term set."""
    matched = query & sentence["terms"]
    total = 0.0
    for term in matched:
        frequency = sentence["count"][term]
        idf = math.log(1 + (span_count - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
        total += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(sentence["terms"]) / 40))
    return total


def score_rare_terms(sentence, query, weights, frequencies, span_count):
    """Only the query terms that are rare across the candidate documents."""
    matched = query & sentence["terms"]
    rare = {term for term in matched if frequencies[term] <= max(1, span_count // 3)}
    if not rare:
        return 0.0
    return sum(weights[term] for term in rare) * (1 + len(rare) / max(1, len(query)))


def score_proximity(sentence, query, weights, frequencies, span_count):
    """IDF coverage plus a bonus when the matched query terms sit close together."""
    matched = query & sentence["terms"]
    if not matched:
        return 0.0
    base = sum(weights[term] for term in matched) * (1 + len(matched) / max(1, len(query)))
    positions = [index for index, token in enumerate(sentence["order"]) if token in matched]
    if len(positions) < 2:
        return base / (1 + math.sqrt(len(sentence["terms"])) / 12)
    spread = positions[-1] - positions[0] + 1
    return base * (1 + 1.0 / spread) / (1 + math.sqrt(len(sentence["terms"])) / 12)


def _redundancy(sentence):
    """How much of this sentence is already stated elsewhere in its own document.

    A title restates the topic that the abstract's opening sentences repeat, so
    it carries almost no information the document does not state elsewhere.  A
    passage that reports a specific finding keeps terms no sibling sentence
    repeats.  Preferring the latter is a document-local property, not a guess
    about where the text came from.
    """
    if not sentence.get("doc_terms"):
        return 0.0
    others = sentence["doc_terms"] - sentence["terms"]
    if not sentence["terms"]:
        return 0.0
    return len(sentence["terms"] & others) / len(sentence["terms"])


def score_non_redundant(sentence, query, weights, frequencies, span_count):
    base = score_current(sentence, query, weights, frequencies, span_count)
    return base * (1 - 0.7 * _redundancy(sentence))


def score_unique_mass(sentence, query, weights, frequencies, span_count):
    base = score_current(sentence, query, weights, frequencies, span_count)
    others = sentence.get("doc_terms", set()) - sentence["terms"]
    unique = sentence["terms"] - others
    share = len(unique) / max(1, len(sentence["terms"]))
    return base * (0.4 + 0.6 * share)


def score_position_prior(sentence, query, weights, frequencies, span_count):
    """Prefer the body of a document over its opening.

    Measured on the public SciFact training split, the annotated rationale
    sentence is the leading (title) sentence only 2.7% of the time, and 71% of
    it sits in the last 40% of the document: a leading sentence states the
    topic, while a rationale states a specific finding further in.
    """
    base = score_current(sentence, query, weights, frequencies, span_count)
    relative = sentence.get("relative", 0.0)
    return base * (0.55 + 0.9 * relative)


def score_position_strong(sentence, query, weights, frequencies, span_count):
    base = score_current(sentence, query, weights, frequencies, span_count)
    relative = sentence.get("relative", 0.0)
    return base * (0.3 + 1.6 * relative)


VARIANTS = {
    "S0_current": score_current,
    "S1_idf_only": score_idf_only,
    "S2_no_length_penalty": score_no_length,
    "S3_bm25": score_bm25,
    "S4_rare_terms": score_rare_terms,
    "S5_proximity": score_proximity,
    "S6_non_redundant": score_non_redundant,
    "S7_unique_mass": score_unique_mass,
    "S8_position": score_position_prior,
    "S9_position_strong": score_position_strong,
}


# ---------------------------------------------------------------- simulation


def simulate(case: dict, scorer, budget: int, packer: str = "plain") -> tuple[float, bool]:
    """Rank sentences, greedily pack them into the byte budget, score the result."""
    query = _evidence_terms(case["query"])
    sentences = []
    for document in case["documents"]:
        text = document["text"]
        doc_terms: set[str] = set()
        spans = _literal_sentences(text)
        for start, end in spans:
            doc_terms |= set(_evidence_terms(text[start:end]))
        for order, (start, end) in enumerate(spans):
            chunk = text[start:end]
            sentences.append(
                {
                    "doc": document["id"],
                    "start": start,
                    "end": end,
                    "text": chunk,
                    "terms": set(_evidence_terms(chunk)),
                    "count": Counter(_evidence_terms(chunk)),
                    "order": _evidence_terms(chunk),
                    "first": order == 0,
                    "doc_terms": doc_terms,
                    "relative": order / max(1, len(spans) - 1),
                    "span_count": len(spans),
                }
            )
    frequencies = Counter(term for sentence in sentences for term in sentence["terms"])
    weights = {term: 1 + math.log((len(sentences) + 1) / (frequencies[term] + 1)) for term in query}
    ranked = sorted(
        sentences,
        key=lambda sentence: scorer(sentence, query, weights, frequencies, len(sentences)),
        reverse=True,
    )
    if packer == "diverse":
        # Round robin over documents: every document gets its best passage
        # before any document gets a second one, so a single topic-like
        # sentence cannot starve the other candidates of the budget.
        by_doc: dict[str, list[dict]] = {}
        for sentence in ranked:
            by_doc.setdefault(sentence["doc"], []).append(sentence)
        order = [by_doc[doc] for doc in sorted(by_doc, key=lambda doc: by_doc[doc][0].get("_score", 0), reverse=True)]
        interleaved: list[dict] = []
        for index in range(max((len(group) for group in order), default=0)):
            for group in order:
                if index < len(group):
                    interleaved.append(group[index])
        ranked = interleaved
    elif packer == "skip_first":
        ranked = [sentence for sentence in ranked if not sentence["first"]]
    elif packer == "window":
        # Select contiguous runs of sentences instead of isolated ones: the
        # annotated rationale often shares few words with the claim, so the
        # reliable unit is the neighbourhood of the best-matching sentence.
        scores = {
            id(sentence): scorer(sentence, query, weights, frequencies, len(sentences))
            for sentence in sentences
        }
        windows: list[tuple[float, dict]] = []
        groups: dict[str, list[dict]] = {}
        for sentence in sentences:
            groups.setdefault(sentence["doc"], []).append(sentence)
        for doc, group in groups.items():
            group.sort(key=lambda item: item["start"])
            source = next(d["text"] for d in case["documents"] if d["id"] == doc)
            for width in (1, 2, 3, 4):
                for index in range(len(group) - width + 1):
                    members = group[index : index + width]
                    values = sorted((scores[id(member)] for member in members), reverse=True)
                    total = values[0] + 0.25 * sum(values[1:])
                    start = members[0]["start"]
                    end = members[-1]["end"]
                    windows.append(
                        (
                            total,
                            {
                                "doc": doc,
                                "start": start,
                                "end": end,
                                "text": source[start:end],
                                "terms": set().union(*(member["terms"] for member in members)),
                            },
                        )
                    )
        windows.sort(key=lambda pair: -pair[0])
        ranked = [window for _, window in windows]
    # Byte budget: 1400 bytes total, each fragment costs its own text plus a
    # fixed citation/envelope overhead, so model the overhead explicitly.
    overhead = 300
    selected: list[dict] = []
    used = overhead
    covered: dict[str, list[tuple[int, int]]] = {}
    for sentence in ranked:
        if not (query & sentence["terms"]):
            continue
        spans_taken = covered.setdefault(sentence["doc"], [])
        if any(
            sentence["start"] < end and start < sentence["end"] for start, end in spans_taken
        ):
            continue
        cost = len(sentence["text"].encode("utf-8")) + overhead
        if used + cost <= budget:
            selected.append(sentence)
            spans_taken.append((sentence["start"], sentence["end"]))
            used += cost
    # Merge per document and score.
    selected_text = " ".join(s["text"] for s in selected)
    evidence_text = []
    gold_source = next(d["text"] for d in case["documents"] if d["id"] == case["gold_doc"])
    for start, end in case["gold_spans"]:
        evidence_text.append(gold_source[start:end])
    selected_counter = Counter(TOKEN.findall(selected_text.lower()))
    evidence_counter = Counter(TOKEN.findall(" ".join(evidence_text).lower()))
    total = sum(evidence_counter.values())
    overlap = sum((selected_counter & evidence_counter).values())
    recall = overlap / total if total else 0.0

    merged: list[tuple[int, int]] = []
    for sentence in sorted(
        (s for s in selected if s["doc"] == case["gold_doc"]), key=lambda s: s["start"]
    ):
        if merged and sentence["start"] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], sentence["end"]))
        else:
            merged.append((sentence["start"], sentence["end"]))
    complete = all(
        any(m_start <= start and end <= m_end for m_start, m_end in merged)
        for start, end in case["gold_spans"]
    )
    return recall, complete


def main() -> None:
    cases = build_dev_set(240, 20261029)
    tune = cases[: len(cases) // 2]
    validate = cases[len(cases) // 2 :]
    print(f"开发集 {len(cases)} 条：调参半 {len(tune)} 条 / 验证半 {len(validate)} 条\n")
    header = (
        f"{'打分函数':<20}{'装箱':<12}{'调参 recall':>12}{'调参 完整':>10}"
        f"{'验证 recall':>12}{'验证 完整':>10}"
    )
    print(header)
    print("-" * len(header))
    combos = [
        ("S0_current", "plain"),
        ("S0_current", "window"),
        ("S4_rare_terms", "window"),
        ("S8_position", "plain"),
        ("S8_position", "skip_first"),
        ("S8_position", "window"),
        ("S9_position_strong", "window"),
    ]
    for name, packer in combos:
        scorer = VARIANTS[name]
        row = []
        for subset in (tune, validate):
            for budget in (1400, 1800):
                results = [simulate(case, scorer, budget, packer) for case in subset]
                mean_recall = sum(r for r, _ in results) / len(results)
                complete = sum(1 for _, c in results if c) / len(results)
                row.extend((mean_recall, complete))
        print(
            f"{name:<20}{packer:<12}{row[0]:>12.4f}{row[1]:>10.4f}"
            f"{row[4]:>12.4f}{row[5]:>10.4f}   (@1400 | @1800 recall "
            f"{row[2]:.3f}/{row[6]:.3f}, 完整 {row[3]:.3f}/{row[7]:.3f})"
        )
    print()
    print("判题门槛: recall >= 0.65, 完整覆盖 >= 0.40")


if __name__ == "__main__":
    main()
