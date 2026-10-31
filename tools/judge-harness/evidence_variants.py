"""Sweep several plausible judge-side sample constructions for context-01.

The task statement fixes the workload shape (24 claims x 3 abstracts, 1400 and
1800 byte budgets, 48 requests) and the scoring formula, but not how the three
abstracts are chosen.  This script builds the request set several ways and
reports the published metrics for each, so the product change can be judged
against every plausible construction instead of one guess.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

COMPETITION = Path(r"D:\Tools\pc-prelim\competition")
SCIFACT = Path(r"D:\Tools\scifact\data")
PRODUCT = Path(r"D:\Tools\pc-prelim")

TOKEN_RE = re.compile(r"[a-z]+|\d+")

VARIANTS = (
    "gold_plus_random",       # annotated document + two random distractors
    "cited_three",            # the claim's three cited documents
    "cited_plus_random",      # cited documents, topped up with random ones
    "all_evidence_docs",      # every annotated document + random fill
)


def load_corpus() -> dict[str, dict]:
    corpus: dict[str, dict] = {}
    for line in (SCIFACT / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            corpus[str(row["doc_id"])] = row
    return corpus


def load_claims(split: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (SCIFACT / f"claims_{split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def document_text(row: dict) -> str:
    return (row["title"] + " " + " ".join(row["abstract"])).strip()


def evidence_spans(row: dict, sentence_indices: list[int]) -> list[tuple[int, int]]:
    abstract = row["abstract"]
    base = len(row["title"]) + 1
    starts: list[int] = []
    cursor = 0
    for sentence in abstract:
        starts.append(cursor)
        cursor += len(sentence) + 1
    spans = []
    for index in sentence_indices:
        if index < len(abstract):
            start = base + starts[index]
            spans.append((start, start + len(abstract[index])))
    return spans


def tokens(text: str) -> Counter[str]:
    return Counter(TOKEN_RE.findall(text.lower()))


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def gold_for(claim: dict, labels: tuple[str, ...]) -> dict[str, list[tuple[int, int]]]:
    gold: dict[str, list[tuple[int, int]]] = {}
    for doc_id, entries in (claim.get("evidence") or {}).items():
        indices = sorted(
            {index for entry in entries if entry.get("label") in labels for index in entry.get("sentences", [])}
        )
        if indices:
            gold[doc_id] = indices
    return gold


def build(variant: str, claims, corpus, count: int, seed: int, labels):
    rng = random.Random(seed)
    all_ids = sorted(corpus)
    cases: list[dict] = []
    gold: dict[str, dict] = {}
    for claim in claims:
        annotation = gold_for(claim, labels)
        if not annotation:
            continue
        cited = [str(cid) for cid in claim.get("cited_doc_ids", []) if str(cid) in corpus]
        if variant == "gold_plus_random":
            if len(annotation) != 1:
                continue
            chosen = list(annotation)
            pool = [cid for cid in all_ids if cid not in annotation]
        elif variant == "cited_three":
            if len(cited) != 3:
                continue
            chosen = cited
            pool = []
        elif variant == "cited_plus_random":
            if len(cited) < 1:
                continue
            chosen = cited[:3]
            pool = [cid for cid in all_ids if cid not in chosen]
        else:  # all_evidence_docs
            chosen = list(annotation)
            pool = [cid for cid in all_ids if cid not in annotation]
        while len(chosen) < 3:
            if not pool:
                break
            pick = rng.choice(pool)
            pool.remove(pick)
            chosen.append(pick)
        if len(chosen) != 3:
            continue
        documents = [{"id": cid, "text": document_text(corpus[cid])} for cid in chosen]
        spans: dict[str, list[tuple[int, int]]] = {}
        for doc_id, indices in annotation.items():
            row = corpus.get(doc_id)
            if row is None:
                continue
            found = evidence_spans(row, indices)
            text = document_text(row)
            if found and max(end for _, end in found) <= len(text):
                spans[doc_id] = found
        if not spans:
            continue
        case_id = f"claim{claim['id']}"
        cases.append(
            {
                "case_id": case_id,
                "query": claim["claim"],
                "documents": documents,
                "max_bytes": 1400,
                "selection": True,
            }
        )
        gold[case_id] = spans
        if len(cases) >= count:
            break
    return cases, gold


def score(cases, gold, results) -> dict:
    rows = []
    for case, result in zip(cases, results, strict=True):
        selected: dict[str, list[tuple[int, int]]] = {}
        selected_parts: list[str] = []
        for fragment in result["fragments"]:
            selected.setdefault(fragment["document_id"], []).append((fragment["start"], fragment["end"]))
            selected_parts.append(fragment["text"])
        evidence_parts: list[str] = []
        complete = True
        for doc_id, spans in gold[result["case_id"]].items():
            merged = merge_intervals(selected.get(doc_id, []))
            for start, end in spans:
                if not any(m_start <= start and end <= m_end for m_start, m_end in merged):
                    complete = False
            source = next(d["text"] for d in case["documents"] if d["id"] == doc_id)
            evidence_parts.extend(source[start:end] for start, end in spans)
        selected_counter = tokens(" ".join(selected_parts))
        evidence_counter = tokens(" ".join(evidence_parts))
        total = sum(evidence_counter.values())
        overlap = sum((selected_counter & evidence_counter).values())
        rows.append(
            {
                "case_id": result["case_id"],
                "recall": (overlap / total) if total else 0.0,
                "complete": complete,
                "bytes": result["bytes"],
                "fragments": len(result["fragments"]),
                "candidates": len(result["candidate_document_ids"]),
            }
        )
    recalls = [row["recall"] for row in rows]
    complete_count = sum(1 for row in rows if row["complete"])
    return {
        "requests": len(rows),
        "mean_recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "complete_requests": complete_count,
        "complete_ratio": complete_count / len(rows) if rows else 0.0,
        "zero_candidate_requests": sum(1 for row in rows if row["candidates"] == 0),
        "thin_candidate_requests": sum(1 for row in rows if row["candidates"] < 3),
        "cases": rows,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--split", default="train")
    parser.add_argument("--labels", nargs="+", default=["SUPPORT"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(PRODUCT / "src"))
    sys.path.insert(0, str(COMPETITION))
    spec = importlib.util.spec_from_file_location(
        "selection_runner", COMPETITION / "challenges/context-01-evidence-selection/acceptance/runner.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    corpus = load_corpus()
    claims = load_claims(args.split)
    report: dict[str, object] = {}

    for variant in VARIANTS:
        cases, gold = build(variant, claims, corpus, args.count, args.seed, tuple(args.labels))
        if not cases:
            print(f"[{variant}] 没有可用样本")
            continue
        variant_report: dict[str, object] = {"cases": len(cases), "budgets": {}}
        for budget in (1400, 1800):
            for case in cases:
                case["max_bytes"] = budget
            results = await runner.evaluate(cases)
            result = score(cases, gold, results)
            variant_report["budgets"][str(budget)] = {
                "mean_recall": round(result["mean_recall"], 4),
                "complete_ratio": round(result["complete_ratio"], 4),
                "complete_requests": result["complete_requests"],
                "zero_candidates": result["zero_candidate_requests"],
                "thin_candidates": result["thin_candidate_requests"],
            }
            print(
                f"[{variant}] budget {budget}: recall={result['mean_recall']:.4f} "
                f"(>=0.65)  complete={result['complete_requests']}/{result['requests']}="
                f"{result['complete_ratio']:.4f} (>=0.40)  "
                f"zero_cand={result['zero_candidate_requests']} thin_cand={result['thin_candidate_requests']}",
                flush=True,
            )
        report[variant] = variant_report

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
