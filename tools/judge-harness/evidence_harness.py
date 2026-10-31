"""Local replica of the hidden context-01-evidence-selection quality gate.

The task statement publishes both the workload shape and the scoring formula,
and it names the exact upstream dataset (SciFact) and revision.  This harness
therefore reuses the *official* runner from the competition directory, feeds it
real SciFact claims, and scores the result with the published formula:

  * text is lowercased and tokenized with ``[a-z]+|\\d+``
  * a request's token recall is |selected INTERSECT evidence| / |evidence|
    over word-frequency multisets
  * a request is "complete" when the merged selected intervals cover every
    annotated evidence character span

Judge thresholds: mean recall >= 0.65, complete requests >= 40% of 48.
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


def load_corpus() -> dict[str, dict]:
    corpus: dict[str, dict] = {}
    for line in (SCIFACT / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            corpus[str(row["doc_id"])] = row
    return corpus


def load_claims(splits: tuple[str, ...]) -> list[dict]:
    claims: list[dict] = []
    for split in splits:
        path = SCIFACT / f"claims_{split}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                claims.append(json.loads(line))
    return claims


def document_text(corpus_row: dict) -> str:
    """Exactly what the official runner builds: title + " " + joined abstract."""
    return (corpus_row["title"] + " " + " ".join(corpus_row["abstract"])).strip()


def evidence_spans(corpus_row: dict, sentence_indices: list[int]) -> list[tuple[int, int]]:
    """Map SciFact sentence indices onto character spans of the document text."""
    abstract = corpus_row["abstract"]
    title = corpus_row["title"]
    base = len(title) + 1  # the " " separator
    spans: list[tuple[int, int]] = []
    cursor = 0
    starts: list[int] = []
    for sentence in abstract:
        starts.append(cursor)
        cursor += len(sentence) + 1
    for index in sentence_indices:
        if index >= len(abstract):
            continue
        start = base + starts[index]
        end = start + len(abstract[index])
        spans.append((start, end))
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


def build_cases(claims, corpus, count: int, seed: int) -> tuple[list[dict], dict[str, list]]:
    """One case per claim: the annotated document plus distractors, three in total."""
    rng = random.Random(seed)
    all_ids = sorted(corpus)
    cases: list[dict] = []
    gold: dict[str, list] = {}
    for claim in claims:
        evidence = claim.get("evidence") or {}
        support_docs = {
            doc_id: entries
            for doc_id, entries in evidence.items()
            if any(entry.get("label") == "SUPPORT" for entry in entries)
        }
        if len(support_docs) != 1:
            continue
        doc_id, entries = next(iter(support_docs.items()))
        row = corpus.get(doc_id)
        if row is None:
            continue
        sentence_indices = sorted({index for entry in entries for index in entry.get("sentences", [])})
        if not sentence_indices:
            continue
        text = document_text(row)
        spans = evidence_spans(row, sentence_indices)
        if not spans or max(end for _, end in spans) > len(text):
            continue
        others = [cid for cid in all_ids if cid != doc_id and cid not in support_docs]
        if len(others) < 2:
            continue
        chosen = rng.sample(others, 2)
        documents = [{"id": doc_id, "text": text}]
        documents.extend({"id": cid, "text": document_text(corpus[cid])} for cid in chosen)
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
        gold[case_id] = {doc_id: spans}
        if len(cases) >= count:
            break
    return cases, gold


def score(cases, gold, results) -> dict:
    per_case = []
    for case, result in zip(cases, results, strict=True):
        selected_by_doc: dict[str, list[tuple[int, int]]] = {}
        selected_text_parts: list[str] = []
        for fragment in result["fragments"]:
            selected_by_doc.setdefault(fragment["document_id"], []).append(
                (fragment["start"], fragment["end"])
            )
            selected_text_parts.append(fragment["text"])
        evidence_text_parts: list[str] = []
        complete = True
        for doc_id, spans in gold[result["case_id"]].items():
            merged = merge_intervals(selected_by_doc.get(doc_id, []))
            for start, end in spans:
                if not any(m_start <= start and end <= m_end for m_start, m_end in merged):
                    complete = False
            # the annotated characters come from the document text itself
            source = next(doc["text"] for doc in case["documents"] if doc["id"] == doc_id)
            evidence_text_parts.extend(source[start:end] for start, end in spans)
        selected_counter = tokens(" ".join(selected_text_parts))
        evidence_counter = tokens(" ".join(evidence_text_parts))
        overlap = sum((selected_counter & evidence_counter).values())
        total = sum(evidence_counter.values())
        recall = overlap / total if total else 0.0
        per_case.append(
            {
                "case_id": result["case_id"],
                "recall": recall,
                "complete": complete,
                "bytes": result["bytes"],
                "fragments": len(result["fragments"]),
                "candidates": len(result["candidate_document_ids"]),
            }
        )
    recalls = [row["recall"] for row in per_case]
    complete_count = sum(1 for row in per_case if row["complete"])
    return {
        "requests": len(per_case),
        "mean_recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "complete_requests": complete_count,
        "complete_ratio": complete_count / len(per_case) if per_case else 0.0,
        "mean_bytes": sum(row["bytes"] for row in per_case) / len(per_case) if per_case else 0.0,
        "cases": per_case,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--budgets", type=int, nargs="+", default=[1400, 1800])
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--splits", nargs="+", default=["train"])
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
    claims = load_claims(tuple(args.splits))
    cases, gold = build_cases(claims, corpus, args.count, args.seed)
    print(f"built {len(cases)} cases from splits={args.splits}", flush=True)

    summary: dict[str, object] = {"cases": len(cases), "budgets": {}}
    for budget in args.budgets:
        for case in cases:
            case["max_bytes"] = budget
        results = await runner.evaluate(cases)
        report = score(cases, gold, results)
        summary["budgets"][str(budget)] = {
            "requests": report["requests"],
            "mean_recall": round(report["mean_recall"], 4),
            "complete_requests": report["complete_requests"],
            "complete_ratio": round(report["complete_ratio"], 4),
            "mean_bytes": round(report["mean_bytes"], 1),
        }
        print(
            f"budget {budget}: mean_recall={report['mean_recall']:.4f} "
            f"(need >= 0.65)  complete={report['complete_requests']}/{report['requests']} "
            f"= {report['complete_ratio']:.4f} (need >= 0.40)  mean_bytes={report['mean_bytes']:.0f}",
            flush=True,
        )
        if args.out:
            Path(args.out).write_text(
                json.dumps({"summary": summary, "cases": report["cases"]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
